"""The AI must never peek at the future, and the phase rules must hold."""
from datetime import date

import numpy as np
import pandas as pd

from aitrader.brain import Brain
from aitrader.engine import run_backtest
from aitrader.features import make_features
from aitrader.phases import check_promotion, study_progress
from aitrader.storage import Store
from aitrader.strategies import all_strategies

from conftest import make_bars


def scramble_after(bars: dict, market: pd.DataFrame, cutoff):
    """Replace every price AFTER `cutoff` with random junk."""
    rng = np.random.default_rng(99)
    def junk(df):
        df = df.copy()
        after = df.index > cutoff
        df.loc[after, ["open", "high", "low", "close"]] *= rng.uniform(0.5, 1.5, (after.sum(), 1))
        return df
    return {t: junk(df) for t, df in bars.items()}, junk(market)


def test_features_do_not_peek_at_the_future():
    bars, market = make_bars()
    cutoff = bars["AAA"].index[600]
    bars2, market2 = scramble_after(bars, market, cutoff)
    f1 = make_features(bars["AAA"], market).loc[:cutoff]
    f2 = make_features(bars2["AAA"], market2).loc[:cutoff]
    pd.testing.assert_frame_equal(f1, f2)


def test_ai_scores_do_not_peek_at_the_future():
    bars, market = make_bars()
    brain = Brain(horizon_days=5, retrain_every_days=21, min_train_days=300)
    cutoff = bars["AAA"].index[650]
    s1 = brain.walk_forward_scores(bars, market).loc[:cutoff]
    s2 = brain.walk_forward_scores(*scramble_after(bars, market, cutoff)).loc[:cutoff]
    assert s1.notna().sum().sum() > 0
    pd.testing.assert_frame_equal(s1, s2)


def test_every_strategy_backtests(cfg):
    bars, market = make_bars()
    for strategy in all_strategies(cfg):
        result = run_backtest(strategy, bars, market, cfg)
        assert result["trading_days"] > 0, strategy.name
        assert result["max_drawdown_pct"] >= 0


def test_study_progress_needs_a_month(cfg, tmp_path):
    store = Store(tmp_path / "t.sqlite")
    store.set("study_started_on", "2026-09-01")
    for i in range(20):
        store.add_prediction(f"2026-09-{i + 1:02d}", "AAA", "x", 0.5, 100, 5)
    assert not study_progress(store, cfg, today=date(2026, 9, 20))["ready"]
    assert study_progress(store, cfg, today=date(2026, 10, 1))["ready"]


def test_promotion_requires_every_rule(cfg):
    good = {"trading_days": 40, "num_closed_trades": 25, "total_return_pct": 4.0,
            "profit_factor": 1.5, "max_drawdown_pct": 5.0}
    assert all(ok for *_, ok in check_promotion(cfg, good, benchmark_return_pct=2.0))
    assert not all(ok for *_, ok in check_promotion(cfg, good, benchmark_return_pct=6.0))   # lost to SPY
    assert not all(ok for *_, ok in check_promotion(cfg, {**good, "max_drawdown_pct": 12}, 2.0))
