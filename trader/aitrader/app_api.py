"""
app_api.py: how the AI Trader app (its window) talks to the bot.

The app runs `python -m aitrader.app_api <action>` from the AITrader folder and shows
the JSON this prints. No web server and no network: the app starts this helper
directly, like any Mac app runs a helper program.

  snapshot [--demo]                          everything the window shows
  pause [--demo]                             no new trades (stop-losses keep working)
  kill --confirm "SELL EVERYTHING" [--demo]  the emergency stop
  demo-build                                 fresh demo data (made-up prices, about a minute)
  update-policy                              is real money involved? (the app asks before updating if so)

--demo works on the demo folder (data/demo) instead of your real data.
"""
import argparse
import contextlib
import json
import sys

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


def handle(action: str, cfg: dict, demo: bool = False, confirm: str = None) -> dict:
    from . import dashboard
    from .config import data_path
    from .demo import build, demo_config
    if action == "demo-build":
        build(cfg)
        return {"message": "Demo data is ready."}
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
    parser.add_argument("action", choices=["snapshot", "pause", "kill", "demo-build", "update-policy"])
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    out = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):    # the bot's own messages must not mix into the JSON
            result = handle(args.action, load_config(), args.demo, args.confirm)
    except Exception as e:
        result = {"error": str(e) or type(e).__name__}
    out.write(json.dumps(result, default=str))
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
