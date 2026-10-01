"""
brokers/base.py: the shared pieces every broker uses.

  Order    what the bot WANTS to do ("buy 3 KO, because...")
  Fill     what actually HAPPENED ("bought 3 KO at $70.12")
  Ledger   the bot's own checkbook: its cash and the positions IT opened
  Broker   paper and Schwab both follow this same shape, so the rest of
           the bot never needs to know which one it's talking to
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

import pandas as pd

from ..risk import shares
from ..settlement import settles_on

# Schwab (and most brokers): 3 good faith violations in 12 months = 90 days restricted to settled cash.
GFV_LIMIT = 3


@dataclass
class Order:
    ticker: str
    side: str          # "BUY" or "SELL"
    qty: float         # whole shares, or parts of a share where the broker allows (risk.shares)
    price: float       # the price we saw when we decided
    reason: str
    urgent: bool = False   # must get out NOW (stop-loss, end of day, emergency): live uses a market order
    emergency: bool = False  # your typed emergency stop: the only sale allowed to risk a good faith violation
    stop_pct: float = None   # buys: this stock's stop-loss distance in % (risk.stop_for); None = the desk's fixed stop


@dataclass
class Fill:
    date: str
    ticker: str
    side: str
    qty: float
    price: float
    reason: str
    realized_pnl: float = 0.0
    order_id: str = ""


@dataclass
class Position:
    ticker: str
    qty: float
    avg_cost: float
    opened_on: str
    stop_order_id: str = ""   # live only: the stop-loss order resting at Schwab
    funds_settle_on: str = "" # cash accounts: if (part of) the money that bought it was still unsettled, the day
                              # that money settles. Selling before then would be a good faith violation.
    stop_pct: float = 0.0     # its own stop-loss distance in % (sized to how much it moves); 0 = the desk's fixed stop


class Ledger:
    """The bot's checkbook. The bot only ever trades what's in here, so it can
    never touch other money or stocks in your Schwab account.

    GOOD FAITH VIOLATIONS (cash accounts, e.g. Schwab): money from a sale isn't "settled" until one
    business day later (T+1; bank holidays don't count, see settlement.py). Buying with unsettled
    money and then selling that stock before the money settles is a good faith violation; 3 in 12
    months and Schwab restricts the account for 90 days. So in a cash account the bot only ever
    buys with SETTLED money: every sale is then safe. The ledger remembers when each sale's money
    settles, and marks any position that was bought with unsettled money (it shouldn't happen) so
    it isn't sold early."""

    def __init__(self, cash: float, positions: dict = None, unsettled: dict = None, pending: list = None,
                 gfv_events: list = None):
        self.cash = float(cash)
        self.positions = positions or {}      # ticker -> Position
        self.unsettled = unsettled or {}      # settlement date -> sale money that becomes settled that day
        self.pending = pending or []          # live only: orders sent but not finished yet
        self.gfv_events = gfv_events or []    # dates of good faith violations (only an emergency stop can cause one)

    def unsettled_after(self, today: str) -> float:
        """Sale money that is still not settled on `today`."""
        return sum(amount for day, amount in self.unsettled.items() if day > str(today)[:10])

    def buying_power(self, today: str, cash_account: bool) -> float:
        if not cash_account:
            return self.cash
        return max(0.0, self.cash - self.unsettled_after(today))

    def gfv_count(self, today: str) -> int:
        """Good faith violations in the last 12 months."""
        year_ago = f"{int(str(today)[:4]) - 1}{str(today)[4:10]}"
        return sum(1 for day in self.gfv_events if day > year_ago)

    def apply(self, fill: Fill) -> Fill:
        fill.qty = shares(fill.qty)
        if fill.side == "BUY":
            cost = fill.qty * fill.price
            still_unsettled = self.unsettled_after(fill.date)
            used_unsettled = still_unsettled > 0 and cost > self.cash - still_unsettled + 0.005
            pos = self.positions.get(fill.ticker)
            if pos:
                total = shares(pos.qty + fill.qty)
                pos.avg_cost = (pos.avg_cost * pos.qty + fill.price * fill.qty) / total
                pos.qty = total
            else:
                pos = self.positions[fill.ticker] = Position(fill.ticker, fill.qty, fill.price, fill.date)
            if used_unsettled:                         # remember: don't sell it before that money settles
                latest = max(day for day, amount in self.unsettled.items() if day > fill.date[:10] and amount > 0)
                pos.funds_settle_on = max(pos.funds_settle_on or "", latest)
            self.cash -= cost
        else:
            pos = self.positions[fill.ticker]
            fill.realized_pnl = round((fill.price - pos.avg_cost) * fill.qty, 2)
            pos.qty = shares(pos.qty - fill.qty)
            if pos.qty <= 1e-6:                        # all sold (not a rounding crumb left behind)
                del self.positions[fill.ticker]
            proceeds = fill.qty * fill.price
            self.cash += proceeds
            today = fill.date[:10]
            self.unsettled = {day: amount for day, amount in self.unsettled.items() if day > today}   # settled: forget
            settle = settles_on(today)
            self.unsettled[settle] = self.unsettled.get(settle, 0.0) + proceeds
        return fill

    def equity(self, prices) -> float:
        """Cash + current value of everything we own."""
        value = self.cash
        for t, pos in self.positions.items():
            price = prices.get(t) if prices is not None else None
            value += pos.qty * (price if price is not None and not pd.isna(price) else pos.avg_cost)
        return value

    def to_dict(self) -> dict:
        return {"cash": self.cash, "unsettled": self.unsettled, "unsettled_by": "settlement-date",
                "gfv_events": self.gfv_events, "pending": self.pending,
                "positions": {t: asdict(p) for t, p in self.positions.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Ledger":
        positions = {t: Position(**p) for t, p in d.get("positions", {}).items()}
        unsettled = d.get("unsettled", {})
        if d.get("unsettled_by") != "settlement-date":            # older versions keyed it by the SALE date
            unsettled = {settles_on(day): amount for day, amount in unsettled.items()}
        return cls(d["cash"], positions, unsettled, d.get("pending", []), d.get("gfv_events", []))


class Broker(ABC):
    mode = "base"             # e.g. "paper-swing", "live-day", "backtest"
    cash_account = False
    blocked = frozenset()     # tickers the bot must not buy (e.g. you own them yourself)

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.on_fill = lambda fill: None      # called the moment any fill is booked (saves it to the database)

    def cash(self) -> float:
        return self.ledger.cash

    def buying_power(self, today: str) -> float:
        return self.ledger.buying_power(today, self.cash_account)

    def gfv_hold(self, order: Order, date: str) -> str:
        """Why this sale must wait (it would be a good faith violation), or "" if it may go ahead.
        Only a cash account can have one. Your typed emergency stop always goes ahead, and is counted."""
        if not self.cash_account or order.side != "SELL":
            return ""
        pos = self.ledger.positions.get(order.ticker)
        if not pos or not pos.funds_settle_on or pos.funds_settle_on <= str(date)[:10]:
            return ""
        if order.emergency:
            self.ledger.gfv_events.append(str(date)[:10])
            self.note(f"!!! GOOD FAITH VIOLATION: emergency sale of {order.ticker} before the money that bought it "
                      f"settled ({pos.funds_settle_on}). {self.ledger.gfv_count(date)} in the last 12 months "
                      f"(at {GFV_LIMIT} Schwab restricts the account for 90 days).")
            return ""
        return (f"{order.ticker}: holding until {pos.funds_settle_on}, when the money that bought it settles "
                f"(selling now would be a good faith violation)")

    def note(self, message: str):
        """A message for the journal (the live broker writes it; paper keeps it quiet)."""

    def positions(self) -> dict:
        return dict(self.ledger.positions)

    def equity(self, prices) -> float:
        return self.ledger.equity(prices)

    @abstractmethod
    def submit(self, order: Order, date: str):
        """Try to execute the order. Returns a Fill, or None if nothing happened."""

    def cancel_all(self, date: str = None):
        """Cancel the bot's orders still waiting at the broker."""

    def _remember_stop(self, ticker: str, stop_pct):
        """A new position keeps the stop it was bought with (sized to how much the stock moves)."""
        pos = self.ledger.positions.get(ticker)
        if pos and stop_pct and not pos.stop_pct:
            pos.stop_pct = float(stop_pct)

    def _book(self, fill: Fill):
        """Write a fill into the checkbook AND the database, in the same moment."""
        if fill.side == "SELL" and fill.ticker not in self.ledger.positions:
            return None
        fill = self.ledger.apply(fill)
        self.on_fill(fill)
        return fill
