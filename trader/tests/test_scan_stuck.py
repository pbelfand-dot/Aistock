"""A network call that never answers must not freeze the scan: Alpaca requests get a time limit, a scan
stuck for too long is started over, and a morning scan cut short tries again during the day."""
import socket
import threading
import time
from datetime import datetime

import pytest
import requests

from aitrader import alpaca_api, scanner
from aitrader.config import data_path
from aitrader.storage import Store


def test_every_alpaca_request_gets_a_time_limit(cfg, monkeypatch):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    held = []                                                   # accepts the connection, never answers
    threading.Thread(target=lambda: [held.append(srv.accept()) for _ in range(3)], daemon=True).start()

    class Client:
        _session = requests.Session()
    client = alpaca_api.timed(alpaca_api.timed(Client()))      # wrapped once, however often it's asked
    monkeypatch.setattr(alpaca_api, "TIMEOUT", (1, 1))
    began = time.monotonic()
    with pytest.raises(requests.exceptions.Timeout):
        client._session.request("GET", f"http://127.0.0.1:{srv.getsockname()[1]}/")
    assert time.monotonic() - began < 10                       # it gave up instead of waiting forever
    srv.close()

    cfg["secrets"].update(alpaca_paper_key="PKTEST", alpaca_paper_secret="secret")
    assert alpaca_api.trading_client(cfg, paper=True)._session.kestrel_timeout
    assert alpaca_api.data_client(cfg)._session.kestrel_timeout


def test_a_stuck_scan_is_given_up_on_and_started_over(cfg, monkeypatch):
    import run
    store, release, started, calls = Store(data_path(cfg, "aitrader.sqlite")), threading.Event(), threading.Event(), []

    def scan(cfg, store, today):
        calls.append(today)
        if len(calls) == 1:
            started.set()
            release.wait(10)                                    # the first one hangs (a call that never answers)
            return "scan: old, late"
        return "scan: fresh"
    monkeypatch.setattr(scanner, "run", scan)
    monkeypatch.setattr(run, "_scanning", None)
    now = datetime(2026, 10, 1, 16, 25)
    assert run.run_job("scan", cfg, store, None, now, set()) == "scan started in the background"
    stuck = run._scanning
    assert started.wait(5)
    assert "already running" in run.run_job("scan", cfg, store, None, now, set())     # still young: leave it
    monkeypatch.setattr(run, "_scan_began", time.monotonic() - 46 * 60)
    assert run.run_job("scan", cfg, store, None, now, set()) == "scan started in the background"
    run._scanning.join(5)
    assert any("stuck for over 45 minutes" in m for _, m in store.journal(10))
    assert run.scan_state(store, "2026-10-01")["summary"] == "scan: fresh"
    assert run.scan_state(store, "2026-10-01")["tries"] == 2
    release.set()                                               # the stuck one finally returns...
    stuck.join(5)
    assert run.scan_state(store, "2026-10-01")["summary"] == "scan: fresh"   # ...and changes nothing


def test_a_morning_scan_cut_short_tries_again_during_the_day(cfg, monkeypatch):
    import run
    monkeypatch.setattr(run, "SCAN_IN_BACKGROUND", False)
    ran = []
    monkeypatch.setattr(scanner, "run", lambda cfg, store, day: ran.append(day) or "scan: ok")
    store, morning = Store(":memory:"), {"morning:2026-10-01"}
    run.keep_trying_the_scan(cfg, store, datetime(2026, 10, 1, 11, 0), set())        # morning not done yet
    run.keep_trying_the_scan(cfg, store, datetime(2026, 10, 1, 15, 40), morning)     # too late: the evening scan
    run.keep_trying_the_scan(cfg, store, datetime(2026, 10, 3, 11, 0), {"morning:2026-10-03"})   # Saturday
    assert ran == []
    run.keep_trying_the_scan(cfg, store, datetime(2026, 10, 1, 11, 0), morning)      # no list yet: scan now
    assert ran == ["2026-10-01"]
