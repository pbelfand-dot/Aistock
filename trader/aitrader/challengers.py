"""
challengers.py: a new idea has to beat the desk's current method before it trades a cent.

A challenger is another version of a desk's method (config.yaml `challengers:`; e.g. momentum_plus next to
momentum). It never trades at first. Two kinds of evidence, both comparing it with the method the desk
uses now, on the same stocks, with the same money, rules and costs:

  history  the whole price history Kestrel keeps (8 years of daily prices), replayed after every close.
           Big sample, but the stock list is today's (stocks that made it), which flatters any momentum
           method; comparing two methods on the SAME list cancels much of that, not all.
  forward  a shadow account per method, from the day the challenger was added: at the desk's real decision
           time it decides on the real prices, simulated on this Mac (resting stop-losses, slippage; no
           team, so both sides are judged the same way). Truly unseen, but small.

It replaces the current method only when it's PROVEN better, by tests built to catch luck:
  1. paired: day by day, its return minus the current method's, over the same history days
  2. stationary bootstrap (Politis & Romano 1994): those daily differences resampled 2,000 times in
     random-length blocks (so streaks stay streaks); it must come out ahead in at least 95% (p <= 0.05)
  3. deflated Sharpe ratio (Bailey & Lopez de Prado 2014): every idea ever tried is written down (the
     `trials` table), and the more ideas tried, the higher the bar, so testing many ideas can't produce
     a lucky "winner"; it must clear 0.95
  4. its worst drop no more than 5 points worse than the current method's
  5. forward: at least 20 trading days in its shadow account, and not behind there

Then: a desk trading pretend money (in its head, or paper) switches by itself and tells you (journal and
phone). A real-money desk only switches when you press "Use it" in the Thinking tab. Every result is in
the Thinking tab and the after-market report.
"""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from .market_hours import now_ny

DEFAULTS = {
    "enabled": True,
    "swing": ["momentum", "momentum_plus", "momentum_calm", "momentum_plus_calm"],
    "day": [],
    "min_forward_days": {"swing": 20, "day": 10},
    "min_history_days": 250,          # a year of paired days before the history can prove anything
    "max_p_value": 0.05,
    "min_deflated_sharpe": 0.95,
    "max_extra_drawdown_pct": 5,
    "auto_switch": True,              # pretend-money desks switch by themselves (a real-money desk never does)
}
EULER = 0.5772156649015329
N01 = NormalDist()


def settings(cfg: dict) -> dict:
    s = {**DEFAULTS, **(cfg.get("challengers") or {})}
    for key in ("enabled", "auto_switch"):
        s[key] = str(s[key]).strip().lower() not in ("off", "false", "no", "0")
    return s


def shadow_mode(desk: str, name: str) -> str:
    return f"shadow-{desk}-{name}"


# ---------------------------------------------------------------- which method the desk uses
def current(store, desk: str, base: str) -> str:
    """The method the desk trades: its plan's (or in-its-head) method, unless a challenger proved better."""
    switch = store.get(f"strategy_switch:{desk}") or {}
    return switch["to"] if base and switch.get("base") == base and switch.get("to") else base


def ring(cfg: dict, desk: str, now_using: str) -> list:
    """The challengers of the desk's current method (the rest of the desk's list in config.yaml). None
    when the current method isn't on the list (e.g. the day desk's TJR model): nothing to compare."""
    s = settings(cfg)
    names = [n for n in (s.get(desk) or []) if n]
    if not s["enabled"] or now_using not in names:
        return []
    from .strategies import all_strategies
    known = {x.name for x in all_strategies(cfg, desk)}
    return [n for n in names if n != now_using and n in known]


def switch(store, desk: str, base: str, to: str, why: str, by: str = "Kestrel"):
    old = current(store, desk, base)
    history = (store.get(f"strategy_switch:{desk}") or {}).get("history", [])
    day = now_ny().strftime("%Y-%m-%d")
    store.set(f"strategy_switch:{desk}", {"base": base, "to": to, "on": day, "why": why, "by": by,
                                          "history": (history + [{"on": day, "from": old, "to": to, "why": why}])[-20:]})
    store.log(f"CHALLENGER WON ({desk} desk): {to} replaces {old} from the next decision. {why}")


# ---------------------------------------------------------------- the shadow accounts (forward evidence)
class _Quiet:
    """The same database, with journal lines dropped (the real journal stays about real trades)."""
    def __init__(self, store):
        self._store = store

    def __getattr__(self, key):
        return getattr(self._store, key)

    def log(self, *args, **kwargs):
        pass

    def set(self, key, value):
        if key == "autopilot_step" and isinstance(value, dict):         # the Thinking tab's "doing now" line
            value = {**value, "text": f"the challengers' shadow accounts: {value.get('text', '')}"}
        self._store.set(key, value)


def run_shadows(cfg: dict, store, desk: str, bars: dict, market: pd.DataFrame, now, now_using: str,
                blocked=()) -> list:
    """At the desk's real decision: each method on the ring (and the current one) decides in its own
    shadow account, simulated on this Mac. Their journal lines are dropped (the real journal stays about
    real trades). Returns the modes that ran."""
    names = ring(cfg, desk, now_using)
    if not names:
        return []
    from .brokers import Ledger, PaperBroker
    from .config import desk_capital, is_cash_account
    from .engine import price_table, resting_stop_fills, run_cycle, sell_all, execute
    from .risk import RiskManager
    from .strategies import get_strategy
    store = _Quiet(store)
    today = now.strftime("%Y-%m-%d")
    ran = []
    for name in [now_using] + names:
        mode = shadow_mode(desk, name)
        saved = store.get(f"{mode}_ledger")
        ledger = Ledger.from_dict(saved) if saved else Ledger(desk_capital(cfg, desk, False))
        broker = PaperBroker(ledger, cfg["paper"]["slippage_pct"], cfg["paper"]["commission_per_trade"],
                             mode=mode, cash_account=is_cash_account(cfg))
        broker.on_fill = lambda f, m=mode: store.record_fill(m, f)
        broker.blocked = frozenset(blocked)
        risk = RiskManager.for_desk(cfg, desk)
        if desk == "swing":                          # stop-losses resting at the broker during the day
            opens, lows = price_table(bars, "open").iloc[-1], price_table(bars, "low").iloc[-1]
            resting_stop_fills(broker, risk, opens, lows, today)
        result = run_cycle(store, broker, get_strategy(name, cfg, desk), risk, bars, market, now,
                           cfg["desks"][desk])
        if result["kill_switch"]:                    # pretend money: sell, start the count again
            execute(sell_all(broker.positions(), result["prices"], "kill switch (shadow account)"), broker, today)
            store.set(f"{mode}_peak_equity", None)
            store.record_equity(mode, today, broker.equity(result["prices"]), broker.cash())
        store.set(f"{mode}_ledger", broker.ledger.to_dict())
        if not store.get(f"{mode}_since"):
            store.set(f"{mode}_since", today)
        ran.append(mode)
    return ran


# ---------------------------------------------------------------- the tests for luck
def bootstrap_p(diff, reps: int = 2000, block: float = None, seed: int = 7) -> float:
    """One-sided p-value that the average daily difference is above zero, from the stationary bootstrap
    (Politis & Romano 1994): resampled in blocks of random length (average `block` days, about the cube
    root of the sample) so that runs of good and bad days stay together. Small = unlikely to be luck."""
    x = np.asarray(diff, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 20 or x.std() == 0:
        return 1.0
    block = block or max(5.0, n ** (1 / 3))
    rng = np.random.default_rng(seed)
    centered = x - x.mean()                         # the "no real edge" world
    pos = rng.integers(0, n, reps)
    total = centered[pos].copy()
    for _ in range(1, n):
        jump = rng.random(reps) < 1 / block
        pos = np.where(jump, rng.integers(0, n, reps), (pos + 1) % n)
        total += centered[pos]
    return float((np.sum(total / n >= x.mean()) + 1) / (reps + 1))


def expected_max_sharpe(trials: int, variance: float) -> float:
    """How high the best of `trials` worthless ideas' Sharpe ratios would reach by luck alone."""
    if trials <= 1:
        return 0.0
    return math.sqrt(variance) * ((1 - EULER) * N01.inv_cdf(1 - 1 / trials)
                                  + EULER * N01.inv_cdf(1 - 1 / (trials * math.e)))


def deflated_sharpe(diff, trials: int, variance: float = None) -> float:
    """The deflated Sharpe ratio (Bailey & Lopez de Prado 2014): the probability that the daily
    differences' true Sharpe ratio is above what the luckiest of `trials` worthless ideas would show,
    allowing for lopsided and fat-tailed days. 0.95+ = a real edge, after counting every idea tried.
    variance: how much the tried ideas' Sharpe ratios differ (at least what chance alone gives)."""
    x = np.asarray(diff, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 30 or x.std() == 0:
        return 0.0
    sr = x.mean() / x.std(ddof=1)
    z = (x - x.mean()) / x.std()
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    benchmark = expected_max_sharpe(trials, max(variance or 0.0, 1 / n))
    spread = max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12)
    return float(N01.cdf((sr - benchmark) * math.sqrt(n - 1) / math.sqrt(spread)))


# ---------------------------------------------------------------- the daily comparison
def _returns(curve: pd.Series) -> pd.Series:
    curve = curve.dropna()
    return curve.pct_change().dropna() if len(curve) > 1 else pd.Series(dtype=float)


def forward(store, desk: str, name: str, now_using: str) -> dict:
    """Both shadow accounts since the later of the two started: trading days, and each one's return."""
    a, b = store.equity_curve(shadow_mode(desk, name)), store.equity_curve(shadow_mode(desk, now_using))
    days = a.index.intersection(b.index)
    if len(days) < 2:
        return {"days": max(len(days) - 1, 0), "return_pct": None, "current_return_pct": None, "ahead_pct": None,
                "since": store.get(f"{shadow_mode(desk, name)}_since")}
    a, b = a.loc[days], b.loc[days]
    mine, theirs = (a.iloc[-1] / a.iloc[0] - 1) * 100, (b.iloc[-1] / b.iloc[0] - 1) * 100
    return {"days": len(days) - 1, "return_pct": round(float(mine), 2), "current_return_pct": round(float(theirs), 2),
            "ahead_pct": round(float(mine - theirs), 2), "since": days[0].strftime("%Y-%m-%d")}


def judge(s: dict, desk: str, history: dict, fwd: dict) -> tuple:
    """(verdict, why): proven / promising / not better / too early."""
    need_days = int((s["min_forward_days"] or {}).get(desk, 20))
    if history["days"] < s["min_history_days"]:
        return "too early", f"only {history['days']} days of history to compare (needs {s['min_history_days']})"
    problems = []
    if history["extra_per_year_pct"] <= 0:
        problems.append(f"it did worse over the history ({history['extra_per_year_pct']:+.1f}% a year)")
    else:
        if history["p_value"] > s["max_p_value"]:
            problems.append(f"its {history['extra_per_year_pct']:+.1f}% a year could be luck "
                            f"(p {history['p_value']:.2f}, needs {s['max_p_value']:g} or less)")
        if history["deflated_sharpe"] < s["min_deflated_sharpe"]:
            problems.append(f"not enough after counting the {history['trials']} ideas tried (deflated Sharpe "
                            f"{history['deflated_sharpe']:.2f}, needs {s['min_deflated_sharpe']:g})")
    if history["extra_drawdown_pct"] > s["max_extra_drawdown_pct"]:
        problems.append(f"its worst drop was {history['extra_drawdown_pct']:.1f} points deeper")
    if problems:
        return "not better", "; ".join(problems)
    if fwd["days"] < need_days:
        return "promising", (f"the history says better ({history['extra_per_year_pct']:+.1f}% a year); shadow "
                             f"trading {fwd['days']} of {need_days} days before it can take over")
    if (fwd["ahead_pct"] or 0) < 0:
        return "promising", (f"the history says better, but it's behind in shadow trading "
                             f"({fwd['ahead_pct']:+.2f}% over {fwd['days']} days); it must not be behind")
    return "proven", (f"{history['extra_per_year_pct']:+.1f}% a year over {history['years']:.1f} years of "
                      f"history (p {history['p_value']:.3f}, deflated Sharpe {history['deflated_sharpe']:.2f} after "
                      f"{history['trials']} ideas tried), worst drop {history['max_drawdown_pct']:.1f}% vs "
                      f"{history['current_max_drawdown_pct']:.1f}%, and {fwd['ahead_pct']:+.2f}% ahead over "
                      f"{fwd['days']} days of shadow trading")


def evaluate(cfg: dict, store, desk: str, bars: dict, market: pd.DataFrame, now_using: str, base: str,
             real_money: bool = False, today: str = None) -> dict:
    """After the close: every challenger against the current method (history + forward), the tests for
    luck, the `trials` log, and the switch when one is proven. Saved for the app and the report."""
    from .engine import run_backtest
    from .strategies import get_strategy
    s = settings(cfg)
    names = ring(cfg, desk, now_using)
    today = today or now_ny().strftime("%Y-%m-%d")
    if not names:
        store.set(f"challengers:{desk}", None)
        return {}
    champ = run_backtest(get_strategy(now_using, cfg, desk), bars, market, cfg, desk, curve=True)
    champ_daily = _returns(champ.pop("daily"))
    tested = []
    for name in names:                                  # 1) replay each one; write every idea tried down first
        strategy = get_strategy(name, cfg, desk)
        bt = run_backtest(strategy, bars, market, cfg, desk, curve=True)
        mine = _returns(bt.pop("daily"))
        days = mine.index.intersection(champ_daily.index)
        diff = (mine.loc[days] - champ_daily.loc[days]).to_numpy()
        sharpe = float(diff.mean() / diff.std(ddof=1)) if len(diff) > 2 and diff.std() > 0 else 0.0
        p = bootstrap_p(diff)
        store.record_trial(desk, name, now_using, today, len(diff), sharpe, p)
        tested.append((name, strategy, bt, diff, p))
    trials = store.trials(desk)                         # 2) judge each against every idea ever tried
    variance = float(np.var([t["sharpe"] for t in trials], ddof=1)) if len(trials) > 1 else 0.0
    rows = []
    for name, strategy, bt, diff, p in tested:
        history = {
            "days": int(len(diff)), "years": round(len(diff) / 252, 1),
            "extra_per_year_pct": round(float(diff.mean() * 252 * 100), 2) if len(diff) else 0.0,
            "p_value": round(p, 4), "trials": len(trials),
            "deflated_sharpe": round(deflated_sharpe(diff, len(trials), variance), 3),
            "return_pct": bt["total_return_pct"], "current_return_pct": champ["total_return_pct"],
            "sharpe": bt["sharpe"], "current_sharpe": champ["sharpe"],
            "max_drawdown_pct": bt["max_drawdown_pct"], "current_max_drawdown_pct": champ["max_drawdown_pct"],
            "extra_drawdown_pct": round(bt["max_drawdown_pct"] - champ["max_drawdown_pct"], 2),
            "trades": bt["num_closed_trades"], "current_trades": champ["num_closed_trades"],
            "start": bt.get("start")}
        fwd = forward(store, desk, name, now_using)
        verdict, why = judge(s, desk, history, fwd)
        store.finish_trial(desk, name, now_using, history["deflated_sharpe"], verdict)
        rows.append({"name": name, "description": strategy.description, "history": history, "forward": fwd,
                     "verdict": verdict, "why": why})

    proven = [r for r in rows if r["verdict"] == "proven"]
    winner = max(proven, key=lambda r: r["history"]["deflated_sharpe"]) if proven else None
    report = {"desk": desk, "as_of": today, "current": now_using, "base": base, "rows": rows,
              "current_description": get_strategy(now_using, cfg, desk).description,
              "switches": (store.get(f"strategy_switch:{desk}") or {}).get("history", []),
              "waiting_for_you": None}
    if winner and real_money:
        report["waiting_for_you"] = winner["name"]
        before = store.get(f"challenger_offer:{desk}") or {}
        if before.get("name") != winner["name"]:
            store.log(f"CHALLENGER PROVEN ({desk} desk, real money): {winner['name']} beat {now_using}: "
                      f"{winner['why']}. A real-money desk only switches when you press Use it (Thinking tab).")
            store.set(f"challenger_offer:{desk}", {"name": winner["name"], "on": today})
    elif winner and s["auto_switch"]:
        switch(store, desk, base, winner["name"], winner["why"])
        report["current"], report["switched_to"] = winner["name"], winner["name"]
    store.set(f"challengers:{desk}", report)
    return report


def use(store, desk: str, name: str) -> str:
    """You pressed Use it: switch a desk to the challenger its latest comparison proved better."""
    report = store.get(f"challengers:{desk}") or {}
    row = next((r for r in report.get("rows", []) if r["name"] == name), None)
    if not row or row["verdict"] != "proven":
        raise ValueError(f"{name} isn't proven better on the {desk} desk (latest comparison: "
                         f"{row['verdict'] if row else 'not compared'})")
    switch(store, desk, report["base"], name, row["why"], by="you")
    store.set(f"challenger_offer:{desk}", None)
    report.update(current=name, waiting_for_you=None, switched_to=name)
    store.set(f"challengers:{desk}", report)
    return f"The {desk} desk now trades {name}."


def lines(store, desks) -> list:
    """The after-market report's section."""
    out = []
    for desk in desks:
        report = store.get(f"challengers:{desk}")
        if not report or not report.get("rows"):
            continue
        if not out:
            out = ["## Challengers (new ideas that must prove themselves first)", ""]
        out.append(f"{desk.title()} desk: trading `{report['current']}`.")
        for r in report["rows"]:
            h, f = r["history"], r["forward"]
            fwd = (f"shadow trading {f['days']} days: {f['return_pct']:+.2f}% vs {f['current_return_pct']:+.2f}%"
                   if f.get("return_pct") is not None else "shadow trading just started")
            out.append(f"- `{r['name']}`: **{r['verdict']}**. History: {h['extra_per_year_pct']:+.1f}% a year vs the "
                       f"current method over {h['years']} years, worst drop {h['max_drawdown_pct']:.1f}% vs "
                       f"{h['current_max_drawdown_pct']:.1f}%. {fwd}. {r['why'][0].upper() + r['why'][1:]}.")
        if report.get("waiting_for_you"):
            out.append(f"- **{report['waiting_for_you']} is proven better: the real-money desk switches only when you "
                       "press Use it in the Thinking tab.**")
        out.append("")
    return out


def summary(store, desks) -> dict:
    """For the Thinking tab: {desk: report}."""
    return {d: store.get(f"challengers:{d}") for d in desks if store.get(f"challengers:{d}")}
