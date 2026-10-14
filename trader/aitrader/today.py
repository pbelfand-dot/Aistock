"""
today.py: the Today screen, the first thing you see when Kestrel opens (docs/DASHBOARD-PLAN.md).

  - school:  what's due (school.py: your quick-add list, Google Classroom through google_school.py, and the pages
             read in Kestrel's browser, school_web.py), and today's calendar events
  - the bot: whether the autopilot ran through the last trading day, the next big economic news, and the
             last after-market report's summary (the account value and each desk come from the snapshot the
             page already has)
  - open at login: on or off (mac_service.py)

It only reads; the trading itself never waits for it.
"""
import re
from datetime import date, datetime, timedelta

from .config import data_path


def greeting(hour: int) -> str:
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"


def _minutes(gap: dict) -> int:
    start, end = (datetime.strptime(gap[k], "%H:%M") for k in ("from", "to"))
    return max(0, int((end - start).total_seconds() // 60))


def _duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes} min"


def last_trading_day(today: date) -> date:
    from .settlement import market_holidays
    day = today - timedelta(days=1)
    while day.weekday() >= 5 or day in market_holidays(day.year):
        day -= timedelta(days=1)
    return day


_GAP_LINE = re.compile(r"Not running from (\d\d:\d\d) to (\d\d:\d\d)")


def gaps_in_report(text: str) -> list:
    """The stretches the autopilot wasn't running, as the after-market report lists them (report.gap_lines)."""
    return [{"from": m.group(1), "to": m.group(2),
             "missed": ["the swing desk's daily decision"] if "swing desk's daily decision" in line else []}
            for line in text.splitlines() for m in [_GAP_LINE.search(line)] if m]


def uptime(cfg, store, today: date) -> dict:
    """Was the autopilot running during market hours: today so far, and the last trading day (run.note_gap
    writes down each stretch it wasn't; for a day before that, its after-market report lists them). No gaps and no
    report for a day means there's no record of it at all."""
    by_day = dict(store.get("autopilot_gaps_by_day") or {})
    live = store.get("autopilot_gaps") or {}
    if live.get("day"):
        by_day.setdefault(live["day"], live.get("items") or [])

    def day_line(day: date, so_far: bool) -> dict:
        path = data_path(cfg, f"reports/after-market-{day.isoformat()}.md")
        report = path.exists()
        if day.isoformat() in by_day:
            gaps = by_day[day.isoformat()] or []
        else:
            try:
                gaps = gaps_in_report(path.read_text()) if report else []
            except OSError:
                gaps = []
        missed_swing = any("swing" in m for g in gaps for m in g.get("missed") or [])
        off = sum(_minutes(g) for g in gaps)
        if gaps:
            text = (f"off {len(gaps)} time{'s' if len(gaps) != 1 else ''} during market hours ({_duration(off)} in all)"
                    + ("; it missed the swing desk's 3:45 decision" if missed_swing else ""))
        elif so_far:
            text = "running all day so far"
        elif report:
            text = "ran all through market hours"
        else:
            text = "no record of it running (was the Mac off?)"
        return {"day": day.isoformat(), "label": f"{day:%a %b} {day.day}", "gaps": gaps, "off_minutes": off,
                "missed_swing": missed_swing, "ok": not gaps and (so_far or report), "text": text}
    from .settlement import market_holidays
    trading_today = today.weekday() < 5 and today not in market_holidays(today.year)
    return {"today": day_line(today, True) if trading_today else None,
            "last": day_line(last_trading_day(today), False)}


_MATH = {r"\ge": "≥", r"\geq": "≥", r"\le": "≤", r"\leq": "≤", r"\times": "×", r"\approx": "≈", r"\sim": "~"}


def plain(text: str) -> str:
    """The local AI sometimes writes math like "$\\ge$ 0.8": shown as plain symbols."""
    text = re.sub(r"\$\s*(\\[a-z]+)\s*\$", lambda m: _MATH.get(m.group(1), m.group(1).lstrip("\\")), str(text))
    return text.replace("**", "").replace("`", "")


def report_summary(cfg) -> dict:
    """The latest after-market report: its day, and its "In plain English" points (or none)."""
    from .report import recent_reports
    try:
        reports = recent_reports(cfg, 1)
    except OSError:
        reports = []
    if not reports:
        return {}
    text, points = reports[0]["markdown"], []
    part = re.search(r"^## In plain English\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if part:
        points = [plain(line.strip()[2:].strip()) for line in part.group(1).splitlines() if line.strip().startswith(("- ", "* "))]
    day = date.fromisoformat(reports[0]["date"])
    return {"date": reports[0]["date"], "label": f"{day:%A %b} {day.day}", "points": points[:6]}


def next_news(cfg, now: datetime) -> list:
    from . import macro
    try:
        return macro.upcoming(cfg, now)[:2] if macro.has_key(cfg) else []
    except Exception:
        return []


def overview(cfg, store, now: datetime = None, school_cfg: dict = None) -> dict:
    """school_cfg: whose homework list (yours, also while the demo's made-up trading data is showing)."""
    from . import mac_service, school
    from .market_hours import now_ny
    now = now or datetime.now()
    today = now.date()
    from . import google_school, school_web
    return {"date": f"{now:%A, %B} {now.day}", "greeting": greeting(now.hour),
            "school": school.summary(school_cfg or cfg, today),
            "google": google_school.status(school_cfg or cfg, now),
            "web": school_web.status(school_cfg or cfg, now),
            "uptime": uptime(cfg, store, today),
            "news": next_news(cfg, now_ny()),
            "report": report_summary(cfg),
            "open_at_login": mac_service.open_at_login()}
