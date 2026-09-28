"""The real-money broker, tested against a FAKE Schwab connection (nothing is ever sent)."""
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


class FakeClient:
    class Account:
        class Fields:
            POSITIONS = "positions"

    def __init__(self, fill_status="FILLED", legs=((2, 10.01),), held=None):
        self.placed, self.cancelled = [], []
        self.fill_status, self.legs, self.held = fill_status, legs, held or {}

    def place_order(self, account_hash, spec):
        self.placed.append(spec.build())
        return FakeResp(201, headers={"Location": f"https://api.schwabapi.com/trader/v1/accounts/{account_hash}/orders/555"})

    def get_order(self, order_id, account_hash):
        return FakeResp(200, {"status": self.fill_status, "orderActivityCollection": [
            {"executionLegs": [{"quantity": q, "price": p} for q, p in self.legs]}]})

    def cancel_order(self, order_id, account_hash):
        self.cancelled.append(order_id)

    def get_account(self, account_hash, fields=None):
        return FakeResp(200, {"securitiesAccount": {"positions": [
            {"instrument": {"symbol": s}, "longQuantity": float(q)} for s, q in self.held.items()]}})


def test_buy_sends_a_limit_order_and_records_the_real_fill():
    client = FakeClient()
    broker = SchwabBroker(Ledger(100), client, HASH, limit_buffer_pct=0.2, cash_account=False)
    fill = broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01")
    sent = client.placed[0]
    assert sent["orderType"] == "LIMIT" and float(sent["price"]) == pytest.approx(10.02)
    assert sent["orderLegCollection"][0]["instruction"] == "BUY"
    assert fill.qty == 2 and fill.price == pytest.approx(10.01) and fill.order_id == "555"
    assert broker.cash() == pytest.approx(100 - 20.02)


def test_budget_cap_shrinks_the_order():
    client = FakeClient(legs=((9, 10.0),))
    broker = SchwabBroker(Ledger(95), client, HASH, cash_account=False)
    broker.submit(Order("KO", "BUY", 50, 10.0, "test"), "2026-10-01")
    assert client.placed[0]["orderLegCollection"][0]["quantity"] == 9     # $95 budget / $10.02 limit


def test_dry_run_sends_nothing():
    client = FakeClient()
    broker = SchwabBroker(Ledger(100), client, HASH, dry_run=True, log=lambda m: None)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.placed == []


def test_unfilled_order_is_cancelled():
    client = FakeClient(fill_status="WORKING", legs=())
    broker = SchwabBroker(Ledger(100), client, HASH, fill_timeout_seconds=0, cash_account=False)
    assert broker.submit(Order("KO", "BUY", 2, 10.0, "test"), "2026-10-01") is None
    assert client.cancelled == [555]


def test_reconcile_never_trusts_the_ledger_over_schwab():
    ledger = Ledger(0)
    ledger.apply(Fill("2026-10-01", "KO", "BUY", 5, 10.0, "seed"))
    ledger.apply(Fill("2026-10-01", "BAC", "BUY", 3, 10.0, "seed"))
    broker = SchwabBroker(ledger, FakeClient(held={"KO": 2}), HASH)
    problems = broker.reconcile()
    assert len(problems) == 2
    assert broker.positions()["KO"].qty == 2 and "BAC" not in broker.positions()


def test_schwab_data_adds_todays_live_bar(cfg):
    import pandas as pd
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
