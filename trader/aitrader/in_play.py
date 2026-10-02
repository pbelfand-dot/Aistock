"""
in_play.py: each morning, the stocks "in play" for the day desk.

A stock is in play when far more of it trades in the first 5 minutes than usual (relative volume):
news, earnings or big buyers are behind it, so it's more likely to keep moving. The research on
opening-range breakouts (Zarattini, Barbon & Aziz, 2024) found the method worked on stocks in play and
not on stocks picked at random; the day desk's own shadow trades on a fixed list agreed (ORB won 2 of 12).

1. Every evening the all-stocks scan (scanner.py) keeps the pool: the busiest stocks the day desk could
   trade ($5+, 1M+ shares a day, moves at least $0.50 a day, affordable: any price with fractional shares).
2. At 9:35 ET: how much of each traded 9:30-9:35, compared with its own average for that same 5 minutes
   over the last 14 days. The ones with the highest relative volume (at least `min_rvol`) join the day
   desk's list for today. Its fixed watchlist stays, so a failed scan never leaves it with nothing.
3. Each day's list is kept, so the report can show whether trades in stocks in play did better than
   trades in the fixed list: the bot learns it from its own results instead of taking the paper's word.

It picks stocks to WATCH. Whether anything is bought is still up to the day desk's method and its rules.
"""
import json
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import data_path

FILE = "in_play.json"
_pause = time.sleep                            # tests don't wait


def settings(cfg: dict) -> dict:
    s = {"enabled": True, "pool": 300, "picks": 10, "min_rvol": 1.0, "min_price": 5.0,
         "min_avg_volume": 1_000_000, "min_atr": 0.5, "history_days": 14,
         "premarket_min_gap_pct": 3.0, "premarket_min_volume_pct": 3.0, "premarket_picks": 8}
    s.update(cfg.get("in_play") or {})
    return s


def is_on(cfg: dict) -> bool:
    from .scanner import is_on as on
    return on(settings(cfg)["enabled"]) and "day" in (cfg.get("desks") or {})


def day_price_limit(cfg: dict) -> float:
    """The most one share can cost for the day desk (no limit with fractional shares)."""
    from .config import desk_capital
    from .risk import RiskManager
    return RiskManager.for_desk(cfg, "day").max_share_price(desk_capital(cfg, "day", False))


def pool(table: pd.DataFrame, cfg: dict) -> list:
    """From the evening scan: the busiest stocks the day desk could trade, most traded first."""
    s = settings(cfg)
    if table.empty or "atr" not in table:
        return []
    ok = table[(table["price"] >= s["min_price"]) & (table["price"] <= day_price_limit(cfg))
               & (table["avg_volume"] >= s["min_avg_volume"]) & (table["atr"] >= s["min_atr"])]
    ok = ok.sort_values("dollar_volume", ascending=False).head(int(s["pool"]))
    return [{"symbol": r.symbol, "price": float(r.price), "atr": round(float(r.atr), 2),
             "avg_volume": float(r.avg_volume)} for r in ok.itertuples()]


def swing_names(cfg: dict, store) -> set:
    """Stocks the swing desk watches, considers or holds: a stock is on one desk only."""
    from .scanner import trade_candidates
    names = set(((cfg.get("desks") or {}).get("swing") or {}).get("watchlist") or []) | set(trade_candidates(cfg))
    for kind in ("study", "paper", "live"):
        names |= set(((store.get(f"{kind}-swing_ledger") or {}).get("positions") or {}))
    return names


# ------------------------------------------------------------------ the opening 5 minutes
def opening_volumes(cfg: dict, symbols: list, days: list) -> dict:
    """{day: {symbol: shares traded 9:30-9:35}} from Alpaca (the same free IEX feed the day desk trades on,
    so today and the past are measured the same way). One small request per day and batch."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from .alpaca_api import data_client
    client, out = data_client(cfg), {}
    for day in days:
        start = opening_bar_start(day)
        out[day] = {}
        for i in range(0, len(symbols), 200):
            chunk = symbols[i:i + 200]
            for wait in (0, 5):
                if wait:
                    _pause(wait)
                try:
                    df = client.get_stock_bars(StockBarsRequest(
                        symbol_or_symbols=chunk, timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=start,
                        end=start + timedelta(minutes=4), feed=DataFeed.IEX)).df     # just the 9:30 bar
                    break
                except Exception:
                    df = None
            if df is None or df.empty:
                continue
            for sym, part in df.groupby(level="symbol"):
                part = part.droplevel("symbol")
                out[day][sym] = {"volume": float(part["volume"].iloc[0]), "open": float(part["open"].iloc[0]),
                                 "close": float(part["close"].iloc[-1])}
    return out


def opening_bar_start(day: str) -> datetime:
    """9:30am New York time on that day, in UTC (right in summer and winter, wherever the Mac is)."""
    from .market_hours import NEW_YORK
    d = datetime.strptime(day, "%Y-%m-%d")
    return d.replace(hour=9, minute=30, tzinfo=NEW_YORK).astimezone(timezone.utc)


def past_weekdays(today: str, n: int) -> list:
    """The n weekdays before today (a market holiday among them just has no bars, and is skipped)."""
    d, out = datetime.strptime(today, "%Y-%m-%d").date(), []
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return out


def rank(today_bars: dict, past: dict, cfg: dict) -> list:
    """Relative volume for each stock: today's opening 5 minutes / its average opening 5 minutes."""
    s, rows = settings(cfg), []
    for sym, bar in today_bars.items():
        history = [p[sym]["volume"] for p in past.values() if sym in p and p[sym]["volume"] > 0]
        if len(history) < 5 or bar["volume"] <= 0:
            continue                                  # too little history to call anything unusual
        rvol = bar["volume"] / (sum(history) / len(history))
        if rvol >= s["min_rvol"] and s["min_price"] <= bar["close"] <= day_price_limit(cfg):
            rows.append({"symbol": sym, "rvol": round(rvol, 1), "price": round(bar["close"], 2),
                         "first_5_min_pct": round((bar["close"] / bar["open"] - 1) * 100, 2) if bar["open"] else 0.0})
    rows.sort(key=lambda r: r["rvol"], reverse=True)
    return rows[:int(s["picks"])]


# ------------------------------------------------------------------ the morning job
def run(cfg: dict, store, today: str, get_volumes=opening_volumes, get_news=None) -> str:
    """Picks today's stocks in play and saves them. Returns a line for the journal."""
    from .alpaca_api import has_keys
    from .scanner import danger, fetch_news, load_list, news_on
    if not is_on(cfg):
        return "stocks in play: off"
    if not (has_keys(cfg, True) or has_keys(cfg, False)):
        return "stocks in play: needs Alpaca keys (the free plan is enough); the day desk uses its watchlist"
    busy = [r["symbol"] for r in load_list(cfg).get("day_pool") or []]
    if not busy:
        return "stocks in play: no pool yet (it comes from the evening scan); the day desk uses its watchlist"
    skip = swing_names(cfg, store)
    busy = [t for t in busy if t not in skip]
    days = past_weekdays(today, int(settings(cfg)["history_days"]) + 4)   # a few extra for holidays
    volumes = get_volumes(cfg, busy, [today] + days)
    if len(volumes.get(today) or {}) < len(busy) / 4:
        raise RuntimeError(f"only {len(volumes.get(today) or {})} of {len(busy)} stocks have a 9:30 bar yet")
    picks = rank(volumes[today], {d: volumes.get(d) or {} for d in days}, cfg)
    skipped = []
    if picks and news_on(cfg):                          # danger headlines (an offering, a halt...): not today
        try:
            news = (get_news or fetch_news)(cfg, [p["symbol"] for p in picks], 3)
        except Exception:
            news = {}
        for p in picks:
            p["danger"] = danger(news.get(p["symbol"], []))
        skipped = [f"{p['symbol']} ({', '.join(p['danger'])})" for p in picks if p["danger"]]
        picks = [p for p in picks if not p["danger"]]
    state = {"day": today, "checked": len(busy), "picks": picks, "skipped": skipped,
             "at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    save(cfg, state)
    history = store.get("in_play_history") or {}
    history[today] = [p["symbol"] for p in picks]
    store.set("in_play_history", {d: v for d, v in sorted(history.items())[-60:]})
    names = ", ".join(f"{p['symbol']} {p['rvol']}x" for p in picks) or "none unusual today"
    return (f"stocks in play: {len(busy)} busy stocks checked; added to the day desk's list: {names}"
            + (f"; skipped for danger news: {', '.join(skipped)}" if skipped else ""))


def save(cfg: dict, state: dict):
    path = data_path(cfg, FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(path)


def load(cfg: dict) -> dict:
    path = data_path(cfg, FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def today_picks(cfg: dict, today: str = None) -> list:
    """The day desk's extra stocks for today: the 9:35 picks ([] before then, or if the morning check didn't
    work), plus the pre-market movers once they've proven they help (challengers.py; until then they're
    only shadow traded)."""
    from .market_hours import now_ny
    if not is_on(cfg):
        return []
    today = today or now_ny().strftime("%Y-%m-%d")
    state, early = load(cfg), load_premarket(cfg)
    picks = [p["symbol"] for p in state.get("picks") or []] if state.get("day") == today else []
    if early.get("day") == today and early.get("trade"):
        picks += [p["symbol"] for p in early.get("picks") or [] if p["symbol"] not in picks]
    return picks


# ------------------------------------------------------------------ before the open: pre-market movers
PREMARKET_FILE = "premarket.json"


def premarket_volumes(cfg: dict, symbols: list, today: str, now: datetime) -> dict:
    """{symbol: {"volume", "last"}}: today's trading from 4:00am until 15 minutes ago, from the SIP feed (every
    exchange; the free plan may read it once it's 15 minutes old). One request per 200 stocks."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from .alpaca_api import data_client
    from .market_hours import NEW_YORK
    start = datetime.strptime(today, "%Y-%m-%d").replace(hour=4, tzinfo=NEW_YORK).astimezone(timezone.utc)
    end = min(now.replace(tzinfo=NEW_YORK) if now.tzinfo is None else now, opening_bar_start(today)) \
        .astimezone(timezone.utc) - timedelta(minutes=16)
    client, out = data_client(cfg), {}
    for i in range(0, len(symbols), 200):
        df = client.get_stock_bars(StockBarsRequest(
            symbol_or_symbols=symbols[i:i + 200], timeframe=TimeFrame(15, TimeFrameUnit.Minute), start=start, end=end,
            feed=DataFeed.SIP)).df
        if df is None or df.empty:
            continue
        for sym, part in df.groupby(level="symbol"):
            out[sym] = {"volume": float(part["volume"].sum()), "last": float(part["close"].iloc[-1])}
    return out


def premarket_rank(volumes: dict, pool_rows: list, cfg: dict) -> list:
    """Stocks gapping at least `premarket_min_gap_pct` from yesterday's close (either way) on heavy early
    trading (at least `premarket_min_volume_pct` of a normal day's volume before the open), busiest first."""
    s, rows = settings(cfg), []
    known = {r["symbol"]: r for r in pool_rows}
    for sym, v in volumes.items():
        r = known.get(sym) or {}
        prev, usual = r.get("price"), r.get("avg_volume")
        if not prev or not usual or v["volume"] <= 0:
            continue
        gap, share = (v["last"] / prev - 1) * 100, v["volume"] / usual * 100
        if abs(gap) >= s["premarket_min_gap_pct"] and share >= s["premarket_min_volume_pct"] \
                and s["min_price"] <= v["last"] <= day_price_limit(cfg):
            rows.append({"symbol": sym, "gap_pct": round(gap, 1), "volume_pct": round(share, 1),
                         "price": round(v["last"], 2)})
    rows.sort(key=lambda r: r["volume_pct"], reverse=True)
    return rows[:int(s["premarket_picks"])]


def premarket(cfg: dict, store, today: str, now: datetime, get_volumes=premarket_volumes, get_news=None) -> str:
    """About 9:20: the stocks moving on heavy trading before the open. Shown in the Thinking tab and the
    journal; the day desk trades them only once its shadow account with them has proven better."""
    from .alpaca_api import has_keys
    from .scanner import danger, fetch_news, load_list, news_on
    if not is_on(cfg):
        return ""
    if not (has_keys(cfg, True) or has_keys(cfg, False)):
        return "pre-market movers: needs Alpaca keys (the free plan is enough)"
    skip = swing_names(cfg, store)
    rows = [r for r in load_list(cfg).get("day_pool") or [] if r["symbol"] not in skip and r.get("avg_volume")]
    if not rows:
        return "pre-market movers: no pool yet (it comes from the evening scan)"
    picks = premarket_rank(get_volumes(cfg, [r["symbol"] for r in rows], today, now), rows, cfg)
    skipped = []
    if picks and news_on(cfg):
        try:
            news = (get_news or fetch_news)(cfg, [p["symbol"] for p in picks], 3)
        except Exception:
            news = {}
        skipped = [p["symbol"] for p in picks if danger(news.get(p["symbol"], []))]
        picks = [p for p in picks if p["symbol"] not in skipped]
    trade = bool(store.get("list_on:day:premarket"))
    state = {"day": today, "checked": len(rows), "picks": picks, "skipped": skipped, "trade": trade,
             "at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    path = data_path(cfg, PREMARKET_FILE)
    path.write_text(json.dumps(state, indent=1))
    history = store.get("premarket_history") or {}
    history[today] = [p["symbol"] for p in picks]
    store.set("premarket_history", {d: v for d, v in sorted(history.items())[-60:]})
    names = ", ".join(f"{p['symbol']} {p['gap_pct']:+.1f}% on {p['volume_pct']:.0f}% of a day's volume" for p in picks)
    return (f"pre-market movers ({len(rows)} busy stocks checked): {names or 'none moving on heavy volume'}"
            + ("" if trade or not picks else "; watched in a shadow account until they prove they help"))


def load_premarket(cfg: dict) -> dict:
    path = data_path(cfg, PREMARKET_FILE)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def premarket_today(cfg: dict, today: str) -> list:
    """Today's pre-market movers (symbols), whether or not the day desk trades them yet."""
    state = load_premarket(cfg)
    return [p["symbol"] for p in state.get("picks") or []] if state.get("day") == today else []


def results(fills: pd.DataFrame, history: dict) -> dict:
    """Finished day trades split by whether the stock was in play that day: {"in play": {...}, "fixed list": {...}}."""
    out = {k: {"trades": 0, "won": 0, "pnl": 0.0} for k in ("in play", "fixed list")}
    if fills is None or fills.empty:
        return out
    sells = fills[fills["side"] == "SELL"]
    for row in sells.itertuples():
        day = str(row.date)[:10]
        group = out["in play" if row.ticker in (history.get(day) or []) else "fixed list"]
        group["trades"] += 1
        group["won"] += int(float(row.realized_pnl) > 0)
        group["pnl"] = round(group["pnl"] + float(row.realized_pnl), 2)
    return out
