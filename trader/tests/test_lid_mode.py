"""Lid-closed mode: awake with the lid closed on the charger, asleep on battery (never hot in a bag)."""
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from aitrader import app_api, lid_mode, mac_service, user_settings
from aitrader.storage import Store

PMSET = lid_mode.PMSET


class FakeMac:
    """pmset, ioreg, sudo and osascript as a Mac would answer them."""
    def __init__(self):
        self.ac, self.closed, self.locked, self.allowed = True, False, False, False
        self.wake, self.slept, self.cancel, self.scripts = None, 0, False, []

    def __call__(self, args, timeout=15):
        ok = lambda out="": SimpleNamespace(returncode=0, stdout=out, stderr="")
        no = lambda err="": SimpleNamespace(returncode=1, stdout="", stderr=err)
        if args == [PMSET, "-g", "batt"]:
            return ok(f"Now drawing from '{'AC Power' if self.ac else 'Battery Power'}'\n -InternalBattery-0 80%\n")
        if args == [PMSET, "-g"]:
            return ok(f"System-wide power settings:\n SleepDisabled\t\t{int(self.locked)}\nCurrently in use:\n sleep 1\n")
        if args[0] == "/usr/sbin/ioreg":
            return ok(f'| "AppleClamshellState" = {"Yes" if self.closed else "No"}\n')
        if args[:3] == ["/usr/bin/sudo", "-n", "-l"]:
            return ok() if self.allowed else no("a password is required")
        if args[:2] == ["/usr/bin/sudo", "-n"]:
            if not self.allowed:
                return no("a password is required")
            if args[2:5] == [PMSET, "-a", "disablesleep"]:
                self.locked = args[5] == "1"
            elif args[2:] == [PMSET, "repeat", "cancel"]:
                self.wake = None
            return ok()
        if args == [PMSET, "sleepnow"]:
            self.slept += 1
            return ok()
        if args[0] == "/usr/bin/osascript":
            self.scripts.append(args[2])
            if self.cancel:
                return no("execution error: User canceled. (-128)")
            self.allowed = True
            self.wake = re.search(r"wakeorpoweron MTWRF (\d\d:\d\d:\d\d)", args[2]).group(1)
            return ok()
        raise AssertionError(f"unexpected command {args}")


@pytest.fixture
def mac(tmp_path, monkeypatch):
    fake = FakeMac()
    monkeypatch.setattr(lid_mode, "_run", fake)
    monkeypatch.setattr(lid_mode, "_is_mac", lambda: True)
    monkeypatch.setattr(user_settings, "settings_file", lambda: tmp_path / "my_settings.json")
    return fake


def test_the_one_time_rule_allows_only_the_sleep_lock_and_is_checked_before_it_is_installed():
    rule = lid_mode.rule("pat")
    assert rule == (f"pat ALL=(root) NOPASSWD: {PMSET} -a disablesleep 1, {PMSET} -a disablesleep 0, "
                    f"{PMSET} repeat cancel")
    script = lid_mode.admin_script("pat", "08:30:00")
    assert script.index("visudo -cf") < script.index("/usr/bin/install -m 0440 -o root -g wheel")
    assert script.startswith("set -e") and f"{PMSET} repeat wakeorpoweron MTWRF 08:30:00" in script
    assert lid_mode._applescript('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'
    if shutil.which("visudo"):                                   # the real sudoers checker accepts the rule
        path = f"/tmp/kestrel-lid-test-{os.getpid()}"
        with open(path, "w") as f:
            f.write(rule + "\n")
        try:
            out = subprocess.run(["visudo", "-cf", path], capture_output=True, text=True)
            assert out.returncode == 0, out.stdout + out.stderr
        finally:
            os.unlink(path)


def test_an_odd_user_name_never_goes_into_a_system_rule(monkeypatch):
    monkeypatch.setattr(lid_mode.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="x'; rm -rf /"))
    with pytest.raises(RuntimeError, match="won't put in a system rule"):
        lid_mode.user_name()


def test_the_backup_morning_wake_is_830_new_york_time_in_the_macs_own_time_zone(monkeypatch):
    at = datetime(2026, 9, 30, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    for zone, expected in (("America/Los_Angeles", "05:30:00"), ("America/Chicago", "07:30:00"),
                           ("America/New_York", "08:30:00")):
        monkeypatch.setenv("TZ", zone)
        time.tzset()
        assert lid_mode.morning_wake_local(at) == expected
    monkeypatch.delenv("TZ")
    time.tzset()


def test_turning_it_on_asks_for_the_mac_password_once(mac):
    mac.cancel = True
    with pytest.raises(RuntimeError, match="cancelled"):
        lid_mode.turn_on()
    assert not lid_mode.is_on() and not mac.locked                 # nothing changed

    mac.cancel = False
    msg = lid_mode.turn_on()["message"]
    assert "Lid-closed mode is ON" in msg and "you can close the lid" in msg
    assert lid_mode.is_on() and mac.allowed and mac.locked and mac.wake
    assert "with administrator privileges" in mac.scripts[-1] and "with prompt" in mac.scripts[-1]
    assert lid_mode.status() == {"can": True, "on": True, "allowed": True, "plugged_in": True, "awake": True}

    off = lid_mode.turn_off()["message"]
    assert "OFF" in off and not mac.locked and mac.wake is None and not lid_mode.is_on()


def test_awake_on_the_charger_asleep_on_battery_never_hot_in_a_bag(mac):
    log, state = [], {}
    mac.allowed = True
    user_settings.save({"lid_closed": "on"})

    state = lid_mode.check(state, log.append)                       # plugged in: lock on
    assert mac.locked and "stays awake with the lid closed" in log[-1]
    mac.closed = True
    state = lid_mode.check(state, log.append)                       # closed on the charger: keeps going
    assert mac.locked and mac.slept == 0 and len(log) == 1

    mac.ac = False                                                  # unplugged and closed: into the bag
    state = lid_mode.check(state, log.append)
    assert not mac.locked and mac.slept == 1 and "putting the Mac to sleep" in log[-1]
    state = lid_mode.check(state, log.append)                       # woke up briefly in the bag: back to sleep
    assert mac.slept == 2 and sum("putting the Mac to sleep" in m for m in log) == 1

    mac.closed = False                                              # opened on battery: normal Mac
    state = lid_mode.check(state, log.append)
    assert not mac.locked and mac.slept == 2
    mac.ac = True                                                   # plugged back in
    state = lid_mode.check(state, log.append)
    assert mac.locked

    user_settings.save({"lid_closed": "off"})                       # switched off some other way
    state = lid_mode.check(state, log.append)
    assert not mac.locked


def test_it_says_so_if_the_permission_is_gone(mac):
    user_settings.save({"lid_closed": "on"})
    log, state = [], {}
    for _ in range(3):
        state = lid_mode.check(state, log.append)
    assert not mac.locked and len(log) == 1 and log[0].startswith("!!! Lid-closed mode couldn't keep the Mac awake")


def test_off_by_default_and_hands_off(mac):
    mac.allowed = True
    log = []
    lid_mode.check({}, log.append)
    assert not mac.locked and log == [] and mac.slept == 0


def test_turning_the_autopilot_off_lets_the_mac_sleep(mac, monkeypatch):
    mac.allowed = True
    lid_mode.turn_on()
    monkeypatch.setattr(mac_service, "uninstall", lambda: None)
    monkeypatch.setattr(app_api, "sys", SimpleNamespace(platform="darwin"))
    assert "Autopilot is OFF" in app_api.handle("autopilot-off", {})["message"]
    assert not mac.locked


def test_the_app_can_switch_it_and_setup_shows_it(mac, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(mac_service, "status", lambda: {"on": True, "running": True})
    assert "is ON" in app_api.handle("lid-mode-on", cfg)["message"]
    store = Store(tmp_path / "aitrader.sqlite")
    assert app_api.setup_status(cfg, store)["lid"]["on"] is True
    assert "is OFF" in app_api.handle("lid-mode-off", cfg)["message"]


def test_not_a_mac_nothing_happens(monkeypatch):
    monkeypatch.setattr(lid_mode, "_is_mac", lambda: False)
    assert lid_mode.status() == {"can": False, "on": False}
    with pytest.raises(RuntimeError, match="for Macs"):
        lid_mode.turn_on()


def test_the_watcher_never_stops_the_autopilot(mac):
    stop = threading.Event()
    calls = []

    def broken_store():
        calls.append(1)
        stop.set()
        raise OSError("disk full")
    lid_mode.watch(broken_store, stop)                               # returns instead of raising
    assert calls == [1]
