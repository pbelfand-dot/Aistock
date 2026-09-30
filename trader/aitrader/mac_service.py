"""
mac_service.py: keep the autopilot running in the background on a Mac.

Uses launchd, the Mac's built-in service manager:
  * starts the autopilot when you log in
  * restarts it if it ever crashes
  * the autopilot holds a `caffeinate -i` while it runs, so the Mac doesn't idle-sleep while it
    works (closing the LID still sleeps a MacBook; see the README)
Its output goes to data/autopilot.log.
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.aitrader.autopilot"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install(root: Path):
    log = root / "data" / "autopilot.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps({
        "Label": LABEL,
        # python itself (not under caffeinate): when launchd restarts it, nothing is left running behind
        "ProgramArguments": [sys.executable, "-u", str(root / "run.py"), "autopilot"],
        "EnvironmentVariables": {"KESTREL_SERVICE": "1"},
        "WorkingDirectory": str(root),
        "RunAtLoad": True,           # start at login
        "KeepAlive": True,           # restart if it stops
        "ThrottleInterval": 60,      # ...but not more than once a minute
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }))
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST)], check=True)


def uninstall():
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)
    PLIST.unlink(missing_ok=True)


def status() -> dict:
    """on = the background autopilot is switched on (installed with launchd); running = it has a live process."""
    if sys.platform != "darwin":
        return {"on": False, "running": False}
    out = subprocess.run(["launchctl", "print", f"{_domain()}/{LABEL}"], capture_output=True, text=True)
    if out.returncode != 0:
        return {"on": False, "running": False}
    return {"on": True, "running": any(line.strip().startswith("pid = ") for line in out.stdout.splitlines())}


def is_running() -> bool:
    """Switched on (the Setup toggle). Whether a process is alive right now: status()["running"]."""
    return status()["on"]


def command_of(pid) -> str:
    """The command line of a process ("" if it's gone or can't be read)."""
    try:
        return subprocess.run(["ps", "-p", str(int(pid)), "-o", "command="], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def keep_awake():
    """While this process lives, the Mac doesn't idle-sleep (caffeinate ends by itself when we exit)."""
    if sys.platform == "darwin":
        subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
