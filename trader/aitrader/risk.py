"""
risk.py: the rules that keep one bad idea from wiping out the account.

These rules apply in backtests, paper AND live, exactly the same way.
Each desk has its own numbers: `desks: <desk>: risk:` in config.yaml.
"""
import math
from dataclasses import dataclass, fields

DECIMALS = 4                           # fractional shares: 0.0001 of a share (Alpaca takes up to 9 decimals)
MIN_ORDER_VALUE = 1.00                 # Alpaca's smallest fractional order is $1


def shares(qty) -> float:
    """A share count, tidy: whole numbers stay whole (3, not 3.0000000001), fractions keep 6 decimals."""
    q = round(float(qty), 6)
    return int(round(q)) if abs(q - round(q)) < 1e-6 else q


def floor_shares(qty: float, fractional: bool) -> float:
    """Round DOWN to what can be bought: whole shares, or 0.0001 of a share."""
    if not qty or qty <= 0 or math.isnan(qty):
        return 0
    if not fractional:
        return int(math.floor(qty + 1e-9))
    step = 10 ** DECIMALS
    return shares(math.floor(qty * step + 1e-6) / step)


def is_fraction(qty) -> bool:
    return abs(float(qty) - round(float(qty))) > 1e-6


@dataclass
class RiskManager:
    max_open_positions: int = 5
    max_position_pct: float = 20.0     # never more than this % of the account in one stock
    stop_loss_pct: float = 7.0         # sell if a position falls this % below what we paid
    daily_loss_limit_pct: float = 3.0  # down this much today -> no new buys today
    max_drawdown_pct: float = 15.0     # down this much from the best day -> kill switch
    cash_buffer_pct: float = 1.0       # always keep a little cash
    fractional: bool = False           # may buy parts of a share (where the orders go can: config.fractional_allowed)
    # Stops sized to how much each stock usually moves (0 = the fixed stop_loss_pct for every stock):
    stop_atr_multiple: float = 0.0     # stop = this many times the stock's usual daily range (14-day ATR) ...
    stop_min_pct: float = 1.0          # ... but at least this far below the buy price
    stop_max_pct: float = 5.0          # ... and at most this far
    risk_per_trade_pct: float = 0.0    # a wider stop means a smaller position: at most this % of the desk lost at
                                       # the stop (0 = off). Never bigger than max_position_pct either.

    @classmethod
    def for_desk(cls, cfg: dict, desk: str, live: bool = False) -> "RiskManager":
        """The desk's rules. Fractional shares follow where its orders go (live: the real-money broker;
        otherwise the paper account, which in-its-head practice copies)."""
        from .config import fractional_allowed
        known = {f.name for f in fields(cls)} - {"fractional"}
        return cls(**{k: v for k, v in cfg["desks"][desk]["risk"].items() if k in known},
                   fractional=fractional_allowed(cfg, live=live))

    def max_share_price(self, desk_capital: float) -> float:
        """The most one share can cost and still fit in one position (no limit with fractional shares)."""
        if self.fractional:
            return float("inf")
        return desk_capital * self.max_position_pct / 100 * (1 - self.cash_buffer_pct / 100)

    def stop_for(self, atr_pct: float = None) -> float:
        """This stock's stop-loss distance in %: sized to its usual daily range when that's set up and
        known, otherwise the desk's fixed stop."""
        if not self.stop_atr_multiple or not atr_pct or math.isnan(atr_pct) or atr_pct <= 0:
            return self.stop_loss_pct
        return round(min(self.stop_max_pct, max(self.stop_min_pct, self.stop_atr_multiple * atr_pct)), 2)

    def position_size(self, equity: float, buying_power: float, price: float, stop_pct: float = None) -> float:
        """How many shares to buy: whole shares (Schwab's and Webull's APIs), or down to 0.0001 of a
        share with fractional shares (at least $1 worth). 0 = nothing affordable. With risk_per_trade_pct,
        a wider stop buys less, so a jumpy stock never risks more than a calm one."""
        if not price or math.isnan(price) or price <= 0:
            return 0
        budget = min(equity * self.max_position_pct / 100,
                     buying_power * (1 - self.cash_buffer_pct / 100))
        if self.risk_per_trade_pct and stop_pct:
            budget = min(budget, equity * self.risk_per_trade_pct / stop_pct)
        qty = floor_shares(budget / price, self.fractional)
        return qty if qty * price >= (MIN_ORDER_VALUE if self.fractional else 0) else 0

    TRIM_AT = 2.0                      # a stock grown to 2x its share of the desk is trimmed back to its share

    def trim_qty(self, qty: float, price: float, equity: float) -> float:
        """Shares to sell when one stock has grown far past its limit (e.g. after the limit was lowered
        from 34% to 12.5%): back down to the limit, whole shares. 0 = leave it alone."""
        if not price or math.isnan(price) or price <= 0 or equity <= 0:
            return 0
        limit = equity * self.max_position_pct / 100
        if qty * price <= limit * self.TRIM_AT:
            return 0
        keep = floor_shares(limit / price, self.fractional)
        return max(0, shares(qty - keep))

    def stop_loss_hit(self, avg_cost: float, price: float, stop_pct: float = None) -> bool:
        return price <= avg_cost * (1 - (stop_pct or self.stop_loss_pct) / 100)

    def new_buys_allowed(self, equity: float, yesterday_equity) -> tuple:
        if yesterday_equity and equity < yesterday_equity * (1 - self.daily_loss_limit_pct / 100):
            return False, f"daily loss limit hit (down more than {self.daily_loss_limit_pct}% today)"
        return True, ""

    def kill_switch_tripped(self, equity: float, peak_equity: float) -> bool:
        return peak_equity > 0 and equity <= peak_equity * (1 - self.max_drawdown_pct / 100)
