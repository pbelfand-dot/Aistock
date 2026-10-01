"""
mistakes.py: making a mistake is fine; making the same one again isn't.

Every buy is written down with the situation it was made in (its tags):
  - the stock itself ("buying NIO")
  - day desk: a stock in play, or one from the fixed list; bought in the first 30 minutes, or after 2pm
  - a stock under $5 a share (wide spreads, jumpy)
  - chasing: day desk, already up 3%+ since today's open; swing desk, up 10%+ in 5 days
  - it moves with a stock the desk already owns; option bets are leaning against it

After trades finish, a situation whose recent trades keep losing becomes a lesson, and the Risk agent
skips new buys in that same situation (it says so in its note and in the journal):
  - the same stock:  3+ trades in the last 60 days, at most 1 of them won, and losing money overall
  - any situation:   8+ trades in the last 60 days, losing on average, worse than the desk's other
                     trades, and clearly (at least 1 standard error below zero, not just bad luck)
  - a relapse:       a lesson it learned before, that lost AGAIN after the lesson had faded, comes back
                     at once (no need to lose 3 or 8 more times)

Only the last 60 days count, so a lesson fades unless it's confirmed again; a fixed rule would stop the
bot from ever finding out that things changed. Lessons only ever make it more careful (skip a buy),
never bolder, and never touch a sale. They come from every account the desk has traded (in its head,
paper, real), so a mistake made while practicing isn't repeated with paper or real money.
"""
from datetime import datetime, timedelta

import pandas as pd

WINDOW_DAYS = 60             # only recent trades count: a lesson fades unless confirmed again
STOCK_TRADES = 3             # the same stock: this many trades ...
STOCK_MAX_WINS = 1           # ... with at most this many wins, and losing money
SITUATION_TRADES = 8         # any other situation: this many trades, clearly losing
CLEARLY = -1.0
KINDS = ("study", "paper", "live")


# ------------------------------------------------------------------ tags: the situation of a buy
def tags_for(order, bars: dict, gaps: dict, moves_with: dict, in_play: dict, style: str) -> list:
    """The situation this buy is made in, as plain-English tags."""
    tags = [f"buying {order.ticker}"]
    df = bars.get(order.ticker)
    price = float(order.price)
    if price < 5:
        tags.append("a stock under $5")
    if style == "day":
        tags.append("a stock in play" if order.ticker in (in_play or {}) else "a fixed-list stock")
        if df is not None and len(df):
            when = df.index[-1]
            if when.hour * 60 + when.minute < 600:
                tags.append("in the first 30 minutes")
            elif when.hour >= 14:
                tags.append("after 2pm")
            today = df[df.index.normalize() == when.normalize()]
            if len(today) and price >= float(today["open"].iloc[0]) * 1.03:
                tags.append("chasing: already up 3%+ today")
    elif df is not None and len(df) > 5 and price >= float(df["close"].iloc[-6]) * 1.10:
        tags.append("chasing: up 10%+ in 5 days")
    if moves_with:
        tags.append("moving with a stock it owns")
    if gaps.get(order.ticker) == "bearish":
        tags.append("option bets against it")
    return tags


def remember_tags(store, desk: str, today: str, tags_by_ticker: dict):
    """Writes down the situation of each buy (kept 120 days), for the review after it finishes."""
    if not tags_by_ticker:
        return
    saved = store.get(f"entry_tags:{desk}") or {}
    for ticker, tags in tags_by_ticker.items():
        saved[f"{ticker}|{today}"] = tags
    oldest = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")
    store.set(f"entry_tags:{desk}", {k: v for k, v in saved.items() if k.split("|")[1] >= oldest})


# ------------------------------------------------------------------ finding the repeated mistakes
def desk_trades(store, desk: str) -> list:
    """Finished trades from every account this desk has traded (in its head, paper, real)."""
    from .learning import round_trips
    out = []
    for kind in KINDS:
        fills = store.fills(f"{kind}-{desk}")
        if fills is not None and len(fills):
            out += [{**t, "account": kind} for t in round_trips(fills)]
    return out


def find(trades: list, tags: dict, remembered: dict, today: str) -> list:
    """The situations to stop buying in: [{"tag", "trades", "won", "pnl", "why"}], worst first."""
    from .learning import _card
    start = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    recent = [t for t in trades if t["closed"] >= start]
    by_tag = {}
    for t in recent:
        for tag in tags.get(f"{t['ticker']}|{t['opened']}") or [f"buying {t['ticker']}"]:
            by_tag.setdefault(tag, []).append(t)
    overall = _card([t["return_pct"] for t in recent])["avg_return_pct"] if recent else 0.0
    lessons = []
    for tag, ts in by_tag.items():
        card = _card([t["return_pct"] for t in ts])
        won, pnl = sum(t["pnl"] > 0 for t in ts), round(sum(t["pnl"] for t in ts), 2)
        since = remembered.get(tag)
        relapse = [t for t in ts if since and t["closed"] > since and t["pnl"] < 0]
        if relapse:
            why = f"lost again ({relapse[-1]['ticker']} on {relapse[-1]['closed']}) after it had learned this once"
        elif tag.startswith("buying ") and len(ts) >= STOCK_TRADES and won <= STOCK_MAX_WINS and pnl < 0:
            why = f"{len(ts)} trades in the last {WINDOW_DAYS} days, {won} won, {'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"
        elif (not tag.startswith("buying ") and card["trades"] >= SITUATION_TRADES and card["avg_return_pct"] < 0
              and card["avg_return_pct"] < overall and card["t"] <= CLEARLY):
            why = (f"{card['trades']} trades in the last {WINDOW_DAYS} days, {won} won, average "
                   f"{card['avg_return_pct']:+.2f}% per trade (the desk's other trades: {overall:+.2f}%)")
        else:
            continue
        lessons.append({"tag": tag, "trades": len(ts), "won": int(won), "pnl": pnl, "why": why})
    return sorted(lessons, key=lambda m: m["pnl"])


def review(store, desk: str, today: str) -> list:
    """Finds this desk's repeated mistakes, remembers them (for relapses) and saves them for the Risk agent.
    Returns the lessons that are NEW since the last review (for the journal)."""
    remembered = store.get(f"mistakes_remembered:{desk}") or {}
    lessons = find(desk_trades(store, desk), store.get(f"entry_tags:{desk}") or {}, remembered, today)
    before = {m["tag"] for m in store.get(f"mistakes:{desk}") or []}
    for m in lessons:
        remembered[m["tag"]] = today
    store.set(f"mistakes_remembered:{desk}", remembered)
    store.set(f"mistakes:{desk}", lessons)
    return [m for m in lessons if m["tag"] not in before]


def matching(tags: list, lessons: list):
    """The first lesson this buy would repeat, or None."""
    avoid = {m["tag"]: m for m in lessons or []}
    return next((avoid[t] for t in tags if t in avoid), None)


def note_lines(lessons: list) -> list:
    return [f"- **Won't repeat: {m['tag']}** ({m['why']})" for m in lessons]
