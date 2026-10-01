"""
brokers/paper.py: fake money, real prices.

Schwab's API has NO paper-trading mode (every API order is real), so paper
trading is simulated here. To keep it honest, every fill is a bit WORSE than
the quoted price (slippage). Real orders rarely fill at the exact price you saw.
The backtester uses this same class, so tests and paper play by the same rules.
"""
import uuid

from ..risk import MIN_ORDER_VALUE, floor_shares, is_fraction
from .base import Broker, Fill, Ledger, Order


class PaperBroker(Broker):
    def __init__(self, ledger: Ledger, slippage_pct: float = 0.05,
                 commission: float = 0.0, mode: str = "paper", cash_account: bool = False):
        super().__init__(ledger)
        self.slippage = slippage_pct / 100
        self.commission = commission
        self.mode = mode
        self.cash_account = cash_account

    def submit(self, order: Order, date: str):
        hold = self.gfv_hold(order, date)
        if hold:                                      # a good faith violation: wait for the money to settle
            self.note(hold)
            return None
        if order.side == "BUY":
            price = order.price * (1 + self.slippage)
            fractional = is_fraction(order.qty)       # the sizing already decided parts of a share are allowed
            affordable = floor_shares((self.buying_power(date) - self.commission) / price, fractional)
            qty = min(order.qty, affordable)
            if qty <= 0 or (fractional and qty * price < MIN_ORDER_VALUE):
                return None
        else:
            held = self.ledger.positions.get(order.ticker)
            price = order.price * (1 - self.slippage)
            qty = min(order.qty, held.qty if held else 0)
            if qty <= 0:                              # a part of a share can always be sold
                return None

        self.ledger.cash -= self.commission
        fill = Fill(date=date, ticker=order.ticker, side=order.side, qty=qty,
                    price=round(price, 4), reason=order.reason, order_id=f"{self.mode}-{uuid.uuid4().hex[:12]}")
        return self._book(fill)
