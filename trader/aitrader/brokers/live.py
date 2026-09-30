"""
brokers/live.py: the safety rules for sending orders to a REAL broker account
(Alpaca paper, Alpaca live, or Schwab). The broker-specific details live in
small "gateways" (alpaca_broker.py, schwab_broker.py); everything that keeps
your money safe is here, written once, used by all of them.

  * Budget-capped: each desk's checkbook (Ledger) starts at its share of the
    money. It also never spends more than the cash the broker says is actually
    available, so it can't borrow (margin) or touch money meant for other things.
  * Only touches what IT bought: it never sells shares it didn't buy, and it
    won't buy a stock you already own yourself in that account.
  * Only cancels ITS OWN orders, never ones you placed by hand.
  * Resting stop-loss: every position also has a stop order waiting at the broker,
    so if your laptop sleeps or crashes a falling position still gets sold.
  * Normal orders are limit orders a hair through the price (fill fast, never at a
    crazy price). URGENT exits (stop-loss, end of day, emergency) are market orders.

THE ONE RULE that keeps it safe: the bot stops tracking an order only once the
broker confirms it is FINISHED (filled, cancelled, rejected or expired). If the
broker can't confirm, the bot does nothing risky and checks again next cycle.
That's how it avoids selling the same shares twice or losing track of a fill.

  * Crash-safe: orders are written down the moment they're sent (with Alpaca,
    even BEFORE they're sent); reconcile() finds out what happened after a restart.
  * dry_run=True shows exactly what it WOULD send, without sending or changing anything.
"""
import math
import time

from .base import Broker, Fill, Ledger, Order

DEAD_STATUSES = {"CANCELED", "REJECTED", "EXPIRED", "REPLACED"}
FINISHED = DEAD_STATUSES | {"FILLED"}
UNKNOWN_ID = "unknown"      # the broker may have an order the bot can't identify yet


class OrderRejected(Exception):
    """The broker refused the order; nothing was placed."""


class LiveBroker(Broker):
    def __init__(self, ledger: Ledger, gateway, mode: str = "live-swing",
                 limit_buffer_pct: float = 0.2, fill_timeout_seconds: int = 60, cash_account: bool = True,
                 dry_run: bool = False, stop_loss_pct: float = None, stop_good_till_cancel: bool = True,
                 save=lambda: None, log=print, on_fill=None, poll_seconds: float = 2):
        super().__init__(ledger)
        self.gw = gateway
        self.mode = mode
        self.buffer = limit_buffer_pct / 100
        self.timeout = fill_timeout_seconds
        self.cash_account = cash_account
        self.dry_run = dry_run
        self.stop_loss_pct = stop_loss_pct          # None = no resting stops
        self.stop_gtc = stop_good_till_cancel       # swing: stays for days; day desk: expires tonight
        self.save = (lambda: None) if dry_run else save
        self.log = log
        if on_fill:
            self.on_fill = on_fill
        self.poll = poll_seconds
        self.blocked = frozenset()

    # ---- money ------------------------------------------------------------------
    def buying_power(self, today: str) -> float:
        return min(self.ledger.buying_power(today, self.cash_account), self.real_cash())

    def real_cash(self) -> float:
        """Cash the broker says the account can trade with right now (never borrowed money)."""
        try:
            return max(0.0, float(self.gw.cash()))
        except Exception as e:
            self.log(f"Could not read your {self.gw.name} balance ({e!r}); no buying this cycle")
            return 0.0

    def _busy(self, ticker: str) -> bool:
        """True if the bot still has an unfinished order for this stock."""
        return any(p["ticker"] == ticker for p in self.ledger.pending)

    # ---- orders -----------------------------------------------------------------
    def submit(self, order: Order, date: str):
        """Never raises: if the broker errors, this order waits for the next cycle and the others go ahead."""
        try:
            return self._submit(order, date)
        except Exception as e:
            self.log(f"!!! {order.side} {order.ticker}: {self.gw.name} error {e!r}; will retry next cycle")
            return None

    def note(self, message: str):
        self.log(message)

    def _submit(self, order: Order, date: str):
        hold = self.gfv_hold(order, date)
        if hold:                                      # a good faith violation: wait for the money to settle
            self.log(f"[{self.mode}] {hold}")
            return None
        if self._busy(order.ticker):
            self.log(f"[{self.mode}] {order.ticker}: an earlier order is still open; waiting for it")
            return None
        pos = self.ledger.positions.get(order.ticker)
        if order.side == "BUY":
            if order.ticker in self.blocked or "*" in self.blocked:
                return None
            limit = round(order.price * (1 + self.buffer), 2)
            qty = min(order.qty, math.floor(self.buying_power(date) / limit))
        else:
            limit = round(order.price * (1 - self.buffer), 2)
            qty = min(order.qty, pos.qty if pos else 0)
        if qty < 1:
            return None
        if self.dry_run:
            kind = "MARKET" if order.urgent and order.side == "SELL" else f"limit ${limit}"
            self.log(f"[DRY RUN] would {order.side} {qty} {order.ticker} ({kind}): {order.reason}")
            return None

        if order.side == "SELL":
            # The resting stop covers these same shares: it must be confirmed gone first.
            done, stop_fill = self._retire_stop(pos, date)
            if not done:
                return None                           # might still be live: never risk selling twice
            if stop_fill:
                return stop_fill                      # the stop already sold (some of) them
            kind = "market_sell" if order.urgent else "limit_sell"
            fill = self._send(kind, order, min(qty, pos.qty), limit, date)
        else:
            fill = self._send("limit_buy", order, qty, limit, date)

        held = self.ledger.positions.get(order.ticker)
        if held and self.stop_loss_pct and not held.stop_order_id and not self._busy(order.ticker):
            self._place_stop(held)      # protect what we hold: a new buy, a partial sell, or a sell that failed
        return fill

    def _send(self, kind: str, order: Order, qty: int, limit: float, date: str):
        entry = {"id": None, "ticker": order.ticker, "side": order.side, "reason": order.reason,
                 "urgent": order.urgent, "client_id": self.gw.new_client_id()}
        if entry["client_id"]:                        # our own tag: written down BEFORE sending
            self.ledger.pending.append(entry)
            self.save()
        try:
            order_id = self.gw.place(kind, order.ticker, qty, price=limit, client_id=entry["client_id"])
        except OrderRejected as e:
            self._forget(entry)
            self.log(f"{self.gw.name} REJECTED {order.side} {order.ticker}: {e}")
            return None
        except Exception as e:
            if not entry["client_id"]:
                raise
            self.log(f"[{self.mode}] couldn't confirm {order.side} {order.ticker} was sent ({e!r}); "
                     "will look it up by its tag next cycle")
            return None
        if order_id is None:
            self._forget(entry)
            self.log(f"!!! {order.side} {order.ticker} was sent but {self.gw.name} returned no order id. "
                     "CHECK YOUR ACCOUNT BY HAND.")
            return None
        entry["id"] = order_id
        if entry not in self.ledger.pending:
            self.ledger.pending.append(entry)
        self.save()                                   # written down BEFORE waiting, in case we crash
        return self._settle(entry, self._wait(order_id, cancel_if_slow=not order.urgent), date)

    def _forget(self, entry):
        if entry in self.ledger.pending:
            self.ledger.pending.remove(entry)
            self.save()

    def _wait(self, order_id: str, cancel_if_slow: bool = True) -> dict:
        """Watch the order until it's finished or time runs out. Normal orders that are
        too slow get cancelled; urgent market orders are left working (e.g. until the open)."""
        deadline = time.time() + self.timeout
        data = self.gw.order(order_id)
        while data["status"] not in FINISHED and time.time() < deadline:
            time.sleep(self.poll)
            data = self.gw.order(order_id)
        if data["status"] not in FINISHED and cancel_if_slow:
            data = self._cancel_and_confirm(order_id)
        return data

    def _settle(self, entry: dict, data: dict, date: str):
        """If the order is finished: book whatever filled and stop tracking it.
        If it isn't: keep tracking it and check again next cycle."""
        if data["status"] not in FINISHED:
            self.log(f"[{self.mode}] order {entry['id']} ({entry['side']} {entry['ticker']}) is still "
                     f"{data['status']} at {self.gw.name}; checking again next cycle")
            return None
        self.ledger.pending.remove(entry)
        fill = None
        if data["filled_qty"] >= 1:
            fill = self._book(Fill(date=date, ticker=entry["ticker"], side=entry["side"], qty=data["filled_qty"],
                                   price=data["avg_price"], reason=entry["reason"], order_id=entry["id"]))
        self.save()
        return fill

    def _cancel_and_confirm(self, order_id: str) -> dict:
        """Cancel, then check what really happened (it may have filled at the last second)."""
        self.gw.cancel(order_id)
        data = {"status": None}
        for _ in range(5):
            time.sleep(self.poll)
            data = self.gw.order(order_id)
            if data["status"] in FINISHED:
                break
        return data

    # ---- resting stop-loss orders ---------------------------------------------------
    def _place_stop(self, pos):
        if pos.stop_order_id:                         # never two stops for the same shares
            return
        stop = round(pos.avg_cost * (1 - self.stop_loss_pct / 100), 2)
        try:
            order_id = self.gw.place("stop_sell", pos.ticker, pos.qty, price=stop, gtc=self.stop_gtc,
                                     client_id=self.gw.new_client_id())
        except OrderRejected as e:
            self.log(f"!!! could not place a resting stop for {pos.ticker} ({e}). "
                     "The bot still checks stops itself every 5 minutes, and will try again.")
            return
        except Exception as e:                        # may or may not have been placed: look it up next cycle
            self.log(f"[{self.mode}] couldn't confirm the stop for {pos.ticker} was placed ({e!r}); checking next cycle")
            order_id = None
        if order_id is None:
            self.log(f"[{self.mode}] {pos.ticker}: stop order id unknown; will find it at {self.gw.name}")
        pos.stop_order_id = UNKNOWN_ID if order_id is None else order_id
        self.save()
        if order_id:
            self.log(f"[{self.mode}] resting stop-loss for {pos.qty} {pos.ticker} at ${stop}")

    def _find_stop(self, pos) -> str:
        """Look up this position's working stop order at the broker (when its id was lost, or you
        edited the stop by hand). Returns its id, "" if there is none, or UNKNOWN_ID if unclear.
        (The bot never trades stocks you own, so a sell-stop on its stock is the bot's.)"""
        matches = self.gw.find_sell_stops(pos.ticker)
        if len(matches) == 1:
            return matches[0]
        return UNKNOWN_ID if matches else ""

    def _retire_stop(self, pos, date: str):
        """Take down a position's resting stop. Returns (done, fill).
        done=False: the stop might still be live at the broker, so selling now could sell twice."""
        if not pos or not pos.stop_order_id:
            return True, None
        if pos.stop_order_id == UNKNOWN_ID:
            pos.stop_order_id = self._find_stop(pos)
            self.save()
            if not pos.stop_order_id:
                return True, None                     # there is no stop to take down
            if pos.stop_order_id == UNKNOWN_ID:
                self.log(f"!!! {pos.ticker}: can't tell which stop order is the bot's, so it won't "
                         f"sell automatically. CHECK {self.gw.name.upper()} BY HAND.")
                return False, None
        data = self.gw.order(pos.stop_order_id)
        if data["status"] not in FINISHED:
            data = self._cancel_and_confirm(pos.stop_order_id)
        if data["status"] not in FINISHED:
            self.log(f"[{self.mode}] {pos.ticker}: resting stop {pos.stop_order_id} not confirmed cancelled "
                     f"({data['status']}); not selling yet, will retry")
            return False, None
        order_id, pos.stop_order_id = pos.stop_order_id, ""
        fill = None
        if data["filled_qty"] >= 1:
            fill = self._book(Fill(date=date, ticker=pos.ticker, side="SELL", qty=min(data["filled_qty"], pos.qty),
                                   price=data["avg_price"], reason=f"stop-loss order filled at {self.gw.name}",
                                   order_id=order_id))
        self.save()
        return True, fill

    def cancel_all(self, date: str = None):
        """Cancel the bot's own unfinished orders (never yours). Resting stops stay in
        place until the bot actually sells, so positions are never left unprotected."""
        if self.dry_run:
            return
        for entry in list(self.ledger.pending):
            if entry["id"] is None:
                continue                              # not confirmed sent yet; reconcile sorts it out
            data = self.gw.order(entry["id"])
            if data["status"] not in FINISHED:
                data = self._cancel_and_confirm(entry["id"])
            self._settle(entry, data, date)

    # ---- safety check, run before every trading cycle --------------------------------
    def reconcile(self, date: str) -> list:
        """Line the bot's checkbook up with reality. Returns a list of problems found.
        (Fills found here are saved immediately through on_fill.)"""
        problems = []

        # Each item is checked on its own: if the broker errors on one, the rest still get checked.
        def attempt(what, step):
            try:
                step()
            except Exception as e:
                problems.append(f"couldn't check {what} ({e!r}); will retry next cycle")

        # 1) Orders still open from before (crash, sleep, slow fills). Urgent market
        #    orders are left working; anything else is cancelled.
        def check_order(entry):
            if entry["id"] is None:                   # sent right before a crash/network error?
                entry["id"] = self.gw.order_by_client_id(entry["client_id"])
                if entry["id"] is None:
                    self._forget(entry)               # it never reached the broker
                    return
            data = self.gw.order(entry["id"])
            if data["status"] not in FINISHED and not entry.get("urgent") and not self.dry_run:
                data = self._cancel_and_confirm(entry["id"])
            if data["status"] in FINISHED and data["filled_qty"]:
                problems.append(f"order {entry['id']} {entry['side']} {entry['ticker']} filled while the bot "
                                "wasn't watching")
            self._settle(entry, data, date)
        for entry in list(self.ledger.pending):
            attempt(f"order {entry['id'] or entry['client_id']}", lambda e=entry: check_order(e))

        # 2) Resting stops that fired, died or were edited by you while the bot wasn't watching
        def check_stop(pos):
            if pos.stop_order_id == UNKNOWN_ID:
                pos.stop_order_id = self._find_stop(pos)
                return
            data = self.gw.order(pos.stop_order_id)
            status = data["status"]
            if status not in FINISHED:
                return
            order_id, pos.stop_order_id = pos.stop_order_id, ""
            if data["filled_qty"] >= 1:
                self._book(Fill(date, pos.ticker, "SELL", min(data["filled_qty"], pos.qty), data["avg_price"],
                                f"stop-loss order filled at {self.gw.name}", order_id=order_id))
            elif status == "REPLACED":                  # you edited it: keep yours, don't add another
                pos.stop_order_id = self._find_stop(pos)
                problems.append(f"{pos.ticker}: you changed its stop order by hand; the bot is using yours")
            else:
                problems.append(f"{pos.ticker}: resting stop was {status}; placing a new one")
        for pos in list(self.ledger.positions.values()):
            if pos.stop_order_id:
                attempt(f"{pos.ticker}'s stop", lambda pos=pos: check_stop(pos))

        # 3) Compare with what the broker says the account really owns
        try:
            actual = self.gw.holdings()
        except Exception as e:
            problems.append(f"couldn't read your {self.gw.name} positions ({e!r}); no buying until it works")
            self.blocked = frozenset(self.ledger.positions) | {"*"}
            self.save()
            return problems
        for ticker, pos in list(self.ledger.positions.items()):
            real = actual.get(ticker, 0)
            if real >= pos.qty or self._busy(ticker):
                continue
            problems.append(f"{ticker}: bot's checkbook has {pos.qty}, {self.gw.name} has {real}. Did you sell "
                            "them by hand? Fixing the checkbook.")
            done = True
            if not self.dry_run:                        # its stop covers shares that aren't there anymore
                try:
                    done, _ = self._retire_stop(pos, date)
                except Exception:
                    done = False
            if not done and real > 0:
                problems.append(f"!!! {ticker}: couldn't confirm its stop order is cancelled. "
                                f"CHECK {self.gw.name.upper()} BY HAND.")
                continue
            if not done:
                problems.append(f"!!! {ticker}: the shares are gone but its stop order may still be open. "
                                f"CHECK {self.gw.name.upper()} BY HAND and cancel any leftover stop on it.")
            if ticker in self.ledger.positions:
                if real == 0:
                    del self.ledger.positions[ticker]
                else:
                    self.ledger.positions[ticker].qty = real

        # 4) Every position gets a resting stop (sized to what's really there)
        if self.stop_loss_pct and not self.dry_run:
            for pos in list(self.ledger.positions.values()):
                if not pos.stop_order_id and not self._busy(pos.ticker):
                    attempt(f"a new stop for {pos.ticker}", lambda pos=pos: self._place_stop(pos))

        # 5) Never buy stocks you own yourself
        mine = {t: p.qty for t, p in self.ledger.positions.items()}
        self.blocked = frozenset(t for t, q in actual.items() if q > mine.get(t, 0))
        for ticker in self.blocked & set(mine):
            problems.append(f"{ticker}: you own extra shares yourself. When the bot sells, the broker may sell "
                            "YOUR oldest shares first (taxes!). Avoid owning the bot's stocks.")
        self.save()
        return problems

    def is_flat(self) -> bool:
        return not self.ledger.positions and not self.ledger.pending
