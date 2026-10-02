"""
weekend.py: practice on Saturdays and Sundays, while the stock market is closed. Two separate
experiments. Neither ever counts toward Stage 1, real money, or what the desks learn from their own
trades (their mistake memory and lessons read only the in-its-head, paper and real accounts):

  1. Replay (accounts weekend-swing and weekend-day): real past trading days, from the 5-minute and
     daily prices already saved on this Mac, replayed fast (about 30 minutes per trading day) through
     each desk's own strategy, team and risk rules. The swing desk decides at 3:45pm of each replayed day
     (on that day's closing prices, a small head start), the day desk every 5 minutes. Consecutive days,
     a different stretch each weekend. A practice run, not new evidence: the strategies were chosen
     by testing this same history.
  2. Crypto (account weekend-crypto): pretend money against LIVE crypto prices (Alpaca's free crypto
     data, no keys needed), using the swing desk's strategy on hourly bars: a decision at the top of
     every hour, stop-losses every 5 minutes, everything sold Sunday at 11:50pm. Nothing goes to any
     broker, so it can't mix with Stage 1's stocks in your Alpaca paper account. An experiment:
     Kestrel's strategies were only ever tested on stocks.

Each weekend starts fresh. The Thinking tab shows both, live; the journal gets one line per replayed
day and a summary at the end of the weekend.
"""
import random
import threading
import time
from dataclasses import fields
from datetime import datetime, timedelta

import pandas as pd

from .config import data_path, data_source, desk_capital
from .market_hours import now_ny
from .storage import Store

REPLAY_MODES = {"swing": "weekend-swing", "day": "weekend-day"}
CRYPTO_MODE = "weekend-crypto"
MODES = (*REPLAY_MODES.values(), CRYPTO_MODE)
SKIP_RECENT_DAYS = 10            # don't replay the last two weeks: the desks just lived them
IN_BACKGROUND = True             # tests replay inline
_replaying = None                # the replay thread, if any
_pause = time.sleep              # tests don't wait
_clock = now_ny                  # tests pick the day


def settings(cfg: dict) -> dict:
    s = {"replay": True, "replay_minutes_per_day": 30, "crypto": True, "crypto_budget": 500,
         "crypto_strategy": "momentum", "crypto_history_days": 30,
         "crypto_coins": ["BTC/USD", "ETH/USD", "LTC/USD", "DOGE/USD", "AVAX/USD", "LINK/USD", "BCH/USD",
                          "DOT/USD", "UNI/USD", "AAVE/USD"],
         "crypto_risk": {"max_open_positions": 3, "max_position_pct": 33, "stop_loss_pct": 5,
                         "daily_loss_limit_pct": 5, "max_drawdown_pct": 20, "cash_buffer_pct": 1}}
    s.update(cfg.get("weekend") or {})
    for key in ("replay", "crypto"):
        s[key] = str(s[key]).strip().lower() not in ("off", "false", "no", "0")
    return s


def is_weekend(now: datetime) -> bool:
    return now.weekday() >= 5


def weekend_of(now: datetime) -> str:
    """The Saturday this weekend began (each weekend starts fresh)."""
    return (now.date() - timedelta(days=now.weekday() - 5)).isoformat()


def quiet(store_path) -> Store:
    """A database connection whose journal lines are dropped: the engine notes each moment ("no trades
    today"), which would flood the journal during a fast replay. Weekend summaries use the real one."""
    s = Store(store_path)
    s.log = lambda *a, **k: None
    return s


# ---------------------------------------------------------------- the weekend's start and end
def state(store) -> dict:
    return store.get("weekend_state") or {}


def start(cfg, store, now) -> dict:
    """A new weekend: clear last weekend's practice accounts and pick the days to replay."""
    s = settings(cfg)
    current = state(store)
    sat = weekend_of(now)
    if current.get("weekend") == sat:
        return current
    for mode in MODES:
        store.clear_mode(mode)
        for key in ("ledger", "peak_equity", "thinking", "checks", "watch", "decisions", "no_buys_logged"):
            store.set(f"{mode}_{key}", None)
    days = replay_days(cfg, store) if s["replay"] else []
    new = {"weekend": sat, "days": days, "i": 0, "bar": 0, "done": [], "summarized": False}
    store.set("weekend_state", new)
    store.set("weekend_crypto", {"weekend": sat, "hour": None, "closed": False})
    store.set("weekend_now", None)
    what = []
    if days:
        what.append(f"replaying real past trading days from {days[0]} (about "
                    f"{s['replay_minutes_per_day']} minutes per day)")
    elif s["replay"]:
        what.append("no replay: not enough 5-minute prices saved on this Mac yet")
    if s["crypto"]:
        what.append(f"crypto with ${s['crypto_budget']:,.0f} of pretend money at live prices")
    store.log("[weekend] practice starts: " + "; ".join(what or ["both experiments are off (Setup)"])
              + ". None of it counts toward Stage 1 or real money.")
    return new


def results(store, cfg=None) -> dict:
    """{mode: {trades, wins, gain, value, start, change}} for the weekend's practice accounts: finished
    trades and their gain, and the account's value now (open positions too) against where it started."""
    from .learning import round_trips
    starts = {}
    if cfg is not None:
        starts = {REPLAY_MODES[d]: desk_capital(cfg, d, False) for d in REPLAY_MODES if d in cfg["desks"]}
        starts[CRYPTO_MODE] = float(settings(cfg)["crypto_budget"])
    out = {}
    for mode in MODES:
        fills = store.fills(mode)
        trips = round_trips(fills) if fills is not None and len(fills) else []
        curve = store.equity_curve(mode)
        ledger = store.get(f"{mode}_ledger")
        value = round(float(curve.iloc[-1]), 2) if len(curve) else (ledger or {}).get("cash")
        start = starts.get(mode)
        out[mode] = {"trades": len(trips), "wins": sum(1 for t in trips if t["pnl"] > 0),
                     "gain": round(sum(t["pnl"] for t in trips), 2), "value": value, "start": start,
                     "change": round(value - start, 2) if value is not None and start else None}
    return out


def summarize(cfg, store, now) -> str:
    """Once, after the weekend: one journal line with how each practice account did."""
    st = state(store)
    if not st.get("weekend") or st.get("summarized") or (is_weekend(now) and weekend_of(now) == st["weekend"]):
        return ""
    r = results(store, cfg)
    names = {"weekend-swing": "replay swing desk", "weekend-day": "replay day desk", "weekend-crypto": "crypto"}
    parts = [f"{names[m]}: {x['trades']} trades, {x['wins']} won, {'+' if x['gain'] >= 0 else '-'}"
             f"${abs(x['gain']):,.2f}" for m, x in r.items() if x["trades"] or store.get(f"{m}_ledger")]
    days = len(st.get("done", []))
    line = (f"[weekend] practice over: {days} past trading day{'s' if days != 1 else ''} replayed"
            + (f" ({st['done'][0]} to {st['done'][-1]})" if days else "") + "; "
            + ("; ".join(parts) or "no trades") + ". Practice only: none of it counts toward Stage 1 or real money.")
    store.set("weekend_state", {**st, "summarized": True, "results": r})
    history = (store.get("weekend_history") or [])[-7:]
    store.set("weekend_history", history + [{"weekend": st["weekend"], "days": st.get("done", []), "results": r}])
    store.log(line)
    return line


# ---------------------------------------------------------------- 1. replay
def cached(cfg, interval: str, ticker: str) -> pd.DataFrame:
    """Prices saved on this Mac by market_data.py (no downloads on the weekend)."""
    path = data_path(cfg, f"cache/{data_source(cfg)}/{interval}/{ticker}.csv")
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"]).sort_index() if len(df) else None


def replay_days(cfg, store, seed=None) -> list:
    """Consecutive past trading days with 5-minute prices, starting somewhere the bot hasn't replayed yet
    (and not the last two weeks)."""
    spy = cached(cfg, "5m", cfg["benchmark"])
    if spy is None:
        return []
    days = sorted({d.date().isoformat() for d in spy.index})
    cutoff = (_clock().date() - timedelta(days=SKIP_RECENT_DAYS)).isoformat()
    days = [d for d in days[5:] if d <= cutoff]            # the first few days are history for the strategies
    if not days:
        return []
    seen = set(store.get("weekend_replayed") or [])
    fresh = [i for i, d in enumerate(days) if d not in seen] or list(range(len(days)))
    first = random.Random(seed).choice(fresh[:max(1, len(fresh) - 20)])
    return days[first:first + 120]


def _strategy(cfg, store, desk):
    """The strategy the desk trades now (in its head: the study strategy; paper or real: its plan)."""
    import run
    from .phases import current_phase
    from .strategies import get_strategy
    phase = current_phase(store, desk)
    name = run.desk_strategy_name(cfg, store, desk, phase)
    return get_strategy(name, cfg, desk)


def _broker(cfg, store, desk, mode):
    from .brokers import Ledger, PaperBroker
    from .config import cents_per_share, is_cash_account
    saved = store.get(f"{mode}_ledger")
    ledger = Ledger.from_dict(saved) if saved else Ledger(desk_capital(cfg, desk, False))
    broker = PaperBroker(ledger, cfg["paper"]["slippage_pct"], cfg["paper"]["commission_per_trade"], mode=mode,
                         cash_account=is_cash_account(cfg), cents_per_share=cents_per_share(cfg, desk))
    broker.on_fill = lambda f: store.record_fill(mode, f)
    return broker


def replay_moment(cfg, store, prices: dict, day: str, when: pd.Timestamp):
    """One 5-minute moment of a replayed day: the day desk decides; at 3:45pm the swing desk too."""
    from .engine import run_cycle
    from .risk import RiskManager
    from .config import active_desks
    desks = active_desks(cfg)
    strategies = prices.setdefault("strategies", {})
    for desk in desks:
        if desk not in strategies:
            strategies[desk] = _strategy(cfg, store, desk)
    if "day" in desks and prices["day"]:
        bars = {t: df.loc[:when] for t, df in prices["day"].items()}
        bars = {t: df for t, df in bars.items() if len(df) and df.index[-1].date().isoformat() == day}
        market = prices["spy5"].loc[:when]
        if bars and len(market):
            broker = _broker(cfg, store, "day", REPLAY_MODES["day"])
            run_cycle(store, broker, strategies["day"], RiskManager.for_desk(cfg, "day"), bars, market,
                      when.to_pydatetime(), cfg["desks"]["day"], cfg=cfg, practice=True)
            store.set(f"{broker.mode}_ledger", broker.ledger.to_dict())
    if "swing" in desks and prices["swing"] and when.strftime("%H:%M") == "15:45":
        bars = {t: df.loc[:day] for t, df in prices["swing"].items()}
        bars = {t: df for t, df in bars.items() if len(df) and df.index[-1].date().isoformat() == day}
        market = prices["spy1"].loc[:day]
        if bars and len(market):
            broker = _broker(cfg, store, "swing", REPLAY_MODES["swing"])
            run_cycle(store, broker, strategies["swing"], RiskManager.for_desk(cfg, "swing"), bars,
                      market, when.to_pydatetime(), cfg["desks"]["swing"], cfg=cfg, practice=True)
            store.set(f"{broker.mode}_ledger", broker.ledger.to_dict())


def load_prices(cfg) -> dict:
    day = {t: df for t in cfg["desks"]["day"]["watchlist"] if (df := cached(cfg, "5m", t)) is not None}
    swing = {t: df for t in cfg["desks"]["swing"]["watchlist"] if (df := cached(cfg, "1d", t)) is not None}
    return {"day": day, "swing": swing, "spy5": cached(cfg, "5m", cfg["benchmark"]),
            "spy1": cached(cfg, "1d", cfg["benchmark"])}


def replay(cfg, path, until=None) -> int:
    """Replays the weekend's days, one 5-minute moment at a time, from where it left off (it survives a
    restart). Stops when the weekend ends. Returns how many moments it played."""
    s = settings(cfg)
    store, log = quiet(path), Store(path)
    played = 0
    try:
        prices = load_prices(cfg)
        if prices["spy5"] is None:
            return 0
        pace = s["replay_minutes_per_day"] * 60 / 78
        by_day = {d: g.index for d, g in prices["spy5"].groupby(prices["spy5"].index.strftime("%Y-%m-%d"))}
        while True:
            st = state(store)
            now = _clock()
            if not is_weekend(now) or weekend_of(now) != st.get("weekend") or st["i"] >= len(st["days"]):
                return played
            day = st["days"][st["i"]]
            moments = by_day.get(day, [])
            if st["bar"] < len(moments):
                when = moments[st["bar"]]
                store.set("weekend_now", {"day": day, "time": when.strftime("%H:%M"), "n": st["i"] + 1,
                                          "at": now.isoformat(timespec="seconds")})
                replay_moment(cfg, store, prices, day, when)
                store.set("weekend_state", {**state(store), "bar": st["bar"] + 1})
                played += 1
                if until is not None and played >= until:
                    return played
                _pause(pace)
                continue
            r = results(store)                               # the day is over: one journal line
            day_r, swing_r = r[REPLAY_MODES["day"]], r[REPLAY_MODES["swing"]]
            log.log(f"[weekend] replayed {datetime.strptime(day, '%Y-%m-%d'):%a %b %d, %Y}: so far this weekend "
                    f"the day desk made {day_r['trades']} trades ({'+' if day_r['gain'] >= 0 else '-'}"
                    f"${abs(day_r['gain']):,.2f}), the swing desk {swing_r['trades']} "
                    f"({'+' if swing_r['gain'] >= 0 else '-'}${abs(swing_r['gain']):,.2f})", echo=False)
            store.set("weekend_replayed", sorted(set(store.get("weekend_replayed") or []) | {day})[-2000:])
            store.set("weekend_state", {**state(store), "i": st["i"] + 1, "bar": 0, "done": st["done"] + [day]})
    finally:
        store.db.close()
        log.db.close()


def replay_running() -> bool:
    return _replaying is not None and _replaying.is_alive()


def keep_replaying(cfg, store) -> str:
    global _replaying
    if replay_running() or not settings(cfg)["replay"] or not state(store).get("days"):
        return ""
    path = data_path(cfg, "aitrader.sqlite")
    if not IN_BACKGROUND:
        return f"replayed {replay(cfg, path)} moments"
    _replaying = threading.Thread(target=replay, args=(cfg, path), daemon=True, name="weekend-replay")
    _replaying.start()
    return "weekend replay started in the background"


# ---------------------------------------------------------------- 2. crypto
def crypto_bars(cfg, coins: list, days: int) -> dict:
    """Hourly bars from Alpaca's crypto data (free, no keys needed), in New York time."""
    from alpaca.data.historical.crypto import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from .alpaca_api import timed
    from datetime import timezone
    client = timed(CryptoHistoricalDataClient())
    df = client.get_crypto_bars(CryptoBarsRequest(symbol_or_symbols=coins, timeframe=TimeFrame.Hour,
                                                  start=datetime.now(timezone.utc) - timedelta(days=days))).df
    out = {}
    if df is None or df.empty:
        return out
    for coin, part in df.groupby(level="symbol"):
        part = part.droplevel("symbol")
        part.index = pd.DatetimeIndex(pd.to_datetime(part.index, utc=True).tz_convert("America/New_York")
                                      .tz_localize(None))
        out[coin] = part[["open", "high", "low", "close", "volume"]].sort_index()
    return out


def crypto_check(cfg, store, now, fetch=crypto_bars) -> str:
    """Every 5 minutes on the weekend: stop-losses; at the top of each hour, a decision; Sunday 11:50pm,
    sell everything (the experiment's weekend is over)."""
    from .brokers import Ledger, PaperBroker
    from .engine import execute, run_cycle, sell_all
    from .risk import RiskManager
    from .strategies import get_strategy
    s = settings(cfg)
    st = store.get("weekend_crypto") or {}
    if not s["crypto"] or st.get("closed") or st.get("weekend") != weekend_of(now):
        return ""
    coins = list(dict.fromkeys(s["crypto_coins"]))
    bars = fetch(cfg, coins, int(s["crypto_history_days"]))
    if not bars or "BTC/USD" not in bars:
        return "crypto: no prices"
    market = bars["BTC/USD"]                                  # the yardstick, like the S&P 500 for stocks
    saved = store.get(f"{CRYPTO_MODE}_ledger")
    broker = PaperBroker(Ledger.from_dict(saved) if saved else Ledger(float(s["crypto_budget"])),
                         cfg["paper"]["slippage_pct"], mode=CRYPTO_MODE)
    broker.on_fill = lambda f: store.record_fill(CRYPTO_MODE, f)
    if now.weekday() == 6 and now.time() >= datetime.strptime("23:50", "%H:%M").time():
        prices = pd.Series({t: float(df["close"].iloc[-1]) for t, df in bars.items()})
        fills = execute(sell_all(broker.positions(), prices, "the weekend is over: crypto practice ends"),
                        broker, now.strftime("%Y-%m-%d"))
        store.set(f"{CRYPTO_MODE}_ledger", broker.ledger.to_dict())
        store.record_equity(CRYPTO_MODE, now.strftime("%Y-%m-%d"), broker.equity(prices), broker.cash())
        store.set("weekend_crypto", {**st, "closed": True})
        return f"crypto: sold {len(fills)} position(s), the weekend is over"
    hour = now.strftime("%Y-%m-%d %H")
    decide = st.get("hour") != hour and now.minute < 10
    known = {f.name for f in fields(RiskManager)} - {"fractional"}
    risk = RiskManager(**{k: v for k, v in {**cfg["desks"]["swing"]["risk"], **s["crypto_risk"]}.items()
                          if k in known}, fractional=True)          # coins are bought in parts
    strategy = get_strategy(s["crypto_strategy"], cfg, "swing")
    run_cycle(store, broker, strategy, risk, bars, market, now, cfg["desks"]["swing"], stops_only=not decide,
              cfg=cfg if decide else None, practice=True)
    store.set(f"{CRYPTO_MODE}_ledger", broker.ledger.to_dict())
    if decide:
        store.set("weekend_crypto", {**st, "hour": hour})
    return f"crypto: {'decided' if decide else 'checked stop-losses'}"


# ---------------------------------------------------------------- the autopilot's weekend
def tick(cfg, store, now) -> str:
    """Called by the autopilot every 5 minutes. Weekends: start (once), keep the replay going, crypto.
    Weekdays: the summary of the weekend that just ended (once)."""
    if not is_weekend(now):
        return summarize(cfg, store, now)
    start(cfg, store, now)
    said = [keep_replaying(cfg, store)]
    own = quiet(data_path(cfg, "aitrader.sqlite"))
    try:
        said.append(crypto_check(cfg, own, now))
    except Exception as e:                                    # crypto prices unreachable: try again in 5 minutes
        said.append(f"crypto: couldn't get prices ({e!r})")
    finally:
        own.db.close()
    return "; ".join(x for x in said if x)
