"""Pretend brokers for tests: nothing is ever sent anywhere.

Both fakes share the same behaviour, so every safety test can run against Schwab AND Alpaca.
Orders are remembered in a common shape: {type, side, symbol, qty, price, stop, gtc, client_id}.
  fill=False          LIMIT orders just sit there (WORKING)
  market_fills=False  MARKET orders just sit there (e.g. the market is closed)
  cancel_works=False  cancels are never confirmed
  failing_ids         looking up these orders errors (e.g. HTTP 429)
"""
from types import SimpleNamespace

FINISHED = {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "REPLACED"}
HASH = "ABC123"


class FakeBroker:
    def __init__(self, cash=1000.0, held=None, fill=True, market_fills=True, market_price=10.0):
        self.orders, self.next_id, self.cancelled = {}, 100, []
        self.cash, self.held, self.fill = cash, held or {}, fill
        self.market_fills, self.market_price = market_fills, market_price
        self.cancel_works, self.failing_ids = True, set()

    def _new(self, n: dict) -> str:
        oid = str(self.next_id)
        self.next_id += 1
        o = self.orders[oid] = {"n": n, "status": "WORKING", "legs": []}
        if n["type"] == "LIMIT" and self.fill:
            o["status"], o["legs"] = "FILLED", [(n["qty"], n["price"])]
        if n["type"] == "MARKET" and self.market_fills:
            o["status"], o["legs"] = "FILLED", [(n["qty"], self.market_price)]
        return oid

    def _cancel(self, oid):
        self.cancelled.append(int(oid))
        if self.cancel_works and self.orders[str(oid)]["status"] == "WORKING":
            self.orders[str(oid)]["status"] = "CANCELED"

    def fire(self, oid, price):
        """The order fills at the broker (e.g. a stop triggers while the laptop sleeps)."""
        o = self.orders[str(oid)]
        o["status"], o["legs"] = "FILLED", [(o["n"]["qty"], price)]

    def set_status(self, oid, status):
        self.orders[str(oid)]["status"] = status

    def add_your_own_order(self, order_type, side, symbol, qty, price=None, stop=None):
        """An order YOU placed by hand (not the bot)."""
        return self._new({"type": order_type, "side": side, "symbol": symbol, "qty": qty, "price": price,
                          "stop": stop, "gtc": True, "client_id": None})

    def orders_n(self):
        return [o["n"] for o in self.orders.values()]

    def placed(self, order_type):
        return [o["n"] for o in self.orders.values() if o["n"]["type"] == order_type]

    @staticmethod
    def _filled(o):
        qty = sum(q for q, _ in o["legs"])
        return qty, (sum(q * p for q, p in o["legs"]) / qty if qty else 0.0)


# ---------------------------------------------------------------- Schwab
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


class FakeSchwab(FakeBroker):
    class Account:
        class Fields:
            POSITIONS = "positions"

    def place_order(self, account_hash, spec):
        body = spec.build() if hasattr(spec, "build") else spec
        leg = body["orderLegCollection"][0]
        n = {"type": body["orderType"], "side": leg["instruction"], "symbol": leg["instrument"]["symbol"],
             "qty": leg["quantity"], "price": float(body["price"]) if "price" in body else None,
             "stop": float(body["stopPrice"]) if "stopPrice" in body else None,
             "gtc": body.get("duration") == "GOOD_TILL_CANCEL", "client_id": None, "raw": body}
        oid = self._new(n)
        return FakeResp(201, headers={"Location": f"https://api.schwabapi.com/trader/v1/accounts/{account_hash}/orders/{oid}"})

    def get_order(self, order_id, account_hash):
        if str(order_id) in self.failing_ids:
            return FakeResp(429, {"message": "too many requests"})
        o = self.orders[str(order_id)]
        legs = [{"quantity": q, "price": p} for q, p in o["legs"]]
        return FakeResp(200, {"status": o["status"], "orderActivityCollection": [{"executionLegs": legs}]})

    def cancel_order(self, order_id, account_hash):
        self._cancel(order_id)

    def get_account(self, account_hash, fields=None):
        return FakeResp(200, {"securitiesAccount": {
            "currentBalances": {"cashAvailableForTrading": self.cash},
            "positions": [{"instrument": {"symbol": s}, "longQuantity": float(q)} for s, q in self.held.items()]}})

    def get_orders_for_account(self, account_hash):
        return FakeResp(200, [{"orderId": int(oid), "status": o["status"], "orderType": o["n"]["type"],
                               "orderLegCollection": [{"instrument": {"symbol": o["n"]["symbol"]},
                                                       "instruction": o["n"]["side"], "quantity": o["n"]["qty"]}]}
                              for oid, o in self.orders.items()])


# ---------------------------------------------------------------- Alpaca
ALPACA_STATUS = {"WORKING": "new", "FILLED": "filled", "CANCELED": "canceled", "REPLACED": "replaced",
                 "PENDING_CANCEL": "pending_cancel", "EXPIRED": "expired", "REJECTED": "rejected"}


def alpaca_error(status_code, message="error"):
    from alpaca.common.exceptions import APIError
    http_error = SimpleNamespace(response=SimpleNamespace(status_code=status_code), request=None)
    return APIError(f'{{"code": {status_code}00000, "message": "{message}"}}', http_error)


class FakeAlpaca(FakeBroker):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.drop_response_after_send = False     # the order arrives, but the reply is lost
        self.drop_before_send = False             # the order never arrives
        self.reject_next = None                   # e.g. (403, "insufficient buying power")

    def submit_order(self, req):
        if self.drop_before_send:
            self.drop_before_send = False
            raise ConnectionError("network dropped before the order arrived")
        if self.reject_next:
            code, msg = self.reject_next
            self.reject_next = None
            raise alpaca_error(code, msg)
        n = {"type": req.type.value.upper(), "side": req.side.value.upper(), "symbol": req.symbol,
             "qty": int(req.qty), "price": getattr(req, "limit_price", None), "stop": getattr(req, "stop_price", None),
             "gtc": req.time_in_force.value == "gtc", "client_id": req.client_order_id}
        oid = self._new(n)
        if self.drop_response_after_send:
            self.drop_response_after_send = False
            raise ConnectionError("network dropped after the order arrived")
        return self._obj(oid)

    def _obj(self, oid):
        from alpaca.trading.enums import OrderSide, OrderStatus, OrderType
        o = self.orders[oid]
        qty, avg = self._filled(o)
        return SimpleNamespace(id=oid, client_order_id=o["n"]["client_id"], symbol=o["n"]["symbol"],
                               status=OrderStatus(ALPACA_STATUS[o["status"]]),
                               filled_qty=str(qty), filled_avg_price=str(avg) if qty else None,
                               side=OrderSide(o["n"]["side"].lower()), order_type=OrderType(o["n"]["type"].lower()),
                               type=OrderType(o["n"]["type"].lower()))

    def get_order_by_id(self, order_id):
        if str(order_id) in self.failing_ids:
            raise alpaca_error(429, "too many requests")
        return self._obj(str(order_id))

    def get_order_by_client_id(self, client_id):
        for oid, o in self.orders.items():
            if o["n"]["client_id"] == client_id:
                return self._obj(oid)
        raise alpaca_error(404, "order not found")

    def cancel_order_by_id(self, order_id):
        self._cancel(order_id)

    def get_account(self):
        c = str(self.cash)
        return SimpleNamespace(cash=c, non_marginable_buying_power=c, buying_power=c, equity=c,
                               trading_blocked=False, account_blocked=False, pattern_day_trader=None, daytrade_count=None)

    def get_all_positions(self):
        return [SimpleNamespace(symbol=s, qty=str(q)) for s, q in self.held.items()]

    def get_orders(self, filter=None):
        symbols = set(getattr(filter, "symbols", None) or [])
        return [self._obj(oid) for oid, o in self.orders.items()
                if o["status"] not in FINISHED and (not symbols or o["n"]["symbol"] in symbols)]


def make_client(kind, **kw):
    return FakeSchwab(**kw) if kind == "schwab" else FakeAlpaca(**kw)


def make_broker(client, cash=1000, **kw):
    from aitrader.brokers import Ledger
    from aitrader.brokers.alpaca_broker import AlpacaBroker
    from aitrader.brokers.schwab_broker import SchwabBroker
    kw.setdefault("stop_loss_pct", 7)
    kw.setdefault("fill_timeout_seconds", 0)
    recorded = []
    common = dict(cash_account=False, poll_seconds=0, log=lambda m: None, on_fill=recorded.append, **kw)
    if isinstance(client, FakeSchwab):
        broker = SchwabBroker(Ledger(cash), client, HASH, **common)
    else:
        broker = AlpacaBroker(Ledger(cash), client, **common)
    broker.recorded = recorded
    return broker
