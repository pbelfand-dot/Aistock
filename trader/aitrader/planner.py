"""
planner.py: phase 2, writing the trading plan after the study month.

For every strategy it combines two kinds of evidence:
  1. BACKTEST: years of history replayed with fake money (big sample, but the
     past never repeats exactly)
  2. FORWARD STUDY: the opinions graded during the study month (small sample,
     but truly unseen)

A strategy is picked only if it clears the bars in config.yaml `plan:`.
If NONE do, the plan says so honestly: "don't trade yet". That's a
perfectly good outcome; it just saved you money.

Output: data/trading_plan.json (for the bot) + data/trading_plan.md (for you).
"""
import json
from datetime import date

import pandas as pd

from .config import data_path
from .engine import run_backtest
from .llm import ask_local_llm
from .performance import buy_and_hold, summarize
from .strategies import all_strategies
from .study import forward_report


def build_plan(cfg: dict, store, bars: dict, market: pd.DataFrame) -> dict:
    rules = cfg["plan"]
    forward = forward_report(store, cfg)
    rows = []
    for strategy in all_strategies(cfg):
        print(f"  backtesting {strategy.name} ...")
        bt = run_backtest(strategy, bars, market, cfg)
        fwd = forward.loc[strategy.name].to_dict() if strategy.name in forward.index else {}
        reasons = []
        if bt["sharpe"] < rules["min_sharpe"]:
            reasons.append(f"sharpe {bt['sharpe']} < {rules['min_sharpe']}")
        if bt["profit_factor"] < rules["min_profit_factor"]:
            reasons.append(f"profit factor {bt['profit_factor']} < {rules['min_profit_factor']}")
        if bt["max_drawdown_pct"] > rules["max_drawdown_pct"]:
            reasons.append(f"max drawdown {bt['max_drawdown_pct']}% > {rules['max_drawdown_pct']}%")
        if bt["num_closed_trades"] < rules["min_trades"]:
            reasons.append(f"only {bt['num_closed_trades']} backtest trades")
        signals, edge = fwd.get("signals") or 0, fwd.get("edge_pct")
        if signals < rules["min_forward_signals"]:
            reasons.append(f"only {signals} graded buy signals in the study month")
        elif edge is None or pd.isna(edge) or edge <= 0:
            reasons.append(f"no edge in the study month (edge {edge}%)")
        rows.append({"strategy": strategy.name, "description": strategy.description,
                     "backtest": bt, "forward": fwd, "eligible": not reasons, "rejected_because": reasons})

    bench = run_benchmark(cfg, market, rows)
    eligible = [r for r in rows if r["eligible"]]
    best = max(eligible, key=lambda r: r["backtest"]["sharpe"]) if eligible else None

    plan = {
        "created_on": date.today().isoformat(),
        "verdict": "TRADE" if best else "NO_TRADE",
        "strategy": best["strategy"] if best else None,
        "watchlist": list(bars),
        "benchmark": {"ticker": cfg["benchmark"], **bench},
        "risk": cfg["risk"],
        "promotion_rules": cfg["promotion"],
        "scorecard": rows,
    }
    plan["narrative"] = write_narrative(cfg, plan)
    save_plan(cfg, plan)
    return plan


def run_benchmark(cfg, market, rows) -> dict:
    """Buy-and-hold the benchmark over the same period as the backtests."""
    starts = [r["backtest"]["start"] for r in rows if r["backtest"].get("start")]
    prices = market["close"]
    if starts:
        prices = prices[prices.index >= pd.Timestamp(min(starts))]
    return summarize(buy_and_hold(prices, cfg["paper"]["starting_cash"]))


def write_narrative(cfg: dict, plan: dict) -> str:
    table = scorecard_markdown(plan)
    prompt = (
        "You are a cautious trading coach explaining a plan to a beginner. Using ONLY the numbers "
        "below (never invent numbers), explain in under 250 words: which strategy was chosen and "
        "why (or why none was), the biggest risks, and what to watch during paper trading. "
        f"Verdict: {plan['verdict']}, chosen: {plan['strategy']}.\n\n{table}")
    text = ask_local_llm(cfg, prompt)
    if text:
        return text
    if plan["strategy"]:
        chosen = next(r for r in plan["scorecard"] if r["strategy"] == plan["strategy"])
        return (f"`{plan['strategy']}` cleared every bar: {chosen['description']} "
                "It had the best risk-adjusted backtest (Sharpe) of the strategies that passed. "
                "Remember: a good backtest is a hypothesis, not a promise. Paper trading is the real test.")
    return ("No strategy cleared the bars, so the honest plan is: DON'T TRADE YET. Keep studying, "
            "try different tickers or strategies, and run `python run.py plan` again later.")


def scorecard_markdown(plan: dict) -> str:
    lines = ["| strategy | backtest return % | sharpe | max drawdown % | trades | win rate % | "
             "study buy signals | study edge % | eligible |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in plan["scorecard"]:
        b, f = r["backtest"], r["forward"]
        lines.append(f"| {r['strategy']} | {b['total_return_pct']} | {b['sharpe']} | {b['max_drawdown_pct']} | "
                     f"{b['num_closed_trades']} | {b['win_rate_pct']} | {f.get('signals')} | "
                     f"{f.get('edge_pct')} | {'YES' if r['eligible'] else 'no'} |")
    bench = plan["benchmark"]
    lines.append(f"| *buy & hold {bench['ticker']}* | {bench['total_return_pct']} | {bench['sharpe']} | "
                 f"{bench['max_drawdown_pct']} | - | - | - | - | - |")
    return "\n".join(lines)


def save_plan(cfg: dict, plan: dict):
    data_path(cfg, "trading_plan.json").write_text(json.dumps(plan, indent=2, default=str))
    risk, promo = plan["risk"], plan["promotion_rules"]
    rejected = "\n".join(f"- **{r['strategy']}**: {'; '.join(r['rejected_because'])}"
                         for r in plan["scorecard"] if not r["eligible"]) or "- none"
    md = f"""# Trading Plan: {plan['created_on']}

**Verdict: {plan['verdict']}**{f" (strategy: `{plan['strategy']}`)" if plan['strategy'] else ""}

## In plain English
{plan['narrative']}

## Scorecard
{scorecard_markdown(plan)}

Why the others were rejected:
{rejected}

## The rules the bot will follow
- Watchlist: {', '.join(plan['watchlist'])}
- At most {risk['max_open_positions']} positions, each at most {risk['max_position_pct']}% of the account
- Stop-loss: sell any position that falls {risk['stop_loss_pct']}% below its buy price
- Daily loss limit: down {risk['daily_loss_limit_pct']}% in a day means no new buys that day
- Kill switch: down {risk['max_drawdown_pct']}% from the best day means sell everything and stop

## What must happen before real money
- At least {promo['min_trading_days']} trading days of paper trading and {promo['min_closed_trades']} closed trades
- Total return above {promo['min_total_return_pct']}%, profit factor at least {promo['min_profit_factor']}
- Max drawdown no worse than {promo['max_drawdown_pct']}%{"; must beat buy-and-hold " + plan['benchmark']['ticker'] if promo.get('must_beat_benchmark') else ""}
- Then YOU confirm with `python run.py promote`

_Next step: read this, then run `python run.py approve-plan` to start paper trading._
"""
    data_path(cfg, "trading_plan.md").write_text(md)


def load_plan(cfg: dict) -> dict:
    path = data_path(cfg, "trading_plan.json")
    if not path.exists():
        raise RuntimeError("No trading plan yet. Finish the study month, then run: python run.py plan")
    return json.loads(path.read_text())
