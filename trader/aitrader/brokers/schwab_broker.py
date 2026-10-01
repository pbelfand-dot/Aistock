"""
brokers/schwab_broker.py: how to talk to Charles Schwab (via the schwab-py library).

Only the Schwab-specific translation lives here. All the safety rules (stops,
never selling twice, budget caps...) are in live.py and shared with Alpaca.
Schwab has no paper trading, so this is used for real money only.
"""
from ..risk import is_fraction
from .live import LiveBroker, OrderRejected


class SchwabGateway:
    name = "Schwab"

    def __init__(self, client, account_hash: str):
        self.client = client
        self.account_hash = account_hash

    def new_client_id(self):
        return None                       # Schwab doesn't let us tag orders with our own id

    def place(self, kind: str, ticker: str, qty: int, price: float = None, gtc: bool = False, client_id=None):
        if is_fraction(qty):              # never round a real order quietly
            raise OrderRejected("Schwab's API trades whole shares only")
        from schwab.orders.common import Duration, OrderType
        from schwab.orders.equities import equity_buy_limit, equity_sell_limit, equity_sell_market
        from schwab.utils import Utils
        if kind == "limit_buy":
            spec = equity_buy_limit(ticker, qty, price)
        elif kind == "limit_sell":
            spec = equity_sell_limit(ticker, qty, price)
        elif kind == "market_sell":
            spec = equity_sell_market(ticker, qty)
        else:                             # stop_sell: a resting stop-loss
            spec = (equity_sell_market(ticker, qty).set_order_type(OrderType.STOP).set_stop_price(price)
                    .set_duration(Duration.GOOD_TILL_CANCEL if gtc else Duration.DAY))
        resp = self.client.place_order(self.account_hash, spec)
        if resp.is_error:
            raise OrderRejected(f"{resp.status_code} {resp.text}")
        order_id = Utils(self.client, self.account_hash).extract_order_id(resp)
        return None if order_id is None else str(order_id)

    def order(self, order_id: str) -> dict:
        resp = self.client.get_order(order_id, self.account_hash)
        resp.raise_for_status()                       # an error is NOT "finished": stop and retry later
        data = resp.json()
        qty, cost = 0, 0.0
        for activity in data.get("orderActivityCollection", []):
            for leg in activity.get("executionLegs", []):
                qty += leg["quantity"]
                cost += leg["quantity"] * leg["price"]
        return {"status": data.get("status"), "filled_qty": int(qty), "avg_price": cost / qty if qty else 0.0}

    def order_by_client_id(self, client_id):
        return None

    def cancel(self, order_id: str):
        self.client.cancel_order(order_id, self.account_hash)

    def _account(self, positions: bool = False) -> dict:
        fields = [self.client.Account.Fields.POSITIONS] if positions else None
        resp = self.client.get_account(self.account_hash, fields=fields)
        resp.raise_for_status()
        return resp.json()["securitiesAccount"]

    def cash(self) -> float:
        bal = self._account().get("currentBalances", {})
        if "cashAvailableForTrading" in bal:                        # cash accounts: SETTLED money only
            unsettled = float(bal.get("unsettledCash") or 0)       # (spending it risks a good faith violation)
            return max(0.0, float(bal["cashAvailableForTrading"]) - unsettled)
        if "cashBalance" in bal and "availableFunds" in bal:        # margin accounts: no borrowing
            return min(float(bal["cashBalance"]), float(bal["availableFunds"]))
        raise RuntimeError("couldn't find the available-cash field in Schwab's reply")

    def holdings(self) -> dict:
        return {p["instrument"]["symbol"]: int(p.get("longQuantity", 0))
                for p in self._account(positions=True).get("positions", [])}

    def find_sell_stops(self, ticker: str) -> list:
        resp = self.client.get_orders_for_account(self.account_hash)
        resp.raise_for_status()
        return [str(o["orderId"]) for o in resp.json()
                if o.get("orderType") in ("STOP", "STOP_LIMIT")
                and o.get("status") not in {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "REPLACED"}
                and any(leg.get("instrument", {}).get("symbol") == ticker and leg.get("instruction") == "SELL"
                        for leg in o.get("orderLegCollection", []))]


class SchwabBroker(LiveBroker):
    def __init__(self, ledger, client, account_hash: str, **kw):
        super().__init__(ledger, SchwabGateway(client, account_hash), **kw)
