"""
performance.py: the scorecard.

  total_return_pct   how much the account grew
  max_drawdown_pct   worst drop from a high point (how much pain you'd sit through)
  sharpe             return per unit of bumpiness; above 1 is good, below 0.5 is meh
  win_rate_pct       % of closed trades that made money
  profit_factor      $ won / $ lost on closed trades; above 1 = making money
"""
import math

import pandas as pd


def summarize(equity: pd.Series, fills: pd.DataFrame = None) -> dict:
    equity = equity.dropna()
    result = {"trading_days": int(len(equity)), "total_return_pct": 0.0, "cagr_pct": 0.0,
              "sharpe": 0.0, "max_drawdown_pct": 0.0, "num_closed_trades": 0,
              "win_rate_pct": 0.0, "profit_factor": 0.0}

    if len(equity) >= 2 and equity.iloc[0] > 0:
        growth = equity.iloc[-1] / equity.iloc[0]
        daily = equity.pct_change().dropna()
        years = len(equity) / 252
        result["total_return_pct"] = (growth - 1) * 100
        result["cagr_pct"] = (growth ** (1 / years) - 1) * 100 if growth > 0 else -100.0
        if daily.std() > 0:
            result["sharpe"] = daily.mean() / daily.std() * math.sqrt(252)
        result["max_drawdown_pct"] = float(-(equity / equity.cummax() - 1).min() * 100)

    if fills is not None and len(fills):
        closed = fills[fills["side"] == "SELL"]["realized_pnl"]
        won, lost = closed[closed > 0].sum(), -closed[closed < 0].sum()
        result["num_closed_trades"] = int(len(closed))
        result["win_rate_pct"] = float((closed > 0).mean() * 100) if len(closed) else 0.0
        result["profit_factor"] = float(won / lost) if lost > 0 else (99.0 if won > 0 else 0.0)

    return {k: round(v, 3) if isinstance(v, float) else v for k, v in result.items()}


def buy_and_hold(prices: pd.Series, starting_cash: float) -> pd.Series:
    """What the account would look like if you just bought and held."""
    prices = prices.dropna()
    return prices / prices.iloc[0] * starting_cash
