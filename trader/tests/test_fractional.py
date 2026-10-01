"""Fractional shares: parts of a share at Alpaca and in the simulation; whole shares at Schwab and Webull."""
import pandas as pd
import pytest

pytest.importorskip("alpaca")

from aitrader import scanner
from aitrader.brokers import Ledger, Order, PaperBroker
from aitrader.brokers.base import Fill
from aitrader.brokers.live import OrderRejected
from aitrader.config import fractional_allowed
from aitrader.engine import decide_orders
from aitrader.risk import RiskManager, floor_shares, shares
from aitrader.strategies import Momentum
from fakes import make_broker, make_client

DAY = "2026-10-01"


def test_where_parts_of_a_share_are_allowed(cfg):
    cfg["fractional"] = {"enabled": True}
    cfg["paper"]["broker"] = "local"
    assert fractional_allowed(cfg)                                     # the simulation on the Mac
    cfg["secrets"].update(alpaca_paper_key="k", alpaca_paper_secret="s")
    cfg["paper"]["broker"] = "alpaca"
    assert fractional_allowed(cfg)                                     # Alpaca's paper account
    cfg["secrets"].update(webull_app_key="k" * 32, webull_app_secret="s" * 32, webull_env="paper")
    cfg["paper"]["broker"] = "webull"
    assert not fractional_allowed(cfg)                                 # Webull: not confirmed yet
    for broker, ok in (("alpaca", True), ("schwab", False), ("webull", False)):
        cfg["broker"] = broker
        assert fractional_allowed(cfg, live=True) is ok
    cfg["fractional"] = {"enabled": "off"}
    cfg["broker"], cfg["paper"]["broker"] = "alpaca", "local"
    assert not fractional_allowed(cfg) and not fractional_allowed(cfg, live=True)


def test_sizing_buys_part_of_a_pricey_share_at_least_a_dollar():
    whole = RiskManager(max_position_pct=12.5)
    part = RiskManager(max_position_pct=12.5, fractional=True)
    assert whole.position_size(500, 500, 300.0) == 0                   # $62 can't buy a $300 share
    assert part.position_size(500, 500, 300.0) == pytest.approx(0.2083)  # $62.50 of it, 4 decimals, rounded down
    assert part.position_size(500, 500, 10.0) == 6.25
    assert part.position_size(5, 5, 300.0) == 0                        # $0.62 is under Alpaca's $1 minimum
    assert whole.max_share_price(500) == pytest.approx(61.875) and part.max_share_price(500) == float("inf")
    assert floor_shares(2.99999, False) == 2 and floor_shares(0.123456, True) == 0.1234
    assert shares(3.0000000001) == 3 and isinstance(shares(3.0), int) and shares(0.45) == 0.45


def test_the_checkbook_never_keeps_a_rounding_crumb():
    ledger = Ledger(1000.0)
    ledger.apply(Fill(DAY, "NVDA", "BUY", 0.1, 300.0, "buy"))
    ledger.apply(Fill(DAY, "NVDA", "BUY", 0.2, 300.0, "buy"))
    assert ledger.positions["NVDA"].qty == 0.3
    ledger.apply(Fill(DAY, "NVDA", "SELL", 0.1, 310.0, "sell"))
    ledger.apply(Fill(DAY, "NVDA", "SELL", 0.2, 310.0, "sell"))
    assert "NVDA" not in ledger.positions and ledger.cash == pytest.approx(1003.0)


def test_paper_and_the_engine_trade_parts_of_a_share():
    broker = PaperBroker(Ledger(500.0), slippage_pct=0.0, mode="paper-swing")
    risk = RiskManager(max_open_positions=8, max_position_pct=12.5, fractional=True)
    orders = decide_orders(pd.Series({"NVDA": 1.0}), pd.Series({"NVDA": 300.0}), {}, 500.0, 500.0, Momentum(), risk)
    assert orders[0].qty == pytest.approx(0.2083)
    fill = broker.submit(orders[0], DAY)
    assert fill.qty == pytest.approx(0.2083) and broker.positions()["NVDA"].qty == pytest.approx(0.2083)
    sold = broker.submit(Order("NVDA", "SELL", 0.2083, 310.0, "exit"), DAY)
    assert sold.qty == pytest.approx(0.2083) and not broker.positions()                   # under one share sells fine


def test_alpaca_buys_part_of_a_share_and_protects_what_it_can_overnight():
    client = make_client("alpaca")
    swing = make_broker(client, 500, stop_good_till_cancel=True)
    fill = swing.submit(Order("NVDA", "BUY", 1.37, 300.0, "momentum"), DAY)
    buy = client.placed("LIMIT")[0]
    assert buy["qty"] == 1.37 and not buy["gtc"] and fill.qty == 1.37
    stop = client.placed("STOP")[0]
    assert stop["qty"] == 1 and stop["gtc"]                            # overnight stop: the whole share
    fill = swing.submit(Order("AMD", "BUY", 0.45, 150.0, "momentum"), DAY)
    assert fill.qty == 0.45 and len(client.placed("STOP")) == 1        # under one share: the bot watches it itself
    assert not swing.positions()["AMD"].stop_order_id

    day_client = make_client("alpaca")
    day = make_broker(day_client, 500, stop_good_till_cancel=False)
    day.submit(Order("NVDA", "BUY", 1.37, 300.0, "tjr"), DAY)
    stop = day_client.placed("STOP")[0]
    assert stop["qty"] == 1.37 and not stop["gtc"]                     # a one-day stop can cover it all


def test_alpaca_sells_parts_of_a_share_and_matches_its_holdings():
    client = make_client("alpaca", held={"NVDA": 1.37})
    broker = make_broker(client, 500, stop_good_till_cancel=True)
    broker.submit(Order("NVDA", "BUY", 1.37, 300.0, "momentum"), DAY)
    assert broker.reconcile(DAY) == []                                 # 1.37 at Alpaca = 1.37 in the checkbook
    fill = broker.submit(Order("NVDA", "SELL", 1.37, 290.0, "exit", urgent=True), DAY)
    assert fill.qty == 1.37 and "NVDA" not in broker.positions()
    assert client.placed("MARKET")[0]["qty"] == 1.37 and 101 in client.cancelled       # its stop came down first


def test_a_stock_alpaca_wont_split_is_bought_in_whole_shares():
    client = make_client("alpaca")
    client.not_fractionable.add("BRKA")
    broker = make_broker(client, 1000)
    assert broker.submit(Order("BRKA", "BUY", 0.4, 700.0, "momentum"), DAY) is None   # under one share: nothing
    fill = broker.submit(Order("XYZ", "BUY", 2.5, 40.0, "momentum"), DAY)
    assert fill.qty == 2.5
    client.not_fractionable.add("ABC")
    fill = broker.submit(Order("ABC", "BUY", 2.5, 40.0, "momentum"), DAY)
    assert fill.qty == 2 and client.placed("LIMIT")[-1]["qty"] == 2   # rounded down to whole shares


def test_a_one_day_stop_that_ran_out_is_replaced_quietly():
    client = make_client("alpaca", held={"NVDA": 1.37})
    broker = make_broker(client, 500, stop_good_till_cancel=False)
    broker.submit(Order("NVDA", "BUY", 1.37, 300.0, "tjr"), DAY)
    first = broker.positions()["NVDA"].stop_order_id
    client.set_status(first, "EXPIRED")
    assert broker.reconcile("2026-10-02") == []                        # not a problem: it's how one-day stops work
    assert broker.positions()["NVDA"].stop_order_id not in ("", first)


def test_schwab_and_webull_never_get_a_part_of_a_share():
    for kind in ("schwab", "webull"):
        broker = make_broker(make_client(kind), 1000)
        with pytest.raises(OrderRejected, match="whole shares"):
            broker.gw.place("limit_buy", "KO", 1.5, price=10.0)


def test_with_fractional_shares_pricey_stocks_stay_on_the_lists(cfg, monkeypatch):
    from test_scanner import fake_market
    cfg["fractional"] = {"enabled": True}
    market = fake_market()
    market["PRICEY"] = market["ROCKET"] * 50                          # strong, but $3,000 a share
    picks = [r["symbol"] for r in scanner.swing_picks(scanner.score(market, cfg), cfg)]
    assert "PRICEY" in picks
    cfg["fractional"] = {"enabled": False}
    assert "PRICEY" not in [r["symbol"] for r in scanner.swing_picks(scanner.score(market, cfg), cfg)]


def test_reports_show_parts_of_a_share(cfg):
    from aitrader import learning, report
    fills = pd.DataFrame([{"date": DAY, "ticker": "NVDA", "side": "BUY", "qty": 0.2083, "price": 300.0,
                           "realized_pnl": 0.0, "reason": "momentum score 1.00 >= 0.8", "order_id": "a"},
                          {"date": "2026-10-02", "ticker": "NVDA", "side": "SELL", "qty": 0.2083, "price": 310.0,
                           "realized_pnl": 2.08, "reason": "exit", "order_id": "b"}])
    done = report.trades(fills, "swing")
    assert done[0]["qty"] == 0.2083 and done[0]["spent"] == pytest.approx(62.49, abs=0.01)
    assert learning.round_trips(fills)[0]["qty"] == 0.2083
