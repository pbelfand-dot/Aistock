"""
report.py: what the bot traded and how it did, the same way for all three accounts:

  study   trading "in its head" while a desk studies (pretend money, simulated on this Mac)
  paper   paper trading (pretend money)
  live    real money

For each account: every trade (what it bought, what it spent, what it got back, the gain or loss in
dollars and percent, win or lose), each day's value and change, and the overall totals.
"""
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
    out.append("**What it did today:**")
    if len(todays):
        out += [_fill_line(f, {}) for f in todays.itertuples(index=False)]
    else:
        why = thinking.get("why_no_buys") or ""
        fresh = [t for t in thinking.get("top") or [] if not t["owned"]]
        if not why and thinking.get("holding", 0) >= thinking.get("max_positions", 99):
            why = f"all {thinking['max_positions']} position slots were full"
        elif not why and fresh and fresh[0]["score"] < thinking.get("buy_above", 1):
            why = (f"nothing new scored high enough (the best it didn't own was {fresh[0]['ticker']} at "
                   f"{fresh[0]['score']:.2f}; it needs {thinking['buy_above']:.2f})")
        out.append(f"- No trades. {why[:1].upper() + why[1:] if why else ''}".rstrip())
    out.append("")
    if thinking.get("top"):
        picks = ", ".join(f"{t['ticker']} {t['score']:.2f}" + (" (owns it)" if t["owned"] else "")
                          for t in thinking["top"][:8])
        out += [f"**Its thinking at the last check ({thinking['time'][-5:]}):** top scores: {picks}. "
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
            out.append(f"- {t}: {p['qty']} shares bought {p['opened_on']} at {_money(p['avg_cost'])}{gain}; "
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

    from .options_flow import report_lines
    out += report_lines(store)

    out += scan_lines(cfg, store, today)
    hold = store.get("earnings_hold:swing") or {}
    if hold.get("day") == today and hold.get("tickers"):
        out += ["## Earnings soon (the swing desk isn't buying these)", "",
                "- " + ", ".join(f"{t}: reports {d}" for t, d in sorted(hold["tickers"].items())), ""]
    out += in_play_lines(cfg, store, today)

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
    state, status = load_list(cfg), store.get("scan_status") or {}
    out = ["## Its stock list (the daily scan)", ""]
    if status.get("error"):
        out.append(f"- The last scan ({status.get('day')}, try {status.get('tries')}) FAILED: {status['error']}")
    elif status.get("started") and not status.get("finished"):
        out.append(f"- A scan started at {status['started'][11:16]} and is still running (or was cut short: it "
                   "tries again).")
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
    history = store.get("in_play_history") or {}
    for kind in ("study", "paper", "live"):
        split = in_play.results(store.fills(f"{kind}-day"), history)
        if split["in play"]["trades"] or (kind != "study" and split["fixed list"]["trades"]):
            parts = [f"{name}: {g['trades']} trades, {g['won']} won, {signed(g['pnl'])}"
                     for name, g in split.items() if g["trades"]]
            out.append(f"- Day trades so far ({ACCOUNT_NAMES[kind]}): " + "; ".join(parts))
    out.append("")
    return out


def write_after_market(cfg, store, today: str) -> str:
    """Writes data/reports/after-market-<day>.md (plus a plain-English summary from the local AI when
    it's on) and notes it in the journal. Returns the report."""
    from .config import data_path
    from .llm import ask_local_llm
    text = after_market(cfg, store, today)
    summary = ask_local_llm(cfg, "You are Kestrel, the owner's trading bot. In under 120 words, using ONLY the "
                                 "facts in this report (never invent numbers), tell the owner what you traded "
                                 "today and why (follow the team's notes: Scout, Analyst, Trader, Risk, "
                                 "Reviewer), how it went, and what you'll watch tomorrow.\n\n" + text)
    if summary:
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
