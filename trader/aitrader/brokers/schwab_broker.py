"""
brokers/schwab_broker.py: REAL orders through Charles Schwab.

Built for a SHARED account (your own investing + the bot in one account):
  * Budget-capped: each desk's checkbook (Ledger) starts at its share of
    live.max_capital. It also never spends more than the cash Schwab says is
    actually available, so it can't dip into margin or your other plans.
  * Only touches what IT bought: it never sells shares it didn't buy, and it
    won't buy a stock you already own yourself. Schwab sells a stock's oldest
    shares first by default, so sharing a ticker could sell YOUR shares and
    mess up your taxes.
  * Only cancels ITS OWN orders, never ones you placed by hand.
  * Limit orders only: a hair through the current price so they fill fast,
    but never at a crazy price during a sudden spike. Unfilled orders are cancelled.
  * Resting stop-loss: after every buy it also leaves a stop order at Schwab,
    so if your laptop sleeps or crashes a falling position still gets sold.
  * Crash-safe: orders are written down the moment they're sent. After a
    restart, reconcile() finds out what happened to them.
  * dry_run=True shows exactly what it WOULD send, without sending or changing anything.
"""
import math
import time

from .base import Broker, Fill, Ledger, Order

ACTIVE_STATUSES = {"NEW", "ACCEPTED", "WORKING", "QUEUED", "PENDING_ACTIVATION", "AWAITING_CONDITION",
                   "AWAITING_MANUAL_REVIEW", "AWAITING_RELEASE_TIME", "AWAITING_STOP_CONDITION",
                   "PENDING_ACKNOWLEDGEMENT"}
DEAD_STATUSES = {"CANCELED", "REJECTED", "EXPIRED", "REPLACED"}


class SchwabBroker(Broker):
    def __init__(self, ledger: Ledger, client, account_hash: str, mode: str = "live-swing",
                 limit_buffer_pct: float = 0.2, fill_timeout_seconds: int = 60, cash_account: bool = True,
                 dry_run: bool = False, stop_loss_pct: float = None, stop_good_till_cancel: bool = True,
                 save=lambda: None, log=print, poll_seconds: float = 2):
        super().__init__(ledger)
        self.client = client
        self.account_hash = account_hash
        self.mode = mode
        self.buffer = limit_buffer_pct / 100
        self.timeout = fill_timeout_seconds
        self.cash_account = cash_account
        self.dry_run = dry_run
        self.stop_loss_pct = stop_loss_pct          # None = no resting stops
        self.stop_gtc = stop_good_till_cancel       # swing: stays for days; day desk: expires tonight
        self.save = (lambda: None) if dry_run else save
        self.log = log
        self.poll = poll_seconds
        self.blocked = frozenset()

    # ---- money ------------------------------------------------------------------
    def buying_power(self, today: str) -> float:
        return min(self.ledger.buying_power(today, self.cash_account), self.real_cash())

    def real_cash(self) -> float:
        """Cash Schwab says the account can trade with right now (never margin)."""
        bal = self._account().get("currentBalances", {})
        if "cashAvailableForTrading" in bal:                        # cash accounts
            return max(0.0, float(bal["cashAvailableForTrading"]))
        if "cashBalance" in bal and "availableFunds" in bal:        # margin accounts: no borrowing
            return max(0.0, min(float(bal["cashBalance"]), float(bal["availableFunds"])))
        self.log("Could not read available cash from Schwab; buying nothing to be safe")
        return 0.0

    def _account(self, positions: bool = False) -> dict:
        fields = [self.client.Account.Fields.POSITIONS] if positions else None
        resp = self.client.get_account(self.account_hash, fields=fields)
        resp.raise_for_status()
        return resp.json()["securitiesAccount"]

    # ---- orders -----------------------------------------------------------------
    def submit(self, order: Order, date: str):
        from schwab.orders.equities import equity_buy_limit, equity_sell_limit

        pos = self.ledger.positions.get(order.ticker)
        if order.side == "BUY":
            if order.ticker in self.blocked:
                return None
            limit = round(order.price * (1 + self.buffer), 2)
            qty = min(order.qty, math.floor(self.buying_power(date) / limit))
        else:
            limit = round(order.price * (1 - self.buffer), 2)
            qty = min(order.qty, pos.qty if pos else 0)
        if qty < 1:
            return None
        if self.dry_run:
            self.log(f"[DRY RUN] would {order.side} {qty} {order.ticker} limit ${limit}: {order.reason}")
            return None

        if order.side == "SELL":
            # A stop-loss order may be resting at Schwab for these shares: take it down first.
            stop_fill = self._retire_stop(pos, date)
            if stop_fill:
                return stop_fill                      # the stop already sold (some of) them
            spec = equity_sell_limit(order.ticker, min(qty, pos.qty), limit)
        else:
            spec = equity_buy_limit(order.ticker, qty, limit)

        fill = self._send(spec, order, date)
        held = self.ledger.positions.get(order.ticker)
        if fill and held and self.stop_loss_pct:      # new position, or shares left after a partial sell
            self._place_stop(held)
        return fill

    def _send(self, spec, order: Order, date: str):
        from schwab.utils import Utils
        resp = self.client.place_order(self.account_hash, spec)
        if resp.is_error:
            self.log(f"Schwab REJECTED {order.side} {order.ticker}: {resp.status_code} {resp.text}")
            return None
        order_id = Utils(self.client, self.account_hash).extract_order_id(resp)
        if order_id is None:
            self.log(f"!!! {order.side} {order.ticker} was sent but Schwab returned no order id. CHECK SCHWAB.")
            return None
        order_id = str(order_id)
        self.ledger.pending.append({"id": order_id, "ticker": order.ticker, "side": order.side, "reason": order.reason})
        self.save()                                   # written down BEFORE waiting, in case we crash

        filled_qty, avg_price = self._wait_for_fill(order_id)
        self.ledger.pending = [p for p in self.ledger.pending if p["id"] != order_id]
        fill = None
        if filled_qty >= 1:
            fill = self.ledger.apply(Fill(date=date, ticker=order.ticker, side=order.side, qty=filled_qty,
                                          price=avg_price, reason=order.reason, order_id=order_id))
        self.save()
        return fill

    def _wait_for_fill(self, order_id: str):
        """Checks the order every few seconds. If time runs out, cancels whatever didn't fill."""
        deadline = time.time() + self.timeout
        data = {}
        while time.time() < deadline:
            data = self._order(order_id)
            if data.get("status") == "FILLED" or data.get("status") in DEAD_STATUSES:
                break
            time.sleep(self.poll)
        else:
            data = self._cancel_and_confirm(order_id)
        return self._filled(data)

    def _order(self, order_id: str) -> dict:
        return self.client.get_order(order_id, self.account_hash).json()

    def _cancel_and_confirm(self, order_id: str) -> dict:
        """Cancel, then check what really happened (it may have filled at the last second)."""
        self.client.cancel_order(order_id, self.account_hash)
        data = {}
        for _ in range(5):
            time.sleep(self.poll)
            data = self._order(order_id)
            if data.get("status") not in ACTIVE_STATUSES | {"PENDING_CANCEL"}:
                break
        return data

    @staticmethod
    def _filled(order_json: dict):
        """(shares filled, average price) from Schwab's order details."""
        qty, cost = 0, 0.0
        for activity in order_json.get("orderActivityCollection", []):
            for leg in activity.get("executionLegs", []):
                qty += leg["quantity"]
                cost += leg["quantity"] * leg["price"]
        return int(qty), (cost / qty if qty else 0.0)

    # ---- resting stop-loss orders ---------------------------------------------------
    def _place_stop(self, pos):
        from schwab.orders.common import Duration, OrderType
        from schwab.orders.equities import equity_sell_market
        from schwab.utils import Utils

        if pos.stop_order_id:                         # never leave two stops for the same shares
            self._retire_stop(pos, time.strftime("%Y-%m-%d"))
            if pos.ticker not in self.ledger.positions:
                return
        stop = round(pos.avg_cost * (1 - self.stop_loss_pct / 100), 2)
        spec = (equity_sell_market(pos.ticker, pos.qty)
                .set_order_type(OrderType.STOP).set_stop_price(stop)
                .set_duration(Duration.GOOD_TILL_CANCEL if self.stop_gtc else Duration.DAY))
        resp = self.client.place_order(self.account_hash, spec)
        if resp.is_error:
            self.log(f"!!! could not place a resting stop for {pos.ticker}: {resp.status_code}. "
                     "The bot still checks stops itself every 5 minutes.")
            return
        pos.stop_order_id = str(Utils(self.client, self.account_hash).extract_order_id(resp))
        self.save()
        self.log(f"[{self.mode}] resting stop-loss for {pos.qty} {pos.ticker} at ${stop}")

    def _retire_stop(self, pos, date: str):
        """Take down this position's resting stop. If it already sold the shares, record that sale."""
        if not pos or not pos.stop_order_id:
            return None
        order_id = pos.stop_order_id
        data = self._order(order_id)
        if data.get("status") in ACTIVE_STATUSES:
            data = self._cancel_and_confirm(order_id)
        pos.stop_order_id = ""
        qty, price = self._filled(data)
        fill = None
        if qty >= 1:
            fill = self.ledger.apply(Fill(date=date, ticker=pos.ticker, side="SELL", qty=min(qty, pos.qty),
                                          price=price, reason="stop-loss order filled at Schwab",
                                          order_id=order_id))
        self.save()
        return fill

    def cancel_all(self):
        """Cancel the bot's own unfinished orders (never yours). Resting stops stay in
        place until the bot actually sells, so positions are never left unprotected."""
        for p in list(self.ledger.pending):
            if self._order(p["id"]).get("status") in ACTIVE_STATUSES and not self.dry_run:
                self._cancel_and_confirm(p["id"])
                self.log(f"Cancelled the bot's open order {p['id']} ({p['side']} {p['ticker']})")

    # ---- safety check, run before every trading cycle --------------------------------
    def reconcile(self, date: str) -> tuple:
        """Line the bot's checkbook up with reality. Returns (problems, fills to record)."""
        problems, fills = [], []

        # 1) Orders that were in flight when the bot last stopped (crash, sleep...)
        for p in list(self.ledger.pending):
            data = self._order(p["id"])
            if data.get("status") in ACTIVE_STATUSES:
                if self.dry_run:
                    continue
                data = self._cancel_and_confirm(p["id"])
            qty, price = self._filled(data)
            self.ledger.pending.remove(p)
            if qty >= 1:
                fills.append(self.ledger.apply(Fill(date, p["ticker"], p["side"], qty, price,
                                                    p["reason"] + " (found after a restart)", order_id=p["id"])))
                problems.append(f"order {p['id']} {p['side']} {p['ticker']} filled while the bot was away")

        # 2) Resting stops that fired (or expired) while the bot wasn't watching
        for pos in list(self.ledger.positions.values()):
            if pos.stop_order_id:
                data = self._order(pos.stop_order_id)
                status = data.get("status")
                if status == "FILLED":
                    qty, price = self._filled(data)
                    fills.append(self.ledger.apply(Fill(date, pos.ticker, "SELL", min(qty, pos.qty), price,
                                                        "stop-loss order filled at Schwab",
                                                        order_id=pos.stop_order_id)))
                    pos.stop_order_id = ""
                    continue
                if status in DEAD_STATUSES:
                    problems.append(f"{pos.ticker}: resting stop was {status}; placing a new one")
                    pos.stop_order_id = ""
            if self.stop_loss_pct and not pos.stop_order_id and not self.dry_run:
                self._place_stop(pos)

        # 3) Compare with what Schwab says the account really owns
        actual = {}
        for p in self._account(positions=True).get("positions", []):
            actual[p["instrument"]["symbol"]] = int(p.get("longQuantity", 0))
        for ticker, pos in list(self.ledger.positions.items()):
            real = actual.get(ticker, 0)
            if real < pos.qty:
                problems.append(f"{ticker}: bot's checkbook has {pos.qty}, Schwab has {real}; fixing the checkbook")
                if real == 0:
                    del self.ledger.positions[ticker]
                else:
                    pos.qty = real
        mine = {t: p.qty for t, p in self.ledger.positions.items()}
        self.blocked = frozenset(t for t, q in actual.items() if q > mine.get(t, 0))
        for ticker in self.blocked & set(mine):
            problems.append(f"{ticker}: you own extra shares yourself. When the bot sells, Schwab may sell "
                            "YOUR oldest shares first (taxes!). Avoid owning the bot's stocks.")
        self.save()
        return problems, fills
