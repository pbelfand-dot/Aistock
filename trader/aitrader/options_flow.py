"""
options_flow.py: the options-gap watcher. It watches and grades; it never trades.

The idea comes from a "Claude agent" video: compare what a stock's PRICE is doing with where the money
in its OPTIONS is betting, and flag the gap. Once a day after the close, for each stock Kestrel watches:
  - the price: its change over the last 5 trading days;
  - the bets: the share of the day's option volume that was CALLS (Alpaca's free option data: each
    contract's daily volume, expirations in the next 45 days), against that stock's own normal share.
A GAP is when the two disagree:
  - bullish gap: calls unusually heavy while the price hasn't gone up (bets ahead of the price);
  - bearish gap: puts unusually heavy while the price hasn't gone down.
Every gap is graded 5 trading days later against SPY: did the stock beat the market (bullish) or trail
it (bearish)? The scorecard shows in the app and the after-market report.

Why only watching: research found that option BUYERS' bets predicted next-week returns (Pan & Poteshman
2006), but public volume can't tell buyers from sellers, large option trades in general don't predict
(Jiang & Strong), and the effect is weakest in the biggest stocks. So Kestrel keeps score first. The
Risk agent (agents.py) may use a bearish gap to skip a buy only if you switch that on, and only once
the scorecard shows an edge.
"""
import time
from datetime import date, timedelta

import pandas as pd

DATA_URL = "https://data.alpaca.markets/v1beta1/options/snapshots/{symbol}"
HISTORY_KEY = "options_flow_history"                 # {symbol: [{date, call_share, volume}]}
SIGNALS_KEY = "options_gap_signals"                  # every gap it flagged, with its grade
SETTINGS = {"enabled": True, "expiry_days": 45, "min_volume": 2000, "horizon_days": 5, "max_symbols": 60,
            "unusual": 0.12, "flat_pct": 1.0}


def settings(cfg: dict) -> dict:
    return {**SETTINGS, **(cfg.get("options_watch") or {})}


def symbols_to_watch(cfg: dict) -> list:
    """The swing desk's list and scan picks, then the day desk's stocks (each once)."""
    from .scanner import trade_candidates
    desks = cfg.get("desks") or {}
    names = list((desks.get("swing") or {}).get("watchlist") or []) + trade_candidates(cfg) \
        + list((desks.get("day") or {}).get("watchlist") or [])
    return list(dict.fromkeys(names))[:int(settings(cfg)["max_symbols"])]


def option_type(occ_symbol: str) -> str:
    """'C' or 'P' from an OCC option symbol like NVDA251017C00195000."""
    return occ_symbol[-9] if len(occ_symbol) > 9 else ""


def fetch_volume(cfg: dict, symbol: str, day: str, session=None) -> tuple:
    """(call volume, put volume) for one stock on `day`, from Alpaca's free option chain snapshots."""
    import requests
    from .alpaca_api import keys
    key, secret = keys(cfg, True)
    if not (key and secret):
        key, secret = keys(cfg, False)
    session = session or requests
    params = {"feed": "indicative", "limit": 1000,
              "expiration_date_lte": (date.fromisoformat(day) + timedelta(days=int(settings(cfg)["expiry_days"]))).isoformat()}
    calls = puts = 0
    for _ in range(20):                                   # pages of up to 1,000 contracts
        resp = session.get(DATA_URL.format(symbol=symbol), params=params, timeout=30,
                           headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        resp.raise_for_status()
        body = resp.json()
        for occ, snap in (body.get("snapshots") or {}).items():
            bar = (snap or {}).get("dailyBar") or {}
            if not str(bar.get("t", ""))[:10] == day:     # a bar from another day isn't today's betting
                continue
            volume = int(bar.get("v") or 0)
            if option_type(occ) == "C":
                calls += volume
            elif option_type(occ) == "P":
                puts += volume
        token = body.get("next_page_token")
        if not token:
            break
        params["page_token"] = token
        time.sleep(0.2)                                   # stay well under the free plan's request limit
    return calls, puts


def classify(call_share: float, baseline, price_5d_pct: float, s: dict) -> str:
    """'bullish', 'bearish' or '' (the bets and the price agree: no gap)."""
    if baseline is None:                                  # under 5 days of history: plain thresholds
        heavy_calls, heavy_puts = call_share >= 0.75, call_share <= 0.35
    else:
        heavy_calls = call_share >= max(0.60, baseline + s["unusual"])
        heavy_puts = call_share <= min(0.50, baseline - s["unusual"])
    if heavy_calls and price_5d_pct <= s["flat_pct"]:
        return "bullish"
    if heavy_puts and price_5d_pct >= -s["flat_pct"]:
        return "bearish"
    return ""


def _change(closes: pd.Series, days: int):
    closes = closes.dropna()
    return None if len(closes) <= days else float((closes.iloc[-1] / closes.iloc[-1 - days] - 1) * 100)


def observe(cfg: dict, store, day: str, closes: dict, fetch=fetch_volume) -> dict:
    """Today's look: updates each stock's normal call share, flags the gaps, and grades old ones.
    closes: {symbol: daily closes (pd.Series)}, including the benchmark."""
    s = settings(cfg)
    history = store.get(HISTORY_KEY) or {}
    signals = store.get(SIGNALS_KEY) or []
    bench = closes.get(cfg["benchmark"])
    flags, looked, errors = [], 0, []
    for symbol in symbols_to_watch(cfg):
        series = closes.get(symbol)
        if series is None or not len(series):
            continue
        try:
            calls, puts = fetch(cfg, symbol, day)
        except Exception as e:                            # one stock's data problem never stops the rest
            errors.append(f"{symbol} ({type(e).__name__})")
            continue
        total = calls + puts
        if total < s["min_volume"]:
            continue
        looked += 1
        share = calls / total
        past = [h for h in history.get(symbol, []) if h["date"] < day][-20:]
        baseline = sum(h["call_share"] for h in past) / len(past) if len(past) >= 5 else None
        price_5d = _change(series, 5)
        history[symbol] = past + [{"date": day, "call_share": round(share, 3), "volume": total}]
        if price_5d is None:
            continue
        direction = classify(share, baseline, price_5d, s)
        if direction:
            flag = {"date": day, "symbol": symbol, "direction": direction, "call_share": round(share, 3),
                    "baseline": None if baseline is None else round(baseline, 3), "volume": total,
                    "price_5d_pct": round(price_5d, 2), "close": round(float(series.dropna().iloc[-1]), 4),
                    "bench_close": None if bench is None else round(float(bench.dropna().iloc[-1]), 4),
                    "excess_pct": None, "right": None}
            flags.append(flag)
            signals = [x for x in signals if not (x["date"] == day and x["symbol"] == symbol)] + [flag]
    signals = grade(signals, closes, cfg["benchmark"], int(s["horizon_days"]))
    store.set(HISTORY_KEY, history)
    store.set(SIGNALS_KEY, signals[-2000:])
    store.set("options_gap_today", {"date": day, "looked": looked, "flags": flags, "errors": errors[:10]})
    return {"looked": looked, "flags": flags, "errors": errors}


def grade(signals: list, closes: dict, benchmark: str, horizon: int) -> list:
    """Each gap, once `horizon` trading days have passed: the stock's return minus the market's."""
    bench = closes.get(benchmark)
    for x in signals:
        if x["right"] is not None or bench is None or x.get("bench_close") is None:
            continue
        series = closes.get(x["symbol"])
        if series is None:
            continue
        after = bench[bench.index > pd.Timestamp(x["date"])]
        if len(after) < horizon:
            continue
        when = after.index[horizon - 1]
        stock_then = series[series.index <= when].dropna()
        if not len(stock_then):
            continue
        stock_ret = float(stock_then.iloc[-1]) / x["close"] - 1
        bench_ret = float(after.iloc[horizon - 1]) / x["bench_close"] - 1
        x["excess_pct"] = round((stock_ret - bench_ret) * 100, 2)
        x["right"] = (x["excess_pct"] > 0) if x["direction"] == "bullish" else (x["excess_pct"] < 0)
    return signals


def scorecard(store) -> dict:
    """How the gaps did: per direction, graded count, how often right, the average move vs the market
    in the predicted direction. 'edge' needs 20+ graded calls, right 55%+, and a positive average."""
    signals = store.get(SIGNALS_KEY) or []
    out = {}
    for direction in ("bullish", "bearish"):
        graded = [x for x in signals if x["direction"] == direction and x["right"] is not None]
        sign = 1 if direction == "bullish" else -1
        right = sum(1 for x in graded if x["right"])
        avg = sum(sign * x["excess_pct"] for x in graded) / len(graded) if graded else None
        out[direction] = {"graded": len(graded), "right_pct": round(right / len(graded) * 100, 1) if graded else None,
                          "avg_edge_pct": None if avg is None else round(avg, 2),
                          "waiting": sum(1 for x in signals if x["direction"] == direction and x["right"] is None)}
        out[direction]["edge"] = bool(graded and len(graded) >= 20 and right / len(graded) >= 0.55 and avg > 0)
    return out


def run(cfg: dict, store, data, day: str) -> str:
    """The autopilot's daily job (after the close). Never raises: the watcher must never stop the day."""
    s = settings(cfg)
    if not s["enabled"]:
        return "options watcher: off"
    from .alpaca_api import has_keys
    if not (has_keys(cfg, True) or has_keys(cfg, False)):
        return "options watcher: needs Alpaca keys (Setup)"
    try:
        closes = {}
        for symbol in symbols_to_watch(cfg) + [cfg["benchmark"]]:
            try:
                closes[symbol] = data.history(symbol, "1d")["close"]
            except Exception:
                continue
        result = observe(cfg, store, day, closes)
    except Exception as e:
        store.log(f"Options-gap watcher: couldn't run today ({e!r})")
        return "options watcher: failed (see the journal)"
    flags = result["flags"]
    store.log(f"Options-gap watcher: looked at {result['looked']} stocks; gaps: "
              + (", ".join(f"{f['symbol']} {f['direction']}" for f in flags) or "none")
              + " (testing only, no trades)")
    return f"options watcher: {result['looked']} stocks, {len(flags)} gaps"


def gaps_today(store) -> dict:
    """{symbol: 'bullish'/'bearish'} from the latest look (what the agents read)."""
    today = store.get("options_gap_today") or {}
    return {f["symbol"]: f["direction"] for f in today.get("flags", [])}


def report_lines(store) -> list:
    """The after-market report's section."""
    today = store.get("options_gap_today") or {}
    card = scorecard(store)
    out = ["## Options-gap watcher (testing only: it never trades on this)", ""]
    if not today:
        out += ["- Not run yet (it needs Alpaca keys and runs after each close).", ""]
        return out
    flags = today.get("flags", [])
    out.append(f"- {today['date']}: looked at {today['looked']} stocks; gaps: "
               + (", ".join(f"{f['symbol']} {f['direction']} ({f['call_share'] * 100:.0f}% calls, price "
                            f"{f['price_5d_pct']:+.1f}% in 5 days)" for f in flags) or "none") + ".")
    for direction, c in card.items():
        if c["graded"]:
            out.append(f"- {direction.title()} gaps so far: {c['graded']} graded, right {c['right_pct']}%, "
                       f"average {c['avg_edge_pct']:+.2f}% vs the market"
                       + (" (shows an edge)" if c["edge"] else " (no proven edge yet)") + f"; {c['waiting']} waiting.")
        elif c["waiting"]:
            out.append(f"- {direction.title()} gaps: {c['waiting']} waiting to be graded (5 trading days).")
    out.append("")
    return out
