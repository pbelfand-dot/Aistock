"""Shared test helpers: fake (synthetic) prices so tests never need the internet."""
import numpy as np
import pandas as pd
import pytest

from aitrader.config import load_config


def make_bars(n_days=900, tickers=("AAA", "BBB", "CCC", "DDD"), seed=0, end="2026-09-25"):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end, periods=n_days)
    market_ret = rng.normal(0.0004, 0.01, n_days)

    def frame(returns):
        close = 100 * np.cumprod(1 + returns)
        return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                             "volume": rng.integers(1_000_000, 2_000_000, n_days).astype(float)}, index=dates)

    market = frame(market_ret)
    bars = {t: frame(0.8 * market_ret + rng.normal(0.0002, 0.015, n_days)) for t in tickers}
    return bars, market


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["data_dir"] = str(tmp_path)
    c["watchlist"] = ["AAA", "BBB", "CCC", "DDD"]
    c["benchmark"] = "MKT"
    c["llm"]["enabled"] = False
    c["ai"]["min_train_days"] = 300
    c["ai"]["retrain_every_days"] = 63   # fewer retrains = faster tests
    c["live_trading_enabled"] = False
    return c
