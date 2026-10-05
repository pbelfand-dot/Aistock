"""
agents.py: Kestrel's team. Every decision goes through five agents. Each has ONE job and writes a short
note that the next one reads, so the thinking is laid out step by step (the after-market report shows
the notes, and so does your phone):

  1. Scout     gathers the facts: prices, the strategy's scores, the daily scan, danger news, the options gap.
  2. Analyst   turns them into a view of each stock: what agrees, what conflicts.
  3. Trader    the orders from the desk's tested strategy (rules decide trades, not a chatbot).
  4. Risk      checks every buy before it goes: its size, danger news, stocks that move together, and
               option bets against it. It can only make things SAFER (skip a buy), never bolder, and only
               for the checks you switch on (config.yaml: agents.risk_vetoes). Otherwise it just says so.
               It also writes down the situation of every buy, and skips a buy that would repeat a
               mistake the desk has already made (mistakes.py; agents.learn_from_mistakes).
  5. Reviewer  after the close: grades the day and the options watcher, and passes on the lessons.

When the local AI (llm.py) is on, each agent's note is also written in plain English from that agent's
facts only: small, focused questions are much easier for a small model than one big one.
"""
import math

import pandas as pd

ROLES = {
    "scout": "You are the Scout on Kestrel's trading team. Say what the facts are, nothing else.",
    "analyst": "You are the Analyst on Kestrel's trading team. Say which stocks look strongest and weakest and "
               "where the signals agree or conflict.",
    "trader": "You are the Trader on Kestrel's trading team. Say what the desk did and the rule behind each order.",
    "risk": "You are the Risk officer on Kestrel's trading team. Say what you checked and anything you warned about.",
    "reviewer": "You are the Reviewer on Kestrel's trading team. Say how today went and the one lesson to keep.",
}
VETO_CHECKS = ("correlation", "options_gap")


def settings(cfg: dict) -> dict:
    s = {"enabled": True, "risk_vetoes": [], "correlation_limit": 0.85, "correlation_bars": 60,
         "learn_from_mistakes": True}
    s.update(cfg.get("agents") or {})
    s["risk_vetoes"] = [v for v in (s.get("risk_vetoes") or []) if v in VETO_CHECKS]
    return s


# ---------------------------------------------------------------- 1. Scout
def scout(scores: pd.Series, prices: pd.Series, positions: dict, cash: float, blocked, gaps: dict,
          strategy, max_positions: int, in_play: dict = None, lessons: list = None) -> dict:
    top = scores.dropna().sort_values(ascending=False).head(6)
    return {"top": [[t, round(float(v), 2)] for t, v in top.items()],
            "in_play": {t: r for t, r in (in_play or {}).items() if t in scores.index},
            "wont_repeat": [m["tag"] for m in lessons or []],
            "holding": sorted(positions), "slots": f"{len(positions)} of {max_positions}",
            "cash": round(float(cash), 2), "danger": sorted(set(blocked) - set(positions))[:8],
            "options_gaps": {t: d for t, d in gaps.items() if t in scores.index},
            "rule": f"{strategy.name}: buy at {strategy.buy_above:.2f}+, sell under {strategy.sell_below:.2f}"}


# ---------------------------------------------------------------- 2. Analyst
def analyst(facts: dict, strategy) -> list:
    """One line per stock worth talking about: its score, and whether the option bets agree."""
    views = []
    danger = set(facts["danger"])
    for ticker, score in facts["top"][:5]:
        gap = facts["options_gaps"].get(ticker)
        if ticker in danger:
            view = "avoid: danger headlines"
        elif score >= strategy.buy_above:
            view = "strong" + ("; option bets agree (calls heavy)" if gap == "bullish" else
                               "; but option bets lean against it (puts heavy)" if gap == "bearish" else "")
        elif score < strategy.sell_below:
            view = "weak"
        else:
            view = "middling" + ("; calls piling up ahead of the price" if gap == "bullish" else "")
        rvol = (facts.get("in_play") or {}).get(ticker)
        if rvol:
            view += f"; in play ({rvol}x its usual opening volume)"
        for fact in (facts.get("beyond") or {}).get(ticker) or []:
            view += f"; {fact}"
        views.append(f"{ticker} {score:.2f}: {view}")
    for ticker, gap in facts["options_gaps"].items():
        if ticker in facts["holding"] and gap == "bearish":
            views.append(f"{ticker} (owned): puts piling up while the price holds; watch it")
    return views


# ---------------------------------------------------------------- 3. Trader
def trader(orders: list) -> list:
    return [f"{o.side} {o.qty} {o.ticker} @ ${o.price:.2f}: {o.reason}" for o in orders] or ["no orders"]


# ---------------------------------------------------------------- 4. Risk
def correlations(bars: dict, ticker: str, others, lookback: int) -> dict:
    """Return correlation of `ticker` with each of `others` over the last `lookback` bars."""
    def returns(t):
        df = bars.get(t)
        return None if df is None or len(df) < lookback // 2 else df["close"].pct_change().iloc[-lookback:]
    mine, out = returns(ticker), {}
    if mine is None:
        return out
    for other in others:
        theirs = returns(other)
        if theirs is None:
            continue
        both = pd.concat([mine, theirs], axis=1).dropna()
        if len(both) >= 10:
            c = both.iloc[:, 0].corr(both.iloc[:, 1])
            if not math.isnan(c):
                out[other] = round(float(c), 2)
    return out


def risk(orders: list, positions: dict, bars: dict, gaps: dict, equity: float, cfg_agents: dict,
         lessons: list = None, in_play: dict = None, style: str = "swing", tags_out: dict = None,
         events: list = None, facts_by_ticker: dict = None) -> tuple:
    """(orders it lets through, its notes). Sells always go through (getting out is never riskier).
    tags_out: filled with the situation of each buy that goes through (mistakes.py)."""
    from .mistakes import matching, tags_for
    notes, keep = [], []
    held = set(positions)
    for o in orders:
        if o.side != "BUY":
            keep.append(o)
            continue
        checks = [f"{o.qty * o.price / equity * 100:.0f}% of the desk" if equity else "size ok"]
        veto = ""
        together = {t: c for t, c in correlations(bars, o.ticker, held, cfg_agents["correlation_bars"]).items()
                    if c >= cfg_agents["correlation_limit"]}
        if together:
            checks.append("moves with " + ", ".join(f"{t} ({c:.2f})" for t, c in together.items()))
            if "correlation" in cfg_agents["risk_vetoes"]:
                veto = "it moves with what we already own"
        if gaps.get(o.ticker) == "bearish":
            checks.append("puts are piling up against it")
            if "options_gap" in cfg_agents["risk_vetoes"] and not veto:
                veto = "option bets lean against it"
        tags = tags_for(o, bars, gaps, together, in_play, style,
                        list(events or []) + list((facts_by_ticker or {}).get(o.ticker) or []))
        repeat = matching(tags, lessons) if cfg_agents.get("learn_from_mistakes", True) else None
        if repeat and not veto:
            veto = f"that would repeat a mistake: {repeat['tag']} ({repeat['why']})"
        if veto:
            notes.append(f"SKIPPED BUY {o.ticker}: {veto} ({'; '.join(checks)})")
            continue
        notes.append(f"OK BUY {o.ticker}: " + "; ".join(checks)
                     + ("" if len(checks) == 1 else " (noted only)"))
        keep.append(o)
        if tags_out is not None:
            tags_out[o.ticker] = tags
        held.add(o.ticker)                              # the next buy is checked against this one too
    return keep, notes or ["nothing to check (no buys)"]


def review_orders(cfg: dict, orders: list, scores: pd.Series, prices: pd.Series, broker, bars: dict, gaps: dict,
                  strategy, max_positions: int, lessons: list = None, in_play: dict = None) -> tuple:
    """The team on one decision: (orders to send, the notes). Called between the strategy and the broker.
    lessons: the desk's mistakes not to repeat (mistakes.py); in_play: {ticker: relative volume} today."""
    s = settings(cfg)
    positions = broker.positions()
    equity = broker.equity(prices)
    facts = scout(scores, prices, positions, broker.cash(), broker.blocked, gaps, strategy, max_positions,
                  in_play=in_play, lessons=lessons)
    from . import macro
    day = max(df.index[-1] for df in bars.values()).strftime("%Y-%m-%d") if bars else ""
    facts["events"] = [macro.EVENTS[k]["name"] for k in macro.events_on(cfg, day)] if day else []
    beyond = {}
    if strategy.style == "swing":                        # quality, insider buys, short interest (fundamentals.py)
        try:
            from .fundamentals import tags as fundamental_tags
            wanted = list(dict.fromkeys([t for t, _ in facts["top"][:5]] + [o.ticker for o in orders if o.side == "BUY"]))
            beyond = fundamental_tags(cfg, wanted, day)
        except Exception:
            beyond = {}
    facts["beyond"] = beyond
    views = analyst(facts, strategy)
    plan = trader(orders)
    tags = {}
    keep, checks = risk(orders, positions, bars, gaps, equity, s, lessons=lessons, in_play=in_play,
                        style=strategy.style, tags_out=tags, events=macro.tags(cfg, day) if day else [],
                        facts_by_ticker=beyond)
    if len(keep) != len(orders):
        plan = trader(keep) if keep else ["no orders (Risk skipped the buys)"]
    return keep, {"scout": facts, "analyst": views, "trader": plan, "risk": checks, "tags": tags}


# ---------------------------------------------------------------- 5. Reviewer (after the close)
def reviewer(cfg: dict, store, desk: str, mode: str, today: str) -> list:
    from .options_flow import scorecard
    from .report import trades
    done = [t for t in trades(store.fills(mode), desk) if t["sold_on"] == today]
    lines = []
    if done:
        won = sum(1 for t in done if t["result"] == "win")
        lines.append(f"{len(done)} trade(s) finished today, {won} won; together "
                     f"{'+' if sum(t['gain'] for t in done) >= 0 else '-'}${abs(sum(t['gain'] for t in done)):,.2f}.")
    else:
        lines.append("No trades finished today.")
    lessons = (store.get(f"lessons:{desk}") or {}).get("strategies") or {}
    lines += [f"Lesson on {name}: {card['status']} ({card['why']})" for name, card in lessons.items()]
    mistakes = store.get(f"mistakes:{desk}") or []
    if mistakes:
        lines.append("Won't repeat: " + "; ".join(f"{m['tag']} ({m['why']})" for m in mistakes[:5]) + ".")
    card = scorecard(store)
    graded = sum(c["graded"] for c in card.values())
    if graded:
        edges = [d for d, c in card.items() if c["edge"]]
        lines.append(f"Options-gap watcher: {graded} calls graded; "
                     + (f"{' and '.join(edges)} gaps show an edge so far." if edges else "no proven edge yet."))
    return lines


# ---------------------------------------------------------------- the notes, for the report
def team_parts(team: dict) -> dict:
    """Each agent's note on one decision, as one line of plain text: {scout, analyst, trader, risk}."""
    f = team["scout"]
    facts = (f"top scores {', '.join(f'{t} {v:.2f}' for t, v in f['top']) or 'none'}; holding "
             f"{', '.join(f['holding']) or 'nothing'} ({f['slots']} slots), cash ${f['cash']:,.2f}; "
             f"danger news: {', '.join(f['danger']) or 'none'}; option gaps: "
             f"{', '.join(f'{t} {d}' for t, d in f['options_gaps'].items()) or 'none'}; rule: {f['rule']}"
             + (f"; in play: {', '.join(f'{t} {r}x' for t, r in f['in_play'].items())}" if f.get("in_play") else "")
             + (f"; won't repeat: {', '.join(f['wont_repeat'])}" if f.get("wont_repeat") else "")
             + (f"; big news today: {', '.join(f['events'])}" if f.get("events") else "") + ".")
    return {"scout": facts, "analyst": "; ".join(team["analyst"]) or "nothing stood out",
            "trader": "; ".join(team["trader"]), "risk": "; ".join(team["risk"])}


def notes_lines(cfg: dict, store, desk: str, mode: str, today: str, narrate: bool = False) -> list:
    """The report's 'team' section for one desk: each agent's note from the last decision, and the
    Reviewer's day. narrate: the local AI rewrites each note in plain English (facts only)."""
    thinking = store.get(f"{mode}_thinking") or {}
    team = thinking.get("team") if thinking.get("time", "").startswith(today) else None   # not an old day's notes
    review = reviewer(cfg, store, desk, mode, today)
    if team and team.get("error"):
        return [f"**The team:** {team['error']}.", "- Reviewer: " + " ".join(review), ""]
    if not team:
        return ["**The team:** no decision notes today (it made no decision today).", "- Reviewer: " + " ".join(review), ""]
    parts = {**team_parts(team), "reviewer": " ".join(review)}
    if narrate:                                          # the reasoning roles only: two short questions per desk
        from .llm import ask_local_llm
        for role, text in ((r, parts[r]) for r in ("analyst", "reviewer")):
            said = ask_local_llm(cfg, f"{ROLES[role]} In at most 40 words, using ONLY these facts (never "
                                      f"invent numbers or tickers):\n{text}")
            if said:
                parts[role] = said.strip().replace("\n", " ")
    names = {"scout": "Scout", "analyst": "Analyst", "trader": "Trader", "risk": "Risk", "reviewer": "Reviewer"}
    return ["**The team (the last decision, then the day):**"] + \
        [f"- {names[r]}: {parts[r]}" for r in names] + [""]
