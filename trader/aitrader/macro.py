"""
macro.py: the big scheduled economic news, from FRED (the St. Louis Fed's free data service; a free
personal key, saved in Setup). Three events move the whole market:

  CPI (inflation)        8:30am New York time, before the open
  the jobs report        8:30am, before the open (usually the first Friday of the month)
  the Fed's rate decision 2:00pm, during the session (with a press conference at 2:30pm)

Kestrel doesn't avoid these days by rule (the evidence is mixed: the famous pre-Fed rally of Lucca &
Moench, 2015, faded after 2015, and other releases showed no such pattern). It counts down to them in the
Thinking tab and the report, and tags every buy made on those days ("on a CPI day"), so the mistake
memory (mistakes.py) learns from the desk's own results whether those days lose, and then skips them.

The calendar is fetched once a day (FRED's release dates include the scheduled future ones) and saved,
so trading never waits on it; without a key, everything works the same, just without the dates.
"""
import json
from datetime import datetime, timedelta

import requests

from .config import data_path

API = "https://api.stlouisfed.org/fred"
EVENTS = {                     # key: FRED release id, what FRED calls it, plain name, tag word, time (New York)
    "cpi": {"release_id": 10, "expect": "consumer price index", "name": "CPI (inflation)", "tag": "CPI",
            "time": "08:30"},
    "jobs": {"release_id": 50, "expect": "employment situation", "name": "jobs report", "tag": "jobs-report",
             "time": "08:30"},
    "fed": {"release_id": 101, "expect": "fomc", "name": "Fed rate decision", "tag": "Fed-decision",
            "time": "14:00"},
}
FILE = "macro_calendar.json"
KEY_PATTERN = r"[a-z0-9]{32}"
_get = requests.get            # tests don't go online


def has_key(cfg) -> bool:
    return bool((cfg.get("secrets") or {}).get("fred_key"))


def _call(cfg, path: str, **params) -> dict:
    r = _get(f"{API}/{path}", params={"api_key": cfg["secrets"]["fred_key"], "file_type": "json", **params},
             timeout=20)
    if r.status_code != 200:
        try:
            why = r.json().get("error_message") or r.text[:200]
        except ValueError:
            why = r.text[:200]
        raise RuntimeError(f"FRED said {r.status_code}: {why}")
    return r.json()


def release_dates(cfg, release_id: int, today: str, ahead_days: int = 180) -> list:
    """The release's dates from a week ago to `ahead_days` ahead, including scheduled ones with no data yet.
    Newest first with a limit, so it never pages through decades of history."""
    data = _call(cfg, "release/dates", release_id=release_id, realtime_start="1776-07-04",
                 realtime_end="9999-12-31", include_release_dates_with_no_data="true", sort_order="desc", limit=60)
    start = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=ahead_days)).strftime("%Y-%m-%d")
    return sorted({d["date"] for d in data.get("release_dates", []) if start <= d["date"] <= end})


def release_name(cfg, release_id: int) -> str:
    return ((_call(cfg, "release", release_id=release_id).get("releases") or [{}])[0].get("name") or "")


def load(cfg) -> dict:
    path = data_path(cfg, FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def refresh(cfg, today: str, force: bool = False) -> dict:
    """Once a day (the morning check-in): the next dates of each event. A failure keeps the old calendar
    and says why (Setup and the Thinking tab show it)."""
    old = load(cfg)
    if not has_key(cfg) or (old.get("updated") == today and not force and not old.get("error")):
        return old
    events, problems = [], []
    for key, e in EVENTS.items():
        try:
            name = release_name(cfg, e["release_id"])
            if e["expect"] not in name.lower():             # FRED renumbered something: skip, don't mislabel
                problems.append(f"FRED release {e['release_id']} is now '{name}', not the {e['name']}")
                continue
            events += [{"key": key, "date": d} for d in release_dates(cfg, e["release_id"], today)]
        except Exception as ex:
            problems.append(f"{e['name']}: {ex}")
    if not events and problems:
        state = {**old, "error": "; ".join(problems)[:300], "tried": today}
    else:
        state = {"updated": today, "events": sorted(events, key=lambda x: x["date"]),
                 "error": "; ".join(problems)[:300] if problems else None}
    data_path(cfg, FILE).write_text(json.dumps(state))
    return state


def events_on(cfg, day: str) -> list:
    """The event keys on this day, from the saved calendar (no network)."""
    return [e["key"] for e in load(cfg).get("events", []) if e["date"] == day and e["key"] in EVENTS]


def tags(cfg, day: str) -> list:
    """Tags for the buys made on this day (mistakes.py)."""
    return [f"on a {EVENTS[k]['tag']} day" for k in events_on(cfg, day)]


def countdown(now: datetime, when: datetime) -> str:
    minutes = (when - now).total_seconds() / 60
    if minutes < -60:
        return "earlier today" if when.date() == now.date() else "past"
    if minutes < 0:
        return f"{-minutes:.0f} min ago"
    if minutes < 60:
        return f"in {minutes:.0f} min"
    if when.date() == now.date():
        return f"in {int(minutes // 60)}h {int(minutes % 60):02d}m"
    days = (when.date() - now.date()).days
    return "tomorrow" if days == 1 else f"in {days} days"


def upcoming(cfg, now: datetime, days: int = 21) -> list:
    """Today's events and the next ones, soonest first: [{key, name, date, time, label, countdown, today}]."""
    out = []
    for e in load(cfg).get("events", []):
        if e["key"] not in EVENTS:
            continue
        info = EVENTS[e["key"]]
        when = datetime.strptime(f"{e['date']} {info['time']}", "%Y-%m-%d %H:%M")
        if when.date() < now.date() or (when - now).days > days:
            continue
        out.append({"key": e["key"], "name": info["name"], "date": e["date"], "time": info["time"],
                    "label": f"{when:%a %b} {when.day}, {when:%-I:%M%p}".replace("AM", "am").replace("PM", "pm"),
                    "countdown": countdown(now, when), "today": when.date() == now.date()})
    return sorted(out, key=lambda x: (x["date"], x["time"]))


def status(cfg, now: datetime) -> dict:
    cal = load(cfg)
    return {"has_key": has_key(cfg), "updated": cal.get("updated"), "error": cal.get("error"),
            "upcoming": upcoming(cfg, now) if has_key(cfg) else []}


def lines(cfg, now: datetime) -> list:
    """The after-market report's section."""
    if not has_key(cfg):
        return []
    events = upcoming(cfg, now, days=14)
    soon = [e for e in events if not e["today"]]
    today = [e for e in events if e["today"]]
    out = ["## Big economic news (FRED)", ""]
    if today:
        out.append("- Today: " + "; ".join(f"{e['name']} at {e['label'].split(', ')[-1]}" for e in today)
                   + ". Buys today are tagged, so the mistake memory learns if these days lose.")
    out.append("- Coming up: " + ("; ".join(f"{e['name']} {e['label']} ({e['countdown']})" for e in soon[:4])
                                  or "nothing in the next two weeks"))
    if load(cfg).get("error"):
        out.append(f"- Note: {load(cfg)['error']}")
    return out + [""]
