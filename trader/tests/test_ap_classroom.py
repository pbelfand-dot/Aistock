"""AP Classroom on the Today screen: the reader finds each assignment, its due date and status in a page's text
(AP Classroom's table, or assignment cards), notices a sign-in page, and keeps only what belongs on Today."""
from datetime import date, datetime

import pytest

from aitrader import ap_classroom, app_api, school

TUE = date(2026, 10, 13)
URL = "https://apclassroom.collegeboard.org/8/assignments?status=assigned"

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
    r = ap_classroom.parse(TABLE, "AP Classroom", TUE)
    got = [(i["title"], i["due"], i["due_time"], i["status"], i["done"]) for i in r["items"]]
    assert got == [("Unit 3 Progress Check: MCQ", date(2026, 10, 17), "11:59pm", "not started", False),
                   ("Unit 3 Progress Check: FRQ Part A", date(2026, 10, 20), "11:59pm", "in progress", False),
                   ("Unit 2 Personal Progress Check", None, "", "not started", False),   # "Now Open": no due date
                   ("Unit 1 Progress Check: MCQ", date(2026, 9, 15), "11:59pm", "complete", True)]
    assert r["course"] == "AP United States History" and not r["signed_out"]


def test_assignment_cards_with_due_lines_and_a_status_nearby():
    r = ap_classroom.parse(CARDS, "", TUE)
    got = [(i["title"], i["due"], i["due_time"], i["status"]) for i in r["items"]]
    assert got == [("Unit 4 Progress Check: MCQ", date(2026, 10, 16), "11:59pm", "not started"),
                   ("Topic Questions 4.1", date(2026, 10, 14), "", "in progress"),
                   ("Unit 3 Progress Check: FRQ", date(2026, 10, 9), "11:59pm", "submitted")]
    assert r["course"] == "AP Calculus AB" and r["items"][2]["done"]


def test_a_sign_in_page_and_an_unknown_page():
    signed_out = ap_classroom.parse("College Board\nSign In\nUsername\nPassword\nForgot username?", "Sign In", TUE)
    assert signed_out["items"] == [] and signed_out["signed_out"]
    other = ap_classroom.parse("Welcome to My AP\nJoin a Course or Exam\nAP Calendar", "My AP", TUE)
    assert other["items"] == [] and not other["signed_out"] and other["course"] == "AP Classroom"   # not a class


@pytest.mark.parametrize("text, due, at", [
    ("Oct 17, 2026, 11:59 PM", date(2026, 10, 17), "11:59pm"), ("October 30", date(2026, 10, 30), ""),
    ("10/17/26 8:00 am", date(2026, 10, 17), "8:00am"), ("2026-11-02", date(2026, 11, 2), ""),
    ("Jan 5", date(2027, 1, 5), ""), ("tomorrow 3:00 p.m.", date(2026, 10, 14), "3:00pm"), ("Now Open", None, "")])
def test_due_dates_in_the_shapes_pages_use(text, due, at):
    assert ap_classroom.find_date(text, TUE) == (due, at)


def test_chosen_pages_feed_today_and_a_sign_out_keeps_what_it_knew(cfg):
    out = app_api.handle("ap-save", cfg, payload={"url": URL, "title": "AP Classroom", "text": TABLE})
    assert out["ok"] and out["found"] == 4 and out["message"].startswith("Found 4 AP assignments (Unit 3 Progress Check: MCQ")
    assert app_api.handle("ap-pages", cfg)["pages"] == [URL]
    items = {i["title"]: i for i in ap_classroom.items(cfg, TUE)}
    assert set(items) == {"Unit 3 Progress Check: MCQ", "Unit 3 Progress Check: FRQ Part A",
                          "Unit 2 Personal Progress Check"}                           # Unit 1: finished in September
    mcq = items["Unit 3 Progress Check: MCQ"]
    assert (mcq["source"], mcq["ap"], mcq["course"], mcq["link"]) == ("ap", True, "AP United States History", URL)
    s = school.summary(cfg, TUE)
    assert [r["title"] for r in s["groups"]["week"]] == ["Unit 3 Progress Check: MCQ", "Unit 3 Progress Check: FRQ Part A"]
    assert [r["title"] for r in s["groups"]["no_date"]] == ["Unit 2 Personal Progress Check"]
    st = ap_classroom.status(cfg, datetime.now())
    assert st["pages"] == 1 and st["found"] == 4 and not st["stale"] and st["courses"] == ["AP United States History"]
    # later the window re-reads it by itself, but College Board signed it out: keep the list, say "sign in again"
    again = ap_classroom.save(cfg, URL, "Sign In", "Sign In\nUsername\nPassword", auto=True)
    assert "sign-in page" in again["message"] and ap_classroom.status(cfg)["signed_out"]
    assert len(ap_classroom.items(cfg, TUE)) == 3
    assert "forgot" in app_api.handle("ap-forget", cfg)["message"] and ap_classroom.items(cfg, TUE) == []


def test_only_college_board_pages_and_only_chosen_ones_are_read(cfg):
    with pytest.raises(ValueError, match="collegeboard.org"):
        ap_classroom.save(cfg, "https://evil.example.com/collegeboard.org/", "", TABLE)
    assert ap_classroom.save(cfg, URL, "", TABLE, auto=True)["ok"] is False          # not chosen: nothing saved
    assert ap_classroom.pages(cfg) == []
    nothing = ap_classroom.save(cfg, "https://myap.collegeboard.org/", "My AP", "Welcome to My AP")
    assert not nothing["ok"] and "screenshot" in nothing["message"]


def test_a_past_due_assignment_that_was_never_done_is_missing(cfg):
    late = "AP Biology\nAssignment\tDue\tStatus\nUnit 5 Progress Check\tOct 9, 2026, 11:59 PM\tNot started"
    ap_classroom.save(cfg, URL, "", late)
    assert [(i["title"], i["status"]) for i in ap_classroom.items(cfg, TUE)] == [("Unit 5 Progress Check", "missing")]
    assert school.summary(cfg, TUE)["missing"] == 1


def test_the_mac_window_opens_ap_classroom_and_re_reads_the_chosen_pages():
    from pathlib import Path
    mac = Path(__file__).resolve().parents[2] / "mac" / "app"
    main, window = (mac / "main.swift").read_text(), (mac / "apclassroom.swift").read_text()
    assert 'action == "ap-open"' in main and 'action == "ap-read"' in main            # the window's own actions
    assert 'askBot(["ap-save"]' in window and 'askBot(["ap-pages"])' in window       # the bot reads and keeps pages
    assert "websiteDataStore = .default()" in window                                 # remembers the sign-in
    assert {"ap-save", "ap-pages", "ap-forget"} <= set(app_api.ACTIONS) and "ap-save" in app_api.STDIN_ACTIONS
