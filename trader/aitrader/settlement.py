"""
settlement.py: when does the money from a sale become "settled"?

US stocks and ETFs settle T+1: one business day after the trade. A business day here means the
stock market is open AND the banks are open. On Columbus Day and Veterans Day the market trades,
but banks (the Federal Reserve) are closed, so nothing settles.

Why it matters (cash accounts, like a Schwab cash account): buying with money that hasn't settled
yet, then selling that stock before the money settles, is a GOOD FAITH VIOLATION. Three in 12
months and Schwab restricts the account to settled cash for 90 days. The bot never buys with
unsettled money, so its sales can never cause one (see brokers/base.py).

When in doubt this calendar says "not settled yet": waiting a day costs nothing, a violation does.
"""
from datetime import date, timedelta
from functools import lru_cache


def _nth_weekday(year, month, weekday, n):          # weekday: Monday=0; n=-1 means the last one
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year):                                   # Gregorian Easter (Anonymous algorithm)
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_observed(d):                               # Saturday -> Friday before, Sunday -> Monday after
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def _fed_observed(d):                                # the Fed moves only Sunday holidays (to Monday)
    return d + timedelta(days=1) if d.weekday() == 6 else d


@lru_cache(maxsize=None)
def market_holidays(year: int) -> frozenset:
    """Days the NYSE is closed (full days)."""
    days = {_nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3), _easter(year) - timedelta(days=2),
            _nth_weekday(year, 5, 0, -1), _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 11, 3, 4)}
    for month, day in ((7, 4), (12, 25)) + (((6, 19),) if year >= 2022 else ()):
        days.add(_nyse_observed(date(year, month, day)))
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:                      # NYSE doesn't close Dec 31 for a Saturday Jan 1
        days.add(_nyse_observed(new_year))
    return frozenset(days)


@lru_cache(maxsize=None)
def bank_holidays(year: int) -> frozenset:
    """Federal Reserve holidays: no settlement."""
    days = {_nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3), _nth_weekday(year, 5, 0, -1),
            _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 10, 0, 2), _nth_weekday(year, 11, 3, 4)}
    for month, day in ((1, 1), (7, 4), (11, 11), (12, 25)) + (((6, 19),) if year >= 2021 else ()):
        days.add(_fed_observed(date(year, month, day)))
    return frozenset(days)


def is_settlement_day(d: date) -> bool:
    return d.weekday() < 5 and d not in market_holidays(d.year) and d not in bank_holidays(d.year)


def settles_on(trade_day) -> str:
    """The date (YYYY-MM-DD) a trade made on trade_day settles: the next settlement day (T+1)."""
    d = date.fromisoformat(str(trade_day)[:10]) + timedelta(days=1)
    while not is_settlement_day(d):
        d += timedelta(days=1)
    return d.isoformat()
