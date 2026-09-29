"""The dashboard (a local web page) and the pause button's meaning."""
import http.client
import json
import os
import socket
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


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_only_the_page_opened_from_the_menu_can_read_or_press_buttons(filled):
    cfg, _ = filled
    calls = []
    port = _free_port()
    server = dashboard.start(cfg, {"pause": lambda: calls.append("pause") or "paused",
                                   "kill": lambda: calls.append("kill") or "killed"}, port)
    key = dashboard.token(cfg)
    assert oct(os.stat(dashboard.data_path(cfg, "dashboard_token")).st_mode & 0o777) == "0o600"
    assert dashboard.url(cfg, port) == f"http://127.0.0.1:{port}/#t={key}"

    def ask(method, path, host=f"127.0.0.1:{port}", key=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": host, **({"X-Token": key} if key else {})}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    try:
        status, page = ask("GET", "/")
        assert status == 200 and b"<title>AI Trader</title>" in page
        assert dashboard.is_running(cfg, port)
        assert ask("GET", "/api/snapshot")[0] == 401                                # no key
        assert ask("GET", "/api/snapshot", key="wrong")[0] == 401
        assert ask("GET", "/api/snapshot", host=f"evil.example:{port}", key=key)[0] == 403   # DNS rebinding
        status, data = ask("GET", "/api/snapshot", key=key)
        assert status == 200 and json.loads(data)["accounts"]["paper"]["value"] == 998.0

        assert ask("POST", "/api/pause")[0] == 403 and calls == []                  # no key: no button
        assert ask("POST", "/api/pause", host=f"evil.example:{port}", key=key)[0] == 403
        assert ask("POST", "/api/kill", key=key, body={})[0] == 400 and calls == []       # must type it
        assert ask("POST", "/api/kill", key=key, body={"confirm": "sell everything"})[0] == 400
        assert ask("POST", "/api/buy", key=key)[0] == 404                             # there is no buy button
        status, data = ask("POST", "/api/pause", key=key)
        assert status == 200 and json.loads(data)["message"] == "paused" and calls == ["pause"]
        assert ask("POST", "/api/kill", key=key, body={"confirm": "SELL EVERYTHING"})[0] == 200
        assert calls == ["pause", "kill"]
        assert dashboard.start(cfg, {}, port) is None                                # port busy: no crash
    finally:
        server.shutdown()
        server.server_close()


def test_the_dashboards_pause_button_halts_every_desk(cfg):
    import run
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    message = run.dashboard_actions(cfg)["pause"]()
    assert store.get("halted:swing") and store.get("halted:day") and not store.get("exiting:swing")
    assert "no new trades" in message and "PAUSED from the dashboard" in store.journal(1)[0][1]


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


def test_demo_runs_the_real_code_and_never_touches_your_data(cfg, tmp_path, monkeypatch):
    from aitrader import demo
    monkeypatch.setattr(demo, "DAYS", 300)
    monkeypatch.setattr(demo, "INTRADAY_DAYS", 6)
    monkeypatch.setattr(demo, "PAPER_DAYS", 5)
    monkeypatch.setattr(demo, "DAY_DESK_PAPER_DAYS", 2)
    (tmp_path / "demo").mkdir()
    monkeypatch.setattr(demo.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "demo"))
    cfg["desks"]["swing"]["watchlist"] = cfg["desks"]["swing"]["watchlist"][:3]
    cfg["desks"]["day"]["watchlist"] = cfg["desks"]["day"]["watchlist"][:3]
    out = demo.build(cfg)
    assert out["data_dir"] != cfg["data_dir"] and not list(tmp_path.glob("*.sqlite"))   # real folder untouched
    snap = dashboard.snapshot(out, Store(dashboard.data_path(out, "aitrader.sqlite")))
    assert snap["demo"] and snap["prices"] == "demo"
    assert [d["phase"] for d in snap["desks"]] == ["PAPER", "PAPER"]
    assert len(snap["accounts"]["paper"]["dates"]) == 5 and snap["accounts"]["paper"]["series"]["benchmark"]

    import run
    run.dashboard_actions(out)["kill"]()              # the demo's emergency stop works offline
    store = Store(dashboard.data_path(out, "aitrader.sqlite"))
    assert store.get("paper-swing_ledger")["positions"] == {} == store.get("paper-day_ledger")["positions"]
    assert store.get("halted:swing") and not store.get("exiting:swing")
    paper = dashboard.snapshot(out, store)["accounts"]["paper"]
    assert paper["value"] == paper["cash"]            # sold out: the headline value is just the cash
