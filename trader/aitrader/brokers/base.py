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


@dataclass
class Order:
    ticker: str
    side: str          # "BUY" or "SELL"
    qty: int
    price: float       # the price we saw when we decided
    reason: str


@dataclass
class Fill:
    date: str
    ticker: str
    side: str
    qty: int
    price: float
    reason: str
    realized_pnl: float = 0.0
    order_id: str = ""


@dataclass
class Position:
    ticker: str
    qty: int
    avg_cost: float
    opened_on: str


class Ledger:
    """The bot's checkbook. The bot only ever trades what's in here, so it can
    never touch other money or stocks in your Schwab account.

    Cash accounts: money from a sale isn't "settled" until the next business day
    (T+1). Spending it early risks a Schwab "good faith violation", so the ledger
    keeps same-day sale money off-limits for buying until the next trading day."""

    def __init__(self, cash: float, positions: dict = None, unsettled: dict = None):
        self.cash = float(cash)
        self.positions = positions or {}      # ticker -> Position
        self.unsettled = unsettled or {}      # date -> sale proceeds received that day

    def buying_power(self, today: str, cash_account: bool) -> float:
        if not cash_account:
            return self.cash
        return max(0.0, self.cash - self.unsettled.get(today, 0.0))

    def apply(self, fill: Fill) -> Fill:
        if fill.side == "BUY":
            pos = self.positions.get(fill.ticker)
            if pos:
                total = pos.qty + fill.qty
                pos.avg_cost = (pos.avg_cost * pos.qty + fill.price * fill.qty) / total
                pos.qty = total
            else:
                self.positions[fill.ticker] = Position(fill.ticker, fill.qty, fill.price, fill.date)
            self.cash -= fill.qty * fill.price
        else:
            pos = self.positions[fill.ticker]
            fill.realized_pnl = round((fill.price - pos.avg_cost) * fill.qty, 2)
            pos.qty -= fill.qty
            if pos.qty <= 0:
                del self.positions[fill.ticker]
            proceeds = fill.qty * fill.price
            self.cash += proceeds
            self.unsettled = {fill.date: self.unsettled.get(fill.date, 0.0) + proceeds}
        return fill

    def equity(self, prices) -> float:
        """Cash + current value of everything we own."""
        value = self.cash
        for t, pos in self.positions.items():
            price = prices.get(t) if prices is not None else None
            value += pos.qty * (price if price is not None and not pd.isna(price) else pos.avg_cost)
        return value

    def to_dict(self) -> dict:
        return {"cash": self.cash, "unsettled": self.unsettled,
                "positions": {t: asdict(p) for t, p in self.positions.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Ledger":
        positions = {t: Position(**p) for t, p in d.get("positions", {}).items()}
        return cls(d["cash"], positions, d.get("unsettled", {}))


class Broker(ABC):
    mode = "base"             # "paper", "live" or "backtest"
    cash_account = False

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def cash(self) -> float:
        return self.ledger.cash

    def buying_power(self, today: str) -> float:
        return self.ledger.buying_power(today, self.cash_account)

    def positions(self) -> dict:
        return dict(self.ledger.positions)

    def equity(self, prices) -> float:
        return self.ledger.equity(prices)

    @abstractmethod
    def submit(self, order: Order, date: str):
        """Try to execute the order. Returns a Fill, or None if nothing happened."""

    def cancel_all(self):
        """Cancel any orders still waiting at the broker."""
