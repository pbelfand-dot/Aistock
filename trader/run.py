"""
run.py: the ONE file you run. Every command:

    python run.py status          where am I, and what's next?
    python run.py daily           do today's job for the current phase (schedule this daily)
    python run.py backtest        test every strategy on years of history (any time)

    python run.py plan            after the study month: write the trading plan
    python run.py approve-plan    you read the plan and say yes -> paper trading starts
    python run.py promote         paper results good enough? -> you confirm -> real money
    python run.py kill            EMERGENCY: cancel orders, sell the bot's positions, stop
    python run.py resume          un-halt after a kill (you've looked into what happened)

    python run.py schwab-login    log in to Schwab (needed about once a week)
"""
import argparse
import sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd

from aitrader.brokers import Ledger, Order, PaperBroker
from aitrader.config import data_path, load_config
from aitrader.engine import closes_table, run_backtest, run_trading_day
from aitrader.market_data import MarketData
from aitrader.performance import buy_and_hold, summarize
from aitrader.phases import STEP_NUMBER, Phase, check_promotion, current_phase, set_phase, study_progress
from aitrader.planner import build_plan, load_plan
from aitrader.risk import RiskManager
from aitrader.storage import Store
from aitrader.strategies import all_strategies, get_strategy
from aitrader.study import forward_report, study_step

NEW_YORK = ZoneInfo("America/New_York")


# ---------------------------------------------------------------- helpers
def market_is_open(latest_bar_date: str) -> bool:
    """Weekday, 9:30am-4:00pm New York time, and today's prices exist (so not a holiday).
    Known gap: early-close days (e.g. the day after Thanksgiving) aren't detected."""
    now = datetime.now(NEW_YORK)
    return (now.weekday() < 5 and dtime(9, 30) <= now.time() < dtime(16, 0)
            and latest_bar_date == now.strftime("%Y-%m-%d"))


def open_broker(cfg, store, phase: Phase, dry_run=False, emergency=False):
    cash_account = cfg["live"]["account_type"] == "cash"
    if phase == Phase.PAPER:
        saved = store.get("paper_ledger")
        ledger = Ledger.from_dict(saved) if saved else Ledger(cfg["paper"]["starting_cash"])
        return PaperBroker(ledger, cfg["paper"]["slippage_pct"], cfg["paper"]["commission_per_trade"],
                           mode="paper", cash_account=cash_account)

    # LIVE: real money. Several locks must all be open (except for an emergency sell-off).
    if not cfg["live_trading_enabled"] and not dry_run and not emergency:
        raise RuntimeError("LIVE_TRADING_ENABLED is not 'true' in .env; refusing to send real orders.")
    from aitrader.brokers.schwab_broker import SchwabBroker
    from aitrader.schwab_api import account_hash, get_client
    client = get_client(cfg)
    saved = store.get("live_ledger")
    ledger = Ledger.from_dict(saved) if saved else Ledger(cfg["live"]["max_capital"])
    broker = SchwabBroker(ledger, client, account_hash(client, cfg["secrets"]["account_number"]),
                          cfg["live"]["limit_buffer_pct"], cfg["live"]["fill_timeout_seconds"],
                          cash_account=cash_account, dry_run=dry_run, log=store.log)
    for problem in broker.reconcile():
        store.log(f"[live] RECONCILE: {problem}")
    return broker


def save_broker(store, broker):
    store.set(f"{broker.mode}_ledger", broker.ledger.to_dict())


def emergency_stop(cfg, store, broker, prices, today, reason):
    """Cancel everything, sell every position the bot opened, halt."""
    store.log(f"!!! EMERGENCY STOP ({broker.mode}): {reason}")
    broker.cancel_all()
    for ticker, pos in broker.positions().items():
        price = prices.get(ticker)
        price = pos.avg_cost if price is None or pd.isna(price) else float(price)
        fill = broker.submit(Order(ticker, "SELL", pos.qty, price, f"EMERGENCY STOP: {reason}"), today)
        if fill:
            store.record_fill(broker.mode, fill)
            store.log(f"[{broker.mode}] SOLD {fill.qty} {ticker} @ ${fill.price:.2f}")
        else:
            store.log(f"!!! COULD NOT SELL {ticker}. CHECK YOUR SCHWAB ACCOUNT BY HAND.")
    save_broker(store, broker)
    store.set("halted", True)
    if current_phase(store) == Phase.LIVE:
        set_phase(store, Phase.PAPER, f"demoted: {reason}")
        reset_paper(store)


def reset_paper(store):
    store.clear_mode("paper")
    store.set("paper_ledger", None)
    store.set("paper_peak_equity", None)


def latest_date(bars) -> str:
    return closes_table(bars).index[-1].strftime("%Y-%m-%d")


def print_table(rows, columns):
    print(pd.DataFrame(rows, columns=columns).to_string(index=False))


# ---------------------------------------------------------------- commands
def cmd_status(cfg, store, args):
    phase = current_phase(store)
    print(f"\n=== AI TRADER: phase {phase.value} (step {STEP_NUMBER[phase]} of 4) ===")
    if store.get("halted"):
        print("  HALTED after a kill/kill-switch. Review the journal, then: python run.py resume")

    p = study_progress(store, cfg)
    print(f"  Study: {p['calendar_days']} calendar days, {p['study_days']} trading days recorded"
          + ("" if p["ready"] else f" (still need: {', '.join(p['missing'])})"))
    report = forward_report(store, cfg)
    if report["signals"].sum() > 0:
        print("  Study report card (graded 'buy' opinions):")
        print("    " + report.to_string().replace("\n", "\n    "))

    for mode in ("paper", "live"):
        curve = store.equity_curve(mode)
        if len(curve):
            s = summarize(curve, store.fills(mode))
            print(f"  {mode.upper()}: ${curve.iloc[-1]:,.2f}  return {s['total_return_pct']}%  "
                  f"trades {s['num_closed_trades']}  win {s['win_rate_pct']}%  max drawdown {s['max_drawdown_pct']}%")

    from aitrader.schwab_api import token_days_left
    left = token_days_left(cfg)
    print("  Schwab login: " + ("not logged in" if left is None else
                                "EXPIRED: run schwab-login" if left <= 0 else f"expires in {left:.1f} days"))

    nxt = {Phase.STUDY: "run `python run.py daily` each trading day; `plan` when the study month is done",
           Phase.PLAN_REVIEW: "read data/trading_plan.md, then `python run.py approve-plan`",
           Phase.PAPER: "keep running `daily`; try `python run.py promote` when results look good",
           Phase.LIVE: "keep running `daily`; log in to Schwab weekly; watch the journal"}
    print(f"  Next: {nxt[phase]}")
    print("\n  Recent journal:")
    for ts, msg in store.journal(8):
        print(f"    {ts}  {msg}")


def cmd_daily(cfg, store, args):
    data = MarketData(cfg)
    bars, market = data.load()
    study_step(cfg, store, bars, market)          # the bot keeps learning in every phase
    phase = current_phase(store)
    if phase == Phase.STUDY:
        p = study_progress(store, cfg)
        print("Study month complete! Run: python run.py plan" if p["ready"]
              else f"Studying... still need {', '.join(p['missing'])}")
    elif phase == Phase.PLAN_REVIEW:
        print("Waiting for you: read data/trading_plan.md, then run: python run.py approve-plan")
    else:
        if phase == Phase.LIVE:
            from aitrader.schwab_api import token_days_left
            left = token_days_left(cfg)
            if left is not None and left < 1.5:
                store.log(f"WARNING: Schwab login expires in {left:.1f} days. Run: python run.py schwab-login")
        cmd_trade(cfg, store, args, bars, market)


def cmd_trade(cfg, store, args, bars=None, market=None):
    phase = current_phase(store)
    if phase not in (Phase.PAPER, Phase.LIVE):
        print(f"No trading in phase {phase.value}.")
        return
    if store.get("halted"):
        print("Bot is HALTED. Review the journal, then: python run.py resume")
        return
    if bars is None:
        bars, market = MarketData(cfg).load()
    today = latest_date(bars)
    anyway = getattr(args, "anyway", False) and phase == Phase.PAPER
    if not market_is_open(today) and not anyway:
        print("Market is closed (or today's prices aren't in yet). No trading.")
        return

    dry_run = getattr(args, "dry_run", False)
    mode = "live" if phase == Phase.LIVE else "paper"
    if store.get(f"{mode}_last_trade_date") == today and not dry_run:
        print(f"Already traded today ({today}).")
        return

    strategy = get_strategy(load_plan(cfg)["strategy"], cfg)
    broker = open_broker(cfg, store, phase, dry_run=dry_run)
    work_store = Store(":memory:") if dry_run else store     # a dry run saves nothing
    result = run_trading_day(work_store, broker, strategy, RiskManager.from_config(cfg), bars, market, today)
    if dry_run:
        print("Dry run finished; nothing was saved or sent.")
        return
    if result["kill_switch"]:
        emergency_stop(cfg, store, broker, closes_table(bars).iloc[-1], today,
                       f"kill switch: equity ${result['equity']:,.2f} is more than "
                       f"{cfg['risk']['max_drawdown_pct']}% below its peak ${result['peak']:,.2f}")
        return
    save_broker(store, broker)
    store.set(f"{mode}_last_trade_date", today)
    print(f"[{mode}] account value: ${result['equity']:,.2f}")


def cmd_backtest(cfg, store, args):
    bars, market = MarketData(cfg).load()
    rows = []
    strategies = [get_strategy(args.strategy, cfg)] if args.strategy else all_strategies(cfg)
    for s in strategies:
        print(f"  backtesting {s.name} ...")
        r = run_backtest(s, bars, market, cfg)
        rows.append([s.name, r["start"], r["total_return_pct"], r["cagr_pct"], r["sharpe"],
                     r["max_drawdown_pct"], r["num_closed_trades"], r["win_rate_pct"], r["profit_factor"]])
    start = min((r[1] for r in rows if r[1]), default=None)
    prices = market["close"] if start is None else market["close"][market.index >= pd.Timestamp(start)]
    b = summarize(buy_and_hold(prices, cfg["paper"]["starting_cash"]))
    rows.append([f"buy&hold {cfg['benchmark']}", start, b["total_return_pct"], b["cagr_pct"], b["sharpe"],
                 b["max_drawdown_pct"], "-", "-", "-"])
    print_table(rows, ["strategy", "from", "return%", "yearly%", "sharpe", "maxDD%", "trades", "win%", "PF"])


def cmd_plan(cfg, store, args):
    phase = current_phase(store)
    if phase not in (Phase.STUDY, Phase.PLAN_REVIEW):
        print(f"Already past planning (phase {phase.value}).")
        return
    p = study_progress(store, cfg)
    if not p["ready"]:
        if not args.force:
            print(f"Not yet. The study month needs: {', '.join(p['missing'])}.")
            return
        store.log("WARNING: plan forced before the study month finished (testing only)")
    bars, market = MarketData(cfg).load()
    plan = build_plan(cfg, store, bars, market)
    print(f"\nPlan written: {data_path(cfg, 'trading_plan.md')}")
    if plan["verdict"] == "TRADE":
        set_phase(store, Phase.PLAN_REVIEW, f"plan picked {plan['strategy']}")
        print("Read it, then run: python run.py approve-plan")
    else:
        if phase == Phase.PLAN_REVIEW:
            set_phase(store, Phase.STUDY, "new plan says NO_TRADE")
        store.log("Plan verdict NO_TRADE; staying in STUDY")
        print("No strategy was good enough. Staying in STUDY (that's the bot protecting your money).")


def cmd_approve_plan(cfg, store, args):
    if current_phase(store) != Phase.PLAN_REVIEW:
        print("There's no plan waiting for approval.")
        return
    plan = load_plan(cfg)
    print(f"Plan from {plan['created_on']}: trade `{plan['strategy']}` with FAKE money first.")
    print(f"Full plan: {data_path(cfg, 'trading_plan.md')}")
    if input("Type YES to start paper trading: ").strip() != "YES":
        print("Not approved.")
        return
    reset_paper(store)
    set_phase(store, Phase.PAPER, "plan approved by you")


def cmd_promote(cfg, store, args):
    if current_phase(store) != Phase.PAPER:
        print("Promotion to LIVE only happens from PAPER.")
        return
    curve = store.equity_curve("paper")
    if len(curve) < 2:
        print("Not enough paper trading yet.")
        return
    _, market = MarketData(cfg).load()
    bench = market["close"][market.index >= curve.index[0]]
    bench_ret = (bench.iloc[-1] / bench.iloc[0] - 1) * 100 if len(bench) > 1 else 0.0
    checks = check_promotion(cfg, summarize(curve, store.fills("paper")), bench_ret)
    print_table([[n, a, r, "PASS" if ok else "FAIL"] for n, a, r, ok in checks],
                ["rule", "actual", "required", "result"])
    if not all(ok for *_, ok in checks):
        print("\nNot yet. Keep paper trading; the bot hasn't earned real money.")
        return
    if not cfg["live_trading_enabled"]:
        print("\nPaper results pass! To go live, set LIVE_TRADING_ENABLED=true in .env and run this again.")
        return
    from aitrader.schwab_api import account_hash, get_client
    account_hash(get_client(cfg), cfg["secrets"]["account_number"])   # proves the Schwab login works
    print(f"\nThe bot will trade REAL money, capped at ${cfg['live']['max_capital']:,}.")
    print("Past results don't guarantee future results. Only use money you can afford to lose.")
    if input("Type REAL MONEY to confirm: ").strip() != "REAL MONEY":
        print("Not promoted.")
        return
    store.set("live_ledger", Ledger(cfg["live"]["max_capital"]).to_dict())
    store.set("live_peak_equity", None)
    set_phase(store, Phase.LIVE, "paper results passed every rule; confirmed by you")


def cmd_kill(cfg, store, args):
    phase = current_phase(store)
    if phase not in (Phase.PAPER, Phase.LIVE):
        print(f"Nothing to stop in phase {phase.value}.")
        store.set("halted", True)
        return
    bars, _ = MarketData(cfg).load()
    broker = open_broker(cfg, store, phase, emergency=True)
    emergency_stop(cfg, store, broker, closes_table(bars).iloc[-1], latest_date(bars), "manual kill command")


def cmd_resume(cfg, store, args):
    store.set("halted", False)
    store.log(f"Resumed by you (phase {current_phase(store).value})")


def cmd_schwab_login(cfg, store, args):
    from aitrader.schwab_api import login
    login(cfg, manual=args.manual)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI trader for Charles Schwab")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("daily").add_argument("--dry-run", action="store_true", help="live: show orders, send nothing")
    t = sub.add_parser("trade")
    t.add_argument("--dry-run", action="store_true", help="live: show orders, send nothing")
    t.add_argument("--anyway", action="store_true", help="paper only: trade even if the market is closed")
    sub.add_parser("study")
    sub.add_parser("backtest").add_argument("--strategy", help="only this strategy")
    sub.add_parser("plan").add_argument("--force", action="store_true", help="skip the 30-day wait (TESTING ONLY)")
    sub.add_parser("approve-plan")
    sub.add_parser("promote")
    sub.add_parser("kill")
    sub.add_parser("resume")
    sub.add_parser("schwab-login").add_argument("--manual", action="store_true",
                                                help="print a login link instead of opening a browser")
    args = parser.parse_args(argv)

    cfg = load_config()
    store = Store(data_path(cfg, "aitrader.sqlite"))
    if args.command == "study":
        bars, market = MarketData(cfg).load()
        study_step(cfg, store, bars, market)
        return
    commands = {"status": cmd_status, "daily": cmd_daily, "trade": cmd_trade, "backtest": cmd_backtest,
                "plan": cmd_plan, "approve-plan": cmd_approve_plan, "promote": cmd_promote,
                "kill": cmd_kill, "resume": cmd_resume, "schwab-login": cmd_schwab_login}
    try:
        commands[args.command](cfg, store, args)
    except RuntimeError as e:
        store.log(f"STOPPED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
