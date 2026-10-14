"""
school_web.py: school websites read in Kestrel's own browser (mac/app/browser.swift), for the Today screen.

AP Classroom offers no way for other apps to read it, and Google Classroom's own way (google_school.py) needs a
Google Cloud key that a school account may not be allowed to use. So Kestrel reads them the way you do: in its
browser, signed in as you (as many accounts as you like: your school Google, your personal Gmail, College Board).
You open a page that lists your work (AP Classroom's assignments, Google Classroom's To-do for each Google account,
any other school site) and press "Add to Today". Kestrel then re-reads those pages by itself every few hours, out of
sight, and signs back in with the passwords you let it save (the browser keeps those, never this file).

How it reads a page, most dependable first:
  1. the page's own data (the JSON it downloaded to draw itself): anything with a title and a due date;
  2. its rows (tables, lists and cards): a title, a date, a status;
  3. its visible text: a "Due <date>" line or a Due column (AP Classroom's older layouts);
  4. the local AI (llm.py, when Ollama is running): it reads the text like a person; only titles that really are
     on the page are kept.
If none of them finds anything, "Copy what Kestrel saw" (Today, or the browser's Page menu) copies what Kestrel saw on
the page, to paste into a chat with Claude so the reader can learn that page.

It only reads; it never clicks, starts, turns in or changes anything (signing back in aside).
Saved on this Mac only: data/school_web.json, and the last read of each page in data/school_web_seen/.
"""
import hashlib
import json
import re
import sys
import urllib.error
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from .config import data_path

FILE = "school_web.json"
OLD_FILE = "ap_classroom.json"          # before the browser (version 1.0.122): AP Classroom pages only
SEEN_DIR = "school_web_seen"            # the last read of each page, for "Copy what Kestrel saw"
STALE_MINUTES = 120                     # the Today screen asks the browser to re-read after this
KEEP_DAYS_BACK, KEEP_DAYS_AHEAD = 21, 60
MAX_PAGES = 30
MAX_ITEMS = 150                         # per page
AI_TEXT = 12000                         # characters of a page the local AI reads
REPORT_TEXT = 12000                     # characters of a page's text in "Copy what Kestrel saw"

MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
DATE = re.compile(r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\b"
                  r"(?:,?\s+(?P<year>\d{4}))?"
                  r"|\b(?P<m>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<y>\d{2,4}))?\b"
                  r"|\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})\b", re.I)
TIME = re.compile(r"\b(?P<h>\d{1,2}):(?P<mi>\d{2})\s*(?P<ap>[ap])\.?\s?m\b\.?", re.I)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY = re.compile(r"\b(?P<wd>mon|tue|wed|thu|fri|sat|sun)(?:day|s|sday|nesday|r|rs|rsday|urday)?\b\.?", re.I)
STATUS = re.compile(r"\b(not started|in progress|completed?|submitted|scored|awaiting scoring|past due|missing|"
                    r"now open|closed|turned in(?: late)?|done late|graded|returned)\b", re.I)
DONE = re.compile(r"\b(completed?|submitted|scored|awaiting scoring|turned in|done late|graded|returned)\b", re.I)
SIGN_IN = re.compile(r"\bsign in\b|\blog in\b|forgot (your )?(password|username)|create (an )?account", re.I)
WORK = re.compile(r"\b(due|assign|missing|quiz|test|exam|homework|progress check|to-?do|turned in|deadline|"
                  r"not started|in progress)", re.I)
NOT_TITLES = {"start", "view", "open", "resume", "begin", "review", "results", "assigned", "due", "status", "score",
              "assignments", "assignment", "my assignments", "to do", "to-do", "details", "go", "continue", "more",
              "missing", "done", "no due date", "this week", "next week", "later", "earlier", "all classes", "today",
              "tomorrow", "upcoming", "see all", "view all", "view work", "mark as done", "turn in", "unsubmit"}
NOT_DUE = re.compile(r"(posted|assigned|created|edited|updated|opened|opens|starts?|start date|submitted|turned in|"
                     r"graded|returned|scored|completed)\b", re.I)
HEADERS = {"assignment", "assignments", "title", "name", "assessment", "start", "start date", "starts", "due",
           "due date", "status", "score", "type", "questions", "course", "class", "actions", "progress", "results",
           "date", "points", "grade"}
COURSE = re.compile(r"\bAP[ \t]+(?:[A-Z][A-Za-z&.']*[ \t]?){1,6}")
NOT_COURSES = {"classroom", "central", "calendar", "daily", "students", "student", "scores", "exam", "exams", "course",
               "courses", "home", "program", "services", "coordinator"}
SITES = {"ap": "AP Classroom", "classroom": "Google Classroom"}


# ------------------------------------------------------------------ dates and words
def _clock(hour: int, minute: int) -> str:
    return datetime(2000, 1, 1, hour, minute).strftime("%-I:%M%p").lower()


def time_of(text: str) -> str:
    """"11:59pm" from "11:59 PM" in a piece of text, or ""."""
    clock = TIME.search(str(text or ""))
    if not clock:
        return ""
    return _clock(int(clock["h"]) % 12 + (12 if clock["ap"].lower() == "p" else 0), int(clock["mi"]))


def find_date(text: str, today: date) -> tuple:
    """(the date, "11:59pm" or "") in a piece of text like "Oct 17, 2026, 11:59 PM", "10/17/2026", "tomorrow" or
    "Friday" (the next one, or today)."""
    text = str(text or "")
    found = DATE.search(text)
    at = time_of(text[found.end():] if found else text)
    if not found:
        low = text.lower()
        if re.search(r"\btoday\b|\btonight\b", low):
            return today, at
        if re.search(r"\btomorrow\b", low):
            return today + timedelta(days=1), at
        if re.search(r"\byesterday\b", low):
            return today - timedelta(days=1), at
        day = WEEKDAY.search(text)
        if day:
            ahead = (WEEKDAYS.index(day["wd"][:3].lower()) - today.weekday()) % 7
            return today + timedelta(days=ahead), at
        return None, ""
    try:
        if found["iy"]:
            return date(int(found["iy"]), int(found["im"]), int(found["id"])), at
        if found["mon"]:
            month, day, year = MONTHS[found["mon"][:3].lower()], int(found["day"]), found["year"]
        else:
            month, day, year = int(found["m"]), int(found["d"]), found["y"]
            year = (int(year) + 2000 if year and len(year) == 2 else year)
        if year:
            return date(int(year), month, day), at
        due = date(today.year, month, day)
        return (due if due >= today - timedelta(days=60) else date(today.year + 1, month, day)), at
    except (ValueError, KeyError):
        return None, ""


def _mostly_date(cell: str, today: date) -> bool:
    """A cell that is a date (and maybe a time or "Due"), not a title that happens to hold one ("Unit 10/11 test")."""
    if not find_date(cell, today)[0]:
        return False
    rest = TIME.sub("", DATE.sub("", WEEKDAY.sub("", cell)))
    rest = re.sub(r"\b(due|date|at|by|on|today|tonight|tomorrow|yesterday|[ecmp][sd]?t)\b|[\s,.:\-–]", "", rest, flags=re.I)
    return len(rest) < 4


def _title_like(line: str) -> bool:
    s = str(line or "").strip(" \t-–—|·:•")
    return (3 <= len(s) <= 200 and s.lower() not in NOT_TITLES and not STATUS.fullmatch(s)
            and len(re.findall(r"[A-Za-z]", s)) >= 3
            and not re.match(r"(due|start|assigned|opens?|closes?|posted)\b", s, re.I)
            and not re.match(r"\d+\s*(questions?|items?|points?|pts|%)\b|\d+\s*/\s*\d+$", s, re.I)
            and not re.match(r"https?://", s)
            and not (DATE.search(s) and len(DATE.sub("", s).strip(" ,.:")) < 4))


def _status(text: str) -> str:
    """The first status in a piece of text ("Now Open" only says there's no due date)."""
    for hit in STATUS.finditer(str(text or "").replace("_", " ")):
        if hit.group(0).lower() != "now open":
            return hit.group(0).lower()
    return ""


def course_name(text: str, title: str) -> str:
    """The AP class a page is about ("AP United States History"), from its title or text; not College Board's own
    names like AP Classroom or AP Calendar."""
    for source in (title, text):
        for found in COURSE.finditer(str(source or "")):
            name = re.sub(r"[ \t]+(Assignments?|Classroom|Home|Course)\b.*$", "", found.group(0).strip())
            words = name.split()
            if len(words) > 1 and words[1].lower() not in NOT_COURSES:
                return name
    return ""


def site_of(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").lower()
    if host == "collegeboard.org" or host.endswith(".collegeboard.org"):
        return "ap"
    if host == "classroom.google.com":
        return "classroom"
    return "web"


def site_label(url: str) -> str:
    site = site_of(url)
    return SITES.get(site) or re.sub(r"^www\.", "", (urlparse(str(url or "")).hostname or "this site").lower())


def _todo_page(url: str, title: str) -> bool:
    """A page that is a list of work: a date on it is a due date even without the word "due"."""
    return bool(re.search(r"assign|to-?do|todo|not-turned-in|missing|homework|coursework", f"{url} {title}", re.I))


# ------------------------------------------------------------------ 1. the page's own data
_TITLE_KEYS = ("title", "assignmenttitle", "assessmenttitle", "assignmentname", "assessmentname", "name", "label")
_STATUS_KEYS = ("status", "state", "progress", "submissionstatus", "completionstatus", "assignmentstatus",
                "studentstatus", "progressstatus", "submissionstate")
_DONE_KEYS = ("completed", "iscompleted", "complete", "iscomplete", "submitted", "issubmitted", "turnedin",
              "isturnedin", "done", "isdone")
_COURSE_KEYS = ("coursename", "coursetitle", "classname", "sectionname", "course", "class", "section", "subject")
_BEST_DUE = ("duedate", "dueat", "duedatetime", "due", "duedatetimeutc", "duedateutc", "duetimestamp", "dueon")


def _when(value, today: date, tz=None) -> tuple:
    """(date, "11:59pm") from a due value in a page's data: "2026-10-17T03:59:00Z" (in this Mac's time zone),
    "2026-10-17", 1792209540000 (milliseconds), {"year": 2026, "month": 10, "day": 17}, or words."""
    if value is None or isinstance(value, bool):
        return None, ""
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        if not 1e9 <= seconds <= 4e9:
            return None, ""
        when = datetime.fromtimestamp(seconds, tz) if tz else datetime.fromtimestamp(seconds)
        return when.date(), "" if (when.hour, when.minute) == (0, 0) else _clock(when.hour, when.minute)
    if isinstance(value, dict):
        low = {str(k).lower(): v for k, v in value.items()}
        if all(k in low for k in ("year", "month", "day")):
            try:
                return date(int(low["year"]), int(low["month"]), int(low["day"])), ""
            except (TypeError, ValueError):
                return None, ""
        for key in ("datetime", "date", "value", "iso", "utc", "time", "seconds"):
            if key in low:
                return _when(low[key], today, tz)
        return None, ""
    if isinstance(value, str):
        s = value.strip()
        iso = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(Z|[+-]\d{2}:?\d{2})?)?", s)
        if iso:
            try:
                if not iso.group(2):
                    return date.fromisoformat(iso.group(1)), ""
                when = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return None, ""
            if when.tzinfo:
                when = when.astimezone(tz)                       # tz None: this Mac's own time zone
            return when.date(), "" if (when.hour, when.minute) == (0, 0) else _clock(when.hour, when.minute)
        if re.fullmatch(r"\d{10,13}", s):
            return _when(int(s), today, tz)
        return find_date(s, today) if len(s) <= 60 else (None, "")
    return None, ""


def _dicts(node, budget: list):
    stack = [node]
    while stack and budget[0] > 0:
        cur = stack.pop()
        budget[0] -= 1
        if isinstance(cur, dict):
            yield cur
            stack.extend(reversed(list(cur.values())))
        elif isinstance(cur, list):
            stack.extend(reversed(cur))


def _keys(d: dict) -> dict:
    low = {}
    for k, v in d.items():
        low.setdefault(re.sub(r"[_\-\s]", "", str(k).lower()), v)
    return low


def _data_item(d: dict, today: date, tz=None):
    low = _keys(d)
    due_keys = [k for k in low if "due" in k and not isinstance(low[k], bool)
                and not k.endswith(("count", "soon", "settings", "setting", "type", "policy", "label", "text", "status"))]
    if not due_keys:
        return None
    name = next((low[k] for k in _TITLE_KEYS if isinstance(low.get(k), str)), None)
    if name is None:
        name = next((v for k, v in low.items() if k.endswith("title") and isinstance(v, str)), None)
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not _title_like(name):
        return None
    due, at = None, ""
    for key in sorted(due_keys, key=lambda k: (k not in _BEST_DUE, k)):
        due, at = _when(low[key], today, tz)
        if due:
            clock = low.get("duetime")                          # Google's style: a date, and a time in UTC
            if not at and isinstance(clock, dict) and isinstance(low[key], dict):
                when = datetime(due.year, due.month, due.day, int(clock.get("hours") or 0),
                                int(clock.get("minutes") or 0), tzinfo=timezone.utc).astimezone(tz)
                due, at = when.date(), _clock(when.hour, when.minute)
            break
    status = next((low[k] for k in _STATUS_KEYS if isinstance(low.get(k), str)), "")
    status = _status(status)
    done = any(low.get(k) is True for k in _DONE_KEYS)
    if due is None and not (status or done or any("assign" in k for k in low)):
        return None                                             # no due date and nothing saying it's work
    course = next((low[k] for k in _COURSE_KEYS if low.get(k)), "")
    if isinstance(course, dict):
        inner = _keys(course)
        course = inner.get("name") or inner.get("title") or ""
    item = {"title": name[:200], "due": due, "due_time": at, "status": status or ("completed" if done else "")}
    if isinstance(course, str) and _title_like(course) and len(course) <= 80:
        item["course"] = course.strip()
    return item


def from_data(blobs, today: date, tz=None) -> list:
    """Assignments in the data the page downloaded: blobs = [{"url", "body": "<JSON text>"}, ...]."""
    found, budget = [], [300000]
    for blob in blobs or []:
        body = blob.get("body") if isinstance(blob, dict) else blob
        if isinstance(body, str):
            body = body.strip()
            if body.startswith(")]}'"):                         # Google's guard in front of its JSON
                body = body[4:]
            try:
                body = json.loads(body)
            except ValueError:
                continue
        for d in _dicts(body, budget):
            item = _data_item(d, today, tz)
            if item:
                found.append(item)
    return found


# ------------------------------------------------------------------ 2. the page's rows
def _row_cells(raw) -> tuple:
    if isinstance(raw, dict):
        cells, link = raw.get("cells") or [], str(raw.get("link") or "")
    else:
        cells, link = raw or [], ""
    cells = [re.sub(r"\s+", " ", str(c)).strip() for c in cells if str(c or "").strip()][:15]
    return cells, link if link.startswith("https://") else ""


def _row_item(cells: list, today: date, site: str, todo: bool):
    dates = []                                                  # (index, date, time, says "due")
    for j, cell in enumerate(cells):
        says_due = bool(re.search(r"\bdue\b", cell, re.I)) or (j > 0 and re.fullmatch(r"due( date)?:?", cells[j - 1], re.I))
        if (NOT_DUE.match(cell) and not says_due) or not (says_due or _mostly_date(cell, today)):
            continue
        day, at = find_date(cell, today)
        if day:
            dates.append((j, day, at, bool(says_due)))
    now_open = any(c.lower() == "now open" for c in cells)
    marked = [d for d in dates if d[3]]
    if marked:
        spot, due, at = marked[0][:3]
    elif len(dates) >= 2:                                       # start ... due: the later date is when it's due
        spot, due, at = max(dates, key=lambda d: d[1])[:3]
    elif dates and todo:
        spot, due, at = dates[0][:3]
    elif now_open:
        spot, due, at = -1, None, ""
    else:
        return None
    used = {d[0] for d in dates}
    name_at = next((k for k, c in enumerate(cells) if k not in used and _title_like(c) and not _mostly_date(c, today)
                    and not re.fullmatch(r"due( date)?:?", c, re.I)), None)
    if name_at is None:
        return None
    item = {"title": cells[name_at], "due": due, "due_time": at, "status": _status(" | ".join(cells))}
    if site == "classroom":                                     # Google Classroom: the class's name follows the title
        course = next((c for k, c in enumerate(cells) if k > name_at and k not in used and _title_like(c)
                       and len(c) <= 80 and not STATUS.search(c) and not _mostly_date(c, today)), "")
        if course:
            item["course"] = course
    return item


def from_rows(rows, today: date, site: str = "web", todo: bool = False) -> list:
    """Assignments in the page's rows: [["Unit 3 Progress Check", "Oct 6", "Oct 17, 11:59 PM", "Not started"], ...]
    or [{"cells": [...], "link": "https://..."}]. A header row with a Due column says which cell is which."""
    found, cols = [], None
    for raw in rows or []:
        cells, link = _row_cells(raw)
        if len(cells) < 2:
            continue
        low = [c.lower().rstrip(":") for c in cells]
        if any(c in ("due", "due date") for c in low) and sum(c in HEADERS for c in low) >= max(2, len(low) - 1):
            cols = {"n": len(cells), "due": next(j for j, c in enumerate(low) if c in ("due", "due date")),
                    "title": next((j for j, c in enumerate(low) if c in ("assignment", "assignments", "title", "name",
                                                                          "assessment")), 0),
                    "status": next((j for j, c in enumerate(low) if c in ("status", "progress")), None)}
            continue
        item = None
        if cols and len(cells) == cols["n"]:
            due, at = find_date(cells[cols["due"]], today)
            name = cells[cols["title"]]
            if _title_like(name) and (due or cells[cols["due"]].lower() == "now open"):
                status = cells[cols["status"]] if cols["status"] is not None else ""
                item = {"title": name, "due": due, "due_time": at, "status": _status(status) or _status(" | ".join(cells))}
        item = item or _row_item(cells, today, site, todo)
        if item:
            if link:
                item["link"] = link
            found.append(item)
    return found


# ------------------------------------------------------------------ 3. the visible text
def parse(text: str, title: str, today: date) -> dict:
    """{"items": [{title, due, due_time, status, done}], "course", "signed_out"} from a page's visible text."""
    lines = [l.rstrip() for l in str(text or "").splitlines()]
    found = []
    # a table with a "Due" column (AP Classroom's older assignments list: title, start, due, status)
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) < 2 or not any(re.fullmatch(r"due( date)?", c, re.I) for c in cells):
            continue
        low = [c.lower() for c in cells]
        due_col = next(j for j, c in enumerate(low) if re.fullmatch(r"due( date)?", c))
        status_col = next((j for j, c in enumerate(low) if "status" in c), None)
        title_col = next((j for j, c in enumerate(low) if c in ("assignment", "title", "name", "assessment")), 0)
        for row in lines[i + 1:]:
            cols = [c.strip() for c in row.split("\t")]
            if len(cols) <= max(due_col, title_col):
                if not row.strip():
                    continue
                break                                            # the table ended
            if not _title_like(cols[title_col]):
                continue
            due, at = find_date(cols[due_col], today)
            status = cols[status_col] if status_col is not None and status_col < len(cols) else ""
            if not status:
                status = _status(row)
            if due or "now open" in cols[due_col].lower():
                found.append({"title": cols[title_col], "due": due, "due_time": at, "status": status})
    # assignment cards: a line with "Due <date>" (or "Due" and the date on the next line), its title just before it
    if not found:
        for i, line in enumerate(lines):
            hit = re.search(r"\bdue\b[:\s]*(.*)", line, re.I)
            if not hit:
                continue
            due, at = find_date(hit.group(1), today)
            last = i
            if not due and not hit.group(1).strip() and i + 1 < len(lines) and _mostly_date(lines[i + 1], today):
                due, at = find_date(lines[i + 1], today)
                last = i + 1
            if not due:
                continue
            before = line[:hit.start()].strip(" \t-–—|·:•,")
            name = before if _title_like(before) else next(
                (lines[j].strip() for j in range(i - 1, max(-1, i - 5), -1) if _title_like(lines[j])), "")
            if not name:
                continue
            after = []                                           # its status: after the due line, before the next card
            for j in range(last + 1, min(len(lines), last + 4)):
                if re.search(r"\bdue\b", lines[j], re.I):
                    break
                after.append(lines[j])
            state = STATUS.search(" ".join(after)) or STATUS.search(line)
            found.append({"title": name.strip(" \t-–—|·:•"), "due": due, "due_time": at,
                          "status": state.group(0) if state else ""})
    items = _finish(found)
    return {"items": items, "course": course_name(text, title) or "AP Classroom",
            "signed_out": not items and bool(SIGN_IN.search(str(text or "")))}


def _finish(found: list) -> list:
    """No repeats; statuses in plain lower case; done or not."""
    items, seen = [], set()
    for f in found:
        key = (f["title"].lower(), f["due"])
        if key in seen:
            continue
        seen.add(key)
        status = str(f.get("status") or "").strip().lower().replace("_", " ")
        status = "" if status == "now open" else status
        items.append({**f, "status": status, "done": bool(DONE.search(status))})
    return items[:MAX_ITEMS]


# ------------------------------------------------------------------ 4. the local AI
AI_PROMPT = """Below is the visible text of a school web page ({label}). List every assignment, quiz, test or other \
piece of school work on it that has a due date or a status.
Answer with JSON only, like this:
{{"items": [{{"title": "Unit 3 Progress Check: MCQ", "course": "AP Biology", "due": "2026-10-17", "time": "11:59 PM", \
"status": "not started"}}]}}
- "title": copy it exactly as it is written on the page.
- "due": the due date as YYYY-MM-DD, or null if it has none. Today is {today}: turn words like "Friday" or \
"tomorrow" into dates.
- "status": not started, in progress, completed, turned in, missing, or empty.
If there is no school work on the page, answer {{"items": []}}.

PAGE TEXT:
<<<
{text}
>>>"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def from_ai(cfg, text: str, label: str, today: date):
    """What the local AI finds on the page, or None if it isn't available (off, Ollama not running, no model yet)."""
    from . import llm
    if not (cfg or {}).get("llm", {}).get("enabled"):
        return None
    names = llm.downloaded(cfg)
    if names is None:
        return None
    model = llm.pick_model(cfg, names)
    if not model:
        return None
    page = str(text or "").strip()[:AI_TEXT]
    body = {"model": model, "stream": False, "format": "json", "options": {"temperature": 0, "num_ctx": 8192},
            "prompt": AI_PROMPT.format(label=label, today=f"{today:%A, %B} {today.day}, {today.year}", text=page)}
    if model not in llm._no_think:
        body["think"] = False
    try:
        try:
            answer = llm._generate(cfg, body)
        except urllib.error.HTTPError as e:
            if e.code != 400 or "think" not in body:
                raise
            llm._no_think.add(model)                     # "does not support thinking": ask again without it
            body.pop("think")
            answer = llm._generate(cfg, body)
        data = json.loads(re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip())
    except Exception as e:
        print(f"  (the local AI couldn't read the page: {e})", file=sys.stderr)
        return None
    whole, found = _norm(page), []
    for i in (data.get("items") if isinstance(data, dict) else data) or []:
        if not isinstance(i, dict):
            continue
        name = re.sub(r"\s+", " ", str(i.get("title") or "")).strip()
        if not _title_like(name) or _norm(name) not in whole:   # only what's really on the page
            continue
        due = None
        if i.get("due"):
            try:
                due = date.fromisoformat(str(i["due"])[:10])
            except ValueError:
                due = find_date(str(i["due"]), today)[0]
        status = str(i.get("status") or "").strip().lower()
        item = {"title": name[:200], "due": due, "due_time": time_of(str(i.get("time") or "")),
                "status": "completed" if status == "done" else _status(status)}
        course = re.sub(r"\s+", " ", str(i.get("course") or "")).strip()
        if _title_like(course) and len(course) <= 80 and _norm(course) in whole:
            item["course"] = course
        found.append(item)
    return found


# ------------------------------------------------------------------ reading a page
def extract(cfg, payload: dict, today: date, old: dict = None) -> dict:
    """What's on a page the browser read: payload = {"url", "title", "text", "rows", "data", "login"}.
    {"items", "course", "how", "tried", "signed_out", "text_hash"}"""
    url, title, text = (str(payload.get(k) or "") for k in ("url", "title", "text"))
    site = site_of(payload.get("page") or url)
    todo = _todo_page(url, title)
    tried, items, how = [], [], ""
    finders = (("page data", lambda: from_data(payload.get("data"), today)),
               ("rows", lambda: from_rows(payload.get("rows"), today, site, todo)),
               ("text", lambda: parse(text, title, today)["items"]))
    for name, finder in finders:
        tried.append(name)
        items = _finish(finder())
        if items:
            how = name
            break
    signed_out = not items and (bool(payload.get("login")) or bool(SIGN_IN.search(text)))
    text_hash = hashlib.sha1(text.encode()).hexdigest()
    if not items and not signed_out and WORK.search(text):
        if old and old.get("text_hash") == text_hash and old.get("how") == "local AI":
            items, how = [{**i, "due": date.fromisoformat(i["due"]) if i.get("due") else None}
                          for i in old.get("items") or []], "local AI"   # the same page as last time: same answer
            tried.append("local AI")
        else:
            found = from_ai(cfg, text, site_label(url), today)
            tried.append("local AI" if found is not None else "local AI (not running)")
            items = _finish(found or [])
            how = "local AI" if items else ""
    course = course_name(text, title) if site == "ap" else ""
    if site == "web" and not course:
        course = re.sub(r"\s+", " ", title).strip()[:60]
    return {"items": items, "course": course, "how": how, "tried": tried, "signed_out": signed_out,
            "text_hash": text_hash}


# ------------------------------------------------------------------ the saved pages
def load(cfg) -> dict:
    path = data_path(cfg, FILE)
    try:
        state = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        state = {}
    state.setdefault("pages", {})
    old = data_path(cfg, OLD_FILE)
    if old.exists():                                    # the AP window's pages (1.0.122) join the browser's
        try:
            for url, page in (json.loads(old.read_text()).get("pages") or {}).items():
                state["pages"].setdefault(url, {**page, "site": "ap", "label": SITES["ap"]})
            _save_state(cfg, state)
            old.unlink()
        except (OSError, ValueError):
            pass
    return state


def _save_state(cfg, state: dict):
    path = data_path(cfg, FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, default=str))
    tmp.replace(path)


def _key(url: str) -> str:
    return hashlib.sha1(str(url).encode()).hexdigest()[:12]


def _data_summary(blobs) -> list:
    """The page data's shape, for "Copy what Kestrel saw": each key about dates, titles or status, with examples."""
    lines, seen, budget = [], {}, [100000]
    wanted = re.compile(r"due|date|time|title|name|status|state|course|class|deadline|assign", re.I)
    for blob in (blobs or [])[:40]:
        source = blob.get("url", "") if isinstance(blob, dict) else ""
        body = blob.get("body") if isinstance(blob, dict) else blob
        try:
            body = json.loads(body.strip().removeprefix(")]}'")) if isinstance(body, str) else body
        except ValueError:
            continue
        stack = [(body, "")]
        while stack and budget[0] > 0:
            node, path = stack.pop()
            budget[0] -= 1
            if isinstance(node, dict):
                for k, v in node.items():
                    here = f"{path}.{k}" if path else str(k)
                    if isinstance(v, (dict, list)):
                        stack.append((v, here))
                    elif wanted.search(str(k)):
                        examples = seen.setdefault(f"{source.split('?')[0]} {here}", [])
                        if len(examples) < 3:
                            examples.append(str(v)[:80])
            elif isinstance(node, list):
                for v in node[:50]:
                    stack.append((v, f"{path}[]"))
    for path, examples in list(seen.items())[:150]:
        lines.append(f"{path} = {' | '.join(examples)}")
    return lines


def _seen(page_url: str, payload: dict, result: dict, now: datetime) -> dict:
    """One read of a page, as "Copy what Kestrel saw" shows it."""
    rows = []
    for raw in (payload.get("rows") or [])[:300]:
        cells, _ = _row_cells(raw)
        if cells:
            rows.append(cells)
    return {"page": page_url, "url": payload.get("url"), "title": payload.get("title"), "account": payload.get("account"),
            "when": now.isoformat(timespec="seconds"), "found": len(result["items"]), "how": result["how"],
            "tried": result["tried"], "login": bool(payload.get("login")), "signed_out": result["signed_out"],
            "text": str(payload.get("text") or "")[:100000], "rows": rows, "data": _data_summary(payload.get("data")),
            "data_count": len(payload.get("data") or [])}


def _remember(cfg, page_url: str, payload: dict, result: dict, now: datetime):
    """The last read of the page, kept for "Copy what Kestrel saw"."""
    path = data_path(cfg, f"{SEEN_DIR}/{_key(page_url)}.json")
    path.write_text(json.dumps(_seen(page_url, payload, result, now), default=str))


def save(cfg, payload: dict, now: datetime = None) -> dict:
    """A page the browser read. payload: "url" (where the browser is), "page" (the chosen page it was asked to read;
    default: url), "title", "text", "rows", "data", "account", "login" (a sign-in form was showing), "auto" (the
    browser re-reading a chosen page by itself: a page that wasn't chosen is never saved)."""
    payload = payload or {}
    page_url = str(payload.get("page") or payload.get("url") or "").strip()
    if not re.match(r"https://[^/\s?#]+", page_url):
        raise ValueError("Kestrel only reads web pages (https://...): open the page in Kestrel's browser first.")
    now = now or datetime.now()
    state = load(cfg)
    old = state["pages"].get(page_url)
    if payload.get("auto") and not old:
        return {"ok": False, "message": "That page isn't one of the pages chosen for Today."}
    if not old and len(state["pages"]) >= MAX_PAGES:
        raise ValueError(f"Today reads at most {MAX_PAGES} pages: forget one in Setup → School first.")
    result = extract(cfg, payload, now.date(), old)
    site, items = site_of(page_url), result["items"]
    account = str(payload.get("account") or (old or {}).get("account") or "")[:120]
    page = {"site": site, "label": site_label(page_url), "account": account, "title": str(payload.get("title") or "")[:200],
            "course": result["course"], "signed_out": result["signed_out"], "updated": now.isoformat(timespec="seconds"),
            "found": len(items), "how": result["how"], "text_hash": result["text_hash"],
            "items": [{**i, "due": i["due"].isoformat() if i["due"] else None} for i in items]}
    if result["signed_out"] and old:
        page.update(items=old.get("items") or [], found=old.get("found", 0), how=old.get("how", ""),
                    course=old.get("course") or page["course"])   # keep what it knew; say "sign in again"
    state["pages"][page_url] = page
    _save_state(cfg, state)
    try:
        _remember(cfg, page_url, payload, result, now)
    except OSError:
        pass
    label = page["label"]
    if result["signed_out"]:
        message = (f"This looks like {label}'s sign-in page: sign in first (Kestrel can save your password), then "
                   "open the page that lists your work and press Add to Today again.")
    elif not items:
        message = (f"Kestrel didn't find any assignments with due dates on this page (it tried: {', '.join(result['tried'])}). "
                   "If the page does list your work, choose Page → Copy What Kestrel Saw and paste it into your chat "
                   "with Claude, so Kestrel can learn this page.")
    else:
        names = ", ".join(i["title"] for i in items[:3]) + ("…" if len(items) > 3 else "")
        message = (f"Found {len(items)} assignment{'s' if len(items) != 1 else ''} on {label} ({names}): they're on "
                   "Today. Kestrel re-reads this page by itself every few hours.")
    return {"ok": bool(items), "message": message, "found": len(items), "course": page["course"], "how": result["how"],
            "signed_out": result["signed_out"]}


def pages(cfg) -> list:
    """The chosen pages for the browser to re-read: [{"url", "site", "account"}]."""
    return [{"url": url, "site": p.get("site") or site_of(url), "account": p.get("account", "")}
            for url, p in load(cfg)["pages"].items()]


def forget(cfg, url: str = None) -> str:
    state = load(cfg)
    if url:
        page = state["pages"].pop(str(url), None)
        if page is None:
            raise ValueError("That page isn't on Today's list any more.")
        _save_state(cfg, state)
        data_path(cfg, f"{SEEN_DIR}/{_key(url)}.json").unlink(missing_ok=True)
        return f"Kestrel stopped reading {page.get('label') or site_label(url)}: {page.get('title') or url}."
    data_path(cfg, FILE).unlink(missing_ok=True)
    for seen in data_path(cfg, f"{SEEN_DIR}/x").parent.glob("*.json"):
        seen.unlink(missing_ok=True)
    return ("Kestrel forgot the pages it read for Today (its browser stays signed in to your accounts, and keeps "
            "the passwords you saved, until you remove them).")


def report(cfg, url: str, payload: dict = None, now: datetime = None) -> str:
    """"Copy what Kestrel saw": a page as Kestrel read it, as text to paste into a chat with Claude. payload: the page
    the browser shows right now (read here and not saved); none: the last time Kestrel read that chosen page."""
    if payload and (payload.get("text") or payload.get("rows") or payload.get("data")):
        now = now or datetime.now()
        result = extract(None, payload, now.date())                 # no local AI here: this is about the layout
        seen = _seen(str(payload.get("url") or url), payload, result, now)
    else:
        path = data_path(cfg, f"{SEEN_DIR}/{_key(url)}.json")
        try:
            seen = json.loads(path.read_text())
        except (OSError, ValueError):
            raise ValueError("Kestrel hasn't read that page yet: open it in Kestrel's browser and press Add to Today.") from None
    lines = ["What Kestrel saw on a school page. (Pasted into a chat with Claude, it shows Claude this page's layout so "
             "Kestrel can learn to read it.)",
             f"Page: {seen.get('page')}", f"Address it was on: {seen.get('url')}", f"Title: {seen.get('title')}",
             f"Read: {seen.get('when')}; found {seen.get('found')}" + (f" (from its {seen['how']})" if seen.get("how") else "")
             + f"; tried: {', '.join(seen.get('tried') or [])}"]
    if seen.get("signed_out") or seen.get("login"):
        lines.append("It looked like a sign-in page.")
    lines += ["", f"--- page data ({seen.get('data_count', 0)} downloads; keys about dates, titles and status) ---"]
    lines += seen.get("data") or ["(none)"]
    lines += ["", "--- rows (lists, tables and cards; the first 60) ---"]
    lines += [" | ".join(r) for r in (seen.get("rows") or [])[:60]] or ["(none)"]
    lines += ["", f"--- visible text (the first {REPORT_TEXT:,} characters) ---", str(seen.get("text") or "")[:REPORT_TEXT]]
    return "\n".join(lines)


def items(cfg, today: date, skip: set = None) -> list:
    """The work on the chosen pages, for the Today list (school.summary): due in the last 3 weeks or the next 2 months,
    or with no due date yet; finished work only while recent. skip: (title, due) pairs Today already has from Google's
    own Classroom sign-in (google_school.py), so nothing shows twice."""
    from .school import is_ap
    out, seen = [], set(skip or ())
    for url, page in load(cfg)["pages"].items():
        site = page.get("site") or site_of(url)
        for i in page.get("items") or []:
            due = date.fromisoformat(i["due"]) if i.get("due") else None
            if due and not (today - timedelta(days=KEEP_DAYS_BACK) <= due <= today + timedelta(days=KEEP_DAYS_AHEAD)):
                continue
            if i.get("done") and (not due or due < today - timedelta(days=3)):
                continue
            mark = (i["title"].lower(), i.get("due"))
            if mark in seen:
                continue
            seen.add(mark)
            course = i.get("course") or page.get("course") or page.get("label") or site_label(url)
            status = "missing" if due and due < today and not i.get("done") else i.get("status") or ""
            key = hashlib.sha1(f"{url}|{i['title']}|{i.get('due')}".encode()).hexdigest()[:12]
            out.append({"id": f"web-{key}", "title": i["title"], "course": course, "due": i.get("due"),
                        "due_time": i.get("due_time", ""), "ap": site == "ap" or is_ap(f"{i['title']} {course}"),
                        "done": bool(i.get("done")), "done_on": i.get("due") if i.get("done") else None,
                        "added": page.get("updated", ""), "source": site if site in SITES else "web",
                        "site": page.get("label") or site_label(url), "account": page.get("account", ""),
                        "status": status, "link": i.get("link") or url})
    return out


def status(cfg, now: datetime = None) -> dict:
    """For Today and Setup: each chosen page (what it found, when, signed out?) and whether it's time to re-read."""
    now = now or datetime.now()
    saved = load(cfg)["pages"]
    listed, ages = [], []
    for url, p in saved.items():
        try:
            age = (now - datetime.fromisoformat(p["updated"])).total_seconds() / 60
        except (KeyError, TypeError, ValueError):
            age = None
        ages.append(age)
        listed.append({"url": url, "site": p.get("site") or site_of(url), "label": p.get("label") or site_label(url),
                       "account": p.get("account", ""), "title": p.get("title", ""), "course": p.get("course", ""),
                       "found": p.get("found", 0), "how": p.get("how", ""), "signed_out": bool(p.get("signed_out")),
                       "minutes_ago": round(age) if age is not None else None})
    known = [a for a in ages if a is not None]
    oldest = max(known) if known else None
    return {"count": len(saved), "pages": listed, "found": sum(p["found"] for p in listed),
            "signed_out": any(p["signed_out"] for p in listed),
            "minutes_ago": round(oldest) if oldest is not None else None,
            "stale": bool(saved) and (oldest is None or len(known) < len(ages) or oldest >= STALE_MINUTES)}
