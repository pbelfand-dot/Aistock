"""The daily scan of all US stocks: the list it builds, how it remembers, and how news can only hold it back."""
from datetime import datetime

import numpy as np
import pandas as pd

from aitrader import knowledge, scanner
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
