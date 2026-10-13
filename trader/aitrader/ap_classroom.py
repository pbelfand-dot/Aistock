"""
ap_classroom.py: AP Classroom on the Today screen.

College Board offers no way for other apps to read AP Classroom, so Kestrel does what you'd do yourself. Its Mac
window opens AP Classroom in a window of its own (mac/app/apclassroom.swift); you sign in to College Board once
(that window remembers you, like Safari), open a page that lists your AP assignments and press "Use this page for
Today". This file reads the page's visible text: each assignment, its due date and its status. Later the window
re-reads the same pages by itself, out of sight, when the Today screen opens (at most every 2 hours).
It only ever reads text: it never clicks, starts or submits anything.

The page's layout isn't documented anywhere, so the reader looks for two shapes:
  - a table with a "Due" column (AP Classroom's assignments list: title, start, due, status); "Now Open" means no
    due date;
  - assignment cards: a title, then a line like "Due Oct 17, 2026, 11:59 PM", and a status nearby (Not started,
    In Progress, Complete, Awaiting scoring...).
If it finds nothing on a page that clearly lists assignments, that page's layout is new to it: a screenshot of the
page is all it takes to teach it.

Saved on this Mac only: data/ap_classroom.json (per page: what it found and when).
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta

from .config import data_path

FILE = "ap_classroom.json"
STALE_MINUTES = 120                 # the Today screen asks the window to re-read after this
KEEP_DAYS_BACK, KEEP_DAYS_AHEAD = 21, 60
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
DATE = re.compile(r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
                  r"(?:,?\s+(?P<year>\d{4}))?"
                  r"|\b(?P<m>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<y>\d{2,4}))?\b"
                  r"|\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})\b", re.I)
TIME = re.compile(r"\b(?P<h>\d{1,2}):(?P<mi>\d{2})\s*(?P<ap>[ap])\.?\s?m\b\.?", re.I)
STATUS = re.compile(r"\b(not started|in progress|completed?|submitted|scored|awaiting scoring|past due|missing|"
                    r"now open|closed|turned in|graded)\b", re.I)
DONE = re.compile(r"\b(completed?|submitted|scored|awaiting scoring|turned in|graded)\b", re.I)
SIGN_IN = re.compile(r"\bsign in\b|\blog in\b|forgot (your )?(password|username)|create (an )?account", re.I)
NOT_TITLES = {"start", "view", "open", "resume", "begin", "review", "results", "assigned", "due", "status", "score",
              "assignments", "assignment", "my assignments", "to do", "to-do", "details", "go", "continue", "more"}
COURSE = re.compile(r"\bAP[ \t]+(?:[A-Z][A-Za-z&.']*[ \t]?){1,6}")
NOT_COURSES = {"classroom", "central", "calendar", "daily", "students", "student", "scores", "exam", "exams", "course",
               "courses", "home", "program", "services", "coordinator"}


def find_date(text: str, today: date) -> tuple:
    """(the date, "11:59pm" or "") in a piece of text like "Oct 17, 2026, 11:59 PM", "10/17/2026" or "tomorrow"."""
    text = str(text or "")
    found = DATE.search(text)
    clock = TIME.search(text[found.end():] if found else text)
    at = ""
    if clock:
        hour = int(clock["h"]) % 12 + (12 if clock["ap"].lower() == "p" else 0)
        at = datetime(2000, 1, 1, hour, int(clock["mi"])).strftime("%-I:%M%p").lower()
    if not found:
        low = text.lower()
        if re.search(r"\btoday\b", low):
            return today, at
        if re.search(r"\btomorrow\b", low):
            return today + timedelta(days=1), at
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


def _title_like(line: str) -> bool:
    s = line.strip(" \t-–—|·:•")
    return (3 <= len(s) <= 200 and s.lower() not in NOT_TITLES and not STATUS.fullmatch(s)
            and not re.match(r"(due|start|assigned|opens?|closes?)\b", s, re.I)
            and not (DATE.search(s) and len(DATE.sub("", s).strip(" ,.:")) < 4))


def course_name(text: str, title: str) -> str:
    """The AP class a page is about ("AP United States History"), from its title or text; not College Board's own
    names like AP Classroom or AP Calendar."""
    for source in (title, text):
        for found in COURSE.finditer(str(source or "")):
            name = re.sub(r"[ \t]+(Assignments?|Classroom|Home|Course)\b.*$", "", found.group(0).strip())
            words = name.split()
            if len(words) > 1 and words[1].lower() not in NOT_COURSES:
                return name
    return "AP Classroom"


def parse(text: str, title: str, today: date) -> dict:
    """{"items": [{title, due, due_time, status, done}], "course", "signed_out"} from a page's visible text."""
    lines = [l.rstrip() for l in str(text or "").splitlines()]
    found = []
    # 1. a table with a "Due" column: AP Classroom's assignments list
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
                hit = STATUS.search(row)
                status = hit.group(0) if hit else ""
            if due or "now open" in cols[due_col].lower():
                found.append({"title": cols[title_col], "due": due, "due_time": at, "status": status})
    # 2. assignment cards: a line with "Due <date>", its title just before it, a status nearby
    if not found:
        for i, line in enumerate(lines):
            hit = re.search(r"\bdue\b[:\s]*(.*)", line, re.I)
            if not hit:
                continue
            due, at = find_date(hit.group(1), today)
            if not due:
                continue
            before = line[:hit.start()].strip(" \t-–—|·:•,")
            name = before if _title_like(before) else next(
                (lines[j].strip() for j in range(i - 1, max(-1, i - 5), -1) if _title_like(lines[j])), "")
            if not name:
                continue
            after = []                                           # its status: after the due line, before the next card
            for j in range(i + 1, min(len(lines), i + 4)):
                if re.search(r"\bdue\b", lines[j], re.I):
                    break
                after.append(lines[j])
            state = STATUS.search(" ".join(after)) or STATUS.search(line)
            found.append({"title": name.strip(" \t-–—|·:•"), "due": due, "due_time": at,
                          "status": state.group(0) if state else ""})
    items, seen = [], set()
    for f in found:
        key = (f["title"].lower(), f["due"])
        if key in seen:
            continue
        seen.add(key)
        status = f["status"].strip().lower()
        items.append({**f, "status": "" if status == "now open" else status, "done": bool(DONE.search(status))})
    return {"items": items, "course": course_name(text, title),
            "signed_out": not items and bool(SIGN_IN.search(str(text or "")))}


# ------------------------------------------------------------------ the saved pages
def load(cfg) -> dict:
    path = data_path(cfg, FILE)
    try:
        state = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        state = {}
    state.setdefault("pages", {})
    return state


def _save_state(cfg, state: dict):
    path = data_path(cfg, FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, default=str))
    tmp.replace(path)


def save(cfg, url: str, title: str, text: str, auto: bool = False, now: datetime = None) -> dict:
    """A page's text from the AP Classroom window: what's on it, kept for the Today screen. auto = the window
    re-reading a saved page by itself (a sign-in page then keeps the last assignments, marked "sign in again")."""
    url = str(url or "").strip()
    if not re.match(r"https://([a-z0-9-]+\.)*collegeboard\.org/", url):
        raise ValueError("That isn't an AP Classroom page (collegeboard.org). Open your assignments page in the AP "
                         "Classroom window first.")
    now = now or datetime.now()
    today = now.date()
    result = parse(text, title, today)
    state = load(cfg)
    old = state["pages"].get(url) or {}
    page = {"title": str(title or "")[:200], "course": result["course"], "signed_out": result["signed_out"],
            "updated": now.isoformat(timespec="seconds"), "found": len(result["items"]),
            "items": [{**i, "due": i["due"].isoformat() if i["due"] else None} for i in result["items"]]}
    if result["signed_out"]:
        page.update(items=old.get("items") or [], found=old.get("found", 0))   # keep what it knew; say sign in again
    if auto and not old:
        return {"ok": False, "message": "That page isn't one of the pages chosen for Today."}
    state["pages"][url] = page
    _save_state(cfg, state)
    names = ", ".join(i["title"] for i in result["items"][:3]) + ("…" if len(result["items"]) > 3 else "")
    if result["signed_out"]:
        message = "This looks like College Board's sign-in page: sign in first, then open your assignments page."
    elif not result["items"]:
        message = ("Kestrel didn't find assignments with due dates on this page. Open the page that lists your AP "
                   "assignments and their due dates, then press Use this page for Today again. If it still finds none, "
                   "send a screenshot of that page so Kestrel can learn its layout.")
    else:
        message = f"Found {len(result['items'])} AP assignment{'s' if len(result['items']) != 1 else ''} ({names}): they're on Today."
    return {"ok": bool(result["items"]), "message": message, "found": len(result["items"]), "course": result["course"]}


def pages(cfg) -> list:
    return list(load(cfg)["pages"])


def forget(cfg) -> str:
    data_path(cfg, FILE).unlink(missing_ok=True)
    return "Kestrel forgot your AP Classroom pages (the AP window stays signed in to College Board until you sign out there)."


def items(cfg, today: date) -> list:
    """The AP assignments for the Today list (school.summary): due in the last 3 weeks or next 2 months, or with no
    due date yet; finished ones only while recent."""
    out = []
    for url, page in load(cfg)["pages"].items():
        for i in page.get("items") or []:
            due = date.fromisoformat(i["due"]) if i.get("due") else None
            if due and not (today - timedelta(days=KEEP_DAYS_BACK) <= due <= today + timedelta(days=KEEP_DAYS_AHEAD)):
                continue
            if i.get("done") and (not due or due < today - timedelta(days=3)):
                continue
            status = "missing" if due and due < today and not i.get("done") else i.get("status") or ""
            key = hashlib.sha1(f"{url}|{i['title']}|{i.get('due')}".encode()).hexdigest()[:12]
            out.append({"id": f"ap-{key}", "title": i["title"], "course": page.get("course") or "AP Classroom",
                        "due": i.get("due"), "due_time": i.get("due_time", ""), "ap": True, "done": bool(i.get("done")),
                        "done_on": i.get("due") if i.get("done") else None, "added": page.get("updated", ""),
                        "source": "ap", "status": status, "link": url})
    return out


def status(cfg, now: datetime = None) -> dict:
    now = now or datetime.now()
    saved = load(cfg)["pages"]
    times = [datetime.fromisoformat(p["updated"]) for p in saved.values() if p.get("updated")]
    age = (now - min(times)).total_seconds() / 60 if times else None
    return {"pages": len(saved), "found": sum(p.get("found", 0) for p in saved.values()),
            "courses": sorted({p.get("course") or "AP Classroom" for p in saved.values()}),
            "signed_out": any(p.get("signed_out") for p in saved.values()),
            "minutes_ago": round(age) if age is not None else None,
            "stale": bool(saved) and (age is None or age >= STALE_MINUTES)}
