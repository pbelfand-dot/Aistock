"""
study.py: phase 1, "study the market". Runs every trading day after the close.

Swing desk: every strategy (including the AI) writes down its opinion on
every stock, with the price. 5 trading days later the bot grades each
opinion against what REALLY happened.

Day desk: every day strategy is "shadow traded" on the day's real 5-minute
prices with fake money, using exactly the same rules as paper trading.

After a month you have an honest, out-of-sample report card: decisions made
before the outcome was known, graded on the actual outcome. It's the best
evidence the bot can collect without risking money.
"""
import pandas as pd

from .engine import closes_table, run_backtest
from .strategies import all_strategies, current_scores


def start_study_clock(store):
    if not store.get("study_started_on"):
        store.set("study_started_on", pd.Timestamp.today().strftime("%Y-%m-%d"))


def record_study_day(store, day: str):
    store.set("study_days", sorted(set(store.get("study_days", [])) | {day}))


# ---------------------------------------------------------------- swing desk
def study_swing(cfg: dict, store, bars: dict, market: pd.DataFrame) -> str:
    """Record today's opinions, then grade old ones. Returns the day that was studied."""
    start_study_clock(store)
    closes = closes_table(bars)
    today = closes.index[-1].strftime("%Y-%m-%d")
    horizon = cfg["study"]["horizon_days"]

    for strategy in all_strategies(cfg, "swing"):
        for ticker, score in current_scores(strategy, bars, market).dropna().items():
            price = closes[ticker].iloc[-1]
            if not pd.isna(price):
                store.add_prediction(today, ticker, strategy.name, score, price, horizon)

    graded = grade_predictions(store, closes)
    record_study_day(store, today)
    store.log(f"[study] swing: recorded opinions for {today}; graded {graded} older opinions")
    return today


def grade_predictions(store, closes: pd.DataFrame) -> int:
    """Fill in what actually happened for opinions whose waiting period is over."""
    graded = 0
    for row in store.predictions(only_open=True).itertuples():
        if row.ticker not in closes:
            continue
        series = closes[row.ticker].dropna()
        pos = series.index.searchsorted(pd.Timestamp(row.made_on))
        target = pos + row.horizon_days
        if pos < len(series) and series.index[pos] == pd.Timestamp(row.made_on) and target < len(series):
            actual = series.iloc[target] / row.price - 1
            store.resolve_prediction(row.id, actual, series.index[target].strftime("%Y-%m-%d"))
            graded += 1
    return graded


def forward_report(store, cfg: dict) -> pd.DataFrame:
    """Swing desk report card, one row per strategy.

    signals      how many graded 'buy' opinions it made
    hit_rate     % of those where the price actually went up
    avg_return   average 5-day return after a 'buy' opinion
    edge         avg_return minus the average of ALL opinions (just buying everything).
                 Positive edge = its picks beat picking at random."""
    preds = store.predictions()
    preds = preds[preds["actual_return"].notna()]
    rows = []
    for strategy in all_strategies(cfg, "swing"):
        mine = preds[preds["strategy"] == strategy.name]
        buys = mine[mine["score"] >= strategy.buy_above]
        baseline = mine["actual_return"].mean() if len(mine) else float("nan")
        avg = buys["actual_return"].mean() if len(buys) else float("nan")
        rows.append({
            "strategy": strategy.name,
            "signals": int(len(buys)),
            "hit_rate_pct": round((buys["actual_return"] > 0).mean() * 100, 1) if len(buys) else None,
            "avg_return_pct": round(avg * 100, 3) if len(buys) else None,
            "edge_pct": round((avg - baseline) * 100, 3) if len(buys) else None,
        })
    return pd.DataFrame(rows).set_index("strategy")


# ---------------------------------------------------------------- day desk
def study_day(cfg: dict, store, bars: dict, market: pd.DataFrame) -> dict:
    """Shadow-trade every day strategy from the start of the study month until now."""
    start_study_clock(store)
    since = store.get("study_started_on")
    today = closes_table(bars).index[-1].strftime("%Y-%m-%d")
    results = {}
    for strategy in all_strategies(cfg, "day"):
        scores = strategy.scores(bars, market, since=since)
        r = run_backtest(strategy, bars, market, cfg, "day", scores=scores, start=since)
        results[strategy.name] = {k: r[k] for k in ("trading_days", "total_return_pct", "num_closed_trades",
                                                     "win_rate_pct", "profit_factor", "max_drawdown_pct")}
    report = {"as_of": today, "since": since, "results": results}
    store.set("day_shadow_report", report)
    record_study_day(store, today)
    store.log(f"[study] day: shadow-traded {len(results)} strategies since {since}")
    return report


def day_forward_report(store) -> pd.DataFrame:
    report = store.get("day_shadow_report")
    if not report:
        return pd.DataFrame()
    return pd.DataFrame(report["results"]).T
