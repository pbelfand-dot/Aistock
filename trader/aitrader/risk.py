"""
risk.py: the rules that keep one bad idea from wiping out the account.

These rules apply in backtests, paper AND live, exactly the same way.
Each desk has its own numbers: `desks: <desk>: risk:` in config.yaml.
"""
import math
from dataclasses import dataclass, fields


@dataclass
class RiskManager:
    max_open_positions: int = 5
    max_position_pct: float = 20.0     # never more than this % of the account in one stock
    stop_loss_pct: float = 7.0         # sell if a position falls this % below what we paid
    daily_loss_limit_pct: float = 3.0  # down this much today -> no new buys today
    max_drawdown_pct: float = 15.0     # down this much from the best day -> kill switch
    cash_buffer_pct: float = 1.0       # always keep a little cash

    @classmethod
    def for_desk(cls, cfg: dict, desk: str) -> "RiskManager":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in cfg["desks"][desk]["risk"].items() if k in known})

    def max_share_price(self, desk_capital: float) -> float:
        """The most one share can cost and still fit in one position."""
        return desk_capital * self.max_position_pct / 100 * (1 - self.cash_buffer_pct / 100)

    def position_size(self, equity: float, buying_power: float, price: float) -> int:
        """How many WHOLE shares to buy (Schwab's API can't do fractional shares)."""
        if not price or math.isnan(price) or price <= 0:
            return 0
        budget = min(equity * self.max_position_pct / 100,
                     buying_power * (1 - self.cash_buffer_pct / 100))
        return max(0, math.floor(budget / price))

    TRIM_AT = 2.0                      # a stock grown to 2x its share of the desk is trimmed back to its share

    def trim_qty(self, qty: int, price: float, equity: float) -> int:
        """Shares to sell when one stock has grown far past its limit (e.g. after the limit was lowered
        from 34% to 12.5%): back down to the limit, whole shares. 0 = leave it alone."""
        if not price or math.isnan(price) or price <= 0 or equity <= 0:
            return 0
        limit = equity * self.max_position_pct / 100
        if qty * price <= limit * self.TRIM_AT:
            return 0
        return max(0, qty - math.floor(limit / price))

    def stop_loss_hit(self, avg_cost: float, price: float) -> bool:
        return price <= avg_cost * (1 - self.stop_loss_pct / 100)

    def new_buys_allowed(self, equity: float, yesterday_equity) -> tuple:
        if yesterday_equity and equity < yesterday_equity * (1 - self.daily_loss_limit_pct / 100):
            return False, f"daily loss limit hit (down more than {self.daily_loss_limit_pct}% today)"
        return True, ""

    def kill_switch_tripped(self, equity: float, peak_equity: float) -> bool:
        return peak_equity > 0 and equity <= peak_equity * (1 - self.max_drawdown_pct / 100)
