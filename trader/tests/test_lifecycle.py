"""Walks the whole journey on fake data, for BOTH desks:
study -> plan -> approve -> paper trade -> promote check -> kill."""
import argparse
import json
from datetime import datetime

import pandas as pd

import run
from aitrader.config import data_path
from aitrader.phases import Phase, current_phase, set_phase
from aitrader.storage import Store

from conftest import make_bars, make_intraday_bars


class FakeData:
    """Stands in for MarketData. `now` controls how much history is 'known' so far."""
    daily = make_bars(n_days=700)
    intraday = make_intraday_bars(n_days=30)
    now = None

    def __init__(self, cfg=None):
        pass

    def load(self, desk, extra=()):
        bars, market = FakeData.intraday if desk == "day" else FakeData.daily
        cut = lambda df: df[df.index <= FakeData.now]
        return {t: cut(df) for t, df in bars.items()}, cut(market)

    def history(self, ticker, interval):
        return self.load("swing")[1]


def force_plan(cfg, store, desk, strategy):
    """Write a plan by hand (random fake data may not produce a tradable one)."""
    plan = {"desk": desk, "strategy": strategy, "verdict": "TRADE", "created_on": "2026-09-01"}
    data_path(cfg, f"trading_plan_{desk}.json").write_text(json.dumps(plan))
    set_phase(store, desk, Phase.PLAN_REVIEW, "test")


def test_full_journey(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(run, "MarketData", FakeData)
    store = Store(tmp_path / "aitrader.sqlite")
    data = FakeData()
    days = FakeData.intraday[1].index.normalize().unique()

    # 1) STUDY: 22 trading days, each studied after the close
    for day in days[:22]:
        FakeData.now = day + pd.Timedelta(hours=16, minutes=10)
        run.run_study(cfg, store, data)
    assert current_phase(store, "swing") == Phase.STUDY
    assert store.predictions()["actual_return"].notna().sum() > 0
    assert store.get("day_shadow_report")["results"]
    assert len(store.get("study_days")) >= 20

    # 2) PLAN (forced: the calendar month hasn't really passed in a test)
    cfg["plan"].update(min_sharpe=-99, min_profit_factor=0, max_drawdown_pct=100, min_trades=0)
    run.cmd_plan(cfg, store, argparse.Namespace(force=True, desk=None))
    assert (tmp_path / "trading_plan_swing.md").exists() and (tmp_path / "trading_plan_day.md").exists()
    if current_phase(store, "swing") != Phase.PLAN_REVIEW:
        force_plan(cfg, store, "swing", "trend_following")
    if current_phase(store, "day") != Phase.PLAN_REVIEW:
        force_plan(cfg, store, "day", "opening_range_breakout")

    # 3) APPROVE -> PAPER (both desks)
    monkeypatch.setattr("builtins.input", lambda prompt: "YES")
    run.cmd_approve_plan(cfg, store, argparse.Namespace(desk=None))
    assert current_phase(store, "swing") == current_phase(store, "day") == Phase.PAPER

    # 4) PAPER: 5 trading days. Day desk every 5 minutes; swing at 3:45pm.
    for day in days[22:27]:
        for bar_time in FakeData.intraday[1].index[FakeData.intraday[1].index.normalize() == day]:
            now = bar_time.to_pydatetime()
            FakeData.now = now
            run.trade_desk(cfg, store, data, "day", now)
            if (now.hour, now.minute) == (15, 45):
                run.trade_desk(cfg, store, data, "swing", now)
        assert store.get("paper-day_ledger")["positions"] == {}, "day desk held a position overnight"
    assert len(store.equity_curve("paper-day")) == 5
    assert len(store.equity_curve("paper-swing")) == 5
    assert len(store.fills("paper-day")) > 0                         # every fill saved as it happened

    # 5) PROMOTE: 5 days isn't enough, so it must refuse
    monkeypatch.setattr("builtins.input", lambda prompt: "REAL MONEY")
    run.cmd_promote(cfg, store, argparse.Namespace(desk=None))
    assert current_phase(store, "swing") == current_phase(store, "day") == Phase.PAPER

    # 6) KILL: sells everything and halts every desk
    run.cmd_kill(cfg, store, None)
    assert store.get("halted:swing") and store.get("halted:day")
    assert store.get("paper-swing_ledger")["positions"] == {}
    assert "HALTED" in run.trade_desk(cfg, store, data, "day", FakeData.now)
    run.cmd_status(cfg, store, None)
