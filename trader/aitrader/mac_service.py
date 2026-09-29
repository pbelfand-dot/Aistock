"""
mac_service.py: keep the autopilot running in the background on a Mac.

Uses launchd, the Mac's built-in service manager:
  * starts the autopilot when you log in
  * restarts it if it ever crashes
  * runs it under `caffeinate -i`, so the Mac doesn't idle-sleep while it works
    (closing the LID still sleeps a MacBook; see the README)
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
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", sys.executable, "-u", str(root / "run.py"), "autopilot"],
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


def is_running() -> bool:
    if sys.platform != "darwin":
        return False
    return subprocess.run(["launchctl", "print", f"{_domain()}/{LABEL}"], capture_output=True).returncode == 0
