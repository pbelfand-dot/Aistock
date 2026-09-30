"""
methods.py: which trading methods actually worked in 2011-2026? A fair side-by-side test.

    python research/history/methods.py OUT_DIR BUNDLE_DIR [BUNDLE_DIR ...]

Every method runs the same way: a $1,000 account, fractional shares, buying only (the bot never
shorts), decisions made on one day's close and traded at the NEXT day's open (no peeking),
0.05% cost on every dollar bought or sold, all starting Jan 3, 2011. The standard settings from
each method's published source are used as-is (nothing tuned here). 2011-2017 and 2018-2026 are
reported separately: if a method only shines in one half, be suspicious.

Two kinds of methods, and it matters which:
  FUNDS  (SPY, sector funds, international, bonds): these funds all existed the whole time, so
         the results are trustworthy.
  STOCKS (picking individual companies): the data only has companies that are still around in
         2026, which flatters any stock-picking method. Treat those results as optimistic.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

COST = 0.0005                  # per side, as a fraction of the dollars traded
START = "2011-01-03"
SPLIT = "2018-01-01"
FUNDS = set("""ACWI DIA EEM EFA EWC EWG EWH EWJ EWY EWZ FXI GLD HYG IJH IJM IJR INDA IWD IWF IWM LQD MDY
QQQ RSP SCHD SHY SMH SPY TIP TLT USO VB VEA VIG VNQ VO VOO VT VTI VWO VXUS XBI XLB XLC XLE XLF XLI XLK
XLP XLU XLV XLY AGG BND BITO DBA DBC DBE EMB FXE FXY GDX GDXJ IBIT IGV IYR JNK KWEB MCHI MUB OIH PFF
REM SLV SOXX UUP XHB XOP XRT""".split())
SECTORS = "XLB XLC XLE XLF XLI XLK XLP XLU XLV XLY".split()
BOT_WATCHLIST = "XLF XLE XLU XLP KRE SCHD KO BAC WFC PFE CSCO VZ".split()     # KRE, WFC not in the data


# ------------------------------------------------------------------ data
def load(bundles):
    opens, closes = {}, {}
    for b in bundles:
        for f in Path(b).glob("bundle/data/equities/*.csv"):
            df = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
            if len(df) < 300:
                continue
            factor = df["adj_close"] / df["close"]
            opens[f.stem], closes[f.stem] = df["open"] * factor, df["adj_close"]
    O, C = pd.DataFrame(opens).sort_index(), pd.DataFrame(closes).sort_index()
    return O, C


def rsi2(C):
    d = C.diff()
    up, down = d.clip(lower=0), -d.clip(upper=0)
    up, down = up.ewm(alpha=0.5, adjust=False).mean(), down.ewm(alpha=0.5, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


# ------------------------------------------------------------------ the account
def simulate(O, C, decide, start=START, cash=1000.0):
    """decide(t, held) is asked after every close. It returns None (no change),
    ("full", {symbol: weight}) to rebalance everything, or ("changes", sells, {symbol: weight})
    to sell some names and buy new ones at a weight of today's account value. Trades happen at
    the next open."""
    cols = list(C.columns)
    idx = {s: i for i, s in enumerate(cols)}
    Cf = C.ffill().to_numpy(float)
    Of = O.to_numpy(float)
    Of = np.where(np.isnan(Of), np.roll(Cf, 1, axis=0), Of)
    T, N = Cf.shape
    shares = np.zeros(N)
    first = C.index.searchsorted(pd.Timestamp(start))
    curve, pending, traded = np.full(T, np.nan), None, 0.0
    for t in range(first, T):
        if pending is not None:
            px = Of[t]
            value = cash + np.nansum(shares * np.nan_to_num(px))
            if pending[0] == "full":
                want = np.zeros(N)
                for s, w in pending[1].items():
                    i = idx[s]
                    if np.isfinite(px[i]) and px[i] > 0:
                        want[i] = value * w / px[i]
                delta = want - shares
                flow = np.nansum(np.abs(delta) * np.nan_to_num(px))
                cash -= np.nansum(delta * np.nan_to_num(px)) + flow * COST
                shares, traded = want, traded + flow
            else:
                _, sells, buys = pending
                for s in sells:
                    i = idx[s]
                    flow = shares[i] * px[i]
                    cash += flow * (1 - COST)
                    shares[i], traded = 0.0, traded + flow
                for s, w in buys.items():
                    i = idx[s]
                    amount = min(value * w, cash)
                    if amount >= 1 and np.isfinite(px[i]) and px[i] > 0:        # Alpaca's $1 minimum
                        shares[i] += amount * (1 - COST) / px[i]
                        cash -= amount
                        traded += amount
            pending = None
        curve[t] = cash + np.nansum(shares * np.nan_to_num(Cf[t]))
        held = {cols[i] for i in np.flatnonzero(shares > 0)}
        pending = decide(t, held)
    out = pd.Series(curve, index=C.index).dropna()
    years = (out.index[-1] - out.index[0]).days / 365.25
    return out, traded / out.mean() / years          # curve, yearly turnover (x account size)


# ------------------------------------------------------------------ the methods
def make_methods(O, C):
    cols = set(C.columns)
    Cn = C.to_numpy(float)
    sma = lambda n: C.rolling(n).mean().to_numpy(float)
    s5, s50, s200 = sma(5), sma(50), sma(200)
    r2 = rsi2(C).to_numpy(float)
    ret = lambda lag: (C / C.shift(lag) - 1).to_numpy(float)
    r126, r252 = ret(126), ret(252)
    mom12_1 = (C.shift(21) / C.shift(252) - 1).to_numpy(float)
    vol126 = C.pct_change().rolling(126).std().to_numpy(float)
    col = {s: i for i, s in enumerate(C.columns)}
    dates = C.index
    month_end = np.r_[dates[1:].month != dates[:-1].month, True]
    stocks = [s for s in C.columns if s not in FUNDS]
    watch = [s for s in BOT_WATCHLIST if s in cols]
    funds = [s for s in C.columns if s in FUNDS and s not in ("IBIT", "BITO", "SHY")]
    # Hindsight check: the companies that went up the most over the whole test (only knowable in 2026).
    total = (C[stocks].ffill().iloc[-1] / C[stocks].loc[START:].bfill().iloc[0]).sort_values(ascending=False)
    top10, top25 = set(total.index[:10]), set(total.index[:25])

    def spy_up(t):
        return Cn[t, col["SPY"]] > s200[t, col["SPY"]]

    def trend_daily(symbol):
        def decide(t, held):
            want = symbol if Cn[t, col[symbol]] > s200[t, col[symbol]] else "SHY"
            return ("full", {want: 1.0}) if held != {want} else None
        return decide

    def fund_momentum(n, filtered):                      # top n funds by 12-1 month return, monthly
        def decide(t, held):
            if not month_end[t] and held:
                return None
            if filtered and not spy_up(t):
                return ("full", {"SHY": 1.0})
            ranked = sorted((mom12_1[t, col[s]], s) for s in funds if np.isfinite(mom12_1[t, col[s]]))[-n:]
            return ("full", {s: 1 / n for _, s in ranked})
        return decide

    def hold(symbol):
        def decide(t, held):
            return ("full", {symbol: 1.0}) if not held else None
        return decide

    def spy_trend_daily(t, held):
        want = "SPY" if spy_up(t) else "SHY"
        return ("full", {want: 1.0}) if held != {want} else None

    def spy_trend_monthly(t, held):                      # Faber: 10-month average, checked monthly
        if not month_end[t] and held:
            return None
        monthly = C["SPY"].iloc[:t + 1][month_end[:t + 1]]
        want = "SPY" if len(monthly) >= 10 and monthly.iloc[-1] > monthly.iloc[-10:].mean() else "SHY"
        return ("full", {want: 1.0}) if held != {want} else None

    def dual_momentum(t, held):                          # Antonacci's GEM, monthly
        if not month_end[t] and held:
            return None
        spy, efa, shy = (r252[t, col[s]] for s in ("SPY", "EFA", "SHY"))
        want = ("SPY" if spy >= efa else "EFA") if spy > shy else "AGG"
        return ("full", {want: 1.0}) if held != {want} else None

    def sectors(filtered):                               # top 3 sector funds by 6-month return, monthly
        def decide(t, held):
            if not month_end[t] and held:
                return None
            if filtered and not spy_up(t):
                return ("full", {"SHY": 1.0})
            ranked = sorted((r126[t, col[s]], s) for s in SECTORS if np.isfinite(r126[t, col[s]]))[-3:]
            return ("full", {s: 1 / 3 for _, s in ranked})
        return decide

    def momentum_stocks(n, filtered, leave_out=frozenset()):   # top n stocks by 12-1 month return, monthly
        pool = [s for s in stocks if s not in leave_out]
        def decide(t, held):
            if not month_end[t] and held:
                return None
            if filtered and not spy_up(t):
                return ("full", {"SHY": 1.0})
            ranked = sorted((mom12_1[t, col[s]], s) for s in pool if np.isfinite(mom12_1[t, col[s]]))[-n:]
            return ("full", {s: 1 / n for _, s in ranked})
        return decide

    def all_stocks(t, held):                             # every stock in the list, equal weight, monthly
        if not month_end[t] and held:
            return None
        have = [s for s in stocks if np.isfinite(Cn[t, col[s]])]
        return ("full", {s: 1 / len(have) for s in have})

    def low_volatility(t, held):                         # 20 calmest stocks, monthly
        if not month_end[t] and held:
            return None
        ranked = sorted((vol126[t, col[s]], s) for s in stocks if np.isfinite(vol126[t, col[s]]))[:20]
        return ("full", {s: 1 / 20 for _, s in ranked})

    def rsi2_spy(t, held):                               # Connors: buy a 2-day dip above the 200-day
        i = col["SPY"]
        if "SPY" in held:
            return ("full", {"SHY": 1.0}) if Cn[t, i] > s5[t, i] else None
        if r2[t, i] < 10 and Cn[t, i] > s200[t, i]:
            return ("full", {"SPY": 1.0})
        return None if held else ("full", {"SHY": 1.0})

    def swing(universe, rule, slots=10):                 # the bot's own swing rules, up to 10 positions
        def decide(t, held):
            sells = [s for s in held if s in universe and
                     (Cn[t, col[s]] > s5[t, col[s]] if rule == "mean_reversion" else Cn[t, col[s]] < s50[t, col[s]])]
            room = slots - (len(held) - len(sells))
            buys = {}
            if room > 0:
                if rule == "mean_reversion":
                    cands = [(r2[t, col[s]], s) for s in universe if s not in held
                             and r2[t, col[s]] < 10 and Cn[t, col[s]] > s200[t, col[s]]]
                    cands.sort()
                else:
                    cands = [(-r126[t, col[s]], s) for s in universe if s not in held
                             and Cn[t, col[s]] > s50[t, col[s]] > s200[t, col[s]]]
                    cands.sort()
                buys = {s: 1 / slots for _, s in cands[:room]}
            return ("changes", sells, buys) if sells or buys else None
        return decide

    print("biggest winners 2011-2026 (hindsight):", ", ".join(f"{s} x{total[s]:.0f}" for s in total.index[:10]))
    return {
        "Hold SPY (benchmark)": ("fund", hold("SPY")),
        "Hold QQQ (Nasdaq 100)": ("fund", hold("QQQ")),
        "Hold RSP (equal-weight S&P 500)": ("fund", hold("RSP")),
        "SPY trend, daily 200-day rule": ("fund", spy_trend_daily),
        "QQQ trend, daily 200-day rule": ("fund", trend_daily("QQQ")),
        "SPY trend, monthly 10-month rule": ("fund", spy_trend_monthly),
        "Dual momentum (SPY / world / bonds)": ("fund", dual_momentum),
        "Sector rotation, top 3": ("fund", sectors(False)),
        "Sector rotation, top 3 + trend filter": ("fund", sectors(True)),
        "SPY dip-buying (RSI 2)": ("fund", rsi2_spy),
        "Fund momentum, top 3 of all funds": ("fund", fund_momentum(3, False)),
        "Fund momentum, top 3 + trend filter": ("fund", fund_momentum(3, True)),
        "All stocks in the list, equal weight (survivor yardstick)": ("stocks", all_stocks),
        "Stock momentum, top 10": ("stocks", momentum_stocks(10, False)),
        "Stock momentum, top 20": ("stocks", momentum_stocks(20, False)),
        "Stock momentum, top 10 + trend filter": ("stocks", momentum_stocks(10, True)),
        "Stock momentum, top 10, without the 10 biggest winners": ("stocks", momentum_stocks(10, False, top10)),
        "Stock momentum, top 10, without the 25 biggest winners": ("stocks", momentum_stocks(10, False, top25)),
        "Low-volatility stocks, 20": ("stocks", low_volatility),
        "Bot trend rule, its watchlist": ("fund+stocks", swing(watch, "trend")),
        "Bot dip rule, its watchlist": ("fund+stocks", swing(watch, "mean_reversion")),
        "Bot trend rule, all stocks": ("stocks", swing(stocks, "trend")),
        "Bot dip rule, all stocks": ("stocks", swing(stocks, "mean_reversion")),
    }


# ------------------------------------------------------------------ scoring
def perf(curve):
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    daily = curve.pct_change().dropna()
    return {"cagr": (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1,
            "max_dd": (1 - curve / curve.cummax()).max(),
            "sharpe": daily.mean() / daily.std() * np.sqrt(252) if daily.std() else 0.0}


def main(out_dir: Path, bundles):
    out_dir.mkdir(parents=True, exist_ok=True)
    O, C = load(bundles)
    methods = make_methods(O, C)
    curves, rows = {}, []
    for name, (kind, decide) in methods.items():
        curve, turnover = simulate(O, C, decide)
        curves[name] = curve
        early, late = curve[curve.index < SPLIT], curve[curve.index >= SPLIT]
        a, e, l = perf(curve), perf(early), perf(late)
        rows.append({"method": name, "kind": kind, "final_$": round(curve.iloc[-1]),
                     "per_year_%": round(a["cagr"] * 100, 1), "worst_drop_%": round(a["max_dd"] * 100, 1),
                     "sharpe": round(a["sharpe"], 2),
                     "2011-17_per_year_%": round(e["cagr"] * 100, 1), "2018-26_per_year_%": round(l["cagr"] * 100, 1),
                     "2018-26_sharpe": round(l["sharpe"], 2), "turnover_x_per_year": round(turnover, 1)})
        print(rows[-1])
    table = pd.DataFrame(rows).set_index("method")
    yearly = pd.DataFrame({n: c.resample("YE").last() for n, c in curves.items()})
    yearly = yearly.pct_change().fillna(yearly.iloc[0] / 1000 - 1)
    table["years_beat_SPY"] = [int((yearly[n] > yearly["Hold SPY (benchmark)"]).sum()) for n in table.index]
    table.to_csv(out_dir / "methods_summary.csv")
    pd.DataFrame(curves).to_csv(out_dir / "methods_curves.csv")
    (yearly * 100).round(1).to_csv(out_dir / "methods_yearly.csv")
    return table


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    print(main(Path(sys.argv[1]), sys.argv[2:]).to_string())
