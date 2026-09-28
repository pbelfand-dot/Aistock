"""
study.py: phase 1, "study the market".

Every trading day, each strategy (including the AI) writes down its opinion
on every stock: its score and the price. N trading days later
(study.horizon_days) the bot grades each opinion against what REALLY happened.

After a month you have a real, out-of-sample report card: opinions made
before the outcome was known, graded on the actual outcome. It's the most
honest evidence the bot can collect without risking money.
"""
import pandas as pd

from .engine import closes_table
from .strategies import all_strategies


def study_step(cfg: dict, store, bars: dict, market: pd.DataFrame) -> str:
    """Record today's opinions, then grade old ones. Returns the day that was studied."""
    closes = closes_table(bars)
    today = closes.index[-1].strftime("%Y-%m-%d")
    horizon = cfg["study"]["horizon_days"]
    if not store.get("study_started_on"):
        store.set("study_started_on", pd.Timestamp.today().strftime("%Y-%m-%d"))

    for strategy in all_strategies(cfg):
        scores = strategy.scores(bars, market).reindex(closes.index).iloc[-1]
        for ticker, score in scores.dropna().items():
            price = closes[ticker].iloc[-1]
            if not pd.isna(price):
                store.add_prediction(today, ticker, strategy.name, score, price, horizon)

    graded = grade_predictions(store, closes)
    store.log(f"[study] recorded opinions for {today}; graded {graded} older opinions")
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
    """The study-month report card, one row per strategy.

    signals      how many graded 'buy' opinions it made
    hit_rate     % of those where the price actually went up
    avg_return   average N-day return after a 'buy' opinion
    edge         avg_return minus the average of ALL opinions (just buying everything).
                 Positive edge = its picks beat picking at random."""
    preds = store.predictions()
    preds = preds[preds["actual_return"].notna()]
    rows = []
    for strategy in all_strategies(cfg):
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
