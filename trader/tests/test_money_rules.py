"""Risk rules, the ledger (bot's checkbook) and the paper broker."""
import pandas as pd
import pytest

from aitrader.brokers import Fill, Ledger, Order, PaperBroker
from aitrader.engine import decide_orders
from aitrader.risk import RiskManager
from aitrader.strategies import Strategy


class Fixed(Strategy):
    name, buy_above, sell_below = "fixed", 0.6, 0.4


def test_position_size_is_whole_shares_and_capped():
    risk = RiskManager(max_position_pct=20, cash_buffer_pct=1)
    assert risk.position_size(equity=1000, buying_power=1000, price=30) == 6   # $200 cap / $30
    assert risk.position_size(equity=1000, buying_power=100, price=30) == 3    # limited by cash
    assert risk.position_size(equity=1000, buying_power=1000, price=250) == 0  # can't afford 1 share


def test_stop_loss_daily_limit_and_kill_switch():
    risk = RiskManager(stop_loss_pct=7, daily_loss_limit_pct=3, max_drawdown_pct=15)
    assert risk.stop_loss_hit(avg_cost=100, price=93)
    assert not risk.stop_loss_hit(avg_cost=100, price=94)
    assert risk.new_buys_allowed(equity=960, yesterday_equity=1000)[0] is False
    assert risk.new_buys_allowed(equity=980, yesterday_equity=1000)[0] is True
    assert risk.kill_switch_tripped(equity=850, peak_equity=1000)
    assert not risk.kill_switch_tripped(equity=851, peak_equity=1000)


def test_paper_broker_buy_sell_pnl_and_slippage():
    broker = PaperBroker(Ledger(1000), slippage_pct=1.0)
    buy = broker.submit(Order("AAA", "BUY", 5, 100.0, "test"), "2026-01-02")
    assert buy.price == pytest.approx(101.0) and broker.cash() == pytest.approx(495.0)
    sell = broker.submit(Order("AAA", "SELL", 5, 110.0, "test"), "2026-01-05")
    assert sell.price == pytest.approx(108.9)
    assert sell.realized_pnl == pytest.approx((108.9 - 101.0) * 5, abs=0.01)
    assert broker.positions() == {}


def test_paper_broker_never_overspends_or_oversells():
    broker = PaperBroker(Ledger(250), slippage_pct=0)
    fill = broker.submit(Order("AAA", "BUY", 10, 100.0, "test"), "2026-01-02")
    assert fill.qty == 2                                               # only afforded 2
    assert broker.submit(Order("BBB", "SELL", 3, 50.0, "test"), "2026-01-02") is None  # don't own it


def test_cash_account_cannot_spend_unsettled_sale_money_same_day():
    broker = PaperBroker(Ledger(0), slippage_pct=0, cash_account=True)
    broker.ledger.apply(Fill("2026-01-01", "AAA", "BUY", 2, 0.0, "seed"))
    broker.submit(Order("AAA", "SELL", 2, 100.0, "test"), "2026-01-05")
    assert broker.cash() == pytest.approx(200)
    assert broker.buying_power("2026-01-05") == 0          # same day: unsettled
    assert broker.buying_power("2026-01-06") == pytest.approx(200)  # next day: settled


def test_decide_orders_exits_then_ranked_entries():
    ledger = Ledger(1000)
    ledger.apply(Fill("2026-01-01", "OLD", "BUY", 2, 100.0, "seed"))
    ledger.apply(Fill("2026-01-01", "DIP", "BUY", 2, 100.0, "seed"))
    prices = pd.Series({"OLD": 101.0, "DIP": 90.0, "A": 10.0, "B": 10.0, "C": 10.0, "PRICEY": 5000.0})
    scores = pd.Series({"OLD": 0.3, "DIP": 0.5, "A": 0.7, "B": 0.9, "C": 0.5, "PRICEY": 0.95})
    risk = RiskManager(max_open_positions=3, max_position_pct=20, stop_loss_pct=7)
    orders = decide_orders(scores, prices, ledger.positions, ledger.cash, ledger.equity(prices), Fixed(), risk)
    sides = [(o.side, o.ticker) for o in orders]
    assert ("SELL", "OLD") in sides                       # score below sell_below
    assert ("SELL", "DIP") in sides                       # stop-loss (down 10%)
    buys = [t for s, t in sides if s == "BUY"]
    assert buys == ["B", "A"]                             # best score first; PRICEY unaffordable; C too weak


def test_no_new_buys_when_blocked():
    prices = pd.Series({"A": 10.0})
    orders = decide_orders(pd.Series({"A": 0.9}), prices, {}, 1000, 1000, Fixed(), RiskManager(), allow_new_buys=False)
    assert orders == []


def test_stops_only_mode_only_sells_on_stop_loss():
    ledger = Ledger(1000)
    ledger.apply(Fill("2026-01-01", "WEAK", "BUY", 2, 100.0, "seed"))
    ledger.apply(Fill("2026-01-01", "DIP", "BUY", 2, 100.0, "seed"))
    prices = pd.Series({"WEAK": 99.0, "DIP": 90.0, "NEW": 10.0})
    scores = pd.Series({"WEAK": 0.1, "DIP": 0.9, "NEW": 0.99})
    orders = decide_orders(scores, prices, ledger.positions, ledger.cash, 1000, Fixed(), RiskManager(), stops_only=True)
    assert [(o.side, o.ticker) for o in orders] == [("SELL", "DIP")]   # no strategy exits, no buys


def test_max_share_price_for_a_1000_dollar_account():
    # $1,000 split 50/50 -> swing desk $500; 34% per position, 1% cash buffer
    assert RiskManager(max_position_pct=34, cash_buffer_pct=1).max_share_price(500) == pytest.approx(168.3)


def test_old_databases_with_repeated_order_ids_still_open(tmp_path):
    import sqlite3
    from aitrader.storage import SCHEMA, Store
    path = tmp_path / "old.sqlite"
    old = sqlite3.connect(path)
    old.executescript(SCHEMA)
    for side in ("BUY", "SELL"):                     # the old paper broker reused ids like this
        old.execute("INSERT INTO fills (mode, date, ticker, side, qty, price, realized_pnl, reason, order_id) "
                    "VALUES ('paper-day', '2026-09-01', 'SOFI', ?, 1, 10, 0, 'x', 'paper-day-2026-09-01-SOFI')", (side,))
    old.commit()
    old.close()
    assert len(Store(path).fills("paper-day")) == 2
