"""
brokers/paper.py: fake money, real prices.

Schwab's API has NO paper-trading mode (every API order is real), so paper
trading is simulated here. To keep it honest, every fill is a bit WORSE than
the quoted price (slippage). Real orders rarely fill at the exact price you saw.
The backtester uses this same class, so tests and paper play by the same rules.
"""
import math

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
        if order.side == "BUY":
            price = order.price * (1 + self.slippage)
            affordable = math.floor((self.buying_power(date) - self.commission) / price)
            qty = min(order.qty, affordable)
        else:
            held = self.ledger.positions.get(order.ticker)
            price = order.price * (1 - self.slippage)
            qty = min(order.qty, held.qty if held else 0)
        if qty < 1:
            return None

        self.ledger.cash -= self.commission
        fill = Fill(date=date, ticker=order.ticker, side=order.side, qty=qty,
                    price=round(price, 4), reason=order.reason, order_id=f"{self.mode}-{date}-{order.ticker}")
        return self.ledger.apply(fill)
