"""
strategies.py: the trading ideas the bot compares against each other.

Every strategy does the same job: for each moment and each stock, give a
score from 0 to 1.
    score >= buy_above   -> "I want to own this"
    score <  sell_below  -> "get out"
    in between           -> "if we own it, keep it; if not, don't buy"

Each strategy belongs to a desk ("style"):
    swing  daily bars, holds days to weeks
    day    5-minute bars, always sold before the close

During the study month all of them are tested side by side. Each desk's
plan picks whichever proved best, or none if none are good enough.

To add your own idea: copy a class, change the rules, add it to all_strategies().
"""
import numpy as np
import pandas as pd

from .brain import Brain
from .features import minutes_since_open, rsi, session_day, sma, vwap


class Strategy:
    name = "base"
    style = "swing"
    description = ""
    buy_above = 0.6
    sell_below = 0.4

    def scores(self, bars: dict, market: pd.DataFrame, since=None) -> pd.DataFrame:
        """Rows = times, columns = tickers, values = score 0..1 (NaN = no opinion).
        `since` lets slow strategies skip work on old rows (rule-based ones ignore it)."""
        raise NotImplementedError


# ---------------------------------------------------------------- swing desk
class TrendFollowing(Strategy):
    name = "trend_following"
    description = ("Ride uptrends: buy when price > 50-day average > 200-day average; "
                   "sell when price falls below the 50-day average.")

    def scores(self, bars, market, since=None):
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

    def scores(self, bars, market, since=None):
        out = {}
        for ticker, df in bars.items():
            close = df["close"]
            s5, s200, rsi2 = sma(close, 5), sma(close, 200), rsi(close, 2)
            score = pd.Series(0.5, index=close.index)
            score[close > s5] = 0.0
            score[(rsi2 < 10) & (close > s200)] = 1.0
            out[ticker] = score.where(s200.notna())
        return pd.DataFrame(out)


class Momentum(Strategy):
    """Stage 1's method: the one the 16-year research backed (research/history/RESULTS-methods.md).
    The score is the stock's rank among everything on the list by its 12-1 month return, so 1.0 is
    the strongest. Buying needs the top 20%; holding needs the top half (the gap stops it trading
    back and forth every day)."""
    name = "momentum"
    description = ("Own the strongest stocks: rank every stock on the list (the watchlist plus the top of "
                   "the daily all-stocks scan) by its return over the last 12 months, skipping the latest "
                   "month. Buy from the top 20% while the stock is above its 200-day average; sell when it "
                   "drops out of the top half or below its 200-day average. No new buys while the S&P 500 "
                   "is below its own 200-day average.")
    buy_above = 0.8
    sell_below = 0.5
    months, skip = 252, 21                   # trading days in 12 months and in the skipped latest month

    def scores(self, bars, market, since=None):
        momentum, uptrend = {}, {}
        for ticker, df in bars.items():
            close = df["close"]
            momentum[ticker] = close.shift(self.skip) / close.shift(self.months) - 1
            uptrend[ticker] = (close > sma(close, 200)).where(sma(close, 200).notna())
        momentum, uptrend = pd.DataFrame(momentum), pd.DataFrame(uptrend)
        score = momentum.rank(axis=1, pct=True)
        score = score.where(uptrend.fillna(False).astype(bool), 0.0).where(momentum.notna())
        benchmark = market["close"]
        market_up = (benchmark > sma(benchmark, 200)).reindex(score.index, method="ffill").fillna(False)
        capped = score.clip(upper=self.buy_above - 0.01)       # keep what it owns, buy nothing new
        return score.where(market_up.astype(bool), capped, axis=0)


# ---------------------------------------------------------------- day desk
class OpeningRangeBreakout(Strategy):
    name = "opening_range_breakout"
    style = "day"
    description = ("Watch the first 30 minutes to set the day's 'opening range'. Buy if the price "
                   "breaks above that range's high; exit if it falls back below the range's middle.")

    def scores(self, bars, market, since=None):
        out = {}
        for ticker, df in bars.items():
            day, minutes, close = session_day(df), minutes_since_open(df), df["close"]
            in_range = minutes < 30
            range_high = df["high"].where(in_range).groupby(day).transform("max")
            range_low = df["low"].where(in_range).groupby(day).transform("min")
            score = pd.Series(0.5, index=df.index)
            score[close < (range_high + range_low) / 2] = 0.0
            score[close > range_high] = 1.0
            out[ticker] = score.mask(in_range)          # no opinion while the range is forming
        return pd.DataFrame(out)


class VwapReversion(Strategy):
    name = "vwap_reversion"
    style = "day"
    description = ("Buy when the price drops well below today's average traded price (VWAP) and "
                   "looks oversold; sell when it gets back to the average.")
    dip_pct = 0.5

    def scores(self, bars, market, since=None):
        out = {}
        for ticker, df in bars.items():
            close, avg, r = df["close"], vwap(df), rsi(df["close"], 14)
            score = pd.Series(0.5, index=df.index)
            score[close >= avg] = 0.0
            score[(close < avg * (1 - self.dip_pct / 100)) & (r < 30)] = 1.0
            out[ticker] = score.mask(minutes_since_open(df) < 15)   # skip the chaotic first 15 minutes
        return pd.DataFrame(out)


# ---------------------------------------------------------------- the AI (both desks)
class AIModel(Strategy):
    def __init__(self, style: str, brain: Brain, buy_above: float, sell_below: float):
        self.style = style
        self.name = f"ai_{style}"
        self.brain = brain
        self.buy_above = buy_above
        self.sell_below = sell_below
        self.description = ("Local machine-learning model: buy when it estimates a high chance the "
                            "price will be higher " + ("in 5 days" if style == "swing" else
                                                       "in an hour (before the close)") +
                            "; sell when that chance drops.")

    def scores(self, bars, market, since=None):
        return self.brain.walk_forward_scores(bars, market, since=since)


def all_strategies(cfg: dict, style: str) -> list:
    ai = cfg["ai"][style]
    if style == "swing":
        brain = Brain(horizon=cfg["study"]["horizon_days"], retrain_every=ai["retrain_every"],
                      min_train=ai["min_train"])
        return [TrendFollowing(), MeanReversion(), Momentum(),
                AIModel("swing", brain, ai["buy_above"], ai["sell_below"])]
    brain = Brain(horizon=ai["horizon"], retrain_every=ai["retrain_every"], min_train=ai["min_train"],
                  intraday=True)
    return [OpeningRangeBreakout(), VwapReversion(), AIModel("day", brain, ai["buy_above"], ai["sell_below"])]


def get_strategy(name: str, cfg: dict, style: str) -> Strategy:
    for strategy in all_strategies(cfg, style):
        if strategy.name == name:
            return strategy
    raise ValueError(f"Unknown {style} strategy '{name}'")


def current_scores(strategy: Strategy, bars: dict, market: pd.DataFrame) -> pd.Series:
    """The latest score for each ticker (only computes what's needed)."""
    last = max(df.index[-1] for df in bars.values())
    table = strategy.scores(bars, market, since=last)
    if not len(table):
        return pd.Series(np.nan, index=list(bars))
    return table.reindex(columns=list(bars)).iloc[-1]
