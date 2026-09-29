"""
market_hours.py: when is the US stock market open?

Regular hours are 9:30am-4:00pm New York time, Monday-Friday. Three days a
year it closes early, at 1:00pm:
  * the day after Thanksgiving
  * July 3 (when it's a Monday-Thursday)
  * Christmas Eve (when it's a Monday-Thursday)
Full holidays need no list: on those days no new prices show up, and the bot
treats "no prices today" as "closed".
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
OPEN = time(9, 30)


def now_ny() -> datetime:
    return datetime.now(NEW_YORK).replace(tzinfo=None)


def thanksgiving(year: int) -> date:
    nov1 = date(year, 11, 1)
    first_thursday = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thursday + timedelta(weeks=3)


def is_early_close(day: date) -> bool:
    if day == thanksgiving(day.year) + timedelta(days=1):
        return True
    return (day.month, day.day) in {(7, 3), (12, 24)} and day.weekday() <= 3


def session_close(day: date) -> time:
    return time(13, 0) if is_early_close(day) else time(16, 0)


def minutes_to_close(ts: datetime) -> float:
    close = datetime.combine(ts.date(), session_close(ts.date()))
    return (close - ts).total_seconds() / 60


def in_session(ts: datetime) -> bool:
    return ts.weekday() < 5 and OPEN <= ts.time() < session_close(ts.date())
