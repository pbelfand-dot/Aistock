"""
phone.py: Kestrel on your phone, through a private Telegram bot (and/or Pushover: pushover.py).

  Alerts: every buy and sell (what it spent, what it got back, WIN or LOSS), the after-close summary,
          the after-market report, and anything urgent (kill switch, emergency stop, pauses).
  Commands: /status  /trades  /report  /pause  /resume  /kill SELL EVERYTHING  /help

Setup (the Setup screen does this): make a bot with Telegram's @BotFather, paste its token, then send
the bot "/start <code>" with the pairing code Setup shows. Only that chat is ever answered.

The Mac only calls out to Telegram (no open ports, no web server). The token lives in ~/AITrader/.env.
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.request

from .config import ROOT, data_path

TOKEN_PATTERN = r"\d{5,15}:[A-Za-z0-9_-]{30,60}"
MAX_TEXT = 3900                                        # Telegram's limit is 4096 characters per message
ALERT_MARKS = ("] BUY ", "] SELL ", "!!!", "KILL SWITCH", "EMERGENCY", "PAUSED by", "Resumed",
               "PHASE CHANGE", "LEARNED:", "since the start", "WARNING:")
HELP = ("Kestrel on your phone:\n"
        "/status  how each account is doing\n"
        "/trades  the last 10 finished trades\n"
        "/report  the latest after-market report\n"
        "/pause   no new trades (stop-losses keep working)\n"
        "/resume  let the desks trade again\n"
        "/kill SELL EVERYTHING  emergency stop: sell everything the bot owns and halt")


def token(cfg) -> str:
    return cfg["secrets"].get("telegram_token", "")


def owner(cfg) -> str:
    return cfg["secrets"].get("telegram_chat", "")


def connected(cfg) -> bool:
    return bool(token(cfg) and owner(cfg))


def call(cfg, method: str, wait: float = 20, **params) -> dict:
    """One Telegram Bot API call (wait = how long to wait for the answer, in seconds)."""
    request = urllib.request.Request(f"https://api.telegram.org/bot{token(cfg)}/{method}",
                                     data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=wait) as resp:
        answer = json.loads(resp.read())
    if not answer.get("ok"):
        raise RuntimeError(answer.get("description", "Telegram said no"))
    return answer["result"]


def send(cfg, text: str, chat: str = None) -> bool:
    """Sends text (split into pieces if long). Never raises: a phone alert must never stop trading."""
    chat = chat or owner(cfg)
    if not (token(cfg) and chat):
        return False
    try:
        for start in range(0, len(text), MAX_TEXT):
            call(cfg, "sendMessage", chat_id=chat, text=text[start:start + MAX_TEXT], disable_web_page_preview=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- pairing
def pairing_code(cfg, new: bool = False) -> str:
    """The code you send the bot ("/start <code>") so only your phone is paired. Kept in data/ (owner-only)."""
    path = data_path(cfg, "phone_pairing_code")
    if new or not path.exists():
        path.write_text(f"{secrets.randbelow(900000) + 100000}")
        os.chmod(path, 0o600)
    return path.read_text().strip()


def save_owner(cfg, chat_id: str):
    from .app_api import env_file, write_env
    write_env(env_file(), {"TELEGRAM_CHAT_ID": chat_id})
    os.environ["TELEGRAM_CHAT_ID"] = chat_id
    cfg["secrets"]["telegram_chat"] = chat_id


# ---------------------------------------------------------------- alerts
def forwarder(cfg):
    """For Store.on_log: sends the journal lines that matter to your phone (trades, daily results,
    anything urgent), and the after-market report when it's written: to Telegram (the whole report)
    and/or Pushover (its summary; Pushover's limit is 1,024 characters), whichever is set up."""
    from . import pushover

    def forward(message: str):
        telegram, push = connected(cfg), pushover.has_keys(cfg)
        if not (telegram or push):
            return
        if message.startswith("After-market report for "):
            day = message.split()[3]
            path = data_path(cfg, f"reports/after-market-{day}.md")
            if telegram and path.exists():
                send(cfg, path.read_text())
            summary = pushover.report_alert(cfg, day) if push else ""
            if summary:
                pushover.send_later(cfg, summary, title=f"Kestrel: after-market report {day}", priority=0)
            return
        if any(mark in message for mark in ALERT_MARKS):
            if telegram:
                send(cfg, message)
            if push:
                pushover.send_later(cfg, message)
    return forward


# ---------------------------------------------------------------- commands
def status_text(cfg, store) -> str:
    from .config import active_desks, desk_capital
    from .phases import current_phase
    lines = ["Kestrel status"]
    beat = store.get("autopilot_heartbeat")
    lines.append(f"Autopilot last seen: {beat.replace('T', ' ') if beat else 'never'}")
    for desk in active_desks(cfg):
        lines.append(f"\n{desk.title()} desk: {current_phase(store, desk).value.replace('_', ' ').lower()}"
                     + (" (PAUSED)" if store.get(f"halted:{desk}") else ""))
        for kind in ("study", "paper", "live"):
            curve = store.equity_curve(f"{kind}-{desk}")
            if not len(curve):
                continue
            start = desk_capital(cfg, desk, kind == "live")
            value = float(curve.iloc[-1])
            prev = float(curve.iloc[-2]) if len(curve) > 1 else start
            name = {"study": "in its head", "paper": "paper", "live": "REAL"}[kind]
            lines.append(f"  {name}: ${value:,.2f} (last day {(value / prev - 1) * 100:+.2f}%, "
                         f"since the start {(value / start - 1) * 100:+.2f}%)")
    return "\n".join(lines)


def trades_text(cfg, store, n: int = 10) -> str:
    from .config import active_desks
    from .report import signed, trades
    done = []
    for desk in active_desks(cfg):
        for kind in ("study", "paper", "live"):
            done += [{**t, "account": kind} for t in trades(store.fills(f"{kind}-{desk}"), desk)]
    done.sort(key=lambda t: t["sold_on"], reverse=True)
    if not done:
        return "No finished trades yet."
    names = {"study": "head", "paper": "paper", "live": "REAL"}
    return "Last trades:\n" + "\n".join(
        f"{t['sold_on']} {t['ticker']} ({t['desk']}, {names[t['account']]}): spent ${t['spent']:,.2f}, "
        f"got ${t['got_back']:,.2f}, {t['result'].upper()} {signed(t['gain'])} ({t['gain_pct']:+.1f}%)"
        for t in done[:n])


def handle(cfg, store, text: str) -> str:
    """Your command -> the answer. Only your paired chat ever gets here."""
    from .app_api import KILL_PHRASE, handle as app_handle, pause_all
    words = text.strip().split(maxsplit=1)
    command = words[0].split("@")[0].lower() if words else ""
    rest = words[1].strip() if len(words) > 1 else ""
    if command == "/status":
        return status_text(cfg, store)
    if command == "/trades":
        return trades_text(cfg, store)
    if command == "/report":
        from .report import recent_reports
        reports = recent_reports(cfg, 60)
        chosen = [r for r in reports if not rest or r["date"] == rest]
        return chosen[0]["markdown"] if chosen else "No after-market report yet (it's written after each close)."
    if command == "/pause":
        return pause_all(cfg, store, "you, from your phone")
    if command == "/resume":
        return app_handle("resume", cfg)["message"]
    if command == "/kill":
        if rest != KILL_PHRASE:
            return f'Emergency stop not done. To confirm, send exactly: /kill {KILL_PHRASE}'
        return app_handle("kill", cfg, confirm=KILL_PHRASE)["message"]
    return HELP


def listen(cfg, store_factory, stop: threading.Event = None):
    """Long-polls Telegram for your messages and answers them (runs as a thread in the autopilot)."""
    offset = None
    while not (stop and stop.is_set()):
        try:                                            # waits up to 30 s for a message, then asks again
            updates = call(cfg, "getUpdates", wait=40, timeout=30, **({"offset": offset} if offset else {}))
        except Exception:
            time.sleep(15)                              # offline or Telegram down: try again soon
            continue
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            chat, text = str((message.get("chat") or {}).get("id", "")), message.get("text") or ""
            if not chat or not text:
                continue
            store = store_factory()
            try:
                if not owner(cfg):
                    if re.fullmatch(r"/start\s+" + re.escape(pairing_code(cfg)), text.strip()):
                        save_owner(cfg, chat)
                        store.log("Phone paired with Kestrel (Telegram)")
                        send(cfg, "Paired. Kestrel will message you here.\n\n" + HELP)
                    else:
                        send(cfg, "Send /start followed by the pairing code shown in Kestrel's Setup screen.", chat)
                elif chat == owner(cfg):
                    store.log(f"Phone command: {text.strip()[:60]}", echo=False)
                    send(cfg, handle(cfg, store, text))
                # anyone else: no answer at all
            finally:
                store.db.close()
