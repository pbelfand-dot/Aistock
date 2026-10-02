"""
scanner.py: once a day, look at ALL US stocks, keep a list of the ones worth trading, and read their news.

1. Every tradable US stock and ETF (from Alpaca; without Alpaca keys, the ~400 names in universe.txt).
2. Skip what's hard to trade well: under $3 a share, or too little trading per day.
3. Rank by 12-month momentum (the past year's rise, skipping the latest month): the one stock-picking
   method the research supported (see knowledge/30-research-findings.md). Only stocks in an uptrend
   (above their 200-day average) make the list.
4. News (if you allow it in Setup): recent headlines for the list and anything the bot owns. A stock with
   danger headlines (a share offering, bankruptcy, a trading halt, delisting, fraud charges...) isn't
   bought for a few days. News never makes it BUY anything.
5. The list remembers: when each stock first made it, how many days it has been on it, and how it has
   done since. Newly listed stocks (under a year of history) get a separate, watch-only list.

The swing desk also considers the top of the list (it still buys only what fits its budget and rules).
"""
import hashlib
import json
import math
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import data_path

UNIVERSE_FILE = Path(__file__).resolve().parent / "universe.txt"
GROUP = 1000                     # stocks per saved piece: a scan cut short (an update, a restart, sleep) picks up there
PARTS = "scan/parts"             # today's pieces
HISTORY = "scan/history.pkl"     # the last scan's year of prices, so the next one only fetches the newest weeks
PROGRESS = "scan/progress.json"  # how far the running scan is (the Thinking tab, the report)
KEEP_ROWS = 300                  # trading days kept per stock (12-month momentum needs 253)
COLUMNS = ["open", "high", "low", "close", "volume"]
progress = {"at": None}          # this process: when the running scan last moved forward (run.py's stuck check)
LIST_FILE = "liked_stocks.json"
NOTE = "stocks-i-like.md"
EXCHANGES = {"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS", "NYSEARCA"}
DANGER_WORDS = ("offering", "bankrupt", "chapter 11", "trading halt", "halted", "delist", "going concern",
                "sec charges", "fraud", "reverse split", "default", "restatement", "subpoena")


def is_on(value) -> bool:
    return str(value).strip().lower() in ("true", "on", "yes", "1")


def settings(cfg: dict) -> dict:
    s = {"enabled": True, "top": 30, "new_listings": 5, "min_price": 3.0, "min_dollar_volume": 5_000_000,
         "trade_top": 30}
    s.update(cfg.get("scanner") or {})
    return s


def news_on(cfg: dict) -> bool:
    return is_on((cfg.get("news") or {}).get("enabled", True))


# ------------------------------------------------------------------ where the stocks come from
def universe(cfg: dict) -> list:
    from .alpaca_api import has_keys
    if has_keys(cfg, True) or has_keys(cfg, False):
        try:
            return alpaca_universe(cfg)
        except Exception as e:
            print(f"  (couldn't list all stocks from Alpaca: {e}; using the built-in list)")
    return builtin_universe()


def builtin_universe() -> list:
    return [s.strip() for s in UNIVERSE_FILE.read_text().split() if s.strip()]


def alpaca_universe(cfg: dict) -> list:
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    from .alpaca_api import has_keys, trading_client
    client = trading_client(cfg, paper=has_keys(cfg, True))
    assets = client.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY))
    return sorted(a.symbol for a in assets
                  if a.tradable and str(getattr(a.exchange, "value", a.exchange)).upper() in EXCHANGES
                  and a.symbol.isalpha())


def fetch_bars(cfg: dict, symbols: list, days: int) -> dict:
    """Daily bars for many symbols at once: Alpaca (full-market data, 15+ minutes delayed, free) or Yahoo."""
    from .alpaca_api import has_keys
    if has_keys(cfg, True) or has_keys(cfg, False):
        return _alpaca_bars(cfg, symbols, days)
    return _yahoo_bars(symbols, days)


CHUNK = 200                                   # symbols per request
WAITS = (10, 30)                              # seconds to wait before trying a refused batch again
_pause = time.sleep                           # tests don't wait


def _alpaca_bars(cfg, symbols, days) -> dict:
    """Thousands of stocks in batches. A batch Alpaca refuses (e.g. too many requests a minute on the free
    plan) is tried again after a pause; if most batches still fail, the whole scan counts as failed and
    the autopilot runs it again, instead of quietly making a list from a fraction of the market."""
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from .alpaca_api import data_client
    client, out, error, failed, batches = data_client(cfg), {}, None, 0, 0
    end = datetime.now(timezone.utc) - timedelta(minutes=20)          # the free plan's full-market data is delayed
    for i in range(0, len(symbols), CHUNK):
        if i:
            _pause(0.5)                        # gentle on the free plan's 200 requests a minute (the day desk shares it)
        chunk, df, batches = symbols[i:i + CHUNK], None, batches + 1
        for wait in (0, *WAITS):
            if wait:
                _pause(wait)
            for feed in (DataFeed.SIP, DataFeed.IEX):                 # IEX if the full feed isn't allowed
                try:
                    df = client.get_stock_bars(StockBarsRequest(
                        symbol_or_symbols=chunk, timeframe=TimeFrame.Day, adjustment=Adjustment.ALL,
                        start=end - timedelta(days=days), end=end, feed=feed)).df
                    break
                except Exception as e:
                    df, error = None, e
            if df is not None:
                break
        progress["at"] = time.monotonic()                           # still moving (run.py's stuck check)
        if df is None:
            failed += 1
            continue
        if df.empty:
            continue
        for sym, part in df.groupby(level="symbol"):
            part = part.droplevel("symbol")
            part.index = pd.DatetimeIndex(pd.to_datetime(part.index, utc=True).tz_convert("America/New_York")
                                          .tz_localize(None)).normalize()
            out[sym] = part[["open", "high", "low", "close", "volume"]]
    if (not out and error is not None) or failed > batches / 2:
        raise RuntimeError(f"Alpaca refused {failed} of {batches} batches of prices: {error!r}")
    return out


def _yahoo_bars(symbols, days) -> dict:
    import yfinance as yf
    out = {}
    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i + 100]
        df = yf.download(chunk, period=f"{max(days // 365 + 1, 1)}y", auto_adjust=True, group_by="ticker",
                         threads=True, progress=False)
        for sym in chunk:
            try:
                part = df[sym].dropna(subset=["Close"])
            except KeyError:
                continue
            if len(part):
                out[sym] = part.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    return out


# ------------------------------------------------------------------ ranking
def score(bars: dict, cfg: dict) -> pd.DataFrame:
    """One row per stock: its numbers and whether it qualifies for the list."""
    s, rows = settings(cfg), []
    for sym, df in bars.items():
        close = df["close"].dropna()
        if len(close) < 60:
            continue
        price = float(close.iloc[-1])
        dollar_volume = float((df["close"] * df["volume"]).iloc[-20:].mean())
        prev = close.shift(1)
        true_range = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
                               axis=1).max(axis=1)
        row = {"symbol": sym, "price": round(price, 2), "dollar_volume": round(dollar_volume),
               "avg_volume": round(float(df["volume"].iloc[-14:].mean())), "atr": round(float(true_range.iloc[-14:].mean()), 2),
               "return_1m_pct": round((price / float(close.iloc[-22]) - 1) * 100, 1),
               "return_3m_pct": round((price / float(close.iloc[-64]) - 1) * 100, 1),
               "history_days": len(close), "new_listing": len(close) < 253}
        if len(close) >= 253:
            row["momentum_pct"] = round((float(close.iloc[-22]) / float(close.iloc[-253]) - 1) * 100, 1)
        if len(close) >= 200:
            sma50, sma200 = close.iloc[-50:].mean(), close.iloc[-200:].mean()
            row["uptrend"] = bool(price > sma200 and sma50 > sma200)
        row["tradeable"] = price >= s["min_price"] and dollar_volume >= s["min_dollar_volume"]
        rows.append(row)
    return pd.DataFrame(rows)


def _ranked(table: pd.DataFrame) -> pd.DataFrame:
    """Tradeable, established, uptrending stocks, strongest 12-month momentum first."""
    ok = table[table["tradeable"]]
    uptrend = ok["uptrend"].fillna(False).astype(bool) if "uptrend" in ok else pd.Series(False, index=ok.index)
    established = ok[(~ok["new_listing"].astype(bool)) & uptrend]
    if "momentum_pct" not in established:
        return established.iloc[0:0]
    return established.dropna(subset=["momentum_pct"]).sort_values("momentum_pct", ascending=False)


def actively_traded(bars: dict, cfg: dict) -> list:
    """From a quick look at the last few weeks: the stocks worth a full year of prices ($3+, traded enough)."""
    s, out = settings(cfg), []
    for sym, df in bars.items():
        close = df["close"].dropna()
        if close.empty:
            continue
        dollar_volume = float((df["close"] * df["volume"]).iloc[-20:].mean())
        if float(close.iloc[-1]) >= s["min_price"] and dollar_volume >= s["min_dollar_volume"]:
            out.append(sym)
    return out


def pick(table: pd.DataFrame, cfg: dict) -> tuple:
    """(the list, the new-listings watch list), best first."""
    s = settings(cfg)
    if table.empty:
        return [], []
    ok = table[table["tradeable"]]
    newcomers = ok[ok["new_listing"]].sort_values("return_3m_pct", ascending=False)
    return (_records(_ranked(table).head(int(s["top"]))), _records(newcomers.head(int(s["new_listings"]))))


def swing_price_limit(cfg: dict) -> float:
    """The most one share can cost for the swing desk (no limit with fractional shares)."""
    from .config import desk_capital
    from .risk import RiskManager
    if "swing" not in (cfg.get("desks") or {}):
        return float("inf")
    return RiskManager.for_desk(cfg, "swing").max_share_price(desk_capital(cfg, "swing", False))


def day_tickers(cfg: dict) -> set:
    return set(((cfg.get("desks") or {}).get("day") or {}).get("watchlist") or [])


def swing_picks(table: pd.DataFrame, cfg: dict) -> list:
    """What the swing desk considers: the strongest stocks it can afford (any price with fractional shares), skipping the
    day desk's stocks (a stock is on one desk only). With more positions each share must cost less, so
    picking from the whole ranking (not just the top of the list) keeps enough strong candidates."""
    if table.empty:
        return []
    ranked = _ranked(table)
    ranked = ranked[(ranked["price"] <= swing_price_limit(cfg)) & ~ranked["symbol"].isin(day_tickers(cfg))]
    return _records(ranked.head(int(settings(cfg)["trade_top"])))


def _records(frame: pd.DataFrame) -> list:
    """Rows as plain values: a number that doesn't exist (e.g. no year of history) becomes None, not NaN."""
    rows = frame.to_dict("records")
    return [{k: (None if isinstance(v, float) and math.isnan(v) else v.item() if hasattr(v, "item") else v)
             for k, v in r.items()} for r in rows]


# ------------------------------------------------------------------ news
def fetch_news(cfg: dict, symbols: list, days: int = 3) -> dict:
    """{symbol: [{"time", "headline", "source", "url"}]} (Alpaca's news feed, or Yahoo without keys)."""
    from .alpaca_api import has_keys, keys, timed
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = {s: [] for s in symbols}
    if has_keys(cfg, True) or has_keys(cfg, False):
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        client = timed(NewsClient(*keys(cfg, has_keys(cfg, True))))
        for i in range(0, len(symbols), 25):
            chunk = symbols[i:i + 25]
            result = client.get_news(NewsRequest(symbols=",".join(chunk), start=since, limit=50))
            items = getattr(result, "data", {}).get("news", []) if hasattr(result, "data") else []
            for item in items:
                for sym in getattr(item, "symbols", []) or []:
                    if sym in out:
                        out[sym].append({"time": str(item.created_at)[:16], "headline": item.headline,
                                         "source": item.source, "url": item.url})
        return out
    import yfinance as yf
    for sym in symbols:
        try:
            for item in (yf.Ticker(sym).news or [])[:10]:
                c = item.get("content", item)
                when = c.get("pubDate") or ""
                if when and pd.Timestamp(when).tz_localize(None) < pd.Timestamp(since).tz_localize(None):
                    continue
                out[sym].append({"time": str(when)[:16], "headline": c.get("title", ""),
                                 "source": (c.get("provider") or {}).get("displayName", "Yahoo"),
                                 "url": (c.get("canonicalUrl") or {}).get("url", "")})
        except Exception:
            continue
    return out


def danger(headlines: list) -> list:
    """The danger words found in these headlines."""
    found = []
    for h in headlines:
        text = str(h.get("headline", "")).lower()
        found += [w for w in DANGER_WORDS if w in text and w not in found]
    return found


# ------------------------------------------------------------------ the list
# ------------------------------------------------------------------ in pieces, resumable, incremental
def _tick(cfg, step: str, done: int, total: int, started: str = None):
    progress["at"] = time.monotonic()
    state = {"step": step, "done": done, "total": total, "at": datetime.now().isoformat(timespec="seconds")}
    if started:
        state["started"] = started
    try:
        path = data_path(cfg, PROGRESS)
        old = json.loads(path.read_text()) if path.exists() else {}
        path.write_text(json.dumps({**old, **state}))
    except (OSError, ValueError):
        pass


def read_progress(cfg) -> dict:
    try:
        return json.loads(data_path(cfg, PROGRESS).read_text())
    except (OSError, ValueError):
        return {}


def _stage() -> str:
    """Pieces from before the close aren't reused after it (they lack today's closing prices)."""
    from .market_hours import now_ny
    return "late" if now_ny().hour >= 16 else "early"


def in_pieces(cfg: dict, fetch, symbols: list, days: int, today: str, step: str) -> dict:
    """fetch() GROUP stocks at a time, saving each piece the moment it arrives. A scan that was cut short
    reuses today's saved pieces instead of starting over."""
    folder = data_path(cfg, f"{PARTS}/{today}-{_stage()}/x").parent
    out, total = {}, len(symbols)
    _tick(cfg, step, 0, total)
    for i in range(0, total, GROUP):
        chunk = symbols[i:i + GROUP]
        path = folder / f"{days}-{hashlib.md5(','.join(chunk).encode()).hexdigest()[:12]}.pkl"
        part = None
        if path.exists():
            try:
                part = pd.read_pickle(path)
            except Exception:
                part = None
        if part is None:
            part = fetch(cfg, chunk, days)
            tmp = path.with_suffix(".tmp")
            pd.to_pickle(part, tmp)
            tmp.replace(path)
        out.update(part)
        _tick(cfg, step, min(i + GROUP, total), total)
    return out


def clean_pieces(cfg: dict, today: str):
    """Pieces from earlier days are never reused."""
    folder = data_path(cfg, f"{PARTS}/x").parent
    for old in folder.iterdir():
        if old.is_dir() and not old.name.startswith(today):
            shutil.rmtree(old, ignore_errors=True)


def load_history(cfg: dict) -> dict:
    path = data_path(cfg, HISTORY)
    try:
        frame = pd.read_pickle(path) if path.exists() else None
    except Exception:
        return {}
    if frame is None or frame.empty:
        return {}
    return {sym: part.droplevel(0) for sym, part in frame.groupby(level=0)}


def save_history(cfg: dict, bars: dict):
    frames = {s: df[COLUMNS].tail(KEEP_ROWS).astype("float32") for s, df in bars.items() if len(df)}
    if not frames:
        return
    path = data_path(cfg, HISTORY)
    tmp = path.with_suffix(".tmp")
    pd.concat(frames).to_pickle(tmp)
    tmp.replace(path)


def joinable(old: pd.DataFrame, new: pd.DataFrame) -> bool:
    """Saved prices can be extended with fresh ones only if they agree where they overlap (a split or a
    dividend rewrites a stock's adjusted history: then its full year is fetched again). The newest saved
    day is left out of the check: a scan before the close saved a day that wasn't finished."""
    overlap = old.index[:-1].intersection(new.index)
    if len(overlap) < 5:
        return False
    ratio = (new.loc[overlap, "close"] / old.loc[overlap, "close"].astype(float)).dropna()
    return len(ratio) >= 5 and float((ratio - 1).abs().max()) < 0.002


def with_history(cfg: dict, fetch, recent: dict, active: list, today: str) -> tuple:
    """A year of prices for every actively traded stock: the saved year extended with the fresh weeks
    where they agree, a full download only for the rest. Returns (bars, how many reused)."""
    saved = load_history(cfg)
    reuse = {s for s in active if s in saved and s in recent and joinable(saved[s], recent[s])}
    need = [s for s in active if s not in reuse]
    full = in_pieces(cfg, fetch, need, 400, today, "a full year of prices") if need else {}
    bars = {}
    for s in active:
        if s in full:
            bars[s] = full[s]
        elif s in reuse:
            old, new = saved[s], recent[s]
            bars[s] = pd.concat([old[old.index < new.index[0]].astype(float), new[COLUMNS]])
    save_history(cfg, bars)
    return bars, len(reuse)


def load_list(cfg: dict) -> dict:
    path = data_path(cfg, LIST_FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def update_list(cfg: dict, liked: list, newcomers: list, news: dict, today: str, picks: list = None,
                day_pool: list = None) -> dict:
    old = load_list(cfg)
    history = old.get("history", {})
    for rank, row in enumerate(liked, 1):
        h = history.setdefault(row["symbol"], {"first_listed": today, "price_when_first_listed": row["price"],
                                               "days_listed": 0})
        if h.get("last_listed") != today:
            h["days_listed"] = h.get("days_listed", 0) + 1
        h.update(last_listed=today, left_on=None)
        row.update(rank=rank, first_listed=h["first_listed"], days_listed=h["days_listed"],
                   since_first_listed_pct=round((row["price"] / h["price_when_first_listed"] - 1) * 100, 1))
    for sym, h in history.items():                                    # dropped off the list today
        if h.get("last_listed") != today and not h.get("left_on"):
            h["left_on"] = today
    picks = picks or []
    for row in liked + newcomers + picks:
        items = news.get(row["symbol"], [])
        row.update(news=items[:5], news_count=len(items), danger=danger(items))
    state = {"updated": today, "liked": liked, "new_listings": newcomers, "history": history,
             "swing_picks": [{k: r.get(k) for k in ("symbol", "price", "momentum_pct", "danger")} for r in picks],
             "day_pool": day_pool or [],                 # busy stocks the day desk could trade (in_play.py)
             "held_news": {s: {"news": v[:5], "danger": danger(v)} for s, v in news.items()
                           if s not in {r["symbol"] for r in liked + newcomers + picks}}}
    path = data_path(cfg, LIST_FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, default=str))
    tmp.replace(path)
    data_path(cfg, NOTE).write_text(note(state))
    return state


def trade_candidates(cfg: dict) -> list:
    """The swing desk's picks from the scan (its own rules and budget still decide). Older lists without
    picks: the top of the list. Never the day desk's stocks."""
    s = settings(cfg)
    if not is_on(s["enabled"]):
        return []
    state = load_list(cfg)
    rows = state["swing_picks"] if state.get("swing_picks") is not None else state.get("liked", [])
    day = day_tickers(cfg)
    return [r["symbol"] for r in rows if r["symbol"] not in day][:int(s["trade_top"])]


def danger_tickers(cfg: dict) -> dict:
    """{symbol: [danger words]} from the latest scan: these aren't bought for now."""
    state = load_list(cfg)
    out = {r["symbol"]: r["danger"] for r in state.get("liked", []) + state.get("new_listings", [])
           + state.get("swing_picks", []) if r.get("danger")}
    out.update({s: v["danger"] for s, v in state.get("held_news", {}).items() if v.get("danger")})
    return out


def note(state: dict) -> str:
    lines = ["# Stocks I like right now", "",
             f"From the daily scan of all US stocks ({state['updated']}): ranked by 12-month momentum, uptrends "
             "only, $3+ a share and actively traded. The list is for watching and for the swing desk's "
             "consideration; its rules and budget still decide every trade.", ""]
    for r in state["liked"][:15]:
        flag = f" DANGER NEWS ({', '.join(r['danger'])}): not buying it for now." if r.get("danger") else ""
        top = f' Latest headline: "{r["news"][0]["headline"]}".' if r.get("news") else ""
        lines.append(f"- #{r['rank']} {r['symbol']} ${r['price']}: up {r.get('momentum_pct')}% over the past "
                     f"year, {r['return_1m_pct']:+}% this month; on the list {r['days_listed']} days "
                     f"({r['since_first_listed_pct']:+}% since).{top}{flag}")
    if state["new_listings"]:
        lines += ["", "New listings (under a year of history; watch only):"]
        lines += [f"- {r['symbol']} ${r['price']}: {r['return_3m_pct']:+}% over 3 months" for r in state["new_listings"]]
    return "\n".join(lines) + "\n"


def run(cfg: dict, store, today: str, fetch=fetch_bars, get_news=fetch_news) -> str:
    """The daily scan. Returns a one-line summary for the journal."""
    s = settings(cfg)
    if not is_on(s["enabled"]):
        return "scan: off (Setup)"
    symbols = universe(cfg)
    clean_pieces(cfg, today)
    _tick(cfg, "a quick look at every stock", 0, len(symbols), started=datetime.now().isoformat(timespec="seconds"))
    recent = in_pieces(cfg, fetch, symbols, 45, today, "a quick look at every stock")   # about 30 trading days...
    if not recent:
        raise RuntimeError(f"no prices came back for any of the {len(symbols)} stocks")
    active = actively_traded(recent, cfg)
    bars, reused = with_history(cfg, fetch, recent, active, today)   # ...then a year only for the ones worth it
    _tick(cfg, "ranking and reading the news", len(active), len(active))
    table = score(bars, cfg)
    liked, newcomers = pick(table, cfg)
    picks = swing_picks(table, cfg)
    held = sorted({t for d in cfg["desks"] for t in (store.get(f"paper-{d}_ledger") or {}).get("positions", {})}
                  | {t for d in cfg["desks"] for t in (store.get(f"live-{d}_ledger") or {}).get("positions", {})})
    wanted = sorted({r["symbol"] for r in liked + newcomers + picks} | set(held))
    news = {}
    if news_on(cfg) and wanted:
        try:
            news = get_news(cfg, wanted, int((cfg.get("news") or {}).get("days", 3)))
        except Exception as e:
            store.log(f"[scan] couldn't read the news ({e!r}); the list is made without it today")
    from .in_play import pool
    state = update_list(cfg, liked, newcomers, news, today, picks, day_pool=pool(table, cfg))
    flagged = [r["symbol"] for r in state["liked"] if r.get("danger")]
    _tick(cfg, "finished", len(active), len(active))
    return (f"scan: {len(recent)} stocks checked, {len(active)} actively traded"
            + (f" ({reused} from the saved year of prices)" if reused else "") + ", "
            f"{len(liked)} on the list (top: {', '.join(r['symbol'] for r in liked[:5]) or 'none'}), "
            f"{len(picks)} the swing desk can afford, {len(state['day_pool'])} busy enough for the day desk"
            + (f"; danger news, not buying: {', '.join(flagged)}" if flagged else ""))
