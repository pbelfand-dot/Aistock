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

--demo works on the demo folder (data/demo) instead of your real data.
"""
import argparse
import contextlib
import json
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

NEXT_STEP = {
    "STUDY": "Studying: the bot watches the market and grades its strategies with no money involved. "
             "Keep the autopilot on.",
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
    """A running background autopilot read .env when it started: restart it so new keys take effect."""
    from . import mac_service
    if not mac_service.is_running():
        return False
    import subprocess
    subprocess.run(["launchctl", "kickstart", "-k", f"{mac_service._domain()}/{mac_service.LABEL}"],
                   capture_output=True)
    return True


def setup_status(cfg, store) -> dict:
    from . import mac_service
    from .alpaca_api import has_keys
    from .config import active_desks, data_source, uses_broker_paper
    from .phases import current_phase, study_progress
    progress = study_progress(store, cfg)
    desks = []
    for desk in active_desks(cfg):
        phase = current_phase(store, desk).value
        text = NEXT_STEP[phase]
        if phase == "STUDY":
            text += (f" So far: {progress['study_days']} trading days studied"
                     + ("; the study is complete: write the plans from the full Setup menu." if progress["ready"]
                        else f"; still needed: {', '.join(progress['missing'])}."))
        desks.append({"desk": desk, "phase": phase, "halted": bool(store.get(f"halted:{desk}")),
                      "exiting": bool(store.get(f"exiting:{desk}")), "next": text})
    return {"paper_keys": has_keys(cfg, True), "live_keys": has_keys(cfg, False),
            "prices_from": data_source(cfg), "paper_at": "Alpaca paper account" if uses_broker_paper(cfg)
            else "simulated on this Mac", "autopilot_on": mac_service.is_running(),
            "autopilot_seen": store.get("autopilot_heartbeat"), "can_autopilot": sys.platform == "darwin",
            "desks": desks}


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aitrader.app_api")
    parser.add_argument("action", choices=["snapshot", "pause", "kill", "demo-build", "update-policy", "setup-status",
                                           "save-keys", "check-keys", "autopilot-on", "autopilot-off", "resume"])
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    out = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):    # the bot's own messages must not mix into the JSON
            payload = json.loads(sys.stdin.read() or "{}") if args.action == "save-keys" else None
            result = handle(args.action, load_config(), args.demo, args.confirm, payload)
    except Exception as e:
        result = {"error": str(e) or type(e).__name__}
    out.write(json.dumps(result, default=str))
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
