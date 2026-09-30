"""
brokers/webull_broker.py: how to talk to Webull (its OpenAPI, signed the way Webull's own SDK signs).

Only the Webull-specific translation lives here. All the safety rules (limit orders with a buffer, fill
timeouts, resting stop-losses, never selling twice, budget caps, settled cash) are in live.py and
shared with Alpaca and Schwab.

Like Alpaca, every order carries our own tag (client_order_id "kst..."), written down before it's sent,
so if the internet drops mid-order the bot can ask Webull "did you get order kst...?", and it can
always tell its orders apart from yours.

The same code drives Webull's PAPER environment (test keys, api.sandbox.webull.com) and real money
(api.webull.com); which one comes from the keys (webull_api.environment).
Order formats: webull-openapi-python-sdk 3.0.2 (order_v2: /openapi/trade/stock/order/place, detail,
cancel, open orders) and Webull's own MCP server's response formats.
"""
import uuid

from .live import LiveBroker, OrderRejected

TAG = "kst"
STATUS = {"FILLED": "FILLED", "CANCELLED": "CANCELED", "CANCELED": "CANCELED", "FAILED": "REJECTED",
          "REJECTED": "REJECTED", "EXPIRED": "EXPIRED"}          # anything else: still working


def _price(value: float) -> str:
    return f"{value:.2f}" if value >= 1 else f"{value:.4f}"


def _rows(reply) -> list:
    if isinstance(reply, list):
        return reply
    if isinstance(reply, dict):
        for key in ("data", "orders", "items", "list"):
            if isinstance(reply.get(key), list):
                return reply[key]
    return []


class WebullGateway:
    name = "Webull"
    tag = TAG                                               # only OUR resting stops are ever looked up

    def __init__(self, cfg: dict, account_id: str, token, call=None):
        from .. import webull_api
        self.cfg, self.account_id, self.token = cfg, account_id, token
        self.call = call or webull_api.call
        self.Error = webull_api.WebullError

    def _ask(self, method, path, query=None, body=None, headers=None):
        return self.call(self.cfg, method, path, query=query, body=body, token=self.token, headers=headers)

    def new_client_id(self) -> str:
        return TAG + uuid.uuid4().hex[:29]                  # 32 characters, letters and digits

    def place(self, kind: str, ticker: str, qty: int, price: float = None, gtc: bool = False, client_id=None):
        client_id = client_id or self.new_client_id()
        order = {"client_order_id": client_id, "symbol": ticker, "instrument_type": "EQUITY", "market": "US",
                 "quantity": str(int(qty)), "support_trading_session": "CORE",
                 "side": "BUY" if kind == "limit_buy" else "SELL",
                 "time_in_force": "GTC" if gtc else "DAY", "entrust_type": "QTY"}
        if kind in ("limit_buy", "limit_sell"):
            order.update(order_type="LIMIT", limit_price=_price(price))
        elif kind == "market_sell":
            order["order_type"] = "MARKET"
        else:                                               # stop_sell: a resting stop-loss
            order.update(order_type="STOP_LOSS", stop_price=_price(price))
        body = {"account_id": self.account_id, "new_orders": [order]}
        try:
            reply = self._ask("POST", "/openapi/trade/stock/order/place", body=body, headers={"category": "US_STOCK"})
        except self.Error as e:
            if e.status is not None and 400 <= e.status < 500 and e.status != 429:
                raise OrderRejected(str(e)) from e
            if self.order_by_client_id(client_id):          # did it get through anyway?
                return client_id
            raise
        except Exception:
            if self.order_by_client_id(client_id):
                return client_id
            raise
        if isinstance(reply, dict) and reply.get("error_code") and not reply.get("client_order_id"):
            raise OrderRejected(str(reply.get("message") or reply.get("error_code")))
        return client_id

    def _detail(self, client_id: str) -> dict:
        reply = self._ask("GET", "/openapi/trade/order/detail",
                          query={"account_id": self.account_id, "client_order_id": client_id})
        orders = (reply or {}).get("orders") if isinstance(reply, dict) else None
        return (orders or [reply or {}])[0]

    def order(self, order_id: str) -> dict:
        o = self._detail(order_id)                           # raises on errors: never read as "finished"
        status = str(o.get("status") or "").upper().replace(" ", "_")
        filled = int(float(o.get("filled_quantity") or o.get("total_filled_qty") or 0))
        return {"status": STATUS.get(status, status or "SUBMITTED"), "filled_qty": filled,
                "avg_price": float(o.get("filled_price") or 0)}

    def order_by_client_id(self, client_id: str):
        """Our tag back if Webull has that order, None only if Webull says it doesn't exist."""
        try:
            o = self._detail(client_id)
        except self.Error as e:
            text = str(e).lower()
            if e.status == 404 or "not exist" in text or "not found" in text:
                return None
            raise
        return client_id if o.get("client_order_id") or o.get("status") else None

    def cancel(self, order_id: str):
        try:
            self._ask("POST", "/openapi/trade/stock/order/cancel",
                      body={"account_id": self.account_id, "client_order_id": order_id})
        except self.Error:
            pass                                            # e.g. already filled; the status check tells the truth

    def _balance(self) -> dict:
        reply = self._ask("GET", "/trading/assets/balances/get", query={"account_id": self.account_id})
        assets = (reply or {}).get("account_currency_assets") or []
        usd = next((a for a in assets if str(a.get("currency", "")).upper() == "USD"), assets[0] if assets else {})
        return {**(reply or {}), **usd}

    def cash(self) -> float:
        """What it can spend without borrowing: the smallest of cash, settled cash and buying power."""
        b = self._balance()
        values = [float(b[k]) for k in ("cash_balance", "settled_cash", "buying_power", "total_cash_balance")
                  if b.get(k) not in (None, "")]
        if not values:
            raise RuntimeError("couldn't find the available-cash field in Webull's reply")
        return max(0.0, min(values))

    def holdings(self) -> dict:
        reply = self._ask("GET", "/trading/assets/positions/list", query={"account_id": self.account_id})
        return {p["symbol"]: max(0, int(float(p.get("quantity") or 0))) for p in _rows(reply)
                if p.get("symbol") and str(p.get("instrument_type") or "EQUITY").upper() in ("EQUITY", "STOCK")}

    def find_sell_stops(self, ticker: str) -> list:
        reply = self._ask("GET", "/openapi/trade/order/open", query={"account_id": self.account_id, "page_size": 100})
        found = []
        for item in _rows(reply):
            for o in item.get("orders") or [item]:
                client_id = o.get("client_order_id") or item.get("client_order_id") or ""
                if (o.get("symbol") == ticker and str(o.get("side")).upper() == "SELL"
                        and str(o.get("order_type")).upper() in ("STOP_LOSS", "STOP_LOSS_LIMIT")
                        and client_id.startswith(self.tag)):
                    found.append(client_id)
        return found

    def account_summary(self) -> dict:
        b = self._balance()
        cash = float(b.get("cash_balance") or b.get("total_cash_balance") or 0)
        equity = float(b.get("total_net_liquidation_value") or b.get("total_asset") or cash)
        return {"cash": cash, "equity": equity, "trading_blocked": False}


def connect(cfg: dict, want: str):
    """(account id, approved token) for trading at Webull in `want` ('paper' or 'live'), or a clear error.
    Never asks Webull for a new approval (that needs you: Setup -> Test Webull)."""
    from .. import webull_api
    if not webull_api.has_keys(cfg):
        raise RuntimeError("Webull: no keys yet (Setup -> Webull).")
    env = webull_api.environment(cfg)
    if env != want:
        raise RuntimeError(f"Webull: the saved keys are {webull_api.NAMES[env]} keys, but this needs "
                           f"{webull_api.NAMES[want]} keys (Setup -> Webull).")
    state = webull_api.token_state(cfg, create=False)
    if state.get("status") != "NORMAL":
        raise RuntimeError("Webull: Kestrel isn't approved in the Webull app right now. Setup -> Test Webull, "
                           "then approve it in the Webull app.")
    account = webull_api.pick_account(cfg, webull_api.accounts(cfg, state["token"]))
    return str(account["account_id"]), state["token"]


class WebullBroker(LiveBroker):
    def __init__(self, ledger, cfg: dict, account_id: str, token, call=None, **kw):
        super().__init__(ledger, WebullGateway(cfg, account_id, token, call=call), **kw)
