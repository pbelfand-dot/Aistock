"""
features.py: turns raw prices into numbers the AI can learn from.

GOLDEN RULE: every number for a given moment only uses prices up to that
moment. If the AI ever "peeks" at the future, it looks brilliant in tests and
loses money for real. That's the most common way home-made trading bots fool
their owners. (tests/test_ai_and_phases.py checks this.)

The same features work on daily bars (swing desk) and 5-minute bars (day desk).
"Days" below means "bars": on 5-minute data, sma50 = the last 50 five-minute bars.
"""
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "ret_1d", "ret_5d", "ret_20d",               # how much it moved recently
    "dist_sma20", "dist_sma50", "dist_sma200",   # how far above/below its averages
    "rsi_14",                                     # beaten down (low) or stretched (high)
    "volatility_20d",                             # how jumpy it's been
    "volume_ratio",                               # unusual trading activity
    "market_ret_20d", "market_dist_sma200",       # what the whole market is doing
]
INTRADAY_COLUMNS = FEATURE_COLUMNS + [
    "minutes_since_open",                         # the market behaves differently at 9:45 vs 3:30
    "dist_vwap",                                  # above/below today's average traded price
    "ret_since_open",                             # how today is going so far
]


def sma(series: pd.Series, bars: int) -> pd.Series:
    """Simple moving average of the last `bars` closes."""
    return series.rolling(bars, min_periods=bars).mean()


def rsi(series: pd.Series, bars: int = 14) -> pd.Series:
    """Relative Strength Index, 0-100. Under 30 = beaten down, over 70 = stretched."""
    change = series.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / bars, min_periods=bars, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / bars, min_periods=bars, adjust=False).mean()
    out = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return out.mask((loss == 0) & gain.notna(), 100.0)


def session_day(bars: pd.DataFrame) -> pd.Index:
    """The calendar day of each bar (to group 5-minute bars into trading days)."""
    return bars.index.normalize()


def vwap(bars: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price since today's open (resets every day)."""
    day = session_day(bars)
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3
    traded = (typical * bars["volume"]).groupby(day).cumsum()
    volume = bars["volume"].groupby(day).cumsum()
    return traded / volume.replace(0, np.nan)


def minutes_since_open(bars: pd.DataFrame) -> pd.Series:
    since_midnight = (bars.index - session_day(bars)) / pd.Timedelta(minutes=1)
    return pd.Series(since_midnight - 570, index=bars.index)       # 570 min = 9:30am


def make_features(bars: pd.DataFrame, market: pd.DataFrame, intraday: bool = False) -> pd.DataFrame:
    """One row per bar, one column per feature, for a single stock."""
    close, volume = bars["close"], bars["volume"]
    m = market["close"].reindex(bars.index).ffill()

    f = pd.DataFrame(index=bars.index)
    f["ret_1d"] = close.pct_change(1)
    f["ret_5d"] = close.pct_change(5)
    f["ret_20d"] = close.pct_change(20)
    f["dist_sma20"] = close / sma(close, 20) - 1
    f["dist_sma50"] = close / sma(close, 50) - 1
    f["dist_sma200"] = close / sma(close, 200) - 1
    f["rsi_14"] = rsi(close, 14) / 100
    f["volatility_20d"] = f["ret_1d"].rolling(20).std()
    f["volume_ratio"] = volume / volume.rolling(20).mean()
    f["market_ret_20d"] = m.pct_change(20)
    f["market_dist_sma200"] = m / sma(m, 200) - 1
    if intraday:
        f["minutes_since_open"] = minutes_since_open(bars)
        f["dist_vwap"] = close / vwap(bars) - 1
        f["ret_since_open"] = close / bars["open"].groupby(session_day(bars)).transform("first") - 1
    return f.replace([np.inf, -np.inf], np.nan)


def make_label(bars: pd.DataFrame, horizon: int, same_day: bool = False) -> pd.Series:
    """The answer the AI tries to learn: 1 if the price is higher `horizon` bars
    later, else 0. Blank (NaN) when that future hasn't happened yet.
    same_day=True (day trading): blank if the horizon runs past today's close,
    because a day trade never holds overnight."""
    close = bars["close"]
    future = close.groupby(session_day(bars)).shift(-horizon) if same_day else close.shift(-horizon)
    future_return = future / close - 1
    return (future_return > 0).astype(float).where(future_return.notna())


def label_known_at(bars: pd.DataFrame, horizon: int, same_day: bool = False) -> pd.Series:
    """WHEN each answer becomes known (the time of the future bar it looks at).
    The AI may only train on answers known by the time it's trained."""
    times = pd.Series(bars.index, index=bars.index)
    return times.groupby(session_day(bars)).shift(-horizon) if same_day else times.shift(-horizon)
