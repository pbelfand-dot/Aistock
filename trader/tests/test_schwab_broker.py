"""The real-money broker, tested against a FAKE Schwab (nothing is ever sent anywhere)."""
import pandas as pd
import pytest

pytest.importorskip("schwab")

from aitrader.brokers import Fill, Ledger, Order
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
        pass


class FakeSchwab:
    """A tiny pretend Schwab: LIMIT orders fill instantly at their limit price
    (unless fill=False); STOP orders rest until fire_stop() is called."""

    class Account:
        class Fields:
            POSITIONS = "positions"

    def __init__(self, cash=1000.0, held=None, fill=True):
        self.orders, self.next_id, self.cancelled = {}, 100, []
        self.cash, self.held, self.fill = cash, held or {}, fill

    def place_order(self, account_hash, spec):
        body = spec.build() if hasattr(spec, "build") else spec
        oid, self.next_id = self.next_id, self.next_id + 1
        qty = body["orderLegCollection"][0]["quantity"]
        if body["orderType"] == "LIMIT" and self.fill:
            self.orders[oid] = {"body": body, "status": "FILLED", "legs": [(qty, float(body["price"]))]}
        else:
            self.orders[oid] = {"body": body, "status": "WORKING", "legs": []}
        return FakeResp(201, headers={"Location": f"https://api.schwabapi.com/trader/v1/accounts/{account_hash}/orders/{oid}"})

    def get_order(self, order_id, account_hash):
        o = self.orders[int(order_id)]
        legs = [{"quantity": q, "price": p} for q, p in o["legs"]]
        return FakeResp(200, {"status": o["status"], "orderActivityCollection": [{"executionLegs": legs}]})

    def cancel_order(self, order_id, account_hash):
        self.cancelled.append(int(order_id))
        if self.orders[int(order_id)]["status"] == "WORKING":
            self.orders[int(order_id)]["status"] = "CANCELED"

    def get_account(self, account_hash, fields=None):
        return FakeResp(200, {"securitiesAccount": {
            "currentBalances": {"cashAvailableForTrading": self.cash},
            "positions": [{"instrument": {"symbol": s}, "longQuantity": float(q)} for s, q in self.held.items()]}})

    def fire_stop(self, order_id, price):
        o = self.orders[int(order_id)]
        o["status"], o["legs"] = "FILLED", [(o["body"]["orderLegCollection"][0]["quantity"], price)]

    def by_type(self, order_type):
        return [o["body"] for o in self.orders.values() if o["body"]["orderType"] == order_type]


def broker_for(client, cash=1000, **kw):
    kw.setdefault("stop_loss_pct", 7)
    return SchwabBroker(Ledger(cash), client, HASH, cash_account=False, poll_seconds=0, log=lambda m: None, **kw)


def test_buy_sends_a_limit_order_then_leaves_a_resting_stop():
    client = FakeSchwab()
    broker = broker_for(client)
    fill = broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    buy = client.by_type("LIMIT")[0]
    assert float(buy["price"]) == pytest.approx(10.02) and buy["orderLegCollection"][0]["instruction"] == "BUY"
    assert fill.qty == 2 and fill.price == pytest.approx(10.02)
    stop = client.by_type("STOP")[0]
    assert float(stop["stopPrice"]) == pytest.approx(9.32)          # 7% below $10.02
    assert stop["duration"] == "GOOD_TILL_CANCEL"
    assert broker.positions()["KO"].stop_order_id == "101"
    assert broker.ledger.pending == []


def test_never_spends_more_than_schwab_says_is_available():
    client = FakeSchwab(cash=45.0)                                   # you spent the rest yourself
    broker = broker_for(client, cash=500)
    broker.submit(Order("KO", "BUY", 20, 10.0, "test"), "2026-10-01")
    assert client.by_type("LIMIT")[0]["orderLegCollection"][0]["quantity"] == 4   # $45 / $10.02


def test_dry_run_sends_and_changes_nothing():
    client = FakeSchwab()
    broker = broker_for(client, dry_run=True)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.orders == {}


def test_unfilled_order_is_cancelled_and_forgotten():
    client = FakeSchwab(fill=False)
    broker = broker_for(client, fill_timeout_seconds=0)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.cancelled == [100] and broker.ledger.pending == []


def test_selling_takes_down_the_resting_stop_first():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    fill = broker.submit(Order("KO", "SELL", 2, 11.0, "test"), "2026-10-02")
    assert 101 in client.cancelled                                   # the stop order
    assert fill.side == "SELL" and fill.price == pytest.approx(10.98)
    assert broker.positions() == {}


def test_if_the_stop_already_sold_we_record_it_instead_of_selling_again():
    client = FakeSchwab()
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    client.fire_stop(101, 9.30)
    fill = broker.submit(Order("KO", "SELL", 2, 9.0, "test"), "2026-10-02")
    assert fill.reason == "stop-loss order filled at Schwab" and fill.price == pytest.approx(9.30)
    assert len(client.by_type("LIMIT")) == 1                         # no second sell was sent


def test_reconcile_catches_up_after_the_laptop_was_asleep():
    client = FakeSchwab(held={"KO": 2, "BAC": 3, "PFE": 10})
    broker = broker_for(client)
    broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")    # stop id 101
    broker.submit(Order("BAC", "BUY", 3, 10.0, "test"), "2026-10-01")   # stop id 103
    client.fire_stop(101, 9.30)                                          # KO stop fired overnight
    client.held = {"BAC": 3, "PFE": 10}                                  # PFE: YOUR shares
    problems, fills = broker.reconcile("2026-10-02")
    assert [(f.ticker, f.side) for f in fills] == [("KO", "SELL")]
    assert set(broker.positions()) == {"BAC"}
    assert "PFE" in broker.blocked                                       # the bot won't touch your stock
    assert broker.submit(Order("PFE", "BUY", 1, 10.0, "test"), "2026-10-02") is None


def test_reconcile_finds_an_order_that_filled_during_a_crash():
    client = FakeSchwab(held={"KO": 2})
    broker = broker_for(client, stop_loss_pct=None)
    client.place_order(HASH, _limit_buy("KO", 2, 10.0))                 # id 100, fills
    broker.ledger.pending.append({"id": "100", "ticker": "KO", "side": "BUY", "reason": "test"})
    problems, fills = broker.reconcile("2026-10-02")
    assert fills[0].ticker == "KO" and broker.positions()["KO"].qty == 2 and broker.ledger.pending == []


def test_cancel_all_only_touches_the_bots_own_orders():
    client = FakeSchwab(fill=False)
    client.place_order(HASH, _limit_buy("AAPL", 1, 100.0))              # id 100: YOUR order
    broker = broker_for(client, fill_timeout_seconds=0)
    client.place_order(HASH, _limit_buy("KO", 1, 10.0))                 # id 101: the bot's, in flight
    broker.ledger.pending.append({"id": "101", "ticker": "KO", "side": "BUY", "reason": "test"})
    broker.cancel_all()
    assert client.cancelled == [101]


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


def _limit_buy(ticker, qty, price):
    from schwab.orders.equities import equity_buy_limit
    return equity_buy_limit(ticker, qty, price)
