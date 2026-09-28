"""
features.py: turns raw prices into numbers the AI can learn from.

GOLDEN RULE: every number for a given day only uses prices up to that day.
If the AI ever "peeks" at tomorrow, it looks brilliant in tests and loses
money for real. That's the most common way home-made trading bots fool
their owners.
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


def sma(series: pd.Series, days: int) -> pd.Series:
    """Simple moving average: the average close of the last `days` days."""
    return series.rolling(days, min_periods=days).mean()


def rsi(series: pd.Series, days: int = 14) -> pd.Series:
    """Relative Strength Index, 0-100. Under 30 = beaten down, over 70 = stretched."""
    change = series.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / days, min_periods=days, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / days, min_periods=days, adjust=False).mean()
    out = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return out.mask((loss == 0) & gain.notna(), 100.0)


def make_features(bars: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """One row per day, one column per feature, for a single stock."""
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
    return f.replace([np.inf, -np.inf], np.nan)


def make_label(bars: pd.DataFrame, horizon_days: int) -> pd.Series:
    """The answer the AI tries to learn: 1 if the price is higher `horizon_days`
    trading days later, else 0. Blank (NaN) when that future hasn't happened yet."""
    future_return = bars["close"].shift(-horizon_days) / bars["close"] - 1
    return (future_return > 0).astype(float).where(future_return.notna())
