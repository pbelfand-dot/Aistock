"""
dashboard.py: the bot's own web page, a brokerage-style view of your accounts.

Open it from the menu ("Open the dashboard"). It runs on YOUR Mac only:
  http://127.0.0.1:8765

What it shows: account value vs. the S&P 500, positions, activity, each desk's
phase, study report card and plan, the watchlist, and the bot's journal.
What you can do from it: PAUSE trading, or EMERGENCY STOP (sells everything the
bot owns). Everything else (approving plans, going live, resuming) stays in the
menu, where it asks you to type a confirmation.

It only reads the bot's own files (its database and saved prices). It never
talks to your broker, so it needs no keys.

Safety: the server only listens on this computer (127.0.0.1), rejects requests
addressed to any other host name, and every data or action request must carry a
secret key that only the page opened from the menu knows. Other websites can't
read your data or press the buttons.
"""
import json
import math
import os
import secrets
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

from .config import active_desks, data_path, data_source, desk_capital
from .market_hours import now_ny
from .performance import summarize
from .phases import STEP_NUMBER, current_phase, study_progress
from .storage import Store
from .study import day_forward_report, forward_report

WEB = Path(__file__).resolve().parent / "web" / "dashboard.html"
KILL_PHRASE = "SELL EVERYTHING"


# ================================================================ the data
def _num(x, digits=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), digits)


def _price_history(cfg, ticker):
    """The bot's saved prices for a ticker: (daily closes, 5-minute closes), either may be None."""
    out = []
    for interval in ("1d", "5m"):
        path = data_path(cfg, f"cache/{data_source(cfg)}/{interval}/{ticker}.csv")
        try:
            out.append(pd.read_csv(path, index_col=0, parse_dates=True)["close"].dropna() if path.exists() else None)
        except Exception:                          # e.g. the autopilot is rewriting that file right now
            out.append(None)
    return out


def quote(cfg, ticker) -> dict:
    """Last price, change since the previous close, and a small price trail for a sparkline."""
    daily, intraday = _price_history(cfg, ticker)
    if intraday is not None and len(intraday):
        last = float(intraday.iloc[-1])
        today = intraday.index[-1].normalize()
        before = intraday[intraday.index < today]
        prev = float(before.iloc[-1]) if len(before) else None
        if daily is not None and len(daily[daily.index < today]):
            prev = float(daily[daily.index < today].iloc[-1])
        trail = intraday[intraday.index >= today].tolist()
    elif daily is not None and len(daily):
        last = float(daily.iloc[-1])
        prev = float(daily.iloc[-2]) if len(daily) > 1 else None
        trail = daily.iloc[-30:].tolist()
    else:
        return {"ticker": ticker, "last": None, "change_pct": None, "trail": []}
    change = (last / prev - 1) * 100 if prev else None
    return {"ticker": ticker, "last": _num(last), "change_pct": _num(change), "trail": [_num(v) for v in trail]}


def _account(cfg, store, kind: str) -> dict:
    """One 'account' like a brokerage shows it: kind is "paper" or "live" (both desks together)."""
    live = kind == "live"
    desks, curves, positions, activity = {}, {}, [], []
    for desk in active_desks(cfg):
        mode = f"{kind}-{desk}"
        curve = store.equity_curve(mode)
        fills = store.fills(mode)
        ledger = store.get(f"{mode}_ledger")
        capital = desk_capital(cfg, desk, live)
        stats = summarize(curve, fills) if len(curve) else None
        if len(curve):
            curves[desk] = curve
        stop_pct = cfg["desks"][desk]["risk"]["stop_loss_pct"]
        holdings = 0.0
        for t, p in (ledger or {}).get("positions", {}).items():
            q = quote(cfg, t)
            last = q["last"] if q["last"] is not None else p["avg_cost"]
            value = last * p["qty"]
            cost = p["avg_cost"] * p["qty"]
            positions.append({"desk": desk, "ticker": t, "qty": p["qty"], "avg_cost": _num(p["avg_cost"]),
                              "last": _num(last), "day_change_pct": q["change_pct"], "market_value": _num(value),
                              "gain": _num(value - cost), "gain_pct": _num((value / cost - 1) * 100) if cost else None,
                              "stop": _num(p["avg_cost"] * (1 - stop_pct / 100)), "opened_on": p["opened_on"],
                              "stop_at_broker": bool(p.get("stop_order_id"))})
            holdings += value
        # Right now, like a brokerage shows it: cash + what it owns at the latest prices.
        now_value = ledger["cash"] + holdings if ledger else (float(curve.iloc[-1]) if len(curve) else None)
        desks[desk] = {"started": bool(len(curve) or ledger), "capital": capital, "value": _num(now_value),
                       "stats": stats}
        for f in fills.itertuples():
            activity.append({"id": f.id, "date": f.date, "desk": desk, "side": f.side, "qty": int(f.qty),
                             "ticker": f.ticker, "price": _num(f.price), "amount": _num(f.qty * f.price),
                             "realized_pnl": _num(f.realized_pnl) if f.side == "SELL" else None,
                             "reason": f.reason})

    # The account's value each day = the desks added up. A desk that hasn't started
    # yet counts as its money sitting in cash, so the line doesn't jump when it starts.
    series = {}
    if curves:
        dates = sorted(set().union(*[c.index for c in curves.values()]))
        idx = pd.DatetimeIndex(dates)
        total = pd.Series(0.0, index=idx)
        for desk in active_desks(cfg):
            c = curves.get(desk)
            filled = (c.reindex(idx).ffill().fillna(desk_capital(cfg, desk, live)) if c is not None
                      else pd.Series(desk_capital(cfg, desk, live), index=idx))
            total += filled
            if c is not None:
                series[desk] = [_num(v) for v in c.reindex(idx).ffill()]
        series["total"] = [_num(v) for v in total]
        bench = _benchmark(cfg, idx, float(total.iloc[0]))
        if bench is not None:
            series["benchmark"] = bench
        dates = [d.strftime("%Y-%m-%d") for d in idx]
    else:
        dates, total = [], pd.Series(dtype=float)

    value = sum((d["value"] if d["value"] is not None else d["capital"]) for d in desks.values())
    before_today = total[total.index < pd.Timestamp(now_ny().date())] if len(total) else total
    prev = float(before_today.iloc[-1]) if len(before_today) else None      # the last close before today
    start = float(total.iloc[0]) if len(total) else None
    cash = sum((store.get(f"{kind}-{d}_ledger") or {}).get("cash", 0.0) for d in desks)
    closed = [a["realized_pnl"] for a in activity if a["side"] == "SELL" and a["realized_pnl"] is not None]
    stats = summarize(total) if len(total) else None
    activity.sort(key=lambda a: (a["date"], a["id"]), reverse=True)
    return {
        "kind": kind,
        "active": any(d["started"] for d in desks.values()),
        "value": _num(value), "cash": _num(cash),
        "day_change": _num(value - prev) if prev else None,
        "day_change_pct": _num((value / prev - 1) * 100) if prev else None,
        "total_return_pct": _num((value / start - 1) * 100) if start else None,
        "max_drawdown_pct": stats["max_drawdown_pct"] if stats else None,
        "closed_trades": len(closed),
        "win_rate_pct": _num(sum(1 for c in closed if c > 0) / len(closed) * 100, 1) if closed else None,
        "desks": desks, "dates": dates, "series": series,
        "positions": sorted(positions, key=lambda p: -(p["market_value"] or 0)),
        "activity": activity[:300],
    }


def _benchmark(cfg, idx, start_value):
    daily, _ = _price_history(cfg, cfg["benchmark"])
    if daily is None or not len(daily):
        return None
    closes = daily.groupby(daily.index.normalize()).last().reindex(idx.normalize(), method="ffill")
    if closes.isna().all():
        return None
    first = closes.dropna().iloc[0]
    return [_num(v / first * start_value) if not pd.isna(v) else None for v in closes]


def _desk_info(cfg, store, desk) -> dict:
    phase = current_phase(store, desk)
    info = {"desk": desk, "phase": phase.value, "step": STEP_NUMBER[phase],
            "halted": bool(store.get(f"halted:{desk}")), "exiting": bool(store.get(f"exiting:{desk}")),
            "watchlist": cfg["desks"][desk]["watchlist"],
            "too_pricey": (store.get(f"too_pricey:{desk}") or {}).get("tickers", {})}
    card = forward_report(store, cfg) if desk == "swing" else day_forward_report(store)
    info["study"] = json.loads(card.reset_index().rename(columns={"index": "strategy"})
                               .to_json(orient="records")) if len(card) else []
    plan_path = data_path(cfg, f"trading_plan_{desk}.json")
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        info["plan"] = {"verdict": plan.get("verdict"), "strategy": plan.get("strategy"),
                        "created_on": plan.get("created_on"), "narrative": plan.get("narrative"),
                        "scorecard": [{"strategy": r["strategy"], "eligible": r["eligible"],
                                       "return_pct": r["backtest"].get("total_return_pct"),
                                       "sharpe": r["backtest"].get("sharpe"),
                                       "max_drawdown_pct": r["backtest"].get("max_drawdown_pct"),
                                       "trades": r["backtest"].get("num_closed_trades"),
                                       "study_month": r.get("forward", {}).get("summary"),
                                       "why_not": "; ".join(r.get("rejected_because", []))}
                                      for r in plan.get("scorecard", [])]}
    return info


def snapshot(cfg, store) -> dict:
    """Everything the page shows, in one go."""
    beat = store.get("autopilot_heartbeat")
    minutes = None
    if beat:
        minutes = round((now_ny() - datetime.fromisoformat(beat)).total_seconds() / 60, 1)
    progress = study_progress(store, cfg)
    return {
        "generated_at": now_ny().isoformat(timespec="seconds"),
        "demo": bool(store.get("demo")),
        "broker": cfg["broker"], "prices": data_source(cfg), "benchmark": cfg["benchmark"],
        "autopilot": {"last_seen": beat, "minutes_ago": minutes},
        "study": progress,
        "desks": [_desk_info(cfg, store, d) for d in active_desks(cfg)],
        "accounts": {"paper": _account(cfg, store, "paper"), "live": _account(cfg, store, "live")},
        "watchlist": [{"desk": d, **quote(cfg, t)} for d in active_desks(cfg) for t in cfg["desks"][d]["watchlist"]],
        "journal": [{"ts": ts, "message": m} for ts, m in store.journal(60)][::-1],
    }


# ================================================================ the web server
def token(cfg) -> str:
    """The dashboard's secret key (kept in data/, readable only by you)."""
    path = data_path(cfg, "dashboard_token")
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)     # private from the start
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(16))
    return path.read_text().strip()


def make_handler(cfg, actions: dict, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    key = token(cfg)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):                      # keep the menu/terminal quiet
            pass

        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            return self.headers.get("Host", "") in allowed_hosts

        def _key_ok(self):
            return secrets.compare_digest(self.headers.get("X-Token", ""), key)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "wrong host"})
            if self.path.split("?")[0] in ("/", "/index.html"):
                return self._send(200, WEB.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/ping":
                return self._send(200, {"app": "ai-trader"})
            if self.path == "/api/snapshot":
                if not self._key_ok():
                    return self._send(401, {"error": "open the dashboard from the AI Trader menu"})
                store = Store(data_path(cfg, "aitrader.sqlite"))       # one connection per request
                try:
                    return self._send(200, snapshot(cfg, store))
                except Exception as e:
                    return self._send(500, {"error": f"couldn't read the bot's data: {e}"})
                finally:
                    store.db.close()
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or not self._key_ok():
                return self._send(403, {"error": "not allowed"})
            try:
                length = max(0, min(int(self.headers.get("Content-Length") or 0), 10_000))
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            name = self.path.removeprefix("/api/")
            if name not in actions:
                return self._send(404, {"error": "not found"})
            if name == "kill" and body.get("confirm") != KILL_PHRASE:
                return self._send(400, {"error": f'type "{KILL_PHRASE}" to confirm'})
            try:
                return self._send(200, {"message": actions[name]()})
            except Exception as e:
                return self._send(500, {"error": str(e)})

    return Handler


def start(cfg, actions: dict, port: int = None):
    """Start the dashboard in the background. Returns the server, or None if the port is busy
    (usually because the background autopilot is already serving it)."""
    port = port or cfg.get("dashboard", {}).get("port", 8765)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg, actions, port))
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def url(cfg, port: int = None) -> str:
    port = port or cfg.get("dashboard", {}).get("port", 8765)
    return f"http://127.0.0.1:{port}/#t={token(cfg)}"


def is_running(cfg, port: int = None) -> bool:
    import urllib.request
    port = port or cfg.get("dashboard", {}).get("port", 8765)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return json.loads(r.read()).get("app") == "ai-trader"
    except Exception:
        return False
