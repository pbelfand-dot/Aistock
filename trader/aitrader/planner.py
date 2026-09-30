"""
planner.py: phase 2, writing a desk's trading plan after the study month.

For every strategy it combines two kinds of evidence:
  1. BACKTEST: all the history we have, replayed with fake money (big
     sample, but the past never repeats exactly)
  2. STUDY MONTH: swing = the graded opinions; day = the shadow trades
     (small sample, but truly unseen)

A strategy is picked only if it clears the bars in config.yaml `plan:`.
If NONE do, the plan says so honestly: "don't trade yet". That's a
perfectly good outcome; it just saved you money.

Output: data/trading_plan_<desk>.json (for the bot) + .md (for you).
"""
import json
from datetime import date

import pandas as pd

from .config import data_path, desk_capital
from .engine import run_backtest
from .llm import ask_local_llm
from .performance import buy_and_hold, summarize
from .strategies import all_strategies
from .study import forward_report


def build_plan(cfg: dict, store, desk: str, bars: dict, market: pd.DataFrame) -> dict:
    rules = cfg["plan"]
    since = store.get("study_started_on")
    swing_card = forward_report(store, cfg) if desk == "swing" else None
    rows = []
    for strategy in all_strategies(cfg, desk):
        print(f"  backtesting {desk}/{strategy.name} ...")
        scores = strategy.scores(bars, market)
        bt = run_backtest(strategy, bars, market, cfg, desk, scores=scores)
        reasons = []
        if bt["sharpe"] < rules["min_sharpe"]:
            reasons.append(f"sharpe {bt['sharpe']} < {rules['min_sharpe']}")
        if bt["profit_factor"] < rules["min_profit_factor"]:
            reasons.append(f"profit factor {bt['profit_factor']} < {rules['min_profit_factor']}")
        if bt["max_drawdown_pct"] > rules["max_drawdown_pct"]:
            reasons.append(f"max drawdown {bt['max_drawdown_pct']}% > {rules['max_drawdown_pct']}%")
        if bt["num_closed_trades"] < rules["min_trades"]:
            reasons.append(f"only {bt['num_closed_trades']} backtest trades")

        if desk == "swing":
            fwd = swing_card.loc[strategy.name].to_dict() if strategy.name in swing_card.index else {}
            signals, edge = int(fwd.get("signals") or 0), fwd.get("edge_pct")
            edge_text = "n/a" if edge is None or pd.isna(edge) else f"{edge:.2f}%"
            fwd["summary"] = f"{signals} graded buy opinions, edge {edge_text}"
            if signals < rules["min_forward_signals"]:
                reasons.append(f"only {signals} graded buy opinions in the study month")
            elif edge is None or pd.isna(edge) or edge <= 0:
                reasons.append(f"no edge in the study month (edge {edge_text})")
        else:
            fwd = run_backtest(strategy, bars, market, cfg, desk, scores=scores, start=since)
            fwd["summary"] = f"{fwd['num_closed_trades']} shadow trades, {fwd['total_return_pct']:.2f}% return"
            if fwd["num_closed_trades"] < rules["min_forward_trades"]:
                reasons.append(f"only {fwd['num_closed_trades']} shadow trades in the study month")
            elif fwd["total_return_pct"] <= 0:
                reasons.append(f"lost money shadow trading in the study month ({fwd['total_return_pct']}%)")
        rows.append({"strategy": strategy.name, "description": strategy.description,
                     "backtest": bt, "forward": fwd, "eligible": not reasons, "rejected_because": reasons})

    eligible = [r for r in rows if r["eligible"]]
    best = max(eligible, key=lambda r: r["backtest"]["sharpe"]) if eligible else None
    plan = {
        "desk": desk,
        "created_on": date.today().isoformat(),
        "verdict": "TRADE" if best else "NO_TRADE",
        "strategy": best["strategy"] if best else None,
        "watchlist": list(bars),
        "capital": desk_capital(cfg, desk, live=False),
        "benchmark": {"ticker": cfg["benchmark"], **run_benchmark(cfg, desk, market, rows)},
        "desk_settings": cfg["desks"][desk],
        "promotion_rules": cfg["promotion"],
        "scorecard": rows,
    }
    plan["narrative"] = write_narrative(cfg, plan)
    save_plan(cfg, plan)
    return plan


def run_benchmark(cfg, desk, market, rows) -> dict:
    """Buy-and-hold the benchmark over the same period as the backtests (daily closes)."""
    starts = [r["backtest"]["start"] for r in rows if r["backtest"].get("start")]
    closes = market["close"].groupby(market.index.normalize()).last()
    if starts:
        closes = closes[closes.index >= pd.Timestamp(min(starts))]
    return summarize(buy_and_hold(closes, desk_capital(cfg, desk, live=False)))


def write_narrative(cfg: dict, plan: dict) -> str:
    prompt = (
        "You are a cautious trading coach explaining a plan to a beginner. Using ONLY the numbers "
        "below (never invent numbers), explain in under 250 words: which strategy was chosen and "
        "why (or why none was), the biggest risks, and what to watch during paper trading. "
        f"Desk: {plan['desk']} trading. Verdict: {plan['verdict']}, chosen: {plan['strategy']}.\n\n"
        f"{scorecard_markdown(plan)}")
    text = ask_local_llm(cfg, prompt)
    if text:
        return text
    if plan["strategy"]:
        chosen = next(r for r in plan["scorecard"] if r["strategy"] == plan["strategy"])
        return (f"`{plan['strategy']}` cleared every bar: {chosen['description']} "
                "It had the best risk-adjusted backtest (Sharpe) of the strategies that passed. "
                "Remember: a good backtest is a hypothesis, not a promise. Paper trading is the real test.")
    return ("No strategy cleared the bars, so the honest plan is: DON'T TRADE THIS DESK YET. Keep "
            "studying, try different tickers or strategies, and run `python run.py plan` again later.")


def scorecard_markdown(plan: dict) -> str:
    if not plan["scorecard"]:                         # Stage 1: the evidence is the 16-year research
        return plan.get("evidence", "No scorecard.")
    lines = ["| strategy | backtest return % | sharpe | max drawdown % | trades | win rate % | "
             "study month | eligible |",
             "|---|---|---|---|---|---|---|---|"]
    for r in plan["scorecard"]:
        b = r["backtest"]
        lines.append(f"| {r['strategy']} | {b['total_return_pct']} | {b['sharpe']} | {b['max_drawdown_pct']} | "
                     f"{b['num_closed_trades']} | {b['win_rate_pct']} | {r['forward'].get('summary')} | "
                     f"{'YES' if r['eligible'] else 'no'} |")
    bench = plan["benchmark"]
    lines.append(f"| *buy & hold {bench['ticker']}* | {bench['total_return_pct']} | {bench['sharpe']} | "
                 f"{bench['max_drawdown_pct']} | - | - | - | - |")
    return "\n".join(lines)


def save_plan(cfg: dict, plan: dict):
    desk = plan["desk"]
    data_path(cfg, f"trading_plan_{desk}.json").write_text(json.dumps(plan, indent=2, default=str))
    s, risk, promo = plan["desk_settings"], plan["desk_settings"]["risk"], plan["promotion_rules"]
    rejected = "\n".join(f"- **{r['strategy']}**: {'; '.join(r['rejected_because'])}"
                         for r in plan["scorecard"] if not r["eligible"]) or "- none"
    timing = ("Decides once a day, 15 minutes before the close. Holds days to weeks."
              if desk == "swing" else
              f"Decides every 5 minutes. No new trades in the last {s['last_entry_minutes_before_close']} "
              f"minutes; sells everything {s['flatten_minutes_before_close']} minutes before the close. "
              "Never holds overnight.")
    next_step = (f"_Stage 1 started by you on {plan['created_on']}: paper trading with pretend money for "
                 f"{promo['min_trading_days']} trading days._" if plan.get("stage") == 1 else
                 f"_Next step: read this, then run `python run.py approve-plan --desk {desk}` to start paper trading._")
    md = f"""# {desk.title()} desk trading plan: {plan['created_on']}

**Verdict: {plan['verdict']}**{f" (strategy: `{plan['strategy']}`)" if plan['strategy'] else ""}

## In plain English
{plan['narrative']}

## Scorecard
{scorecard_markdown(plan)}

Why the others were rejected:
{rejected}

## The rules the bot will follow
- Money: ${plan['capital']:,.0f} (this desk's share)
- Watchlist: {', '.join(plan['watchlist'])}
- Timing: {timing}
- At most {risk['max_open_positions']} positions, each at most {risk['max_position_pct']}% of the desk's money
- Stop-loss: sell any position that falls {risk['stop_loss_pct']}% below its buy price
- Daily loss limit: desk down {risk['daily_loss_limit_pct']}% in a day means no new buys that day
- Kill switch: desk down {risk['max_drawdown_pct']}% from its best day means sell everything and stop

## What must happen before real money
- At least {promo['min_trading_days']} trading days of paper trading and {promo['min_closed_trades']} closed trades
- Total return above {promo['min_total_return_pct']}%, profit factor at least {promo['min_profit_factor']}
- Max drawdown no worse than {promo['max_drawdown_pct']}%{"; must beat buy-and-hold " + plan['benchmark']['ticker'] if promo.get('must_beat_benchmark') else ""}
- Then YOU confirm with `python run.py promote --desk {desk}`

{next_step}
"""
    data_path(cfg, f"trading_plan_{desk}.md").write_text(md)


STAGE1_DESK, STAGE1_STRATEGY = "swing", "momentum"
STAGE1_EVIDENCE = """No backtest on this computer: Stage 1 rests on the 16-year test in
research/history/RESULTS-methods.md (Jan 2011 to Sep 2026, same rules for every method).

- Momentum was the one stock-picking method with real-world support. The test's numbers for it
  (29.9% a year with the trend filter) are flattered: the stock list only has today's survivors.
- The honest expectation comes from a real momentum fund (iShares MTUM): about 15.6-16% a year
  since 2013, when SPY made 14.4%. That is the market plus a point or two, with bigger drops.
- The bot's old swing rules on its old watchlist made 1-2% a year. Stage 1 doesn't use them.
- Even the best method made money AND beat SPY in only about half of all 30-trading-day windows.
  Thirty days can catch a broken method; it can't prove a good one."""


def stage1_plan(cfg: dict, candidates: list = ()) -> dict:
    """Stage 1 of your plan: the swing desk paper trades the momentum method, starting now (no study
    month). Nothing is backtested here, so it takes a second; the plan cites the research instead."""
    desk = STAGE1_DESK
    watchlist = list(dict.fromkeys([*cfg["desks"][desk]["watchlist"], *candidates]))
    strategy = next(s for s in all_strategies(cfg, desk) if s.name == STAGE1_STRATEGY)
    plan = {
        "desk": desk,
        "stage": 1,
        "created_on": date.today().isoformat(),
        "verdict": "TRADE",
        "strategy": STAGE1_STRATEGY,
        "watchlist": watchlist,
        "capital": desk_capital(cfg, desk, live=False),
        "benchmark": {"ticker": cfg["benchmark"]},
        "desk_settings": cfg["desks"][desk],
        "promotion_rules": cfg["promotion"],
        "scorecard": [],
        "evidence": STAGE1_EVIDENCE,
        "narrative": (f"Stage 1, started by you: paper trading (pretend money) with `{STAGE1_STRATEGY}`. "
                      f"{strategy.description} The list it picks from is the watchlist plus the top of "
                      "the daily all-stocks scan, so it can own any US stock that's strong enough and "
                      "affordable. The stop-loss, daily loss limit, kill switch and good faith violation "
                      "rules all apply, and it learns from every finished trade (smaller or paused if the "
                      "method loses, never bigger). Watch whether it keeps up with the S&P 500: that's "
                      "the bar it must clear before real money."),
    }
    save_plan(cfg, plan)
    return plan


def load_plan(cfg: dict, desk: str) -> dict:
    path = data_path(cfg, f"trading_plan_{desk}.json")
    if not path.exists():
        raise RuntimeError(f"No {desk} trading plan yet. Finish the study month, then run: python run.py plan")
    return json.loads(path.read_text())
