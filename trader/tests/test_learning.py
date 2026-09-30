"""The bot learns from every finished trade: it gets more careful when something loses, never bolder."""
import numpy as np
import pandas as pd

from aitrader import knowledge, learning


def fills_from(results, strategy="momentum", start="2026-01-02"):
    """One buy and one sale per trade; results are % returns."""
    rows, day = [], pd.Timestamp(start)
    for i, r in enumerate(results):
        buy, sell = 100.0, 100.0 * (1 + r / 100)
        rows.append({"mode": "paper-swing", "date": day.strftime("%Y-%m-%d"), "ticker": f"T{i % 5}", "side": "BUY",
                     "qty": 1, "price": buy, "realized_pnl": 0.0, "reason": f"{strategy} score 0.70 >= 0.56"})
        day += pd.offsets.BDay(3)
        rows.append({"mode": "paper-swing", "date": day.strftime("%Y-%m-%d"), "ticker": f"T{i % 5}", "side": "SELL",
                     "qty": 1, "price": sell, "realized_pnl": sell - buy, "reason": "momentum says exit"})
        day += pd.offsets.BDay(1)
    return pd.DataFrame(rows)


def test_finished_trades_are_matched_to_what_bought_them():
    trades = learning.round_trips(fills_from([2.0, -1.0]))
    assert [round(t["return_pct"], 2) for t in trades] == [2.0, -1.0]
    assert trades[0]["strategy"] == "momentum" and trades[0]["opened"] == "2026-01-02"


def test_a_handful_of_trades_changes_nothing():
    lessons = learning.review(fills_from([-3.0] * 8))
    assert lessons["strategies"]["momentum"]["status"] == "learning"
    assert learning.adjust(lessons, "momentum", {}) == {"size": 1.0, "no_buys": ""}


def test_a_losing_strategy_gets_half_size_then_is_paused():
    rng = np.random.default_rng(1)
    some = list(rng.normal(-0.4, 2.0, 14))
    lessons = learning.review(fills_from(some))
    assert lessons["strategies"]["momentum"]["status"] == "half size"
    assert learning.adjust(lessons, "momentum", {})["size"] == 0.5

    many = list(rng.normal(-1.0, 2.0, 40))
    lessons = learning.review(fills_from(many))
    card = lessons["strategies"]["momentum"]
    assert card["status"] == "paused" and card["trades"] == 40
    change = learning.adjust(lessons, "momentum", {})
    assert change["size"] == 0 and "paused" in change["no_buys"]


def test_a_winning_streak_never_makes_it_bolder():
    lessons = learning.review(fills_from([3.0] * 50))
    assert lessons["strategies"]["momentum"]["size"] == 1.0          # never above normal
    assert learning.adjust(lessons, "momentum", {})["size"] == 1.0


def test_a_market_condition_is_only_avoided_with_enough_evidence():
    days = pd.bdate_range("2024-01-01", "2026-06-30")
    up = np.r_[np.linspace(100, 150, 400), np.linspace(150, 110, len(days) - 400)]   # rise, then a long fall
    market = pd.DataFrame({"close": up}, index=days)
    # Trades bought while the market was below its 200-day average lost; the others won.
    rows = []
    for i, day in enumerate(days[250::6][:70]):
        below = up[days.get_loc(day)] < pd.Series(up).rolling(200).mean().iloc[days.get_loc(day)]
        r = (-1.5 if below else 3.0) + 0.3 * np.sin(i)  # wins overall, loses in a falling market
        rows.append({"date": day.strftime("%Y-%m-%d"), "ticker": f"T{i}", "side": "BUY", "qty": 1, "price": 100.0,
                     "realized_pnl": 0.0, "reason": "momentum score 0.7 >= 0.56"})
        rows.append({"date": (day + pd.offsets.BDay(2)).strftime("%Y-%m-%d"), "ticker": f"T{i}", "side": "SELL",
                     "qty": 1, "price": 100 + r, "realized_pnl": r, "reason": "exit"})
    fills = pd.DataFrame(rows).assign(mode="paper-swing")
    lessons = learning.review(fills, market)
    assert "market below its 200-day average" in lessons["avoid"]
    change = learning.adjust(lessons, "momentum", {"trend": "market below its 200-day average"})
    assert "no new buys" in change["no_buys"]
    assert learning.adjust(lessons, "momentum", {"trend": "market above its 200-day average"})["no_buys"] == ""

    few = learning.review(fills.iloc[:20], market)                   # 10 trades: not enough to conclude anything
    assert few["avoid"] == []


def test_the_local_ai_reads_what_it_learned(cfg):
    from aitrader.config import data_path
    lessons = learning.review(fills_from([1.0, -2.0, 0.5]))
    data_path(cfg, learning.NOTE).write_text(learning.note({"swing": lessons}))
    text = knowledge.pack(cfg)
    assert "What I learned from my own trades" in text and "momentum" in text


def test_losing_the_same_amount_every_time_is_clear_evidence_not_none():
    lessons = learning.review(fills_from([-1.0] * 35))
    assert lessons["strategies"]["momentum"]["t"] == -99.0 and lessons["strategies"]["momentum"]["status"] == "paused"
    import json
    json.loads(json.dumps(lessons))                                  # stays plain JSON for the app
