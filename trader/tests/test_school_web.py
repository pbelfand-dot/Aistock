"""School pages read in Kestrel's browser (school_web.py): the reader finds each assignment, its due date and status in
a page's own data, its rows or its text (AP Classroom, Google Classroom's To-do for each Google account, any school
site), asks the local AI only when nothing else works, notices a sign-in page, and keeps only what belongs on Today."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from aitrader import app_api, llm, school, school_web
from aitrader.config import data_path

TUE = date(2026, 10, 13)
URL = "https://apclassroom.collegeboard.org/8/assignments?status=assigned"
SCHOOL_TODO = "https://classroom.google.com/u/0/a/not-turned-in/all"
HOME_TODO = "https://classroom.google.com/u/1/a/not-turned-in/all"
EDT = timezone(timedelta(hours=-4))

TABLE = """AP United States History
Assignments
Assigned\tCompleted\tScored
Assignment\tStart\tDue\tStatus
Unit 3 Progress Check: MCQ\tOct 6, 2026, 8:00 AM\tOct 17, 2026, 11:59 PM\tNot started
Unit 3 Progress Check: FRQ Part A\tOct 6, 2026\tOct 20, 2026, 11:59 PM\tIn Progress
Unit 2 Personal Progress Check\tSep 20, 2026\tNow Open\tNot started
Unit 1 Progress Check: MCQ\tSep 1, 2026\tSep 15, 2026, 11:59 PM\tComplete

Help\tPrivacy"""

CARDS = """AP Calculus AB
To Do
Unit 4 Progress Check: MCQ
Due Fri, Oct 16, 2026 at 11:59 PM
Not Started
Start
Topic Questions 4.1
Due Oct 14
In Progress
Resume
Unit 3 Progress Check: FRQ
Due: 10/09/2026 11:59 PM
Submitted"""


def test_the_assignments_table_with_its_due_column():
    r = school_web.parse(TABLE, "AP Classroom", TUE)
    got = [(i["title"], i["due"], i["due_time"], i["status"], i["done"]) for i in r["items"]]
    assert got == [("Unit 3 Progress Check: MCQ", date(2026, 10, 17), "11:59pm", "not started", False),
                   ("Unit 3 Progress Check: FRQ Part A", date(2026, 10, 20), "11:59pm", "in progress", False),
                   ("Unit 2 Personal Progress Check", None, "", "not started", False),   # "Now Open": no due date
                   ("Unit 1 Progress Check: MCQ", date(2026, 9, 15), "11:59pm", "complete", True)]
    assert r["course"] == "AP United States History" and not r["signed_out"]


def test_assignment_cards_with_due_lines_and_a_status_nearby():
    r = school_web.parse(CARDS, "", TUE)
    got = [(i["title"], i["due"], i["due_time"], i["status"]) for i in r["items"]]
    assert got == [("Unit 4 Progress Check: MCQ", date(2026, 10, 16), "11:59pm", "not started"),
                   ("Topic Questions 4.1", date(2026, 10, 14), "", "in progress"),
                   ("Unit 3 Progress Check: FRQ", date(2026, 10, 9), "11:59pm", "submitted")]
    assert r["course"] == "AP Calculus AB" and r["items"][2]["done"]


def test_a_due_label_with_its_date_on_the_next_line():
    text = "AP Biology\nUnit 2 Progress Check: FRQ\nDue\nOct 22, 2026, 11:59 PM\nNot Started\nStart"
    got = [(i["title"], i["due"], i["status"]) for i in school_web.parse(text, "", TUE)["items"]]
    assert got == [("Unit 2 Progress Check: FRQ", date(2026, 10, 22), "not started")]


def test_a_sign_in_page_and_an_unknown_page():
    signed_out = school_web.parse("College Board\nSign In\nUsername\nPassword\nForgot username?", "Sign In", TUE)
    assert signed_out["items"] == [] and signed_out["signed_out"]
    other = school_web.parse("Welcome to My AP\nJoin a Course or Exam\nAP Calendar", "My AP", TUE)
    assert other["items"] == [] and not other["signed_out"] and other["course"] == "AP Classroom"   # not a class


@pytest.mark.parametrize("text, due, at", [
    ("Oct 17, 2026, 11:59 PM", date(2026, 10, 17), "11:59pm"), ("October 30", date(2026, 10, 30), ""),
    ("10/17/26 8:00 am", date(2026, 10, 17), "8:00am"), ("2026-11-02", date(2026, 11, 2), ""),
    ("Jan 5", date(2027, 1, 5), ""), ("tomorrow 3:00 p.m.", date(2026, 10, 14), "3:00pm"), ("Now Open", None, ""),
    ("Friday, 11:59 PM", date(2026, 10, 16), "11:59pm"), ("Due Tues", TUE, ""), ("Mon", date(2026, 10, 19), ""),
    ("yesterday", date(2026, 10, 12), "")])
def test_due_dates_in_the_shapes_pages_use(text, due, at):
    assert school_web.find_date(text, TUE) == (due, at)


def test_the_pages_own_data_with_utc_times_shown_in_this_macs_time_zone():
    data = {"data": {"student": {"assignments": [
        {"id": 1, "title": "Unit 3 Progress Check: MCQ", "dueDate": "2026-10-17T03:59:00Z", "status": "NOT_STARTED",
         "course": {"name": "AP Biology"}},
        {"id": 2, "assignmentName": "Topic Questions 3.2", "due_at": 1792209540000, "isCompleted": True},
        {"id": 3, "title": "Unit 4 Personal Progress Check", "dueDate": None, "status": "IN_PROGRESS"},
        {"id": 4, "name": "Join code", "dueDateSettings": {"enabled": True}},          # not work: no due value
        {"id": 5, "title": "Unit 1", "dueDate": None}]}}}                              # no due date, nothing says work
    blobs = [{"url": "https://apc-api.collegeboard.org/graphql", "body": ")]}'" + json.dumps(data)}]
    got = [(i["title"], i["due"], i["due_time"], i["status"], i.get("course"))
           for i in school_web.from_data(blobs, TUE, tz=EDT)]
    assert got == [("Unit 3 Progress Check: MCQ", date(2026, 10, 16), "11:59pm", "not started", "AP Biology"),
                   ("Topic Questions 3.2", date(2026, 10, 16), "11:59pm", "completed", None),
                   ("Unit 4 Personal Progress Check", None, "", "in progress", None)]
    google = {"title": "Lab report", "dueDate": {"year": 2026, "month": 10, "day": 15},
              "dueTime": {"hours": 3, "minutes": 59}, "state": "PUBLISHED"}             # Classroom's style: UTC
    assert [(i["due"], i["due_time"]) for i in school_web.from_data([json.dumps(google)], TUE, tz=EDT)] == \
        [(date(2026, 10, 14), "11:59pm")]


def test_rows_with_a_header_without_one_and_google_classrooms_to_do():
    rows = [["Assignment", "Start", "Due", "Status"],
            {"cells": ["Unit 3 Progress Check: MCQ", "Oct 6, 2026", "Oct 17, 2026, 11:59 PM", "Not started"],
             "link": "https://apclassroom.collegeboard.org/8/assessments/1"},
            ["Unit 3 Progress Check: FRQ", "Oct 6", "Oct 20", "In Progress", "Resume"]]   # no header for this one
    got = [(i["title"], i["due"], i["status"], i.get("link")) for i in school_web.from_rows(rows, TUE, "ap")]
    assert got == [("Unit 3 Progress Check: MCQ", date(2026, 10, 17), "not started",
                    "https://apclassroom.collegeboard.org/8/assessments/1"),
                   ("Unit 3 Progress Check: FRQ", date(2026, 10, 20), "in progress", None)]   # the later date
    todo = [["Assigned", "Missing", "Done"],
            {"cells": ["Lab report: Photosynthesis", "AP Biology", "Posted Oct 6", "Thursday, 11:59 PM"],
             "link": "https://classroom.google.com/c/123/a/456/details"},
            ["Chapter 10/11 reading notes", "English 11", "Due Friday"],
            ["Unit 10 vocab", "Spanish 3"]]                                      # no date: not on Today
    got = [(i["title"], i.get("course"), i["due"], i["due_time"])
           for i in school_web.from_rows(todo, TUE, "classroom", todo=True)]
    assert got == [("Lab report: Photosynthesis", "AP Biology", date(2026, 10, 15), "11:59pm"),
                   ("Chapter 10/11 reading notes", "English 11", date(2026, 10, 16), "")]
    # a date that isn't next to "due", on a page that isn't a list of work, isn't a due date
    assert school_web.from_rows([["Back to school night", "Thursday"]], TUE, "web") == []


def test_chosen_pages_feed_today_and_a_sign_out_keeps_what_it_knew(cfg):
    out = app_api.handle("web-save", cfg, payload={"url": URL, "title": "AP Classroom", "text": TABLE})
    assert out["ok"] and out["found"] == 4 and out["how"] == "text"
    assert out["message"].startswith("Found 4 assignments on AP Classroom (Unit 3 Progress Check: MCQ")
    assert app_api.handle("web-pages", cfg)["pages"] == [{"url": URL, "site": "ap", "account": ""}]
    assert app_api.handle("ap-pages", cfg)["pages"] == [URL]                  # what the 1.0.122 AP window asks
    items = {i["title"]: i for i in school_web.items(cfg, TUE)}
    assert set(items) == {"Unit 3 Progress Check: MCQ", "Unit 3 Progress Check: FRQ Part A",
                          "Unit 2 Personal Progress Check"}                           # Unit 1: finished in September
    mcq = items["Unit 3 Progress Check: MCQ"]
    assert (mcq["source"], mcq["ap"], mcq["course"], mcq["link"]) == ("ap", True, "AP United States History", URL)
    s = school.summary(cfg, TUE)
    assert [r["title"] for r in s["groups"]["week"]] == ["Unit 3 Progress Check: MCQ", "Unit 3 Progress Check: FRQ Part A"]
    assert [r["title"] for r in s["groups"]["no_date"]] == ["Unit 2 Personal Progress Check"]
    st = school_web.status(cfg, datetime.now())
    assert st["count"] == 1 and st["found"] == 4 and not st["stale"]
    assert st["pages"][0]["label"] == "AP Classroom" and st["pages"][0]["course"] == "AP United States History"
    # later the browser re-reads it by itself, but College Board signed it out: keep the list, say "sign in again"
    again = app_api.handle("ap-save", cfg, payload={"url": URL, "title": "Sign In", "text": "Sign In\nUsername\nPassword",
                                                    "auto": True})
    assert "sign-in page" in again["message"] and school_web.status(cfg)["signed_out"]
    assert len(school_web.items(cfg, TUE)) == 3
    assert "forgot" in app_api.handle("web-forget", cfg, payload={})["message"] and school_web.items(cfg, TUE) == []


def test_only_web_pages_and_only_chosen_ones_are_read_again(cfg):
    for bad in ("http://example.com/", "file:///etc/passwd", "javascript:alert(1)", ""):
        with pytest.raises(ValueError, match="https"):
            school_web.save(cfg, {"url": bad, "text": TABLE})
    assert school_web.save(cfg, {"url": URL, "text": TABLE, "auto": True})["ok"] is False   # not chosen: not saved
    assert school_web.pages(cfg) == []
    nothing = school_web.save(cfg, {"url": "https://myap.collegeboard.org/", "title": "My AP", "text": "Welcome to My AP"})
    assert not nothing["ok"] and "Copy What Kestrel Saw" in nothing["message"]


def test_a_past_due_assignment_that_was_never_done_is_missing(cfg):
    late = "AP Biology\nAssignment\tDue\tStatus\nUnit 5 Progress Check\tOct 9, 2026, 11:59 PM\tNot started"
    school_web.save(cfg, {"url": URL, "text": late})
    assert [(i["title"], i["status"]) for i in school_web.items(cfg, TUE)] == [("Unit 5 Progress Check", "missing")]
    assert school.summary(cfg, TUE)["missing"] == 1


def test_two_google_accounts_each_with_its_own_to_do(cfg):
    school_web.save(cfg, {"url": SCHOOL_TODO, "title": "To-do", "account": "me@school.org",
                          "rows": [["Lab report: Photosynthesis", "AP Biology", "Thursday, 11:59 PM"]]},
                    now=datetime(2026, 10, 13, 7, 0))
    school_web.save(cfg, {"url": HOME_TODO, "title": "To-do", "account": "me@gmail.com",
                          "rows": [["Driver's ed worksheet", "Driver's Ed", "Due Oct 20"]]},
                    now=datetime(2026, 10, 13, 7, 1))
    got = {(i["title"], i["account"], i["source"], i["course"]) for i in school_web.items(cfg, TUE)}
    assert got == {("Lab report: Photosynthesis", "me@school.org", "classroom", "AP Biology"),
                   ("Driver's ed worksheet", "me@gmail.com", "classroom", "Driver's Ed")}
    st = school_web.status(cfg, datetime(2026, 10, 13, 8, 0))
    assert [(p["label"], p["account"], p["found"]) for p in st["pages"]] == \
        [("Google Classroom", "me@school.org", 1), ("Google Classroom", "me@gmail.com", 1)]
    assert st["minutes_ago"] == 60 and not st["stale"]
    assert {p["account"] for p in school_web.pages(cfg)} == {"me@school.org", "me@gmail.com"}
    assert "stopped reading" in app_api.handle("web-forget", cfg, payload={"url": HOME_TODO})["message"]
    assert [p["url"] for p in school_web.pages(cfg)] == [SCHOOL_TODO]


def test_work_googles_own_sign_in_already_listed_is_not_repeated(cfg, monkeypatch):
    from aitrader import google_school
    api = [{"id": "gc-1", "title": "Lab report: Photosynthesis", "course": "AP Biology", "due": "2026-10-15",
            "ap": True, "done": False, "done_on": None, "added": "", "source": "classroom", "status": ""}]
    monkeypatch.setattr(google_school, "load_cache", lambda cfg: {"items": api})
    school_web.save(cfg, {"url": SCHOOL_TODO, "title": "To-do",
                          "rows": [["Lab report: Photosynthesis", "AP Biology", "Thursday"],
                                   ["Essay draft", "English 11", "Due Oct 16"]]}, now=datetime(2026, 10, 13, 7))
    titles = [r["title"] for r in school.summary(cfg, TUE)["groups"]["week"]]
    assert sorted(titles) == ["Essay draft", "Lab report: Photosynthesis"]           # once each


def test_the_local_ai_reads_a_new_layout_and_only_whats_really_on_the_page_is_kept(cfg, monkeypatch):
    cfg["llm"]["enabled"] = True
    text = "Course work\nWeek of Oct 12\nBio lab write-up — hand it in Friday\nAlso: quiz on cells next Monday"
    calls = []

    def answer(cfg_, body):
        calls.append(body)
        assert body["format"] == "json" and "Bio lab write-up" in body["prompt"] and "Tuesday, October 13" in body["prompt"]
        return json.dumps({"items": [
            {"title": "Bio lab write-up", "due": "2026-10-16", "time": "", "status": ""},
            {"title": "quiz on cells", "due": "2026-10-19", "status": "not started"},
            {"title": "Chemistry test", "due": "2026-10-21"}]})                  # made up: not on the page
    monkeypatch.setattr(llm, "downloaded", lambda cfg_: ["gemma4:12b"])
    monkeypatch.setattr(llm, "pick_model", lambda cfg_, names: "gemma4:12b")
    monkeypatch.setattr(llm, "_generate", answer)
    url = "https://teacher.example.org/biology/assignments"
    out = school_web.save(cfg, {"url": url, "title": "Biology", "text": text}, now=datetime(2026, 10, 13, 9))
    assert out["ok"] and out["how"] == "local AI" and out["found"] == 2
    got = [(i["title"], i["due"], i["source"]) for i in school_web.items(cfg, TUE)]
    assert got == [("Bio lab write-up", "2026-10-16", "web"), ("quiz on cells", "2026-10-19", "web")]
    school_web.save(cfg, {"url": url, "title": "Biology", "text": text, "auto": True}, now=datetime(2026, 10, 13, 12))
    assert len(calls) == 1 and school_web.status(cfg)["found"] == 2               # same page: no second question
    monkeypatch.setattr(llm, "downloaded", lambda cfg_: None)                       # Ollama not running
    off = school_web.save(cfg, {"url": url + "?x", "text": text})
    assert not off["ok"] and "local AI (not running)" in off["message"]


def test_copy_what_kestrel_saw_and_the_old_ap_windows_pages_move_over(cfg):
    data_path(cfg, "ap_classroom.json").write_text(json.dumps({"pages": {URL: {
        "title": "AP Classroom", "course": "AP Biology", "signed_out": False, "updated": "2026-10-13T08:00:00",
        "found": 1, "items": [{"title": "Unit 5 Progress Check", "due": "2026-10-20", "due_time": "", "status": "",
                               "done": False}]}}}))
    assert [(p["url"], p["site"]) for p in school_web.pages(cfg)] == [(URL, "ap")]    # moved into school_web.json
    assert not data_path(cfg, "ap_classroom.json").exists()
    assert [i["title"] for i in school_web.items(cfg, TUE)] == ["Unit 5 Progress Check"]
    page = "https://apclassroom.collegeboard.org/8/home"
    school_web.save(cfg, {"url": page, "title": "AP Classroom", "text": "Welcome back\nYour class\nAP Biology",
                          "rows": [["Unit 5", "Progress check"]],
                          "data": [{"url": "https://apc-api.collegeboard.org/q?x=1",
                                    "body": json.dumps({"course": {"title": "AP Biology", "startDate": "2026-08-20"}})}]})
    text = app_api.handle("web-report", cfg, payload={"url": page})["text"]
    assert "Page: https://apclassroom.collegeboard.org/8/home" in text and "found 0" in text
    assert "https://apc-api.collegeboard.org/q course.title = AP Biology" in text
    assert "Unit 5 | Progress check" in text and "Welcome back" in text
    with pytest.raises(ValueError, match="hasn't read"):
        app_api.handle("web-report", cfg, payload={"url": "https://nope.example/"})
    live = app_api.handle("web-report", cfg, payload={"url": "https://teacher.example.org/hw", "title": "Homework",
                                                      "text": "Homework\nEssay draft\nDue Oct 16"})["text"]
    assert "Page: https://teacher.example.org/hw" in live and "found 1 (from its text)" in live   # read now, not saved
    assert [p["url"] for p in school_web.pages(cfg)] == [URL, page]


def test_the_bots_api_lists_the_browser_actions():
    assert {"web-save", "web-pages", "web-forget", "web-report", "ap-save", "ap-pages", "ap-forget"} <= set(app_api.ACTIONS)
    assert {"web-save", "web-forget", "web-report", "ap-save"} <= app_api.STDIN_ACTIONS


def test_the_mac_browser_reads_pages_signs_in_and_keeps_passwords_away_from_the_bot():
    from pathlib import Path
    mac = Path(__file__).resolve().parents[2] / "mac" / "app"
    main, browser, logins = ((mac / f).read_text() for f in ("main.swift", "browser.swift", "logins.swift"))
    for action in ("browser-open", "web-read", "logins-list", "logins-forget", "ap-open", "ap-read"):
        assert f'action == "{action}"' in main, action                       # the window's own actions
    assert 'askBot(["web-pages"])' in browser and 'action: String = "web-save"' in browser and '"web-report"' in browser
    assert "websiteDataStore = .default()" in browser                        # stays signed in, like Safari
    assert "applicationNameForUserAgent = safariName" in browser             # Google lets you sign in
    assert 'bundledScript("browser")' in browser and 'bundledScript("browser-page")' in browser
    assert "in: .defaultClient" in browser and "contentWorld: .defaultClient" in browser   # pages can't reach it
    assert "AES.GCM" in logins and "Application Support/Kestrel" in logins   # sealed, outside the bot's folder
    assert "askBot" not in logins                                            # the bot never gets the passwords
    helper = (mac / "browser.js").read_text()
    assert "kestrelLogin" in helper and "window.kestrel = {" in helper
    assert "browserSelfTest" in main                                          # the build machine opens a tab
    assert "passwordsTried.contains(key)" in browser and "12 * 3600" in browser  # a refused password isn't retried
