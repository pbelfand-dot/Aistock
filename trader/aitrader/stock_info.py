"""
stock_info.py: "what is this?" for any stock symbol you click in the app.

The company: its name and exchange from Alpaca (with your keys), and what it does from Yahoo Finance
(sector, industry, a short description, website, size). Each stock is looked up once and kept for 30
days, so clicking around never slows the bot down.

What Kestrel itself knows about it: which of its lists it's on and why, whether it's in play today,
what each account holds, its finished trades, its latest score, news and danger headlines, and any
mistake it won't repeat with it. All read from the bot's own files; nothing here trades.
"""
import json
import re
import socket
from datetime import date, datetime

from .config import data_path

CACHE = "stock_info.json"
KEEP_DAYS = 30
TICKER = r"[A-Z][A-Z0-9.\-]{0,9}"
ACCOUNTS = {"study": "in its head", "paper": "paper", "live": "real money"}


def clean(ticker) -> str:
    t = str(ticker or "").strip().upper()
    if not re.fullmatch(TICKER, t):
        raise ValueError(f"{ticker!r} isn't a stock symbol.")
    return t


# ---------------------------------------------------------------- the company
def _from_alpaca(cfg, ticker) -> dict:
    from .alpaca_api import has_keys, trading_client
    paper = has_keys(cfg, True)
    if not (paper or has_keys(cfg, False)):
        return {}
    a = trading_client(cfg, paper=paper).get_asset(ticker)
    return {"name": a.name, "exchange": str(getattr(a.exchange, "value", a.exchange) or ""),
            "tradable": bool(a.tradable), "fractionable": bool(getattr(a, "fractionable", False))}


def _short(text: str, limit: int = 600) -> str:
    """The first sentences of a long description, up to about `limit` characters."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 3 else cut.rstrip() + "..."


def _from_yahoo(ticker) -> dict:
    import yfinance as yf
    info = yf.Ticker(ticker.replace(".", "-")).get_info() or {}
    kind = {"ETF": "ETF", "MUTUALFUND": "fund", "EQUITY": "stock"}.get(str(info.get("quoteType", "")).upper(), "")
    out = {"name": info.get("longName") or info.get("shortName"), "kind": kind,
           "sector": info.get("sector") or info.get("category"), "industry": info.get("industry"),
           "summary": _short(info.get("longBusinessSummary")), "website": info.get("website"),
           "market_cap": info.get("marketCap") or info.get("totalAssets"), "country": info.get("country"),
           "fund_family": info.get("fundFamily")}
    return {k: v for k, v in out.items() if v not in (None, "")}


def _cache(cfg) -> dict:
    path = data_path(cfg, CACHE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def company(cfg, ticker: str, alpaca=_from_alpaca, yahoo=_from_yahoo) -> dict:
    """What the company is (cached 30 days). {} if it couldn't be looked up (e.g. no internet)."""
    saved = _cache(cfg)
    hit = saved.get(ticker)
    if hit and (date.today() - date.fromisoformat(hit.get("looked_up", "2000-01-01"))).days < KEEP_DAYS:
        return hit
    parts, before = [], socket.getdefaulttimeout()
    socket.setdefaulttimeout(10)                         # a slow website never hangs the app
    try:
        for look_up in (lambda: alpaca(cfg, ticker), lambda: yahoo(ticker)):
            try:
                parts.append(look_up() or {})
            except Exception:
                parts.append({})
    finally:
        socket.setdefaulttimeout(before)
    found = {**parts[0], **parts[1]}                     # Yahoo's name is the short one ("NIO Inc.")
    if parts[0].get("exchange"):
        found["exchange"] = parts[0]["exchange"]
    if not found.get("name"):
        return hit or {}                                 # nothing new: an old answer beats none
    found["looked_up"] = date.today().isoformat()
    saved[ticker] = found
    path = data_path(cfg, CACHE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(saved, indent=1))
    tmp.replace(path)
    return found


# ---------------------------------------------------------------- what Kestrel knows
def kestrel_view(cfg, store, ticker: str, today: str = None) -> dict:
    from . import in_play, scanner
    from .report import trades
    today = today or datetime.now().strftime("%Y-%m-%d")
    desks = list(cfg.get("desks") or {})
    lists = [f"On the {d} desk's watchlist" for d in desks if ticker in (cfg["desks"][d].get("watchlist") or [])]
    scan = scanner.load_list(cfg)
    row = next((r for r in scan.get("liked") or [] if r["symbol"] == ticker), None)
    if row:
        lists.append(f"#{row.get('rank')} on the stocks it likes: up {row.get('momentum_pct')}% over the past year "
                     f"(skipping the last month), {row.get('days_listed', 1)} days on the list")
    if any(r["symbol"] == ticker for r in scan.get("swing_picks") or []):
        lists.append("The swing desk considers it: one of the strongest stocks it can afford")
    if any(r["symbol"] == ticker for r in scan.get("new_listings") or []):
        lists.append("A new listing (under a year of history): watched, not traded")
    if any(r["symbol"] == ticker for r in scan.get("day_pool") or []):
        lists.append("Busy enough for the day desk's 9:35 check for stocks in play")
    state = in_play.load(cfg)
    pick = next((p for p in state.get("picks") or [] if p["symbol"] == ticker), None) \
        if state.get("day") == today else None
    if pick:
        lists.append(f"In play today: {pick['rvol']}x its usual volume in the first 5 minutes")
    for d in desks:
        pricey = store.get(f"too_pricey:{d}") or {}
        if ticker in (pricey.get("tickers") or {}):
            lists.append(f"Too pricey for the {d} desk right now: one share costs more than its "
                         f"${pricey.get('limit')} position budget")

    holding, done, scores = [], [], []
    for kind, account in ACCOUNTS.items():
        for d in desks:
            mode = f"{kind}-{d}"
            p = ((store.get(f"{mode}_ledger") or {}).get("positions") or {}).get(ticker)
            if p:
                holding.append({"account": account, "desk": d, "qty": p["qty"], "avg_cost": round(p["avg_cost"], 2),
                                "since": p.get("opened_on")})
            done += [{**t, "account": account} for t in trades(store.fills(mode), d) if t["ticker"] == ticker]
            thinking = store.get(f"{mode}_thinking") or {}
            top = next((t for t in thinking.get("top") or [] if t["ticker"] == ticker), None)
            if top:
                scores.append({"account": account, "desk": d, "score": top["score"], "strategy": thinking.get("strategy"),
                               "buy_above": thinking.get("buy_above"), "sell_below": thinking.get("sell_below"),
                               "time": thinking.get("time")})
    done.sort(key=lambda t: t["sold_on"], reverse=True)

    rows = (scan.get("liked") or []) + (scan.get("new_listings") or []) + (scan.get("swing_picks") or [])
    news_row = next((r for r in rows if r["symbol"] == ticker and r.get("news")), None)
    news = (news_row or {}).get("news") or ((scan.get("held_news") or {}).get(ticker) or {}).get("news") or []
    lessons = [m for d in desks for m in store.get(f"mistakes:{d}") or [] if m["tag"] == f"buying {ticker}"]
    from .earnings import cached
    report_day = cached(cfg, ticker)
    if report_day:
        lists.append(f"Next earnings report: {report_day}")
    from . import sec_filings
    return {"lists": lists, "holding": holding, "trades": done[:5],
            "won": sum(t["result"] == "win" for t in done), "finished": len(done),
            "scores": scores, "news": news[:3],
            "danger": (scanner.danger_tickers(cfg).get(ticker) or []) + (sec_filings.danger_tickers(cfg).get(ticker) or []),
            "lessons": [f"Won't buy it again for now: {m['why']}" for m in lessons],
            "why_moved": why_moved(cfg, ticker, news), "filings": sec_filings.recent(cfg, ticker)}


def move(cfg, ticker: str) -> dict:
    """How much it moved: today (since the last close) and over the last 5 trading days."""
    from .dashboard import _price_history, quote
    q = quote(cfg, ticker)
    out = {"last": q.get("last"), "today_pct": q.get("change_pct"), "week_pct": None}
    daily = _price_history(cfg, ticker)[0]
    if daily is not None and len(daily) > 5 and q.get("last"):
        out["week_pct"] = round((q["last"] / float(daily.iloc[-6]) - 1) * 100, 2)
    return out


def why_moved(cfg, ticker: str, news: list = None) -> dict:
    """The move and what came out about it: the latest headlines (the news Kestrel already reads) and
    SEC filings, with their times. A hint, not a proof: news can follow a move as well as cause it."""
    from . import scanner, sec_filings
    if news is None:
        scan = scanner.load_list(cfg)
        rows = (scan.get("liked") or []) + (scan.get("new_listings") or []) + (scan.get("swing_picks") or [])
        row = next((r for r in rows if r["symbol"] == ticker and r.get("news")), None)
        news = (row or {}).get("news") or ((scan.get("held_news") or {}).get(ticker) or {}).get("news") or []
    return {**move(cfg, ticker), "headlines": news[:3], "filings": sec_filings.recent(cfg, ticker, days=3)[:3]}


def info(cfg, store, ticker) -> dict:
    ticker = clean(ticker)
    return {"ticker": ticker, "company": company(cfg, ticker), "kestrel": kestrel_view(cfg, store, ticker)}
