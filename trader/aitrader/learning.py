"""
learning.py: the bot learns from every trade it finishes.

After each trade closes, it goes into a review: which strategy bought it, how it ended, and what
the market looked like when it was bought (the S&P 500 above or below its 200-day average, calm or
wild). From all its reviews the bot keeps a scorecard per strategy and per market condition, and
adjusts itself:

  * too few trades yet            -> no change (a handful of trades is mostly luck)
  * a strategy losing so far      -> half-size positions
  * a strategy clearly losing     -> it stops opening trades (paused), and says so in the journal
  * a market condition clearly losing for this desk -> no new buys while that condition holds

It only ever becomes MORE careful, never bolder: a winning streak doesn't raise the size, because
that's how accounts blow up on luck. Every lesson is re-checked on every trade, so one that later
proves wrong goes away by itself. The lessons are also written as a note the local AI reads
(data/learned-from-my-trades.md), and shown in the app.

The price-predicting model (brain.py) keeps learning too: it re-trains on new market data on its
own schedule.
"""
import math

import pandas as pd

from .risk import shares

LEARNING_TRADES = 12        # below this, no change: too few to tell skill from luck
PAUSE_TRADES = 30           # a strategy must lose over at least this many trades to be paused
CONDITION_TRADES = 20       # a market condition needs this many trades before it can be avoided
PRIOR_TRADES = 10           # "no edge until proven": results are shrunk toward zero by this many trades
CLEARLY = -1.0              # "clearly losing": average more than 1 standard error below zero
NOTE = "learned-from-my-trades.md"


def strategy_of(reason: str) -> str:
    """BUY reasons read like 'momentum score 0.62 >= 0.56'."""
    return str(reason).split(" score ")[0].strip() or "unknown"


def round_trips(fills: pd.DataFrame) -> list:
    """Finished trades (a sale, or part of one, matched to what bought it), oldest first."""
    open_lots, trades = {}, []
    for row in fills.itertuples(index=False):
        if row.side == "BUY":
            lot = open_lots.get(row.ticker)
            if lot:
                total = lot["qty"] + row.qty
                lot["price"] = (lot["price"] * lot["qty"] + row.price * row.qty) / total
                lot["qty"] = total
            else:
                open_lots[row.ticker] = {"opened": str(row.date)[:10], "price": float(row.price), "qty": shares(float(row.qty)),
                                         "strategy": strategy_of(row.reason)}
        elif row.ticker in open_lots:
            lot = open_lots[row.ticker]
            qty = shares(min(float(row.qty), lot["qty"]))
            trades.append({"ticker": row.ticker, "strategy": lot["strategy"], "opened": lot["opened"],
                           "closed": str(row.date)[:10], "qty": qty, "entry": lot["price"], "exit": float(row.price),
                           "return_pct": (float(row.price) / lot["price"] - 1) * 100,
                           "pnl": float(row.realized_pnl), "exit_reason": str(row.reason)})
            lot["qty"] -= qty
            if lot["qty"] <= 0:
                del open_lots[row.ticker]
    return trades


def conditions(market: pd.DataFrame) -> pd.DataFrame:
    """For each day: was the market (the benchmark) trending up, and was it calm or wild?"""
    close = market["close"] if isinstance(market, pd.DataFrame) else market
    close = close.groupby(pd.DatetimeIndex(close.index).normalize()).last()
    vol = close.pct_change().rolling(20).std()
    return pd.DataFrame({
        "trend": (close > close.rolling(200).mean()).map({True: "market above its 200-day average",
                                                          False: "market below its 200-day average"}),
        "mood": (vol > vol.rolling(250, min_periods=60).median()).map({True: "wild market (high volatility)",
                                                                       False: "calm market (low volatility)"}),
    }).where(close.rolling(200).count() >= 200)


def _card(returns: list) -> dict:
    n = len(returns)
    mean = sum(returns) / n if n else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / (n - 1)) if n > 1 else 0.0
    return {"trades": n, "win_rate": round(100 * sum(r > 0 for r in returns) / n, 1) if n else None,
            "avg_return_pct": round(mean, 2), "shrunk_pct": round(sum(returns) / (n + PRIOR_TRADES), 3),
            "t": _t_stat(mean, sd, n)}


def _t_stat(mean: float, sd: float, n: int) -> float:
    """How many standard errors the average is from zero. Identical results every time (no spread) are
    the clearest evidence there is, not "no evidence": capped at +/-99 so it stays plain JSON."""
    if n < 2:
        return 0.0
    if sd < 1e-9:
        return 0.0 if abs(mean) < 1e-12 else math.copysign(99.0, mean)
    return round(max(-99.0, min(99.0, mean / (sd / math.sqrt(n)))), 2)


def review(fills: pd.DataFrame, market: pd.DataFrame = None) -> dict:
    """The scorecards and what to change because of them."""
    trades = round_trips(fills)
    marks = conditions(market) if market is not None and len(market) else None
    for t in trades:
        day = pd.Timestamp(t["opened"])
        row = marks.loc[:day].iloc[-1] if marks is not None and len(marks.loc[:day]) else None
        t["trend"] = row["trend"] if row is not None and isinstance(row["trend"], str) else None
        t["mood"] = row["mood"] if row is not None and isinstance(row["mood"], str) else None

    strategies = {}
    for name in sorted({t["strategy"] for t in trades}):
        card = _card([t["return_pct"] for t in trades if t["strategy"] == name])
        if card["trades"] >= PAUSE_TRADES and card["avg_return_pct"] < 0 and card["t"] <= CLEARLY:
            card.update(status="paused", size=0.0,
                        why=f"lost over {card['trades']} trades (average {card['avg_return_pct']:+.2f}%)")
        elif card["trades"] >= LEARNING_TRADES and card["shrunk_pct"] < 0:
            card.update(status="half size", size=0.5,
                        why=f"losing so far over {card['trades']} trades (average {card['avg_return_pct']:+.2f}%)")
        else:
            card.update(status="learning" if card["trades"] < LEARNING_TRADES else "normal", size=1.0,
                        why=f"{card['trades']} trades so far" if card["trades"] < LEARNING_TRADES
                        else f"not losing over {card['trades']} trades")
        strategies[name] = card

    avoid, by_condition = [], {}
    overall = _card([t["return_pct"] for t in trades])["avg_return_pct"] if trades else 0.0
    for key in ("trend", "mood"):
        for value in sorted({t[key] for t in trades if t[key]}):
            card = _card([t["return_pct"] for t in trades if t[key] == value])
            by_condition[value] = card
            if (card["trades"] >= CONDITION_TRADES and card["avg_return_pct"] < 0 and card["t"] <= CLEARLY
                    and card["avg_return_pct"] < overall):
                avoid.append(value)
    return {"trades": len(trades), "strategies": strategies, "conditions": by_condition, "avoid": avoid,
            "recent": trades[-10:]}


def adjust(lessons: dict, strategy_name: str, today_condition: dict) -> dict:
    """What this cycle should do differently: {"size": 0.5-1.0 or 0, "no_buys": reason or ""}."""
    card = lessons["strategies"].get(strategy_name)
    size = card["size"] if card else 1.0
    if size == 0:
        return {"size": 0.0, "no_buys": f"{strategy_name} is paused: it {card['why']}"}
    for value in (today_condition or {}).values():
        if value in lessons["avoid"]:
            return {"size": size, "no_buys": f"its trades in a {value} have clearly lost money, so no new buys today"}
    return {"size": size, "no_buys": ""}


def today_condition(market: pd.DataFrame) -> dict:
    if market is None or not len(market):
        return {}
    row = conditions(market).iloc[-1]
    return {k: v for k, v in row.items() if isinstance(v, str)}


def note(desks: dict) -> str:
    """The lessons in plain English, for the local AI and the app."""
    lines = ["# What I learned from my own trades", "",
             "Updated after every finished trade. Too few trades = no conclusions; lessons only ever make "
             "me more careful.", ""]
    for desk, lessons in desks.items():
        lines.append(f"## {desk.capitalize()} desk: {lessons['trades']} finished trades")
        if not lessons["trades"]:
            lines.append("- No finished trades yet.")
        for name, c in lessons["strategies"].items():
            lines.append(f"- **{name}**: {c['trades']} trades, {c['win_rate']}% winners, average "
                         f"{c['avg_return_pct']:+.2f}% per trade. Status: {c['status']} ({c['why']}).")
        for value, c in lessons["conditions"].items():
            lines.append(f"- In a {value}: {c['trades']} trades, average {c['avg_return_pct']:+.2f}%.")
        for value in lessons["avoid"]:
            lines.append(f"- **Avoiding new buys in a {value}** (clearly losing there).")
        from .mistakes import note_lines
        lines += note_lines(lessons.get("mistakes") or [])
        lines.append("")
    return "\n".join(lines)
