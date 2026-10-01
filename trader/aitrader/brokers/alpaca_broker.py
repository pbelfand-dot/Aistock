"""
brokers/alpaca_broker.py: how to talk to Alpaca (via the official alpaca-py library).

Only the Alpaca-specific translation lives here. All the safety rules (stops,
never selling twice, budget caps...) are in live.py and shared with Schwab.

Alpaca bonus: every order carries our own tag ("aitrader-..."). The tag is
written down before the order is sent, so even if the internet drops at the
worst moment the bot can ask Alpaca "did you get order aitrader-xyz?". It
also means the bot can always tell its orders apart from yours.

The same code drives Alpaca's PAPER account (fake money, real order handling)
and the LIVE account; only the keys differ.
"""
import uuid

from ..risk import shares
from .live import LiveBroker, OrderRejected

TAG = "aitrader-"


class AlpacaGateway:
    name = "Alpaca"

    def __init__(self, client):
        self.client = client              # alpaca.trading.client.TradingClient
        self._fractionable = {}

    def fractionable(self, ticker: str) -> bool:
        """Alpaca says, stock by stock, whether it can be bought in parts of a share."""
        if ticker not in self._fractionable:
            asset = self.client.get_asset(ticker)
            self._fractionable[ticker] = bool(getattr(asset, "fractionable", False) and asset.tradable)
        return self._fractionable[ticker]

    def new_client_id(self) -> str:
        return TAG + uuid.uuid4().hex[:20]

    def place(self, kind: str, ticker: str, qty: int, price: float = None, gtc: bool = False, client_id=None):
        from alpaca.common.exceptions import APIError
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest, StopOrderRequest

        client_id = client_id or self.new_client_id()
        common = dict(symbol=ticker, qty=qty, side=OrderSide.BUY if kind == "limit_buy" else OrderSide.SELL,
                      time_in_force=TimeInForce.GTC if gtc else TimeInForce.DAY, client_order_id=client_id)
        if kind in ("limit_buy", "limit_sell"):
            request = LimitOrderRequest(limit_price=price, **common)
        elif kind == "market_sell":
            request = MarketOrderRequest(**common)
        else:                             # stop_sell: a resting stop-loss
            request = StopOrderRequest(stop_price=price, **common)
        try:
            return str(self.client.submit_order(request).id)
        except APIError as e:
            status = e.status_code
            if status is not None and 400 <= status < 500 and status != 429:
                raise OrderRejected(_message(e)) from e
            found = self.order_by_client_id(client_id)      # did it get through anyway?
            if found:
                return found
            raise
        except Exception:
            found = self.order_by_client_id(client_id)
            if found:
                return found
            raise

    def order(self, order_id: str) -> dict:
        o = self.client.get_order_by_id(order_id)          # raises on errors: never read as "finished"
        return {"status": _upper(o.status), "filled_qty": shares(float(o.filled_qty or 0)),
                "avg_price": float(o.filled_avg_price or 0)}

    def order_by_client_id(self, client_id: str):
        """The broker's id for our tag, or None if Alpaca never received that order."""
        from alpaca.common.exceptions import APIError
        try:
            return str(self.client.get_order_by_client_id(client_id).id)
        except APIError as e:
            if e.status_code == 404:
                return None
            raise

    def cancel(self, order_id: str):
        from alpaca.common.exceptions import APIError
        try:
            self.client.cancel_order_by_id(order_id)
        except APIError:
            pass                          # e.g. already filled; the status check afterwards tells the truth

    def cash(self) -> float:
        a = self.client.get_account()
        if a.trading_blocked or a.account_blocked:
            raise RuntimeError("Alpaca says trading is blocked on this account")
        values = [float(v) for v in (a.cash, a.non_marginable_buying_power) if v is not None]
        return min(values)                # never borrowed money

    def holdings(self) -> dict:
        return {p.symbol: max(0, shares(float(p.qty))) for p in self.client.get_all_positions()}

    def find_sell_stops(self, ticker: str) -> list:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest
        orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker]))
        return [str(o.id) for o in orders
                if _lower(o.side) == "sell" and _lower(o.order_type or o.type) in ("stop", "stop_limit")]

    def account_summary(self) -> dict:
        a = self.client.get_account()
        return {"cash": float(a.cash), "equity": float(a.equity), "trading_blocked": a.trading_blocked}


def _upper(value) -> str:
    return str(getattr(value, "value", value)).upper()


def _lower(value) -> str:
    return str(getattr(value, "value", value)).lower()


def _message(error) -> str:
    try:
        return f"{error.status_code} {error.message}"
    except Exception:
        return str(error)


class AlpacaBroker(LiveBroker):
    def __init__(self, ledger, client, **kw):
        super().__init__(ledger, AlpacaGateway(client), **kw)
