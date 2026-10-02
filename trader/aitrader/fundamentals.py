"""
fundamentals.py: three facts about a company beyond its price, all free. They feed the momentum_quality
challenger (which must prove itself before it trades: challengers.py) and each stock's card.

  quality         gross profits divided by total assets (Novy-Marx 2013, "The other side of value"):
                  companies that earn more per dollar of assets have earned higher returns. From the SEC's
                  XBRL "frames" (one file per figure per year holds every company), back to 2017; a year's
                  numbers count from 90 days after it ended (by then the annual report is out). Ranked
                  against every US company that reports them. Banks and funds have no gross profit: no
                  opinion on them.
  insider buys    an officer or director buying the company's stock on the open market (Form 4, code P),
                  not under a pre-planned 10b5-1 schedule. Insiders sell for many reasons but buy for one
                  (Lakonishok & Lee 2001; Cohen, Malloy & Pomorski 2012: the unplanned trades carry the
                  information). Read from the Form 4s in the SEC filings Kestrel already checks every 30
                  minutes; collected from now on.
  short interest  shares sold short and days to cover (shares short divided by average daily volume), from
                  Yahoo Finance (FINRA's twice-monthly numbers). Heavily shorted stocks have done worse on
                  average (Boehmer, Huszar & Jordan 2010; Hong, Li, Ni, Scheinkman & Yan 2015 on days to
                  cover). Saved once a day, so its history builds from now on.

All of it needs the SEC contact email (Setup → AI & news) except short interest. Trading never waits on
it: everything is fetched in the background and read from the saved files.
"""
import json
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import data_path

FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{period}.json"
GROSS, REVENUE, COST = ("GrossProfit",), ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"), \
    ("CostOfRevenue", "CostOfGoodsAndServicesSold")
FIRST_YEAR = 2017
LAG_DAYS = 90                    # a year's numbers count from 90 days after it ended
STALE_DAYS = 550                 # a company that stopped reporting: its old number stops counting
INSIDER_DAYS = 30                # an insider buy counts for 30 days after it was filed
HEAVY_DAYS_TO_COVER, HEAVY_SHORT_PCT = 8.0, 20.0
QUALITY_FILE, INSIDER_FILE, SHORT_FILE = "fundamentals/quality.json", "fundamentals/insiders.json", \
    "fundamentals/short_interest.json"
_running = None


def _load(cfg, name) -> dict:
    path = data_path(cfg, name)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(cfg, name, value):
    data_path(cfg, name).write_text(json.dumps(value))


def saved_ciks(cfg) -> dict:
    """{ticker: CIK} from the SEC's list Kestrel already saved (no network)."""
    return _load(cfg, "sec/company_tickers.json").get("map") or {}


# ---------------------------------------------------------------- quality (gross profits / assets)
def _frame(cfg, concept: str, period: str, refresh: bool) -> dict:
    """{cik: [end, value]}: one figure for every company that reported it for that period (cached)."""
    from .sec_filings import _fetch
    name = f"fundamentals/frames/{concept}_{period}.json"
    path = data_path(cfg, name)
    if path.exists() and not refresh:
        return _load(cfg, name)
    data = _fetch(cfg, FRAMES_URL.format(concept=concept, period=period))
    out = {str(d["cik"]): [d.get("end"), d.get("val")] for d in (data or {}).get("data", [])
           if d.get("cik") is not None and d.get("val") is not None}
    _save(cfg, name, out)
    return out


def quality_year(gross: dict, revenue: list, cost: list, assets: dict) -> dict:
    """{cik: [end, gross profit / assets, percentile among all companies]} for one year. Gross profit as
    reported, or revenue minus cost of revenue (the first figure each company reports)."""
    values = {}
    for cik, (_, total) in assets.items():
        if not total or total <= 0:
            continue
        if cik in gross:
            end, profit = gross[cik]
        else:
            rev = next((r[cik] for r in revenue if cik in r), None)
            cst = next((c[cik] for c in cost if cik in c), None)
            if not rev or not cst:
                continue
            end, profit = rev[0], rev[1] - cst[1]
        values[cik] = (end, profit / total)
    if not values:
        return {}
    pct = pd.Series({c: v[1] for c, v in values.items()}).rank(pct=True)
    return {c: [v[0], round(float(v[1]), 4), round(float(pct[c]), 3)] for c, v in values.items()}


def refresh_quality(cfg, today: str) -> dict:
    """Every company's gross profits / assets for each year since 2017. Past years are fetched once;
    the last two again each week (late filers, corrections)."""
    year_now = int(today[:4])
    saved = _load(cfg, QUALITY_FILE)
    fresh = saved.get("updated", "") >= (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    if fresh and saved.get("years"):
        return saved
    years = dict(saved.get("years") or {})
    for y in range(FIRST_YEAR, year_now):
        refresh = y >= year_now - 2
        if str(y) in years and not refresh:
            continue
        period = f"CY{y}"
        row = quality_year(_frame(cfg, GROSS[0], period, refresh),
                           [_frame(cfg, c, period, refresh) for c in REVENUE],
                           [_frame(cfg, c, period, refresh) for c in COST],
                           _frame(cfg, "Assets", f"{period}Q4I", refresh))
        if row:
            years[str(y)] = row
    out = {"updated": today, "years": years}
    _save(cfg, QUALITY_FILE, out)
    return out


def quality_points(cfg, ticker: str, ciks: dict = None, years: dict = None) -> list:
    """[(counts from, percentile, ratio, year end)] for one stock, oldest first."""
    cik = str((ciks if ciks is not None else saved_ciks(cfg)).get(ticker.upper().replace(".", "-")) or "")
    if not cik:
        return []
    years = years if years is not None else (_load(cfg, QUALITY_FILE).get("years") or {})
    out = []
    for y, row in years.items():
        if cik in row:
            end, ratio, pct = row[cik]
            start = (pd.Timestamp(end or f"{y}-12-31") + pd.Timedelta(days=LAG_DAYS))
            out.append((start, pct, ratio, end))
    return sorted(out)


def _as_of(points: list, index: pd.DatetimeIndex, value_at: int, stale_days: int) -> np.ndarray:
    """The latest point's value known at each time (NaN before the first, or once it's too old)."""
    out = np.full(len(index), np.nan)
    if not points:
        return out
    starts = pd.DatetimeIndex([p[0] for p in points])
    pos = starts.searchsorted(index, side="right") - 1
    ok = pos >= 0
    vals = np.array([p[value_at] for p in points], dtype=float)
    out[ok] = vals[pos[ok]]
    age = (index - starts[np.clip(pos, 0, None)]).days
    out[ok & (np.asarray(age) > stale_days)] = np.nan
    return out


def quality_table(cfg, tickers: list, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Each stock's quality percentile (0-1, among all US companies) as known at each time."""
    ciks, years = saved_ciks(cfg), _load(cfg, QUALITY_FILE).get("years") or {}
    return pd.DataFrame({t: _as_of(quality_points(cfg, t, ciks, years), index, 1, STALE_DAYS) for t in tickers},
                        index=index)


# ---------------------------------------------------------------- insider buys (Form 4)
def _yes(text) -> bool:
    return str(text or "").strip().lower() in ("1", "true", "y", "yes")


def form4_buys(xml_text: str) -> list:
    """Open-market purchases (code P) by an officer or director in one Form 4, unless it says the trade was
    made under a 10b5-1 plan: [{date, shares, price, value, who}]."""
    try:
        root = ET.fromstring(xml_text.strip().encode())
    except ET.ParseError:
        return []
    find = lambda node, path: (node.findtext(path) or "").strip() if node is not None else ""
    planned = any("10b5" in el.tag.lower() and _yes(el.text) for el in root.iter())
    owners = root.findall("reportingOwner")
    insiders = [o for o in owners if _yes(find(o, "reportingOwnerRelationship/isOfficer"))
                or _yes(find(o, "reportingOwnerRelationship/isDirector"))]
    if planned or not insiders:
        return []
    o = insiders[0]
    title = find(o, "reportingOwnerRelationship/officerTitle") or \
        ("director" if _yes(find(o, "reportingOwnerRelationship/isDirector")) else "officer")
    who = f"{find(o, 'reportingOwnerId/rptOwnerName')} ({title})"
    out = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        if find(tx, "transactionCoding/transactionCode") != "P":
            continue
        try:
            shares = float(find(tx, "transactionAmounts/transactionShares/value") or 0)
            price = float(find(tx, "transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        out.append({"date": find(tx, "transactionDate/value")[:10], "shares": shares, "price": price,
                    "value": round(shares * price, 2), "who": who})
    return out


def update_insiders(cfg, ticker: str, cik: int, submissions: dict, now: datetime, limit: int = 20) -> list:
    """Reads the company's Form 4s of the last 30 days that it hasn't read yet (from the SEC filings check).
    Returns the new insider buys found."""
    from .sec_filings import _fetch_text
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    cutoff = (now - timedelta(days=INSIDER_DAYS)).strftime("%Y-%m-%d")
    state = _load(cfg, INSIDER_FILE)
    seen, buys = state.get("seen") or {}, state.get("buys") or []
    found = []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        get = lambda key: (recent.get(key) or [""] * len(forms))[i] or ""
        filed, accession = get("filingDate"), get("accessionNumber")
        if filed < cutoff or not accession or accession in seen:
            continue
        if limit <= 0:
            break
        limit -= 1
        doc = re.sub(r"^xsl[^/]*/", "", get("primaryDocument"))       # the raw XML, not the styled page
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}"
        seen[accession] = filed
        for b in form4_buys(_fetch_text(cfg, url)):
            found.append({**b, "ticker": ticker, "filed": filed, "url": url})
    keep = (now - timedelta(days=400)).strftime("%Y-%m-%d")
    _save(cfg, INSIDER_FILE, {"seen": {a: d for a, d in seen.items() if d >= keep},
                              "buys": [b for b in buys + found if b["filed"] >= keep]})
    return found


def insider_buys(cfg, ticker: str = None) -> list:
    buys = _load(cfg, INSIDER_FILE).get("buys") or []
    return [b for b in buys if ticker is None or b["ticker"] == ticker]


def insider_table(cfg, tickers: list, index: pd.DatetimeIndex) -> pd.DataFrame:
    """True where an insider buy was filed in the 30 days up to that time."""
    out = {}
    buys = insider_buys(cfg)
    for t in tickers:
        filed = pd.DatetimeIndex(sorted({pd.Timestamp(b["filed"]) for b in buys if b["ticker"] == t}))
        if not len(filed):
            out[t] = np.zeros(len(index), dtype=bool)
            continue
        pos = filed.searchsorted(index.normalize(), side="right") - 1
        age = (index.normalize() - filed[np.clip(pos, 0, None)]).days
        out[t] = (pos >= 0) & (np.asarray(age) <= INSIDER_DAYS)
    return pd.DataFrame(out, index=index)


# ---------------------------------------------------------------- short interest
def _from_yahoo(ticker: str) -> dict:
    import yfinance as yf
    info = yf.Ticker(ticker.replace(".", "-")).info or {}
    when = info.get("dateShortInterest")
    pct = info.get("shortPercentOfFloat")
    return {"days_to_cover": info.get("shortRatio"), "short_pct_float": round(pct * 100, 2) if pct else None,
            "shares_short": info.get("sharesShort"),
            "as_of": datetime.fromtimestamp(when, tz=timezone.utc).strftime("%Y-%m-%d")
            if isinstance(when, (int, float)) else None}


def refresh_short_interest(cfg, tickers: list, today: str, fetch=None) -> dict:
    """Once a day: each stock's latest short interest, saved with the day it was seen."""
    fetch = fetch or _from_yahoo
    state = _load(cfg, SHORT_FILE)
    for t in tickers:
        rows = state.get(t) or []
        if rows and rows[-1]["seen"] == today:
            continue
        try:
            row = fetch(t)
        except Exception:
            continue
        if row.get("days_to_cover") is None and row.get("short_pct_float") is None:
            continue                                     # funds and some stocks have none
        state[t] = (rows + [{**row, "seen": today}])[-400:]
    _save(cfg, SHORT_FILE, state)
    return state


def heavily_shorted(row: dict) -> bool:
    return bool(row) and ((row.get("days_to_cover") or 0) >= HEAVY_DAYS_TO_COVER
                          or (row.get("short_pct_float") or 0) >= HEAVY_SHORT_PCT)


def short_table(cfg, tickers: list, index: pd.DatetimeIndex) -> pd.DataFrame:
    """True where the latest short interest seen by then says heavily shorted."""
    state = _load(cfg, SHORT_FILE)
    out = {}
    for t in tickers:
        points = [(pd.Timestamp(r["seen"]), 1.0 if heavily_shorted(r) else 0.0) for r in state.get(t) or []]
        out[t] = _as_of(points, index.normalize(), 1, 30) == 1.0
    return pd.DataFrame(out, index=index)


# ---------------------------------------------------------------- refresh, and the stock card
def refresh(cfg, tickers: list, today: str) -> str:
    """The morning refresh (in the background): quality (weekly) and short interest (daily)."""
    from . import sec_filings
    done = []
    if sec_filings.is_on(cfg):
        sec_filings.cik_map(cfg, today)
        q = refresh_quality(cfg, today)
        done.append(f"quality for {sum(len(r) for r in (q.get('years') or {}).values()):,} company-years")
    s = refresh_short_interest(cfg, tickers, today)
    done.append(f"short interest for {sum(1 for t in tickers if s.get(t))} stocks")
    return "; ".join(done)


def refresh_in_background(cfg, store, tickers: list, today: str, inline: bool = False):
    global _running
    if _running is not None and _running.is_alive():
        return

    def work():
        try:
            refresh(cfg, tickers, today)
        except Exception as e:
            _save(cfg, "fundamentals/error.json", {"day": today, "error": repr(e)[:200]})
    if inline:
        work()
        return
    _running = threading.Thread(target=work, daemon=True, name="fundamentals")
    _running.start()


def tags(cfg, tickers: list, day: str) -> dict:
    """{ticker: short plain-English facts} as known on `day`, for the team's notes and the mistake memory
    (mistakes.py learns whether buys like "heavily shorted" lose)."""
    if not tickers or not day:
        return {}
    index = pd.DatetimeIndex([pd.Timestamp(day)])
    q, s, b = quality_table(cfg, tickers, index), short_table(cfg, tickers, index), insider_table(cfg, tickers, index)
    out = {}
    for t in tickers:
        found = []
        pct = q[t].iloc[0]
        if not np.isnan(pct):
            found.append("weak quality (bottom 30% by gross profits)" if pct <= 0.3 else
                         "high quality (top 30% by gross profits)" if pct >= 0.7 else "")
        if s[t].iloc[0]:
            found.append("heavily shorted")
        if b[t].iloc[0]:
            found.append("an insider just bought")
        if any(found):
            out[t] = [f for f in found if f]
    return out


def card(cfg, ticker: str) -> dict:
    """For the stock card: quality, recent insider buys and short interest, in plain English."""
    out = {}
    q = quality_points(cfg, ticker)
    if q:
        start, pct, ratio, end = q[-1]
        out["quality"] = {"pct": pct, "ratio": ratio, "year_end": end,
                          "text": f"gross profits {ratio:.0%} of assets (year to {end}): better than "
                                  f"{pct:.0%} of US companies" + (" (weak: the bottom 30%)" if pct <= 0.3 else "")}
    buys = sorted(insider_buys(cfg, ticker), key=lambda b: b["filed"], reverse=True)[:3]
    if buys:
        out["insider_buys"] = [{**b, "text": f"{b['who']} bought ${b['value']:,.0f} on {b['date']} (filed {b['filed']})"}
                               for b in buys]
    rows = _load(cfg, SHORT_FILE).get(ticker) or []
    if rows:
        r = rows[-1]
        bits = [f"{r['short_pct_float']:.1f}% of the float sold short" if r.get("short_pct_float") is not None else "",
                f"{r['days_to_cover']:.1f} days to cover" if r.get("days_to_cover") is not None else ""]
        out["short"] = {**r, "heavy": heavily_shorted(r),
                        "text": ", ".join(b for b in bits if b) + (f" (as of {r['as_of']})" if r.get("as_of") else "")
                        + (": heavily shorted" if heavily_shorted(r) else "")}
    return out
