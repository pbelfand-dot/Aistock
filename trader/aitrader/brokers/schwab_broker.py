"""
brokers/schwab_broker.py: REAL orders through Charles Schwab.

Safety built in:
  * Budget-capped: the bot's Ledger starts at live.max_capital, and it can
    never spend more than that, whatever else is in the account.
  * Only touches what IT bought: it never sells stocks it didn't open.
  * Limit orders only: a hair through the current price so they fill fast,
    but never at a crazy price during a sudden spike.
  * Orders that don't fill within live.fill_timeout_seconds are cancelled.
  * dry_run=True shows exactly what it WOULD send, without sending anything.
"""
import math
import time

from .base import Broker, Fill, Ledger, Order

ACTIVE_STATUSES = {"NEW", "ACCEPTED", "WORKING", "QUEUED", "PENDING_ACTIVATION",
                   "AWAITING_CONDITION", "AWAITING_MANUAL_REVIEW", "AWAITING_RELEASE_TIME"}
DEAD_STATUSES = {"CANCELED", "REJECTED", "EXPIRED", "REPLACED"}


class SchwabBroker(Broker):
    mode = "live"

    def __init__(self, ledger: Ledger, client, account_hash: str, limit_buffer_pct: float = 0.2,
                 fill_timeout_seconds: int = 60, cash_account: bool = True, dry_run: bool = False,
                 log=print):
        super().__init__(ledger)
        self.client = client
        self.account_hash = account_hash
        self.buffer = limit_buffer_pct / 100
        self.timeout = fill_timeout_seconds
        self.cash_account = cash_account
        self.dry_run = dry_run
        self.log = log

    # ---- sending orders ---------------------------------------------------
    def submit(self, order: Order, date: str):
        from schwab.orders.equities import equity_buy_limit, equity_sell_limit
        from schwab.utils import Utils

        if order.side == "BUY":
            limit = round(order.price * (1 + self.buffer), 2)
            qty = min(order.qty, math.floor(self.buying_power(date) / limit))
            spec = equity_buy_limit(order.ticker, qty, limit)
        else:
            limit = round(order.price * (1 - self.buffer), 2)
            held = self.ledger.positions.get(order.ticker)
            qty = min(order.qty, held.qty if held else 0)
            spec = equity_sell_limit(order.ticker, qty, limit)
        if qty < 1:
            return None

        if self.dry_run:
            self.log(f"[DRY RUN] would {order.side} {qty} {order.ticker} limit ${limit}: {order.reason}")
            return None

        resp = self.client.place_order(self.account_hash, spec)
        if resp.is_error:
            self.log(f"Schwab REJECTED {order.side} {order.ticker}: {resp.status_code} {resp.text}")
            return None
        order_id = Utils(self.client, self.account_hash).extract_order_id(resp)
        filled_qty, avg_price = self._wait_for_fill(order_id)
        if filled_qty < 1:
            return None
        fill = Fill(date=date, ticker=order.ticker, side=order.side, qty=filled_qty,
                    price=avg_price, reason=order.reason, order_id=str(order_id))
        return self.ledger.apply(fill)

    def _wait_for_fill(self, order_id):
        """Checks the order every 2 seconds. If time runs out, cancels whatever didn't fill."""
        deadline = time.time() + self.timeout
        data = {}
        while time.time() < deadline:
            data = self.client.get_order(order_id, self.account_hash).json()
            if data.get("status") == "FILLED" or data.get("status") in DEAD_STATUSES:
                break
            time.sleep(2)
        else:
            self.client.cancel_order(order_id, self.account_hash)
            time.sleep(2)
            data = self.client.get_order(order_id, self.account_hash).json()
        return self._filled(data)

    @staticmethod
    def _filled(order_json: dict):
        """(shares filled, average price) from Schwab's order details."""
        qty, cost = 0, 0.0
        for activity in order_json.get("orderActivityCollection", []):
            for leg in activity.get("executionLegs", []):
                qty += leg["quantity"]
                cost += leg["quantity"] * leg["price"]
        return int(qty), (cost / qty if qty else 0.0)

    def cancel_all(self):
        """Cancels EVERY open order in this account, including ones you placed by hand.
        One more reason to give the bot its own Schwab account."""
        resp = self.client.get_orders_for_account(self.account_hash)
        resp.raise_for_status()
        for o in resp.json():
            if o.get("status") in ACTIVE_STATUSES:
                self.client.cancel_order(o["orderId"], self.account_hash)
                self.log(f"Cancelled open order {o['orderId']}")

    # ---- safety check -----------------------------------------------------------
    def reconcile(self) -> list:
        """Compare the bot's ledger with what Schwab says you actually own.
        If Schwab shows FEWER shares than the ledger (e.g. you sold by hand),
        the ledger is corrected down so the bot never sells shares that aren't there."""
        resp = self.client.get_account(self.account_hash, fields=[self.client.Account.Fields.POSITIONS])
        resp.raise_for_status()
        actual = {}
        for p in resp.json()["securitiesAccount"].get("positions", []):
            actual[p["instrument"]["symbol"]] = int(p.get("longQuantity", 0))
        problems = []
        for ticker, pos in list(self.ledger.positions.items()):
            real = actual.get(ticker, 0)
            if real < pos.qty:
                problems.append(f"{ticker}: ledger has {pos.qty}, Schwab has {real}; fixing ledger")
                if real == 0:
                    del self.ledger.positions[ticker]
                else:
                    pos.qty = real
        return problems
