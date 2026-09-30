"""TJR's model (tjr.py): sweep -> break of structure -> gap retrace entry, and its history test."""
import numpy as np
import pandas as pd
import pytest

from aitrader import tjr
from aitrader.strategies import all_strategies

# (open, high, low, close) every 5 minutes from 9:30am on the setup day
SETUP = [(100.0, 100.5, 99.8, 100.3), (100.3, 100.8, 100.2, 100.7),
         (100.7, 101.0, 100.5, 100.6),                                   # 9:40: the swing high (101.0)
         (100.6, 100.7, 100.0, 100.1), (100.1, 100.2, 99.5, 99.6),
         (99.6, 99.7, 98.8, 99.2),                                       # 9:55: sweeps yesterday's low (99.0)
         (99.2, 99.9, 99.1, 99.8), (99.8, 100.6, 99.95, 100.5),
         (100.5, 101.3, 100.4, 101.2),                                   # 10:10: closes above 101.0: break
         (101.2, 101.4, 100.9, 101.0),
         (101.0, 101.0, 100.3, 100.6),                                   # 10:20: back in the gap: ENTRY
         (100.6, 101.5, 100.5, 101.4), (101.4, 102.5, 101.3, 102.4), (102.4, 103.6, 102.3, 103.5),
         (103.5, 104.9, 103.4, 104.8),                                   # 10:40: reaches 2R: exit
         (104.8, 105.0, 104.5, 104.9)]


def day_bars(rows, day, start_minute=570):
    idx = [pd.Timestamp(day) + pd.Timedelta(minutes=start_minute + 5 * i) for i in range(len(rows))]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.DatetimeIndex(idx)).assign(volume=1e5)


def history(setup=SETUP, start_minute=570):
    quiet = [(100.0, 100.3, 99.7, 100.0)] * 78
    quiet[40] = (100.0, 100.2, 99.0, 99.9)                               # yesterday's low: 99.0
    before = day_bars(quiet, "2026-09-28")
    last = setup[-1][3]                                                   # then quiet at the last price
    rest = [(last, last + 0.05, last - 0.05, last)] * (78 - len(setup) - (start_minute - 570) // 5)
    pre = [(100.0, 100.3, 99.9, 100.1)] * ((start_minute - 570) // 5)
    return pd.concat([before, day_bars(pre + list(setup) + rest, "2026-09-29")])


@pytest.fixture
def bias_up(monkeypatch):
    monkeypatch.setattr(tjr, "hourly_bias", lambda df: pd.Series(True, index=df.index))


def at(s, hhmm):
    return s[pd.Timestamp(f"2026-09-29 {hhmm}")]


def test_the_textbook_setup_is_found_bar_by_bar(bias_up):
    s = tjr.ticker_scores(history())
    assert at(s, "10:15") == tjr.NOTHING and at(s, "10:20") == tjr.ENTRY          # buys on the retrace
    assert at(s, "10:25") == tjr.IN_TRADE and at(s, "10:35") == tjr.IN_TRADE
    assert at(s, "10:40") == tjr.FLAT and at(s, "15:55") == tjr.FLAT             # target hit; done for the day
    assert (s[s.index.normalize() == pd.Timestamp("2026-09-28")] == tjr.NOTHING).all()
    today = tjr.ticker_scores(history(), since=pd.Timestamp("2026-09-29 10:20"))  # the live path: today only
    assert today.index[0] == pd.Timestamp("2026-09-29 09:30") and at(today, "10:20") == tjr.ENTRY


def test_no_break_of_structure_no_trade(bias_up):
    rows = list(SETUP)
    rows[8] = (100.5, 100.95, 100.4, 100.9)                              # never closes above 101.0
    rows[11:] = [(100.8, 100.95, 100.6, 100.8)] * (len(rows) - 11)
    assert (tjr.ticker_scores(history(rows)) != tjr.ENTRY).all()


def test_a_close_through_the_gap_cancels_it(bias_up):
    rows = list(SETUP)
    rows[10] = (101.0, 101.0, 99.5, 99.7)                                # falls through the gap (99.9-100.4)
    assert (tjr.ticker_scores(history(rows)) != tjr.ENTRY).all()


def test_only_in_the_morning_window_and_with_the_hourly_trend(bias_up, monkeypatch):
    late = tjr.ticker_scores(history(start_minute=570 + 150))             # same setup at 12:00
    assert (late != tjr.ENTRY).all()
    monkeypatch.setattr(tjr, "hourly_bias", lambda df: pd.Series(False, index=df.index))
    assert (tjr.ticker_scores(history()) != tjr.ENTRY).all()              # hourly trend not up: no trade


def test_the_stop_below_the_sweep_ends_the_trade(bias_up):
    rows = list(SETUP)
    rows[11:] = [(100.6, 100.7, 99.0, 99.2), (99.2, 99.3, 98.0, 98.2)] + [(98.2, 98.3, 98.0, 98.1)] * 3
    s = tjr.ticker_scores(history(rows))
    assert at(s, "10:20") == tjr.ENTRY and at(s, "10:25") == tjr.IN_TRADE and at(s, "10:30") == tjr.FLAT


def test_hourly_trend_needs_a_higher_low_and_a_close_above_it():
    idx = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 5 * i)
                            for d in pd.bdate_range("2026-09-01", periods=12) for i in range(78)])
    t = np.arange(len(idx))
    rising = 100 + t * 0.01 + 1.5 * np.sin(t / 9)                        # waves that climb: higher lows
    falling = 100 - t * 0.01 + 1.5 * np.sin(t / 9)
    frame = lambda p: pd.DataFrame({"open": p, "high": p + 0.1, "low": p - 0.1, "close": p}, index=idx)
    assert tjr.hourly_bias(frame(rising)).iloc[-200:].mean() > 0.5
    assert tjr.hourly_bias(frame(falling)).iloc[-200:].sum() == 0


def test_it_is_one_of_the_day_desks_methods_and_is_what_it_trades_in_its_head(cfg):
    assert "tjr_model" in [s.name for s in all_strategies(cfg, "day")]
    assert cfg["study"]["in_its_head_strategy"]["day"] == "tjr_model"


def test_the_history_test_compares_with_random_entries(cfg):
    from conftest import make_intraday_bars
    bars, market = make_intraday_bars(n_days=12)
    result = tjr.history_test(cfg, bars, market)
    assert set(result) >= {"passed", "why_not", "tjr", "placebo", "days", "tickers"}
    assert result["passed"] is False and result["why_not"]                 # a random walk shouldn't pass
    assert result["tickers"] == sorted(bars)


def test_the_day_desk_practices_tjr_in_its_head_and_explains_it(cfg, tmp_path, monkeypatch):
    import run
    from aitrader import report
    from aitrader.storage import Store
    from test_lifecycle import FakeData
    monkeypatch.setattr(run, "MarketData", FakeData)
    store = Store(tmp_path / "aitrader.sqlite")
    day = FakeData.intraday[1].index.normalize().unique()[0]
    for bar_time in FakeData.intraday[1].index[FakeData.intraday[1].index.normalize() == day][:30]:
        FakeData.now = bar_time.to_pydatetime()
        run.trade_desk(cfg, store, FakeData(), "day", FakeData.now)
    assert store.get("study-day_thinking")["strategy"] == "tjr_model"
    text = report.after_market(cfg, store, day.strftime("%Y-%m-%d"))
    assert "**Strategy: `tjr_model`.** TJR's model:" in text


def test_stage2_starts_only_after_the_history_test_passes(cfg, tmp_path):
    import run
    from aitrader import app_api
    from aitrader.config import data_path
    from aitrader.phases import Phase, current_phase
    from aitrader.storage import Store
    store = Store(data_path(cfg, "aitrader.sqlite"))
    with pytest.raises(ValueError, match="hasn't run yet"):
        run.start_stage2(cfg, store)
    failed = {"passed": False, "why_not": ["only 12 trades (needs 30)"], "tjr": {}, "placebo": {}, "days": 20,
              "tickers": ["AAA"], "ran_on": "2026-09-29"}
    store.set("tjr_history_test", failed)
    with pytest.raises(ValueError, match="only 12 trades"):
        run.start_stage2(cfg, store)
    assert app_api.stage2_status(store)["can_start"] is False
    passed = {**failed, "passed": True, "why_not": [],
              "tjr": {"num_closed_trades": 41, "win_rate_pct": 44.0, "profit_factor": 1.4, "total_return_pct": 3.1,
                      "max_drawdown_pct": 2.0},
              "placebo": {"num_closed_trades": 60, "profit_factor": 0.9, "total_return_pct": -1.2}}
    store.set("tjr_history_test", passed)
    assert app_api.stage2_status(store)["can_start"] is True
    assert "Stage 2 started" in run.start_stage2(cfg, store)
    assert current_phase(store, "day") == Phase.PAPER and current_phase(store, "swing") == Phase.STUDY
    plan = run.load_plan(cfg, "day")
    assert plan["strategy"] == "tjr_model" and plan["stage"] == 2 and "41 trades" in plan["evidence"]
    status = app_api.stage2_status(store)
    assert status["running_since"] and status["can_start"] is False
    with pytest.raises(ValueError, match="already paper trading"):
        run.start_stage2(cfg, store)


def test_the_weekly_test_runs_after_the_study_and_not_twice_a_week(cfg, tmp_path, monkeypatch):
    from datetime import datetime
    import run
    from aitrader.storage import Store
    from test_lifecycle import FakeData
    store = Store(tmp_path / "aitrader.sqlite")
    assert "tjr" in run.due_jobs(datetime(2026, 9, 30, 16, 15), {"study:2026-09-30"})
    assert "tjr" not in run.due_jobs(datetime(2026, 9, 30, 16, 15), set())             # after the study
    calls = []
    monkeypatch.setattr(tjr, "history_test", lambda cfg, bars, market: calls.append(1) or
                        {"passed": False, "why_not": ["x"], "tjr": {}, "placebo": {}, "days": 5, "tickers": []})
    assert run.run_tjr_test(cfg, store, FakeData(), "2026-09-30") == "TJR test: not passed"
    assert run.run_tjr_test(cfg, store, FakeData(), "2026-10-02") == "TJR test: done this week"
    assert run.run_tjr_test(cfg, store, FakeData(), "2026-10-07") == "TJR test: not passed" and len(calls) == 2
    assert any("TJR history test" in m for _, m in store.journal(5))
