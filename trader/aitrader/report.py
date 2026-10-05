"""
report.py: what the bot traded and how it did, the same way for all three accounts:

  study   trading "in its head" while a desk studies (pretend money, simulated on this Mac)
  paper   paper trading (pretend money)
  live    real money

For each account: every trade (what it bought, what it spent, what it got back, the gain or loss in
dollars and percent, win or lose), each day's value and change, and the overall totals.
"""
from datetime import datetime

import pandas as pd

from .risk import shares

MODES = ("study", "paper", "live")
LABELS = {"study": "In its head (while studying)", "paper": "Paper (practice money)", "live": "Real money"}


def _r(x, digits=2):
    return None if x is None or pd.isna(x) else round(float(x), digits)


def trades(fills: pd.DataFrame, desk: str = "") -> list:
    """Finished trades, newest first: each sale matched to what was paid for those shares."""
    lots, out = {}, []
    for f in fills.itertuples(index=False):
        qty, price = shares(float(f.qty)), float(f.price)
        if f.side == "BUY":
            lot = lots.setdefault(f.ticker, {"qty": 0, "cost": 0.0, "opened": str(f.date)[:10], "why": str(f.reason)})
            lot["qty"] += qty
            lot["cost"] += qty * price
            continue
        lot = lots.get(f.ticker)
        if not lot or lot["qty"] <= 0:
            continue
        sold = min(qty, lot["qty"])
        avg = lot["cost"] / lot["qty"]
        spent, got = sold * avg, sold * price
        pnl = float(f.realized_pnl) if f.realized_pnl is not None and not pd.isna(f.realized_pnl) else got - spent
        out.append({"desk": desk, "ticker": f.ticker, "qty": sold, "bought_on": lot["opened"],
                    "sold_on": str(f.date)[:10], "buy_price": _r(avg), "sell_price": _r(price),
                    "spent": _r(spent), "got_back": _r(got), "gain": _r(pnl),
                    "gain_pct": _r(pnl / spent * 100) if spent else None,
                    "result": "win" if pnl > 0 else "loss" if pnl < 0 else "even",
                    "days_held": int((pd.Timestamp(str(f.date)[:10]) - pd.Timestamp(lot["opened"])).days),
                    "why_bought": lot["why"], "why_sold": str(f.reason)})
        lot["cost"] -= sold * avg
        lot["qty"] -= sold
        if lot["qty"] <= 0:
            del lots[f.ticker]
    return out[::-1]


def daily(curve: pd.Series, start_value: float = None) -> list:
    """Each day's value and change (newest first). The first day compares with the starting money."""
    rows, prev = [], start_value
    for day, value in curve.dropna().items():
        change = value - prev if prev else None
        rows.append({"date": pd.Timestamp(day).strftime("%Y-%m-%d"), "value": _r(value), "change": _r(change),
                     "change_pct": _r(change / prev * 100) if prev else None})
        prev = value
    return rows[::-1]


def calendar(done: list, days: list) -> list:
    """The P&L calendar (oldest first): for each day with trading, the money made or lost on trades that
    finished that day (realized), how many, how many won and lost, and the account value's change."""
    out = {}

    def day(d):
        return out.setdefault(d, {"date": d, "realized": 0.0, "trades": 0, "wins": 0, "losses": 0, "change": None})
    for t in done:
        row = day(t["sold_on"])
        row["realized"] += t["gain"] or 0.0
        row["trades"] += 1
        row["wins"] += t["result"] == "win"
        row["losses"] += t["result"] == "loss"
    for r in days:
        day(r["date"])["change"] = r["change"]
    for row in out.values():
        row["realized"] = _r(row["realized"])
    return [out[d] for d in sorted(out)]


def totals(done: list, open_positions: list, start_value: float, value_now: float,
           benchmark_return_pct: float = None, days: int = 0) -> dict:
    """The overall numbers: money in, money out, gains, wins and losses."""
    wins = [t for t in done if t["result"] == "win"]
    losses = [t for t in done if t["result"] == "loss"]
    realized = sum(t["gain"] or 0 for t in done)
    unrealized = sum(p.get("gain") or 0 for p in open_positions)
    total_return = (value_now / start_value - 1) * 100 if start_value and value_now is not None else None
    best = max(done, key=lambda t: t["gain_pct"] or 0) if done else None
    worst = min(done, key=lambda t: t["gain_pct"] or 0) if done else None
    return {
        "start_value": _r(start_value), "value_now": _r(value_now), "days": days,
        "gain": _r(value_now - start_value) if start_value and value_now is not None else None,
        "return_pct": _r(total_return),
        "benchmark_return_pct": _r(benchmark_return_pct),
        "beat_benchmark": (total_return > benchmark_return_pct
                           if total_return is not None and benchmark_return_pct is not None else None),
        "trades_closed": len(done), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": _r(len(wins) / len(done) * 100, 1) if done else None,
        "spent_total": _r(sum(t["spent"] or 0 for t in done) + sum(p.get("spent") or 0 for p in open_positions)),
        "realized_gain": _r(realized), "unrealized_gain": _r(unrealized),
        "avg_win_pct": _r(sum(t["gain_pct"] for t in wins) / len(wins)) if wins else None,
        "avg_loss_pct": _r(sum(t["gain_pct"] for t in losses) / len(losses)) if losses else None,
        "best": {"ticker": best["ticker"], "gain_pct": best["gain_pct"], "gain": best["gain"]} if best else None,
        "worst": {"ticker": worst["ticker"], "gain_pct": worst["gain_pct"], "gain": worst["gain"]} if worst else None,
        "open_positions": len(open_positions),
    }


def day_line(store, mode: str, start_value: float, today: str) -> str:
    """One line for the journal after the close: today's result and the running totals."""
    curve = store.equity_curve(mode)
    if not len(curve) or curve.index[-1].strftime("%Y-%m-%d") != today:      # didn't trade today
        return ""
    value = float(curve.iloc[-1])
    before = curve[curve.index < pd.Timestamp(today)]
    prev = float(before.iloc[-1]) if len(before) else start_value
    done = trades(store.fills(mode))
    todays = [t for t in done if t["sold_on"] == today]
    won = sum(1 for t in done if t["result"] == "win")
    text = (f"[{mode}] {today}: value ${value:,.2f}, today {(value / prev - 1) * 100:+.2f}% "
            f"({signed(value - prev)}); since the start {(value / start_value - 1) * 100:+.2f}% "
            f"({signed(value - start_value)}); {len(done)} trades finished, {won} won, {len(done) - won} didn't")
    if todays:
        text += "; today: " + ", ".join(f"{t['ticker']} {t['gain_pct']:+.1f}% ({signed(t['gain'])})" for t in todays)
    return text


# ---------------------------------------------------------------- the after-market report
ACCOUNT_NAMES = {"study": "in its head (pretend money while it studies)", "paper": "paper (practice money)",
                 "live": "REAL MONEY"}


def _money(x):
    return "--" if x is None else f"${x:,.2f}"


def signed(x) -> str:
    """+$12.30 / -$4.10 (not $-4.10)."""
    return f"{'-' if x < 0 else '+'}${abs(x):,.2f}"


def _fill_line(f, spent_by_ticker) -> str:
    amount = float(f.qty) * float(f.price)
    if f.side == "BUY":
        return f"- BUY {shares(float(f.qty))} {f.ticker} @ ${float(f.price):.2f} (spent ${amount:,.2f}): {f.reason}"
    pnl = float(f.realized_pnl or 0)
    cost = amount - pnl
    verdict = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "even"
    pct = f", {pnl / cost * 100:+.1f}%" if cost > 0 else ""
    return (f"- SELL {shares(float(f.qty))} {f.ticker} @ ${float(f.price):.2f} (got back ${amount:,.2f}; "
            f"{verdict} {signed(pnl)}{pct}): {f.reason}")


def why_not_buying(thinking: dict) -> str:
    """Why a decision bought nothing: the reason it gave, or what the scores and slots show."""
    why = thinking.get("why_no_buys") or ""
    fresh = [t for t in thinking.get("top") or [] if not t["owned"]]
    if not why and thinking.get("holding", 0) >= thinking.get("max_positions", 99):
        why = f"all {thinking['max_positions']} position slots were full"
    elif not why and fresh and fresh[0]["score"] < thinking.get("buy_above", 1):
        why = (f"nothing new scored high enough (the best it didn't own was {fresh[0]['ticker']} at "
               f"{fresh[0]['score']:.2f}; it needs {thinking['buy_above']:.2f})")
    return why


def _when(stamp) -> str:
    """'Fri Oct 2, 15:49' from '2026-10-02 15:49'."""
    try:
        t = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""
    return f"{t:%a %b} {t.day}, {t:%H:%M}"


def gap_lines(store, today: str) -> list:
    """When the autopilot wasn't running during market hours today (run.note_gap)."""
    gaps = store.get("autopilot_gaps") or {}
    items = gaps.get("items") if gaps.get("day") == today else []
    if not items:
        return []
    out = ["## The autopilot today", ""]
    for g in items:
        out.append(f"- **Not running from {g['from']} to {g['to']}** (the Mac asleep, off, unplugged or frozen)"
                   + (f": it missed {' and '.join(g['missed'])}." if g.get("missed") else "."))
    out += ["- To keep it running: leave the Mac plugged in with lid-closed mode on (Setup → Autopilot), and turn on "
            "Alert me if Kestrel stops (Setup → Your phone) so your phone tells you when it happens.", ""]
    return out


def _desk_section(cfg, store, desk, kind, today) -> list:
    from .config import desk_capital
    from .dashboard import quote
    mode = f"{kind}-{desk}"
    start = desk_capital(cfg, desk, kind == "live")
    curve = store.equity_curve(mode)
    fills = store.fills(mode)
    todays = fills[fills["date"].astype(str).str[:10] == today] if len(fills) else fills
    thinking = store.get(f"{mode}_thinking") or {}
    out = [f"## {desk.title()} desk: {ACCOUNT_NAMES[kind]}", ""]
    if thinking.get("strategy"):
        from .strategies import all_strategies
        desc = next((s.description for s in all_strategies(cfg, desk) if s.name == thinking["strategy"]), "")
        out += [f"**Strategy: `{thinking['strategy']}`.** {desc} It buys at a score of "
                f"{thinking['buy_above']:.2f} or more and sells below {thinking['sell_below']:.2f}.", ""]
    if len(curve):
        value = float(curve.iloc[-1])
        before = curve[curve.index < pd.Timestamp(today)]
        prev = float(before.iloc[-1]) if len(before) else start
        out += [f"**Result:** value {_money(value)}; today {(value / prev - 1) * 100:+.2f}% ({signed(value - prev)}); "
                f"since the start {(value / start - 1) * 100:+.2f}% ({signed(value - start)}).", ""]
    fresh = thinking.get("time", "").startswith(today)
    when = thinking["time"][-5:] if fresh else _when(thinking.get("time"))
    out.append("**What it did today:**")
    if len(todays):
        out += [_fill_line(f, {}) for f in todays.itertuples(index=False)]
    elif not fresh:
        out.append(f"- **It made no decision today.** Its last check was {when or 'never'}: the autopilot wasn't "
                   "running when it was due (see \"The autopilot today\" below).")
    else:
        why = why_not_buying(thinking)
        out.append(f"- No trades. {why[:1].upper() + why[1:] if why else ''}".rstrip())
    out.append("")
    if thinking.get("top"):
        picks = ", ".join(f"{t['ticker']} {t['score']:.2f}" + (" (owns it)" if t["owned"] else "")
                          for t in thinking["top"][:8])
        out += [f"**Its thinking at the last check ({when}{'' if fresh else ', not today'}):** top scores: {picks}. "
                f"It held {thinking['holding']} of {thinking['max_positions']} positions with "
                f"{_money(thinking.get('cash'))} cash."
                + (f" Not buying more because: {thinking['why_no_buys']}." if thinking.get("why_no_buys") else ""), ""]
    from .agents import notes_lines, settings as team_settings
    if team_settings(cfg)["enabled"]:
        out += notes_lines(cfg, store, desk, mode, today, narrate=bool((cfg.get("llm") or {}).get("enabled")))
    ledger = store.get(f"{mode}_ledger") or {}
    positions = ledger.get("positions", {})
    if positions:
        stop_pct = cfg["desks"][desk]["risk"]["stop_loss_pct"]
        out.append("**Holding overnight:**")
        for t, p in positions.items():
            last = quote(cfg, t)["last"]
            gain = f", now {_money(last)} ({(last / p['avg_cost'] - 1) * 100:+.1f}%)" if last else ""
            own = p.get("stop_pct") or stop_pct
            out.append(f"- {t}: {p['qty']:g} share{'' if p['qty'] == 1 else 's'} bought {p['opened_on']} at "
                       f"{_money(p['avg_cost'])}{gain}; "
                       f"stop-loss {_money(p['avg_cost'] * (1 - own / 100))} ({own:g}% below"
                       + (", sized to how much it moves)" if p.get("stop_pct") else ")"))
        out.append("")
    lessons = store.get(f"lessons:{desk}") or {}
    cards = lessons.get("strategies") or {}
    mistakes = store.get(f"mistakes:{desk}") or []
    if (cards and lessons.get("mode") == mode) or mistakes:
        out.append("**What it has learned from its own trades:**")
        if lessons.get("mode") == mode:
            out += [f"- {name}: {card['status']} ({card['why']})" for name, card in cards.items()]
            if lessons.get("avoid"):
                out.append(f"- Not buying in: {', '.join(lessons['avoid'])}")
        from .mistakes import note_lines
        out += note_lines(mistakes)
        out.append("")
    done = trades(fills)
    if done:
        won = sum(1 for t in done if t["result"] == "win")
        out += [f"**All finished trades so far:** {len(done)}, {won} won, {len(done) - won} didn't; "
                f"together {signed(sum(t['gain'] or 0 for t in done))}.", ""]
    return out


def after_market(cfg, store, today: str) -> str:
    """The end-of-day report: the market, what each desk traded and why, what it was thinking, what it
    learned, how the strategies it compares are doing, changes to its stock list, and what's next."""
    from .config import active_desks
    from .dashboard import _price_history, quote
    from .learning import conditions
    from .phases import current_phase, mode_of
    out = [f"# After-market report: {pd.Timestamp(today):%A, %B %d, %Y}", ""]

    bench = cfg["benchmark"]
    q = quote(cfg, bench)
    daily, _ = _price_history(cfg, bench)
    mood = ""
    if daily is not None and len(daily) >= 200:
        row = conditions(daily).iloc[-1]
        mood = "; ".join(v for v in row.values if isinstance(v, str))
    if q["last"] is not None:
        out += [f"**The market:** {bench} closed at {_money(q['last'])}"
                + (f" ({q['change_pct']:+.2f}% today)" if q["change_pct"] is not None else "")
                + (f"; {mood}." if mood else "."), ""]

    out += gap_lines(store, today)
    for desk in active_desks(cfg):
        current = mode_of(current_phase(store, desk), desk).split("-")[0]
        for kind in MODES:
            fills = store.fills(f"{kind}-{desk}")
            traded_today = len(fills) and (fills["date"].astype(str).str[:10] == today).any()
            if kind == current or traded_today:
                out += _desk_section(cfg, store, desk, kind, today)

    out += ["## The strategies it compares (the study)", ""]
    from .strategies import all_strategies
    from .study import day_forward_report, forward_report
    swing_card, day_card = forward_report(store, cfg), day_forward_report(store)
    for desk in active_desks(cfg):
        card = swing_card if desk == "swing" else day_card
        for s in all_strategies(cfg, desk):
            row = card.loc[s.name].to_dict() if len(card) and s.name in card.index else {}
            if desk == "swing":
                score = (f"{int(row.get('signals') or 0)} graded buy ideas, hit rate "
                         f"{row.get('hit_rate_pct') if row.get('hit_rate_pct') is not None else '--'}%, edge "
                         f"{row.get('edge_pct') if row.get('edge_pct') is not None else '--'}%") if row else "not graded yet"
            else:
                score = (f"{int(row.get('num_closed_trades') or 0)} shadow trades, return "
                         f"{row.get('total_return_pct', '--')}%, win rate {row.get('win_rate_pct', '--')}%") if row else "no shadow trades yet"
            out.append(f"- **{desk} / {s.name}**: {score}. {s.description}")
    out.append("")
    try:                                                   # new ideas racing the current method (challengers.py)
        from .challengers import lines as challenger_lines
        out += challenger_lines(store, active_desks(cfg))
    except Exception as e:
        out += [f"- (couldn't add the challengers: {e!r})", ""]

    from .options_flow import report_lines
    out += report_lines(store)

    out += scan_lines(cfg, store, today)
    hold = store.get("earnings_hold:swing") or {}
    if hold.get("day") == today and hold.get("tickers"):
        out += ["## Earnings soon (the swing desk isn't buying these)", "",
                "- " + ", ".join(f"{t}: reports {d}" for t, d in sorted(hold["tickers"].items())), ""]
    out += in_play_lines(cfg, store, today)
    for section in (lambda: why_lines(cfg, store, today), lambda: filing_lines(cfg, today),
                    lambda: _macro_lines(cfg, today)):
        try:                                               # a missing source never stops the report
            out += section()
        except Exception as e:
            out += [f"- (couldn't add a section: {e!r})", ""]

    out += ["## Next", ""]
    for desk in active_desks(cfg):
        phase = current_phase(store, desk).value
        when = "decides at 3:45pm ET and checks stop-losses every 5 minutes" if desk == "swing" \
            else "decides every 5 minutes and sells everything before the close"
        out.append(f"- {desk.title()} desk ({phase.replace('_', ' ').lower()}): {when}.")
    return "\n".join(out).rstrip() + "\n"


def scan_lines(cfg, store, today: str) -> list:
    """The daily scan of all US stocks: its list, and whether the scan is actually working."""
    from .scanner import is_on, load_list, settings
    if not is_on(settings(cfg)["enabled"]):
        return ["## Its stock list (the daily scan)", "", "- The scan of all US stocks is off (Setup -> Settings).", ""]
    from .scanner import read_progress
    state, status = load_list(cfg), store.get("scan_status") or {}
    out = ["## Its stock list (the daily scan)", ""]
    if status.get("error"):
        out.append(f"- The last scan ({status.get('day')}, try {status.get('tries')}) FAILED: {status['error']}")
    elif status.get("started") and not status.get("finished"):
        p = read_progress(cfg)
        where = (f" (at {p['step']}: {p['done']:,} of {p['total']:,})" if p.get("total") and p.get("step") != "finished"
                 else "")
        out.append(f"- A scan started at {status['started'][11:16]} and is still running{where}. Each piece it "
                   "finishes is saved, so a restart or an update picks up where it stopped.")
    tries = store.get("scan_tries") or {}
    if tries.get("day") == today and len(tries.get("items") or []) > 1:
        out.append("- Scan tries today: " + "; ".join(
            f"{t['kind']} #{t['try']} at {(t.get('started') or '')[11:16] or '?'}: "
            + ("finished" if t.get("finished") else f"failed ({t['error']})" if t.get("error") else "cut short or running")
            for t in tries["items"]))
    if not state.get("updated"):
        out += ["- No stock list yet: the scan hasn't finished on this Mac, so the swing desk only picks from its "
                "watchlist. It scans after each close (and in the morning if the evening scan didn't finish).", ""]
        return out
    joined = [r["symbol"] for r in state.get("liked", []) if r.get("first_listed") == today]
    left = [s for s, h in state.get("history", {}).items() if h.get("left_on") == today]
    danger = [f"{r['symbol']} ({', '.join(r['danger'])})" for r in state.get("liked", []) if r.get("danger")]
    top = ", ".join(r["symbol"] for r in state.get("liked", [])[:10])
    picks = ", ".join(r["symbol"] for r in (state.get("swing_picks") or [])[:10])
    if status.get("finished") and status.get("summary"):
        out.append(f"- Last scan ({status['day']} {status['finished'][11:16]}): {status['summary'].removeprefix('scan: ')}")
    out += [f"- Top 10 by 12-month strength: {top or '--'} (updated {state['updated']})",
            f"- The swing desk also considers (strongest it can afford): {picks or 'none'}",
            f"- New today: {', '.join(joined) or 'none'}; dropped off: {', '.join(left) or 'none'}",
            f"- Danger news (won't buy): {', '.join(danger) or 'none'}", ""]
    return out


def why_lines(cfg, store, today: str) -> list:
    """Why they moved: what it owns, and the scan's top picks that moved 3%+ today, with the latest
    headline and SEC filing for each (a hint, not proof: news can follow a move as well as cause it)."""
    from .scanner import load_list
    from .stock_info import why_moved
    held = list(dict.fromkeys(t for kind in MODES for d in cfg["desks"]
                              for t in ((store.get(f"{kind}-{d}_ledger") or {}).get("positions") or {})))
    picks = [r["symbol"] for r in (load_list(cfg).get("swing_picks") or [])[:10]]
    out = []
    for t in list(dict.fromkeys(held + picks))[:20]:
        w = why_moved(cfg, t)
        if w["today_pct"] is None or (t not in held and abs(w["today_pct"]) < 3):
            continue
        said = [f"{h['headline']} ({h.get('source') or 'news'}, {str(h.get('time') or '')[11:16] or h.get('time', '')})"
                for h in w["headlines"][:1]]
        said += [f"SEC {f['what']} ({f['ago']})" for f in w["filings"][:1]]
        week = f", {w['week_pct']:+.1f}% in 5 days" if w["week_pct"] is not None else ""
        out.append(f"- {t} {w['today_pct']:+.1f}% today{week}" + (" (owns it)" if t in held else "")
                   + (": " + "; ".join(said) if said else ": no news or filings found"))
    return (["## Why they moved", "", *out, ""]) if out else []


def _macro_lines(cfg, today: str) -> list:
    from datetime import datetime
    from . import macro
    return macro.lines(cfg, datetime.strptime(today, "%Y-%m-%d").replace(hour=16, minute=25))


def filing_lines(cfg, today: str) -> list:
    """Serious SEC filings: the stocks it won't buy because of them."""
    from . import sec_filings
    danger = sec_filings.danger_tickers(cfg)
    if not danger:
        return []
    return ["## SEC filings: not buying", "",
            *[f"- {t}: {', '.join(r.removeprefix('SEC: ') for r in reasons)}" for t, reasons in danger.items()], ""]


def in_play_lines(cfg, store, today: str) -> list:
    """Today's stocks in play (in_play.py), and whether trading them has gone better than the fixed list."""
    from . import in_play
    if not in_play.is_on(cfg):
        return []
    state = in_play.load(cfg)
    out = ["## Stocks in play (the day desk's morning scan)", ""]
    if state.get("day") == today:
        names = ", ".join(f"{p['symbol']} ({p['rvol']}x usual volume)" for p in state.get("picks") or [])
        out.append(f"- Today: {names or 'nothing unusual'} (of {state.get('checked', 0)} busy stocks checked)")
        if state.get("skipped"):
            out.append(f"- Skipped for danger news: {', '.join(state['skipped'])}")
    else:
        out.append("- No list today (it needs the evening scan's pool and Alpaca data); the day desk used its watchlist.")
    early = in_play.load_premarket(cfg)
    if early.get("day") == today:
        names = ", ".join(f"{p['symbol']} {p['gap_pct']:+.1f}% on {p['volume_pct']:.0f}% of a day's volume"
                          for p in early.get("picks") or [])
        out.append(f"- Pre-market movers (about 9:20): {names or 'none moving on heavy volume'}"
                   + ("; on the day desk's list" if early.get("trade") else
                      "; shadow traded only, until they prove they help (Challengers)" if names else ""))
    history = store.get("in_play_history") or {}
    for kind in ("study", "paper", "live"):
        split = in_play.results(store.fills(f"{kind}-day"), history)
        if split["in play"]["trades"] or (kind != "study" and split["fixed list"]["trades"]):
            parts = [f"{name}: {g['trades']} trades, {g['won']} won, {signed(g['pnl'])}"
                     for name, g in split.items() if g["trades"]]
            out.append(f"- Day trades so far ({ACCOUNT_NAMES[kind]}): " + "; ".join(parts))
    out.append("")
    return out


def trim_words(text: str, limit: int) -> str:
    """The local AI sometimes runs long: keep whole lines up to about `limit` words, never ending on a heading."""
    kept, words = [], 0
    for line in text.strip().splitlines():
        n = len(line.split())
        if words + n > limit and kept:
            break
        kept.append(line)
        words += n
    while kept and (kept[-1].lstrip().startswith("#") or not kept[-1].strip() or kept[-1].rstrip().endswith(":")):
        kept.pop()
    return "\n".join(kept)


def summary_facts(cfg, store, today: str) -> str:
    """The few facts the local AI may use for the plain-English summary, desk by desk (given the whole report,
    a small model mixed up the two desks)."""
    from .config import active_desks, desk_capital
    from .phases import current_phase, mode_of
    lines = []
    for desk in active_desks(cfg):
        kind = mode_of(current_phase(store, desk), desk).split("-")[0]
        mode = f"{kind}-{desk}"
        curve, fills = store.equity_curve(mode), store.fills(mode)
        start = desk_capital(cfg, desk, kind == "live")
        head = f"{desk.upper()} DESK ({ACCOUNT_NAMES[kind]})"
        if len(curve):
            value = float(curve.iloc[-1])
            before = curve[curve.index < pd.Timestamp(today)]
            prev = float(before.iloc[-1]) if len(before) else start
            head += f": value {_money(value)}, today {(value / prev - 1) * 100:+.2f}%, since the start {(value / start - 1) * 100:+.2f}%"
        lines.append(head)
        todays = fills[fills["date"].astype(str).str[:10] == today] if len(fills) else fills
        for f in todays.itertuples(index=False):
            lines.append(f"- {f.side} {f.qty:g} {f.ticker} at {_money(f.price)}: {f.reason}")
        thinking = store.get(f"{mode}_thinking") or {}
        if not thinking.get("time", "").startswith(today):
            lines.append("- It made NO decision today (the autopilot wasn't running when it was due).")
        else:
            if not len(todays):
                lines.append(f"- No trades. {why_not_buying(thinking)}")
            owned = [t["ticker"] for t in thinking.get("top") or [] if t["owned"]]
            lines.append(f"- Holding {thinking.get('holding', 0)} of {thinking.get('max_positions')} positions"
                         + (f" ({', '.join(owned)})" if owned else "") + f", cash {_money(thinking.get('cash'))}")
    for g in ((store.get("autopilot_gaps") or {}).get("items") or []) \
            if (store.get("autopilot_gaps") or {}).get("day") == today else []:
        lines.append(f"AUTOPILOT: not running {g['from']}-{g['to']}" + (f"; missed {' and '.join(g['missed'])}" if g.get("missed") else ""))
    from .macro import has_key, upcoming
    if has_key(cfg):
        soon = upcoming(cfg, datetime.strptime(today, "%Y-%m-%d").replace(hour=16, minute=30))
        if soon:
            lines.append(f"NEXT BIG NEWS: {soon[0]['name']} {soon[0]['label']}")
    return "\n".join(lines)


def write_after_market(cfg, store, today: str) -> str:
    """Writes data/reports/after-market-<day>.md (plus a plain-English summary from the local AI when
    it's on) and notes it in the journal. Returns the report."""
    from .config import data_path
    from .llm import ask_local_llm
    text = after_market(cfg, store, today)
    from datetime import timedelta
    nxt = datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    summary = ask_local_llm(cfg, (
        "You are Kestrel, the owner's trading bot. Write at most 5 short bullet points (under 120 words in all), "
        "using ONLY the facts below: what each desk did today and why, how it went, and what you'll watch on the "
        f"next trading day, {nxt:%A %B} {nxt.day}. The swing desk and the day desk are separate accounts: never mix "
        "their numbers. Never invent numbers, dates or events, and never guess why the market or a stock moved.\n\n")
        + summary_facts(cfg, store, today))
    if summary:
        summary = trim_words(summary, 160)
        title, rest = text.split("\n", 1)
        text = f"{title}\n\n## In plain English\n\n{summary.strip()}\n{rest}"
    path = data_path(cfg, f"reports/after-market-{today}.md")
    path.write_text(text)
    store.log(f"After-market report for {today} is ready (Journal tab; {path.name})")
    return text


def recent_reports(cfg, days: int = 7) -> list:
    """The latest after-market reports, newest first: [{"date", "markdown"}]."""
    from .config import data_path
    folder = data_path(cfg, "reports/x").parent
    files = sorted(folder.glob("after-market-*.md"), reverse=True)[:days]
    return [{"date": f.stem.replace("after-market-", ""), "markdown": f.read_text()} for f in files]
