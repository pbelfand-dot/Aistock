"""
app_api.py: how the Kestrel app (its window) talks to the bot.

The app runs `python -m aitrader.app_api <action>` from the AITrader folder and shows
the JSON this prints. No web server and no network: the app starts this helper
directly, like any Mac app runs a helper program.

  snapshot [--demo]                          everything the window shows
  pause [--demo]                             no new trades (stop-losses keep working)
  kill --confirm "SELL EVERYTHING" [--demo]  the emergency stop
  demo-build                                 fresh demo data (made-up prices, about a minute)
  update-policy                              is real money involved? (the app asks before updating if so)
  setup-status                               keys, autopilot and each desk's next step (the Setup screen)
  save-keys  < {"key_id": .., "secret": ..}  saves Alpaca PAPER keys to .env (read from stdin, never argv)
  check-keys                                 tests the Alpaca paper keys and the price data
  autopilot-on / autopilot-off               the background autopilot (starts at login, restarts itself)
  resume                                     un-pause the desks (not while an emergency exit is still selling)
  save-settings < {name: value}              broker, real-money cap, account type, paper money (kept on updates)
  save-live-keys < {"key_id", "secret"}      Alpaca LIVE keys (saving them never turns real money on)
  save-schwab-keys < {"app_key", ...}        Schwab app key/secret, callback address, account number
  schwab-login-start / schwab-login-finish   log in to Schwab: open the page, then paste the address you land on
  check-schwab                               tests the Schwab login (read-only)
  connect-claude < {"which": "code"|"desktop"}  lets Claude see the bot (and Schwab, read-only)
  start-stage1                               Stage 1: the swing desk paper trades momentum now (pretend money)
  save-phone < {"token": ..}                 your phone: a private Telegram bot for alerts and commands (phone.py)
  phone-test                                 sends your phone a test message
  phone-screen-send                          sends your phone the link to the Kestrel screen (Tailscale)

--demo works on the demo folder (data/demo) instead of your real data.
"""
import argparse
import contextlib
import json
import math
import os
import re
import sys
from types import SimpleNamespace

from .config import load_config
from .storage import Store

KILL_PHRASE = "SELL EVERYTHING"


def pause_all(cfg, store, who: str) -> str:
    """Every desk: no new trades. Nothing is sold now; stop-losses keep protecting what the bot
    owns, and the day desk still sells before the close. Resume from the menu."""
    from .config import active_desks
    for desk in active_desks(cfg):
        store.set(f"halted:{desk}", True)
    store.log(f"PAUSED by {who}: no new trades. Stop-losses still protect what it owns.")
    return ("Paused: no new trades. Nothing was sold now; stop-losses still protect what it owns, and the "
            "day desk still sells before the close. Resume from the Setup menu.")


def real_money_status(cfg, store) -> dict:
    """Is real money involved right now? The app updates itself automatically only when it isn't;
    otherwise it asks you first, so new code never takes over real-money trading unannounced."""
    from .phases import Phase, current_phase
    reasons = []
    if cfg.get("live_trading_enabled"):
        reasons.append("real-money trading is switched on (LIVE_TRADING_ENABLED=true)")
    for desk in cfg["desks"]:
        if current_phase(store, desk) == Phase.LIVE:
            reasons.append(f"the {desk} desk is trading real money")
        saved = store.get(f"live-{desk}_ledger")
        if saved and (saved.get("positions") or saved.get("pending")):
            reasons.append(f"the {desk} desk owns real shares or has real orders open")
    return {"real_money": bool(reasons), "reasons": reasons}


# ---------------------------------------------------------------- the Setup screen
PAPER_KEYS = ("ALPACA_PAPER_API_KEY", "ALPACA_PAPER_SECRET_KEY")
STDIN_ACTIONS = {"save-keys", "save-settings", "save-live-keys", "save-schwab-keys", "schwab-login-finish",
                 "connect-claude", "save-phone"}                     # these read their details from stdin (never argv)

NEXT_STEP = {
    "STUDY": "Studying: the bot watches the market and grades its strategies with no money involved. "
             "Keep the autopilot on.",
    "STAGE1": "Stage 1: paper trading the momentum method with pretend money. Keep the autopilot on; "
              "it decides 15 minutes before each close.",
    "PLAN_REVIEW": "A trading plan is ready. Read it in Research & plans, then approve it from the full "
                   "Setup menu (Terminal) to start paper trading.",
    "PAPER": "Paper trading with pretend money. Keep the autopilot on; its results decide if it may move up.",
    "LIVE": "Trading real money. Keep the autopilot on and watch the Journal.",
}


def env_file():
    from .config import ROOT
    return ROOT / ".env"


def write_env(path, updates: dict):
    """Sets NAME=value lines in .env, keeping every other line (and comment) as it was. Owner-only file."""
    lines = path.read_text().splitlines() if path.exists() else []
    out, done = [], set()
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if name in updates:
            out.append(f"{name}={updates[name]}")
            done.add(name)
        else:
            out.append(line)
    out += [f"{name}={value}" for name, value in updates.items() if name not in done]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


LIVE_KEYS = ("ALPACA_LIVE_API_KEY", "ALPACA_LIVE_SECRET_KEY")
SCHWAB_KEYS = ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "SCHWAB_CALLBACK_URL", "SCHWAB_ACCOUNT_NUMBER")


def _key(value, what: str, pattern=r"[A-Za-z0-9]{10,64}") -> str:
    value = str(value or "").strip()
    if not re.fullmatch(pattern, value):
        raise ValueError(f"That {what} doesn't look right: copy the whole thing (no spaces).")
    return value


def save_live_keys(payload: dict) -> dict:
    key_id = _key(payload.get("key_id"), "live key ID")
    secret = _key(payload.get("secret"), "live secret", r"[A-Za-z0-9/+=_-]{20,128}")
    if key_id.upper().startswith("PK"):
        raise ValueError("That's a PAPER key. Real-money keys come from Alpaca's live account (they start with AK).")
    write_env(env_file(), dict(zip(LIVE_KEYS, (key_id, secret))))
    restart_autopilot()
    return {"message": "Real-money keys saved on this Mac only. Nothing trades real money until a desk earns it "
                       "AND you switch it on in the full Setup menu with a typed confirmation."}


def save_schwab_keys(payload: dict) -> dict:
    app_key = _key(payload.get("app_key"), "Schwab App Key", r"[A-Za-z0-9]{16,64}")
    secret = _key(payload.get("app_secret"), "Schwab Secret", r"[A-Za-z0-9]{8,64}")
    callback = str(payload.get("callback_url") or "https://127.0.0.1:8182").strip()
    if not re.fullmatch(r"https://[^\s]+", callback) or callback.endswith("/"):
        raise ValueError("The callback address must match your Schwab app EXACTLY, e.g. https://127.0.0.1:8182 "
                         "(https, no slash at the end).")
    account = str(payload.get("account_number") or "").strip()
    if account and not re.fullmatch(r"\d{6,12}", account):
        raise ValueError("The account number is digits only (leave it empty if you have one Schwab account).")
    write_env(env_file(), dict(zip(SCHWAB_KEYS, (app_key, secret, callback, account))))
    restart_autopilot()
    return {"message": "Schwab keys saved on this Mac only. Next: Open Schwab login."}


def save_phone(cfg, payload: dict) -> dict:
    """Saves the Telegram bot token (after checking it with Telegram) and makes a new pairing code."""
    from . import phone
    token = str(payload.get("token", "")).strip()
    if not re.fullmatch(phone.TOKEN_PATTERN, token):
        raise ValueError("That doesn't look like a Telegram bot token (it looks like 1234567890:AA...). "
                         "Copy it from @BotFather.")
    cfg["secrets"]["telegram_token"] = token
    try:
        bot = phone.call(cfg, "getMe")
    except Exception as e:
        raise ValueError(f"Telegram didn't accept that token ({e}). Copy it again from @BotFather.") from None
    write_env(env_file(), {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": ""})     # a new bot: pair again
    code = phone.pairing_code(cfg, new=True)
    restart_autopilot()
    return {"message": f"Saved on this Mac only. Now open @{bot.get('username')} in Telegram and send: /start {code}",
            "bot": bot.get("username"), "code": code}


def phone_test(cfg) -> dict:
    from . import phone
    if not phone.connected(cfg):
        return {"ok": False, "text": "Not paired yet: send your bot /start and the pairing code first."}
    ok = phone.send(cfg, "Kestrel test message: your phone is connected.")
    return {"ok": ok, "text": "Sent. Check Telegram." if ok else "Couldn't reach Telegram. Is the Mac online?"}


def check_schwab(cfg) -> dict:
    from .brokers.schwab_broker import SchwabGateway
    from .schwab_api import account_hash, get_client, token_days_left
    try:
        client = get_client(cfg)
        gateway = SchwabGateway(client, account_hash(client, cfg["secrets"]["account_number"]))
        left = token_days_left(cfg)
        return {"ok": True, "text": f"Schwab: connected. Settled cash ${gateway.cash():,.2f}. "
                                    f"Log in again within {left:.1f} days."}
    except Exception as e:
        return {"ok": False, "text": f"Schwab: {e}"}


def connect_claude(which: str) -> dict:
    from .claude_setup import connect_claude_code, connect_claude_desktop
    from .config import ROOT
    if which not in ("code", "desktop"):
        raise ValueError("Pick Claude Code or Claude Desktop.")
    text = connect_claude_code(ROOT) if which == "code" else connect_claude_desktop(ROOT)
    return {"message": text}


def gfv_status(cfg, store) -> dict:
    """Good faith violations in the last 12 months (real-money ledgers), and whether cash rules are on."""
    from datetime import date
    from .brokers.base import GFV_LIMIT, Ledger
    from .config import is_cash_account
    today = date.today().isoformat()
    count = 0
    for desk in cfg["desks"]:
        saved = store.get(f"live-{desk}_ledger")
        if saved:
            count += Ledger.from_dict(saved).gfv_count(today)
    return {"cash_rules": is_cash_account(cfg), "violations": count, "limit": GFV_LIMIT}


def save_keys(payload: dict) -> dict:
    key_id = str(payload.get("key_id", "")).strip()
    secret = str(payload.get("secret", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9]{10,64}", key_id):
        raise ValueError("That key ID doesn't look right: copy the whole Key ID from Alpaca (letters and numbers).")
    if not re.fullmatch(r"[A-Za-z0-9/+=_-]{20,128}", secret):
        raise ValueError("That secret doesn't look right: copy the whole Secret Key from Alpaca.")
    if key_id.upper().startswith("AK"):
        raise ValueError("That's a LIVE (real money) key. Paste your PAPER key: in Alpaca, switch to "
                         "Paper Trading first, then generate keys (paper key IDs start with PK).")
    write_env(env_file(), dict(zip(PAPER_KEYS, (key_id, secret))))
    restarted = restart_autopilot()
    return {"message": "Saved on this Mac only (~/AITrader/.env)."
                       + (" The autopilot restarted to use them." if restarted else "")}


def check_keys(cfg) -> dict:
    """Tests the paper keys and the price data, the way `run.py check` does, as data for the app."""
    from .config import data_source
    from .market_data import MarketData
    out = {}
    try:
        bars = MarketData(cfg).history(cfg["benchmark"], "1d")
        out["prices"] = {"ok": True, "text": f"Prices ({data_source(cfg)}): {cfg['benchmark']} closed at "
                                             f"${bars['close'].iloc[-1]:,.2f} on {bars.index[-1]:%b %-d}."}
    except Exception as e:
        out["prices"] = {"ok": False, "text": f"Prices ({data_source(cfg)}): problem: {e}"}
    from .alpaca_api import has_keys, trading_client
    if not has_keys(cfg, True):
        out["paper"] = {"ok": False, "text": "Alpaca paper: no keys yet. Paper trading is simulated on this Mac "
                                             "until you add them."}
        return out
    try:
        from .brokers.alpaca_broker import AlpacaGateway
        a = AlpacaGateway(trading_client(cfg, True)).account_summary()
        out["paper"] = {"ok": not a["trading_blocked"],
                        "text": f"Alpaca paper: connected. Cash ${a['cash']:,.2f}, value ${a['equity']:,.2f}."
                                + (" Trading is blocked on this account." if a["trading_blocked"] else "")}
    except Exception as e:
        out["paper"] = {"ok": False, "text": f"Alpaca paper: couldn't connect ({e}). Check you copied both keys "
                                             f"from the PAPER account."}
    return out


def restart_autopilot() -> bool:
    """A running background autopilot read .env when it started: restart it so new keys take effect.
    Reinstalling (not just kickstarting) also moves older installs to the current service setup."""
    from . import mac_service
    from .config import ROOT
    if not mac_service.is_running():
        return False
    mac_service.install(ROOT)
    return True


def autopilot_problem(store) -> str:
    """Why the autopilot stopped, if it did recently (the latest STOPPED line in the journal)."""
    for ts, message in reversed(store.journal(200)):
        if message.startswith("STOPPED:") or "stuck for" in message:
            return f"{ts.replace('T', ' ')}: {message}"
        if message.startswith("Autopilot started"):
            return ""
    return ""


def setup_status(cfg, store) -> dict:
    from . import mac_service
    service = mac_service.status()
    from .alpaca_api import has_keys
    from .config import active_desks, data_source, uses_broker_paper
    from .phases import current_phase, study_progress
    progress = study_progress(store, cfg)
    desks = []
    from .planner import STAGE1_DESK
    stage1 = {"desk": STAGE1_DESK, "can_start": False, "running_since": None, "trading_days": 0,
              "days_needed": cfg["promotion"]["min_trading_days"]}
    for desk in active_desks(cfg):
        phase = current_phase(store, desk).value
        text = NEXT_STEP[phase]
        if desk == STAGE1_DESK:
            stage1["can_start"] = phase in ("STUDY", "PLAN_REVIEW")
            if phase == "PAPER" and store.get("stage") == 1:
                stage1["running_since"] = store.get(f"{desk}_paper_started_on")
                stage1["trading_days"] = len(store.equity_curve(f"paper-{desk}"))
                text = NEXT_STEP["STAGE1"] + f" {stage1['trading_days']} of {stage1['days_needed']} trading days done."
        if phase == "STUDY":
            text += (f" So far: {progress['study_days']} trading days studied"
                     + ("; the study is complete: write the plans from the full Setup menu." if progress["ready"]
                        else f"; still needed: {', '.join(progress['missing'])}."))
        desks.append({"desk": desk, "phase": phase, "halted": bool(store.get(f"halted:{desk}")),
                      "exiting": bool(store.get(f"exiting:{desk}")), "next": text})
    from . import user_settings
    from .schwab_api import token_days_left
    secrets = cfg["secrets"]
    return {"paper_keys": has_keys(cfg, True), "live_keys": has_keys(cfg, False),
            "live_enabled": bool(cfg.get("live_trading_enabled")), "settings": user_settings.current(cfg),
            "schwab": {"keys": bool(secrets["app_key"] and secrets["app_secret"]),
                       "days_left": token_days_left(cfg), "callback_url": secrets["callback_url"],
                       "account_number": bool(secrets["account_number"])},
            "gfv": gfv_status(cfg, store),
            "prices_from": data_source(cfg), "paper_at": "Alpaca paper account" if uses_broker_paper(cfg)
            else "simulated on this Mac", "autopilot_on": service["on"], "autopilot_alive": service["running"],
            "autopilot_problem": autopilot_problem(store),
            "autopilot_seen": store.get("autopilot_heartbeat"), "can_autopilot": sys.platform == "darwin",
            "desks": desks, "stage1": stage1, "phone": phone_status(cfg)}


def phone_status(cfg) -> dict:
    from . import phone, phone_screen
    from .scanner import is_on
    has_token = bool(phone.token(cfg))
    screen_on = is_on((cfg.get("phone") or {}).get("screen", False))
    ip = phone_screen.tailscale_ip()
    return {"token": has_token, "paired": phone.connected(cfg),
            "code": phone.pairing_code(cfg) if has_token and not phone.connected(cfg) else None,
            "screen": {"on": screen_on, "tailscale": bool(ip),
                       "link": phone_screen.link(cfg) if screen_on and ip else None}}


def phone_screen_send(cfg) -> dict:
    """Sends the phone-screen link to your phone through Telegram (so you don't have to type it)."""
    from . import phone, phone_screen
    url = phone_screen.link(cfg)
    if not url:
        return {"ok": False, "text": "Tailscale isn't on for this Mac. Open the Tailscale app and log in."}
    if not phone.connected(cfg):
        return {"ok": False, "text": f"Pair Telegram first (step 5), or type this on your phone: {url}"}
    ok = phone.send(cfg, f"Your Kestrel screen (open it, then Share -> Add to Home Screen):\n{url}")
    return {"ok": ok, "text": "Sent to Telegram. Open it on your phone." if ok else "Couldn't reach Telegram."}


def handle(action: str, cfg: dict, demo: bool = False, confirm: str = None, payload: dict = None) -> dict:
    from . import dashboard
    from .config import data_path
    from .demo import build, demo_config
    if action == "demo-build":
        build(cfg)
        return {"message": "Demo data is ready."}
    if action == "save-keys":
        return save_keys(payload or {})
    if action == "check-keys":
        return check_keys(cfg)
    if action == "save-settings":
        from . import user_settings
        saved = user_settings.save(payload or {})
        restart_autopilot()
        return {"message": "Settings saved (they stay when the app updates).", "settings": saved}
    if action == "save-live-keys":
        return save_live_keys(payload or {})
    if action == "save-schwab-keys":
        return save_schwab_keys(payload or {})
    if action == "schwab-login-start":
        from .schwab_api import login_start
        return {"url": login_start(cfg)}
    if action == "schwab-login-finish":
        from .schwab_api import login_finish
        left = login_finish(cfg, str((payload or {}).get("url", "")))
        restart_autopilot()
        return {"message": f"Logged in to Schwab. The login lasts {left:.0f} days; log in again before then."}
    if action == "check-schwab":
        return check_schwab(cfg)
    if action == "connect-claude":
        return connect_claude(str((payload or {}).get("which", "")))
    if action == "save-phone":
        return save_phone(cfg, payload or {})
    if action == "phone-test":
        return phone_test(cfg)
    if action == "phone-screen-send":
        return phone_screen_send(cfg)
    if action in ("autopilot-on", "autopilot-off"):
        from . import mac_service
        from .config import ROOT
        if sys.platform != "darwin":
            raise RuntimeError("The background autopilot is for Macs.")
        if action == "autopilot-on":
            mac_service.install(ROOT)
            return {"message": "Autopilot is ON: it runs in the background, starts when you log in and "
                               "restarts itself. Keep the Mac plugged in and awake during market hours."}
        mac_service.uninstall()
        return {"message": "Autopilot is OFF. Nothing new happens until you turn it back on."}
    if demo:
        cfg = demo_config(cfg)
        if not data_path(cfg, "aitrader.sqlite").exists():
            raise RuntimeError("The demo data isn't built yet.")
    store = Store(data_path(cfg, "aitrader.sqlite"))
    try:
        if action == "snapshot":
            return dashboard.snapshot(cfg, store)
        if action == "update-policy":
            return real_money_status(cfg, store)
        if action == "setup-status":
            return setup_status(cfg, store)
        if action == "resume":
            import run                                  # run.py, next to the aitrader folder
            run.cmd_resume(cfg, store, SimpleNamespace(desk=None))
            still = [d for d in cfg["desks"] if store.get(f"halted:{d}")]
            return {"message": "Resumed: the desks can trade again." if not still else
                    f"Still halted: {', '.join(still)} (an emergency exit is still selling; it retries every 5 minutes)."}
        if action == "pause":
            return {"message": pause_all(cfg, store, "you, from the app")}
        if action == "start-stage1":
            import run                                  # run.py, next to the aitrader folder
            return {"message": run.start_stage1(cfg, store)}
        if action == "kill":
            if confirm != KILL_PHRASE:
                raise ValueError(f'Type "{KILL_PHRASE}" to confirm.')
            import run                                  # run.py, next to the aitrader folder
            run.cmd_kill(cfg, store, None)
            return {"message": "Emergency stop: the bot sold (or is selling) everything it owns, and both desks "
                               "are halted. Check the Activity and Journal tabs."}
        raise ValueError(f"unknown action {action!r}")
    finally:
        store.db.close()


def plain_json(value):
    """The page reads strict JSON: a missing number (NaN) or infinity becomes null instead of breaking it."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: plain_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_json(v) for v in value]
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aitrader.app_api")
    parser.add_argument("action", choices=[
        "snapshot", "pause", "kill", "demo-build", "update-policy", "setup-status", "save-keys", "check-keys",
        "autopilot-on", "autopilot-off", "resume", "save-settings", "save-live-keys", "save-schwab-keys",
        "schwab-login-start", "schwab-login-finish", "check-schwab", "connect-claude", "start-stage1",
        "save-phone", "phone-test", "phone-screen-send"])
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    out = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):    # the bot's own messages must not mix into the JSON
            payload = json.loads(sys.stdin.read() or "{}") if args.action in STDIN_ACTIONS else None
            result = handle(args.action, load_config(), args.demo, args.confirm, payload)
    except Exception as e:
        result = {"error": str(e) or type(e).__name__}
    out.write(json.dumps(plain_json(result), default=str, allow_nan=False))
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
