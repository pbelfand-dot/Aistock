"""
school.py: your school work on the Today screen (docs/DASHBOARD-PLAN.md).

Homework you add yourself (quick add), AP Classroom work included, ticked off when it's done; once you sign
in with Google (google_school.py), your Google Classroom assignments with their own turned-in or missing state;
and the AP Classroom pages you chose in Kestrel's AP window (ap_classroom.py).
  - "APUSH Unit 3 progress check, Friday" works: a due day after the last comma (today, tomorrow, a weekday,
    "Oct 17", "10/17" or "in 3 days") becomes the due date. A date picked in the form wins.
  - AP work is spotted from the words (AP, APUSH, APES, "progress check"...) or the AP box, and gets the
    Open AP Classroom button: College Board has no API or calendar feed, so the dashboard can't read
    AP Classroom by itself.

Saved on this Mac only (data/school.json). It never touches trading.
"""
import json
import re
import secrets
from datetime import date, datetime, timedelta

from .config import data_path

FILE = "school.json"
AP_CLASSROOM = "https://myap.collegeboard.org/"  # students reach AP Classroom through My AP (College Board's sign-in)
CLASSROOM = "https://classroom.google.com/"     # its To-do page (assigned, missing, done) is one click from there
KEEP_DONE_DAYS = 30                 # finished work drops off the list after this
MAX_TITLE = 200

_AP_WORDS = re.compile(r"\bAP\b")    # capital AP only ("a map", "ap" in a word don't count)
_AP_COURSES = re.compile(r"\bAP ?(USH|WH|EH|ES|CSA|CSP|GOV|LANG|LIT|BIO|CHEM|PHYS|CALC|STATS?|PSYCH|HUG|MACRO|MICRO|"
                         r"SEM|SEMINAR|RES|ART|MUSIC|SPAN|FRENCH)\b|progress check|AP Classroom|AP Daily", re.I)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def is_ap(text: str) -> bool:
    text = str(text or "")
    return bool(_AP_WORDS.search(text) or _AP_COURSES.search(text))


def parse_due(words: str, today: date):
    """A due day in plain words, or None: today, tomorrow, yesterday, a weekday (the next one; today if it's that day),
    "next friday", "in 3 days", "Oct 17", "October 17", "10/17", "2026-10-17"."""
    w = re.sub(r"^(due|by|on)\s+", "", str(words or "").strip().lower().rstrip("."))
    if not w:
        return None
    if w in ("today", "tonight"):
        return today
    if w in ("tomorrow", "tmrw", "tmr"):
        return today + timedelta(days=1)
    if w == "yesterday":                                 # late work: it goes straight to overdue
        return today - timedelta(days=1)
    m = re.fullmatch(r"in (\d{1,2}) days?", w)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"(next )?([a-z]+)", w)
    if m:
        name = m.group(2)
        hit = next((i for i, d in enumerate(WEEKDAYS) if d == name or (len(name) >= 3 and d.startswith(name))), None)
        if hit is not None:
            ahead = (hit - today.weekday()) % 7
            if m.group(1) and not ahead:                # "next friday" on a Friday: a week from today
                ahead = 7
            return today + timedelta(days=ahead)
    try:
        return date.fromisoformat(w)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", w) or re.fullmatch(r"([a-z]{3})[a-z]*\.? (\d{1,2})", w)
    if m:
        month = int(m.group(1)) if m.group(1).isdigit() else (MONTHS.index(m.group(1)) + 1 if m.group(1) in MONTHS else 0)
        if not month:
            return None
        try:
            due = date(today.year, month, int(m.group(2)))
        except ValueError:
            return None
        return due if due >= today - timedelta(days=60) else date(today.year + 1, month, int(m.group(2)))
    return None


def parse_quick(text: str, today: date) -> tuple:
    """("the title", the due date or None) from one quick-add line: the part after the last comma, or after
    " due ", is the due day when it reads as one."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    for sep in (r",", r"\sdue\s"):
        hits = list(re.finditer(sep, text, re.I))
        if hits:
            title, words = text[:hits[-1].start()].strip(" ,"), text[hits[-1].end():]
            due = parse_due(words, today)
            if due and title:
                return title, due
    return text, None


# ------------------------------------------------------------------ the saved list
def load(cfg) -> dict:
    path = data_path(cfg, FILE)
    try:
        state = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        state = {}
    state.setdefault("items", [])
    return state


def save(cfg, state: dict, today: date = None):
    today = today or date.today()
    oldest = (today - timedelta(days=KEEP_DONE_DAYS)).isoformat()
    state["items"] = [i for i in state["items"] if not i.get("done") or (i.get("done_on") or "") >= oldest]
    path = data_path(cfg, FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(path)


def add(cfg, text: str, due: str = None, course: str = "", ap=None, today: date = None) -> dict:
    """Adds one piece of homework. due: "YYYY-MM-DD" from the form's date box (wins over words in the text)."""
    today = today or date.today()
    title, said = parse_quick(text, today)
    title = title[:MAX_TITLE].strip()
    if not title:
        raise ValueError("Type what's due, e.g. \"APUSH Unit 3 progress check, Friday\".")
    when = None
    if due:
        try:
            when = date.fromisoformat(str(due))
        except ValueError:
            raise ValueError("That due date doesn't look right.") from None
    when = when or said
    course = re.sub(r"\s+", " ", str(course or "")).strip()[:60]
    item = {"id": "h" + secrets.token_hex(4), "title": title, "course": course,
            "due": when.isoformat() if when else None, "ap": bool(ap) if ap is not None else is_ap(f"{title} {course}"),
            "done": False, "done_on": None, "added": datetime.now().isoformat(timespec="seconds"), "source": "you"}
    state = load(cfg)
    state["items"].append(item)
    save(cfg, state, today)
    return item


def _find(state: dict, item_id: str) -> dict:
    item = next((i for i in state["items"] if i["id"] == str(item_id)), None)
    if not item:
        raise ValueError("That item isn't on the list any more.")
    return item


def set_done(cfg, item_id: str, done: bool = True, today: date = None) -> dict:
    today = today or date.today()
    state = load(cfg)
    item = _find(state, item_id)
    item["done"], item["done_on"] = bool(done), today.isoformat() if done else None
    save(cfg, state, today)
    return item


def remove(cfg, item_id: str) -> dict:
    state = load(cfg)
    item = _find(state, item_id)
    state["items"].remove(item)
    save(cfg, state)
    return item


# ------------------------------------------------------------------ the Today screen
def _label(due: date, today: date) -> str:
    days = (due - today).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    if days < 0:
        return f"{-days} days ago"
    if days < 7:
        return f"{due:%A}"
    return f"{due:%a %b} {due.day}"


def due_label(due: str, today: date = None) -> str:
    """"today", "Friday", "Mon Oct 26"... for a "YYYY-MM-DD" due date."""
    return _label(date.fromisoformat(due), today or date.today())


def summary(cfg, today: date = None) -> dict:
    """The list in groups, soonest first: overdue, today, tomorrow, this week (the next 7 days), later, no date,
    and what was finished in the last 3 days. Your own items and, once you've signed in, Google Classroom's
    (google_school.py: its own turned-in state, and a link to each one); plus today's calendar events."""
    from . import ap_classroom
    from .google_school import load_cache
    today = today or date.today()
    cache = load_cache(cfg)
    groups = {k: [] for k in ("overdue", "today", "tomorrow", "week", "later", "no_date", "done")}
    for item in load(cfg)["items"] + list(cache.get("items") or []) + ap_classroom.items(cfg, today):
        due = date.fromisoformat(item["due"]) if item.get("due") else None
        row = {**item, "label": _label(due, today) if due else ""}
        if item.get("done"):
            if (item.get("done_on") or "") >= (today - timedelta(days=3)).isoformat():
                groups["done"].append(row)
        elif due is None:
            groups["no_date"].append(row)
        elif due < today:
            groups["overdue"].append(row)
        elif due == today:
            groups["today"].append(row)
        elif due == today + timedelta(days=1):
            groups["tomorrow"].append(row)
        elif due <= today + timedelta(days=7):
            groups["week"].append(row)
        else:
            groups["later"].append(row)
    for name, rows in groups.items():
        rows.sort(key=lambda r: (r.get("due") or "9999", r["added"]), reverse=name == "done")
    open_items = sum(len(groups[k]) for k in ("overdue", "today", "tomorrow", "week", "later", "no_date"))
    events = cache.get("events") or {}
    return {"groups": groups, "open": open_items, "ap_open": sum(r["ap"] for k in ("overdue", "today", "tomorrow", "week",
                                                                                  "later", "no_date") for r in groups[k]),
            "missing": sum(1 for r in groups["overdue"] if r.get("source") in ("classroom", "ap")),
            "events": events.get("items") or [] if events.get("date") == today.isoformat() else [],
            "links": {"ap_classroom": AP_CLASSROOM, "classroom": CLASSROOM}}
