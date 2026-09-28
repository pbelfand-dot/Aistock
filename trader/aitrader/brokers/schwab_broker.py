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
  * Resting stop-loss: every position it holds also has a stop order waiting at
    Schwab, so if your laptop sleeps or crashes a falling position still gets sold.
  * Normal orders are limit orders a hair through the price (fill fast, never at a
    crazy price). URGENT exits (stop-loss, end of day, emergency) are market orders.

THE ONE RULE that keeps it safe: the bot stops tracking an order only once Schwab
confirms it is FINISHED (filled, cancelled, rejected or expired). If Schwab can't
confirm, the bot does nothing risky and checks again next cycle. That's how it
avoids selling the same shares twice or losing track of a fill.

  * Crash-safe: orders are written down the moment they're sent; reconcile()
    finds out what happened to them after a restart.
  * dry_run=True shows exactly what it WOULD send, without sending or changing anything.
"""
import math
import time

from .base import Broker, Fill, Ledger, Order

DEAD_STATUSES = {"CANCELED", "REJECTED", "EXPIRED", "REPLACED"}
FINISHED = DEAD_STATUSES | {"FILLED"}
UNKNOWN_ID = "unknown"      # Schwab accepted an order but didn't tell us its id


class SchwabBroker(Broker):
    def __init__(self, ledger: Ledger, client, account_hash: str, mode: str = "live-swing",
                 limit_buffer_pct: float = 0.2, fill_timeout_seconds: int = 60, cash_account: bool = True,
                 dry_run: bool = False, stop_loss_pct: float = None, stop_good_till_cancel: bool = True,
                 save=lambda: None, log=print, on_fill=None, poll_seconds: float = 2):
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
        if on_fill:
            self.on_fill = on_fill
        self.poll = poll_seconds
        self.blocked = frozenset()

    # ---- money ------------------------------------------------------------------
    def buying_power(self, today: str) -> float:
        return min(self.ledger.buying_power(today, self.cash_account), self.real_cash())

    def real_cash(self) -> float:
        """Cash Schwab says the account can trade with right now (never margin)."""
        try:
            bal = self._account().get("currentBalances", {})
        except Exception as e:
            self.log(f"Could not read your Schwab balance ({e!r}); no buying this cycle")
            return 0.0
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

    def _busy(self, ticker: str) -> bool:
        """True if the bot still has an unfinished order for this stock."""
        return any(p["ticker"] == ticker for p in self.ledger.pending)

    # ---- orders -----------------------------------------------------------------
    def submit(self, order: Order, date: str):
        """Never raises: if Schwab errors, this order waits for the next cycle and the others go ahead."""
        try:
            return self._submit(order, date)
        except Exception as e:
            self.log(f"!!! {order.side} {order.ticker}: Schwab error {e!r}; will retry next cycle")
            return None

    def _submit(self, order: Order, date: str):
        from schwab.orders.equities import equity_buy_limit, equity_sell_limit, equity_sell_market

        if self._busy(order.ticker):
            self.log(f"[{self.mode}] {order.ticker}: an earlier order is still open at Schwab; waiting for it")
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
            qty = min(qty, pos.qty)
            spec = (equity_sell_market(order.ticker, qty) if order.urgent
                    else equity_sell_limit(order.ticker, qty, limit))
        else:
            spec = equity_buy_limit(order.ticker, qty, limit)

        fill = self._send(spec, order, date)
        held = self.ledger.positions.get(order.ticker)
        if held and self.stop_loss_pct and not held.stop_order_id and not self._busy(order.ticker):
            self._place_stop(held)      # protect what we hold: a new buy, a partial sell, or a sell that failed
        return fill

    def _send(self, spec, order: Order, date: str):
        from schwab.utils import Utils
        resp = self.client.place_order(self.account_hash, spec)
        if resp.is_error:
            self.log(f"Schwab REJECTED {order.side} {order.ticker}: {resp.status_code} {resp.text}")
            return None
        order_id = Utils(self.client, self.account_hash).extract_order_id(resp)
        if order_id is None:
            self.log(f"!!! {order.side} {order.ticker} was sent but Schwab returned no order id. CHECK SCHWAB BY HAND.")
            return None
        order_id = str(order_id)
        self.ledger.pending.append({"id": order_id, "ticker": order.ticker, "side": order.side,
                                    "reason": order.reason, "urgent": order.urgent})
        self.save()                                   # written down BEFORE waiting, in case we crash
        return self._settle(order_id, self._wait(order_id, cancel_if_slow=not order.urgent), date)

    def _wait(self, order_id: str, cancel_if_slow: bool = True) -> dict:
        """Watch the order until it's finished or time runs out. Normal orders that are
        too slow get cancelled; urgent market orders are left working (e.g. until the open)."""
        deadline = time.time() + self.timeout
        data = self._order(order_id)
        while data.get("status") not in FINISHED and time.time() < deadline:
            time.sleep(self.poll)
            data = self._order(order_id)
        if data.get("status") not in FINISHED and cancel_if_slow:
            data = self._cancel_and_confirm(order_id)
        return data

    def _settle(self, order_id: str, data: dict, date: str):
        """If the order is finished: book whatever filled and stop tracking it.
        If it isn't: keep tracking it and check again next cycle."""
        entry = next(p for p in self.ledger.pending if p["id"] == order_id)
        if data.get("status") not in FINISHED:
            self.log(f"[{self.mode}] order {order_id} ({entry['side']} {entry['ticker']}) is still "
                     f"{data.get('status')} at Schwab; checking again next cycle")
            return None
        self.ledger.pending.remove(entry)
        qty, price = self._filled(data)
        fill = None
        if qty >= 1:
            fill = self._book(Fill(date=date, ticker=entry["ticker"], side=entry["side"], qty=qty,
                                   price=price, reason=entry["reason"], order_id=order_id))
        self.save()
        return fill

    def _order(self, order_id: str) -> dict:
        resp = self.client.get_order(order_id, self.account_hash)
        resp.raise_for_status()                       # an error is NOT "finished": stop and retry later
        return resp.json()

    def _cancel_and_confirm(self, order_id: str) -> dict:
        """Cancel, then check what really happened (it may have filled at the last second)."""
        self.client.cancel_order(order_id, self.account_hash)
        data = {}
        for _ in range(5):
            time.sleep(self.poll)
            data = self._order(order_id)
            if data.get("status") in FINISHED:
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

        if pos.stop_order_id:                         # never two stops for the same shares
            return
        stop = round(pos.avg_cost * (1 - self.stop_loss_pct / 100), 2)
        spec = (equity_sell_market(pos.ticker, pos.qty)
                .set_order_type(OrderType.STOP).set_stop_price(stop)
                .set_duration(Duration.GOOD_TILL_CANCEL if self.stop_gtc else Duration.DAY))
        resp = self.client.place_order(self.account_hash, spec)
        if resp.is_error:
            self.log(f"!!! could not place a resting stop for {pos.ticker}: {resp.status_code}. "
                     "The bot still checks stops itself every 5 minutes, and will try again.")
            return
        order_id = Utils(self.client, self.account_hash).extract_order_id(resp)
        if order_id is None:
            self.log(f"!!! stop for {pos.ticker} was sent but Schwab returned no order id. CHECK SCHWAB BY HAND.")
        pos.stop_order_id = UNKNOWN_ID if order_id is None else str(order_id)
        self.save()
        self.log(f"[{self.mode}] resting stop-loss for {pos.qty} {pos.ticker} at ${stop}")

    def _find_stop(self, pos) -> str:
        """Look up this position's working stop order at Schwab (when its id was lost, or you
        edited the stop by hand). Returns its id, "" if there is none, or UNKNOWN_ID if unclear.
        (The bot never trades stocks you own, so a sell-stop on its stock is the bot's.)"""
        resp = self.client.get_orders_for_account(self.account_hash)
        resp.raise_for_status()
        matches = [o for o in resp.json()
                   if o.get("orderType") in ("STOP", "STOP_LIMIT") and o.get("status") not in FINISHED
                   and any(leg.get("instrument", {}).get("symbol") == pos.ticker and leg.get("instruction") == "SELL"
                           for leg in o.get("orderLegCollection", []))]
        if len(matches) == 1:
            return str(matches[0]["orderId"])
        return UNKNOWN_ID if matches else ""

    def _retire_stop(self, pos, date: str):
        """Take down a position's resting stop. Returns (done, fill).
        done=False: the stop might still be live at Schwab, so selling now could sell twice."""
        if not pos or not pos.stop_order_id:
            return True, None
        if pos.stop_order_id == UNKNOWN_ID:
            pos.stop_order_id = self._find_stop(pos)
            self.save()
            if not pos.stop_order_id:
                return True, None                     # there is no stop to take down
            if pos.stop_order_id == UNKNOWN_ID:
                self.log(f"!!! {pos.ticker}: can't tell which stop order at Schwab is the bot's, so it won't "
                         "sell automatically. CHECK SCHWAB BY HAND.")
                return False, None
        data = self._order(pos.stop_order_id)
        if data.get("status") not in FINISHED:
            data = self._cancel_and_confirm(pos.stop_order_id)
        if data.get("status") not in FINISHED:
            self.log(f"[{self.mode}] {pos.ticker}: resting stop {pos.stop_order_id} not confirmed cancelled "
                     f"({data.get('status')}); not selling yet, will retry")
            return False, None
        order_id, pos.stop_order_id = pos.stop_order_id, ""
        qty, price = self._filled(data)
        fill = None
        if qty >= 1:
            fill = self._book(Fill(date=date, ticker=pos.ticker, side="SELL", qty=min(qty, pos.qty), price=price,
                                   reason="stop-loss order filled at Schwab", order_id=order_id))
        self.save()
        return True, fill

    def cancel_all(self, date: str = None):
        """Cancel the bot's own unfinished orders (never yours). Resting stops stay in
        place until the bot actually sells, so positions are never left unprotected."""
        for p in list(self.ledger.pending):
            if self.dry_run:
                continue
            data = self._order(p["id"])
            if data.get("status") not in FINISHED:
                data = self._cancel_and_confirm(p["id"])
            self._settle(p["id"], data, date)

    # ---- safety check, run before every trading cycle --------------------------------
    def reconcile(self, date: str) -> list:
        """Line the bot's checkbook up with reality. Returns a list of problems found.
        (Fills found here are saved immediately through on_fill.)"""
        problems = []

        # Each item is checked on its own: if Schwab errors on one, the rest still get checked.
        def attempt(what, step):
            try:
                step()
            except Exception as e:
                problems.append(f"couldn't check {what} ({e!r}); will retry next cycle")

        # 1) Orders still open from before (crash, sleep, slow fills). Urgent market
        #    orders are left working; anything else is cancelled.
        def check_order(p):
            data = self._order(p["id"])
            if data.get("status") not in FINISHED and not p.get("urgent") and not self.dry_run:
                data = self._cancel_and_confirm(p["id"])
            if data.get("status") in FINISHED and self._filled(data)[0]:
                problems.append(f"order {p['id']} {p['side']} {p['ticker']} filled while the bot wasn't watching")
            self._settle(p["id"], data, date)
        for p in list(self.ledger.pending):
            attempt(f"order {p['id']}", lambda p=p: check_order(p))

        # 2) Resting stops that fired, died or were edited by you while the bot wasn't watching
        def check_stop(pos):
            if pos.stop_order_id == UNKNOWN_ID:
                pos.stop_order_id = self._find_stop(pos)
                return
            data = self._order(pos.stop_order_id)
            status = data.get("status")
            if status not in FINISHED:
                return
            order_id, pos.stop_order_id = pos.stop_order_id, ""
            qty, price = self._filled(data)
            if qty >= 1:
                self._book(Fill(date, pos.ticker, "SELL", min(qty, pos.qty), price,
                                "stop-loss order filled at Schwab", order_id=order_id))
            elif status == "REPLACED":                  # you edited it in Schwab: keep yours, don't add another
                pos.stop_order_id = self._find_stop(pos)
                problems.append(f"{pos.ticker}: you changed its stop order in Schwab; the bot is using yours")
            else:
                problems.append(f"{pos.ticker}: resting stop was {status}; placing a new one")
        for pos in list(self.ledger.positions.values()):
            if pos.stop_order_id:
                attempt(f"{pos.ticker}'s stop", lambda pos=pos: check_stop(pos))

        # 3) Compare with what Schwab says the account really owns
        try:
            holdings = self._account(positions=True).get("positions", [])
        except Exception as e:
            problems.append(f"couldn't read your Schwab positions ({e!r}); no buying until it works")
            self.blocked = frozenset(self.ledger.positions) | {"*"}
            self.save()
            return problems
        actual = {p["instrument"]["symbol"]: int(p.get("longQuantity", 0)) for p in holdings}
        for ticker, pos in list(self.ledger.positions.items()):
            real = actual.get(ticker, 0)
            if real >= pos.qty or self._busy(ticker):
                continue
            problems.append(f"{ticker}: bot's checkbook has {pos.qty}, Schwab has {real}. Did you sell them by "
                            "hand? Fixing the checkbook.")
            done = True
            if not self.dry_run:                        # its stop covers shares that aren't there anymore
                try:
                    done, _ = self._retire_stop(pos, date)
                except Exception:
                    done = False
            if not done and real > 0:
                problems.append(f"!!! {ticker}: couldn't confirm its stop order is cancelled. CHECK SCHWAB BY HAND.")
                continue
            if not done:
                problems.append(f"!!! {ticker}: the shares are gone but its stop order may still be at Schwab. "
                                "CHECK SCHWAB BY HAND and cancel any leftover stop on it.")
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
            problems.append(f"{ticker}: you own extra shares yourself. When the bot sells, Schwab may sell "
                            "YOUR oldest shares first (taxes!). Avoid owning the bot's stocks.")
        self.save()
        return problems

    def is_flat(self) -> bool:
        return not self.ledger.positions and not self.ledger.pending
