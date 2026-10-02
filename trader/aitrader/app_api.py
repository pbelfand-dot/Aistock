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
  save-webull-keys < {"app_key", ...}        Webull App Key/Secret and (optional) account ID
  check-webull < {"poll": bool}              tests Webull (read-only); asks for the in-app approval if needed
  connect-claude < {"which": "code"|"desktop"}  lets Claude see the bot (and Schwab, read-only)
  start-stage1                               Stage 1: the swing desk paper trades momentum now (pretend money)
  start-stage2                               Stage 2: the day desk paper trades TJR's model (after its history test)
  tjr-test                                   runs TJR's history test now (a minute or two)
  save-phone < {"token": ..}                 your phone: a private Telegram bot for alerts and commands (phone.py)
  phone-test                                 sends your phone a test message
  save-pushover < {"user", "token"}          push alerts through Pushover (pushover.py): checks the keys, sends a test
  pushover-test                              sends a test push notification
  stock-info < {"ticker": ..}                what a stock is (the company) and what Kestrel knows about it
  phone-screen-send                          sends your phone the link to the Kestrel screen (Tailscale)
  lid-mode-on / lid-mode-off                 keep trading with the lid closed while plugged in (asks for the
                                             Mac password once; see lid_mode.py)

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
STDIN_ACTIONS = {"use-challenger", "save-healthcheck", "save-keys", "save-settings", "save-live-keys", "save-schwab-keys", "schwab-login-finish",
                 "connect-claude", "save-phone", "save-webull-keys", "save-pushover", "stock-info",
                 "check-webull", "save-data-sources"}               # these read their details from stdin (never argv)

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
WEBULL_KEYS = ("WEBULL_APP_KEY", "WEBULL_APP_SECRET", "WEBULL_ACCOUNT_ID", "WEBULL_ENVIRONMENT")


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


def save_webull_keys(cfg, payload: dict) -> dict:
    """Saves the Webull keys. Webull only lets Kestrel use the account once you approve it in the
    Webull app (Test Webull asks for that). Trading there is a separate choice: Settings -> Paper trading
    happens at: Webull (paper keys), or Broker for real money: Webull (real-money keys and the usual locks)."""
    from . import webull_api
    app_key = _key(payload.get("app_key"), "Webull App Key", r"[A-Za-z0-9_+/=.-]{8,256}")
    secret = _key(payload.get("app_secret"), "Webull App Secret", r"[A-Za-z0-9_+/=.-]{8,256}")
    account = str(payload.get("account_id") or "").strip()
    if account and not re.fullmatch(r"[A-Za-z0-9-]{4,40}", account):
        raise ValueError("The account ID is letters and numbers (leave it empty if you have one Webull account).")
    env = str(payload.get("environment") or "paper").strip().lower()
    if env not in webull_api.HOSTS:
        raise ValueError("Pick Paper or Real money for the Webull keys.")
    if app_key != cfg["secrets"].get("webull_app_key"):
        webull_api.forget_token(cfg)                     # an approval belongs to the old key
    values = (app_key, secret, account, env)
    write_env(env_file(), dict(zip(WEBULL_KEYS, values)))
    for name, value in zip(("webull_app_key", "webull_app_secret", "webull_account_id", "webull_env"), values):
        cfg["secrets"][name] = value
    restart_autopilot()
    return {"message": "Webull keys saved on this Mac only. Next: Test Webull, then approve Kestrel in the Webull app."}


def check_webull(cfg, payload: dict) -> dict:
    """Read-only. poll=True (the Setup screen waiting for your approval) never asks for a new approval."""
    from . import webull_api
    if (payload or {}).get("poll"):
        if not webull_api.has_keys(cfg):
            return {"ok": False, "waiting": False, "text": "Webull: no keys yet."}
        try:
            status = webull_api.token_state(cfg, create=False).get("status")
        except webull_api.WebullError as e:
            return {"ok": False, "waiting": True, "text": f"Webull: {e}"}          # keep waiting: maybe offline
        if status == "PENDING":
            return {"ok": False, "waiting": True, "text": "Webull: waiting for your approval. " + webull_api.APPROVE}
        if status != "NORMAL":
            return {"ok": False, "waiting": False, "text": "Webull: the approval timed out (Webull allows 5 minutes). "
                                                           "Press Test Webull to get a new one."}
    result = webull_api.connect(cfg)
    if result.get("switched_to"):
        restart_autopilot()                              # so the autopilot uses the right Webull server too
    return result


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


def save_pushover(cfg, payload: dict) -> dict:
    """Saves the Pushover User Key and API Token (after Pushover accepts them) and sends a test alert."""
    from . import pushover
    user, token = str(payload.get("user", "")).strip(), str(payload.get("token", "")).strip()
    for name, value in (("User Key", user), ("API Token", token)):
        if not re.fullmatch(pushover.KEY_PATTERN, value):
            raise ValueError(f"That {name} doesn't look right: it's 30 letters and digits. Copy it again from "
                             "pushover.net (User Key: your dashboard; API Token: your Kestrel application).")
    if user == token:
        raise ValueError("The User Key and the API Token are the same: the API Token comes from the application "
                         "you create at pushover.net/apps/build.")
    cfg["secrets"].update(pushover_user=user, pushover_token=token)
    try:
        devices = pushover.validate(cfg).get("devices") or []
    except Exception as e:
        cfg["secrets"].update(pushover_user="", pushover_token="")
        raise ValueError(f"Pushover didn't accept them ({e}). Check that the User Key is yours and the API "
                         "Token is from the application you made.") from None
    write_env(env_file(), {"PUSHOVER_USER_KEY": user, "PUSHOVER_APP_TOKEN": token})
    sent = pushover.send(cfg, "Kestrel is connected: trades, results and anything urgent will show up here.",
                         priority=0)
    restart_autopilot()
    where = f" on {', '.join(devices)}" if devices else ""
    return {"message": "Saved on this Mac only. " + (f"A test alert is on its way{where}." if sent else
            "Pushover accepted the keys, but the test alert didn't go out; press Send a test."),
            "devices": devices}


def pushover_test(cfg) -> dict:
    from . import pushover
    if not pushover.has_keys(cfg):
        return {"ok": False, "text": "Paste your Pushover User Key and API Token first."}
    ok = pushover.send(cfg, "Kestrel test alert: Pushover works.", priority=0)
    return {"ok": ok, "text": "Sent. Check your phone." if ok else "Couldn't reach Pushover. Is the Mac online?"}


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
    from .config import active_desks, data_source, paper_broker
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
    from . import llm, user_settings
    from .schwab_api import token_days_left
    secrets = cfg["secrets"]
    return {"paper_keys": has_keys(cfg, True), "live_keys": has_keys(cfg, False),
            "live_enabled": bool(cfg.get("live_trading_enabled")), "settings": user_settings.current(cfg),
            "schwab": {"keys": bool(secrets["app_key"] and secrets["app_secret"]),
                       "days_left": token_days_left(cfg), "callback_url": secrets["callback_url"],
                       "account_number": bool(secrets["account_number"])},
            "webull": webull_status(cfg),
            "gfv": gfv_status(cfg, store),
            "prices_from": data_source(cfg),
            "paper_at": {"alpaca": "Alpaca paper account", "webull": "Webull paper account",
                         "local": "simulated on this Mac"}[paper_broker(cfg)], "autopilot_on": service["on"], "autopilot_alive": service["running"],
            "autopilot_problem": autopilot_problem(store),
            "autopilot_seen": store.get("autopilot_heartbeat"), "can_autopilot": sys.platform == "darwin",
            "desks": desks, "stage1": stage1, "stage2": stage2_status(store), "phone": phone_status(cfg),
            "lid": lid_status(), "local_ai": llm.status(cfg), "data_sources": data_sources_status(cfg),
            "uptime": uptime_status(cfg, store)}


def uptime_status(cfg, store) -> dict:
    from . import uptime
    return uptime.status(cfg, store)


def save_healthcheck(cfg, payload: dict) -> dict:
    """Setup → Your phone: the dead-man's switch. The address is tried (one ping) before it's saved."""
    from . import uptime
    address = str(payload.get("url", "")).strip().rstrip("/")
    if not uptime.valid(address):
        raise ValueError("That doesn't look like a ping address. On healthchecks.io open your check and copy the "
                         "address under \"Ping URL\" (it starts with https://hc-ping.com/).")
    cfg["secrets"]["healthcheck_url"] = address
    problem = uptime.send(cfg)
    if problem:
        raise ValueError(f"The ping didn't go through: {problem}. Check the address and try again.")
    write_env(env_file(), {"HEALTHCHECK_URL": address})
    restart_autopilot()
    return {"message": "Saved on this Mac only, and the first ping went through: your check on healthchecks.io "
                       "should say \"up\". From now on Kestrel pings it every 5 minutes."}


def data_sources_status(cfg) -> dict:
    from datetime import datetime
    from . import macro, sec_filings
    return {"fred": macro.status(cfg, datetime.now()), "sec": sec_filings.status(cfg)}


def save_data_sources(cfg, payload: dict) -> dict:
    """Setup → AI & news: the free FRED key (economic news dates) and the contact email the SEC asks for.
    Each is tried before it's saved; only what you fill in changes."""
    from datetime import datetime
    from . import macro, sec_filings
    key = str(payload.get("fred_key", "")).strip().lower()
    email = str(payload.get("sec_email", "")).strip()
    if not key and not email:
        raise ValueError("Fill in the FRED key, your email for the SEC, or both.")
    saved, said = {}, []
    if key:
        if not re.fullmatch(macro.KEY_PATTERN, key):
            raise ValueError("That FRED key doesn't look right: it's 32 lower-case letters and digits. Copy it again "
                             "from fredaccount.stlouisfed.org → API Keys.")
        cfg["secrets"]["fred_key"] = key
        try:
            macro.release_name(cfg, 10)
        except Exception as e:
            raise ValueError(f"FRED didn't accept that key ({e}).") from None
        saved["FRED_API_KEY"] = key
    if email:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
            raise ValueError("That email doesn't look right.")
        cfg["secrets"]["sec_email"] = email
        try:
            sec_filings._fetch(cfg, sec_filings.SUBMISSIONS_URL.format(cik=320193))
        except Exception as e:
            raise ValueError(f"The SEC didn't answer ({e}). Try again in a minute.") from None
        saved["SEC_CONTACT_EMAIL"] = email
    write_env(env_file(), saved)
    if key:
        cal = macro.refresh(cfg, datetime.now().strftime("%Y-%m-%d"), force=True)
        nxt = macro.upcoming(cfg, datetime.now())
        said.append("FRED connected" + (f": next up, {nxt[0]['name']} {nxt[0]['label']} ({nxt[0]['countdown']})"
                                         if nxt else "") + (f" (note: {cal['error']})" if cal.get("error") else ""))
    if email:
        said.append("SEC filings on: the first check runs within 30 minutes on a trading day")
    restart_autopilot()
    return {"message": "Saved on this Mac only. " + "; ".join(said) + "."}


def llm_download(cfg) -> dict:
    """Setup → AI & news: download the local AI's model now (normally it starts by itself the first time it's needed)."""
    from . import llm
    if not cfg["llm"].get("enabled"):
        raise RuntimeError("The local AI is turned off in config.yaml (llm.enabled).")
    names = llm.downloaded(cfg)
    if names is None:
        raise RuntimeError("Ollama isn't running. Install it (free) from ollama.com/download, open it once, "
                           "then try again.")
    model = llm.wanted_model(cfg)
    if llm.has(names, model):
        return {"message": f"The local AI ({model}) is already downloaded and ready."}
    llm.start_download(cfg, model, force=True)
    return {"message": f"Downloading {model} in the background. It can take a while; Setup shows how far it got, "
                       f"and the write-ups use it as soon as it's done."}


def check_paper_move(cfg, choice: str):
    """Moving paper trading to another broker while paper positions are open would lose track of them."""
    from .config import data_path, paper_broker
    trial = {**cfg, "paper": {**cfg["paper"], "broker": choice}}
    if paper_broker(trial) == paper_broker(cfg):
        return
    store = Store(data_path(cfg, "aitrader.sqlite"))
    try:
        busy = [d for d in cfg["desks"] if ((store.get(f"paper-{d}_ledger") or {}).get("positions")
                                            or (store.get(f"paper-{d}_ledger") or {}).get("pending"))]
    finally:
        store.db.close()
    if busy:
        raise ValueError(f"The {' and '.join(busy)} desk still holds paper positions where it trades now. Wait until "
                         "they're sold (the day desk sells before each close), then switch.")


def tjr_status(store) -> dict:
    """TJR's latest history test, small enough for the app."""
    t = store.get("tjr_history_test") or {}
    if not t:
        return {}
    pick = lambda r: {k: r.get(k) for k in ("num_closed_trades", "win_rate_pct", "profit_factor",
                                            "total_return_pct", "max_drawdown_pct")}
    return {"ran_on": t.get("ran_on"), "passed": t.get("passed"), "why_not": t.get("why_not"), "days": t.get("days"),
            "tickers": len(t.get("tickers") or []), "tjr": pick(t.get("tjr") or {}), "placebo": pick(t.get("placebo") or {})}


def stage2_status(store) -> dict:
    from .phases import current_phase
    from .planner import STAGE2_DESK
    phase = current_phase(store, STAGE2_DESK).value
    test = tjr_status(store)
    running = phase == "PAPER" and bool(store.get("stage2"))
    return {"desk": STAGE2_DESK, "test": test, "running_since": store.get(f"{STAGE2_DESK}_paper_started_on") if running else None,
            "can_start": phase in ("STUDY", "PLAN_REVIEW") and bool(test.get("passed")),
            "trading_days": len(store.equity_curve(f"paper-{STAGE2_DESK}")) if running else 0}


def lid_status() -> dict:
    from . import lid_mode
    try:
        return lid_mode.status()
    except Exception:
        return {"can": False, "on": False}


def webull_status(cfg) -> dict:
    from . import webull_api
    from .config import paper_broker
    env = webull_api.environment(cfg)
    return {"keys": webull_api.has_keys(cfg), "account_id": bool(cfg["secrets"].get("webull_account_id")),
            "environment": env, "approval": webull_api.load_token(cfg).get("status"),
            "trading": paper_broker(cfg) == "webull" if env == "paper" else cfg["broker"] == "webull"}


def phone_status(cfg) -> dict:
    from . import phone, phone_screen
    from .scanner import is_on
    has_token = bool(phone.token(cfg))
    screen_on = is_on((cfg.get("phone") or {}).get("screen", False))
    ip = phone_screen.tailscale_ip()
    from . import pushover
    return {"token": has_token, "paired": phone.connected(cfg),
            "pushover": {"keys": pushover.has_keys(cfg), "sent": pushover.sent_this_month(cfg),
                         "limit": pushover.MONTHLY_LIMIT},
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
        payload = payload or {}
        if "paper_broker" in payload:
            check_paper_move(cfg, str(payload["paper_broker"]).strip().lower())
        saved = user_settings.save(payload)
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
    if action == "save-webull-keys":
        return save_webull_keys(cfg, payload or {})
    if action == "check-webull":
        return check_webull(cfg, payload or {})
    if action == "connect-claude":
        return connect_claude(str((payload or {}).get("which", "")))
    if action == "save-phone":
        return save_phone(cfg, payload or {})
    if action == "phone-test":
        return phone_test(cfg)
    if action == "save-pushover":
        return save_pushover(cfg, payload or {})
    if action == "pushover-test":
        return pushover_test(cfg)
    if action == "phone-screen-send":
        return phone_screen_send(cfg)
    if action == "llm-download":
        return llm_download(cfg)
    if action == "save-data-sources":
        return save_data_sources(cfg, payload or {})
    if action == "save-healthcheck":
        return save_healthcheck(cfg, payload or {})
    if action in ("lid-mode-on", "lid-mode-off"):
        from . import lid_mode
        return lid_mode.turn_on() if action == "lid-mode-on" else lid_mode.turn_off()
    if action in ("autopilot-on", "autopilot-off"):
        from . import mac_service
        from .config import ROOT
        if sys.platform != "darwin":
            raise RuntimeError("The background autopilot is for Macs.")
        if action == "autopilot-on":
            mac_service.install(ROOT)
            return {"message": "Autopilot is ON: it runs in the background, starts when you log in and "
                               "restarts itself. Keep the Mac plugged in; to close the lid, turn on lid-closed mode "
                               "just below."}
        mac_service.uninstall()
        from . import lid_mode
        lid_mode.release_if_on()                         # nothing manages the lid-closed lock without it
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
        if action == "stock-info":
            from .stock_info import info
            return info(cfg, store, (payload or {}).get("ticker"))
        if action == "setup-status":
            return setup_status(cfg, store)
        if action == "thinking":
            return dashboard.thinking(cfg, store)
        if action == "use-challenger":                  # you pressed Use it (a proven challenger, real-money desk)
            from . import challengers
            p = payload or {}
            return {"message": challengers.use(store, str(p.get("desk")), str(p.get("name")))}
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
        if action == "start-stage2":
            import run
            return {"message": run.start_stage2(cfg, store)}
        if action == "tjr-test":
            import run
            from datetime import date
            from .market_data import MarketData
            run.run_tjr_test(cfg, store, MarketData(cfg), date.today().isoformat(), force=True)
            return {"message": "TJR's history test is done: see Setup → Start here (What happens next) and the Research tab.",
                    "test": tjr_status(store)}
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
        "save-phone", "phone-test", "phone-screen-send", "save-webull-keys", "check-webull", "lid-mode-on",
        "lid-mode-off", "start-stage2", "tjr-test", "save-pushover", "pushover-test", "stock-info", "llm-download", "thinking", "save-data-sources",
        "use-challenger", "save-healthcheck"])
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
