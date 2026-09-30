"""
tjr.py: TJR's model as code (Stage 2 of the owner's plan), on the day desk's 5-minute bars.

From the rulebook (research/tjr/RULES.md) and the 50 recap videos (research/tjr/recaps/HYPOTHESES.md):

  1. Bias (H1, H17): only buy while the stock's HOURLY structure is up: its latest confirmed hourly
     swing low is higher than the one before, and the last hourly close is still above it.
  2. Liquidity (rules 1-2): lows where stops sit: yesterday's low and today's/yesterday's 5-minute
     swing lows. A SWEEP is a bar trading below one of them.
  3. Break of structure (rule 3, H2, H8): within 12 bars of the sweep, a 5-minute bar CLOSES above the
     last swing high before the sweep ("the high that created the low"). No break, no trade.
  4. Fair value gap (rule 4): the bullish gap that break left (bar 1's high below bar 3's low, at least
     0.05% of the price). Entry when a later bar trades back into the gap and closes without falling
     through it (H2: "entry on rejection"), within 12 bars. A close below the gap cancels the setup.
  5. When (H5): entries 9:35-11:30am New York time (41 of his 55 recorded entries were 9:20-10:30).
  6. Stop (rule 5, H3): below the sweep's low, with a buffer of 1/4 of the 5-minute ATR (5 of his 11
     losses were stopped by a few points just past the swing). Target: 2x the risk (2R: better than the
     next high in the 16-year daily test).
  7. One trade per stock per day (H10: no add-ons). Long only: shorting it lost in every version of the
     16-year test, and the bot doesn't short. The day desk still sells everything before the close.

Scores for the engine: 1.0 on the entry bar, 0.6 while the trade is on, 0.0 once its stop or target is
hit (and for the rest of the day), 0.2 when there's no trade. So the desk buys at 1.0 and sells below 0.5.

Before it can paper trade (Stage 2) it must pass its HISTORY TEST on the Mac's own 5-minute data
(history_test below): enough trades, a profit factor over 1.15, making money, and beating a placebo
that buys at random moments in the same window with the same stop and target.
"""
import numpy as np
import pandas as pd

from .strategies import Strategy

WINDOW = (5, 120)                    # minutes after 9:30am when entries are allowed: 9:35-11:30
SWEEP_BARS = 12                      # a break of structure must follow the sweep within this many bars
ENTRY_BARS = 12                      # ...and price must come back into the gap within this many
MIN_GAP = 0.0005                     # the gap must be at least 0.05% of the price
STOP_BUFFER_ATR = 0.25
TARGET_R = 2.0
SWING_K = 2                          # a swing high/low: the highest/lowest of 2 bars on each side
PLACEBO_RATE = 0.01                  # the placebo's chance of buying on any bar in the window

IN_TRADE, ENTRY, FLAT, NOTHING = 0.6, 1.0, 0.0, 0.2


def _swings(values: np.ndarray, k: int, highs: bool) -> np.ndarray:
    """Index i is a swing (high or low) if it's the extreme of the k bars on each side. The result at
    position i is known only at bar i + k (confirmation), which the callers respect."""
    rolling = pd.Series(values).rolling(2 * k + 1, center=True)
    extreme = (rolling.max() if highs else rolling.min()).to_numpy()
    return (values == extreme) & ~np.isnan(extreme)


def hourly_bias(df: pd.DataFrame) -> pd.Series:
    """True at each 5-minute bar when the hourly structure is up (H17): the latest CONFIRMED hourly
    swing low is higher than the one before, and the last completed hourly close is above it."""
    hourly = df.resample("60min", offset="30min").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    lows = hourly["low"].to_numpy()
    is_low = _swings(lows, 2, highs=False)
    confirmed_at = {hourly.index[i + 2]: lows[i] for i in np.flatnonzero(is_low) if i + 2 < len(hourly)}
    state, last2, up = [], [], False
    for when, close in zip(hourly.index, hourly["close"].to_numpy()):
        if when in confirmed_at:
            last2 = (last2 + [confirmed_at[when]])[-2:]
        up = len(last2) == 2 and last2[1] > last2[0] and close > last2[1]
        state.append(up)
    # an hourly bar labelled 10:30 covers 10:30-11:30: its verdict applies from 11:30 on
    done = pd.Series(state, index=hourly.index + pd.Timedelta(minutes=60))
    return done.reindex(df.index, method="ffill").fillna(False).astype(bool)


def _atr(df: pd.DataFrame, bars: int = 14) -> np.ndarray:
    prev = df["close"].shift()
    true_range = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return true_range.rolling(bars, min_periods=3).mean().to_numpy()


def ticker_scores(df: pd.DataFrame, since=None, target_r: float = TARGET_R, placebo_seed: int = None) -> pd.Series:
    """The score of every bar for one stock. placebo_seed: instead of the setup, enter at random
    moments in the same window (same stop and target), for the history test's comparison."""
    df = df.sort_index()
    o, h, l, c = (df[x].to_numpy(dtype=float) for x in ("open", "high", "low", "close"))
    day = df.index.normalize()
    minute = ((df.index - day) / pd.Timedelta(minutes=1)).to_numpy() - 570
    atr = _atr(df)
    bias = hourly_bias(df).to_numpy()
    swing_hi, swing_lo = _swings(h, SWING_K, True), _swings(l, SWING_K, False)
    days = pd.Index(day.unique())
    prev_low = pd.Series(l, index=day).groupby(level=0).min().shift().reindex(day).to_numpy()
    rng = np.random.default_rng(placebo_seed) if placebo_seed is not None else None
    score = np.full(len(df), NOTHING)
    start_day = days[0] if since is None else pd.Timestamp(since).normalize()
    for d in days[days >= start_day]:
        idx = np.flatnonzero(day == d)
        first, last = idx[0], idx[-1]
        back = max(0, first - 78)                                     # yesterday's bars
        levels = [prev_low[first]] if not np.isnan(prev_low[first]) else []
        levels += [l[i] for i in np.flatnonzero(swing_lo[back:max(back, first - SWING_K)]) + back]
        mode, traded = "hunt", False
        sweep_bar = sweep_low = ref_high = gap_lo = gap_hi = stop = target = None
        await_until = 0
        for j in range(first, last + 1):
            # swing lows confirmed by now join the levels (k bars after the swing)
            if j - SWING_K >= max(back, first - SWING_K) and swing_lo[j - SWING_K]:
                levels.append(l[j - SWING_K])
            if mode == "in":
                if l[j] <= stop or h[j] >= target:
                    score[j], mode = FLAT, "done"
                else:
                    score[j] = IN_TRADE
                continue
            if mode == "done":
                score[j] = FLAT
                continue
            in_window = WINDOW[0] <= minute[j] <= WINDOW[1]
            if rng is not None:                                       # the placebo: random entries
                if not traded and in_window and bias[j] and rng.random() < PLACEBO_RATE and not np.isnan(atr[j]):
                    lo = l[max(first, j - 6):j + 1].min()
                    stop = lo - STOP_BUFFER_ATR * atr[j]
                    risk = c[j] - stop
                    if risk > 0:
                        target, traded, mode, score[j] = c[j] + target_r * risk, True, "in", ENTRY
                continue
            if mode == "hunt":
                below = [lv for lv in levels if l[j] < lv]
                if below and not traded:
                    levels = [lv for lv in levels if lv not in below]      # a swept level is used up
                    before = np.flatnonzero(swing_hi[back:max(back, j - SWING_K + 1)]) + back
                    ref_high = h[before[-1]] if len(before) else (h[max(0, j - 12):j].max() if j > 0 else None)
                    if ref_high is not None:
                        mode, sweep_bar, sweep_low = "swept", j, l[j]
                continue
            if mode == "swept":
                sweep_low = min(sweep_low, l[j])
                if c[j] > ref_high:                                   # break of structure
                    gaps = [i for i in range(j, sweep_bar + 1, -1)
                            if h[i - 2] < l[i] and (l[i] - h[i - 2]) / c[i] >= MIN_GAP]
                    if gaps:
                        i = gaps[0]
                        gap_lo, gap_hi, mode, await_until = h[i - 2], l[i], "await", j + ENTRY_BARS
                    else:
                        mode = "hunt"
                elif j - sweep_bar > SWEEP_BARS:
                    mode = "hunt"
                continue
            if mode == "await":
                if c[j] < gap_lo or j > await_until:                  # fell through the gap, or too late
                    mode = "hunt"
                    continue
                if l[j] <= gap_hi and in_window and bias[j] and not np.isnan(atr[j]):
                    stop = sweep_low - STOP_BUFFER_ATR * atr[j]
                    risk = c[j] - stop
                    if risk > 0:
                        target, traded, mode, score[j] = c[j] + target_r * risk, True, "in", ENTRY
    out = pd.Series(score, index=df.index)
    return out if since is None else out[out.index.normalize() >= start_day]


class TJRModel(Strategy):
    name = "tjr_model"
    style = "day"
    buy_above = 0.9
    sell_below = 0.5
    description = ("TJR's model: while the stock's hourly trend is up, wait for price to sweep below a low "
                   "where stops sit (yesterday's low or a 5-minute swing low), then break back above the last "
                   "swing high; buy when it pulls back into the gap that break left, 9:35-11:30am. Stop just "
                   "below the sweep, target 2x the risk, one trade per stock a day.")

    def scores(self, bars, market, since=None):
        return pd.DataFrame({t: ticker_scores(df, since) for t, df in bars.items() if len(df)})


class TJRPlacebo(TJRModel):
    """Random entries in the same window, same stop/target rules: what TJR's setup must beat."""
    name = "tjr_placebo"
    description = "Random buys at 9:35-11:30am with TJR's stop and target (the comparison, never traded)."

    def scores(self, bars, market, since=None):
        return pd.DataFrame({t: ticker_scores(df, since, placebo_seed=n) for n, (t, df) in enumerate(bars.items())
                             if len(df)})


# ---------------------------------------------------------------- the history test (Stage 2's gate)
PASS = {"min_trades": 30, "min_profit_factor": 1.15}


def history_test(cfg: dict, bars: dict, market: pd.DataFrame) -> dict:
    """TJR's model and the placebo, replayed on the day desk's own 5-minute history with its real rules
    (slots, sizes, costs). Passes with enough trades, a profit factor over 1.15, a profit, and a better
    profit factor than the placebo (per-trade quality: trading more often isn't "better")."""
    from .engine import run_backtest
    tjr = run_backtest(TJRModel(), bars, market, cfg, "day")
    placebo = run_backtest(TJRPlacebo(), bars, market, cfg, "day")
    trades = int(tjr.get("num_closed_trades") or 0)
    pf, base = tjr.get("profit_factor"), placebo.get("profit_factor")
    ret = tjr.get("total_return_pct") or 0.0
    ok = lambda x: x is not None and x == x
    why = []
    if trades < PASS["min_trades"]:
        why.append(f"only {trades} trades (needs {PASS['min_trades']})")
    if not ok(pf) or pf < PASS["min_profit_factor"]:
        why.append(f"profit factor {round(pf, 2) if ok(pf) else '--'} (needs {PASS['min_profit_factor']})")
    if ret <= 0:
        why.append(f"lost money ({ret:+.2f}%)")
    if ok(pf) and ok(base) and pf <= base:
        why.append(f"no better than random entries (profit factor {pf:.2f} vs {base:.2f})")
    return {"passed": not why, "why_not": why, "tjr": tjr, "placebo": placebo,
            "days": int(tjr.get("trading_days") or 0), "tickers": sorted(bars)}
