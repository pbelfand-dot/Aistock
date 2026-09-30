"""
mcp_server.py: lets Claude (Claude Desktop or Claude Code) SEE your bot.

MCP ("Model Context Protocol") is how Claude plugs into other programs. With this
connected you can ask Claude things like "how is my bot doing?", "why did it sell
KO?" or "show me the day desk's plan".

What Claude CAN do here:  read status, journal, plans, positions, results and your
                          broker account; PAUSE trading (nothing is sold).
What Claude can NOT do:   buy, sell, resume, approve plans or go live. Only the bot
                          trades, and only you approve.

Set it up from the app menu ("Connect Claude"), or see the README.
"""
import io
import json
from contextlib import redirect_stdout
from functools import wraps

from mcp.server import MCPServer

import run
from aitrader.config import active_desks, data_path, load_config
from aitrader.performance import summarize
from aitrader.storage import Store

server = MCPServer(
    "ai-trader",
    instructions=("Read-only window into the user's AI trading bot (two desks: swing and day; phases "
                  "STUDY -> PLAN_REVIEW -> PAPER -> LIVE). You may pause trading if the user asks, "
                  "but you cannot trade, resume, approve plans or go live. Never invent numbers."))


def quiet(tool):
    """MCP talks over stdout, so anything the bot prints is captured and returned instead."""
    @wraps(tool)
    def wrapper(*args, **kwargs):
        printed = io.StringIO()
        with redirect_stdout(printed):
            result = tool(*args, **kwargs)
        return result if result is not None else printed.getvalue()
    return wrapper


def _open():
    cfg = load_config()
    return cfg, Store(data_path(cfg, "aitrader.sqlite"))


@server.tool()
@quiet
def bot_status() -> str:
    """Each desk's phase, study report card, paper/live results, and the recent journal."""
    cfg, store = _open()
    run.cmd_status(cfg, store, None)


@server.tool()
@quiet
def journal(lines: int = 40) -> str:
    """The bot's diary: what it did and why, newest last."""
    _, store = _open()
    return "\n".join(f"{ts}  {msg}" for ts, msg in store.journal(max(1, min(lines, 500))))


@server.tool()
@quiet
def trading_plan(desk: str = "swing") -> str:
    """The written trading plan for a desk ("swing" or "day"), with its scorecard."""
    cfg, _ = _open()
    path = data_path(cfg, f"trading_plan_{desk}.md")
    return path.read_text() if path.exists() else f"No {desk} plan yet (it's written after the study month)."


@server.tool()
@quiet
def positions() -> str:
    """What the bot owns right now, per desk: in its head (while studying), paper and live."""
    cfg, store = _open()
    out = {}
    for desk in active_desks(cfg):
        for mode in (f"study-{desk}", f"paper-{desk}", f"live-{desk}"):
            ledger = store.get(f"{mode}_ledger")
            if ledger:
                out[mode] = {"cash": round(ledger["cash"], 2),
                             "positions": {t: {"shares": p["qty"], "avg_cost": round(p["avg_cost"], 2),
                                               "bought_on": p["opened_on"]} for t, p in ledger["positions"].items()},
                             "open_orders": len(ledger.get("pending", []))}
    return json.dumps(out, indent=2) if out else "The bot doesn't hold anything yet."


@server.tool()
@quiet
def performance() -> str:
    """Scorecard for each desk: in its head (while studying), paper and live. Return, drawdown, win
    rate, profit factor, plus the last 20 finished trades (spent, got back, gain $ and %, win/loss)."""
    from aitrader.report import trades
    cfg, store = _open()
    out = {}
    for desk in active_desks(cfg):
        for mode in (f"study-{desk}", f"paper-{desk}", f"live-{desk}"):
            curve = store.equity_curve(mode)
            if len(curve):
                fills = store.fills(mode)
                out[mode] = {"value_now": round(float(curve.iloc[-1]), 2), **summarize(curve, fills),
                             "last_trades": trades(fills, desk)[:20]}
    return json.dumps(out, indent=2, default=str) if out else "No trading yet (in its head, paper or live)."


@server.tool()
@quiet
def broker_account() -> str:
    """Your broker account(s) as the broker sees them: cash, equity and holdings (read-only)."""
    cfg, _ = _open()
    if cfg["broker"] != "alpaca":
        return "Schwab: use the 'schwab' tools (read-only) for your Schwab account."
    from aitrader.alpaca_api import has_keys, trading_client
    from aitrader.brokers.alpaca_broker import AlpacaGateway
    out = {}
    for paper in (True, False):
        if has_keys(cfg, paper):
            gw = AlpacaGateway(trading_client(cfg, paper))
            out["alpaca_paper" if paper else "alpaca_live"] = {**gw.account_summary(), "holdings": gw.holdings()}
    return json.dumps(out, indent=2) if out else "No Alpaca keys in .env yet."


@server.tool()
@quiet
def knowledge(topic: str = "") -> str:
    """The bot's background notes: the owner's plan, the safety rules (incl. good faith violations),
    what 16 years of history showed, and what TJR's videos taught. Empty topic = the list."""
    from aitrader import knowledge as notes
    if not topic:
        return "Notes: " + ", ".join(notes.topics()) + ". Ask for one by name, or 'all'."
    return notes.pack() if topic == "all" else notes.read(topic)


@server.tool()
@quiet
def pause_trading(reason: str) -> str:
    """Pause ALL desks: no new trades until the user resumes in the app menu. Nothing is sold now;
    stop-losses keep protecting open positions, and the day desk still sells before the close
    (it never holds overnight). Use only when the user asks."""
    cfg, store = _open()
    for desk in active_desks(cfg):
        store.set(f"halted:{desk}", True)
    store.log(f"PAUSED by Claude at your request: {reason}")
    return ("All desks paused: no new trades. Nothing was sold now; stop-losses still protect open positions "
            "and the day desk still sells before the close. Resume from the app's Setup screen ('Resume trading').")


if __name__ == "__main__":
    server.run()                                       # stdio: Claude starts this program itself
