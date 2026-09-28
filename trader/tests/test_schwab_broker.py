"""The real-money broker, tested against a FAKE Schwab (nothing is ever sent anywhere).

Each test is a way real money could go wrong. The rule under test throughout:
the bot stops tracking an order only once Schwab confirms it is finished."""
from datetime import datetime

import pandas as pd
import pytest

pytest.importorskip("schwab")

from aitrader.brokers import Ledger, Order
from aitrader.brokers.schwab_broker import SchwabBroker

HASH = "ABC123"


class FakeResp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code, self._data, self.headers, self.text = status, data, headers or {}, ""

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSchwab:
    """A tiny pretend Schwab.
    LIMIT orders fill instantly at their limit (unless fill=False). MARKET orders fill at
    market_price (unless market_fills=False). STOP orders rest until fire(). cancel_works=False
    simulates a cancel Schwab never confirms."""

    class Account:
        class Fields:
            POSITIONS = "positions"

    def __init__(self, cash=1000.0, held=None, fill=True, market_fills=True, market_price=10.0):
        self.orders, self.next_id, self.cancelled = {}, 100, []
        self.cash, self.held, self.fill = cash, held or {}, fill
        self.market_fills, self.market_price = market_fills, market_price
        self.cancel_works, self.get_order_fails = True, False

    def place_order(self, account_hash, spec):
        body = spec.build() if hasattr(spec, "build") else spec
        oid, self.next_id = self.next_id, self.next_id + 1
        qty = body["orderLegCollection"][0]["quantity"]
        o = self.orders[oid] = {"body": body, "status": "WORKING", "legs": []}
        if body["orderType"] == "LIMIT" and self.fill:
            o["status"], o["legs"] = "FILLED", [(qty, float(body["price"]))]
        if body["orderType"] == "MARKET" and self.market_fills:
            o["status"], o["legs"] = "FILLED", [(qty, self.market_price)]
        return FakeResp(201, headers={"Location": f"https://api.schwabapi.com/trader/v1/accounts/{account_hash}/orders/{oid}"})

    def get_order(self, order_id, account_hash):
        if self.get_order_fails:
            return FakeResp(429, {"message": "too many requests"})
        o = self.orders[int(order_id)]
        legs = [{"quantity": q, "price": p} for q, p in o["legs"]]
        return FakeResp(200, {"status": o["status"], "orderActivityCollection": [{"executionLegs": legs}]})

    def cancel_order(self, order_id, account_hash):
        self.cancelled.append(int(order_id))
        if self.cancel_works and self.orders[int(order_id)]["status"] == "WORKING":
            self.orders[int(order_id)]["status"] = "CANCELED"

    def get_account(self, account_hash, fields=None):
        return FakeResp(200, {"securitiesAccount": {
            "currentBalances": {"cashAvailableForTrading": self.cash},
            "positions": [{"instrument": {"symbol": s}, "longQuantity": float(q)} for s, q in self.held.items()]}})

    def fire(self, order_id, price):
        """The order fills at Schwab (e.g. a stop triggers while the laptop sleeps)."""
        o = self.orders[int(order_id)]
        o["status"], o["legs"] = "FILLED", [(o["body"]["orderLegCollection"][0]["quantity"], price)]

    def of_type(self, order_type):
        return [o["body"] for o in self.orders.values() if o["body"]["orderType"] == order_type]


def broker_for(client, cash=1000, **kw):
    kw.setdefault("stop_loss_pct", 7)
    kw.setdefault("fill_timeout_seconds", 0)
    recorded = []
    broker = SchwabBroker(Ledger(cash), client, HASH, cash_account=False, poll_seconds=0,
                          log=lambda m: None, on_fill=recorded.append, **kw)
    broker.recorded = recorded
    return broker


# ---------------------------------------------------------------- normal trading
def test_buy_sends_a_limit_order_then_leaves_a_resting_stop():
    client = FakeSchwab()
    broker = broker_for(client)
    fill = broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    buy = client.of_type("LIMIT")[0]
    assert float(buy["price"]) == pytest.approx(10.02) and buy["orderLegCollection"][0]["instruction"] == "BUY"
    assert fill.qty == 2 and fill.price == pytest.approx(10.02)
    assert broker.recorded == [fill]                                 # saved the moment it happened
    stop = client.of_type("STOP")[0]
    assert float(stop["stopPrice"]) == pytest.approx(9.32) and stop["duration"] == "GOOD_TILL_CANCEL"
    assert broker.positions()["KO"].stop_order_id == "101" and broker.ledger.pending == []


def test_never_spends_more_than_schwab_says_is_available():
    client = FakeSchwab(cash=45.0)                                   # you spent the rest yourself
    broker = broker_for(client, cash=500)
    broker.submit(Order("KO", "BUY", 20, 10.0, "test"), "2026-10-01")
    assert client.of_type("LIMIT")[0]["orderLegCollection"][0]["quantity"] == 4   # $45 / $10.02


def test_dry_run_sends_and_changes_nothing():
    client = FakeSchwab()
    broker = broker_for(client, dry_run=True)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.orders == {}


def test_unfilled_order_is_cancelled_and_forgotten():
    client = FakeSchwab(fill=False)
    broker = broker_for(client)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.cancelled == [100] and broker.ledger.pending == []


def test_selling_takes_down_the_resting_stop_first():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    fill = broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02")
    assert 101 in client.cancelled                                   # the stop order
    assert fill.side == "SELL" and fill.price == pytest.approx(10.98) and broker.positions() == {}


def test_urgent_sells_are_market_orders():
    client = FakeSchwab(market_price=9.1)
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    fill = broker.submit(Order("KO", "SELL", 2, 9.2, "stop-loss", urgent=True), "2026-10-02")
    assert client.of_type("MARKET") and fill.price == pytest.approx(9.1)


# ---------------------------------------------------------------- never sell twice
def test_if_the_stop_already_sold_we_record_it_instead_of_selling_again():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.fire(101, 9.30)
    fill = broker.submit(Order("KO", "SELL", 2, 9.0, "test"), "2026-10-02")
    assert fill.reason == "stop-loss order filled at Schwab" and fill.price == pytest.approx(9.30)
    assert len(client.of_type("LIMIT")) == 1                         # no second sell was sent


def test_if_schwab_wont_confirm_the_stop_is_cancelled_we_dont_sell():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.cancel_works = False                                      # cancel never confirmed
    assert broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02") is None
    assert len(client.of_type("LIMIT")) == 1                         # the sell was NOT sent
    assert broker.positions()["KO"].stop_order_id == "101"           # still tracking the stop


def test_an_error_from_schwab_is_never_mistaken_for_finished():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.get_order_fails = True                                    # e.g. HTTP 429 "too many requests"
    with pytest.raises(RuntimeError):
        broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02")
    assert len(client.of_type("LIMIT")) == 1 and broker.positions()["KO"].stop_order_id == "101"


# ---------------------------------------------------------------- never left unprotected
def test_a_sell_that_does_not_fill_gets_its_stop_back():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.fill = False
    assert broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02") is None
    assert len(client.of_type("STOP")) == 2                          # old one cancelled, new one placed
    assert broker.positions()["KO"].stop_order_id == "103"


def test_an_urgent_sell_that_waits_for_the_open_stays_tracked():
    client = FakeSchwab(market_fills=False)                          # e.g. kill command at night
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    assert broker.submit(Order("KO", "SELL", 2, 9.0, "kill", urgent=True), "2026-10-01") is None
    assert [p["id"] for p in broker.ledger.pending] == ["102"]       # still tracked, NOT cancelled
    assert 102 not in client.cancelled and len(client.of_type("STOP")) == 1   # no new stop (sell is working)
    client.held = {"KO": 2}
    broker.reconcile("2026-10-02")                                   # still working: left alone
    assert [p["id"] for p in broker.ledger.pending] == ["102"]
    client.fire(102, 9.5)
    client.held = {}
    broker.reconcile("2026-10-02")
    assert broker.is_flat() and broker.recorded[-1].side == "SELL"


# ---------------------------------------------------------------- catching up after sleep/crash
def test_reconcile_catches_up_after_the_laptop_was_asleep():
    client = FakeSchwab(held={"KO": 2, "BAC": 3, "PFE": 10})
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


def test_if_you_sell_the_bots_shares_by_hand_its_stop_is_cleaned_up():
    client = FakeSchwab(held={"KO": 5, "BAC": 5})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 5, 10.0, "test"), "2026-10-01")    # stop 101
    broker.submit(Order("BAC", "BUY", 5, 10.0, "test"), "2026-10-01")   # stop 103
    client.held = {"BAC": 2}                                             # you sold all KO and 3 BAC
    broker.reconcile("2026-10-02")
    assert "KO" not in broker.positions() and 101 in client.cancelled   # no orphan stop left behind
    assert 103 in client.cancelled and broker.positions()["BAC"].qty == 2
    new_stop = client.orders[int(broker.positions()["BAC"].stop_order_id)]["body"]
    assert new_stop["orderLegCollection"][0]["quantity"] == 2           # resized to what's really there


def test_a_late_fill_after_an_unconfirmed_cancel_is_not_lost():
    client = FakeSchwab(fill=False)
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


def test_cancel_all_only_touches_the_bots_own_orders():
    client = FakeSchwab(fill=False)
    client.place_order(HASH, _limit_buy("AAPL", 1, 100.0))              # id 100: YOUR order
    broker = broker_for(client)
    client.place_order(HASH, _limit_buy("KO", 1, 10.0))                 # id 101: the bot's, in flight
    broker.ledger.pending.append({"id": "101", "ticker": "KO", "side": "BUY", "reason": "test"})
    broker.cancel_all("2026-10-02")
    assert client.cancelled == [101] and broker.ledger.pending == []


# ---------------------------------------------------------------- the emergency exit, end to end
def test_emergency_exit_keeps_going_until_the_live_desk_is_really_flat(cfg, tmp_path, monkeypatch):
    import aitrader.schwab_api as schwab_api
    import run
    from aitrader.phases import Phase, current_phase, set_phase
    from aitrader.storage import Store

    client = FakeSchwab(held={"KO": 2}, market_fills=False)
    monkeypatch.setattr(schwab_api, "get_client", lambda cfg: client)
    monkeypatch.setattr(schwab_api, "account_hash", lambda client, number: HASH)
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
    assert run.live_not_flat(store, "swing")

    client.fire(101, 9.05)                                           # the market sell fills at the open
    client.held = {}
    message = run.trade_desk(cfg, store, Prices(), "swing", datetime(2026, 9, 28, 11, 0))
    assert "getting out" in message
    assert current_phase(store, "swing") == Phase.PAPER               # now it's flat: back to paper
    assert store.fills("live-swing")["side"].tolist() == ["SELL"]


def _limit_buy(ticker, qty, price):
    from schwab.orders.equities import equity_buy_limit
    return equity_buy_limit(ticker, qty, price)


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
