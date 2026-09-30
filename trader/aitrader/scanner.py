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
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import data_path

UNIVERSE_FILE = Path(__file__).resolve().parent / "universe.txt"
LIST_FILE = "liked_stocks.json"
NOTE = "stocks-i-like.md"
EXCHANGES = {"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS", "NYSEARCA"}
DANGER_WORDS = ("offering", "bankrupt", "chapter 11", "trading halt", "halted", "delist", "going concern",
                "sec charges", "fraud", "reverse split", "default", "restatement", "subpoena")


def is_on(value) -> bool:
    return str(value).strip().lower() in ("true", "on", "yes", "1")


def settings(cfg: dict) -> dict:
    s = {"enabled": True, "top": 30, "new_listings": 5, "min_price": 3.0, "min_dollar_volume": 5_000_000,
         "trade_top": 15}
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


def _alpaca_bars(cfg, symbols, days) -> dict:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from .alpaca_api import data_client
    client, out, error = data_client(cfg), {}, None
    end = datetime.now(timezone.utc) - timedelta(minutes=20)          # the free plan's full-market data is delayed
    for i in range(0, len(symbols), 400):
        chunk = symbols[i:i + 400]
        for feed in (DataFeed.SIP, DataFeed.IEX):                     # IEX if the full feed isn't allowed
            try:
                df = client.get_stock_bars(StockBarsRequest(
                    symbol_or_symbols=chunk, timeframe=TimeFrame.Day, adjustment=Adjustment.ALL,
                    start=end - timedelta(days=days), end=end, feed=feed)).df
                break
            except Exception as e:
                df, error = None, e
        if df is None or df.empty:
            continue
        for sym, part in df.groupby(level="symbol"):
            part = part.droplevel("symbol")
            part.index = pd.DatetimeIndex(pd.to_datetime(part.index, utc=True).tz_convert("America/New_York")
                                          .tz_localize(None)).normalize()
            out[sym] = part[["open", "high", "low", "close", "volume"]]
    if not out and error is not None:
        raise RuntimeError(f"no prices from Alpaca: {error!r}")
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
        row = {"symbol": sym, "price": round(price, 2), "dollar_volume": round(dollar_volume),
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


def pick(table: pd.DataFrame, cfg: dict) -> tuple:
    """(the list, the new-listings watch list), best first."""
    s = settings(cfg)
    if table.empty:
        return [], []
    ok = table[table["tradeable"]]
    uptrend = ok["uptrend"].fillna(False).astype(bool) if "uptrend" in ok else pd.Series(False, index=ok.index)
    established = ok[(~ok["new_listing"].astype(bool)) & uptrend]
    if "momentum_pct" in established:
        established = established.dropna(subset=["momentum_pct"]).sort_values("momentum_pct", ascending=False)
    else:
        established = established.iloc[0:0]
    newcomers = ok[ok["new_listing"]].sort_values("return_3m_pct", ascending=False)
    return (_records(established.head(int(s["top"]))), _records(newcomers.head(int(s["new_listings"]))))


def _records(frame: pd.DataFrame) -> list:
    """Rows as plain values: a number that doesn't exist (e.g. no year of history) becomes None, not NaN."""
    rows = frame.to_dict("records")
    return [{k: (None if isinstance(v, float) and math.isnan(v) else v.item() if hasattr(v, "item") else v)
             for k, v in r.items()} for r in rows]


# ------------------------------------------------------------------ news
def fetch_news(cfg: dict, symbols: list, days: int = 3) -> dict:
    """{symbol: [{"time", "headline", "source", "url"}]} (Alpaca's news feed, or Yahoo without keys)."""
    from .alpaca_api import has_keys, keys
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = {s: [] for s in symbols}
    if has_keys(cfg, True) or has_keys(cfg, False):
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        client = NewsClient(*keys(cfg, has_keys(cfg, True)))
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
def load_list(cfg: dict) -> dict:
    path = data_path(cfg, LIST_FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def update_list(cfg: dict, liked: list, newcomers: list, news: dict, today: str) -> dict:
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
    for row in liked + newcomers:
        items = news.get(row["symbol"], [])
        row.update(news=items[:5], news_count=len(items), danger=danger(items))
    state = {"updated": today, "liked": liked, "new_listings": newcomers, "history": history,
             "held_news": {s: {"news": v[:5], "danger": danger(v)} for s, v in news.items()
                           if s not in {r["symbol"] for r in liked + newcomers}}}
    path = data_path(cfg, LIST_FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, default=str))
    tmp.replace(path)
    data_path(cfg, NOTE).write_text(note(state))
    return state


def trade_candidates(cfg: dict) -> list:
    """The top of the list, for the swing desk to consider (its own rules and budget still decide)."""
    s = settings(cfg)
    if not is_on(s["enabled"]):
        return []
    return [r["symbol"] for r in load_list(cfg).get("liked", [])[:int(s["trade_top"])]]


def danger_tickers(cfg: dict) -> dict:
    """{symbol: [danger words]} from the latest scan: these aren't bought for now."""
    state = load_list(cfg)
    out = {r["symbol"]: r["danger"] for r in state.get("liked", []) + state.get("new_listings", []) if r.get("danger")}
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
    bars = fetch(cfg, symbols, 400)
    table = score(bars, cfg)
    liked, newcomers = pick(table, cfg)
    held = sorted({t for d in cfg["desks"] for t in (store.get(f"paper-{d}_ledger") or {}).get("positions", {})}
                  | {t for d in cfg["desks"] for t in (store.get(f"live-{d}_ledger") or {}).get("positions", {})})
    wanted = sorted({r["symbol"] for r in liked + newcomers} | set(held))
    news = {}
    if news_on(cfg) and wanted:
        try:
            news = get_news(cfg, wanted, int((cfg.get("news") or {}).get("days", 3)))
        except Exception as e:
            store.log(f"[scan] couldn't read the news ({e!r}); the list is made without it today")
    state = update_list(cfg, liked, newcomers, news, today)
    flagged = [r["symbol"] for r in state["liked"] if r.get("danger")]
    return (f"scan: {len(bars)} stocks checked, {int(table['tradeable'].sum()) if len(table) else 0} tradeable, "
            f"{len(liked)} on the list (top: {', '.join(r['symbol'] for r in liked[:5]) or 'none'})"
            + (f"; danger news, not buying: {', '.join(flagged)}" if flagged else ""))
