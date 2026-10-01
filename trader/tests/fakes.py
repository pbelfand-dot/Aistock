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
        self.not_fractionable = set()             # stocks Alpaca won't split into parts of a share

    def submit_order(self, req):
        if self.drop_before_send:
            self.drop_before_send = False
            raise ConnectionError("network dropped before the order arrived")
        if self.reject_next:
            code, msg = self.reject_next
            self.reject_next = None
            raise alpaca_error(code, msg)
        qty = float(req.qty)
        fraction = abs(qty - round(qty)) > 1e-9
        if fraction and req.time_in_force.value != "day":            # like Alpaca: fractional orders are DAY only
            raise alpaca_error(422, "fractional orders must be DAY orders")
        if fraction and req.symbol in self.not_fractionable:
            raise alpaca_error(422, f"asset {req.symbol} is not fractionable")
        n = {"type": req.type.value.upper(), "side": req.side.value.upper(), "symbol": req.symbol,
             "qty": qty if fraction else int(round(qty)), "price": getattr(req, "limit_price", None),
             "stop": getattr(req, "stop_price", None), "gtc": req.time_in_force.value == "gtc",
             "client_id": req.client_order_id}
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

    def get_asset(self, symbol):
        return SimpleNamespace(symbol=symbol, tradable=True, fractionable=symbol not in self.not_fractionable)

    def get_all_positions(self):
        return [SimpleNamespace(symbol=s, qty=str(q)) for s, q in self.held.items()]

    def get_orders(self, filter=None):
        symbols = set(getattr(filter, "symbols", None) or [])
        return [self._obj(oid) for oid, o in self.orders.items()
                if o["status"] not in FINISHED and (not symbols or o["n"]["symbol"] in symbols)]


# ---------------------------------------------------------------- Webull
WEBULL_STATUS = {"WORKING": "SUBMITTED", "FILLED": "FILLED", "CANCELED": "CANCELLED", "REJECTED": "FAILED",
                 "EXPIRED": "EXPIRED", "REPLACED": "CANCELLED"}


class FakeWebull(FakeBroker):
    """Webull's OpenAPI as webull_api.call would answer it (signed requests aren't needed here)."""
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.drop_response_after_send = False
        self.drop_before_send = False
        self.reject_next = None
        self.headers_seen = []

    def _error(self, status, text):
        from aitrader.webull_api import WebullError
        return WebullError(f"{text} (HTTP {status})", status)

    def _find(self, client_id):
        for oid, o in self.orders.items():
            if (o["n"]["client_id"] or oid) == client_id:
                return oid
        return None

    def __call__(self, cfg, method, path, query=None, body=None, token=None, headers=None, **kw):
        query = query or {}
        if path == "/openapi/trade/stock/order/place":
            self.headers_seen.append(headers)
            if self.drop_before_send:
                self.drop_before_send = False
                raise ConnectionError("network dropped before the order arrived")
            if self.reject_next:
                code, msg = self.reject_next
                self.reject_next = None
                raise self._error(code, msg)
            o = body["new_orders"][0]
            kind = {"LIMIT": "LIMIT", "MARKET": "MARKET", "STOP_LOSS": "STOP"}[o["order_type"]]
            n = {"type": kind, "side": o["side"], "symbol": o["symbol"], "qty": int(o["quantity"]),
                 "price": float(o["limit_price"]) if "limit_price" in o else None,
                 "stop": float(o["stop_price"]) if "stop_price" in o else None,
                 "gtc": o["time_in_force"] == "GTC", "client_id": o["client_order_id"], "webull": o}
            self._new(n)
            if self.drop_response_after_send:
                self.drop_response_after_send = False
                raise ConnectionError("network dropped after the order arrived")
            return {"client_order_id": o["client_order_id"]}
        if path == "/openapi/trade/order/detail":
            if query["client_order_id"] in self.failing_ids:
                raise self._error(429, "too many requests")
            oid = self._find(query["client_order_id"])
            if oid is None:
                raise self._error(404, "order not found")
            return self._detail(oid)
        if path == "/openapi/trade/stock/order/cancel":
            self._cancel(self._find(body["client_order_id"]))
            return {"client_order_id": body["client_order_id"]}
        if path == "/trading/assets/balances/get":
            c = str(self.cash)
            return {"total_cash_balance": c, "account_currency_assets": [
                {"currency": "USD", "cash_balance": c, "settled_cash": c, "buying_power": c}]}
        if path == "/trading/assets/positions/list":
            return [{"symbol": s, "quantity": str(q), "instrument_type": "EQUITY"} for s, q in self.held.items()]
        if path == "/openapi/trade/order/open":
            return [self._detail(oid) for oid, o in self.orders.items() if o["status"] not in FINISHED]
        raise AssertionError(f"unexpected Webull call {method} {path}")

    def _detail(self, oid):
        o = self.orders[oid]
        qty, avg = self._filled(o)
        cid = o["n"]["client_id"] or oid
        kind = {"LIMIT": "LIMIT", "MARKET": "MARKET", "STOP": "STOP_LOSS"}.get(o["n"]["type"], o["n"]["type"])
        return {"client_order_id": cid, "orders": [
            {"client_order_id": cid, "symbol": o["n"]["symbol"], "side": o["n"]["side"], "order_type": kind,
             "status": WEBULL_STATUS[o["status"]], "filled_quantity": str(qty), "filled_price": str(avg) if qty else ""}]}


def make_client(kind, **kw):
    return {"schwab": FakeSchwab, "alpaca": FakeAlpaca, "webull": FakeWebull}[kind](**kw)


def make_broker(client, cash=1000, **kw):
    from aitrader.brokers import Ledger
    from aitrader.brokers.alpaca_broker import AlpacaBroker
    from aitrader.brokers.schwab_broker import SchwabBroker
    kw.setdefault("stop_loss_pct", 7)
    kw.setdefault("fill_timeout_seconds", 0)
    recorded = []
    common = {**dict(cash_account=False, poll_seconds=0, log=lambda m: None, on_fill=recorded.append), **kw}
    if isinstance(client, FakeSchwab):
        broker = SchwabBroker(Ledger(cash), client, HASH, **common)
    elif isinstance(client, FakeWebull):
        from aitrader.brokers.webull_broker import WebullBroker
        broker = WebullBroker(Ledger(cash), {"secrets": {}}, "ACCT1", "tok", call=client, **common)
        broker.gw.new_client_id = lambda: str(client.next_id)      # the fake's numbering, like the others
        broker.gw.tag = ""                                         # every sell stop counts, like the others
    else:
        broker = AlpacaBroker(Ledger(cash), client, **common)
    broker.recorded = recorded
    return broker
