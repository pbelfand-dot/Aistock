"""Mistakes: fine once, not twice (mistakes.py), and the team knowing today's stocks in play."""
import numpy as np
import pandas as pd

import run
from aitrader import agents, mistakes, report
from aitrader.brokers.base import Fill, Ledger, Order
from aitrader.brokers.paper import PaperBroker
from aitrader.storage import Store
from aitrader.strategies import Momentum, OpeningRangeBreakout


def day_bars(ticker="NIO", open_=3.40, last=3.55, at="09:45"):
    idx = pd.date_range(f"2026-09-30 09:30", f"2026-09-30 {at}", freq="5min")
    close = np.linspace(open_, last, len(idx))
    return {ticker: pd.DataFrame({"open": [open_] + list(close[:-1]), "high": close, "low": close, "close": close,
                                  "volume": 1e5}, index=idx)}


def test_each_buy_is_tagged_with_its_situation():
    o = Order("NIO", "BUY", 72, 3.55, "orb score 1.00")
    tags = mistakes.tags_for(o, day_bars(), {"NIO": "bearish"}, {"RIVN": 0.9}, {"NIO": 4.2}, "day")
    assert tags == ["buying NIO", "a stock under $5", "a stock in play", "in the first 30 minutes",
                    "chasing: already up 3%+ today", "moving with a stock it owns", "option bets against it"]
    calm = mistakes.tags_for(Order("F", "BUY", 1, 12.0, "x"), day_bars("F", 12.0, 12.1, "14:30"), {}, {}, {}, "day")
    assert calm == ["buying F", "a fixed-list stock", "after 2pm"]
    idx = pd.bdate_range(end="2026-09-30", periods=10)
    swing = {"XLE": pd.DataFrame({"close": [50.0] * 4 + [50, 51, 53, 55, 56, 57]}, index=idx)}
    assert "chasing: up 10%+ in 5 days" in mistakes.tags_for(Order("XLE", "BUY", 1, 57.0, "x"), swing, {}, {}, {}, "swing")


def trade(ticker, opened, closed, pnl):
    return {"ticker": ticker, "opened": opened, "closed": closed, "pnl": pnl, "return_pct": pnl,
            "strategy": "x", "entry": 10, "exit": 10, "qty": 1, "exit_reason": ""}


def test_the_same_stock_losing_again_and_again_becomes_a_lesson():
    trades = [trade("NIO", "2026-09-28", "2026-09-28", -2.0), trade("NIO", "2026-09-29", "2026-09-29", 0.5)]
    assert mistakes.find(trades, {}, {}, "2026-09-30") == []                 # twice is not yet a pattern
    trades.append(trade("NIO", "2026-09-30", "2026-09-30", -1.0))
    lesson = mistakes.find(trades, {}, {}, "2026-09-30")
    assert [m["tag"] for m in lesson] == ["buying NIO"] and "3 trades in the last 60 days, 1 won" in lesson[0]["why"]
    assert mistakes.find(trades, {}, {}, "2026-12-15") == []                # 60+ days later it has faded


def test_a_situation_that_clearly_keeps_losing_becomes_a_lesson():
    rng = np.random.default_rng(0)
    tags, trades = {}, []
    for i in range(30):
        day = f"2026-09-{i % 28 + 1:02d}"
        ticker = f"S{i}"
        chased = i % 2 == 0
        pnl = float(-1.5 + rng.normal(0, 0.3)) if chased else float(0.8 + rng.normal(0, 0.3))
        trades.append(trade(ticker, day, day, pnl))
        tags[f"{ticker}|{day}"] = [f"buying {ticker}", "a fixed-list stock"] + (["chasing: already up 3%+ today"] if chased else [])
    found = {m["tag"]: m for m in mistakes.find(trades, tags, {}, "2026-09-30")}
    assert list(found) == ["chasing: already up 3%+ today"]                  # not the fixed list as a whole
    assert "15 trades in the last 60 days, 0 won" in found["chasing: already up 3%+ today"]["why"]


def test_a_mistake_learned_once_comes_back_at_the_first_relapse():
    trades = [trade("NIO", "2026-12-20", "2026-12-20", -0.4)]               # one loss, months after the lesson
    assert mistakes.find(trades, {}, {}, "2026-12-21") == []
    back = mistakes.find(trades, {}, {"buying NIO": "2026-10-15"}, "2026-12-21")
    assert back[0]["tag"] == "buying NIO" and "lost again" in back[0]["why"]


def test_risk_skips_a_buy_that_repeats_a_mistake_but_never_a_sale():
    lessons = [{"tag": "buying NIO", "why": "3 trades, 0 won", "pnl": -5.0}]
    orders = [Order("NIO", "BUY", 10, 3.5, "orb"), Order("F", "BUY", 1, 12.0, "orb"), Order("NIO", "SELL", 5, 3.5, "exit")]
    tags = {}
    keep, notes = agents.risk(orders, {"NIO": object()}, {}, {}, 1000.0, agents.settings({}), lessons=lessons,
                              style="day", tags_out=tags)
    assert [(o.ticker, o.side) for o in keep] == [("F", "BUY"), ("NIO", "SELL")]
    assert notes[0].startswith("SKIPPED BUY NIO: that would repeat a mistake: buying NIO (3 trades, 0 won)")
    assert tags == {"F": ["buying F", "a fixed-list stock"]}                  # written down for the review
    off = agents.settings({"agents": {"learn_from_mistakes": False}})
    keep, _ = agents.risk(orders, {}, {}, {}, 1000.0, off, lessons=lessons, style="day")
    assert len(keep) == 3


def test_the_team_knows_todays_stocks_in_play(cfg, tmp_path):
    broker = PaperBroker(Ledger(500.0), 0.0, mode="study-day")
    scores = pd.Series({"HOT": 1.0, "F": 1.0})
    prices = pd.Series({"HOT": 20.0, "F": 12.0})
    orders = [Order("HOT", "BUY", 5, 20.0, "opening_range_breakout score 1.00 >= 0.6")]
    keep, team = agents.review_orders(cfg, orders, scores, prices, broker, {}, {}, OpeningRangeBreakout(), 3,
                                      lessons=[{"tag": "buying F", "why": "x", "pnl": -1}], in_play={"HOT": 4.2})
    assert team["scout"]["in_play"] == {"HOT": 4.2} and team["scout"]["wont_repeat"] == ["buying F"]
    assert "in play (4.2x its usual opening volume)" in [v for v in team["analyst"] if v.startswith("HOT")][0]
    assert team["tags"]["HOT"][:2] == ["buying HOT", "a stock in play"]


def test_lessons_carry_from_practice_into_paper_and_show_in_the_journal_and_report(cfg, tmp_path):
    store = Store(tmp_path / "aitrader.sqlite")
    for i, day in enumerate(("2026-09-28", "2026-09-29", "2026-09-30")):     # practice (in its head): 3 NIO losses
        store.record_fill("study-day", Fill(day, "NIO", "BUY", 10, 3.5, "orb score 1.00", 0.0, f"b{i}"))
        store.record_fill("study-day", Fill(day, "NIO", "SELL", 10, 3.4, "exit", -1.0, f"s{i}"))
    risk, change = run.learned(cfg, store, "day", "paper-day", "tjr_model", None, "2026-09-30")
    assert [m["tag"] for m in store.get("mistakes:day")] == ["buying NIO"]   # paper now knows it
    assert any("LEARNED: won't repeat buying NIO" in msg for _, msg in store.journal(10))
    run.learned(cfg, store, "day", "paper-day", "tjr_model", None, "2026-09-30")
    assert sum("LEARNED: won't repeat" in msg for _, msg in store.journal(20)) == 1     # said once, not every cycle
    text = "\n".join(report._desk_section(cfg, store, "day", "study", "2026-09-30"))
    assert "**Won't repeat: buying NIO**" in text
    assert "Won't repeat: buying NIO" in " ".join(agents.reviewer(cfg, store, "day", "study-day", "2026-09-30"))
