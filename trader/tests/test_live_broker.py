"""The real-money broker rules, tested against FAKE Schwab AND FAKE Alpaca (nothing is ever sent anywhere).

Each test is a way real money could go wrong. The rule under test throughout:
the bot stops tracking an order only once the broker confirms it is finished."""
from datetime import datetime

import pandas as pd
import pytest

pytest.importorskip("schwab")
pytest.importorskip("alpaca")

from aitrader.brokers import Order
from aitrader.brokers.base import Fill
from aitrader.brokers.live import UNKNOWN_ID
from fakes import HASH, FakeResp, FakeSchwab, make_broker, make_client


@pytest.fixture(params=["schwab", "alpaca"])
def kind(request):
    return request.param


def broker_for(client, cash=1000, **kw):
    return make_broker(client, cash, **kw)


# ---------------------------------------------------------------- normal trading
def test_buy_sends_a_limit_order_then_leaves_a_resting_stop(kind):
    client = make_client(kind)
    broker = broker_for(client)
    fill = broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    buy = client.placed("LIMIT")[0]
    assert buy["price"] == pytest.approx(10.02) and buy["side"] == "BUY"
    assert fill.qty == 2 and fill.price == pytest.approx(10.02)
    assert broker.recorded == [fill]                                 # saved the moment it happened
    stop = client.placed("STOP")[0]
    assert stop["stop"] == pytest.approx(9.32) and stop["gtc"] and stop["side"] == "SELL"
    assert broker.positions()["KO"].stop_order_id == "101" and broker.ledger.pending == []


def test_never_spends_more_than_schwab_says_is_available(kind):
    client = make_client(kind, cash=45.0)                                   # you spent the rest yourself
    broker = broker_for(client, cash=500)
    broker.submit(Order("KO", "BUY", 20, 10.0, "test"), "2026-10-01")
    assert client.placed("LIMIT")[0]["qty"] == 4   # $45 / $10.02


def test_dry_run_sends_and_changes_nothing(kind):
    client = make_client(kind)
    broker = broker_for(client, dry_run=True)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.orders == {}


def test_unfilled_order_is_cancelled_and_forgotten(kind):
    client = make_client(kind, fill=False)
    broker = broker_for(client)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.cancelled == [100] and broker.ledger.pending == []


def test_selling_takes_down_the_resting_stop_first(kind):
    client = make_client(kind)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    fill = broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02")
    assert 101 in client.cancelled                                   # the stop order
    assert fill.side == "SELL" and fill.price == pytest.approx(10.98) and broker.positions() == {}


def test_urgent_sells_are_market_orders(kind):
    client = make_client(kind, market_price=9.1)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    fill = broker.submit(Order("KO", "SELL", 2, 9.2, "stop-loss", urgent=True), "2026-10-02")
    assert client.placed("MARKET") and fill.price == pytest.approx(9.1)


# ---------------------------------------------------------------- never sell twice
def test_if_the_stop_already_sold_we_record_it_instead_of_selling_again(kind):
    client = make_client(kind)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.fire(101, 9.30)
    fill = broker.submit(Order("KO", "SELL", 2, 9.0, "test"), "2026-10-02")
    assert fill.reason.startswith("stop-loss order filled at") and fill.price == pytest.approx(9.30)
    assert len(client.placed("LIMIT")) == 1                         # no second sell was sent


def test_if_schwab_wont_confirm_the_stop_is_cancelled_we_dont_sell(kind):
    client = make_client(kind)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.cancel_works = False                                      # cancel never confirmed
    assert broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02") is None
    assert len(client.placed("LIMIT")) == 1                         # the sell was NOT sent
    assert broker.positions()["KO"].stop_order_id == "101"           # still tracking the stop


def test_an_error_from_schwab_is_never_mistaken_for_finished(kind):
    client = make_client(kind)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.failing_ids = {"101"}                                     # e.g. HTTP 429 "too many requests"
    assert broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02") is None
    assert len(client.placed("LIMIT")) == 1 and broker.positions()["KO"].stop_order_id == "101"


def test_one_schwab_error_does_not_stop_everything_else(kind):
    client = make_client(kind, held={"KO": 2, "BAC": 2})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")    # stop 101
    broker.submit(Order("BAC", "BUY", 2, 10.0, "test"), "2026-10-01")   # stop 103
    client.failing_ids = {"101"}                                           # KO's stop can't be looked up
    problems = broker.reconcile("2026-10-02")                            # doesn't blow up...
    assert any("KO" in p for p in problems)
    fills = [broker.submit(Order(t, "SELL", 2, 11.0, "kill", urgent=True), "2026-10-02") for t in ("KO", "BAC")]
    assert fills[0] is None and fills[1].ticker == "BAC"                 # ...and BAC still gets sold


def test_a_stop_whose_id_was_lost_is_found_again(kind):
    client = make_client(kind, held={"KO": 2})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")    # stop 101
    broker.positions()["KO"].stop_order_id = UNKNOWN_ID                 # Schwab never told us its id
    broker.reconcile("2026-10-02")
    assert broker.positions()["KO"].stop_order_id == "101" and len(client.placed("STOP")) == 1


def test_shares_gone_with_an_unknown_stop_does_not_get_stuck(kind):
    client = make_client(kind, held={"KO": 2})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.set_status(101, "CANCELED")                            # you cancelled it and sold by hand
    broker.positions()["KO"].stop_order_id = UNKNOWN_ID
    client.held = {}
    broker.reconcile("2026-10-02")
    assert broker.is_flat()


def test_if_you_edit_the_bots_stop_in_schwab_it_uses_yours(kind):
    client = make_client(kind, held={"KO": 2})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")    # stop 101
    client.set_status(101, "REPLACED")                            # you moved the stop price...
    client.add_your_own_order("STOP", "SELL", "KO", 2, stop=9.0)          # ...which made order 102
    broker.reconcile("2026-10-02")
    assert broker.positions()["KO"].stop_order_id == "102" and len(client.placed("STOP")) == 2


# ---------------------------------------------------------------- never left unprotected
def test_a_sell_that_does_not_fill_gets_its_stop_back(kind):
    client = make_client(kind)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.fill = False
    assert broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02") is None
    assert len(client.placed("STOP")) == 2                          # old one cancelled, new one placed
    assert broker.positions()["KO"].stop_order_id == "103"


def test_an_urgent_sell_that_waits_for_the_open_stays_tracked(kind):
    client = make_client(kind, market_fills=False)                          # e.g. kill command at night
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    assert broker.submit(Order("KO", "SELL", 2, 9.0, "kill", urgent=True), "2026-10-01") is None
    assert [p["id"] for p in broker.ledger.pending] == ["102"]       # still tracked, NOT cancelled
    assert 102 not in client.cancelled and len(client.placed("STOP")) == 1   # no new stop (sell is working)
    client.held = {"KO": 2}
    broker.reconcile("2026-10-02")                                   # still working: left alone
    assert [p["id"] for p in broker.ledger.pending] == ["102"]
    client.fire(102, 9.5)
    client.held = {}
    broker.reconcile("2026-10-02")
    assert broker.is_flat() and broker.recorded[-1].side == "SELL"


# ---------------------------------------------------------------- catching up after sleep/crash
def test_reconcile_catches_up_after_the_laptop_was_asleep(kind):
    client = make_client(kind, held={"KO": 2, "BAC": 3, "PFE": 10})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")    # stop id 101
    broker.submit(Order("BAC", "BUY", 3, 10.0, "test"), "2026-10-01")   # stop id 103
    client.fire(101, 9.30)                                               # KO stop fired overnight
    client.held = {"BAC": 3, "PFE": 10}                                  # PFE: YOUR shares
    broker.reconcile("2026-10-02")
    assert (broker.recorded[-1].ticker, broker.recorded[-1].side) == ("KO", "SELL")
    assert set(broker.positions()) == {"BAC"}
    assert "PFE" in broker.blocked                                       # the bot won't touch your stock
    assert broker.submit(Order("PFE", "BUY", 1, 10.0, "test"), "2026-10-02") is None


def test_if_you_sell_the_bots_shares_by_hand_its_stop_is_cleaned_up(kind):
    client = make_client(kind, held={"KO": 5, "BAC": 5})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 5, 10.0, "test"), "2026-10-01")    # stop 101
    broker.submit(Order("BAC", "BUY", 5, 10.0, "test"), "2026-10-01")   # stop 103
    client.held = {"BAC": 2}                                             # you sold all KO and 3 BAC
    broker.reconcile("2026-10-02")
    assert "KO" not in broker.positions() and 101 in client.cancelled   # no orphan stop left behind
    assert 103 in client.cancelled and broker.positions()["BAC"].qty == 2
    new_stop = client.orders[broker.positions()["BAC"].stop_order_id]["n"]
    assert new_stop["qty"] == 2                                          # resized to what's really there


def test_a_late_fill_after_an_unconfirmed_cancel_is_not_lost(kind):
    client = make_client(kind, fill=False)
    broker = broker_for(client)
    client.cancel_works = False
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert [p["id"] for p in broker.ledger.pending] == ["100"]           # still tracked
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None   # no double buy
    client.fire(100, 10.02)                                              # it filled after all
    client.held = {"KO": 2}
    broker.reconcile("2026-10-02")
    assert broker.positions()["KO"].qty == 2 and broker.recorded[-1].side == "BUY"
    assert broker.positions()["KO"].stop_order_id                       # and it's protected


def test_cancel_all_only_touches_the_bots_own_orders(kind):
    client = make_client(kind, fill=False)
    client.add_your_own_order("LIMIT", "BUY", "AAPL", 1, price=100.0)   # id 100: YOUR order
    broker = broker_for(client)
    client.add_your_own_order("LIMIT", "BUY", "KO", 1, price=10.0)      # id 101: the bot's, in flight
    broker.ledger.pending.append({"id": "101", "ticker": "KO", "side": "BUY", "reason": "test"})
    broker.cancel_all("2026-10-02")
    assert client.cancelled == [101] and broker.ledger.pending == []


# ---------------------------------------------------------------- the emergency exit, end to end
def test_emergency_exit_keeps_going_until_the_live_desk_is_really_flat(kind, cfg, tmp_path, monkeypatch):
    import aitrader.alpaca_api as alpaca_api
    import aitrader.schwab_api as schwab_api
    import run
    from aitrader.phases import Phase, current_phase, set_phase
    from aitrader.storage import Store

    client = make_client(kind, held={"KO": 2}, market_fills=False)
    monkeypatch.setattr(schwab_api, "get_client", lambda cfg: client)
    monkeypatch.setattr(schwab_api, "account_hash", lambda client, number: HASH)
    monkeypatch.setattr(alpaca_api, "trading_client", lambda cfg, paper: client)
    cfg["broker"] = kind
    cfg["live"].update(fill_timeout_seconds=0, poll_seconds=0)
    store = Store(tmp_path / "t.sqlite")
    set_phase(store, "swing", Phase.LIVE, "test")
    store.set("live-swing_ledger", {"cash": 480.0, "unsettled": {}, "pending": [], "positions": {
        "KO": {"ticker": "KO", "qty": 2, "avg_cost": 10.0, "opened_on": "2026-09-01", "stop_order_id": ""}}})

    class Prices:
        def load(self, desk, extra=()):
            bars = {"KO": pd.DataFrame({"close": [9.0]}, index=[pd.Timestamp("2026-09-28")])}
            return bars, bars["KO"]

    broker = run.open_broker(cfg, store, "swing", Phase.LIVE, emergency=True)   # places a stop (100)
    run.emergency_stop(cfg, store, "swing", broker, pd.Series({"KO": 9.0}), "2026-09-28", "test")
    assert current_phase(store, "swing") == Phase.LIVE and store.get("halted:swing")   # NOT dropped yet
    assert run.live_not_flat(store, "swing") and store.get("exiting:swing")

    client.fire(101, 9.05)                                           # the market sell fills at the open
    client.held = {}
    message = run.trade_desk(cfg, store, Prices(), "swing", datetime(2026, 9, 28, 11, 0))
    assert "getting out" in message
    assert current_phase(store, "swing") == Phase.PAPER               # now it's flat: back to paper
    assert store.get("halted:swing") and not store.get("exiting:swing")   # stays paused until you resume
    assert store.fills("live-swing")["side"].tolist() == ["SELL"]


def test_schwab_data_adds_todays_live_bar(cfg):
    from aitrader.market_data import MarketData

    now = pd.Timestamp.now(tz="America/New_York")
    yesterday = (now.normalize() - pd.Timedelta(days=1)).tz_localize(None)
    quote = {"KO": {"quote": {"lastPrice": 71.5, "openPrice": 70.0, "highPrice": 72.0, "lowPrice": 69.5,
                              "totalVolume": 1000, "tradeTime": int(now.timestamp() * 1000)}}}

    class QuoteClient:
        def get_quotes(self, symbols):
            return FakeResp(200, quote)

    md = MarketData({**cfg, "data": {**cfg["data"], "source": "schwab"}})
    md._schwab = QuoteClient()
    bars = {"KO": pd.DataFrame({"open": [69.0], "high": [70.0], "low": [68.0], "close": [69.5],
                                "volume": [900.0]}, index=[yesterday])}
    md._add_todays_bar(bars)
    assert len(bars["KO"]) == 2 and bars["KO"]["close"].iloc[-1] == 71.5


# ---------------------------------------------------------------- Alpaca only: its own order tags
def test_alpaca_orders_carry_the_bots_tag():
    client = make_client("alpaca")
    broker_for(client).submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    assert all(o["client_id"].startswith("aitrader-") for o in client.orders_n())


def test_alpaca_order_that_arrived_but_the_reply_was_lost_is_found():
    client = make_client("alpaca")
    client.drop_response_after_send = True
    broker = broker_for(client)
    fill = broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    assert fill and fill.qty == 2 and len(client.placed("LIMIT")) == 1     # found by its tag, not re-sent


def test_alpaca_order_that_never_arrived_is_forgotten_safely():
    client = make_client("alpaca", held={})
    client.drop_before_send = True
    broker = broker_for(client)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert len(broker.ledger.pending) == 1                                  # unsure: remembered by its tag
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None   # no double buy meanwhile
    broker.reconcile("2026-10-01")
    assert broker.ledger.pending == [] and client.orders == {}             # Alpaca never got it: forgotten


def test_alpaca_rejection_leaves_nothing_behind():
    client = make_client("alpaca")
    client.reject_next = (403, "insufficient buying power")
    broker = broker_for(client)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert broker.ledger.pending == [] and broker.positions() == {}


def test_paper_phase_trades_inside_the_alpaca_paper_account(cfg, tmp_path, monkeypatch):
    import aitrader.alpaca_api as alpaca_api
    import run
    from aitrader.brokers.alpaca_broker import AlpacaBroker
    from aitrader.phases import Phase
    from aitrader.storage import Store

    used = {}
    monkeypatch.setattr(alpaca_api, "trading_client", lambda cfg, paper: used.setdefault("paper", paper) and make_client("alpaca"))
    cfg["secrets"].update(alpaca_paper_key="k", alpaca_paper_secret="s")
    broker = run.open_broker(cfg, Store(tmp_path / "t.sqlite"), "swing", Phase.PAPER)
    assert isinstance(broker, AlpacaBroker) and used["paper"] is True
    assert broker.ledger.cash == 5000                                       # swing desk's half of the paper money
    cfg["paper"]["use_broker_paper"] = False
    assert not isinstance(run.open_broker(cfg, Store(tmp_path / "u.sqlite"), "swing", Phase.PAPER), AlpacaBroker)


# ---------------------------------------------------------------- good faith violations (cash accounts)
def test_real_money_cash_account_never_rebuys_with_unsettled_sale_money(kind):
    client = make_client(kind, cash=1000.0)
    broker = broker_for(client, cash=100, cash_account=True, stop_loss_pct=None)
    assert broker.submit(Order("KO", "BUY", 9, 10.0, "buy"), "2026-10-09")            # settled money
    assert broker.submit(Order("KO", "SELL", 9, 10.0, "sell"), "2026-10-09")
    buys_before = len([o for o in client.placed("LIMIT") if o["side"] == "BUY"])
    assert broker.submit(Order("PEP", "BUY", 9, 10.0, "buy"), "2026-10-12") is None   # Columbus Day: not settled
    assert len([o for o in client.placed("LIMIT") if o["side"] == "BUY"]) == buys_before
    assert broker.submit(Order("PEP", "BUY", 9, 10.0, "buy"), "2026-10-13")            # settled


def test_real_money_sale_that_would_be_a_violation_waits_for_settlement(kind):
    notes = []
    client = make_client(kind, cash=1000.0)
    broker = broker_for(client, cash=0, cash_account=True, stop_loss_pct=None, log=notes.append)
    broker.ledger.cash, broker.ledger.unsettled = 100.0, {"2026-10-01": 100.0}
    broker._book(Fill("2026-09-30", "KO", "BUY", 5, 10.0, "bought with unsettled money"))
    client.held["KO"] = 5
    assert broker.submit(Order("KO", "SELL", 5, 9.0, "stop-loss", urgent=True), "2026-09-30") is None
    assert not [o for o in client.orders_n() if o["side"] == "SELL"]                  # nothing sent
    assert any("good faith violation" in n for n in notes)
