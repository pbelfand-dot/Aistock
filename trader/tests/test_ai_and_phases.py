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

from conftest import make_bars, make_intraday_bars


def scramble_after(bars: dict, market: pd.DataFrame, cutoff):
    """Replace every price AFTER `cutoff` with random junk."""
    rng = np.random.default_rng(99)

    def junk(df):
        df = df.copy()
        after = df.index > cutoff
        df.loc[after, ["open", "high", "low", "close", "volume"]] *= rng.uniform(0.5, 1.5, (after.sum(), 1))
        return df
    return {t: junk(df) for t, df in bars.items()}, junk(market)


def test_features_do_not_peek_at_the_future():
    for bars, market, intraday in [(*make_bars(), False), (*make_intraday_bars(), True)]:
        ticker = list(bars)[0]
        cutoff = bars[ticker].index[600]
        bars2, market2 = scramble_after(bars, market, cutoff)
        f1 = make_features(bars[ticker], market, intraday).loc[:cutoff]
        f2 = make_features(bars2[ticker], market2, intraday).loc[:cutoff]
        pd.testing.assert_frame_equal(f1, f2)


def test_swing_ai_does_not_peek_at_the_future():
    bars, market = make_bars()
    brain = Brain(horizon=5, retrain_every=21, min_train=300)
    cutoff = bars["AAA"].index[650]
    s1 = brain.walk_forward_scores(bars, market).loc[:cutoff]
    s2 = brain.walk_forward_scores(*scramble_after(bars, market, cutoff)).loc[:cutoff]
    assert s1.notna().sum().sum() > 0
    pd.testing.assert_frame_equal(s1, s2)


def test_day_ai_does_not_peek_at_the_future():
    bars, market = make_intraday_bars()
    brain = Brain(horizon=12, retrain_every=78, min_train=780, intraday=True)
    cutoff = bars["EEE"].index[1500]
    s1 = brain.walk_forward_scores(bars, market).loc[:cutoff]
    s2 = brain.walk_forward_scores(*scramble_after(bars, market, cutoff)).loc[:cutoff]
    assert s1.notna().sum().sum() > 0
    pd.testing.assert_frame_equal(s1, s2)


def test_since_gives_the_same_latest_scores_faster():
    bars, market = make_bars()
    brain = Brain(horizon=5, retrain_every=21, min_train=300)
    last = bars["AAA"].index[-1]
    full = brain.walk_forward_scores(bars, market).loc[last]
    quick = brain.walk_forward_scores(bars, market, since=last).loc[last]
    pd.testing.assert_series_equal(full, quick)


def test_every_strategy_backtests(cfg):
    for desk, (bars, market) in [("swing", make_bars()), ("day", make_intraday_bars())]:
        for strategy in all_strategies(cfg, desk):
            result = run_backtest(strategy, bars, market, cfg, desk)
            assert result["trading_days"] > 0, strategy.name
            assert result["max_drawdown_pct"] >= 0


def test_study_progress_needs_a_month(cfg, tmp_path):
    store = Store(tmp_path / "t.sqlite")
    store.set("study_started_on", "2026-09-01")
    store.set("study_days", [f"2026-09-{i + 1:02d}" for i in range(20)])
    assert not study_progress(store, cfg, today=date(2026, 9, 20))["ready"]
    assert study_progress(store, cfg, today=date(2026, 10, 1))["ready"]


def test_promotion_requires_every_rule(cfg):
    good = {"trading_days": 40, "num_closed_trades": 25, "total_return_pct": 4.0,
            "profit_factor": 1.5, "max_drawdown_pct": 5.0}
    assert all(ok for *_, ok in check_promotion(cfg, good, benchmark_return_pct=2.0))
    assert not all(ok for *_, ok in check_promotion(cfg, good, benchmark_return_pct=6.0))   # lost to SPY
    assert not all(ok for *_, ok in check_promotion(cfg, {**good, "max_drawdown_pct": 12}, 2.0))


def test_the_owners_rule_made_money_and_beat_spy_over_30_days_no_trade_count(cfg):
    """Momentum trades rarely: 3 closed trades and a low profit factor still pass if it made money,
    beat SPY and stayed within the drawdown limit. Too short, a loss, or losing to SPY fail."""
    few = {"trading_days": 30, "num_closed_trades": 3, "total_return_pct": 5.0,
           "profit_factor": 0.8, "max_drawdown_pct": 6.0}
    names = [name for name, *_ in check_promotion(cfg, few, benchmark_return_pct=2.0)]
    assert "closed trades" not in names and "profit factor" not in names
    assert all(ok for *_, ok in check_promotion(cfg, few, benchmark_return_pct=2.0))
    assert not all(ok for *_, ok in check_promotion(cfg, {**few, "trading_days": 29}, 2.0))
    assert not all(ok for *_, ok in check_promotion(cfg, {**few, "total_return_pct": -1.0}, -3.0))   # lost money
    assert not all(ok for *_, ok in check_promotion(cfg, few, benchmark_return_pct=6.0))            # lost to SPY
    assert not all(ok for *_, ok in check_promotion(cfg, {**few, "max_drawdown_pct": 11.0}, 2.0))
    cfg["promotion"].update(min_closed_trades=20, min_profit_factor=1.2)                          # switch back on
    assert not all(ok for *_, ok in check_promotion(cfg, few, benchmark_return_pct=2.0))


def test_the_local_ai_gets_the_knowledge_pack_with_every_request(cfg, monkeypatch):
    """The owner's plan, the safety rules, the research and the TJR notes go along as background."""
    import io
    import json as _json
    from aitrader import knowledge, llm
    sent = {}

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        sent.update(_json.loads(request.data))
        return Reply(_json.dumps({"response": "ok"}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    cfg["llm"].update(enabled=True, url="http://localhost:11434", model="qwen3:4b")
    assert llm.ask_local_llm(cfg, "Write the plan.") == "ok"
    assert sent["prompt"] == "Write the plan." and sent["options"]["num_ctx"] >= 8192
    for must_know in ("good faith violation", "Stage 1", "MTUM", "TJR", "never decide trades"):
        assert must_know.lower() in sent["system"].lower(), must_know
    assert set(knowledge.topics()) >= {"00-how-to-use", "10-safety-rules", "20-the-plan", "30-research-findings",
                                       "40-tjr-playbook"}
