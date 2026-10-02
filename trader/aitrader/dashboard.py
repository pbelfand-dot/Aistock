"""
dashboard.py: what the Kestrel app's window shows, a brokerage-style view of your accounts.

snapshot() gathers it all in one go: account value vs. the S&P 500, positions,
activity, each desk's phase, study report card and plan, the watchlist, and the
bot's journal. The app gets it through app_api.py (no web server, no network).

It only reads the bot's own files (its database and saved prices). It never
talks to your broker, so it needs no keys.
"""
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import active_desks, data_path, data_source, desk_capital
from .market_hours import now_ny
from .performance import summarize
from .risk import shares
from .phases import STEP_NUMBER, current_phase, study_progress
from .study import day_forward_report, forward_report

WEB = Path(__file__).resolve().parent / "web" / "dashboard.html"    # the page the app shows


# ================================================================ the data
def _num(x, digits=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), digits)


def _price_history(cfg, ticker):
    """The bot's saved prices for a ticker: (daily closes, 5-minute closes), either may be None."""
    out = []
    for interval in ("1d", "5m"):
        path = data_path(cfg, f"cache/{data_source(cfg)}/{interval}/{ticker}.csv")
        try:
            out.append(pd.read_csv(path, index_col=0, parse_dates=True)["close"].dropna() if path.exists() else None)
        except Exception:                          # e.g. the autopilot is rewriting that file right now
            out.append(None)
    return out


def quote(cfg, ticker) -> dict:
    """Last price, change since the previous close, and a small price trail for a sparkline."""
    daily, intraday = _price_history(cfg, ticker)
    if intraday is not None and len(intraday):
        last = float(intraday.iloc[-1])
        today = intraday.index[-1].normalize()
        before = intraday[intraday.index < today]
        prev = float(before.iloc[-1]) if len(before) else None
        if daily is not None and len(daily[daily.index < today]):
            prev = float(daily[daily.index < today].iloc[-1])
        trail = intraday[intraday.index >= today].tolist()
    elif daily is not None and len(daily):
        last = float(daily.iloc[-1])
        prev = float(daily.iloc[-2]) if len(daily) > 1 else None
        trail = daily.iloc[-30:].tolist()
    else:
        return {"ticker": ticker, "last": None, "change_pct": None, "trail": []}
    change = (last / prev - 1) * 100 if prev else None
    return {"ticker": ticker, "last": _num(last), "change_pct": _num(change), "trail": [_num(v) for v in trail]}


def _account(cfg, store, kind: str) -> dict:
    """One 'account' like a brokerage shows it: kind is "paper" or "live" (both desks together)."""
    live = kind == "live"
    desks, curves, positions, activity = {}, {}, [], []
    for desk in active_desks(cfg):
        mode = f"{kind}-{desk}"
        curve = store.equity_curve(mode)
        fills = store.fills(mode)
        ledger = store.get(f"{mode}_ledger")
        capital = desk_capital(cfg, desk, live)
        stats = summarize(curve, fills) if len(curve) else None
        if len(curve):
            curves[desk] = curve
        stop_pct = cfg["desks"][desk]["risk"]["stop_loss_pct"]
        holdings = 0.0
        for t, p in (ledger or {}).get("positions", {}).items():
            q = quote(cfg, t)
            last = q["last"] if q["last"] is not None else p["avg_cost"]
            value = last * p["qty"]
            cost = p["avg_cost"] * p["qty"]
            positions.append({"desk": desk, "ticker": t, "qty": p["qty"], "avg_cost": _num(p["avg_cost"]),
                              "last": _num(last), "day_change_pct": q["change_pct"], "market_value": _num(value),
                              "gain": _num(value - cost), "gain_pct": _num((value / cost - 1) * 100) if cost else None,
                              "stop": _num(p["avg_cost"] * (1 - (p.get("stop_pct") or stop_pct) / 100)),
                              "stop_pct": p.get("stop_pct") or stop_pct, "opened_on": p["opened_on"],
                              "stop_at_broker": bool(p.get("stop_order_id"))})
            holdings += value
        # Right now, like a brokerage shows it: cash + what it owns at the latest prices.
        now_value = ledger["cash"] + holdings if ledger else (float(curve.iloc[-1]) if len(curve) else None)
        desks[desk] = {"started": bool(len(curve) or ledger), "capital": capital, "value": _num(now_value),
                       "stats": stats}
        for f in fills.itertuples():
            activity.append({"id": f.id, "date": f.date, "desk": desk, "side": f.side, "qty": shares(float(f.qty)),
                             "ticker": f.ticker, "price": _num(f.price), "amount": _num(f.qty * f.price),
                             "realized_pnl": _num(f.realized_pnl) if f.side == "SELL" else None,
                             "reason": f.reason})

    # The account's value each day = the desks added up. A desk that hasn't started
    # yet counts as its money sitting in cash, so the line doesn't jump when it starts.
    series = {}
    if curves:
        dates = sorted(set().union(*[c.index for c in curves.values()]))
        idx = pd.DatetimeIndex(dates)
        total = pd.Series(0.0, index=idx)
        for desk in active_desks(cfg):
            c = curves.get(desk)
            filled = (c.reindex(idx).ffill().fillna(desk_capital(cfg, desk, live)) if c is not None
                      else pd.Series(desk_capital(cfg, desk, live), index=idx))
            total += filled
            if c is not None:
                series[desk] = [_num(v) for v in c.reindex(idx).ffill()]
        series["total"] = [_num(v) for v in total]
        bench = _benchmark(cfg, idx, float(total.iloc[0]))
        if bench is not None:
            series["benchmark"] = bench
        dates = [d.strftime("%Y-%m-%d") for d in idx]
    else:
        dates, total = [], pd.Series(dtype=float)

    value = sum((d["value"] if d["value"] is not None else d["capital"]) for d in desks.values())
    before_today = total[total.index < pd.Timestamp(now_ny().date())] if len(total) else total
    prev = float(before_today.iloc[-1]) if len(before_today) else None      # the last close before today
    start = float(total.iloc[0]) if len(total) else None
    cash = sum((store.get(f"{kind}-{d}_ledger") or {}).get("cash", info["capital"])     # not started = all cash
               for d, info in desks.items())
    closed = [a["realized_pnl"] for a in activity if a["side"] == "SELL" and a["realized_pnl"] is not None]
    stats = summarize(total) if len(total) else None
    activity.sort(key=lambda a: (a["date"], a["id"]), reverse=True)

    # The trade report (report.py): every finished trade, each day's change, and the totals.
    from .report import calendar as calendar_rows, daily as daily_rows, totals as totals_row, trades as trade_rows
    done = sorted((t for d in active_desks(cfg) for t in trade_rows(store.fills(f"{kind}-{d}"), d)),
                  key=lambda t: t["sold_on"], reverse=True)
    holding = [{"desk": p["desk"], "ticker": p["ticker"], "qty": p["qty"], "bought_on": p["opened_on"],
                "spent": _num(p["avg_cost"] * p["qty"]), "value": p["market_value"], "gain": p["gain"],
                "gain_pct": p["gain_pct"]} for p in positions]
    start_value = sum(desk_capital(cfg, d, live) for d in active_desks(cfg))
    bench = series.get("benchmark") or []
    bench = [b for b in bench if b is not None]
    bench_ret = (bench[-1] / bench[0] - 1) * 100 if len(bench) >= 2 and bench[0] else None
    return {
        "kind": kind,
        "active": any(d["started"] for d in desks.values()),
        "value": _num(value), "cash": _num(cash),
        "day_change": _num(value - prev) if prev else None,
        "day_change_pct": _num((value / prev - 1) * 100) if prev else None,
        "total_return_pct": _num((value / start_value - 1) * 100) if start and start_value else None,   # vs the starting money
        "max_drawdown_pct": stats["max_drawdown_pct"] if stats else None,
        "closed_trades": len(closed),
        "win_rate_pct": _num(sum(1 for c in closed if c > 0) / len(closed) * 100, 1) if closed else None,
        "desks": desks, "dates": dates, "series": series,
        "positions": sorted(positions, key=lambda p: -(p["market_value"] or 0)),
        "activity": activity[:300],
        "trades": done[:300],
        "holding": holding,
        "daily": daily_rows(total, start_value)[:400] if len(total) else [],
        "calendar": calendar_rows(done, daily_rows(total, start_value) if len(total) else []),
        "totals": totals_row(done, holding, start_value, value, bench_ret, days=int(len(total))),
    }


def _benchmark(cfg, idx, start_value):
    daily, _ = _price_history(cfg, cfg["benchmark"])
    if daily is None or not len(daily):
        return None
    closes = daily.groupby(daily.index.normalize()).last().reindex(idx.normalize(), method="ffill")
    if closes.isna().all():
        return None
    first = closes.dropna().iloc[0]
    return [_num(v / first * start_value) if not pd.isna(v) else None for v in closes]


def _desk_info(cfg, store, desk) -> dict:
    phase = current_phase(store, desk)
    info = {"desk": desk, "phase": phase.value, "step": STEP_NUMBER[phase],
            "halted": bool(store.get(f"halted:{desk}")), "exiting": bool(store.get(f"exiting:{desk}")),
            "watchlist": cfg["desks"][desk]["watchlist"],
            "too_pricey": (store.get(f"too_pricey:{desk}") or {}).get("tickers", {})}
    info["lessons"] = store.get(f"lessons:{desk}")          # what it learned from its own trades (learning.py)
    card = forward_report(store, cfg) if desk == "swing" else day_forward_report(store)
    info["study"] = json.loads(card.reset_index().rename(columns={"index": "strategy"})
                               .to_json(orient="records")) if len(card) else []
    plan_path = data_path(cfg, f"trading_plan_{desk}.json")
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        from .challengers import current
        switched = store.get(f"strategy_switch:{desk}") if current(store, desk, plan.get("strategy")) != plan.get("strategy") else None
        info["plan"] = {"verdict": plan.get("verdict"), "strategy": current(store, desk, plan.get("strategy")),
                        "planned": plan.get("strategy"), "switched": switched,
                        "created_on": plan.get("created_on"), "narrative": plan.get("narrative"),
                        "scorecard": [{"strategy": r["strategy"], "eligible": r["eligible"],
                                       "return_pct": r["backtest"].get("total_return_pct"),
                                       "sharpe": r["backtest"].get("sharpe"),
                                       "max_drawdown_pct": r["backtest"].get("max_drawdown_pct"),
                                       "trades": r["backtest"].get("num_closed_trades"),
                                       "study_month": r.get("forward", {}).get("summary"),
                                       "why_not": "; ".join(r.get("rejected_because", []))}
                                      for r in plan.get("scorecard", [])]}
    return info


def snapshot(cfg, store) -> dict:
    """Everything the page shows, in one go."""
    beat = store.get("autopilot_heartbeat")
    minutes = None
    if beat:
        minutes = round((now_ny() - datetime.fromisoformat(beat)).total_seconds() / 60, 1)
    progress = study_progress(store, cfg)
    return {
        "generated_at": now_ny().isoformat(timespec="seconds"),
        "demo": bool(store.get("demo")),
        "broker": cfg["broker"], "prices": data_source(cfg), "benchmark": cfg["benchmark"],
        "autopilot": {"last_seen": beat, "minutes_ago": minutes},
        "study": progress,
        "desks": [_desk_info(cfg, store, d) for d in active_desks(cfg)],
        "accounts": {kind: _account(cfg, store, kind) for kind in ("study", "paper", "live")},
        "watchlist": [{"desk": d, **quote(cfg, t)} for d in active_desks(cfg) for t in cfg["desks"][d]["watchlist"]],
        "journal": [{"ts": ts, "message": m} for ts, m in store.journal(60)][::-1],
        "scan": _scan(cfg),
        "options_gap": _options_gap(store),
        "tjr_test": _tjr_test(store),
        "reports": _reports(cfg),
        "right_now": _right_now(cfg, store),
    }


def _reports(cfg) -> list:
    """The last week of after-market reports (report.py), newest first."""
    from .report import recent_reports
    try:
        return recent_reports(cfg, 7)
    except OSError:
        return []


JOB_NAMES = {"morning": "the morning check-in", "day": "a day-desk check", "swing": "the swing decision",
             "swing-stops": "a stop-loss check", "study": "the after-close study", "scan": "the stock scan",
             "report": "the after-market report", "options": "the options-gap watcher",
             "inplay": "finding today's stocks in play", "tjr": "TJR's history test"}


def thinking(cfg, store, now=None) -> dict:
    """The live Thinking tab: what the autopilot is doing this moment, and for each desk its latest check
    (the scores, the team's notes, what it did or why not), what it's watching, and today's earlier checks."""
    from datetime import timedelta
    from .market_hours import in_session
    from .phases import mode_of
    demo = cfg["data"].get("source") == "demo"
    if now is None and demo:                             # the demo's made-up days: show its last check
        from .phases import mode_of as _mode
        times = [(store.get(f"{_mode(current_phase(store, d), d)}_thinking") or {}).get("time", "")
                 for d in active_desks(cfg)]
        now = datetime.strptime(max(times), "%Y-%m-%d %H:%M") if any(times) else None
    now = now or now_ny()
    today = now.strftime("%Y-%m-%d")
    beat = store.get("autopilot_heartbeat")
    minutes = (now - datetime.fromisoformat(beat)).total_seconds() / 60 if beat else None
    running = minutes is not None and minutes < 12
    busy, step = store.get("autopilot_busy") or {}, store.get("autopilot_step") or {}
    if demo:
        live = {"busy": False, "text": f"Demo: what the bot was thinking at its last check on made-up prices "
                                       f"({now:%Y-%m-%d %H:%M})."}
    elif busy.get("job"):
        text = JOB_NAMES.get(busy["job"], busy["job"])
        text = text[:1].upper() + text[1:]
        if step.get("at", "") >= busy.get("since", "~"):
            text += f": {step['text']}"
        live = {"busy": True, "text": text + "…", "since": busy["since"][11:19]}
    elif running and in_session(now):
        nxt = (now + timedelta(minutes=5 - now.minute % 5)).replace(second=0, microsecond=0)
        live = {"busy": False, "text": f"Waiting for the next check at {nxt:%H:%M} (every 5 minutes while the "
                                       f"market is open)."}
    else:
        live = {"busy": False, "text": _right_now(cfg, store, now)["headline"]}
    scan = store.get("scan_status") or {}
    if scan.get("day") == today and scan.get("started") and not scan.get("finished") and not scan.get("error"):
        from .scanner import read_progress
        p = read_progress(cfg)
        where = (f"; {p['step']}: {p['done']:,} of {p['total']:,}" if p.get("total") and p.get("step") != "finished"
                 else "")
        live["also"] = f"In the background: scanning all US stocks (started {scan['started'][11:16]}{where})."

    desks = []
    for desk in active_desks(cfg):
        mode = mode_of(current_phase(store, desk), desk)
        account = {"study": "in its head", "paper": "paper", "live": "REAL money"}[mode.split("-")[0]]
        desks.append({**_desk_card(cfg, store, desk, mode, account, today),
                      "halted": bool(store.get(f"halted:{desk}"))})
    week = _weekend(cfg, store, now)
    if week.get("active") and not demo:
        live = {**live, "text": week["text"], "busy": week["replay"].get("running", False),
                "also": week.get("also") or live.get("also")}
    from . import challengers, in_play, macro
    early = in_play.load_premarket(cfg)
    return {"time": now.isoformat(timespec="seconds"), "running": running, "live": live, "desks": desks,
            "weekend": week, "macro": macro.status(cfg, now),
            "challengers": challengers.summary(store, active_desks(cfg)),
            "premarket": early if early.get("day") == today and "day" in active_desks(cfg) else None}


def _desk_card(cfg, store, desk, mode, account, today=None) -> dict:
    """One desk's latest check for the Thinking tab. today=None: the latest check, whatever its date
    (weekend practice replays past days)."""
    from .agents import team_parts
    from .report import why_not_buying
    from .strategies import all_strategies
    t = store.get(f"{mode}_thinking") or {}
    fresh = bool(t) and (today is None or t.get("time", "").startswith(today))
    day = t.get("time", "")[:10] if today is None else today
    team = t.get("team") if fresh else None
    style = "day" if desk == "day" else "swing"
    description = next((s.description for s in all_strategies(cfg, style) if s.name == t.get("strategy")), "")
    if desk == "crypto" and description:
        description += (" On crypto it runs on hourly bars instead of daily ones (its \"days\" are hours), and "
                        "Bitcoin stands in for the S&P 500.")
    watch = store.get(f"{mode}_watch") or {}
    checks = store.get(f"{mode}_checks") or {}
    return {
        "desk": desk, "mode": mode, "account": account, "halted": False, "today": fresh, "time": t.get("time"),
        "strategy": t.get("strategy"), "description": description,
        "buy_above": t.get("buy_above"), "sell_below": t.get("sell_below"),
        "top": t.get("top") or [], "holding": t.get("holding"), "max_positions": t.get("max_positions"),
        "cash": t.get("cash"), "orders": t.get("orders") or [], "why": why_not_buying(t) if t else "",
        "team": team_parts(team) if team and not team.get("error") else None,
        "team_error": (team or {}).get("error"),
        "watch": watch if day and watch.get("time", "").startswith(day) else None,
        "checks": list(reversed(checks.get("items", []))) if day and checks.get("date") == day else []}


def _weekend(cfg, store, now) -> dict:
    """Weekend practice (weekend.py) for the Thinking tab: what it's replaying, the crypto experiment,
    and how each practice account is doing. On weekdays: last weekend's results."""
    from . import weekend
    s = weekend.settings(cfg)
    st = weekend.state(store)
    active = weekend.is_weekend(now) and st.get("weekend") == weekend.weekend_of(now)
    out = {"active": active, "replay_on": s["replay"], "crypto_on": s["crypto"],
           "history": (store.get("weekend_history") or [])[-4:][::-1]}
    if not active:
        return out
    at = store.get("weekend_now") or {}
    seen = (now - datetime.fromisoformat(at["at"])).total_seconds() if at.get("at") else None
    replay = {"days_done": len(st.get("done", [])), "days_planned": len(st.get("days", [])),
              "pace": s["replay_minutes_per_day"], "running": seen is not None and seen < 180}
    if at.get("day"):
        replay.update(day=at["day"], label=f"{datetime.strptime(at['day'], '%Y-%m-%d'):%a %b %d, %Y}",
                      time=at["time"], n=at["n"])
    crypto = store.get("weekend_crypto") or {}
    names = {"weekend-day": ("day", "weekend replay"), "weekend-swing": ("swing", "weekend replay"),
             "weekend-crypto": ("crypto", "pretend money, live prices")}
    cards = [_desk_card(cfg, store, desk, mode, account) for mode, (desk, account) in names.items()
             if store.get(f"{mode}_thinking")]
    if not s["replay"]:
        text = "Weekend practice: the replay is off (Setup → Settings)."
    elif replay.get("day"):
        text = (f"Weekend practice: replaying {replay['label']} at {replay['time']} (day {replay['n']} this "
                f"weekend; about {replay['pace']} minutes per day).")
    elif not st.get("days"):
        text = "Weekend practice: no replay this weekend (not enough 5-minute prices saved on this Mac yet)."
    else:
        text = "Weekend practice: the replay starts within 5 minutes."
    also = ("Crypto: " + ("over for this weekend (everything sold)." if crypto.get("closed") else
                          "deciding at the top of every hour, stop-losses every 5 minutes, all sold Sunday 11:50pm.")
            ) if s["crypto"] else ""
    return {**out, "text": text, "also": also, "replay": replay, "cards": cards,
            "results": weekend.results(store, cfg)}


def _right_now(cfg, store, now=None) -> dict:
    """One glance: is Kestrel testing right now, and what is each desk doing or waiting for?"""
    from datetime import time as dtime
    from .market_hours import in_session, minutes_to_close, session_close
    from .phases import mode_of
    from .settlement import market_holidays
    now = now or now_ny()
    beat = store.get("autopilot_heartbeat")
    minutes = (now - datetime.fromisoformat(beat)).total_seconds() / 60 if beat else None
    running = minutes is not None and minutes < 12
    trading_day = now.weekday() < 5 and now.date() not in market_holidays(now.year)
    busy = store.get("autopilot_busy") or {}
    names = JOB_NAMES
    if not running and busy.get("job"):
        since = datetime.fromisoformat(busy["since"])
        took = (now - since).total_seconds() / 60
        headline = (f"The autopilot is busy with {names.get(busy['job'], busy['job'])} (since {since:%H:%M}, "
                    f"{took:.0f} min)." + (" If it's stuck, it restarts itself after 30 minutes." if took > 10 else ""))
    elif not running:
        headline = ("The autopilot isn't running, so nothing is being tested. Turn it on in Setup → Autopilot "
                    "and keep the Mac awake.") if minutes is None or minutes > 60 else \
                   (f"The autopilot hasn't checked in for {minutes:.0f} minutes (is the Mac asleep? To keep "
                    "trading with the lid closed, turn on lid-closed mode in Setup → Autopilot).")
    elif not trading_day:
        headline = "The market is closed today. Kestrel picks up again on the next trading day."
    elif now.time() < dtime(9, 30):
        headline = "The market opens at 9:30am New York time; Kestrel is ready."
    elif not in_session(now):
        done = data_path(cfg, f"reports/after-market-{now:%Y-%m-%d}.md").exists()
        headline = ("The market is closed for today. " + ("Today's after-market report is ready (Journal tab)."
                    if done else "The after-market report comes about 25 minutes after the close."))
    else:
        headline = f"Testing now: the autopilot checked in {'just now' if minutes < 1 else f'{minutes:.0f} min ago'}."

    lines = []
    open_now = running and trading_day and in_session(now)
    since_open = (now.hour * 60 + now.minute) - (9 * 60 + 30)
    for desk in active_desks(cfg):
        phase = current_phase(store, desk)
        mode = mode_of(phase, desk)
        account = {"study": "in its head", "paper": "paper", "live": "REAL money"}[mode.split("-")[0]]
        thinking = store.get(f"{mode}_thinking") or {}
        fills = store.fills(mode)
        today_fills = int((fills["date"].astype(str).str[:10] == now.strftime("%Y-%m-%d")).sum()) if len(fills) else 0
        last = (f" Last check {thinking['time'][-5:]}" + (f", top pick {thinking['top'][0]['ticker']} "
                f"({thinking['top'][0]['score']:.2f})" if thinking.get("top") else "") + ".") \
            if thinking.get("time", "").startswith(now.strftime("%Y-%m-%d")) else ""
        trades = f" {today_fills} trade{'s' if today_fills != 1 else ''} today." if today_fills else ""
        if store.get(f"halted:{desk}") and mode.split("-")[0] != "study":
            doing = "paused: no new trades (stop-losses still work). Resume in Setup → Start here."
        elif not open_now:
            doing = ("decides at 3:45pm on trading days." if desk == "swing"
                     else "trades between 10:00am and 3:30pm on trading days, and never holds overnight.")
        elif desk == "swing":
            decided = now.time() >= dtime(15, 45)
            doing = ("decided for today." if decided else
                     "decides at 3:45pm; until then it watches the stop-losses every 5 minutes.")
        else:
            close_in = minutes_to_close(now)
            name = (thinking.get("strategy") or (cfg["study"].get("in_its_head_strategy") or {}).get("day")
                    or "opening_range_breakout")
            orb = name == "opening_range_breakout"
            if name == "tjr_model" and close_in > cfg["desks"]["day"]["flatten_minutes_before_close"]:
                doing = ("watching for TJR's setup (a sweep below a low, a break back up, a pullback into the gap); "
                         "it buys only 9:35-11:30am." if since_open <= 120 else
                         "TJR's buying window (9:35-11:30am) is over for today; it only manages open trades.")
            elif since_open < 30 and orb:
                doing = "measuring the opening range; its first trade is possible after 10:00am."
            elif since_open < 15:
                doing = "waiting out the first minutes after the open."
            elif close_in <= cfg["desks"]["day"]["flatten_minutes_before_close"]:
                doing = "selling everything before the close (day trades never stay overnight)."
            elif close_in <= cfg["desks"]["day"]["last_entry_minutes_before_close"]:
                doing = "no new trades in the last 30 minutes; it sells everything by 3:50pm."
            else:
                doing = "checking every 5 minutes."
        lines.append(f"{desk.title()} desk ({account}): {doing}{last}{trades}")
    return {"ok": running, "headline": headline, "lines": lines}


def _tjr_test(store) -> dict:
    from .app_api import tjr_status
    return tjr_status(store)


def _options_gap(store) -> dict:
    """The options-gap watcher (options_flow.py): the latest look, the scorecard, the last graded calls."""
    from .options_flow import SIGNALS_KEY, scorecard
    signals = store.get(SIGNALS_KEY) or []
    return {"today": store.get("options_gap_today"), "card": scorecard(store),
            "recent": [x for x in signals if x["right"] is not None][-10:][::-1]}


def _scan(cfg) -> dict:
    """The daily all-stocks scan (scanner.py): the list, new listings, and their news."""
    from .scanner import load_list
    state = load_list(cfg)
    keep = ("rank", "symbol", "price", "momentum_pct", "return_1m_pct", "return_3m_pct", "days_listed",
            "since_first_listed_pct", "news", "news_count", "danger")
    return {"updated": state.get("updated"),
            "liked": [{k: r.get(k) for k in keep} for r in state.get("liked", [])],
            "new_listings": [{k: r.get(k) for k in keep} for r in state.get("new_listings", [])]}
