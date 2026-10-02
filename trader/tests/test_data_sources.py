"""News and data sources: the big economic news dates (FRED), official SEC filings, and "why it moved".
Nothing here goes online: FRED and the SEC are faked."""
import json
from datetime import datetime

import pandas as pd
import pytest

import run
from aitrader import app_api, dashboard, macro, report, sec_filings, stock_info
from aitrader.config import data_path, data_source
from aitrader.storage import Store


class Answer:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.text = body, status, json.dumps(body)

    def json(self):
        return self.body


# ---------------------------------------------------------------- FRED
NAMES = {10: "Consumer Price Index", 50: "Employment Situation", 101: "FOMC Press Release"}
DATES = {10: ["2026-09-11", "2026-10-15", "2026-11-13"], 50: ["2026-10-02", "2026-11-06"],
         101: ["2026-10-28", "2026-12-09"]}


@pytest.fixture
def fred(cfg, monkeypatch):
    cfg["secrets"]["fred_key"] = "a" * 32
    calls = []

    def get(url, params, timeout):
        calls.append((url, params))
        rid = int(params["release_id"])
        if url.endswith("/release"):
            return Answer({"releases": [{"id": rid, "name": NAMES[rid]}]})
        return Answer({"release_dates": [{"release_id": rid, "date": d} for d in DATES[rid]]})
    monkeypatch.setattr(macro, "_get", get)
    return calls


def test_the_calendar_has_cpi_jobs_and_fed_dates_with_a_countdown(cfg, fred):
    cal = macro.refresh(cfg, "2026-10-01")
    assert not cal["error"] and {e["key"] for e in cal["events"]} == {"cpi", "jobs", "fed"}
    assert all(p["include_release_dates_with_no_data"] == "true" and p["realtime_end"] == "9999-12-31"
               for u, p in fred if u.endswith("/dates"))                # future dates come too
    assert macro.events_on(cfg, "2026-10-02") == ["jobs"]
    assert macro.tags(cfg, "2026-10-28") == ["on a Fed-decision day"]
    soon = macro.upcoming(cfg, datetime(2026, 10, 2, 7, 0))
    assert soon[0]["name"] == "jobs report" and soon[0]["today"] and soon[0]["countdown"] == "in 1h 30m"
    assert soon[1]["name"] == "CPI (inflation)" and soon[1]["countdown"] == "in 13 days"
    n = len(fred)
    macro.refresh(cfg, "2026-10-01")
    assert len(fred) == n                                               # once a day
    text = "\n".join(macro.lines(cfg, datetime(2026, 10, 2, 16, 25)))
    assert "Today: jobs report at 8:30am" in text and "CPI (inflation) Thu Oct 15" in text


def test_a_renumbered_release_is_skipped_not_mislabelled_and_no_key_means_nothing(cfg, fred, monkeypatch):
    NAMES[50] = "Something Else"
    try:
        cal = macro.refresh(cfg, "2026-10-01", force=True)
    finally:
        NAMES[50] = "Employment Situation"
    assert "jobs" not in {e["key"] for e in cal["events"]} and "Something Else" in cal["error"]
    cfg["secrets"]["fred_key"] = ""
    assert macro.status(cfg, datetime(2026, 10, 2))["upcoming"] == [] and macro.lines(cfg, datetime(2026, 10, 2)) == []


def test_buys_on_a_big_news_day_are_tagged_for_the_mistake_memory(cfg, fred, tmp_path):
    from aitrader.brokers.base import Ledger
    from aitrader.brokers.paper import PaperBroker
    from aitrader.engine import run_cycle
    from aitrader.risk import RiskManager
    from aitrader.strategies import Strategy
    from test_lifecycle import FakeData

    class Always(Strategy):
        name, style, buy_above, sell_below = "always", "swing", 0.5, 0.1

        def scores(self, bars, market, since=None):
            return pd.DataFrame({t: 1.0 for t in bars}, index=market.index)
    bars, market = FakeData.daily
    day = market.index[-1].strftime("%Y-%m-%d")
    data_path(cfg, macro.FILE).write_text(json.dumps({"updated": day, "events": [{"key": "cpi", "date": day}]}))
    store = Store(tmp_path / "aitrader.sqlite")
    broker = PaperBroker(Ledger(500.0), 0.0, mode="paper-swing")
    run_cycle(store, broker, Always(), RiskManager(max_open_positions=2, max_position_pct=40), bars, market,
              market.index[-1].to_pydatetime().replace(hour=15, minute=45), cfg["desks"]["swing"], cfg=cfg)
    tags = store.get("entry_tags:swing")
    assert tags and all("on a CPI day" in t for t in tags.values())
    assert store.get("paper-swing_thinking")["team"]["scout"]["events"] == ["CPI (inflation)"]   # the Scout says so


# ---------------------------------------------------------------- SEC
def submissions(**recent):
    return {"filings": {"recent": recent}}


NOW = datetime(2026, 10, 2, 11, 0)


def test_the_secs_fresh_filing_time_quirk_is_handled():
    fresh = sec_filings.accepted_at("2026-10-02T10:42:00.000Z", NOW)          # New York time labelled Z
    assert fresh == datetime(2026, 10, 2, 10, 42)
    old = sec_filings.accepted_at("2026-10-01T20:05:00.000Z", NOW)            # rewritten to true UTC later
    assert old == datetime(2026, 10, 1, 16, 5)
    future = sec_filings.accepted_at("2026-10-02T14:42:00.000Z", NOW)         # can't be in the future: UTC
    assert future == datetime(2026, 10, 2, 10, 42)
    assert sec_filings.ago(NOW, fresh) == "18 min ago"


def test_filings_read_in_plain_english_and_serious_ones_are_danger():
    data = submissions(form=["8-K", "4", "NT 10-Q", "8-K", "10-Q"],
                       filingDate=["2026-10-02", "2026-10-01", "2026-09-30", "2026-09-29", "2026-07-30"],
                       acceptanceDateTime=["2026-10-02T10:42:00.000Z", "2026-10-01T21:00:00.000Z",
                                           "2026-09-30T20:00:00.000Z", "2026-09-29T20:00:00.000Z",
                                           "2026-07-30T20:00:00.000Z"],
                       accessionNumber=["0001-26-000001", "0001-26-000002", "0001-26-000003", "0001-26-000004",
                                        "0001-26-000005"],
                       primaryDocument=["a.htm", "b.xml", "c.htm", "d.htm", "e.htm"],
                       items=["2.02,9.01", "", "", "4.02", ""])
    f = sec_filings.parse(320193, data, NOW)
    assert [x["form"] for x in f] == ["8-K", "4", "NT 10-Q", "8-K"]          # newest first; July is too old
    assert f[0]["what"] == "news (8-K): results (earnings)" and not f[0]["danger"]
    assert f[0]["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000126000001/a.htm"
    assert f[2]["danger"] == ["a late quarterly report"]
    assert f[3]["danger"] == ["its past financial statements can't be relied on"]


@pytest.fixture
def sec(cfg, monkeypatch):
    cfg["secrets"]["sec_email"] = "owner@example.com"
    cfg["desks"]["swing"]["watchlist"] = ["AAA", "BBB"]
    cfg["desks"]["day"]["watchlist"] = []
    seen = []
    filing = submissions(form=["8-K"], filingDate=["2026-10-02"], acceptanceDateTime=["2026-10-02T10:42:00.000Z"],
                         accessionNumber=["0001-26-000009"], primaryDocument=["x.htm"], items=["1.03"])

    def get(url, headers, timeout):
        seen.append((url, headers))
        if url == sec_filings.TICKERS_URL:
            return Answer({"0": {"cik_str": 111, "ticker": "AAA", "title": "A Co"},
                           "1": {"cik_str": 222, "ticker": "BBB", "title": "B Co"}})
        return Answer(filing if "0000000111" in url else submissions(form=[]))
    monkeypatch.setattr(sec_filings, "_get", get)
    monkeypatch.setattr(sec_filings, "MIN_GAP", 0)
    return seen


def test_a_danger_filing_blocks_buying_and_warns_when_it_owns_the_stock(cfg, sec, tmp_path):
    store = Store(tmp_path / "aitrader.sqlite")
    store.set("paper-swing_ledger", {"cash": 400.0, "positions": {"AAA": {"ticker": "AAA", "qty": 1, "avg_cost": 50.0,
                                                                           "opened_on": "2026-09-30"}}})
    assert sec_filings.check(cfg, store, NOW).startswith("SEC filings: 2 stocks checked")
    assert all("owner@example.com" in h["User-Agent"] for _, h in sec)      # the SEC's rule: say who's asking
    assert run.danger_now(cfg)["AAA"] == ["SEC: bankruptcy or receivership"]
    assert "BBB" not in run.danger_now(cfg)
    lines = [m for _, m in store.journal(5)]
    assert any(m.startswith("WARNING: [sec] AAA filed 8-K") for m in lines)
    sec_filings.check(cfg, store, NOW)
    assert sum("[sec] AAA" in m for _, m in store.journal(10)) == 1        # said once, not every 30 minutes
    card = sec_filings.recent(cfg, "AAA", now=NOW)
    assert card[0]["ago"] == "18 min ago" and card[0]["what"].startswith("news (8-K): bankruptcy")


def test_no_email_means_no_requests(cfg, sec):
    cfg["secrets"]["sec_email"] = ""
    assert not sec_filings.is_on(cfg)
    assert sec_filings.keep_checking(cfg, Store(":memory:"), NOW) == "" and not sec


# ---------------------------------------------------------------- why it moved
def test_why_it_moved_shows_the_move_the_headline_and_the_filing(cfg, sec, tmp_path):
    folder = f"cache/{data_source(cfg)}"
    days = pd.bdate_range(end="2026-10-01", periods=10)
    pd.DataFrame({"open": 50.0, "high": 51.0, "low": 49.0, "close": [50.0] * 9 + [52.0], "volume": 1e6},
                 index=days).to_csv(data_path(cfg, f"{folder}/1d/AAA.csv"))
    five = pd.date_range("2026-10-02 09:30", periods=10, freq="5min")
    pd.DataFrame({"open": 54.0, "high": 55.0, "low": 53.0, "close": 54.6, "volume": 1e5},
                 index=five).to_csv(data_path(cfg, f"{folder}/5m/AAA.csv"))
    data_path(cfg, "liked_stocks.json").write_text(json.dumps({"held_news": {"AAA": {"news": [
        {"time": "2026-10-02 10:40", "headline": "AAA wins a big contract", "source": "Benzinga", "url": "https://x"}]}}}))
    store = Store(tmp_path / "aitrader.sqlite")
    store.set("paper-swing_ledger", {"cash": 400.0, "positions": {"AAA": {"ticker": "AAA", "qty": 1, "avg_cost": 50.0,
                                                                           "opened_on": "2026-09-30"}}})
    sec_filings.check(cfg, store, NOW)
    w = stock_info.why_moved(cfg, "AAA")
    assert w["today_pct"] == 5.0 and w["week_pct"] == pytest.approx(9.2, abs=0.01)
    assert w["headlines"][0]["headline"] == "AAA wins a big contract" and w["filings"]
    text = "\n".join(report.why_lines(cfg, store, "2026-10-02"))
    assert "- AAA +5.0% today, +9.2% in 5 days (owns it): AAA wins a big contract (Benzinga, 10:40)" in text


# ---------------------------------------------------------------- Setup
def test_setup_checks_each_one_before_saving_it(cfg, fred, sec, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: None)
    with pytest.raises(ValueError, match="32 lower-case"):
        app_api.save_data_sources(cfg, {"fred_key": "short"})
    with pytest.raises(ValueError, match="email"):
        app_api.save_data_sources(cfg, {"sec_email": "not-an-email"})
    r = app_api.save_data_sources(cfg, {"fred_key": "B" * 32, "sec_email": "owner@example.com"})
    assert "FRED connected" in r["message"] and "SEC filings on" in r["message"]
    text = env.read_text()
    assert "FRED_API_KEY=" + "b" * 32 in text and "SEC_CONTACT_EMAIL=owner@example.com" in text
    assert "save-data-sources" in app_api.STDIN_ACTIONS                    # never on the command line
    status = app_api.data_sources_status(cfg)
    assert status["fred"]["has_key"] and status["sec"]["on"]
