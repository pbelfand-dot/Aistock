"""The team of agents (agents.py) and the options-gap watcher (options_flow.py)."""
from datetime import datetime

import numpy as np
import pandas as pd

import run
from aitrader import agents, options_flow, report
from aitrader.brokers.base import Ledger, Order
from aitrader.brokers.paper import PaperBroker
from aitrader.storage import Store
from aitrader.strategies import Momentum

DAYS = pd.bdate_range("2026-08-03", periods=40)


def closes(path):
    return pd.Series(path, index=DAYS[:len(path)], dtype=float)


# ---------------------------------------------------------------- the options-gap watcher
def test_a_gap_is_when_the_bets_and_the_price_disagree():
    s = options_flow.settings({})
    assert options_flow.classify(0.80, None, 0.2, s) == "bullish"          # heavy calls, flat price
    assert options_flow.classify(0.80, None, 4.0, s) == ""                 # heavy calls, price already up: agree
    assert options_flow.classify(0.30, None, 0.5, s) == "bearish"          # heavy puts, price holding up
    assert options_flow.classify(0.30, None, -3.0, s) == ""                # heavy puts, price already falling
    assert options_flow.classify(0.70, 0.55, 0.0, s) == "bullish"          # unusual vs ITS OWN normal (55%)
    assert options_flow.classify(0.70, 0.66, 0.0, s) == ""                 # normal for this stock
    assert options_flow.option_type("NVDA251017C00195000") == "C" and options_flow.option_type("SPY251017P00570000") == "P"


def test_it_reads_todays_volume_from_alpacas_free_option_chain():
    pages = [
        {"snapshots": {"AAA261016C00050000": {"dailyBar": {"t": "2026-09-30T04:00:00Z", "v": 900}},
                       "AAA261016P00050000": {"dailyBar": {"t": "2026-09-30T04:00:00Z", "v": 100}},
                       "AAA261016C00055000": {"dailyBar": {"t": "2026-09-29T04:00:00Z", "v": 5000}}},  # yesterday's
         "next_page_token": "p2"},
        {"snapshots": {"AAA261023P00045000": {"dailyBar": {"t": "2026-09-30T04:00:00Z", "v": 250}},
                       "AAA261023C00060000": {}}}]
    asked = []

    class Session:
        def get(self, url, params, timeout, headers):
            asked.append(dict(params))
            body = pages[len(asked) - 1]
            return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()
    cfg = {"secrets": {"alpaca_paper_key": "k", "alpaca_paper_secret": "s", "alpaca_live_key": "", "alpaca_live_secret": ""}}
    assert options_flow.fetch_volume(cfg, "AAA", "2026-09-30", session=Session()) == (900, 350)
    assert asked[0]["feed"] == "indicative" and asked[0]["expiration_date_lte"] == "2026-11-14"
    assert asked[1]["page_token"] == "p2"


def test_gaps_are_flagged_graded_against_the_market_and_scored(cfg, tmp_path, monkeypatch):
    from aitrader import scanner
    monkeypatch.setattr(scanner, "trade_candidates", lambda cfg: [])
    cfg["desks"]["swing"]["watchlist"], cfg["desks"]["day"]["watchlist"] = ["AAA", "BBB"], []
    store = Store(tmp_path / "aitrader.sqlite")
    share = {"AAA": 0.55, "BBB": 0.55}
    fetch = lambda cfg, symbol, day: (int(share[symbol] * 10000), int((1 - share[symbol]) * 10000))
    flat, rising = [100.0] * 40, [100.0 + i for i in range(40)]
    prices = {"AAA": closes(flat[:30] + [100, 101, 102, 104, 106, 108, 110, 111, 112, 113]),
              "BBB": closes(flat), cfg["benchmark"]: closes(flat)}
    for i in range(20, 30):                                            # ten normal days: 55% calls
        day = DAYS[i].strftime("%Y-%m-%d")
        options_flow.observe(cfg, store, day, {k: v[:i + 1] for k, v in prices.items()}, fetch=fetch)
    assert options_flow.gaps_today(store) == {}

    share["AAA"] = 0.80                                                # calls pile up; the price hasn't moved
    day = DAYS[29].strftime("%Y-%m-%d")
    out = options_flow.observe(cfg, store, day, {k: v[:30] for k, v in prices.items()}, fetch=fetch)
    assert [f["symbol"] for f in out["flags"]] == ["AAA"] and out["flags"][0]["direction"] == "bullish"
    assert out["flags"][0]["baseline"] == 0.55 and options_flow.gaps_today(store) == {"AAA": "bullish"}

    share["AAA"] = 0.55
    for i in range(30, 36):                                            # the price follows the bets
        options_flow.observe(cfg, store, DAYS[i].strftime("%Y-%m-%d"), {k: v[:i + 1] for k, v in prices.items()},
                             fetch=fetch)
    graded = [x for x in store.get(options_flow.SIGNALS_KEY) if x["symbol"] == "AAA"][0]
    assert graded["right"] is True and graded["excess_pct"] == 6.0            # 100 -> 106 while SPY stayed flat
    card = options_flow.scorecard(store)
    assert card["bullish"]["graded"] == 1 and card["bullish"]["right_pct"] == 100.0
    assert card["bullish"]["edge"] is False                               # one call proves nothing (needs 20+)
    lines = "\n".join(options_flow.report_lines(store))
    assert "testing only" in lines and "Bullish gaps so far: 1 graded, right 100.0%" in lines


def test_the_daily_job_needs_keys_and_never_stops_the_day(cfg, tmp_path, monkeypatch):
    store = Store(tmp_path / "aitrader.sqlite")
    assert "needs Alpaca keys" in options_flow.run(cfg, store, None, "2026-09-30")
    cfg["secrets"].update(alpaca_paper_key="PK123", alpaca_paper_secret="s" * 30)

    class Broken:
        def history(self, symbol, interval):
            raise OSError("offline")
    monkeypatch.setattr(options_flow, "observe", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "failed" in options_flow.run(cfg, store, Broken(), "2026-09-30")
    assert any("couldn't run today" in m for _, m in store.journal(5))
    assert "options" in run.due_jobs(datetime(2026, 9, 30, 16, 15), set())
    assert "options" not in run.due_jobs(datetime(2026, 9, 30, 16, 15), {"options:2026-09-30"})
    assert "options" not in run.due_jobs(datetime(2026, 9, 30, 15, 0), set())


# ---------------------------------------------------------------- the team
def _bars(paths: dict) -> dict:
    idx = pd.bdate_range("2026-06-01", periods=len(next(iter(paths.values()))))
    return {t: pd.DataFrame({"close": p, "open": p, "high": p, "low": p, "volume": 1e6}, index=idx) for t, p in paths.items()}


def test_risk_warns_about_stocks_that_move_together_and_only_skips_when_you_allow_it():
    rng = np.random.default_rng(3)
    base = 100 + np.cumsum(rng.normal(0, 1, 80))
    twin = base * 1.001 + rng.normal(0, 0.05, 80)                      # moves with OWN
    other = 100 + np.cumsum(rng.normal(0, 1, 80))
    bars = _bars({"OWN": base, "TWIN": twin, "OTHER": other})
    positions = {"OWN": object()}
    buys = [Order("TWIN", "BUY", 1, 100.0, "momentum score 0.95"), Order("OTHER", "BUY", 1, 100.0, "momentum score 0.9"),
            Order("OWN", "SELL", 1, 100.0, "exit")]
    notes_only = agents.settings({})
    keep, notes = agents.risk(buys, positions, bars, {"OTHER": "bearish"}, 1000.0, notes_only)
    assert [o.ticker for o in keep] == ["TWIN", "OTHER", "OWN"]           # warns, doesn't block (the default)
    assert "moves with OWN" in notes[0] and "(noted only)" in notes[0]
    assert "puts are piling up against it" in notes[1]

    strict = agents.settings({"agents": {"risk_vetoes": ["correlation", "options_gap", "made-up"]}})
    assert strict["risk_vetoes"] == ["correlation", "options_gap"]
    keep, notes = agents.risk(buys, positions, bars, {"OTHER": "bearish"}, 1000.0, strict)
    assert [o.ticker for o in keep] == ["OWN"]                            # sells always go through
    assert notes[0].startswith("SKIPPED BUY TWIN: it moves with what we already own")
    assert notes[1].startswith("SKIPPED BUY OTHER: option bets lean against it")


def test_the_team_writes_a_note_at_each_step_of_a_decision(cfg, tmp_path):
    store = Store(tmp_path / "aitrader.sqlite")
    store.set("options_gap_today", {"date": "2026-09-30", "looked": 3, "flags": [
        {"symbol": "AAA", "direction": "bullish"}, {"symbol": "CCC", "direction": "bearish"}]})
    broker = PaperBroker(Ledger(500.0), 0.0, mode="paper-swing")
    scores = pd.Series({"AAA": 0.95, "BBB": 0.9, "CCC": 0.6, "DDD": 0.1})
    prices = pd.Series({"AAA": 10.0, "BBB": 20.0, "CCC": 30.0, "DDD": 40.0})
    orders = [Order("AAA", "BUY", 5, 10.0, "momentum score 0.95 >= 0.8")]
    keep, team = agents.review_orders(cfg, orders, scores, prices, broker, {}, options_flow.gaps_today(store),
                                      Momentum(), 8)
    assert keep == orders
    assert team["scout"]["top"][0] == ["AAA", 0.95] and team["scout"]["options_gaps"] == {"AAA": "bullish", "CCC": "bearish"}
    assert team["analyst"][0] == "AAA 0.95: strong; option bets agree (calls heavy)"
    assert team["trader"] == ["BUY 5 AAA @ $10.00: momentum score 0.95 >= 0.8"]
    assert team["risk"] == ["OK BUY AAA: 10% of the desk"]


def test_the_report_shows_the_team_and_the_watcher(cfg, tmp_path, monkeypatch):
    from test_in_its_head import FakeData
    monkeypatch.setattr(run, "MarketData", FakeData)
    store = Store(tmp_path / "aitrader.sqlite")
    data = FakeData()
    days = FakeData.intraday[1].index.normalize().unique()
    for bar_time in FakeData.intraday[1].index[FakeData.intraday[1].index.normalize() == days[0]]:
        now = bar_time.to_pydatetime()
        FakeData.now = now
        run.trade_desk(cfg, store, data, "day", now)
    thinking = store.get("study-day_thinking")
    assert set(thinking["team"]) == {"scout", "analyst", "trader", "risk"}
    text = report.after_market(cfg, store, days[0].strftime("%Y-%m-%d"))
    assert "**The team (the last decision, then the day):**" in text
    for role in ("Scout", "Analyst", "Trader", "Risk", "Reviewer"):
        assert f"- {role}: " in text
    assert "## Options-gap watcher (testing only: it never trades on this)" in text


def test_a_team_problem_never_blocks_a_trade(cfg, tmp_path, monkeypatch):
    from aitrader.engine import run_cycle
    from aitrader.risk import RiskManager
    from aitrader.strategies import Strategy
    from test_lifecycle import FakeData

    class Always(Strategy):                                                # wants to buy everything
        name, style, buy_above, sell_below = "always", "swing", 0.5, 0.1

        def scores(self, bars, market, since=None):
            return pd.DataFrame({t: 1.0 for t in bars}, index=market.index)
    monkeypatch.setattr(agents, "review_orders", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad data")))
    store = Store(tmp_path / "aitrader.sqlite")
    broker = PaperBroker(Ledger(500.0), 0.0, mode="paper-swing")
    bars, market = FakeData.daily
    now = market.index[-1].to_pydatetime().replace(hour=15, minute=45)
    run_cycle(store, broker, Always(), RiskManager(max_open_positions=2, max_position_pct=40), bars, market, now,
              cfg["desks"]["swing"], cfg=cfg)
    assert broker.positions()                                              # the orders went ahead
    assert "couldn't write its notes" in store.get("paper-swing_thinking")["team"]["error"]
