"""
strategies.py: the trading ideas the bot compares against each other.

Every strategy does the same job: for each day and each stock, give a score
from 0 to 1.
    score >= buy_above   -> "I want to own this"
    score <  sell_below  -> "get out"
    in between           -> "if we own it, keep it; if not, don't buy"

During the study month all of them are tested side by side. The trading plan
picks whichever proved best, or none if none are good enough.

To add your own idea: copy a class, change the rules, add it to all_strategies().
"""
import numpy as np
import pandas as pd

from .brain import Brain
from .features import rsi, sma


class Strategy:
    name = "base"
    description = ""
    buy_above = 0.6
    sell_below = 0.4

    def scores(self, bars: dict, market: pd.DataFrame) -> pd.DataFrame:
        """Rows = dates, columns = tickers, values = score 0..1 (NaN = no opinion)."""
        raise NotImplementedError


class TrendFollowing(Strategy):
    name = "trend_following"
    description = ("Ride uptrends: buy when price > 50-day average > 200-day average; "
                   "sell when price falls below the 50-day average.")

    def scores(self, bars, market):
        out = {}
        for ticker, df in bars.items():
            close = df["close"]
            s50, s200 = sma(close, 50), sma(close, 200)
            score = pd.Series(0.5, index=close.index)
            score[(close > s50) & (s50 > s200)] = 1.0
            score[close < s50] = 0.0
            out[ticker] = score.where(s200.notna())
        return pd.DataFrame(out)


class MeanReversion(Strategy):
    name = "mean_reversion"
    description = ("Buy sharp short-term dips (2-day RSI under 10) in stocks still above their "
                   "200-day average; sell on the bounce (close above the 5-day average).")

    def scores(self, bars, market):
        out = {}
        for ticker, df in bars.items():
            close = df["close"]
            s5, s200, rsi2 = sma(close, 5), sma(close, 200), rsi(close, 2)
            score = pd.Series(0.5, index=close.index)
            score[close > s5] = 0.0
            score[(rsi2 < 10) & (close > s200)] = 1.0
            out[ticker] = score.where(s200.notna())
        return pd.DataFrame(out)


class AIModel(Strategy):
    name = "ai_model"
    description = ("Local machine-learning model: buy when it estimates a high chance the price "
                   "is higher in N days; sell when that chance drops.")

    def __init__(self, brain: Brain, buy_above: float, sell_below: float):
        self.brain = brain
        self.buy_above = buy_above
        self.sell_below = sell_below

    def scores(self, bars, market):
        return self.brain.walk_forward_scores(bars, market)


def all_strategies(cfg: dict) -> list:
    brain = Brain(horizon_days=cfg["study"]["horizon_days"],
                  retrain_every_days=cfg["ai"]["retrain_every_days"],
                  min_train_days=cfg["ai"]["min_train_days"])
    return [
        TrendFollowing(),
        MeanReversion(),
        AIModel(brain, cfg["ai"]["buy_above"], cfg["ai"]["sell_below"]),
    ]


def get_strategy(name: str, cfg: dict) -> Strategy:
    for strategy in all_strategies(cfg):
        if strategy.name == name:
            return strategy
    raise ValueError(f"Unknown strategy '{name}'")


def latest_scores(strategy: Strategy, bars: dict, market: pd.DataFrame) -> pd.Series:
    """Today's score for each ticker (the last row)."""
    table = strategy.scores(bars, market)
    return table.iloc[-1] if len(table) else pd.Series(dtype=float, index=list(bars), data=np.nan)
