"""Challengers: new ideas (momentum_plus, momentum_calm, ...) shadow trade next to the desk's method and only
take over once the tests for luck say they're really better (challengers.py)."""
import numpy as np
import pandas as pd
import pytest

import run
from aitrader import app_api, challengers, dashboard, phone
from aitrader.engine import scaled_risk
from aitrader.phases import Phase, set_phase
from aitrader.risk import RiskManager
from aitrader.storage import Store
from aitrader.strategies import Momentum, MomentumCalm, MomentumPlus, current_scores, get_strategy
from conftest import make_bars
from test_lifecycle import FakeData, force_plan


def frame(close, idx):
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1e6}, index=idx)


def test_momentum_plus_prefers_a_smooth_climb_to_a_few_big_jumps():
    days = 400
    idx = pd.bdate_range(end="2026-09-29", periods=days)
    rng = np.random.default_rng(5)
    smooth = np.geomspace(50, 100, days) * (1 + rng.normal(0, 0.002, days))
    jumpy = 50 * np.cumprod(1 + rng.normal(0, 0.012, days))
    for k in (60, 140, 220, 300):                           # four big jumps make up the same climb
        jumpy[k:] *= 1.25
    jumpy *= smooth[-30] / jumpy[-30]                       # the same 12-1 month return as SMOOTH
    bars = {"SMOOTH": frame(smooth, idx), "JUMPY": frame(jumpy, idx),
            **{f"F{i}": frame(np.geomspace(40, 40 * (1.1 + i / 10), days) * (1 + rng.normal(0, 0.01, days)), idx)
               for i in range(4)}}
    market = frame(np.geomspace(100, 125, days), idx)
    plus = current_scores(MomentumPlus(), bars, market)
    assert plus["SMOOTH"] > plus["JUMPY"]
    assert plus["SMOOTH"] >= MomentumPlus.buy_above


def test_the_new_methods_never_peek_at_the_future():
    bars, market = make_bars(700, tickers=tuple(f"T{i}" for i in range(12)), seed=4)
    end = market.index[500]
    cut = {t: df[df.index <= end] for t, df in bars.items()}
    for strategy in (MomentumPlus(), MomentumCalm()):
        full, early = strategy.scores(bars, market), strategy.scores(cut, market[market.index <= end])
        assert ((full.loc[early.index] - early).abs().max().max() or 0) == 0
    full = MomentumCalm().exposure(bars, market, Momentum().scores(bars, market))
    early = MomentumCalm().exposure(cut, market[market.index <= end], Momentum().scores(cut, market[market.index <= end]))
    assert (full.loc[early.index] - early).abs().max() == 0


def test_calm_momentum_buys_smaller_when_its_stocks_get_stormy(cfg):
    days = 700
    idx = pd.bdate_range(end="2026-09-29", periods=days)
    rng = np.random.default_rng(2)
    noise = np.where(np.arange(days) > days - 120, 0.04, 0.008)        # the last 6 months: 5x jumpier
    bars = {f"S{i}": frame(np.geomspace(20, 60 + i, days) * np.cumprod(1 + rng.normal(0, 1, days) * noise), idx)
            for i in range(6)}
    market = frame(np.geomspace(100, 140, days), idx)
    sizes = MomentumCalm().exposure(bars, market, Momentum().scores(bars, market))
    assert sizes.iloc[400] == 1.0                                       # calm: full size
    assert 0.3 <= sizes.iloc[-1] < 0.6                                   # stormy: much smaller, never below 30%
    assert Momentum().exposure(bars, market, Momentum().scores(bars, market)) is None   # plain momentum: always full
    risk = RiskManager.for_desk(cfg, "swing")
    smaller = scaled_risk(risk, 0.5)
    assert smaller.max_position_pct == risk.max_position_pct / 2 and smaller.stop_loss_pct == risk.stop_loss_pct
    assert scaled_risk(risk, 1.0) is risk


def test_the_tests_for_luck():
    rng = np.random.default_rng(0)
    edge, luck = rng.normal(0.001, 0.01, 1500), rng.normal(0, 0.01, 1500)
    luck -= luck.mean()                                                 # truly nothing there
    assert challengers.bootstrap_p(edge) < 0.01
    assert challengers.bootstrap_p(luck) > 0.3
    assert challengers.expected_max_sharpe(1, 0.01) == 0
    assert challengers.expected_max_sharpe(100, 0.01) > challengers.expected_max_sharpe(10, 0.01) > 0
    one, many = challengers.deflated_sharpe(edge, 1), challengers.deflated_sharpe(edge, 200, 0.004)
    assert one > 0.95 and many < one                                    # every extra idea tried raises the bar
    assert challengers.deflated_sharpe(luck, 1) < 0.6


def history(**kw):
    h = {"days": 1500, "years": 6.0, "extra_per_year_pct": 3.0, "p_value": 0.01, "trials": 3, "deflated_sharpe": 0.98,
         "max_drawdown_pct": 20.0, "current_max_drawdown_pct": 22.0, "extra_drawdown_pct": -2.0}
    return {**h, **kw}


def test_only_a_proven_challenger_takes_over(cfg):
    s = challengers.settings(cfg)
    ahead = {"days": 25, "ahead_pct": 0.8}
    assert challengers.judge(s, "swing", history(), ahead)[0] == "proven"
    assert challengers.judge(s, "swing", history(), {"days": 5, "ahead_pct": 2.0})[0] == "promising"     # too soon
    assert challengers.judge(s, "swing", history(), {"days": 25, "ahead_pct": -0.3})[0] == "promising"   # behind
    verdict, why = challengers.judge(s, "swing", history(p_value=0.2), ahead)
    assert verdict == "not better" and "could be luck" in why
    assert challengers.judge(s, "swing", history(deflated_sharpe=0.7), ahead)[0] == "not better"
    verdict, why = challengers.judge(s, "swing", history(extra_drawdown_pct=9.0), ahead)
    assert verdict == "not better" and "worst drop" in why
    assert challengers.judge(s, "swing", history(extra_per_year_pct=-1.0), ahead)[0] == "not better"
    assert challengers.judge(s, "swing", history(days=100), ahead)[0] == "too early"


@pytest.fixture
def studying(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(run, "MarketData", FakeData)
    store = Store(tmp_path / "aitrader.sqlite")
    days = FakeData.daily[1].index[-6:]
    for day in days:
        FakeData.now = day + pd.Timedelta(hours=15, minutes=45)
        run.trade_desk(cfg, store, FakeData(), "swing", FakeData.now.to_pydatetime(), anyway=True)
    return cfg, store, FakeData(), days[-1].strftime("%Y-%m-%d")


def test_challengers_shadow_trade_next_to_the_desk_without_touching_it(studying):
    cfg, store, data, today = studying
    for name in ("momentum", "momentum_plus", "momentum_calm", "momentum_plus_calm", "momentum_quality"):
        assert len(store.equity_curve(f"shadow-swing-{name}")) == 6
        assert store.get(f"shadow-swing-{name}_since")
    assert len(store.equity_curve("study-swing")) == 6                   # the desk's own record is its own
    journal = " ".join(m for _, m in store.journal(500))
    assert "shadow-swing" not in journal                                 # the journal stays about real trading

    compared = run.check_challengers(cfg, store, data, today)
    assert compared and compared[0].startswith("swing: momentum_plus ")
    report = store.get("challengers:swing")
    assert report["current"] == "momentum" and [r["name"] for r in report["rows"]] == \
        ["momentum_plus", "momentum_calm", "momentum_plus_calm", "momentum_quality"]
    row = report["rows"][0]
    assert row["history"]["days"] > 250 and row["forward"]["days"] == 5 and row["verdict"] in ("not better", "promising")
    assert [t["name"] for t in store.trials("swing")] == ["momentum_calm", "momentum_plus", "momentum_plus_calm",
                                                          "momentum_quality"]
    assert all(t["deflated_sharpe"] is not None for t in store.trials("swing"))
    assert run.desk_strategy_name(cfg, store, "swing") == "momentum"      # nothing proven: nothing changes

    thinking = dashboard.thinking(cfg, store)
    assert thinking["challengers"]["swing"]["rows"][0]["name"] == "momentum_plus"
    text = "\n".join(challengers.lines(store, ["swing", "day"]))
    assert "## Challengers" in text and "`momentum_plus`" in text and "a year vs the current method" in text


def test_a_proven_challenger_takes_over_a_pretend_money_desk_and_tells_you(studying, monkeypatch):
    cfg, store, data, today = studying
    monkeypatch.setattr(challengers, "judge", lambda s, desk, h, f: ("proven", "test proof"))
    run.check_challengers(cfg, store, data, today)
    report = store.get("challengers:swing")
    best = max(report["rows"], key=lambda r: r["history"]["deflated_sharpe"])["name"]
    assert report["switched_to"] == best and run.desk_strategy_name(cfg, store, "swing") == best
    assert any(f"CHALLENGER WON (swing desk): {best} replaces momentum" in m for _, m in store.journal(20))
    assert any(mark in "CHALLENGER WON (swing desk)" for mark in phone.ALERT_MARKS)       # it reaches your phone

    FakeData.now = pd.Timestamp(today) + pd.Timedelta(hours=15, minutes=45)
    run.trade_desk(cfg, store, data, "swing", FakeData.now.to_pydatetime(), anyway=True)
    assert store.get("study-swing_thinking")["strategy"] == best
    assert "momentum" in challengers.ring(cfg, "swing", best)            # the old method can still win it back


def test_a_real_money_desk_switches_only_when_you_press_use_it(cfg, tmp_path, monkeypatch):
    store = Store(tmp_path / "aitrader.sqlite")
    force_plan(cfg, store, "swing", "momentum")
    set_phase(store, "swing", Phase.LIVE, "test")
    monkeypatch.setattr(challengers, "judge", lambda s, desk, h, f: ("proven", "test proof"))
    bars, market = FakeData.daily
    report = challengers.evaluate(cfg, store, "swing", bars, market, "momentum", "momentum", real_money=True,
                                  today="2026-09-25")
    assert report["waiting_for_you"] and run.desk_strategy_name(cfg, store, "swing") == "momentum"
    assert any("CHALLENGER PROVEN (swing desk, real money)" in m for _, m in store.journal(5))

    with pytest.raises(ValueError):
        challengers.use(store, "swing", "trend_following")               # never something unproven
    store.db.close()
    reply = app_api.handle("use-challenger", cfg, False, None, {"desk": "swing", "name": report["waiting_for_you"]})
    assert reply["message"] == f"The swing desk now trades {report['waiting_for_you']}."
    store = Store(tmp_path / "aitrader.sqlite")
    assert run.desk_strategy_name(cfg, store, "swing") == report["waiting_for_you"]
    assert store.get("strategy_switch:swing")["by"] == "you"


def test_the_day_desk_has_no_challengers_until_some_are_listed(cfg):
    assert challengers.ring(cfg, "day", "tjr_model") == []
    cfg["challengers"] = {"swing": ["momentum", "nonsense"]}
    assert challengers.ring(cfg, "swing", "momentum") == []             # unknown names are skipped
    cfg["challengers"] = {"enabled": "off"}
    assert challengers.ring(cfg, "swing", "momentum") == []
    assert get_strategy("momentum_plus", cfg, "swing").name == "momentum_plus"
