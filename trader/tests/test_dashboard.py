"""The app's dashboard: its numbers, the bridge the app uses to ask the bot, and what Pause means."""
import json
from datetime import datetime

import pandas as pd
import pytest

from aitrader import dashboard
from aitrader.brokers.base import Fill
from aitrader.phases import Phase, set_phase
from aitrader.storage import Store


@pytest.fixture
def filled(cfg, monkeypatch):
    """A paper swing desk that has traded for a few days, plus saved prices. It's 4:30pm on the 25th."""
    monkeypatch.setattr(dashboard, "now_ny", lambda: datetime(2026, 9, 25, 16, 30))
    cfg["data"]["source"] = "yahoo"
    cfg["paper"]["starting_cash"] = 1000                # $500 per desk, like the real setup
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    set_phase(store, "swing", Phase.PAPER, "test")
    for date, value in (("2026-09-23", 500.0), ("2026-09-24", 505.0), ("2026-09-25", 498.0)):
        store.record_equity("paper-swing", date, value, 400.0)
    store.record_fill("paper-swing", Fill("2026-09-23", "AAA", "BUY", 2, 50.0, "test buy", order_id="1"))
    store.record_fill("paper-swing", Fill("2026-09-24", "BBB", "SELL", 1, 20.0, "test sell", 3.0, "2"))
    store.set("paper-swing_ledger", {"cash": 400.0, "unsettled": {}, "pending": [], "positions": {
        "AAA": {"ticker": "AAA", "qty": 2, "avg_cost": 50.0, "opened_on": "2026-09-23", "stop_order_id": ""}}})
    for ticker, closes in (("AAA", [48.0, 49.0, 49.0]), ("MKT", [100.0, 101.0, 102.0])):
        path = dashboard.data_path(cfg, f"cache/yahoo/1d/{ticker}.csv")
        pd.DataFrame({"close": closes}, index=pd.to_datetime(["2026-09-23", "2026-09-24", "2026-09-25"])).to_csv(path)
    return cfg, store


def test_snapshot_reads_like_a_brokerage_account(filled):
    cfg, store = filled
    snap = json.loads(json.dumps(dashboard.snapshot(cfg, store)))         # must be plain JSON
    paper = snap["accounts"]["paper"]
    assert paper["active"] and not snap["accounts"]["live"]["active"]
    assert paper["dates"] == ["2026-09-23", "2026-09-24", "2026-09-25"]
    assert paper["series"]["total"] == [1000.0, 1005.0, 998.0]           # day desk not started = its $500 cash
    assert paper["series"]["benchmark"] == [1000.0, 1010.0, 1020.0]      # SPY-style line, same starting amount
    assert paper["value"] == 998.0 and paper["day_change"] == -7.0 and paper["total_return_pct"] == -0.2
    (pos,) = paper["positions"]
    assert pos["ticker"] == "AAA" and pos["last"] == 49.0 and pos["gain"] == -2.0 and pos["stop"] == 46.5
    assert [a["side"] for a in paper["activity"]] == ["SELL", "BUY"]      # newest first
    assert paper["win_rate_pct"] == 100.0 and paper["closed_trades"] == 1
    assert {d["desk"]: d["step"] for d in snap["desks"]} == {"swing": 3, "day": 1}
    assert next(w for w in snap["watchlist"] if w["ticker"] == "AAA")["change_pct"] == 0.0


def ask(monkeypatch, capsys, cfg, *args):
    """What the app does: run `python -m aitrader.app_api ...` and read the JSON it prints."""
    from aitrader import app_api
    monkeypatch.setattr(app_api, "load_config", lambda: cfg)
    capsys.readouterr()
    assert app_api.main(list(args)) == 0
    return json.loads(capsys.readouterr().out)          # only JSON: the bot's own messages go elsewhere


def test_the_app_asks_the_bot_directly_and_gets_json(filled, monkeypatch, capsys):
    cfg, store = filled
    assert ask(monkeypatch, capsys, cfg, "snapshot")["accounts"]["paper"]["value"] == 998.0

    answer = ask(monkeypatch, capsys, cfg, "kill")                        # no typed phrase: nothing happens
    assert "SELL EVERYTHING" in answer["error"] and not store.get("halted:swing")
    assert "error" in ask(monkeypatch, capsys, cfg, "kill", "--confirm", "sell everything")

    answer = ask(monkeypatch, capsys, cfg, "pause")                       # Pause: every desk, nothing sold
    assert "no new trades" in answer["message"]
    assert store.get("halted:swing") and store.get("halted:day") and not store.get("exiting:swing")
    assert "PAUSED by you, from the app" in store.journal(1)[0][1]
    assert store.get("paper-swing_ledger")["positions"]                   # still owns its stock


# ---------------------------------------------------------------- what "paused" means
@pytest.fixture
def paused_desk(cfg, monkeypatch):
    """A paused day desk that owns a stock at the broker, with the trading steps recorded."""
    import run
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    set_phase(store, "day", Phase.PAPER, "test")
    store.set("paper-day_ledger", {"cash": 400.0, "unsettled": {}, "pending": [], "positions": {
        "EEE": {"ticker": "EEE", "qty": 2, "avg_cost": 50.0, "opened_on": "2026-09-28", "stop_order_id": ""}}})
    store.set("halted:day", True)
    calls = []
    monkeypatch.setattr(run, "broker_backed", lambda cfg, phase: True)
    monkeypatch.setattr(run, "continue_exit", lambda *a: calls.append("sell everything") or "getting out")
    monkeypatch.setattr(run, "_trade_desk", lambda cfg, store, data, desk, phase, now, stops_only, *a:
                        calls.append(f"cycle stops_only={stops_only}") or "value $500")
    return run, cfg, store, calls


def test_paused_desk_never_trades_but_keeps_guarding_what_it_owns(paused_desk):
    run, cfg, store, calls = paused_desk
    message = run.trade_desk(cfg, store, None, "day", datetime(2026, 9, 28, 11, 0))
    assert calls == ["cycle stops_only=True"]         # stop-losses + the day desk's sell-before-close only
    assert "HALTED" in message


def test_emergency_exit_keeps_selling_until_flat(paused_desk):
    run, cfg, store, calls = paused_desk
    store.set("exiting:day", True)
    run.trade_desk(cfg, store, None, "day", datetime(2026, 9, 28, 11, 0))
    assert calls == ["sell everything"]


def test_resume_waits_until_an_emergency_exit_is_finished(paused_desk):
    import argparse
    run, cfg, store, _ = paused_desk
    store.set("exiting:day", True)
    run.cmd_resume(cfg, store, argparse.Namespace(desk="day"))
    assert store.get("halted:day")                     # still selling: stays halted
    store.set("paper-day_ledger", {"cash": 500.0, "unsettled": {}, "pending": [], "positions": {}})
    run.cmd_resume(cfg, store, argparse.Namespace(desk="day"))
    assert not store.get("halted:day") and not store.get("exiting:day")


def test_demo_runs_the_real_code_and_never_touches_your_data(cfg, tmp_path, monkeypatch, capsys):
    from aitrader import demo
    monkeypatch.setattr(demo, "DAYS", 300)
    monkeypatch.setattr(demo, "INTRADAY_DAYS", 6)
    monkeypatch.setattr(demo, "PAPER_DAYS", 5)
    monkeypatch.setattr(demo, "DAY_DESK_PAPER_DAYS", 2)
    cfg["desks"]["swing"]["watchlist"] = cfg["desks"]["swing"]["watchlist"][:3]
    cfg["desks"]["day"]["watchlist"] = cfg["desks"]["day"]["watchlist"][:3]
    assert "isn't built" in ask(monkeypatch, capsys, cfg, "snapshot", "--demo")["error"]

    assert ask(monkeypatch, capsys, cfg, "demo-build")["message"] == "Demo data is ready."
    assert not (tmp_path / "aitrader.sqlite").exists()                    # your real data: untouched
    snap = ask(monkeypatch, capsys, cfg, "snapshot", "--demo")
    assert snap["demo"] and snap["prices"] == "demo"
    assert [d["phase"] for d in snap["desks"]] == ["PAPER", "PAPER"]
    assert len(snap["accounts"]["paper"]["dates"]) == 5 and snap["accounts"]["paper"]["series"]["benchmark"]

    ask(monkeypatch, capsys, cfg, "kill", "--confirm", "SELL EVERYTHING", "--demo")   # works offline
    store = Store(tmp_path / "demo" / "aitrader.sqlite")
    assert store.get("paper-swing_ledger")["positions"] == {} == store.get("paper-day_ledger")["positions"]
    assert store.get("halted:swing") and not store.get("exiting:swing")
    paper = ask(monkeypatch, capsys, cfg, "snapshot", "--demo")["accounts"]["paper"]
    assert paper["value"] == paper["cash"]            # sold out: the headline value is just the cash
    assert not (tmp_path / "aitrader.sqlite").exists()
