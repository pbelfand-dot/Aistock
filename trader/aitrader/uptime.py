"""
uptime.py: a dead-man's switch. A Mac that's asleep, unplugged, offline or frozen can't warn you about
itself, so something outside has to notice the silence: healthchecks.io (free for up to 20 checks).

Kestrel "pings" your check after every autopilot cycle (every 5 minutes). If the pings stop, healthchecks.io
alerts you through whatever you connect there (Pushover, Telegram, email, ...). If a trading job keeps
failing while the loop still runs (3 cycles in a row: about 15 minutes), Kestrel sends "fail" with the
reason, so that's an alert too; the next good cycle clears it.

Set the check to the Cron schedule `*/5 9-15 * * 1-5` in the America/New_York time zone with a grace time of
15 minutes, so it only expects Kestrel while the market is open (the Mac may sleep at night).

The ping address is a secret of sorts (anyone with it could ping your check): it's kept in ~/AITrader/.env
like the keys. Pings never slow trading: they go out in the background with a short timeout.
"""
import re
import threading
from datetime import datetime

import requests

URL_PATTERN = r"https://[A-Za-z0-9.-]+(:\d+)?/[A-Za-z0-9/_-]{8,200}"
FAILS_BEFORE_ALERT = 3
TRADING_JOBS = ("day", "swing", "swing-stops")
_post = requests.post            # tests don't go online
_result = {}                     # the last ping's result (from its background thread), saved next cycle


def url(cfg) -> str:
    return ((cfg.get("secrets") or {}).get("healthcheck_url") or "").strip().rstrip("/")


def is_on(cfg) -> bool:
    return bool(url(cfg))


def valid(address: str) -> bool:
    return bool(re.fullmatch(URL_PATTERN, address.strip().rstrip("/")))


def send(cfg, fail: str = None, timeout: float = 10) -> str:
    """One ping (or "fail" with the reason). Returns "" when it went through, else what went wrong."""
    try:
        r = _post(url(cfg) + ("/fail" if fail else ""), data=(fail or "ok")[:10000].encode(), timeout=timeout)
        return "" if r.status_code == 200 else f"healthchecks.io said {r.status_code}"
    except Exception as e:
        return f"couldn't reach healthchecks.io ({type(e).__name__})"


def after_cycle(cfg, store, failed_jobs: dict, background: bool = True) -> str:
    """Called at the end of every autopilot cycle. failed_jobs: {job: error} from this cycle."""
    if not is_on(cfg):
        return ""
    if _result:                                         # the previous ping's result (sqlite stays on this thread)
        store.set("uptime_last", dict(_result))
    trading = {j: e for j, e in failed_jobs.items() if j in TRADING_JOBS}
    streak = (store.get("uptime_fail_streak") or 0) + 1 if trading else 0
    store.set("uptime_fail_streak", streak)
    reason = ("; ".join(f"{j} failed: {e}" for j, e in trading.items()) + f" ({streak} cycles in a row)"
              if streak >= FAILS_BEFORE_ALERT else None)
    at = datetime.now().isoformat(timespec="seconds")

    def work():
        problem = send(cfg, reason)
        _result.clear()
        _result.update(at=at, ok=not problem, problem=problem, fail=reason)
    if background:
        threading.Thread(target=work, daemon=True, name="uptime-ping").start()
    else:
        work()
        store.set("uptime_last", dict(_result))
    return reason or ""


def status(cfg, store) -> dict:
    last = store.get("uptime_last") or {}
    return {"on": is_on(cfg), "last": last}
