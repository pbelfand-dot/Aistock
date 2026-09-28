"""
run.py: the ONE file you run.

    python run.py autopilot       START THIS AND LEAVE IT RUNNING. Every trading day it:
                                    - day desk: decides every 5 minutes, sells out before the close
                                    - swing desk: watches stop-losses, decides at 3:45pm
                                    - studies after the close (grading, shadow trading)
    python run.py status          where is each desk, and what's next?
    python run.py backtest        test every strategy on history (any time)

    python run.py plan            after the study month: write each desk's trading plan
    python run.py approve-plan    you read a plan and say yes -> that desk starts paper trading
    python run.py promote         paper results good enough? -> you confirm -> that desk trades real money
    python run.py kill            EMERGENCY: cancel orders, sell everything the bot owns, stop
    python run.py resume          un-halt after a kill (after you've looked into what happened)
    python run.py schwab-login    log in to Schwab (needed about once a week)

Most commands take --desk swing or --desk day (default: both).
For testing: `study` runs today's study once; `trade --desk day --anyway` runs one paper cycle.
"""
import argparse
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, time as dtime, timedelta

import pandas as pd

from aitrader.brokers import Ledger, Order, PaperBroker
from aitrader.config import active_desks, data_path, desk_capital, load_config
from aitrader.engine import run_backtest, run_cycle
from aitrader.market_data import MarketData
from aitrader.market_hours import in_session, minutes_to_close, now_ny, session_close
from aitrader.performance import buy_and_hold, summarize
from aitrader.phases import (STEP_NUMBER, Phase, check_promotion, current_phase, mode_of, set_phase,
                             study_progress)
from aitrader.planner import build_plan, load_plan
from aitrader.risk import RiskManager
from aitrader.storage import Store
from aitrader.strategies import all_strategies, get_strategy
from aitrader.study import day_forward_report, forward_report, study_day, study_swing

TRADING = (Phase.PAPER, Phase.LIVE)


# ================================================================ helpers
def pick_desks(cfg, args) -> list:
    desk = getattr(args, "desk", None)
    return [desk] if desk else active_desks(cfg)


@contextmanager
def trading_lock(cfg, wait_seconds=180):
    """Only one bot process may trade at a time. E.g. if you run `kill` while the autopilot
    is mid-cycle, kill waits for that cycle to finish instead of both editing the checkbook."""
    path = data_path(cfg, "trading.lock")
    deadline = time.time() + wait_seconds
    while True:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 600:     # left behind by a crashed process
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                raise RuntimeError("another bot process has been trading for minutes; try again")
            time.sleep(1)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def load_desk(cfg, store, data, desk, keep=(), live=False):
    """A desk's prices, minus stocks too expensive to ever buy (unless we already own them)."""
    bars, market = data.load(desk, extra=keep)
    limit = RiskManager.for_desk(cfg, desk).max_share_price(desk_capital(cfg, desk, live))
    too_pricey = {t: round(float(df["close"].iloc[-1]), 2) for t, df in bars.items()
                  if df["close"].iloc[-1] > limit and t not in keep}
    store.set(f"too_pricey:{desk}", {"limit": round(limit, 2), "tickers": too_pricey})
    return {t: df for t, df in bars.items() if t not in too_pricey}, market


def fill_recorder(store, mode, dry_run=False):
    """Saves each fill to the database and journal the moment it happens."""
    def record(f):
        pnl = f" (P&L ${f.realized_pnl:+.2f})" if f.side == "SELL" else ""
        line = f"[{mode}] {f.side} {f.qty} {f.ticker} @ ${f.price:.2f}{pnl}: {f.reason}"
        if dry_run:
            print(f"[DRY RUN] {line}")
            return
        store.record_fill(mode, f)
        store.log(line)
    return record


def open_broker(cfg, store, desk, phase, dry_run=False, emergency=False):
    mode = mode_of(phase, desk)
    saved = store.get(f"{mode}_ledger")
    cash_account = cfg["live"]["account_type"] == "cash"
    if phase != Phase.LIVE:
        ledger = Ledger.from_dict(saved) if saved else Ledger(desk_capital(cfg, desk, live=False))
        broker = PaperBroker(ledger, cfg["paper"]["slippage_pct"], cfg["paper"]["commission_per_trade"],
                             mode=mode, cash_account=cash_account)
        broker.on_fill = fill_recorder(store, mode, dry_run)
        return broker

    # LIVE: real money. Several locks must all be open (except for an emergency sell-off).
    if not emergency:
        if not cfg["live_trading_enabled"] and not dry_run:
            raise RuntimeError("LIVE_TRADING_ENABLED is not 'true' in .env; refusing to send real orders.")
        if cfg["data"]["source"] != "schwab":
            raise RuntimeError("Real money needs Schwab's real-time prices: set data.source: schwab in config.yaml")
    from aitrader.brokers.schwab_broker import SchwabBroker
    from aitrader.schwab_api import account_hash, get_client
    client = get_client(cfg)
    ledger = Ledger.from_dict(saved) if saved else Ledger(desk_capital(cfg, desk, live=True))
    live = cfg["live"]
    broker = SchwabBroker(
        ledger, client, account_hash(client, cfg["secrets"]["account_number"]), mode=mode,
        limit_buffer_pct=live["limit_buffer_pct"], fill_timeout_seconds=live["fill_timeout_seconds"],
        cash_account=cash_account, dry_run=dry_run,
        stop_loss_pct=RiskManager.for_desk(cfg, desk).stop_loss_pct if live["resting_stops"] else None,
        stop_good_till_cancel=(desk == "swing"),
        save=lambda: store.set(f"{mode}_ledger", ledger.to_dict()), log=store.log,
        on_fill=fill_recorder(store, mode, dry_run), poll_seconds=live.get("poll_seconds", 2))
    for problem in broker.reconcile(now_ny().strftime("%Y-%m-%d")):
        store.log(f"[{mode}] CHECK: {problem}")
    return broker


def save_broker(store, broker):
    store.set(f"{broker.mode}_ledger", broker.ledger.to_dict())


def reset_paper(store, desk):
    mode = f"paper-{desk}"
    store.clear_mode(mode)
    store.set(f"{mode}_ledger", None)
    store.set(f"{mode}_peak_equity", None)


def emergency_stop(cfg, store, desk, broker, prices, today, reason):
    """Cancel the bot's orders, sell every position it opened (market orders), halt the desk."""
    store.log(f"!!! EMERGENCY STOP ({broker.mode}): {reason}")
    store.set(f"halted:{desk}", True)
    broker.cancel_all(today)
    sell_everything(broker, prices, today, f"EMERGENCY STOP: {reason}", store)
    save_broker(store, broker)
    finish_if_flat(store, desk, broker, reason)


def sell_everything(broker, prices, today, reason, store):
    for ticker, pos in broker.positions().items():
        price = prices.get(ticker)
        price = pos.avg_cost if price is None or pd.isna(price) else float(price)
        broker.submit(Order(ticker, "SELL", pos.qty, price, reason, urgent=True), today)
        order_working = any(p["ticker"] == ticker for p in broker.ledger.pending)
        if ticker in broker.positions() and not order_working:
            store.log(f"!!! {ticker} is not sold yet; the bot keeps trying every 5 minutes. You can also sell it in Schwab.")


def finish_if_flat(store, desk, broker, reason):
    """A LIVE desk drops back to PAPER only once it owns nothing and has no open orders.
    Until then it stays LIVE + HALTED, so the bot keeps watching and selling those shares."""
    if current_phase(store, desk) != Phase.LIVE:
        return
    if broker.ledger.positions or broker.ledger.pending:
        store.log(f"[{broker.mode}] still getting out: {len(broker.ledger.positions)} position(s), "
                  f"{len(broker.ledger.pending)} open order(s). Staying LIVE + HALTED until flat.")
        return
    set_phase(store, desk, Phase.PAPER, f"demoted: {reason}")
    reset_paper(store, desk)


def live_not_flat(store, desk) -> bool:
    saved = store.get(f"live-{desk}_ledger")
    return bool(saved and (saved["positions"] or saved.get("pending")))


def continue_exit(cfg, store, data, desk, now) -> str:
    """A halted LIVE desk that still owns shares: keep selling until it's flat."""
    broker = open_broker(cfg, store, desk, Phase.LIVE, emergency=True)      # reconcile books any fills
    bars, _ = data.load(desk, extra=broker.positions())
    prices = pd.Series({t: df["close"].iloc[-1] for t, df in bars.items()})
    sell_everything(broker, prices, now.strftime("%Y-%m-%d"), "EMERGENCY STOP: still getting out", store)
    save_broker(store, broker)
    finish_if_flat(store, desk, broker, "emergency exit finished")
    return f"{desk}: getting out, {len(broker.ledger.positions)} position(s) left"


def trade_desk(cfg, store, data, desk, now, stops_only=False, dry_run=False, anyway=False) -> str:
    """One trading moment for one desk. Returns a one-line summary."""
    phase = current_phase(store, desk)
    if phase not in TRADING:
        return f"{desk}: not trading yet (phase {phase.value})"
    anyway = anyway and phase == Phase.PAPER                 # never for real money
    if not anyway and not in_session(now):
        return f"{desk}: market closed"
    with trading_lock(cfg):
        if store.get(f"halted:{desk}"):                      # (a kill may have happened while we waited)
            if phase == Phase.LIVE and live_not_flat(store, desk) and not dry_run:
                return continue_exit(cfg, store, data, desk, now)
            return f"{desk}: HALTED. Review the journal, then: python run.py resume"
        return _trade_desk(cfg, store, data, desk, phase, now, stops_only, dry_run, anyway)


def _trade_desk(cfg, store, data, desk, phase, now, stops_only, dry_run, anyway) -> str:
    strategy = get_strategy(load_plan(cfg, desk)["strategy"], cfg, desk)
    broker = open_broker(cfg, store, desk, phase, dry_run=dry_run)
    bars, market = load_desk(cfg, store, data, desk, keep=set(broker.positions()), live=phase == Phase.LIVE)
    if not bars:
        return f"{desk}: nothing on the watchlist is affordable (see `status`)"
    if not anyway and market.index[-1].date() != now.date():
        return f"{desk}: no prices today (market holiday?)"

    work_store = Store(":memory:") if dry_run else store     # a dry run saves nothing
    result = run_cycle(work_store, broker, strategy, RiskManager.for_desk(cfg, desk), bars, market, now,
                       cfg["desks"][desk], stops_only=stops_only)
    if dry_run:
        return f"{desk}: dry run finished; nothing was saved or sent"
    if result["kill_switch"]:
        emergency_stop(cfg, store, desk, broker, result["prices"], now.strftime("%Y-%m-%d"),
                       f"kill switch: desk value ${result['equity']:,.2f} is more than "
                       f"{cfg['desks'][desk]['risk']['max_drawdown_pct']}% below its peak ${result['peak']:,.2f}")
        return f"{desk}: KILL SWITCH TRIPPED"
    save_broker(store, broker)
    return f"{desk} [{broker.mode}]: value ${result['equity']:,.2f}"


def protect_live(cfg, store, desk):
    """After the close: one more check that every live position has its stop resting at Schwab."""
    try:
        with trading_lock(cfg):
            open_broker(cfg, store, desk, Phase.LIVE, emergency=True)     # reconcile places missing stops
    except Exception as e:
        store.log(f"!!! {desk}: evening stop check failed ({e!r}). Check Schwab that its positions have stops.")


def run_study(cfg, store, data) -> list:
    """Study every desk. Returns the desks that failed (e.g. no internet)."""
    failed = []
    for desk in active_desks(cfg):
        try:
            bars, market = load_desk(cfg, store, data, desk)
            (study_swing if desk == "swing" else study_day)(cfg, store, bars, market)
        except Exception as e:
            store.log(f"[study] {desk} desk failed: {e!r}")
            failed.append(desk)
    return failed


def schwab_login_warning(cfg):
    from aitrader.schwab_api import token_days_left
    left = token_days_left(cfg)
    if left is not None and left < 1.5:
        return f"Schwab login expires in {left:.1f} days. Run: python run.py schwab-login"
    return None


# ================================================================ autopilot
ONCE_A_DAY = ("morning", "swing", "study")


def due_jobs(now: datetime, done: set) -> list:
    """What the autopilot should do at this moment (runs every 5 minutes)."""
    if now.weekday() >= 5:
        return []
    today = now.strftime("%Y-%m-%d")
    jobs = []
    if now.time() >= dtime(9, 25) and f"morning:{today}" not in done:
        jobs.append("morning")
    if in_session(now):
        jobs.append("day")                                   # day desk: every 5 minutes
        if minutes_to_close(now) <= 15 and f"swing:{today}" not in done:
            jobs.append("swing")                             # swing desk: the daily decision
        else:
            jobs.append("swing-stops")                       # swing desk: just watch the stop-losses
    after_close = datetime.combine(now.date(), session_close(now.date())) + timedelta(minutes=10)
    if now >= after_close and f"study:{today}" not in done:
        jobs.append("study")
    return jobs


def run_job(job, cfg, store, data, now, done) -> str:
    today = now.strftime("%Y-%m-%d")
    if job == "morning":
        desks = ", ".join(f"{d} {current_phase(store, d).value}" for d in active_desks(cfg))
        store.log(f"Daily check-in. Desks: {desks}")
        warning = schwab_login_warning(cfg)
        if warning:
            store.log(f"WARNING: {warning}")
        return ""
    if job == "day":
        return trade_desk(cfg, store, data, "day", now) if "day" in active_desks(cfg) else ""
    if job == "swing-stops":
        return trade_desk(cfg, store, data, "swing", now, stops_only=True) if "swing" in active_desks(cfg) else ""
    if job == "swing":
        return trade_desk(cfg, store, data, "swing", now) if "swing" in active_desks(cfg) else ""
    if job == "study":
        if "swing" in active_desks(cfg) and current_phase(store, "swing") in TRADING and f"swing:{today}" not in done:
            store.log("WARNING: the swing desk missed today's decision (was the laptop asleep at 3:45pm?)")
        for desk in active_desks(cfg):
            if current_phase(store, desk) == Phase.LIVE:
                protect_live(cfg, store, desk)
        if run_study(cfg, store, data):
            raise RuntimeError("study incomplete")      # not marked done, so it retries in 5 minutes
        return "study done for today"
    return ""


def cmd_autopilot(cfg, store, args):
    data = MarketData(cfg)
    store.log("Autopilot started. Keep this window open and the laptop awake (Ctrl+C stops it).")
    while True:
        now = now_ny()
        today = now.strftime("%Y-%m-%d")
        done = set(store.get("autopilot_done", []))
        for job in due_jobs(now, done):
            try:
                message = run_job(job, cfg, store, data, now, done)
                if message:
                    print(f"[{now:%H:%M}] {message}")
                if job in ONCE_A_DAY:
                    done.add(f"{job}:{today}")
            except Exception as e:                           # never crash; try again next cycle
                store.log(f"autopilot: {job} failed: {e!r} (will retry in 5 minutes)")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        store.set("autopilot_done", sorted(k for k in done if k.split(":")[1] >= week_ago))
        store.set("autopilot_heartbeat", now.isoformat(timespec="seconds"))
        after = now_ny()                                     # the work may have taken minutes
        time.sleep(300 - (after.minute % 5) * 60 - after.second + 5)   # wake just after the next 5-minute mark


# ================================================================ commands
def cmd_status(cfg, store, args):
    p = study_progress(store, cfg)
    print("\n=== AI TRADER ===")
    print(f"  Study: {p['calendar_days']} calendar days, {p['study_days']} trading days studied"
          + ("" if p["ready"] else f" (still need: {', '.join(p['missing'])})"))
    beat = store.get("autopilot_heartbeat")
    print(f"  Autopilot last seen: {beat or 'never (start it: python run.py autopilot)'}")
    from aitrader.schwab_api import token_days_left
    left = token_days_left(cfg)
    print("  Schwab login: " + ("not logged in" if left is None else
                                "EXPIRED: run schwab-login" if left <= 0 else f"expires in {left:.1f} days"))

    nxt = {Phase.STUDY: "keep the autopilot running; `python run.py plan` when the study month is done",
           Phase.PLAN_REVIEW: "read data/trading_plan_{desk}.md, then `python run.py approve-plan --desk {desk}`",
           Phase.PAPER: "keep the autopilot running; `python run.py promote --desk {desk}` when results look good",
           Phase.LIVE: "keep the autopilot running; log in to Schwab weekly; watch the journal"}
    for desk in active_desks(cfg):
        phase = current_phase(store, desk)
        halted = "  ** HALTED **" if store.get(f"halted:{desk}") else ""
        print(f"\n  --- {desk.upper()} desk: {phase.value} (step {STEP_NUMBER[phase]} of 4), "
              f"${desk_capital(cfg, desk, phase == Phase.LIVE):,.0f}{halted}")
        pricey = store.get(f"too_pricey:{desk}")
        if pricey and pricey["tickers"]:
            print(f"  Too pricey to buy (1 share > ${pricey['limit']}): "
                  + ", ".join(f"{t} ${v}" for t, v in pricey["tickers"].items()))
        card = forward_report(store, cfg) if desk == "swing" else day_forward_report(store)
        if len(card) and (desk == "day" or card["signals"].sum() > 0):
            print("  Study report card:\n    " + card.to_string().replace("\n", "\n    "))
        for mode in (f"paper-{desk}", f"live-{desk}"):
            curve = store.equity_curve(mode)
            if len(curve):
                s = summarize(curve, store.fills(mode))
                print(f"  {mode}: ${curve.iloc[-1]:,.2f}  return {s['total_return_pct']}%  trades "
                      f"{s['num_closed_trades']}  win {s['win_rate_pct']}%  max drawdown {s['max_drawdown_pct']}%")
        print(f"  Next: {nxt[phase].format(desk=desk)}")

    print("\n  Recent journal:")
    for ts, msg in store.journal(10):
        print(f"    {ts}  {msg}")


def cmd_study(cfg, store, args):
    run_study(cfg, store, MarketData(cfg))


def cmd_trade(cfg, store, args):
    data, now = MarketData(cfg), now_ny()
    done = set(store.get("autopilot_done", []))
    for desk in pick_desks(cfg, args):
        key = f"swing:{now:%Y-%m-%d}"
        if desk == "swing" and key in done and not args.dry_run:
            print("swing: already decided today")
            continue
        print(trade_desk(cfg, store, data, desk, now, dry_run=args.dry_run, anyway=args.anyway))
        if desk == "swing" and not args.dry_run and current_phase(store, desk) in TRADING:
            store.set("autopilot_done", sorted(done | {key}))


def cmd_backtest(cfg, store, args):
    data = MarketData(cfg)
    for desk in pick_desks(cfg, args):
        bars, market = load_desk(cfg, store, data, desk)
        rows = []
        for s in all_strategies(cfg, desk):
            if args.strategy and s.name != args.strategy:
                continue
            print(f"  backtesting {desk}/{s.name} ...")
            r = run_backtest(s, bars, market, cfg, desk)
            rows.append([s.name, r["start"], r["total_return_pct"], r["cagr_pct"], r["sharpe"],
                         r["max_drawdown_pct"], r["num_closed_trades"], r["win_rate_pct"], r["profit_factor"]])
        start = min((r[1] for r in rows if r[1]), default=None)
        closes = market["close"].groupby(market.index.normalize()).last()
        if start:
            closes = closes[closes.index >= pd.Timestamp(start)]
        b = summarize(buy_and_hold(closes, desk_capital(cfg, desk, live=False)))
        rows.append([f"buy&hold {cfg['benchmark']}", start, b["total_return_pct"], b["cagr_pct"], b["sharpe"],
                     b["max_drawdown_pct"], "-", "-", "-"])
        print(f"\n{desk.upper()} desk (${desk_capital(cfg, desk, live=False):,.0f}):")
        print(pd.DataFrame(rows, columns=["strategy", "from", "return%", "yearly%", "sharpe", "maxDD%",
                                          "trades", "win%", "PF"]).to_string(index=False))


def cmd_plan(cfg, store, args):
    p = study_progress(store, cfg)
    if not p["ready"]:
        if not args.force:
            print(f"Not yet. The study month needs: {', '.join(p['missing'])}.")
            return
        store.log("WARNING: plan forced before the study month finished (testing only)")
    data = MarketData(cfg)
    for desk in pick_desks(cfg, args):
        phase = current_phase(store, desk)
        if phase not in (Phase.STUDY, Phase.PLAN_REVIEW):
            print(f"{desk}: already past planning (phase {phase.value}).")
            continue
        bars, market = load_desk(cfg, store, data, desk)
        plan = build_plan(cfg, store, desk, bars, market)
        print(f"\n{desk}: plan written to {data_path(cfg, f'trading_plan_{desk}.md')}")
        if plan["verdict"] == "TRADE":
            set_phase(store, desk, Phase.PLAN_REVIEW, f"plan picked {plan['strategy']}")
            print(f"Read it, then run: python run.py approve-plan --desk {desk}")
        else:
            if phase == Phase.PLAN_REVIEW:
                set_phase(store, desk, Phase.STUDY, "new plan says NO_TRADE")
            store.log(f"{desk} plan verdict NO_TRADE; staying in STUDY")
            print(f"{desk}: no strategy was good enough. Staying in STUDY (that's the bot protecting your money).")


def cmd_approve_plan(cfg, store, args):
    for desk in pick_desks(cfg, args):
        if current_phase(store, desk) != Phase.PLAN_REVIEW:
            print(f"{desk}: no plan waiting for approval.")
            continue
        plan = load_plan(cfg, desk)
        print(f"{desk} plan from {plan['created_on']}: trade `{plan['strategy']}` with FAKE money first.")
        print(f"Full plan: {data_path(cfg, f'trading_plan_{desk}.md')}")
        if input(f"Type YES to start paper trading the {desk} desk: ").strip() != "YES":
            print("Not approved.")
            continue
        reset_paper(store, desk)
        set_phase(store, desk, Phase.PAPER, "plan approved by you")


def cmd_promote(cfg, store, args):
    data = None
    for desk in pick_desks(cfg, args):
        if current_phase(store, desk) != Phase.PAPER:
            print(f"{desk}: promotion to LIVE only happens from PAPER.")
            continue
        if live_not_flat(store, desk):
            print(f"{desk}: the bot still has real positions or orders from before. Sort those out first.")
            continue
        curve = store.equity_curve(f"paper-{desk}")
        if len(curve) < 2:
            print(f"{desk}: not enough paper trading yet.")
            continue
        data = data or MarketData(cfg)
        bench = data.history(cfg["benchmark"], "1d")["close"]
        bench = bench[bench.index >= curve.index[0]]
        bench_ret = (bench.iloc[-1] / bench.iloc[0] - 1) * 100 if len(bench) > 1 else 0.0
        checks = check_promotion(cfg, summarize(curve, store.fills(f"paper-{desk}")), bench_ret)
        print(f"\n{desk.upper()} desk:")
        print(pd.DataFrame([[n, a, r, "PASS" if ok else "FAIL"] for n, a, r, ok in checks],
                           columns=["rule", "actual", "required", "result"]).to_string(index=False))
        if not all(ok for *_, ok in checks):
            print("Not yet. Keep paper trading; this desk hasn't earned real money.")
            continue
        if cfg["data"]["source"] != "schwab":
            print("Paper results pass! Real money needs Schwab's real-time prices: set data.source: schwab.")
            continue
        if not cfg["live_trading_enabled"]:
            print("Paper results pass! To go live, set LIVE_TRADING_ENABLED=true in .env and run this again.")
            continue
        from aitrader.schwab_api import account_hash, get_client
        account_hash(get_client(cfg), cfg["secrets"]["account_number"])   # proves the Schwab login works
        print(f"The {desk} desk will trade REAL money, capped at ${desk_capital(cfg, desk, live=True):,.0f}.")
        print("Past results don't guarantee future results. Only use money you can afford to lose.")
        if input("Type REAL MONEY to confirm: ").strip() != "REAL MONEY":
            print("Not promoted.")
            continue
        store.set(f"live-{desk}_ledger", Ledger(desk_capital(cfg, desk, live=True)).to_dict())
        store.set(f"live-{desk}_peak_equity", None)
        set_phase(store, desk, Phase.LIVE, "paper results passed every rule; confirmed by you")


def cmd_kill(cfg, store, args):
    for desk in active_desks(cfg):
        store.set(f"halted:{desk}", True)              # right away: no new cycles may start
    with trading_lock(cfg):                            # wait for a running cycle to finish
        _kill_all(cfg, store)
    print("All desks halted. Run `python run.py resume` when you're ready.")


def _kill_all(cfg, store):
    data, now = MarketData(cfg), now_ny()
    for desk in active_desks(cfg):
        phase = current_phase(store, desk)
        if phase not in TRADING:
            continue
        broker = open_broker(cfg, store, desk, phase, emergency=True)
        bars, _ = data.load(desk, extra=broker.positions())
        prices = pd.Series({t: df["close"].iloc[-1] for t, df in bars.items()})
        emergency_stop(cfg, store, desk, broker, prices, now.strftime("%Y-%m-%d"), "manual kill command")


def cmd_resume(cfg, store, args):
    for desk in pick_desks(cfg, args):
        store.set(f"halted:{desk}", False)
        store.log(f"{desk} desk resumed by you (phase {current_phase(store, desk).value})")


def cmd_schwab_login(cfg, store, args):
    from aitrader.schwab_api import login
    login(cfg, manual=args.manual)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI trader for Charles Schwab")
    sub = parser.add_subparsers(dest="command", required=True)
    desk_help = "only this desk (default: all enabled desks)"
    sub.add_parser("autopilot")
    sub.add_parser("status")
    sub.add_parser("study")
    t = sub.add_parser("trade")
    t.add_argument("--desk", choices=["swing", "day"], help=desk_help)
    t.add_argument("--dry-run", action="store_true", help="live: show orders, send nothing")
    t.add_argument("--anyway", action="store_true", help="paper only: trade even if the market is closed")
    b = sub.add_parser("backtest")
    b.add_argument("--desk", choices=["swing", "day"], help=desk_help)
    b.add_argument("--strategy", help="only this strategy")
    p = sub.add_parser("plan")
    p.add_argument("--desk", choices=["swing", "day"], help=desk_help)
    p.add_argument("--force", action="store_true", help="skip the 30-day wait (TESTING ONLY)")
    for name in ("approve-plan", "promote", "resume"):
        sub.add_parser(name).add_argument("--desk", choices=["swing", "day"], help=desk_help)
    sub.add_parser("kill")
    sub.add_parser("schwab-login").add_argument("--manual", action="store_true",
                                                help="print a login link instead of opening a browser")
    args = parser.parse_args(argv)

    cfg = load_config()
    store = Store(data_path(cfg, "aitrader.sqlite"))
    commands = {"autopilot": cmd_autopilot, "status": cmd_status, "study": cmd_study, "trade": cmd_trade,
                "backtest": cmd_backtest, "plan": cmd_plan, "approve-plan": cmd_approve_plan,
                "promote": cmd_promote, "kill": cmd_kill, "resume": cmd_resume, "schwab-login": cmd_schwab_login}
    try:
        commands[args.command](cfg, store, args)
    except RuntimeError as e:
        store.log(f"STOPPED: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        store.log("Stopped by you (Ctrl+C)")


if __name__ == "__main__":
    main()
