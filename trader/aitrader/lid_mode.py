"""
lid_mode.py: keep trading with the MacBook lid closed (Setup -> Autopilot -> "Keep trading with the lid closed").

A closed MacBook always sleeps unless macOS's sleep lock (`pmset disablesleep`) is on, and only an
administrator can switch that lock. Turning this on asks for your Mac password ONCE, to:
  - allow exactly these commands without a password (a rule in /etc/sudoers.d/kestrel-lid, checked
    with visudo before it's put in place):
        pmset -a disablesleep 1      pmset -a disablesleep 0      pmset repeat cancel
  - wake the Mac at 8:30am New York time on weekdays, as a backup in case it fell asleep.

Then the autopilot checks every few seconds:
  - plugged in  -> the sleep lock is ON: the Mac stays awake with the lid closed (like a desktop).
  - on battery  -> the lock is OFF, and if the lid is closed the Mac goes to sleep right away,
                   so it never runs hot in a bag.
Turning it off in Setup releases the lock and cancels the morning wake. While it's on and plugged in,
Apple menu -> Sleep does nothing (that's the lock); turn it off first to sleep the Mac by hand.
"""
import os
import pwd
import re
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

PMSET = "/usr/bin/pmset"
RULE_PATH = "/etc/sudoers.d/kestrel-lid"
MORNING_WAKE_NY = (8, 30)                              # before the 9:30 open (the morning job runs at 9:25)
CHECK_EVERY = 10                                       # seconds


def _is_mac() -> bool:
    return sys.platform == "darwin"


def _run(args, timeout: float = 15):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def is_on() -> bool:
    from . import user_settings
    return user_settings.load().get("lid_closed") == "on"


def plugged_in() -> bool:
    """True on the charger (or a desktop Mac). Unknown counts as battery: then the Mac may sleep."""
    out = _run([PMSET, "-g", "batt"])
    first = out.stdout.splitlines()[0] if out and out.returncode == 0 and out.stdout.strip() else ""
    return "AC Power" in first


def lid_closed() -> bool:
    out = _run(["/usr/sbin/ioreg", "-r", "-k", "AppleClamshellState", "-d", "1"])
    return bool(out and re.search(r'"AppleClamshellState"\s*=\s*Yes', out.stdout))


def sleep_locked() -> bool:
    out = _run([PMSET, "-g"])
    return bool(out and re.search(r"^\s*SleepDisabled\s+1\b", out.stdout, re.M))


def allowed() -> bool:
    """The one-time password step was done (the no-password rule for the sleep lock is in place)."""
    out = _run(["/usr/bin/sudo", "-n", "-l", PMSET, "-a", "disablesleep", "1"])
    return bool(out and out.returncode == 0)


def set_lock(on: bool) -> bool:
    out = _run(["/usr/bin/sudo", "-n", PMSET, "-a", "disablesleep", "1" if on else "0"])
    return bool(out and out.returncode == 0)


# ---------------------------------------------------------------- the one-time password step
def user_name() -> str:
    name = pwd.getpwuid(os.getuid()).pw_name
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]*", name):
        raise RuntimeError(f"Your Mac user name ({name!r}) has characters Kestrel won't put in a system rule.")
    return name


def rule(user: str) -> str:
    return (f"{user} ALL=(root) NOPASSWD: {PMSET} -a disablesleep 1, {PMSET} -a disablesleep 0, "
            f"{PMSET} repeat cancel")


def morning_wake_local(now: datetime = None) -> str:
    """8:30am New York time, in this Mac's own time zone (pmset uses local time)."""
    ny = ZoneInfo("America/New_York")
    day = (now or datetime.now(ny)).astimezone(ny)
    wake = day.replace(hour=MORNING_WAKE_NY[0], minute=MORNING_WAKE_NY[1], second=0, microsecond=0)
    return wake.astimezone().strftime("%H:%M:%S")


def admin_script(user: str, wake: str) -> str:
    """What runs once as administrator (after macOS asks for your password)."""
    return "; ".join([
        "set -e",
        "f=$(/usr/bin/mktemp /tmp/kestrel-lid.XXXXXX)",
        "trap '/bin/rm -f \"$f\"' EXIT",
        f"/bin/echo '{rule(user)}' > \"$f\"",
        "/usr/sbin/visudo -cf \"$f\" >/dev/null",       # a broken rule never gets installed
        "/bin/mkdir -p /etc/sudoers.d",
        f"/usr/bin/install -m 0440 -o root -g wheel \"$f\" {RULE_PATH}",
        f"{PMSET} repeat wakeorpoweron MTWRF {wake}",
    ])


def _applescript(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def turn_on() -> dict:
    from . import user_settings
    if not _is_mac():
        raise RuntimeError("Lid-closed mode is for Macs.")
    script = admin_script(user_name(), morning_wake_local())
    prompt = "Kestrel needs your Mac password once to keep trading with the lid closed (only while plugged in)."
    out = _run(["/usr/bin/osascript", "-e",
                f"do shell script {_applescript(script)} with prompt {_applescript(prompt)} "
                f"with administrator privileges"], timeout=300)
    if not out or out.returncode != 0:
        why = (out.stderr.strip() if out else "") or "no answer"
        if "-128" in why or "canceled" in why.lower() or "cancelled" in why.lower():
            raise RuntimeError("Not turned on: the Mac password step was cancelled.")
        raise RuntimeError(f"Not turned on: macOS said {why}")
    if not allowed():
        raise RuntimeError("Not turned on: the permission didn't take. Try again, or tell Claude what happened.")
    user_settings.save({"lid_closed": "on"})
    on_ac = plugged_in()
    if on_ac:
        set_lock(True)
    return {"message": "Lid-closed mode is ON. While the Mac is plugged in it stays awake with the lid closed, "
                       "and the autopilot keeps trading. On battery it sleeps as usual. "
                       + ("It's plugged in now, so you can close the lid." if on_ac else
                          "It's on battery now: plug it in before you close the lid.")}


def turn_off() -> dict:
    from . import user_settings
    user_settings.save({"lid_closed": "off"})
    released = set_lock(False)
    _run(["/usr/bin/sudo", "-n", PMSET, "repeat", "cancel"])
    return {"message": "Lid-closed mode is OFF: closing the lid puts the Mac to sleep again, and Kestrel pauses "
                       "until you open it." + ("" if released or not sleep_locked() else
                                               " (macOS still shows the sleep lock on: run `sudo pmset -a "
                                               "disablesleep 0` in Terminal.)")}


def release_if_on():
    """The autopilot is being switched off: nothing will manage the lock, so let the Mac sleep."""
    if _is_mac() and is_on():
        set_lock(False)


def status() -> dict:
    if not _is_mac():
        return {"can": False, "on": False}
    return {"can": True, "on": is_on(), "allowed": allowed(), "plugged_in": plugged_in(),
            "awake": sleep_locked()}


# ---------------------------------------------------------------- the autopilot's side
def check(state: dict, log) -> dict:
    """One look: lock the Mac awake on the charger, release it (and sleep a closed Mac) on battery."""
    if not is_on():
        if state.pop("held", None) and sleep_locked():
            set_lock(False)                            # switched off some other way: don't leave it locked
        return state
    ac, locked = plugged_in(), sleep_locked()
    if ac:
        state["held"] = True
    if ac and not locked:
        if set_lock(True):
            log("Lid-closed mode: plugged in, so the Mac stays awake with the lid closed.")
            state.pop("warned", None)
        elif not state.get("warned"):
            log("!!! Lid-closed mode couldn't keep the Mac awake. Turn it off and on again in Setup "
                "→ Autopilot (it needs your Mac password once).")
            state["warned"] = True
    elif not ac and locked:
        set_lock(False)
        log("Lid-closed mode: on battery, so the Mac may sleep again (closed, it sleeps right away).")
    if not ac and lid_closed():
        if not state.get("slept"):
            log("Lid-closed mode: on battery with the lid closed: putting the Mac to sleep.")
        state["slept"] = True
        _run([PMSET, "sleepnow"])
    else:
        state.pop("slept", None)
    return state


def watch(store_factory, stop=None):
    """Runs as a thread in the autopilot."""
    state = {}
    while not (stop and stop.is_set()):
        try:
            store = store_factory()
            try:
                state = check(state, store.log)
            finally:
                store.db.close()
        except Exception:
            pass                                        # never let this stop the autopilot
        (stop.wait(CHECK_EVERY) if stop else time.sleep(CHECK_EVERY))
