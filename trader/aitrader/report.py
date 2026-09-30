"""
report.py: what the bot traded and how it did, the same way for all three accounts:

  study   trading "in its head" while a desk studies (pretend money, simulated on this Mac)
  paper   paper trading (pretend money)
  live    real money

For each account: every trade (what it bought, what it spent, what it got back, the gain or loss in
dollars and percent, win or lose), each day's value and change, and the overall totals.
"""
import pandas as pd

MODES = ("study", "paper", "live")
LABELS = {"study": "In its head (while studying)", "paper": "Paper (practice money)", "live": "Real money"}


def _r(x, digits=2):
    return None if x is None or pd.isna(x) else round(float(x), digits)


def trades(fills: pd.DataFrame, desk: str = "") -> list:
    """Finished trades, newest first: each sale matched to what was paid for those shares."""
    lots, out = {}, []
    for f in fills.itertuples(index=False):
        qty, price = int(f.qty), float(f.price)
        if f.side == "BUY":
            lot = lots.setdefault(f.ticker, {"qty": 0, "cost": 0.0, "opened": str(f.date)[:10], "why": str(f.reason)})
            lot["qty"] += qty
            lot["cost"] += qty * price
            continue
        lot = lots.get(f.ticker)
        if not lot or lot["qty"] <= 0:
            continue
        sold = min(qty, lot["qty"])
        avg = lot["cost"] / lot["qty"]
        spent, got = sold * avg, sold * price
        pnl = float(f.realized_pnl) if f.realized_pnl is not None and not pd.isna(f.realized_pnl) else got - spent
        out.append({"desk": desk, "ticker": f.ticker, "qty": sold, "bought_on": lot["opened"],
                    "sold_on": str(f.date)[:10], "buy_price": _r(avg), "sell_price": _r(price),
                    "spent": _r(spent), "got_back": _r(got), "gain": _r(pnl),
                    "gain_pct": _r(pnl / spent * 100) if spent else None,
                    "result": "win" if pnl > 0 else "loss" if pnl < 0 else "even",
                    "days_held": int((pd.Timestamp(str(f.date)[:10]) - pd.Timestamp(lot["opened"])).days),
                    "why_bought": lot["why"], "why_sold": str(f.reason)})
        lot["cost"] -= sold * avg
        lot["qty"] -= sold
        if lot["qty"] <= 0:
            del lots[f.ticker]
    return out[::-1]


def daily(curve: pd.Series, start_value: float = None) -> list:
    """Each day's value and change (newest first). The first day compares with the starting money."""
    rows, prev = [], start_value
    for day, value in curve.dropna().items():
        change = value - prev if prev else None
        rows.append({"date": pd.Timestamp(day).strftime("%Y-%m-%d"), "value": _r(value), "change": _r(change),
                     "change_pct": _r(change / prev * 100) if prev else None})
        prev = value
    return rows[::-1]


def totals(done: list, open_positions: list, start_value: float, value_now: float,
           benchmark_return_pct: float = None, days: int = 0) -> dict:
    """The overall numbers: money in, money out, gains, wins and losses."""
    wins = [t for t in done if t["result"] == "win"]
    losses = [t for t in done if t["result"] == "loss"]
    realized = sum(t["gain"] or 0 for t in done)
    unrealized = sum(p.get("gain") or 0 for p in open_positions)
    total_return = (value_now / start_value - 1) * 100 if start_value and value_now is not None else None
    best = max(done, key=lambda t: t["gain_pct"] or 0) if done else None
    worst = min(done, key=lambda t: t["gain_pct"] or 0) if done else None
    return {
        "start_value": _r(start_value), "value_now": _r(value_now), "days": days,
        "gain": _r(value_now - start_value) if start_value and value_now is not None else None,
        "return_pct": _r(total_return),
        "benchmark_return_pct": _r(benchmark_return_pct),
        "beat_benchmark": (total_return > benchmark_return_pct
                           if total_return is not None and benchmark_return_pct is not None else None),
        "trades_closed": len(done), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": _r(len(wins) / len(done) * 100, 1) if done else None,
        "spent_total": _r(sum(t["spent"] or 0 for t in done) + sum(p.get("spent") or 0 for p in open_positions)),
        "realized_gain": _r(realized), "unrealized_gain": _r(unrealized),
        "avg_win_pct": _r(sum(t["gain_pct"] for t in wins) / len(wins)) if wins else None,
        "avg_loss_pct": _r(sum(t["gain_pct"] for t in losses) / len(losses)) if losses else None,
        "best": {"ticker": best["ticker"], "gain_pct": best["gain_pct"], "gain": best["gain"]} if best else None,
        "worst": {"ticker": worst["ticker"], "gain_pct": worst["gain_pct"], "gain": worst["gain"]} if worst else None,
        "open_positions": len(open_positions),
    }


def day_line(store, mode: str, start_value: float, today: str) -> str:
    """One line for the journal after the close: today's result and the running totals."""
    curve = store.equity_curve(mode)
    if not len(curve) or curve.index[-1].strftime("%Y-%m-%d") != today:      # didn't trade today
        return ""
    value = float(curve.iloc[-1])
    before = curve[curve.index < pd.Timestamp(today)]
    prev = float(before.iloc[-1]) if len(before) else start_value
    done = trades(store.fills(mode))
    todays = [t for t in done if t["sold_on"] == today]
    won = sum(1 for t in done if t["result"] == "win")
    text = (f"[{mode}] {today}: value ${value:,.2f}, today {(value / prev - 1) * 100:+.2f}% "
            f"(${value - prev:+,.2f}); since the start {(value / start_value - 1) * 100:+.2f}% "
            f"(${value - start_value:+,.2f}); {len(done)} trades finished, {won} won, {len(done) - won} didn't")
    if todays:
        text += "; today: " + ", ".join(f"{t['ticker']} {t['gain_pct']:+.1f}% (${t['gain']:+,.2f})" for t in todays)
    return text
