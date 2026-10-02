"""
sec_filings.py: official company filings from the SEC's EDGAR system (free, no key). The SEC asks every
program to say who is asking, so each request carries your contact email (saved in Setup, kept in
~/AITrader/.env) and Kestrel stays well under the SEC's limit of 10 requests a second.

For the stocks Kestrel owns or is considering (its watchlists, the top of the daily scan, today's stocks
in play), about every 30 minutes on trading days:
  * the stock card lists the last two weeks of filings with links ("8-K filed 18 min ago: results");
  * serious filings make a stock a danger stock, like danger headlines: no buying it for 30 days.
    8-K item 1.03 (bankruptcy), 3.01 (delisting notice), 4.02 (past financial statements can't be
    relied on), 1.05 (a material cyber attack), and NT 10-K / NT 10-Q (a late annual or quarterly
    report). A danger filing on a stock it owns is a WARNING in the journal (and on your phone). It
    doesn't sell by itself: the stop-loss still protects it.
"""
import json
import threading
import time
from datetime import datetime, timedelta

import requests

from .config import data_path

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILE = "sec_filings.json"
SHOW_DAYS = 14                  # the stock card's filings
DANGER_DAYS = 30                # how long a danger filing blocks buying
CHECK_EVERY_MINUTES = 30
MAX_TICKERS = 150
MIN_GAP = 0.15                  # seconds between requests: under 7 a second (the SEC allows 10)
DANGER_ITEMS = {"1.03": "bankruptcy or receivership", "3.01": "a delisting notice",
                "4.02": "its past financial statements can't be relied on", "1.05": "a material cyber attack"}
DANGER_FORMS = {"NT 10-K": "a late annual report", "NT 10-Q": "a late quarterly report"}
ITEMS = {"1.01": "a major agreement", "1.02": "an agreement ended", "1.03": "bankruptcy", "1.05": "a cyber attack",
         "2.01": "bought or sold a business", "2.02": "results (earnings)", "2.03": "new debt",
         "2.05": "restructuring costs", "2.06": "a write-down", "3.01": "delisting notice",
         "3.02": "sold new shares", "3.03": "shareholder rights changed", "4.01": "changed auditors",
         "4.02": "financials can't be relied on", "5.01": "change of control",
         "5.02": "a director or executive change", "5.03": "bylaws changed", "5.07": "shareholder vote results",
         "7.01": "an announcement (Reg FD)", "8.01": "other news"}
FORMS = {"8-K": "news (8-K)", "8-K/A": "news, corrected (8-K/A)", "10-Q": "quarterly report (10-Q)",
         "10-K": "annual report (10-K)", "4": "insider trade (Form 4)", "S-1": "new share offering (S-1)",
         "S-3": "shelf offering (S-3)", "SC 13D": "a 5%+ owner, active (13D)", "SC 13G": "a 5%+ owner, passive (13G)",
         "SCHEDULE 13D": "a 5%+ owner, active (13D)", "SCHEDULE 13G": "a 5%+ owner, passive (13G)",
         "DEF 14A": "proxy statement", "6-K": "foreign company news (6-K)", "20-F": "foreign annual report (20-F)",
         "NT 10-K": "LATE annual report (NT 10-K)", "NT 10-Q": "LATE quarterly report (NT 10-Q)"}
_get = requests.get             # tests don't go online
_last_call = [0.0]
_checking = None


def contact(cfg) -> str:
    return (cfg.get("secrets") or {}).get("sec_email") or ""


def is_on(cfg) -> bool:
    s = str((cfg.get("sec") or {}).get("enabled", True)).strip().lower()
    return s not in ("off", "false", "no", "0") and bool(contact(cfg))


def _fetch(cfg, url: str) -> dict:
    wait = MIN_GAP - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()
    r = _get(url, headers={"User-Agent": f"Kestrel personal trading app {contact(cfg)}",
                           "Accept-Encoding": "gzip, deflate"}, timeout=20)
    if r.status_code == 404:
        return {}
    if r.status_code != 200:
        raise RuntimeError(f"the SEC said {r.status_code}" + (" (too many requests: slowing down)"
                                                               if r.status_code in (403, 429) else ""))
    return r.json()


def cik_map(cfg, today: str) -> dict:
    """{ticker: CIK} from the SEC's own list, refreshed once a week."""
    path = data_path(cfg, "sec/company_tickers.json")
    try:
        saved = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        saved = {}
    if saved.get("map") and saved.get("updated", "") >= (datetime.strptime(today, "%Y-%m-%d")
                                                          - timedelta(days=7)).strftime("%Y-%m-%d"):
        return saved["map"]
    rows = _fetch(cfg, TICKERS_URL)
    mapping = {str(r["ticker"]).upper(): int(r["cik_str"]) for r in (rows or {}).values() if r.get("ticker")}
    if mapping:
        path.write_text(json.dumps({"updated": today, "map": mapping}))
    return mapping or saved.get("map") or {}


def accepted_at(value: str, now: datetime) -> datetime:
    """When the SEC accepted the filing, in New York time. EDGAR's quirk: for about 5.5 hours a fresh
    filing's time is New York wall-clock time labelled Z (UTC), then it's rewritten to true UTC."""
    from zoneinfo import ZoneInfo
    if not value:
        return None
    wall = datetime.fromisoformat(value.replace("Z", "")[:19])
    as_utc = datetime.fromisoformat(value.replace("Z", "")[:19] + "+00:00").astimezone(
        ZoneInfo("America/New_York")).replace(tzinfo=None)
    if wall > now + timedelta(minutes=5):                 # can't be in the future: it's true UTC
        return as_utc
    return wall if now - wall < timedelta(hours=5, minutes=30) else as_utc


def ago(now: datetime, when: datetime) -> str:
    minutes = (now - when).total_seconds() / 60
    if minutes < 60:
        return f"{max(0, minutes):.0f} min ago"
    if minutes < 24 * 60:
        return f"{minutes / 60:.0f}h ago"
    return f"{when:%b} {when.day}"


def parse(cik: int, data: dict, now: datetime, days: int = DANGER_DAYS) -> list:
    """The company's filings of the last `days` days, newest first, in plain English, with links."""
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for i, form in enumerate(forms):
        day = (recent.get("filingDate") or [""] * len(forms))[i]
        if day < cutoff:
            continue
        get = lambda key: (recent.get(key) or [""] * len(forms))[i] or ""
        items = [x.strip() for x in get("items").split(",") if x.strip()]
        accession = get("accessionNumber")
        doc = get("primaryDocument")
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}" if doc else
               f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}")
        when = accepted_at(get("acceptanceDateTime"), now)
        danger = [DANGER_ITEMS[x] for x in items if x in DANGER_ITEMS and form.startswith("8-K")]
        if form in DANGER_FORMS:
            danger.append(DANGER_FORMS[form])
        what = FORMS.get(form, form)
        if items:
            said = [ITEMS[x] for x in items if x in ITEMS and x != "9.01"]
            if said:
                what += ": " + ", ".join(dict.fromkeys(said))
        out.append({"form": form, "date": day, "time": when.isoformat(timespec="minutes") if when else None,
                    "what": what, "items": items, "url": url, "danger": danger})
    return sorted(out, key=lambda f: f["time"] or f["date"], reverse=True)


def load(cfg) -> dict:
    path = data_path(cfg, FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def wanted(cfg, store) -> list:
    """What it owns (every account), its watchlists, the top of the scan and today's stocks in play."""
    from .scanner import trade_candidates
    from .in_play import today_picks
    held = [t for kind in ("study", "paper", "live") for d in cfg["desks"]
            for t in ((store.get(f"{kind}-{d}_ledger") or {}).get("positions") or {})]
    lists = [t for d in cfg["desks"] for t in cfg["desks"][d].get("watchlist") or []]
    try:
        extra = trade_candidates(cfg) + today_picks(cfg)
    except Exception:
        extra = []
    return list(dict.fromkeys(held + lists + extra))[:MAX_TICKERS], set(held)


def check(cfg, store, now: datetime) -> str:
    """Looks up the filings of every stock it cares about; says so when a new danger filing appears."""
    if not is_on(cfg):
        return "SEC filings: off (add your contact email in Setup → AI & news)"
    today = now.strftime("%Y-%m-%d")
    tickers, held = wanted(cfg, store)
    ciks = cik_map(cfg, today)
    before = load(cfg).get("stocks") or {}
    stocks, failed = {}, 0
    for t in tickers:
        cik = ciks.get(t.upper().replace(".", "-"))
        if not cik:
            continue                                         # funds, ETFs and foreign stocks may have none
        try:
            filings = parse(cik, _fetch(cfg, SUBMISSIONS_URL.format(cik=cik)), now)
        except Exception:
            failed += 1
            if t in before:
                stocks[t] = before[t]                        # keep what it knew
            continue
        stocks[t] = {"cik": cik, "checked": now.isoformat(timespec="minutes"), "filings": filings[:15]}
        seen = {f["url"] for f in (before.get(t) or {}).get("filings") or []}
        for f in filings:
            if f["danger"] and f["url"] not in seen:
                prefix = "WARNING: " if t in held else ""
                store.log(f"{prefix}[sec] {t} filed {f['form']} ({', '.join(f['danger'])}): not buying it for "
                          f"{DANGER_DAYS} days{'; the stop-loss still protects what it owns' if t in held else ''}. "
                          f"{f['url']}")
    data_path(cfg, FILE).write_text(json.dumps({"checked": now.isoformat(timespec="minutes"), "stocks": stocks,
                                                "failed": failed}))
    return f"SEC filings: {len(stocks)} stocks checked" + (f", {failed} failed" if failed else "")


def danger_tickers(cfg, now: datetime = None) -> dict:
    """{ticker: [reasons]}: a serious filing in the last 30 days. Not bought for now."""
    now = now or datetime.now()
    cutoff = (now - timedelta(days=DANGER_DAYS)).strftime("%Y-%m-%d")
    out = {}
    for t, s in (load(cfg).get("stocks") or {}).items():
        reasons = [r for f in s.get("filings") or [] if f["date"] >= cutoff for r in f.get("danger") or []]
        if reasons:
            out[t] = list(dict.fromkeys(f"SEC: {r}" for r in reasons))
    return out


def recent(cfg, ticker: str, now: datetime = None, days: int = SHOW_DAYS) -> list:
    """The stock card's filings: the last two weeks, newest first, with how long ago."""
    now = now or datetime.now()
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    s = (load(cfg).get("stocks") or {}).get(ticker) or {}
    out = []
    for f in s.get("filings") or []:
        if f["date"] < cutoff:
            continue
        when = datetime.fromisoformat(f["time"]) if f.get("time") else None
        out.append({**f, "ago": ago(now, when) if when else f["date"]})
    return out[:8]


def keep_checking(cfg, store, now: datetime) -> str:
    """Every 30 minutes on trading days from 7am to 8pm, in the background (trading never waits)."""
    global _checking
    if not is_on(cfg) or now.weekday() >= 5 or not (7 <= now.hour < 20):
        return ""
    if _checking is not None and _checking.is_alive():
        return ""
    last = load(cfg).get("checked")
    if last and (now - datetime.fromisoformat(last)).total_seconds() < CHECK_EVERY_MINUTES * 60:
        return ""
    from .storage import Store
    path = data_path(cfg, "aitrader.sqlite")

    def work():
        own = Store(path)
        own.on_log = store.on_log                            # a danger filing on a holding reaches your phone
        try:
            check(cfg, own, now)
        except Exception as e:
            own.log(f"[sec] couldn't check the filings ({e!r}); tries again in 30 minutes")
            data_path(cfg, FILE).write_text(json.dumps({**load(cfg), "checked": now.isoformat(timespec="minutes"),
                                                        "error": repr(e)[:200]}))
        finally:
            own.db.close()
    _checking = threading.Thread(target=work, daemon=True, name="sec-filings")
    _checking.start()
    return "SEC filings: checking in the background"


def status(cfg) -> dict:
    s = load(cfg)
    return {"on": is_on(cfg), "has_email": bool(contact(cfg)), "checked": s.get("checked"),
            "stocks": len(s.get("stocks") or {}), "error": s.get("error"),
            "danger": danger_tickers(cfg)}
