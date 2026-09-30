"""
tjr_daily.py: does TJR's model (sweep -> break of structure -> fair value gap) work on daily charts?

    python research/history/tjr_daily.py OUT_DIR BUNDLE_DIR [BUNDLE_DIR ...]

BUNDLE_DIR = an unpacked market research bundle (it has bundle/data/equities/*.csv): daily
prices 2010-2026. The rules are research/tjr/RULES.md, on daily bars:
  1. a confirmed swing low (a "liquidity" level) gets swept: price trades below it,
  2. break of structure: within N bars a close above the high of the leg that came down into it,
  3. entry: price comes back into the latest bullish fair value gap of that move (limit order),
  4. stop just below the sweep's extreme; target the next swing high above (the opposite
     liquidity) if it pays at least 2x the risk, or a fixed 2x the risk (both are tested).
The bot only buys (it never shorts), so the LONG side decides; the short side is shown for insight.

Honesty checks built in:
  - no peeking: a swing point only counts once the k bars after it exist; targets and levels only
    use what was known at the time; fills are at the order price or the (worse) opening price;
  - costs: 0.10% per round trip; if the stop and the target are both touched on one day, it's a loss;
  - a PLACEBO: random buy days with the same stop sizes and targets. Stocks mostly rose in
    2010-2026, so any buy rule can look good; the setup only matters if it beats the placebo;
  - a $1,000 account with the rulebook's risk rules (1% risk per trade, at most 2 new trades a day,
    fractional shares) against simply holding SPY.
Caveat: the stock list is today's (companies that survived), which flatters buying; the placebo
has the same flattery, so the comparison between them is fair.
"""
import sys
from bisect import bisect_left, bisect_right
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

COST = 0.001          # round trip, as a fraction of the entry price
BUFFER = 0.001        # stop this far beyond the sweep's extreme
N_BOS = 12            # bars allowed between the sweep and the break of structure
M_FILL = 24           # bars the gap stays valid for the entry order
MAX_HOLD = 60         # bars: exit at the close if neither stop nor target is hit
MIN_GAP = 0.0005      # ignore gaps smaller than 0.05% of price
LOOKBACK = 120        # bars: how old a swing level may be and still count
MIN_RR = 2.0


# ------------------------------------------------------------------ data
def load(bundles) -> dict:
    """Adjusted daily bars (splits and dividends) per symbol."""
    out = {}
    for b in bundles:
        for f in sorted(Path(b).glob("bundle/data/equities/*.csv")):
            df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
            if len(df) < 300:
                continue
            factor = df["adj_close"] / df["close"]
            out[f.stem] = pd.DataFrame({"open": df["open"] * factor, "high": df["high"] * factor,
                                        "low": df["low"] * factor, "close": df["adj_close"]}).dropna()
    return out


def pivots(high, low, k):
    """Swing highs/lows: the extreme of the k bars on each side (known only k bars later).
    Returns the bar numbers of each, in order."""
    n = len(high)
    ph, pl = np.zeros(n, bool), np.zeros(n, bool)
    hw, lw = sliding_window_view(high, 2 * k + 1), sliding_window_view(low, 2 * k + 1)
    before_h, before_l = sliding_window_view(high[:-1], k), sliding_window_view(low[:-1], k)
    mid = np.arange(k, n - k)
    ph[mid] = (high[mid] == hw.max(axis=1)) & (before_h[:len(mid)].max(axis=1) < high[mid])
    pl[mid] = (low[mid] == lw.min(axis=1)) & (before_l[:len(mid)].min(axis=1) > low[mid])
    return np.flatnonzero(ph), np.flatnonzero(pl)


# ------------------------------------------------------------------ one stock, one direction
def setups(df: pd.DataFrame, k: int, target_mode: str, side: str) -> list:
    """Every trade the rules would have taken on this stock. side 'long' or 'short' (mirrored)."""
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    if side == "short":                        # mirror the prices; the logic below is for longs
        o, h, l, c = -o, -l, -h, -c
    ph, pl = pivots(h, l, k)
    dates, n = df.index, len(c)
    trades, t = [], k + 1
    swept = set()
    while t < n - 2:
        # 1) a sweep: today's low goes below a swing low that was already confirmed (bar <= t-k-1)
        a, b = bisect_left(pl, t - LOOKBACK), bisect_left(pl, t - k)
        levels = [i for i in pl[a:b] if i not in swept and l[t] < l[i]]
        if not levels:
            t += 1
            continue
        lvl = max(levels)                                        # the most recent level taken out
        swept.update(levels)
        # the last swing high before the sweep (known by then), else the high of the leg down
        a, b = bisect_right(ph, lvl), bisect_left(ph, t - k)
        if b > a:
            ref = h[ph[b - 1]]
        elif t > lvl + 1:
            ref = h[lvl + 1:t].max()
        else:
            t += 1
            continue
        extreme, bos = l[t], None
        for u in range(t, min(n, t + N_BOS + 1)):               # 2) break of structure
            extreme = min(extreme, l[u])
            if c[u] > ref:
                bos = u
                break
        if bos is None:
            t += 1
            continue
        gap = None                                               # 3) latest bullish fair value gap of the move
        for j in range(bos, t + 1, -1):
            if h[j - 2] < l[j] and (l[j] - h[j - 2]) / abs(c[j]) >= MIN_GAP:
                gap = (h[j - 2], l[j])
                break
        if gap is None:
            t = bos + 1
            continue
        bottom, top = gap
        stop = extreme - abs(extreme) * BUFFER
        risk = top - stop
        if risk <= 0:
            t = bos + 1
            continue
        if target_mode == "liquidity":                           # next confirmed swing high above
            a, b = bisect_left(ph, bos - 250), bisect_left(ph, bos - k)
            above = [h[i] for i in ph[a:b] if h[i] >= top + MIN_RR * risk]
            if not above:
                t = bos + 1
                continue
            target = min(above)
        else:
            target = top + MIN_RR * risk
        entry_bar = None                                         # the limit order waits in the gap
        for u in range(bos + 1, min(n, bos + 1 + M_FILL)):
            if h[u] >= target and l[u] > top:                    # ran to target without us
                break
            if l[u] <= top:
                entry_bar, entry = u, min(o[u], top)
                break
            if c[u] < bottom:                                    # the gap failed
                break
        if entry_bar is None or entry <= stop:
            t = bos + 1
            continue
        exit_bar, exit_price, why = None, None, None             # 4) manage the trade
        if l[entry_bar] <= stop:                                 # same day through the stop: a loss
            exit_bar, exit_price, why = entry_bar, stop, "stop"
        for u in range(entry_bar + 1, min(n, entry_bar + MAX_HOLD + 1)):
            if exit_bar is not None:
                break
            if l[u] <= stop:
                exit_bar, exit_price, why = u, min(o[u], stop), "stop"
            elif h[u] >= target:
                exit_bar, exit_price, why = u, max(o[u], target), "target"
        if exit_bar is None:
            last = min(n - 1, entry_bar + MAX_HOLD)
            exit_bar, exit_price, why = last, c[last], "time"
        risk_now = entry - stop
        r = (exit_price - entry) / risk_now - COST * abs(entry) / risk_now
        trades.append({"entry_date": dates[entry_bar], "exit_date": dates[exit_bar], "side": side,
                       "entry": abs(entry), "stop": abs(stop), "target": abs(target), "exit": abs(exit_price),
                       "stop_pct": risk_now / abs(entry), "target_R": (target - entry) / risk_now,
                       "R": r, "why": why, "bars": exit_bar - entry_bar})
        t = exit_bar + 1                                         # one trade at a time per stock
    return trades


def placebo(df: pd.DataFrame, real: list, rng, per_trade: int = 3) -> list:
    """Random buy days with the same stop size and the same reward-to-risk as each real trade,
    the same exits and the same costs."""
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    n, out = len(c), []
    for tr in real:
        for _ in range(per_trade):
            e = int(rng.integers(260, n - 2))
            entry, sp = o[e], tr["stop_pct"]
            stop = entry * (1 - sp)
            target = entry + tr["target_R"] * (entry - stop)
            exit_price = None
            for u in range(e, min(n, e + MAX_HOLD + 1)):
                if l[u] <= stop:
                    exit_price = min(o[u], stop) if u > e else stop
                    break
                if h[u] >= target:
                    exit_price = max(o[u], target) if u > e else target
                    break
            if exit_price is None:
                exit_price = c[min(n - 1, e + MAX_HOLD)]
            risk = entry - stop
            out.append({"entry_date": df.index[e], "R": (exit_price - entry) / risk - COST * entry / risk})
    return out


# ------------------------------------------------------------------ summaries
def stats(trades) -> dict:
    if not len(trades):
        return {"trades": 0}
    r = pd.Series([t["R"] for t in trades])
    wins, losses = r[r > 0].sum(), -r[r <= 0].sum()
    return {"trades": len(r), "win_rate_pct": round((r > 0).mean() * 100, 1), "avg_R": round(r.mean(), 3),
            "median_R": round(r.median(), 2), "profit_factor": round(wins / losses, 2) if losses else float("inf"),
            "total_R": round(r.sum(), 1)}


def account(trades: list, data: dict, start_cash=1000.0, risk=0.01, per_day=2):
    """A $1,000 account: 1% risk per trade from the stop, at most 2 new trades a day, cash-limited."""
    trades = sorted(trades, key=lambda t: (t["entry_date"], -t.get("rank", 0)))
    closes = pd.DataFrame({s: d["close"] for s, d in data.items()}).ffill()
    days = closes.index[(closes.index >= trades[0]["entry_date"])] if trades else closes.index
    cash, open_pos, curve, equity = start_cash, [], {}, start_cash
    by_day = {}
    for tr in trades:
        by_day.setdefault(tr["entry_date"], []).append(tr)
    for day in days:
        for pos in [p for p in open_pos if p["exit_date"] <= day]:    # exits first
            cash += pos["shares"] * pos["exit"] * (1 - COST / 2)
            open_pos.remove(pos)
        for tr in by_day.get(day, [])[:per_day]:              # sized on yesterday's value (no peeking)
            per_share = tr["entry"] - tr["stop"]
            shares = min(equity * risk / per_share, cash / (tr["entry"] * (1 + COST / 2)))
            if shares * tr["entry"] < 1:                        # Alpaca's $1 minimum
                continue
            cash -= shares * tr["entry"] * (1 + COST / 2)
            open_pos.append({**tr, "shares": shares})
        curve[day] = equity = cash + sum(p["shares"] * closes.at[day, p["sym"]] for p in open_pos
                                         if not np.isnan(closes.at[day, p["sym"]]))
    return pd.Series(curve)


def perf(curve: pd.Series) -> dict:
    curve = curve.dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    growth = curve.iloc[-1] / curve.iloc[0]
    daily = curve.pct_change().dropna()
    return {"start": str(curve.index[0].date()), "end": str(curve.index[-1].date()),
            "final_$": round(curve.iloc[-1], 2), "CAGR_pct": round((growth ** (1 / years) - 1) * 100, 2),
            "max_drawdown_pct": round((1 - curve / curve.cummax()).max() * 100, 1),
            "sharpe": round(daily.mean() / daily.std() * np.sqrt(252), 2) if daily.std() else 0.0}


# ------------------------------------------------------------------ main
def main(out_dir: Path, bundles):
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load(bundles)
    print(f"{len(data)} symbols loaded")
    rng = np.random.default_rng(42)
    rows, all_trades = [], {}
    for k in (3, 5):
        for target_mode in ("liquidity", "fixed2R"):
            for side in ("long", "short"):
                trades, fake = [], []
                for sym, df in data.items():
                    tr = setups(df, k, target_mode, side)
                    for t in tr:
                        t["sym"] = sym
                    trades += tr
                    if side == "long":
                        fake += placebo(df, tr, rng)
                key = f"k{k}_{target_mode}_{side}"
                all_trades[key] = trades
                early = [t for t in trades if t["entry_date"] < pd.Timestamp("2018-01-01")]
                late = [t for t in trades if t["entry_date"] >= pd.Timestamp("2018-01-01")]
                rows.append({"test": key, **stats(trades), "avg_R_2010_17": stats(early).get("avg_R"),
                             "avg_R_2018_26": stats(late).get("avg_R"),
                             "placebo_avg_R": stats(fake).get("avg_R") if side == "long" else None,
                             "placebo_win_pct": stats(fake).get("win_rate_pct") if side == "long" else None})
                print(rows[-1])
    table = pd.DataFrame(rows).set_index("test")
    table.to_csv(out_dir / "tjr_daily_summary.csv")
    # Pick the version using 2010-2017 only; 2018-2026 is then an honest, unseen test.
    early = lambda k: stats([t for t in all_trades[k] if t["entry_date"] < pd.Timestamp("2018-01-01")])
    best = max((k for k in all_trades if k.endswith("_long")), key=lambda k: early(k).get("avg_R", -9))
    curve = account(all_trades[best], data)
    spy = data["SPY"]["close"]
    spy = spy[spy.index >= curve.index[0]] / spy[spy.index >= curve.index[0]].iloc[0] * 1000
    pd.DataFrame({"tjr_account": curve, "spy_hold": spy}).to_csv(out_dir / "tjr_daily_account.csv")
    pd.DataFrame(all_trades[best]).to_csv(out_dir / f"tjr_daily_trades_{best}.csv", index=False)
    late = pd.Timestamp("2018-01-01")
    print("account test uses", best, "(chosen on 2010-2017 only)")
    print("TJR account, all years:  ", perf(curve))
    print("SPY hold, all years:     ", perf(spy))
    print("TJR account, 2018-2026:  ", perf(curve[curve.index >= late]))
    print("SPY hold, 2018-2026:     ", perf(spy[spy.index >= late]))
    return table, best


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), sys.argv[2:])
