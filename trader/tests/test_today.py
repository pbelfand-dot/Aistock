"""The Today screen: your homework (quick add, AP work), whether the autopilot ran, the last report, and opening
Kestrel when you log in (docs/DASHBOARD-PLAN.md, step 1)."""
import plistlib
from datetime import date, datetime
from pathlib import Path

import pytest

import run
from aitrader import app_api, mac_service, phone_screen, school, today
from aitrader.config import data_path
from aitrader.storage import Store

TUE = date(2026, 10, 13)                     # a Tuesday
REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("words, due", [
    ("today", "2026-10-13"), ("tomorrow", "2026-10-14"), ("Friday", "2026-10-16"), ("fri", "2026-10-16"),
    ("due thursday", "2026-10-15"), ("tuesday", "2026-10-13"), ("next tuesday", "2026-10-20"),
    ("monday", "2026-10-19"), ("in 3 days", "2026-10-16"), ("Oct 17", "2026-10-17"), ("October 30", "2026-10-30"),
    ("10/17", "2026-10-17"), ("1/5", "2027-01-05"), ("2026-11-02", "2026-11-02"), ("pages 10-20", None), ("", None)])
def test_due_days_in_plain_words(words, due):
    got = school.parse_due(words, TUE)
    assert (got.isoformat() if got else None) == due


def test_quick_add_reads_the_due_day_after_the_last_comma_or_due():
    assert school.parse_quick("APUSH Unit 3 progress check, Friday", TUE) == ("APUSH Unit 3 progress check", date(2026, 10, 16))
    assert school.parse_quick("Essay draft due Oct 20", TUE) == ("Essay draft", date(2026, 10, 20))
    assert school.parse_quick("Read ch. 5, pages 10-20", TUE) == ("Read ch. 5, pages 10-20", None)   # not a day: kept whole
    assert school.parse_quick("  Lab   report ", TUE) == ("Lab report", None)


def test_ap_work_is_spotted_from_the_words():
    for text in ("APUSH Unit 3 progress check", "AP Bio lab", "Unit 2 Progress Check MCQ", "AP Lang essay", "apes reading"):
        assert school.is_ap(text), text
    for text in ("Map of Europe", "Chapter 4 review", "a happy essay"):
        assert not school.is_ap(text), text


def test_homework_is_grouped_by_when_its_due_and_ticked_off(cfg):
    a = school.add(cfg, "APUSH progress check, Friday", today=TUE)
    b = school.add(cfg, "Math worksheet", due="2026-10-13", today=TUE)
    c = school.add(cfg, "Lab report, yesterday", today=TUE)
    d = school.add(cfg, "Bio notes, tomorrow", course="Biology", today=TUE)
    e = school.add(cfg, "Read Gatsby", today=TUE)
    f = school.add(cfg, "History project", due="2026-11-02", today=TUE)
    assert a["ap"] and a["due"] == "2026-10-16" and not b["ap"]
    s = school.summary(cfg, TUE)
    g = {k: [r["title"] for r in rows] for k, rows in s["groups"].items()}
    assert g["overdue"] == ["Lab report"] and g["today"] == ["Math worksheet"] and g["tomorrow"] == ["Bio notes"]
    assert g["week"] == ["APUSH progress check"] and g["later"] == ["History project"] and g["no_date"] == ["Read Gatsby"]
    assert s["open"] == 6 and s["ap_open"] == 1
    assert s["groups"]["week"][0]["label"] == "Friday" and s["groups"]["overdue"][0]["label"] == "yesterday"
    assert s["links"]["ap_classroom"].startswith("https://myap.collegeboard.org")
    school.set_done(cfg, b["id"], today=TUE)
    s = school.summary(cfg, TUE)
    assert [r["title"] for r in s["groups"]["done"]] == ["Math worksheet"] and s["open"] == 5
    school.set_done(cfg, b["id"], done=False, today=TUE)                       # unticked: back on the list
    assert [r["title"] for r in school.summary(cfg, TUE)["groups"]["today"]] == ["Math worksheet"]
    school.remove(cfg, e["id"])
    assert school.summary(cfg, TUE)["open"] == 5
    school.set_done(cfg, c["id"], today=TUE)                                    # finished work drops off after 30 days
    school.save(cfg, school.load(cfg), date(2026, 11, 20))
    assert c["id"] not in [i["id"] for i in school.load(cfg)["items"]] and d["id"] in [i["id"] for i in school.load(cfg)["items"]]
    with pytest.raises(ValueError):
        school.add(cfg, "   ", today=TUE)
    with pytest.raises(ValueError):
        school.set_done(cfg, "h-gone")


def test_the_app_adds_and_ticks_homework_through_its_helper(cfg):
    added = app_api.handle("school-add", cfg, payload={"text": "AP Bio lab, tomorrow"})
    assert added["item"]["ap"] and added["message"] == "Added: AP Bio lab (due tomorrow)"
    done = app_api.handle("school-done", cfg, payload={"id": added["item"]["id"], "done": True})
    assert done["message"] == "Done: AP Bio lab"
    out = app_api.handle("today", cfg)
    assert out["school"]["groups"]["done"][0]["title"] == "AP Bio lab"
    assert set(out) >= {"date", "greeting", "school", "uptime", "news", "report", "open_at_login"}
    for action in ("today", "school-add", "school-done", "school-remove", "login-open-on", "login-open-off"):
        assert f'"{action}"' in (REPO / "mac/app/main.swift").read_text(), action          # the window may ask for it
    assert {"school-add", "school-done", "school-remove"} <= app_api.STDIN_ACTIONS
    assert {"today", "school-add", "school-done"} <= phone_screen.ALLOWED and "login-open-on" not in phone_screen.ALLOWED


def test_the_phone_can_add_homework(cfg, monkeypatch):
    import json
    monkeypatch.setattr(phone_screen, "access_key", lambda cfg, new=False: "k")
    monkeypatch.setattr("aitrader.config.load_config", lambda: cfg)
    code, text = phone_screen.answer(cfg, json.dumps({"action": "school-add",
                                                       "input": json.dumps({"text": "Essay, Friday"})}).encode(), "k")
    assert code == 200 and json.loads(text)["item"]["title"] == "Essay"


def test_opening_at_login_is_a_launch_agent_that_opens_the_app(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(mac_service, "LOGIN_PLIST", tmp_path / "com.aitrader.open-at-login.plist")
    monkeypatch.setattr(mac_service.subprocess, "run", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(mac_service.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(mac_service.sys, "platform", "darwin")
    assert mac_service.open_at_login() == {"can": True, "on": False}
    mac_service.open_at_login_on()
    plist = plistlib.loads(mac_service.LOGIN_PLIST.read_bytes())
    assert plist["ProgramArguments"] == ["/usr/bin/open", "-b", "com.aitrader.app"] and plist["RunAtLoad"]
    assert "KeepAlive" not in plist and plist["LimitLoadToSessionType"] == "Aqua"
    assert calls == [] and mac_service.open_at_login()["on"]                   # nothing started now: at the next login
    mac_service.open_at_login_off()
    assert not mac_service.LOGIN_PLIST.exists() and ["launchctl", "bootout", "gui/501/com.aitrader.open-at-login"] in calls
    monkeypatch.setattr(mac_service.sys, "platform", "linux")
    assert mac_service.open_at_login() == {"can": False, "on": False}


def test_today_says_whether_the_autopilot_ran_through_the_last_trading_day(cfg):
    store = Store(":memory:")
    run.note_gap(cfg, store, "2026-10-12T14:30:00", datetime(2026, 10, 12, 15, 48))      # Monday: the 3:45 decision
    run.note_gap(cfg, store, "2026-10-12T10:50:00", datetime(2026, 10, 12, 11, 20))
    up = today.uptime(cfg, store, TUE)
    assert up["last"]["label"] == "Mon Oct 12" and up["last"]["missed_swing"] and not up["last"]["ok"]
    assert up["last"]["text"] == ("off 2 times during market hours (1h 48m in all); it missed the swing desk's 3:45 "
                                  "decision")
    assert up["today"]["text"] == "running all day so far" and up["today"]["ok"]
    assert today.uptime(cfg, Store(":memory:"), date(2026, 10, 14))["last"]["text"].startswith("no record")
    data_path(cfg, "reports/after-market-2026-10-13.md").write_text("# Report\n")
    assert today.uptime(cfg, Store(":memory:"), date(2026, 10, 14))["last"]["text"] == "ran all through market hours"
    assert today.last_trading_day(date(2026, 10, 12)) == date(2026, 10, 9)                # Monday -> Friday


def test_a_day_from_before_the_update_reads_its_gaps_from_its_report(cfg):
    """Your Oct 12 report, as written: the gaps come from it, not "ran all through market hours"."""
    data_path(cfg, "reports/after-market-2026-10-12.md").write_text(
        "# After-market report: Monday, October 12, 2026\n\n## The autopilot today\n\n"
        "- **Not running from 10:25 to 10:36** (the Mac asleep, off, unplugged or frozen): it missed 2 of the day "
        "desk's 5-minute checks.\n"
        "- **Not running from 14:30 to 15:48** (the Mac asleep, off, unplugged or frozen): it missed the swing desk's "
        "daily decision and 15 of the day desk's 5-minute checks.\n- To keep it running: ...\n")
    last = today.uptime(cfg, Store(":memory:"), TUE)["last"]
    assert last["text"] == "off 2 times during market hours (1h 29m in all); it missed the swing desk's 3:45 decision"


def test_today_shows_the_reports_plain_english_points(cfg):
    data_path(cfg, "reports/after-market-2026-10-12.md").write_text(
        "# After-market report: Monday, October 12, 2026\n\n## In plain English\n\n"
        "- **Swing desk** sold MUU at a stop-loss.\n- Bought LAZR on `momentum` scores $\\ge$ 0.8.\n\n"
        "## The market\n\n- SPY closed at $778.03\n")
    r = today.report_summary(cfg)
    assert r["label"] == "Monday Oct 12"
    assert r["points"] == ["Swing desk sold MUU at a stop-loss.", "Bought LAZR on momentum scores ≥ 0.8."]
    data_path(cfg, "reports/after-market-2026-10-13.md").write_text("# After-market report\n\n## The market\n")
    assert today.report_summary(cfg) == {"date": "2026-10-13", "label": "Tuesday Oct 13", "points": []}
