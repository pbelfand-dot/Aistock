"""Walks the whole journey on fake data: study -> plan -> approve -> paper trade -> promote check."""
import argparse

import pytest

import run
from aitrader.phases import Phase, current_phase
from aitrader.storage import Store
from aitrader.study import study_step

from conftest import make_bars


class FakeData:
    """Stands in for MarketData. `day` controls how much history is 'known' so far."""
    bars, market = make_bars()
    day = 850

    def __init__(self, cfg):
        pass

    def load(self):
        cut = lambda df: df.iloc[: FakeData.day]
        return {t: cut(df) for t, df in FakeData.bars.items()}, cut(FakeData.market)


def test_full_journey(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(run, "MarketData", FakeData)
    monkeypatch.setattr(run, "market_is_open", lambda d: True)
    store = Store(tmp_path / "aitrader.sqlite")

    # 1) STUDY: 25 trading days of opinions, graded as time passes
    for day in range(850, 875):
        FakeData.day = day
        study_step(cfg, store, *FakeData(cfg).load())
    assert current_phase(store) == Phase.STUDY
    assert store.predictions()["actual_return"].notna().sum() > 0

    # 2) PLAN: loosen the bars so this fake market produces a tradable plan
    cfg["plan"].update(min_sharpe=-99, min_profit_factor=0, max_drawdown_pct=100, min_trades=0,
                       min_forward_signals=0)
    run.cmd_plan(cfg, store, argparse.Namespace(force=True))
    plan = run.load_plan(cfg)
    if plan["verdict"] != "TRADE":
        pytest.skip("no strategy had a positive edge on this random data")
    assert current_phase(store) == Phase.PLAN_REVIEW

    # 3) APPROVE -> PAPER
    monkeypatch.setattr("builtins.input", lambda prompt: "YES")
    run.cmd_approve_plan(cfg, store, None)
    assert current_phase(store) == Phase.PAPER

    # 4) PAPER trade for 10 days (and never twice on the same day)
    for day in range(875, 885):
        FakeData.day = day
        run.cmd_trade(cfg, store, argparse.Namespace(dry_run=False, anyway=False))
        run.cmd_trade(cfg, store, argparse.Namespace(dry_run=False, anyway=False))
    assert len(store.equity_curve("paper")) == 10

    # 5) PROMOTE: 10 days isn't enough, so it must refuse
    monkeypatch.setattr("builtins.input", lambda prompt: "REAL MONEY")
    run.cmd_promote(cfg, store, None)
    assert current_phase(store) == Phase.PAPER

    # 6) KILL: sells everything and halts
    run.cmd_kill(cfg, store, None)
    assert store.get("halted") is True
    assert store.get("paper_ledger")["positions"] == {}
    run.cmd_status(cfg, store, None)
