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
    calm = False                             # True = smaller buys when its stocks get stormy (see exposure)

    def scores(self, bars: dict, market: pd.DataFrame, since=None) -> pd.DataFrame:
        """Rows = times, columns = tickers, values = score 0..1 (NaN = no opinion).
        `since` lets slow strategies skip work on old rows (rule-based ones ignore it)."""
        raise NotImplementedError

    def exposure(self, bars: dict, market: pd.DataFrame, scores: pd.DataFrame):
        """How big its new buys are at each moment, as a share of the usual size (1.0 = full size), or None
        for always full size. Calm strategies scale down when the stocks they pick get stormy."""
        return basket_exposure(bars, scores, self.buy_above) if self.calm else None


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


def basket_exposure(bars: dict, scores: pd.DataFrame, buy_above: float, window: int = 126,
                    floor: float = 0.3) -> pd.Series:
    """Volatility scaling (Barroso & Santa-Clara 2015, "Momentum has its moments"; Moreira & Muir 2017):
    the daily return of an equal-weight basket of the stocks it wanted to buy the day before, its realized
    volatility over the last 6 months, and the size of new buys = its usual (median) volatility so far
    divided by today's, at most 1.0 (no borrowing) and at least `floor`. Momentum's worst crashes came in
    stormy markets, so this buys less exactly then. Only past prices are used."""
    closes = pd.DataFrame({t: df["close"] for t, df in bars.items()}).sort_index()
    wanted = (scores.reindex(index=closes.index, columns=closes.columns) >= buy_above).shift(1)
    wanted = wanted.astype("boolean").fillna(False).astype(bool)
    basket = closes.pct_change(fill_method=None).where(wanted).mean(axis=1)
    vol = basket.rolling(window, min_periods=window // 2).std() * np.sqrt(252)
    usual = vol.expanding(min_periods=window).median()
    return (usual / vol).clip(lower=floor, upper=1.0).fillna(1.0)


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

    def ranking(self, bars: dict, market: pd.DataFrame) -> pd.DataFrame:
        """What it ranks the stocks by (higher = stronger): the 12-1 month return."""
        return pd.DataFrame({t: df["close"].shift(self.skip) / df["close"].shift(self.months) - 1
                             for t, df in bars.items()})

    def scores(self, bars, market, since=None):
        uptrend = pd.DataFrame({t: (df["close"] > sma(df["close"], 200)).where(sma(df["close"], 200).notna())
                                for t, df in bars.items()})
        momentum = self.ranking(bars, market).reindex(index=uptrend.index, columns=uptrend.columns)
        score = momentum.rank(axis=1, pct=True)
        score = score.where(uptrend.astype("boolean").fillna(False).astype(bool), 0.0).where(momentum.notna())
        benchmark = market["close"]
        market_up = (benchmark > sma(benchmark, 200)).reindex(score.index, method="ffill").fillna(False)
        capped = score.clip(upper=self.buy_above - 0.01)       # keep what it owns, buy nothing new
        return score.where(market_up.astype(bool), capped, axis=0)


class MomentumPlus(Momentum):
    """Challenger (challengers.py): momentum ranked with three findings that held up in published research,
    all from the daily prices Kestrel already has:
      residual momentum  (Blitz, Huij & Martens 2011): the stock's own climb with the market's part taken
                         out, divided by how jumpy that climb was. Their test: about the same return as plain
                         momentum with roughly half the risk, and far smaller crashes.
      frog in the pan    (Da, Gurun & Warachka 2014): a climb made of many small up days keeps going more
                         reliably than one made of a few big jumps (the news that drove it sank in slowly).
      52-week high       (George & Hwang 2004): stocks near their 52-week high kept rising more often.
    Half the rank is residual momentum, a quarter each the other two. Same buy and sell bars, 200-day trend
    filter and S&P 500 filter as momentum."""
    name = "momentum_plus"
    description = ("Momentum, sharper: ranks stocks by their own climb over 12 months (skipping the latest month) "
                   "with the market's part taken out, divided by how jumpy the climb was; prefers smooth climbs "
                   "made of many small up days and stocks near their 52-week high. Same buy/sell rules, 200-day "
                   "filter and S&P 500 filter as momentum.")

    def ranking(self, bars, market):
        closes = pd.DataFrame({t: df["close"] for t, df in bars.items()}).sort_index()
        highs = pd.DataFrame({t: df["high"] for t, df in bars.items()}).reindex(closes.index)
        returns = np.log(closes).diff()
        m = np.log(market["close"].reindex(closes.index).ffill()).diff()
        w = self.months - self.skip                                     # the 11-month formation window
        mean_r, mean_m = returns.rolling(w).mean(), m.rolling(w).mean()
        cov = returns.mul(m, axis=0).rolling(w).mean() - mean_r.mul(mean_m, axis=0)
        var_m = (m ** 2).rolling(w).mean() - mean_m ** 2
        beta = cov.div(var_m, axis=0)
        var_resid = ((returns ** 2).rolling(w).mean() - mean_r ** 2 - (beta ** 2).mul(var_m, axis=0)).clip(lower=1e-12)
        residual = (returns.rolling(w).sum() - beta.mul(m.rolling(w).sum(), axis=0)) / np.sqrt(var_resid * w)
        up, down = (returns > 0).rolling(w).mean(), (returns < 0).rolling(w).mean()
        smooth = np.sign(returns.rolling(w).sum()) * (up - down)        # frog in the pan, flipped: higher = smoother
        residual, smooth = residual.shift(self.skip), smooth.shift(self.skip)
        near_high = closes / highs.rolling(self.months, min_periods=self.months).max()
        rank = lambda x: x.rank(axis=1, pct=True)
        blend = 0.5 * rank(residual) + 0.25 * rank(smooth) + 0.25 * rank(near_high)
        return blend.where(residual.notna() & smooth.notna() & near_high.notna())


class MomentumCalm(Momentum):
    """Challenger: plain momentum, with smaller buys when its stocks get stormy (basket_exposure)."""
    name = "momentum_calm"
    calm = True
    description = ("Momentum with volatility scaling: the same picks, but new buys get smaller (down to 30% of "
                   "the usual size) when the stocks momentum picks have been much jumpier than usual over the "
                   "last 6 months, the conditions in which momentum crashed in the past.")


class MomentumPlusCalm(MomentumPlus):
    """Challenger: momentum_plus with momentum_calm's volatility scaling."""
    name = "momentum_plus_calm"
    calm = True
    description = ("momentum_plus's sharper ranking with momentum_calm's volatility scaling: smaller new buys "
                   "when its stocks have been much jumpier than usual.")


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


def daily_atr(df: pd.DataFrame, days: int = 14) -> pd.Series:
    """For 5-minute bars: the stock's average daily range (true range) over the previous `days` days,
    known at the open of each day (today's own range isn't used), on every row of that day."""
    day = session_day(df)
    daily = df.groupby(day).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    prev = daily["close"].shift(1)
    true_range = pd.concat([daily["high"] - daily["low"], (daily["high"] - prev).abs(), (daily["low"] - prev).abs()],
                           axis=1).max(axis=1)
    atr = true_range.rolling(days).mean().shift(1)
    return pd.Series(day.map(atr).to_numpy(), index=df.index, dtype=float)


class OpeningRange5(Strategy):
    """The research version of the opening-range breakout (Zarattini, Barbon & Aziz 2024, "A Profitable
    Day Trading Strategy For The U.S. Equity Market"), long only. In their test (2016-2023, before
    slippage) it made money on stocks in play and about nothing on all stocks; a 30-minute range did
    much worse than 5 minutes. Their numbers were long AND short with borrowed money, so the bot's own
    shadow trades decide whether it earns a place."""
    name = "orb_5min"
    style = "day"
    description = ("The research version of the breakout, long only: the first 5 minutes set the range. If that "
                   "first candle closed up, buy when the price breaks above its high; sell if it falls 10% of the "
                   "stock's usual daily range (14-day ATR) below that high, otherwise hold to the close. One try "
                   "per stock a day. It worked on stocks in play (unusual opening volume), not on random stocks.")
    stop_atr = 0.10

    def scores(self, bars, market, since=None):
        out = {}
        for ticker, df in bars.items():
            day, minutes, close = session_day(df), minutes_since_open(df), df["close"]
            first = minutes < 5
            first_open = df["open"].where(first).groupby(day).transform("first")
            first_close = df["close"].where(first).groupby(day).transform("first")
            first_high = df["high"].where(first).groupby(day).transform("max")
            stop = first_high - self.stop_atr * daily_atr(df)
            stopped = (close < stop).astype(int).groupby(day).cummax().astype(bool)   # one try a day
            score = pd.Series(0.5, index=df.index)
            score[(close > first_high) & (first_close > first_open) & ~stopped] = 1.0
            score[stopped] = 0.0
            out[ticker] = score.mask(first | stop.isna())
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
                AIModel("swing", brain, ai["buy_above"], ai["sell_below"]),
                MomentumPlus(), MomentumCalm(), MomentumPlusCalm()]           # challengers (challengers.py)
    brain = Brain(horizon=ai["horizon"], retrain_every=ai["retrain_every"], min_train=ai["min_train"],
                  intraday=True)
    from .tjr import TJRModel                            # Stage 2: TJR's model (tjr.py)
    return [OpeningRangeBreakout(), OpeningRange5(), VwapReversion(),
            AIModel("day", brain, ai["buy_above"], ai["sell_below"]), TJRModel()]


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
