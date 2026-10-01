"""
run.py: the ONE file you run.

    python run.py menu            a simple numbered menu for everything below (the Mac app opens this)
    python run.py autopilot       START THIS AND LEAVE IT RUNNING. Every trading day it:
                                    - day desk: decides every 5 minutes, sells out before the close
                                    - swing desk: watches stop-losses, decides at 3:45pm
                                    - studies after the close (grading, shadow trading)
    python run.py dashboard       open the Kestrel app (its window is the dashboard)
    python run.py status          where is each desk, and what's next?
    python run.py check           test your Alpaca/Schwab keys and price data
    python run.py backtest        test every strategy on history (any time)

    python run.py plan            after the study month: write each desk's trading plan
    python run.py approve-plan    you read a plan and say yes -> that desk starts paper trading
    python run.py start-stage1    Stage 1 now: the swing desk paper trades momentum (skips the study month)
    python run.py report          the after-market report: what it traded today, why, and what's next
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
from aitrader.config import (active_desks, data_path, data_source, desk_capital, is_cash_account, load_config,
                             paper_broker, uses_broker_paper)
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
IN_ITS_HEAD = (Phase.STUDY, Phase.PLAN_REVIEW)      # studying desks trade in their head (pretend, on this Mac)


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
        amount = f.qty * f.price
        if f.side == "SELL":
            cost = amount - f.realized_pnl                  # what those shares cost
            pct = f", {f.realized_pnl / cost * 100:+.1f}%" if cost > 0 else ""
            pnl = f"{'-' if f.realized_pnl < 0 else '+'}${abs(f.realized_pnl):,.2f}"
            money = f" (got ${amount:,.2f}; {'WIN' if f.realized_pnl > 0 else 'LOSS' if f.realized_pnl < 0 else 'even'} {pnl}{pct})"
        else:
            money = f" (spent ${amount:,.2f})"
        line = f"[{mode}] {f.side} {f.qty} {f.ticker} @ ${f.price:.2f}{money}: {f.reason}"
        if dry_run:
            print(f"[DRY RUN] {line}")
            return
        store.record_fill(mode, f)
        store.log(line)
    return record


def broker_backed(cfg, phase) -> bool:
    """True when this phase's orders go to a real broker account (Alpaca paper, or live money)."""
    return phase == Phase.LIVE or (phase == Phase.PAPER and uses_broker_paper(cfg))


def open_broker(cfg, store, desk, phase, dry_run=False, emergency=False):
    mode = mode_of(phase, desk)
    live = phase == Phase.LIVE
    saved = store.get(f"{mode}_ledger")
    ledger = Ledger.from_dict(saved) if saved else Ledger(desk_capital(cfg, desk, live))
    cash_account = is_cash_account(cfg)                     # cash accounts: never spend unsettled money
    if not broker_backed(cfg, phase):                        # paper, simulated on this laptop
        broker = PaperBroker(ledger, cfg["paper"]["slippage_pct"], cfg["paper"]["commission_per_trade"],
                             mode=mode, cash_account=cash_account)
        broker.on_fill = fill_recorder(store, mode, dry_run)
        broker.note = lambda message: store.log(f"[{mode}] {message}")
        return broker

    # Real money: several locks must all be open (except for an emergency sell-off).
    if live and not emergency:
        if not cfg["live_trading_enabled"] and not dry_run:
            raise RuntimeError("LIVE_TRADING_ENABLED is not 'true' in .env; refusing to send real orders.")
        if data_source(cfg) not in ("alpaca", "schwab"):
            raise RuntimeError("Real money needs real-time prices: set data.source to auto/alpaca in config.yaml")
    settings = cfg["live"]
    common = dict(
        mode=mode, limit_buffer_pct=settings["limit_buffer_pct"],
        fill_timeout_seconds=settings["fill_timeout_seconds"], cash_account=cash_account, dry_run=dry_run,
        stop_loss_pct=RiskManager.for_desk(cfg, desk).stop_loss_pct if settings["resting_stops"] else None,
        stop_good_till_cancel=(desk == "swing"),
        save=lambda: store.set(f"{mode}_ledger", ledger.to_dict()), log=store.log,
        on_fill=fill_recorder(store, mode, dry_run), poll_seconds=settings.get("poll_seconds", 2))
    where = cfg["broker"] if live else paper_broker(cfg)
    if where == "webull":
        from aitrader.brokers.webull_broker import WebullBroker, connect
        account_id, token = connect(cfg, "live" if live else "paper")
        broker = WebullBroker(ledger, cfg, account_id, token, **common)
    elif where == "alpaca":
        from aitrader.alpaca_api import trading_client
        from aitrader.brokers.alpaca_broker import AlpacaBroker
        broker = AlpacaBroker(ledger, trading_client(cfg, paper=not live), **common)
    else:
        from aitrader.brokers.schwab_broker import SchwabBroker
        from aitrader.schwab_api import account_hash, get_client
        client = get_client(cfg)
        broker = SchwabBroker(ledger, client, account_hash(client, cfg["secrets"]["account_number"]), **common)
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
    store.set(f"exiting:{desk}", True)                  # keep selling until flat (a plain pause doesn't)
    broker.cancel_all(today)
    sell_everything(broker, prices, today, f"EMERGENCY STOP: {reason}", store)
    save_broker(store, broker)
    finish_if_flat(store, desk, broker, reason)


def sell_everything(broker, prices, today, reason, store):
    for ticker, pos in broker.positions().items():
        price = prices.get(ticker)
        price = pos.avg_cost if price is None or pd.isna(price) else float(price)
        broker.submit(Order(ticker, "SELL", pos.qty, price, reason, urgent=True, emergency=True), today)
        order_working = any(p["ticker"] == ticker for p in broker.ledger.pending)
        if ticker in broker.positions() and not order_working:
            store.log(f"!!! {ticker} is not sold yet; the bot keeps trying every 5 minutes. You can also sell it in Schwab.")


def close_in_head(cfg, store, desk):
    """A desk leaving the study: sell what it holds in its head at the last known price (pretend
    money), so its "in its head" record ends cleanly instead of freezing with open positions."""
    mode = f"study-{desk}"
    saved = store.get(f"{mode}_ledger")
    if not saved or not saved.get("positions"):
        return
    try:
        from aitrader.dashboard import quote
        broker = open_broker(cfg, store, desk, Phase.STUDY)
        prices = pd.Series({t: quote(cfg, t)["last"] for t in broker.positions()}, dtype=float)
        today = now_ny().strftime("%Y-%m-%d")
        sell_everything(broker, prices, today,
                        f"in its head: the {desk} desk moved on to paper trading; closed at the last price", store)
        save_broker(store, broker)
        left = sum(p.qty * p.avg_cost for p in broker.positions().values())
        store.record_equity(mode, today, broker.cash() + left, broker.cash())
    except Exception as e:                                   # never block moving up
        store.log(f"[{mode}] couldn't close the pretend positions ({e!r}); they stay in the record")


def finish_if_flat(store, desk, broker, reason):
    """After an emergency stop a desk stays HALTED and keeps selling until it owns nothing and has
    no open orders. Only then does a LIVE desk drop back to PAPER."""
    if broker.ledger.positions or broker.ledger.pending:
        store.log(f"[{broker.mode}] still getting out: {len(broker.ledger.positions)} position(s), "
                  f"{len(broker.ledger.pending)} open order(s). Staying HALTED and retrying until flat.")
        return
    store.set(f"exiting:{desk}", False)                 # out: from now on it's simply halted (paused)
    if current_phase(store, desk) == Phase.LIVE:
        set_phase(store, desk, Phase.PAPER, f"demoted: {reason}")
        reset_paper(store, desk)


def not_flat(store, mode) -> bool:
    saved = store.get(f"{mode}_ledger")
    return bool(saved and (saved["positions"] or saved.get("pending")))


def live_not_flat(store, desk) -> bool:
    return not_flat(store, f"live-{desk}")


def continue_exit(cfg, store, data, desk, now) -> str:
    """After an emergency stop, a desk that still owns shares at the broker: keep selling until it's flat."""
    phase = current_phase(store, desk)
    broker = open_broker(cfg, store, desk, phase, emergency=True)           # reconcile books any fills
    bars, _ = data.load(desk, extra=broker.positions())
    prices = pd.Series({t: df["close"].iloc[-1] for t, df in bars.items()})
    sell_everything(broker, prices, now.strftime("%Y-%m-%d"), "EMERGENCY STOP: still getting out", store)
    save_broker(store, broker)
    finish_if_flat(store, desk, broker, "emergency exit finished")
    return f"{desk}: getting out, {len(broker.ledger.positions)} position(s) left"


def trade_desk(cfg, store, data, desk, now, stops_only=False, dry_run=False, anyway=False) -> str:
    """One trading moment for one desk. Returns a one-line summary."""
    phase = current_phase(store, desk)
    if phase in IN_ITS_HEAD and cfg["study"].get("in_its_head", True):
        if not anyway and not in_session(now):
            return f"{desk}: market closed"
        with trading_lock(cfg):                             # pretend money: pauses don't apply
            return _trade_desk(cfg, store, data, desk, phase, now, stops_only, dry_run, anyway)
    if phase not in TRADING:
        return f"{desk}: not trading yet (phase {phase.value})"
    anyway = anyway and phase == Phase.PAPER                 # never for real money
    if not anyway and not in_session(now):
        return f"{desk}: market closed"
    with trading_lock(cfg):
        if store.get(f"halted:{desk}"):                      # (a kill may have happened while we waited)
            owns_something = not_flat(store, mode_of(phase, desk))
            if store.get(f"exiting:{desk}") and broker_backed(cfg, phase) and owns_something and not dry_run:
                return continue_exit(cfg, store, data, desk, now)
            if not owns_something or dry_run:
                return f"{desk}: HALTED. Review the journal, then: python run.py resume"
            # PAUSED: no new trades, but keep guarding what it owns: stop-losses, and the day
            # desk still sells before the close (it never holds overnight).
            return f"{desk}: HALTED, only guarding what it owns. " + _trade_desk(
                cfg, store, data, desk, phase, now, True, dry_run, anyway)
        return _trade_desk(cfg, store, data, desk, phase, now, stops_only, dry_run, anyway)


def head_strategy(cfg, desk) -> str:
    """The method a studying desk trades in its head (config.yaml: study.in_its_head_strategy)."""
    return (cfg["study"].get("in_its_head_strategy") or {}).get(desk) or \
        {"swing": "momentum", "day": "opening_range_breakout"}[desk]


def _trade_desk(cfg, store, data, desk, phase, now, stops_only, dry_run, anyway) -> str:
    in_head = phase in IN_ITS_HEAD
    strategy = get_strategy(head_strategy(cfg, desk) if in_head else load_plan(cfg, desk)["strategy"], cfg, desk)
    broker = open_broker(cfg, store, desk, phase, dry_run=dry_run)
    bars, market = load_desk(cfg, store, data, desk, keep=set(broker.positions()), live=phase == Phase.LIVE)
    if not bars:
        return f"{desk}: nothing on the watchlist is affordable (see `status`)"
    if not anyway and market.index[-1].date() != now.date():
        return f"{desk}: no prices today (market holiday?)"

    work_store = Store(":memory:") if dry_run else store     # a dry run saves nothing
    from aitrader.scanner import danger_tickers
    danger = danger_tickers(cfg)                              # danger headlines: not buying these for now
    broker.blocked = frozenset(broker.blocked) | {t for t in danger if t not in broker.positions()}
    risk, change = learned(cfg, store, desk, broker.mode, strategy.name, market, now.strftime("%Y-%m-%d"))
    result = run_cycle(work_store, broker, strategy, risk, bars, market, now,
                       cfg["desks"][desk], stops_only=stops_only, no_buys=change["no_buys"], cfg=cfg)
    if dry_run:
        return f"{desk}: dry run finished; nothing was saved or sent"
    if result["kill_switch"] and in_head:                    # pretend money: sell, note it, start the count again
        sell_everything(broker, result["prices"], now.strftime("%Y-%m-%d"),
                        "kill switch (in its head): down too far from its best day", store)
        save_broker(store, broker)
        store.set(f"{broker.mode}_peak_equity", None)
        store.log(f"[{broker.mode}] KILL SWITCH (in its head): value ${result['equity']:,.2f} was more than "
                  f"{cfg['desks'][desk]['risk']['max_drawdown_pct']}% below its best ${result['peak']:,.2f}; "
                  "sold everything (pretend) and carries on")
        return f"{desk} [{broker.mode}]: kill switch in its head"
    if result["kill_switch"]:
        emergency_stop(cfg, store, desk, broker, result["prices"], now.strftime("%Y-%m-%d"),
                       f"kill switch: desk value ${result['equity']:,.2f} is more than "
                       f"{cfg['desks'][desk]['risk']['max_drawdown_pct']}% below its peak ${result['peak']:,.2f}")
        return f"{desk}: KILL SWITCH TRIPPED"
    save_broker(store, broker)
    return f"{desk} [{broker.mode}]: value ${result['equity']:,.2f}"


def learned(cfg, store, desk, mode, strategy_name, market, today=None):
    """What the desk has learned from its own finished trades (learning.py): smaller positions for a
    strategy that's losing, none for one that's clearly losing or in a market condition that clearly
    loses. Never bigger. Plus the mistakes it won't repeat (mistakes.py: the Risk agent skips buys in a
    situation that keeps losing). Also refreshes the lessons note the local AI reads."""
    import dataclasses
    from aitrader import learning, mistakes
    risk = RiskManager.for_desk(cfg, desk)
    try:
        for m in mistakes.review(store, desk, today or now_ny().strftime("%Y-%m-%d")):
            store.log(f"[{mode}] LEARNED: won't repeat {m['tag']} ({m['why']}); the Risk agent skips those buys now")
    except Exception as e:                                   # learning must never stop trading safely
        store.log(f"[{mode}] couldn't review its mistakes ({e!r}); trading on without that check this cycle")
    try:
        lessons = learning.review(store.fills(mode), market)
        change = learning.adjust(lessons, strategy_name, learning.today_condition(market))
    except Exception as e:                                   # learning must never stop trading safely
        store.log(f"[{mode}] couldn't review its past trades ({e!r}); trading without lessons this cycle")
        return risk, {"size": 1.0, "no_buys": ""}
    before = store.get(f"lessons:{desk}") or {}
    store.set(f"lessons:{desk}", {"mode": mode, **{k: lessons[k] for k in ("trades", "strategies", "conditions", "avoid")}})
    if before.get("trades") != lessons["trades"]:            # a trade finished since last time: tell the owner
        for name, card in lessons["strategies"].items():
            old = (before.get("strategies") or {}).get(name, {})
            if card["status"] != old.get("status") and card["status"] in ("half size", "paused"):
                store.log(f"[{mode}] LEARNED: {name} {card['why']} -> {card['status']}")
        data_path(cfg, learning.NOTE).write_text(learning.note(
            {d: {**(store.get(f"lessons:{d}") or {"trades": 0, "strategies": {}, "conditions": {}, "avoid": []}),
                 "mistakes": store.get(f"mistakes:{d}") or []} for d in active_desks(cfg)}))
    if change["size"] < 1:
        risk = dataclasses.replace(risk, max_position_pct=risk.max_position_pct * change["size"])
    return risk, change


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


def prove_live_connection(cfg):
    """Raises if the real-money account can't be reached with the keys in .env."""
    if cfg["broker"] == "alpaca":
        from aitrader.alpaca_api import trading_client
        trading_client(cfg, paper=False).get_account()
    elif cfg["broker"] == "webull":
        from aitrader.brokers.webull_broker import connect
        connect(cfg, "live")                                # real-money keys, approved in the Webull app
    else:
        from aitrader.schwab_api import account_hash, get_client
        account_hash(get_client(cfg), cfg["secrets"]["account_number"])


def schwab_login_warning(cfg):
    if cfg["broker"] != "schwab":
        return None
    from aitrader.schwab_api import token_days_left
    left = token_days_left(cfg)
    if left is not None and left < 1.5:
        return f"Schwab login expires in {left:.1f} days. Run: python run.py schwab-login"
    return None


# ================================================================ autopilot
ONCE_A_DAY = ("morning", "inplay", "swing", "study", "options", "tjr", "scan", "report")


def due_jobs(now: datetime, done: set) -> list:
    """What the autopilot should do at this moment (runs every 5 minutes)."""
    if now.weekday() >= 5:
        return []
    today = now.strftime("%Y-%m-%d")
    jobs = []
    if now.time() >= dtime(9, 25) and f"morning:{today}" not in done:
        jobs.append("morning")
    if in_session(now):
        if dtime(9, 35) <= now.time() < dtime(9, 50) and f"inplay:{today}" not in done:
            jobs.append("inplay")                            # today's stocks in play (in_play.py), before the day desk
        jobs.append("day")                                   # day desk: every 5 minutes
        if minutes_to_close(now) <= 15 and f"swing:{today}" not in done:
            jobs.append("swing")                             # swing desk: the daily decision
        else:
            jobs.append("swing-stops")                       # swing desk: just watch the stop-losses
    after_close = datetime.combine(now.date(), session_close(now.date())) + timedelta(minutes=10)
    if now >= after_close and f"study:{today}" not in done:
        jobs.append("study")
    if now >= after_close + timedelta(minutes=5) and f"options:{today}" not in done:
        jobs.append("options")                               # the options-gap watcher (options_flow.py)
    if now >= after_close + timedelta(minutes=5) and f"study:{today}" in done and f"tjr:{today}" not in done:
        jobs.append("tjr")                                   # TJR's weekly history test (tjr.py)
    if now >= after_close + timedelta(minutes=10) and f"scan:{today}" not in done:
        jobs.append("scan")                                  # the daily all-stocks scan and news (scanner.py)
    if (now >= after_close + timedelta(minutes=15) and f"study:{today}" in done
            and f"report:{today}" not in done):
        jobs.append("report")                                # the after-market report (report.py)
    return jobs


SCAN_IN_BACKGROUND = True                               # tests run it inline
SCAN_TRIES = 3                                          # a scan that keeps failing waits for the next day
_scanning = None                                        # the running scan thread, if any


def scan_running() -> bool:
    return _scanning is not None and _scanning.is_alive()


def scan_state(store, today, kind="evening") -> dict:
    """Today's scan so far: {"tries", "started", "finished", "summary", "error"} ({} = not started)."""
    state = store.get("scan_status") or {}
    return state if state.get("day") == today and state.get("kind") == kind else {}


def job_complete(job, store, today) -> bool:
    """Most daily jobs are done once they ran. The scan runs in the background, so it's done only when it
    finished (or failed SCAN_TRIES times); a scan cut short (the Mac restarted, an update) runs again."""
    if job != "scan":
        return True
    state = scan_state(store, today)
    return bool(state.get("finished")) or (not scan_running() and state.get("tries", 0) >= SCAN_TRIES)


def scan_in_background(cfg, store, today, why, kind="evening") -> str:
    """The all-stocks scan can take many minutes (thousands of stocks). It runs in its own thread with its
    own database connection, so trading, stop-losses and the check-ins never wait for it. Each try is
    written down (scan_status), so the report can say when the list was last made, or why it wasn't."""
    import threading
    from aitrader import scanner
    global _scanning
    if scan_running():
        return "scan: already running in the background"
    state = scan_state(store, today, kind)
    if state.get("finished"):
        return ""
    tries = state.get("tries", 0) + 1
    if tries > SCAN_TRIES:
        return f"scan: gave up for today after {SCAN_TRIES} tries ({state.get('error') or 'cut short'})"
    store.set("scan_status", {"day": today, "kind": kind, "tries": tries,
                              "started": now_ny().isoformat(timespec="minutes")})
    path = data_path(cfg, "aitrader.sqlite")

    def work():
        own = Store(path) if SCAN_IN_BACKGROUND else store
        own.on_log = store.on_log                           # phone alerts too
        base = {"day": today, "kind": kind, "tries": tries}
        try:
            summary = scanner.run(cfg, own, today)
            own.set("scan_status", {**base, "finished": now_ny().isoformat(timespec="minutes"), "summary": summary})
            own.log(f"[scan] {summary}")
        except Exception as e:                               # the autopilot tries again in 5 minutes
            own.set("scan_status", {**base, "error": repr(e)[:300], "failed_at": now_ny().isoformat(timespec="minutes")})
            again = "tries again in 5 minutes" if tries < SCAN_TRIES else "gave up until tomorrow"
            own.log(f"[scan] failed (try {tries} of {SCAN_TRIES}: {e!r}); {again}")
        finally:
            if own is not store:
                own.db.close()
    store.log(f"[scan] {why} (in the background: trading carries on meanwhile)")
    if not SCAN_IN_BACKGROUND:
        work()
        return "scan finished"
    _scanning = threading.Thread(target=work, daemon=True, name="scan")
    _scanning.start()
    return "scan started in the background"


def last_weekday_before(day: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def first_scan(cfg, store, today):
    """No stock list yet (a new install), or last evening's scan didn't finish (the Mac was asleep or
    off): scan in the morning, so the swing desk's decision (3:45pm) picks from all US stocks, not just
    its watchlist."""
    from aitrader import scanner
    if not scanner.is_on(scanner.settings(cfg)["enabled"]):
        return
    state = scanner.load_list(cfg)
    if not state.get("updated"):
        why = "no stock list yet: scanning all US stocks (takes a while the first time)"
    elif state["updated"] < last_weekday_before(today):
        why = f"the stock list is from {state['updated']} (last evening's scan didn't finish): scanning again"
    else:
        return
    scan_in_background(cfg, store, today, why, kind="morning")


def run_job(job, cfg, store, data, now, done) -> str:
    today = now.strftime("%Y-%m-%d")
    if job == "morning":
        desks = ", ".join(f"{d} {current_phase(store, d).value}" for d in active_desks(cfg))
        store.log(f"Daily check-in. Desks: {desks}")
        warning = schwab_login_warning(cfg)
        if warning:
            store.log(f"WARNING: {warning}")
        try:                                            # keeps an approved Webull login from lapsing (15 idle days)
            from aitrader.webull_api import keep_alive
            warning = keep_alive(cfg)
        except Exception as e:                          # never let Webull stop the day
            warning = f"Webull: couldn't check the connection ({e})."
        if warning:
            store.log(f"WARNING: {warning}")
        first_scan(cfg, store, today)
        return ""
    if job == "inplay":
        from aitrader import in_play
        if "day" not in active_desks(cfg):
            return ""
        message = in_play.run(cfg, store, today)             # raises if the 9:30 bars aren't in yet: retries
        store.log(f"[day] {message}")
        return message
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
        report_days(cfg, store, today)
        return "study done for today"
    if job == "tjr":
        return run_tjr_test(cfg, store, data, today)
    if job == "options":
        from aitrader.options_flow import run as watch_options
        return watch_options(cfg, store, data, today)
    if job == "report":
        from aitrader.report import write_after_market
        write_after_market(cfg, store, today)
        return f"after-market report for {today} written"
    if job == "scan":
        from aitrader import scanner
        if not scanner.is_on(scanner.settings(cfg)["enabled"]):
            return "scan: off (Setup)"
        return scan_in_background(cfg, store, today, "the daily scan of all US stocks and their news")
    return ""


def report_days(cfg, store, today):
    """After the close: one journal line per account that traded (in its head, paper, real)."""
    from aitrader.report import MODES, day_line
    for desk in active_desks(cfg):
        for kind in MODES:
            try:
                line = day_line(store, f"{kind}-{desk}", desk_capital(cfg, desk, kind == "live"), today)
            except Exception as e:                           # a report must never stop the study
                line = f"[{kind}-{desk}] couldn't write today's summary ({e!r})"
            if line:
                store.log(line)


def process_alive(pid) -> bool:
    if not pid or os.name == "nt":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_phone(cfg, store):
    """Your phone (phone.py): forward alerts, and answer your commands in a background thread."""
    import threading
    from aitrader import phone
    from aitrader.scanner import is_on
    if is_on((cfg.get("phone") or {}).get("screen", False)):  # the Kestrel screen over Tailscale
        from aitrader import phone_screen
        threading.Thread(target=phone_screen.serve_forever, args=(cfg,), daemon=True, name="phone-screen").start()
    from aitrader import pushover
    if phone.token(cfg) or pushover.has_keys(cfg):
        store.on_log = phone.forwarder(cfg)             # alerts: Telegram and/or Pushover
    if not phone.token(cfg):
        return                                          # commands need Telegram (Pushover only delivers)
    path = data_path(cfg, "aitrader.sqlite")
    threading.Thread(target=phone.listen, args=(cfg, lambda: Store(path)), daemon=True, name="phone").start()


def start_lid_mode(cfg):
    """Lid-closed mode (lid_mode.py): awake with the lid closed on the charger, asleep on battery."""
    if sys.platform != "darwin":
        return
    import threading
    from aitrader import lid_mode
    path = data_path(cfg, "aitrader.sqlite")
    threading.Thread(target=lid_mode.watch, args=(lambda: Store(path),), daemon=True, name="lid-mode").start()


STUCK_MINUTES = 30                                      # a job taking longer than this = stuck: restart


def start_watchdog(cfg, progress: dict):
    """If one job hangs (e.g. a network call that never answers), the autopilot restarts itself after
    STUCK_MINUTES instead of silently doing nothing all day. Mac sleep doesn't count (monotonic clock)."""
    import threading

    def watch():
        while True:
            time.sleep(60)
            restart_if_stuck(cfg, progress)
    threading.Thread(target=watch, daemon=True, name="watchdog").start()


def restart_if_stuck(cfg, progress: dict) -> bool:
    stuck = (time.monotonic() - progress["t"]) / 60
    if stuck <= STUCK_MINUTES:
        return False
    own = Store(data_path(cfg, "aitrader.sqlite"))
    own.log(f"!!! autopilot stuck for {stuck:.0f} minutes on '{progress['job']}': restarting itself")
    own.set("autopilot_busy", None)
    own.db.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)          # same process id, fresh start
    return True


def launched_by_service() -> bool:
    """True when launchd (Setup -> Autopilot: on) started this autopilot, not a Terminal window."""
    from aitrader import mac_service
    return (os.environ.get("KESTREL_SERVICE") == "1" or os.getppid() == 1
            or "caffeinate" in mac_service.command_of(os.getppid()))        # older installs


def take_over(store) -> str:
    """Only one autopilot may run. The background one (launchd) always wins: an older autopilot that's
    still alive (e.g. left behind by a restart, maybe stuck) is stopped. A Terminal one steps aside."""
    import signal
    from aitrader import mac_service
    other = store.get("autopilot_pid")
    if not other or other == os.getpid() or not process_alive(other):
        return ""
    if "run.py" not in (cmd := mac_service.command_of(other)) or "autopilot" not in cmd:
        return ""                                            # that process id now belongs to something else
    if not launched_by_service():
        raise RuntimeError(f"The autopilot is already running (process {other}). Only one may run at a time.")
    os.kill(other, signal.SIGTERM)
    for _ in range(15):
        time.sleep(1)
        if not process_alive(other):
            break
    else:
        os.kill(other, signal.SIGKILL)
    return f"Stopped an older autopilot (process {other}) that was still running; this one takes over."


def cmd_autopilot(cfg, store, args):
    note = take_over(store)
    store.set("autopilot_pid", os.getpid())
    if note:
        store.log(note)
    from aitrader import mac_service
    mac_service.keep_awake()
    import socket
    socket.setdefaulttimeout(120)                       # a network call that never answers fails (and retries)
    data = MarketData(cfg)
    start_phone(cfg, store)
    progress = {"t": time.monotonic(), "job": None}
    start_watchdog(cfg, progress)
    start_lid_mode(cfg)
    store.log("Autopilot started. Keep the laptop awake and online (Ctrl+C stops it).")
    while True:
        now = now_ny()
        today = now.strftime("%Y-%m-%d")
        store.set("autopilot_heartbeat", now.isoformat(timespec="seconds"))
        done = set(store.get("autopilot_done", []))
        for job in due_jobs(now, done):
            progress.update(t=time.monotonic(), job=job)
            store.set("autopilot_busy", {"job": job, "since": now_ny().isoformat(timespec="seconds")})
            try:
                message = run_job(job, cfg, store, data, now, done)
                if message:
                    print(f"[{now:%H:%M}] {message}")
                if job in ONCE_A_DAY and job_complete(job, store, today):
                    done.add(f"{job}:{today}")
            except Exception as e:                           # never crash; try again next cycle
                store.log(f"autopilot: {job} failed: {e!r} (will retry in 5 minutes)")
        progress.update(t=time.monotonic(), job=None)
        store.set("autopilot_busy", None)
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        store.set("autopilot_done", sorted(k for k in done if k.split(":")[1] >= week_ago))
        store.set("autopilot_heartbeat", now_ny().isoformat(timespec="seconds"))
        after = now_ny()                                     # the work may have taken minutes
        time.sleep(300 - (after.minute % 5) * 60 - after.second + 5)   # wake just after the next 5-minute mark


# ================================================================ commands
def cmd_status(cfg, store, args):
    p = study_progress(store, cfg)
    print("\n=== KESTREL ===")
    print(f"  Study: {p['calendar_days']} calendar days, {p['study_days']} trading days studied"
          + ("" if p["ready"] else f" (still need: {', '.join(p['missing'])})"))
    beat = store.get("autopilot_heartbeat")
    print(f"  Autopilot last seen: {beat or 'never (start it: python run.py autopilot)'}")
    paper_where = ({"alpaca": "your Alpaca PAPER account", "webull": "your Webull PAPER account"}[paper_broker(cfg)]
                   if uses_broker_paper(cfg)
                   else "simulated on this laptop (add ALPACA_PAPER keys to use Alpaca's paper account)")
    print(f"  Broker: {cfg['broker']}  |  prices: {data_source(cfg)}  |  paper trading: {paper_where}")
    if cfg["broker"] == "schwab":
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
        halted = ("  ** EMERGENCY EXIT: selling what it owns **" if store.get(f"exiting:{desk}")
                  else "  ** HALTED (paused): no new trades **" if store.get(f"halted:{desk}") else "")
        print(f"\n  --- {desk.upper()} desk: {phase.value} (step {STEP_NUMBER[phase]} of 4), "
              f"${desk_capital(cfg, desk, phase == Phase.LIVE):,.0f}{halted}")
        pricey = store.get(f"too_pricey:{desk}")
        if pricey and pricey["tickers"]:
            print(f"  Too pricey to buy (1 share > ${pricey['limit']}): "
                  + ", ".join(f"{t} ${v}" for t, v in pricey["tickers"].items()))
        card = forward_report(store, cfg) if desk == "swing" else day_forward_report(store)
        if len(card) and (desk == "day" or card["signals"].sum() > 0):
            print("  Study report card:\n    " + card.to_string().replace("\n", "\n    "))
        from aitrader.report import trades as trade_list
        for mode in (f"study-{desk}", f"paper-{desk}", f"live-{desk}"):      # in its head, paper, real
            curve = store.equity_curve(mode)
            if len(curve):
                start = desk_capital(cfg, desk, mode.startswith("live"))
                done = trade_list(store.fills(mode))
                won = sum(1 for t in done if t["result"] == "win")
                s = summarize(curve, store.fills(mode))
                gain = curve.iloc[-1] - start
                print(f"  {mode}: ${curve.iloc[-1]:,.2f} ({(curve.iloc[-1] / start - 1) * 100:+.2f}% since the start, "
                      f"{'-' if gain < 0 else '+'}${abs(gain):,.2f})  trades {len(done)} ({won} won)  "
                      f"max drawdown {s['max_drawdown_pct']}%")
                for t in done[:5]:
                    print(f"      {t['sold_on']} {t['ticker']}: spent ${t['spent']:,.2f}, got ${t['got_back']:,.2f}, "
                          f"{t['result'].upper()} {'-' if t['gain'] < 0 else '+'}${abs(t['gain']):,.2f} ({t['gain_pct']:+.1f}%)")
        print(f"  Next: {nxt[phase].format(desk=desk)}")

    print("\n  Recent journal:")
    for ts, msg in store.journal(10):
        print(f"    {ts}  {msg}")


def cmd_check(cfg, store, args):
    """Test every connection with the keys in .env, and say what to fix."""
    print(f"\nPrices ({data_source(cfg)}):")
    try:
        bars = MarketData(cfg).history(cfg["benchmark"], "1d")
        print(f"  OK: {cfg['benchmark']} last close ${bars['close'].iloc[-1]:,.2f} on {bars.index[-1]:%Y-%m-%d}")
    except Exception as e:
        print(f"  PROBLEM: {e!r}")
    if cfg["broker"] == "alpaca":
        from aitrader.alpaca_api import has_keys, trading_client
        from aitrader.brokers.alpaca_broker import AlpacaGateway
        for paper in (True, False):
            name = "Alpaca PAPER" if paper else "Alpaca LIVE"
            if not has_keys(cfg, paper):
                print(f"\n{name}: no keys in .env" + (" (fine until a desk earns real money)" if not paper else ""))
                continue
            try:
                a = AlpacaGateway(trading_client(cfg, paper)).account_summary()
                print(f"\n{name}: connected. cash ${a['cash']:,.2f}, equity ${a['equity']:,.2f}, "
                      f"trading blocked: {a['trading_blocked']}")
                budget = cfg["paper"]["starting_cash"] if paper else cfg["live"]["max_capital"]
                if paper and abs(a["equity"] - budget) > budget * 0.5:
                    print(f"  Tip: make a paper account with ${budget:,.0f} (Alpaca dashboard -> paper account menu "
                          "-> new paper account) so paper feels like your real account. The bot caps itself either way.")
            except Exception as e:
                print(f"\n{name}: PROBLEM {e!r}")
    elif cfg["broker"] == "schwab":
        try:
            prove_live_connection(cfg)
            print("\nSchwab: connected.")
        except Exception as e:
            print(f"\nSchwab: PROBLEM {e!r}")
    from aitrader import webull_api
    if webull_api.has_keys(cfg) or cfg["broker"] == "webull":
        print("\n" + webull_api.connect(cfg)["text"])


MENU = [
    ("Open the Kestrel app (your dashboard)", "dashboard"),
    ("Status: where is each desk, and what's next?", "status"),
    ("Check my Alpaca keys and price data", "check"),
    ("Edit my keys (opens the .env file)", "edit-keys"),
    ("Start the autopilot in THIS window (close the window to stop it)", "autopilot"),
    ("Keep the autopilot running in the BACKGROUND (starts at login, restarts itself)", "service-on"),
    ("Stop the background autopilot", "service-off"),
    ("Backtest: how would each strategy have done?", "backtest"),
    ("Write the trading plans (after the study month)", "plan"),
    ("After-market report: what it traded today and why", "report"),
    ("Start Stage 1: paper trade the momentum method now (no study month)", "start-stage1"),
    ("Approve a plan (starts paper trading)", "approve-plan"),
    ("Promote a desk to REAL money", "promote"),
    ("Connect Claude Code (Claude can see the bot, and your Schwab account read-only)", "connect-claude-code"),
    ("Connect Claude Desktop (same, for the Claude Desktop app)", "connect-claude"),
    ("Log in to Schwab (needed about every 5 days once you use Schwab)", "schwab-login"),
    ("EMERGENCY: sell everything the bot owns and stop", "kill"),
    ("Resume after an emergency stop", "resume"),
]


def cmd_menu(cfg, store, args):
    """A simple numbered menu, so you never have to remember commands."""
    from aitrader import mac_service
    from aitrader.config import ROOT
    note = ROOT / ".config_note"
    if note.exists():                                  # left by the app after an update
        print("\n" + note.read_text())
        note.unlink()
    while True:
        running = " (background autopilot: RUNNING)" if mac_service.is_running() else ""
        print(f"\n==== KESTREL{running} ====")
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  {i:>2}) {label}")
        print("   q) Quit this menu (a background autopilot keeps running)")
        choice = input("\nPick a number: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            continue
        action = MENU[int(choice) - 1][1]
        try:
            if action == "edit-keys":
                import subprocess
                subprocess.run(["open", "-e", str(ROOT / ".env")])
                print("Save the file in TextEdit, then pick 'Check my Alpaca keys'.")
            elif action == "service-on":
                mac_service.install(ROOT)
                print("Background autopilot is ON. It starts at login and restarts itself if it crashes.")
                print(f"Its log: {ROOT / 'data' / 'autopilot.log'}. Keep the lid open and the charger in.")
            elif action == "service-off":
                mac_service.uninstall()
                print("Background autopilot is OFF.")
            elif action == "dashboard":
                print(open_app())
            elif action == "connect-claude-code":
                from aitrader.claude_setup import connect_claude_code
                print(connect_claude_code(ROOT))
            elif action == "connect-claude":
                from aitrader.claude_setup import connect_claude_desktop
                print(connect_claude_desktop(ROOT))
            else:
                main([action], cfg=cfg, store=store)
        except KeyboardInterrupt:
            print("\n(stopped)")
        except Exception as e:
            print(f"\nPROBLEM: {e}")


def open_app() -> str:
    """Opens the Kestrel app; its window is the dashboard."""
    import subprocess
    if sys.platform != "darwin":
        return "The Kestrel app is for Mac."
    found = subprocess.run(["open", "-b", "com.aitrader.app"], capture_output=True).returncode == 0
    return ("Opened the Kestrel app." if found else
            "Couldn't find the Kestrel app. Drag it into Applications and open it once.")


def cmd_dashboard(cfg, store, args):
    print(open_app())


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
        close_in_head(cfg, store, desk)
        reset_paper(store, desk)
        set_phase(store, desk, Phase.PAPER, "plan approved by you")


def start_stage1(cfg, store) -> str:
    """Stage 1 of your plan: the swing desk starts paper trading the momentum method now, skipping the
    study month. Pretend money only; real money still needs the promotion rules and your typed yes."""
    from aitrader.planner import STAGE1_DESK, stage1_plan
    from aitrader.scanner import trade_candidates
    desk = STAGE1_DESK
    if not cfg["desks"][desk].get("enabled", True):
        raise ValueError(f"The {desk} desk is switched off in config.yaml.")
    phase = current_phase(store, desk)
    if phase == Phase.PAPER:
        raise ValueError(f"Stage 1 is already running (paper trading since {store.get(f'{desk}_paper_started_on')}).")
    if phase == Phase.LIVE:
        raise ValueError(f"The {desk} desk is trading real money; Stage 1 is paper only.")
    with trading_lock(cfg):
        plan = stage1_plan(cfg, trade_candidates(cfg))
        close_in_head(cfg, store, desk)
        reset_paper(store, desk)
        store.set(f"lessons:{desk}", None)
        store.set("stage", 1)
        set_phase(store, desk, Phase.PAPER, "Stage 1 started by you")
    days = cfg["promotion"]["min_trading_days"]
    return (f"Stage 1 started: the {desk} desk paper trades the {plan['strategy']} method with "
            f"${plan['capital']:,.0f} of pretend money for {days} trading days. It decides 15 minutes "
            "before each close, so keep the autopilot on. Nothing uses real money.")


TJR_TEST_EVERY_DAYS = 7


def run_tjr_test(cfg, store, data, today: str, force: bool = False) -> str:
    """TJR's history test on the day desk's 5-minute data (tjr.py), about once a week."""
    from aitrader.tjr import history_test
    last = store.get("tjr_history_test") or {}
    if not force and last.get("ran_on") and \
            (pd.Timestamp(today) - pd.Timestamp(last["ran_on"])).days < TJR_TEST_EVERY_DAYS:
        return "TJR test: done this week"
    bars, market = data.load("day")
    if not bars:
        return "TJR test: no 5-minute data yet"
    result = history_test(cfg, bars, market)
    result["ran_on"] = today
    store.set("tjr_history_test", result)
    t = result["tjr"]
    store.log(f"TJR history test ({result['days']} trading days of 5-minute data): {t.get('num_closed_trades')} "
              f"trades, profit factor {t.get('profit_factor')}, return {t.get('total_return_pct')}%: "
              + ("PASSED. Stage 2 can start (Setup)." if result["passed"] else
                 "not passed yet (" + "; ".join(result["why_not"]) + ")."))
    return "TJR test: " + ("passed" if result["passed"] else "not passed")


def start_stage2(cfg, store) -> str:
    """Stage 2 of your plan: the day desk paper trades TJR's model, once its history test has passed.
    Stage 1 keeps running on the swing desk. Pretend money only."""
    from aitrader.planner import STAGE2_DESK, stage2_plan
    desk = STAGE2_DESK
    test = store.get("tjr_history_test") or {}
    if not test.get("passed"):
        why = "; ".join(test.get("why_not") or ["it hasn't run yet (the autopilot runs it after a close)"])
        raise ValueError(f"TJR's model hasn't passed its history test: {why}.")
    phase = current_phase(store, desk)
    if phase == Phase.PAPER:
        raise ValueError(f"The {desk} desk is already paper trading (since {store.get(f'{desk}_paper_started_on')}).")
    if phase == Phase.LIVE:
        raise ValueError(f"The {desk} desk is trading real money; Stage 2 is paper only.")
    with trading_lock(cfg):
        stage2_plan(cfg, test)
        close_in_head(cfg, store, desk)
        reset_paper(store, desk)
        store.set(f"lessons:{desk}", None)
        store.set("stage2", True)
        set_phase(store, desk, Phase.PAPER, "Stage 2 started by you")
    return (f"Stage 2 started: the {desk} desk paper trades TJR's model with pretend money, 9:35-11:30am, and "
            "sells everything before the close. Stage 1 keeps running on the swing desk. Nothing uses real money.")


def cmd_start_stage1(cfg, store, args):
    print("Stage 1: the swing desk paper trades the momentum method (pretend money), starting now.")
    print("The 16-year research: research/history/RESULTS-methods.md")
    if input("Type YES to start Stage 1: ").strip() != "YES":
        print("Not started.")
        return
    try:
        print(start_stage1(cfg, store))
    except ValueError as e:
        print(e)


def cmd_report(cfg, store, args):
    """Prints the after-market report (today's is written now if the autopilot hasn't yet)."""
    from aitrader.report import recent_reports, write_after_market
    day = args.date or now_ny().strftime("%Y-%m-%d")
    found = [r for r in recent_reports(cfg, 60) if r["date"] == day]
    print(found[0]["markdown"] if found else write_after_market(cfg, store, day))


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
        if data_source(cfg) not in ("alpaca", "schwab"):
            print("Paper results pass! Real money needs real-time prices: set data.source to auto/alpaca.")
            continue
        if not cfg["live_trading_enabled"]:
            print("Paper results pass! To go live, set LIVE_TRADING_ENABLED=true in .env and run this again.")
            continue
        prove_live_connection(cfg)
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
        if store.get(f"exiting:{desk}"):
            phase = current_phase(store, desk)
            if phase in TRADING and broker_backed(cfg, phase) and not_flat(store, mode_of(phase, desk)):
                print(f"{desk}: still selling after the emergency stop, so it stays halted. It retries every "
                      f"5 minutes; if a sale is stuck, sell it yourself at the broker and try again.")
                continue
            store.set(f"exiting:{desk}", False)
        store.set(f"halted:{desk}", False)
        store.log(f"{desk} desk resumed by you (phase {current_phase(store, desk).value})")


def cmd_schwab_login(cfg, store, args):
    from aitrader.schwab_api import login
    login(cfg, manual=args.manual)


def main(argv=None, cfg=None, store=None):
    parser = argparse.ArgumentParser(description="AI trader for Alpaca and Charles Schwab")
    sub = parser.add_subparsers(dest="command", required=True)
    desk_help = "only this desk (default: all enabled desks)"
    sub.add_parser("autopilot")
    sub.add_parser("menu")
    sub.add_parser("status")
    sub.add_parser("check")
    sub.add_parser("dashboard")
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
    sub.add_parser("start-stage1")
    sub.add_parser("report").add_argument("--date", help="YYYY-MM-DD (default: today)")
    sub.add_parser("schwab-login").add_argument("--manual", action="store_true",
                                                help="print a login link instead of opening a browser")
    args = parser.parse_args(argv)

    cfg = cfg or load_config()
    store = store or Store(data_path(cfg, "aitrader.sqlite"))
    commands = {"menu": cmd_menu, "dashboard": cmd_dashboard, "autopilot": cmd_autopilot, "status": cmd_status, "check": cmd_check, "study": cmd_study, "trade": cmd_trade,
                "backtest": cmd_backtest, "plan": cmd_plan, "approve-plan": cmd_approve_plan,
                "start-stage1": cmd_start_stage1, "report": cmd_report,
                "promote": cmd_promote, "kill": cmd_kill, "resume": cmd_resume, "schwab-login": cmd_schwab_login}
    try:
        commands[args.command](cfg, store, args)
    except RuntimeError as e:
        store.log(f"STOPPED: {e}")
        if args.command != "menu" and argv is None:
            sys.exit(1)
    except KeyboardInterrupt:
        store.log("Stopped by you (Ctrl+C)")


if __name__ == "__main__":
    main()
