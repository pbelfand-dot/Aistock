"""Shared test helpers: fake (synthetic) prices so tests never need the internet."""
import numpy as np
import pandas as pd
import pytest

from aitrader.config import load_config

SWING = ("AAA", "BBB", "CCC", "DDD")
DAY = ("EEE", "FFF", "GGG", "HHH")


def _frame(close, index, rng):
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.002,
                         "low": np.minimum(open_, close) * 0.998, "close": close,
                         "volume": rng.integers(100_000, 200_000, len(index)).astype(float)}, index=index)


def make_bars(n_days=900, tickers=SWING, seed=0, end="2026-09-25"):
    """Daily bars."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end, periods=n_days)
    market_ret = rng.normal(0.0004, 0.01, n_days)
    market = _frame(100 * np.cumprod(1 + market_ret), dates, rng)
    bars = {t: _frame(100 * np.cumprod(1 + 0.8 * market_ret + rng.normal(0.0002, 0.015, n_days)), dates, rng)
            for t in tickers}
    return bars, market


def make_intraday_bars(n_days=30, tickers=DAY, seed=1, end="2026-09-25"):
    """5-minute bars, 9:30-3:55pm (78 per day)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=end, periods=n_days)
    index = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 5 * i) for d in days for i in range(78)])
    market_ret = rng.normal(0, 0.001, len(index))
    market = _frame(100 * np.cumprod(1 + market_ret), index, rng)
    bars = {t: _frame(50 * np.cumprod(1 + 0.8 * market_ret + rng.normal(0, 0.002, len(index))), index, rng)
            for t in tickers}
    return bars, market


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["data_dir"] = str(tmp_path)
    c["desks"]["swing"]["watchlist"] = list(SWING)
    c["desks"]["day"]["watchlist"] = list(DAY)
    c["benchmark"] = "MKT"
    c["paper"]["starting_cash"] = 10000
    c["llm"]["enabled"] = False
    c["ai"]["swing"].update(min_train=300, retrain_every=63)   # smaller = faster tests
    c["ai"]["day"].update(min_train=780, retrain_every=390)
    c["live_trading_enabled"] = False
    c["secrets"] = {k: "" for k in c["secrets"]}      # never use the real keys in .env during tests
    return c
