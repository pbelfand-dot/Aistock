"""The live Thinking tab: every check is written down (scores, the team's notes, what it did or why not,
how far each holding is from its stop), and the tab says what the autopilot is doing this moment."""
from pathlib import Path

import run
from aitrader import dashboard
from aitrader.storage import Store

REPO = Path(__file__).resolve().parents[2]


def day_of_checks(cfg, tmp_path, monkeypatch):
    from test_in_its_head import FakeData
    monkeypatch.setattr(run, "MarketData", FakeData)
    store, data = Store(tmp_path / "aitrader.sqlite"), FakeData()
    days = FakeData.intraday[1].index.normalize().unique()
    times = FakeData.intraday[1].index[FakeData.intraday[1].index.normalize() == days[0]]
    for bar_time in times:
        FakeData.now = bar_time.to_pydatetime()
        run.trade_desk(cfg, store, data, "day", FakeData.now)
    return store, times


def test_every_check_shows_up_with_its_scores_team_and_decision(cfg, tmp_path, monkeypatch):
    store, times = day_of_checks(cfg, tmp_path, monkeypatch)
    last = times[-1].to_pydatetime()
    t = dashboard.thinking(cfg, store, now=last)
    day = next(d for d in t["desks"] if d["desk"] == "day")
    assert day["today"] and day["account"] == "in its head" and day["strategy"]
    assert day["top"] and all({"ticker", "score", "owned"} <= set(r) for r in day["top"])
    assert set(day["team"]) == {"scout", "analyst", "trader", "risk"}
    assert day["orders"] or day["why"]                           # what it did, or why it didn't
    checks = store.get("study-day_checks")["items"]
    assert len(day["checks"]) == len(checks) > 10                # every 5-minute check today, newest first
    assert day["checks"][0]["time"] >= day["checks"][-1]["time"]
    assert store.get("autopilot_step")["text"]                   # it said what it was doing as it went


def test_it_shows_what_it_owns_and_how_far_each_is_from_the_stop(cfg, tmp_path):
    import pandas as pd
    from aitrader.brokers.base import Ledger, Position
    from aitrader.brokers.paper import PaperBroker
    from aitrader.engine import remember_watch
    from aitrader.risk import RiskManager
    store = Store(tmp_path / "aitrader.sqlite")
    ledger = Ledger(500.0)
    ledger.positions["KO"] = Position("KO", 1.5, 80.0, "2026-10-01")
    ledger.positions["XLE"] = Position("XLE", 1, 60.0, "2026-10-01", stop_pct=3.0)
    broker = PaperBroker(ledger, 0.0, mode="paper-swing")
    remember_watch(store, "paper-swing", pd.Timestamp("2026-10-01 11:05").to_pydatetime(),
                   RiskManager(stop_loss_pct=7), pd.Series({"KO": 86.0, "XLE": 62.0}), broker)
    w = {h["ticker"]: h for h in store.get("paper-swing_watch")["holdings"]}
    assert w["KO"]["stop"] == 74.4 and w["KO"]["above_stop_pct"] == 15.6       # the desk's 7% stop
    assert w["XLE"]["stop"] == 58.2 and w["XLE"]["above_stop_pct"] == 6.5      # its own, sized stop


def test_it_says_what_the_autopilot_is_doing_right_now(cfg, tmp_path):
    from datetime import datetime
    store, now = Store(tmp_path / "aitrader.sqlite"), datetime(2026, 10, 1, 10, 37, 20)
    store.set("autopilot_heartbeat", "2026-10-01T10:35:05")
    store.set("autopilot_busy", {"job": "day", "since": "2026-10-01T10:35:01"})
    store.set("autopilot_step", {"mode": "study-day", "text": "scoring 40 stocks with tjr_model",
                                 "at": "2026-10-01T10:35:09"})
    live = dashboard.thinking(cfg, store, now=now)["live"]
    assert live["busy"] and live["text"] == "A day-desk check: scoring 40 stocks with tjr_model…"
    store.set("autopilot_busy", None)
    live = dashboard.thinking(cfg, store, now=now)["live"]
    assert not live["busy"] and "next check at 10:40" in live["text"]
    store.set("scan_status", {"day": "2026-10-01", "kind": "morning", "tries": 1, "started": "2026-10-01T09:25"})
    assert "scanning all US stocks" in dashboard.thinking(cfg, store, now=now)["live"]["also"]
    assert all(not d["today"] and d["checks"] == [] for d in dashboard.thinking(cfg, store, now=now)["desks"])


def test_the_phone_and_the_app_may_ask_for_it():
    from aitrader import phone_screen
    assert "thinking" in phone_screen.ALLOWED                    # read-only, like the snapshot
    assert '"thinking"' in (REPO / "mac/app/main.swift").read_text()
