"""Stage 1: the momentum method, and the Setup button that starts paper trading it (pretend money only)."""
import json

import numpy as np
import pandas as pd
import pytest

from aitrader import scanner
from aitrader.config import data_path
from aitrader.engine import decide_orders
from aitrader.phases import Phase, current_phase, set_phase
from aitrader.risk import RiskManager
from aitrader.storage import Store
from aitrader.strategies import Momentum, current_scores, get_strategy


def trend(start, end, days=400, seed=0):
    rng = np.random.default_rng(seed)
    close = np.geomspace(start, end, days) * (1 + rng.normal(0, 0.002, days))
    idx = pd.bdate_range(end="2026-09-29", periods=days)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1e6}, index=idx)


def stocks():
    return {"FAST": trend(20, 60), "MID": trend(40, 52, seed=1), "SLOW": trend(30, 33, seed=2),
            "DOWN": trend(80, 40, seed=3), "FLAT": trend(50, 51, seed=4)}


def test_momentum_likes_the_strongest_stock_and_drops_falling_ones():
    now = current_scores(Momentum(), stocks(), trend(100, 130, seed=9))
    assert now.idxmax() == "FAST" and now["FAST"] == 1.0 >= Momentum.buy_above
    assert now["DOWN"] == 0.0                               # below its 200-day average: get out
    assert now["MID"] > now["SLOW"]


def test_no_new_buys_while_the_market_is_below_its_200_day_average_but_winners_are_kept():
    falling_market = trend(130, 90, seed=9)
    now = current_scores(Momentum(), stocks(), falling_market)
    assert now.max() < Momentum.buy_above                   # nothing new is bought
    assert now["FAST"] >= Momentum.sell_below               # what it owns isn't dumped just for that


def test_momentum_needs_a_year_of_history_before_it_has_an_opinion():
    young = {"NEW": trend(10, 20, days=150), **stocks()}
    assert np.isnan(current_scores(Momentum(), young, trend(100, 130, seed=9))["NEW"])


def test_momentum_buys_the_top_of_the_list(cfg):
    bars, market = stocks(), trend(100, 130, seed=9)
    scores = current_scores(Momentum(), bars, market)
    prices = pd.Series({t: df["close"].iloc[-1] for t, df in bars.items()})
    orders = decide_orders(scores, prices, {}, 500.0, 500.0, Momentum(), RiskManager.for_desk(cfg, "swing"))
    assert [o.ticker for o in orders] == ["FAST", "MID"] and {o.side for o in orders} == {"BUY"}   # strongest first


def ask(monkeypatch, capsys, cfg, *args):
    from aitrader import app_api
    monkeypatch.setattr(app_api, "load_config", lambda: cfg)
    capsys.readouterr()
    assert app_api.main(list(args)) == 0
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def studying(cfg, monkeypatch):
    from aitrader import mac_service
    monkeypatch.setattr(mac_service, "is_running", lambda: False)
    monkeypatch.setattr(scanner, "trade_candidates", lambda cfg: ["FAST", "MID"])
    store = Store(data_path(cfg, "aitrader.sqlite"))
    store.set("paper-swing_ledger", {"cash": 1.0, "unsettled": {}, "pending": [], "positions": {}})   # old leftovers
    return cfg, store


def test_the_setup_button_starts_stage1_paper_trading_only_when_you_press_it(studying, monkeypatch, capsys):
    cfg, store = studying
    status = ask(monkeypatch, capsys, cfg, "setup-status")
    assert status["stage1"]["can_start"] is True and status["stage1"]["running_since"] is None
    assert current_phase(store, "swing") == Phase.STUDY                 # nothing switches on by itself

    reply = ask(monkeypatch, capsys, cfg, "start-stage1")
    assert "Stage 1 started" in reply["message"] and "Nothing uses real money" in reply["message"]
    store = Store(data_path(cfg, "aitrader.sqlite"))
    assert current_phase(store, "swing") == Phase.PAPER
    assert current_phase(store, "day") == Phase.STUDY                   # the day desk keeps studying
    assert store.get("paper-swing_ledger") is None                     # a fresh start
    plan = json.loads(data_path(cfg, "trading_plan_swing.json").read_text())
    assert plan["strategy"] == "momentum" and plan["stage"] == 1 and plan["verdict"] == "TRADE"
    assert {"FAST", "MID"} <= set(plan["watchlist"])
    assert get_strategy(plan["strategy"], cfg, "swing").name == "momentum"   # the trading loop can load it
    assert "MTUM" in data_path(cfg, "trading_plan_swing.md").read_text()

    status = ask(monkeypatch, capsys, cfg, "setup-status")
    assert status["stage1"]["can_start"] is False and status["stage1"]["running_since"]
    swing = next(d for d in status["desks"] if d["desk"] == "swing")
    assert swing["next"].startswith("Stage 1") and "0 of 30 trading days done" in swing["next"]
    again = ask(monkeypatch, capsys, cfg, "start-stage1")
    assert "already running" in again["error"]


def test_stage1_never_touches_a_desk_trading_real_money(studying, monkeypatch, capsys):
    cfg, store = studying
    set_phase(store, "swing", Phase.LIVE, "test")
    assert "real money" in ask(monkeypatch, capsys, cfg, "start-stage1")["error"]
    assert current_phase(Store(data_path(cfg, "aitrader.sqlite")), "swing") == Phase.LIVE
