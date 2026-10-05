"""The daily scan of all US stocks: the list it builds, how it remembers, and how news can only hold it back."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from aitrader import knowledge, scanner
from aitrader.config import data_path
from aitrader.storage import Store


def series(start, end, days=300, volume=2_000_000, seed=0):
    rng = np.random.default_rng(seed)
    close = np.geomspace(start, end, days) * (1 + rng.normal(0, 0.003, days))
    idx = pd.bdate_range(end="2026-09-29", periods=days)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": volume}, index=idx)


def fake_market():
    return {
        "ROCKET": series(20, 60),                      # up 3x over the year, still rising: #1
        "STEADY": series(40, 52, seed=1),              # up ~30%
        "SINKER": series(80, 40, seed=2),              # falling: never on the list
        "PENNY": series(0.5, 2.5, seed=3),             # under $3: skipped
        "QUIET": series(20, 50, volume=10_000, seed=4),  # too little trading
        "NEWCO": series(10, 25, days=120, seed=5),     # listed 6 months ago: watch-only list
    }


def run_scan(cfg, store, day="2026-09-29", news=None, market=None):
    fetch = lambda cfg, symbols, days: market or fake_market()
    get_news = lambda cfg, symbols, days: {s: (news or {}).get(s, []) for s in symbols}
    cfg["scanner"] = {**scanner.settings(cfg), "top": 5}
    return scanner.run(cfg, store, day, fetch=fetch, get_news=get_news)


def test_the_list_is_uptrending_actively_traded_stocks_best_first(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    store = Store(":memory:")
    summary = run_scan(cfg, store)
    state = scanner.load_list(cfg)
    assert [r["symbol"] for r in state["liked"]] == ["ROCKET", "STEADY"]
    assert [r["symbol"] for r in state["new_listings"]] == ["NEWCO"]
    assert "6 stocks checked" in summary and "ROCKET" in summary
    assert scanner.trade_candidates(cfg) == ["ROCKET", "STEADY"]


def test_the_list_remembers_when_each_stock_joined_and_left(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    store = Store(":memory:")
    run_scan(cfg, store, "2026-09-28")
    run_scan(cfg, store, "2026-09-29")
    rocket = scanner.load_list(cfg)["liked"][0]
    assert rocket["first_listed"] == "2026-09-28" and rocket["days_listed"] == 2
    market = fake_market()
    market["STEADY"] = series(52, 30, seed=1)                                   # it turned down
    run_scan(cfg, store, "2026-09-30", market=market)
    state = scanner.load_list(cfg)
    assert "STEADY" not in [r["symbol"] for r in state["liked"]]
    assert state["history"]["STEADY"]["left_on"] == "2026-09-30"


def test_danger_headlines_block_buying_and_news_never_adds_a_stock(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    store = Store(":memory:")
    news = {"ROCKET": [{"time": "2026-09-29 08:00", "headline": "Rocket Corp announces $200M public offering",
                        "source": "Benzinga", "url": "https://example.com/a"}],
            "SINKER": [{"time": "2026-09-29 09:00", "headline": "Sinker beats estimates, soars", "source": "x", "url": ""}]}
    summary = run_scan(cfg, store, news=news)
    assert scanner.danger_tickers(cfg) == {"ROCKET": ["offering"]}
    assert "danger news, not buying: ROCKET" in summary
    assert "SINKER" not in [r["symbol"] for r in scanner.load_list(cfg)["liked"]]   # good news doesn't add it


def test_you_can_turn_the_scan_and_the_news_off(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    store = Store(":memory:")
    cfg["scanner"] = {"enabled": "off"}
    assert scanner.run(cfg, store, "2026-09-29") == "scan: off (Setup)"
    assert scanner.trade_candidates(cfg) == []
    cfg["scanner"], cfg["news"] = {"enabled": True}, {"enabled": "off"}
    asked = []
    scanner.run(cfg, store, "2026-09-29", fetch=lambda c, s, d: fake_market(),
                get_news=lambda c, s, d: asked.append(s) or {})
    assert asked == []                                                          # no news read at all


def test_the_local_ai_reads_the_list(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    run_scan(cfg, Store(":memory:"))
    text = knowledge.pack(cfg)
    assert "Stocks I like right now" in text and "ROCKET" in text


def test_the_scan_runs_after_the_close_once_a_day():
    import run
    after = datetime(2026, 9, 29, 16, 25)
    assert "scan" in run.due_jobs(after, set())
    assert "scan" not in run.due_jobs(after, {"scan:2026-09-29"})
    assert "scan" not in run.due_jobs(datetime(2026, 9, 29, 11, 0), set())


def test_the_swing_desk_also_considers_the_top_of_the_list(cfg, monkeypatch):
    from aitrader import market_data
    monkeypatch.setattr(scanner, "trade_candidates", lambda cfg: ["ROCKET"])
    loaded = []
    monkeypatch.setattr(market_data.MarketData, "history",
                        lambda self, t, i: loaded.append(t) or series(10, 20))
    data = market_data.MarketData(cfg)
    bars, _ = data.load("swing")
    assert "ROCKET" in bars and "ROCKET" in loaded
    bars, _ = data.load("day")
    assert "ROCKET" not in bars                                                 # the day desk keeps its own list


def test_the_app_always_gets_valid_json_even_with_missing_numbers(cfg, monkeypatch, capsys):
    """A stock with no year of history has no 12-month number: it must come out as null, not NaN."""
    import json
    from aitrader import app_api
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    run_scan(cfg, Store(":memory:"))
    monkeypatch.setattr(app_api, "load_config", lambda: cfg)
    capsys.readouterr()
    app_api.main(["snapshot"])
    text = capsys.readouterr().out
    assert "NaN" not in text and "Infinity" not in text
    snap = json.loads(text)
    assert snap["scan"]["new_listings"][0]["symbol"] == "NEWCO" and snap["scan"]["new_listings"][0]["momentum_pct"] is None


def test_a_new_install_scans_in_the_morning_so_the_first_decision_can_use_the_list(cfg, monkeypatch):
    import run
    monkeypatch.setattr(run, "schwab_login_warning", lambda cfg: "")
    monkeypatch.setattr(run, "SCAN_IN_BACKGROUND", False)
    ran = []
    monkeypatch.setattr(scanner, "run", lambda cfg, store, today: ran.append(today) or "scan: 6 stocks checked")
    store = Store(":memory:")
    run.run_job("morning", cfg, store, None, datetime(2026, 9, 30, 9, 30), set())
    assert ran == ["2026-09-30"]
    monkeypatch.setattr(scanner, "load_list", lambda cfg: {"updated": "2026-09-30", "liked": [{"symbol": "ROCKET"}]})
    run.run_job("morning", cfg, store, None, datetime(2026, 10, 1, 9, 30), set())
    assert ran == ["2026-09-30"]                                                # has a list: waits for tonight


def test_when_the_notes_are_too_long_the_tjr_notes_are_cut_not_the_stock_list(cfg, monkeypatch):
    """TJR's notes are for Stage 2; the stocks it likes and its own lessons matter now."""
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    run_scan(cfg, Store(":memory:"))
    text = knowledge.pack(cfg, max_chars=len(knowledge.pack(cfg)) - 200)
    assert "Stocks I like right now" in text and "ROCKET" in text
    assert text.index("Stocks I like right now") < text.index("# TJR's model")
    assert text.index("Hard safety rules") < text.index("Stocks I like right now")   # safety always first


def test_the_scan_runs_in_the_background_so_trading_never_waits(cfg, monkeypatch):
    import threading
    import run
    started, release = threading.Event(), threading.Event()

    def slow_scan(cfg, store, today):
        started.set()
        release.wait(5)
        return "scan: 6 stocks checked"
    monkeypatch.setattr(scanner, "run", slow_scan)
    store = Store(data_path(cfg, "aitrader.sqlite"))
    assert run.run_job("scan", cfg, store, None, datetime(2026, 9, 29, 16, 25), set()) == "scan started in the background"
    assert started.wait(5)                                          # it's running...
    assert "already running" in run.run_job("scan", cfg, store, None, datetime(2026, 9, 29, 16, 30), set())
    release.set()                                                   # ...while the caller carried on
    run._scanning.join(5)
    assert any("[scan] scan: 6 stocks checked" in m for _, m in Store(data_path(cfg, "aitrader.sqlite")).journal(10))


def test_a_stuck_autopilot_restarts_itself_but_a_busy_one_is_left_alone(cfg, monkeypatch):
    import time
    import run
    restarted = []
    monkeypatch.setattr(run.os, "execv", lambda exe, argv: restarted.append(argv))
    assert not run.restart_if_stuck(cfg, {"t": time.monotonic() - 20 * 60, "job": "scan"})     # 20 min: fine
    assert restarted == []
    assert run.restart_if_stuck(cfg, {"t": time.monotonic() - 31 * 60, "job": "day"})          # 31 min: stuck
    assert restarted and any("stuck for 31 minutes on 'day'" in m
                             for _, m in Store(data_path(cfg, "aitrader.sqlite")).journal(5))


def test_a_new_background_autopilot_stops_an_old_one_left_behind(cfg, monkeypatch):
    import run
    from aitrader import mac_service
    store = Store(data_path(cfg, "aitrader.sqlite"))
    store.set("autopilot_pid", 4242)
    alive = {4242}
    killed = []
    monkeypatch.setattr(run, "process_alive", lambda pid: pid in alive)
    monkeypatch.setattr(run.os, "kill", lambda pid, sig: killed.append((pid, sig)) or alive.discard(pid))
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    monkeypatch.setattr(mac_service, "command_of", lambda pid: "/usr/bin/python3 -u /Users/x/AITrader/run.py autopilot")
    monkeypatch.setenv("KESTREL_SERVICE", "1")
    assert "Stopped an older autopilot (process 4242)" in run.take_over(store) and killed[0][0] == 4242

    store.set("autopilot_pid", 5151)                              # that id now belongs to some other program
    alive.add(5151)
    monkeypatch.setattr(mac_service, "command_of", lambda pid: "/usr/libexec/something")
    assert run.take_over(store) == "" and 5151 in alive

    monkeypatch.delenv("KESTREL_SERVICE")                         # a Terminal-window autopilot steps aside
    monkeypatch.setattr(run.os, "getppid", lambda: 999)
    monkeypatch.setattr(mac_service, "command_of", lambda pid: "python run.py autopilot" if pid == 5151 else "-zsh")
    with pytest.raises(RuntimeError, match="already running"):
        run.take_over(store)


def test_on_means_running_and_setup_says_why_it_stopped(cfg, monkeypatch):
    import subprocess
    from aitrader import app_api, mac_service
    monkeypatch.setattr(mac_service.sys, "platform", "darwin")
    answers = {"out": "state = waiting\n\tpid = 812\n", "code": 0}
    monkeypatch.setattr(mac_service.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], answers["code"], stdout=answers["out"], stderr=""))
    assert mac_service.status() == {"on": True, "running": True}
    answers["out"] = "state = spawn scheduled\n\tlast exit code = 1\n"            # crashing: on, not running
    assert mac_service.status() == {"on": True, "running": False}
    answers["code"] = 113                                                        # not installed
    assert mac_service.status() == {"on": False, "running": False}

    store = Store(data_path(cfg, "aitrader.sqlite"))
    store.log("Autopilot started. Keep the laptop awake and online (Ctrl+C stops it).")
    assert app_api.autopilot_problem(store) == ""
    store.log("STOPPED: The autopilot is already running (process 4242). Only one may run at a time.")
    assert "already running (process 4242)" in app_api.autopilot_problem(store)


def test_the_swing_desk_gets_the_strongest_stocks_it_can_afford_and_never_the_day_desks(cfg, monkeypatch):
    market = fake_market()
    market["PRICEY"] = series(100, 400, seed=6)                 # the strongest of all, but $400 a share
    market["DAYONE"] = series(20, 58, seed=7)                   # strong, but the day desk trades it
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(market))
    cfg["desks"]["day"]["watchlist"] = list(cfg["desks"]["day"]["watchlist"]) + ["DAYONE"]
    cfg["paper"]["starting_cash"] = 1000                          # swing: $500, 8 slots -> about $62 a share
    cfg["desks"]["swing"]["risk"].update(max_open_positions=8, max_position_pct=12.5)
    assert round(scanner.swing_price_limit(cfg), 2) == 61.88
    store = Store(":memory:")
    run_scan(cfg, store, market=market)
    state = scanner.load_list(cfg)
    assert state["liked"][0]["symbol"] == "PRICEY"                # still on the list you see
    picks = scanner.trade_candidates(cfg)
    assert "PRICEY" not in picks and "DAYONE" not in picks and picks[0] == "ROCKET"
    assert all(r["price"] <= 61.88 for r in state["swing_picks"])


def test_an_older_list_without_picks_still_works(cfg, monkeypatch):
    import json
    from aitrader.config import data_path
    data_path(cfg, scanner.LIST_FILE).write_text(json.dumps({"liked": [{"symbol": "AAA"}, {"symbol": "SOFI"}]}))
    cfg["desks"]["day"]["watchlist"] = ["SOFI"]
    assert scanner.trade_candidates(cfg) == ["AAA"]


def test_the_scan_counts_as_done_only_when_it_finished(cfg, monkeypatch):
    """A scan cut short (the Mac restarted, an update) or one that failed runs again; six failures wait
    for the next day. Before, it was never marked done and started over every 5 minutes all evening."""
    import run
    monkeypatch.setattr(run, "SCAN_IN_BACKGROUND", False)
    store, today, now = Store(":memory:"), "2026-09-30", datetime(2026, 9, 30, 16, 25)
    results = iter([RuntimeError("Alpaca refused 20 of 30 batches"), "scan: 9000 stocks checked"])

    def fake_run(cfg, store, day):
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(scanner, "run", fake_run)
    run.run_job("scan", cfg, store, None, now, set())
    assert not run.job_complete("scan", store, today)                   # failed once: tries again
    assert "try 1 of 6" in store.journal(5)[-1][1] and "tries again in 5 minutes" in store.journal(5)[-1][1]
    run.run_job("scan", cfg, store, None, now, set())
    assert run.job_complete("scan", store, today)                       # finished
    assert run.scan_state(store, today)["summary"] == "scan: 9000 stocks checked"
    assert run.run_job("scan", cfg, store, None, now, set()) == ""      # doesn't scan again today

    store = Store(":memory:")
    monkeypatch.setattr(scanner, "run", lambda cfg, store, day: 1 / 0)
    for _ in range(run.SCAN_TRIES):
        run.run_job("scan", cfg, store, None, now, set())
    assert run.job_complete("scan", store, today)                       # gave up until tomorrow
    assert "gave up" in run.run_job("scan", cfg, store, None, now, set())

    store = Store(":memory:")                                           # started, then the Mac restarted
    store.set("scan_status", {"day": today, "kind": "evening", "tries": 1, "started": "2026-09-30T16:20"})
    assert not run.job_complete("scan", store, today)


def test_a_stale_list_is_scanned_again_in_the_morning(cfg, monkeypatch):
    import run
    monkeypatch.setattr(run, "SCAN_IN_BACKGROUND", False)
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    run_scan(cfg, Store(":memory:"), "2026-09-25")                      # Friday's list
    ran = []
    monkeypatch.setattr(scanner, "run", lambda cfg, store, day: ran.append(day) or "scan: ok")
    run.first_scan(cfg, Store(":memory:"), "2026-09-28")                # Monday: Friday's list is fine
    assert ran == []
    run.first_scan(cfg, Store(":memory:"), "2026-09-30")                # Wednesday: Tuesday's scan didn't finish
    assert ran == ["2026-09-30"]


def test_a_quick_look_first_then_a_full_year_only_for_actively_traded_stocks(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    asked = []

    def fetch(cfg, symbols, days):
        asked.append((days, sorted(symbols)))
        return {s: df for s, df in fake_market().items() if s in symbols}
    cfg["scanner"] = {**scanner.settings(cfg), "top": 5}
    summary = scanner.run(cfg, Store(":memory:"), "2026-09-29", fetch=fetch, get_news=lambda c, s, d: {})
    assert asked[0] == (45, sorted(fake_market()))
    assert asked[1] == (400, ["NEWCO", "ROCKET", "SINKER", "STEADY"])  # not PENNY (under $3) or QUIET (thin)
    assert "6 stocks checked, 4 actively traded" in summary and "the swing desk can afford" in summary


def test_alpaca_batches_that_fail_are_tried_again_and_mostly_failing_is_an_error(cfg, monkeypatch):
    from aitrader import alpaca_api
    monkeypatch.setattr(scanner, "_pause", lambda s: None)
    cfg["secrets"].update(alpaca_paper_key="k", alpaca_paper_secret="s")
    calls = {"n": 0}

    class Reply:
        def __init__(self, symbols):
            rows = [(s, pd.Timestamp("2026-09-29", tz="UTC")) for s in symbols]
            self.df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 5.0, "volume": 1e6},
                                   index=pd.MultiIndex.from_tuples(rows, names=["symbol", "timestamp"]))

    class Flaky:                                                         # refuses the first 3 requests
        def get_stock_bars(self, request):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise RuntimeError("too many requests")
            return Reply(request.symbol_or_symbols)
    monkeypatch.setattr(alpaca_api, "data_client", lambda cfg: Flaky())
    out = scanner._alpaca_bars(cfg, ["AAA", "BBB"], 45)
    assert sorted(out) == ["AAA", "BBB"]                                 # the retry got it

    class Refuses:
        def get_stock_bars(self, request):
            raise RuntimeError("too many requests")
    monkeypatch.setattr(alpaca_api, "data_client", lambda cfg: Refuses())
    with pytest.raises(RuntimeError, match="refused 1 of 1 batches"):
        scanner._alpaca_bars(cfg, ["AAA"], 45)


def test_the_report_says_whether_the_scan_is_working(cfg, monkeypatch):
    from aitrader.report import scan_lines
    store = Store(":memory:")
    text = "\n".join(scan_lines(cfg, store, "2026-09-30"))
    assert "No stock list yet" in text and "only picks from its watchlist" in text
    store.set("scan_status", {"day": "2026-09-30", "kind": "evening", "tries": 2, "error": "RuntimeError('refused')"})
    assert "FAILED: RuntimeError('refused')" in "\n".join(scan_lines(cfg, store, "2026-09-30"))
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    summary = run_scan(cfg, store, "2026-09-30")
    store.set("scan_status", {"day": "2026-09-30", "kind": "evening", "tries": 1,
                              "finished": "2026-09-30T16:31", "summary": summary})
    text = "\n".join(scan_lines(cfg, store, "2026-09-30"))
    assert "Last scan (2026-09-30 16:31): 6 stocks checked" in text and "ROCKET" in text
    assert "The swing desk also considers" in text


def test_a_scan_cut_short_resumes_from_its_saved_pieces(cfg, monkeypatch):
    """Each piece of the scan is saved the moment it arrives: after a restart or an update the scan picks up
    where it stopped instead of starting over (before, an update could kill it every time)."""
    monkeypatch.setattr(scanner, "GROUP", 2)
    monkeypatch.setattr(scanner, "universe", lambda cfg: sorted(fake_market()))
    asked, crash = [], {"after": 2}

    def fetch(cfg, symbols, days):
        if days == 45 and crash["after"] == 0:
            raise RuntimeError("the Mac restarted")
        asked.append((days, tuple(symbols)))
        if days == 45:
            crash["after"] -= 1
        return {s: df for s, df in fake_market().items() if s in symbols}
    cfg["scanner"] = {**scanner.settings(cfg), "top": 5}
    with pytest.raises(RuntimeError):
        scanner.run(cfg, Store(":memory:"), "2026-09-29", fetch=fetch, get_news=lambda c, s, d: {})
    assert [a for a in asked if a[0] == 45] == [(45, ("NEWCO", "PENNY")), (45, ("QUIET", "ROCKET"))]
    crash["after"], asked[:] = 99, []
    summary = scanner.run(cfg, Store(":memory:"), "2026-09-29", fetch=fetch, get_news=lambda c, s, d: {})
    assert [a for a in asked if a[0] == 45] == [(45, ("SINKER", "STEADY"))]          # only the piece it hadn't got
    assert summary.startswith("scan: 6 stocks checked, 4 actively traded")
    assert scanner.read_progress(cfg)["step"] == "finished"


def test_the_next_days_scan_reuses_the_saved_year_of_prices(cfg, monkeypatch):
    monkeypatch.setattr(scanner, "universe", lambda cfg: sorted(fake_market()))
    asked = []

    def fetch(cfg, symbols, days):
        asked.append((days, sorted(symbols)))
        out = {s: df for s, df in fake_market().items() if s in symbols}
        return {s: df.tail(30) for s, df in out.items()} if days == 45 else out
    cfg["scanner"] = {**scanner.settings(cfg), "top": 5}
    first = scanner.run(cfg, Store(":memory:"), "2026-09-28", fetch=fetch, get_news=lambda c, s, d: {})
    assert (400, ["NEWCO", "ROCKET", "SINKER", "STEADY"]) in asked
    asked.clear()
    second = scanner.run(cfg, Store(":memory:"), "2026-09-29", fetch=fetch, get_news=lambda c, s, d: {})
    assert [a for a in asked if a[0] == 400] == []                                  # nothing downloaded twice
    assert "(4 from the saved year of prices)" in second
    assert scanner.load_list(cfg)["liked"][0]["symbol"] == "ROCKET"

    split = {s: df.copy() for s, df in fake_market().items()}                       # ROCKET splits 2-for-1
    split["ROCKET"][["open", "high", "low", "close"]] /= 2
    asked.clear()
    scanner.run(cfg, Store(":memory:"), "2026-09-30",
                fetch=lambda c, symbols, days: (asked.append((days, sorted(symbols))) or
                                                {s: (df.tail(30) if days == 45 else df) for s, df in split.items()
                                                 if s in symbols}), get_news=lambda c, s, d: {})
    assert (400, ["ROCKET"]) in asked                                                # its history is fetched again


def test_the_report_waits_for_a_running_scan_until_530(cfg, monkeypatch):
    import run
    from aitrader import report
    monkeypatch.setattr(run, "scan_running", lambda: True)
    written = []
    monkeypatch.setattr(report, "write_after_market", lambda cfg, store, day: written.append(day))
    store = Store(":memory:")
    said = run.run_job("report", cfg, store, None, datetime(2026, 10, 2, 16, 30), set())
    assert said.startswith("after-market report: waiting for the scan") and not written
    assert not run.job_complete("report", store, "2026-10-02")                    # tries again in 5 minutes
    run.run_job("report", cfg, store, None, datetime(2026, 10, 2, 17, 31), set())  # 5:30pm: writes it anyway
    assert written == ["2026-10-02"] and run.job_complete("report", store, "2026-10-02")


def test_the_local_ais_summary_is_kept_short():
    from aitrader.report import trim_words
    long = "\n".join(f"* point {i} " + "word " * 40 for i in range(10))
    short = trim_words(long, 160)
    assert short.count("\n") == 2 and short.startswith("* point 0")                # whole lines, about 160 words


def test_a_stock_listed_60_to_63_days_ago_no_longer_breaks_the_scan(cfg, monkeypatch):
    """The bug behind 'the scan never finishes': a stock with 60-63 days of prices crashed the 3-month
    return (IndexError), and with new listings every week there's nearly always one."""
    market = {**fake_market(), "IPO": series(10, 14, days=61, seed=7)}
    summary = run_scan(cfg, Store(":memory:"), market=market)
    assert summary.startswith("scan: 7 stocks checked")
    assert scanner.load_list(cfg)["liked"][0]["symbol"] == "ROCKET"
    odd = {**fake_market(), "BROKEN": series(10, 14, seed=8).assign(close=float("nan"))}
    assert run_scan(cfg, Store(":memory:"), day="2026-09-30", market=odd).startswith("scan: 7 stocks checked")
