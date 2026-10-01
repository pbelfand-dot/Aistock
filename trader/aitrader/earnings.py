"""
earnings.py: don't open a swing position right before the company reports earnings.

A report can make a stock jump or drop 10-20% overnight, straight past a 7% stop-loss (a stop can't sell
in the middle of the night; it sells at the next open, wherever that is). So the swing desk doesn't BUY a
stock whose next earnings report is within `days_before` trading days. Stocks it already owns are kept
(their stops still work), and the day desk doesn't need this: it never holds overnight.

Honest note: this is about avoiding big surprise losses, not about making more. On average, stocks
have actually done a bit BETTER around their earnings reports (Frazzini & Lamont 2007 measured over 7% a
year; later studies find that premium has shrunk). Skipping them gives up some of that for fewer gaps.

The dates come from Yahoo Finance (free, no key), looked up once a day each morning for the swing desk's
stocks. A stock with no known date (ETFs have none) is never held back by this.
"""
import json
import socket
from datetime import date, datetime, timedelta

import pandas as pd

from .config import data_path

FILE = "earnings.json"


def settings(cfg: dict) -> dict:
    s = {"enabled": True, "days_before": 3, "desks": ["swing"]}
    s.update(cfg.get("earnings") or {})
    return s


def is_on(cfg: dict, desk: str) -> bool:
    from .scanner import is_on as on
    s = settings(cfg)
    return on(s["enabled"]) and desk in (s.get("desks") or [])


def _from_yahoo(ticker: str, today: str):
    """The next earnings date on or after today (YYYY-MM-DD), or None."""
    import yfinance as yf
    t = yf.Ticker(ticker.replace(".", "-"))
    found = []
    cal = t.calendar
    if isinstance(cal, dict):
        found = list(cal.get("Earnings Date") or [])
    elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
        found = list(cal.loc["Earnings Date"].dropna())
    if not found:
        try:
            frame = t.get_earnings_dates(limit=8)
            found = list(frame.index) if frame is not None else []
        except Exception:
            found = []
    days = sorted({pd.Timestamp(d).date().isoformat() for d in found if d is not None and not pd.isna(d)})
    return next((d for d in days if d >= today), None)


def _load(cfg) -> dict:
    path = data_path(cfg, FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def next_dates(cfg: dict, tickers, today: str, fetch=None, limit: int = 120) -> dict:
    """{ticker: next earnings date or None}, looked up once a day (kept in data/earnings.json)."""
    fetch = fetch or _from_yahoo
    saved = _load(cfg)
    known = saved.get("dates", {}) if saved.get("day") == today else {}
    missing = [t for t in dict.fromkeys(tickers) if t not in known][:limit]
    if missing:
        before = socket.getdefaulttimeout()
        socket.setdefaulttimeout(10)                    # a slow website never stalls the bot
        try:
            for t in missing:
                try:
                    known[t] = fetch(t, today)
                except Exception:
                    known[t] = None                     # unknown: never holds a stock back
        finally:
            socket.setdefaulttimeout(before)
        path = data_path(cfg, FILE)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"day": today, "dates": known}, indent=1))
        tmp.replace(path)
    return {t: known.get(t) for t in tickers}


def trading_days_until(today: str, day: str) -> int:
    """Weekdays from today to that day (0 = today, -1 = already past)."""
    a, b = date.fromisoformat(today), date.fromisoformat(day)
    if b < a:
        return -1
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def soon(cfg: dict, tickers, today: str, fetch=None, limit: int = 120) -> dict:
    """{ticker: earnings date} for those reporting within days_before trading days (today included)."""
    window = int(settings(cfg)["days_before"])
    dates = next_dates(cfg, tickers, today, fetch=fetch, limit=limit)
    return {t: d for t, d in dates.items() if d and 0 <= trading_days_until(today, d) <= window}


def cached(cfg: dict, ticker: str):
    """The next earnings date if it was looked up today or recently (no new lookup)."""
    d = (_load(cfg).get("dates") or {}).get(ticker)
    return d if d and d >= datetime.now().strftime("%Y-%m-%d") else None
