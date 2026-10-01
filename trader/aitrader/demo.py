"""
demo.py: DEMO data, so you can see the dashboard before the bot has traded.

It makes up prices (a random walk) for the watchlist, then runs them through the
bot's REAL code: the study month, the plans and a few weeks of paper trading.
Everything goes into its own folder (data/demo); your real data is never touched,
and the app shows a DEMO banner the whole time.
"""
import copy
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .brokers import Ledger, PaperBroker
from .config import active_desks, desk_capital, is_cash_account
from .engine import run_cycle
from .market_hours import now_ny
from .phases import Phase, set_phase
from .planner import build_plan
from .risk import RiskManager
from .storage import Store
from .strategies import get_strategy
from .study import record_study_day, study_day, study_swing

DAYS, INTRADAY_DAYS, PAPER_DAYS, DAY_DESK_PAPER_DAYS = 420, 30, 30, 8


def _bars(index, start_price, market_returns, rng, beta, noise, drift):
    close = start_price * np.cumprod(1 + beta * market_returns + rng.normal(drift, noise, len(index)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + rng.uniform(0, 0.006, len(index))),
                         "low": np.minimum(open_, close) * (1 - rng.uniform(0, 0.006, len(index))), "close": close,
                         "volume": rng.integers(200_000, 900_000, len(index)).astype(float)}, index=index)


def demo_config(cfg: dict) -> dict:
    """Your settings, pointed at the demo folder (made-up prices, no keys, no internet)."""
    cfg = copy.deepcopy(cfg)
    cfg["data_dir"] = str(Path(cfg["data_dir"]) / "demo")
    cfg["data"]["source"] = "demo"
    cfg["llm"]["enabled"] = False
    cfg["secrets"] = {k: "" for k in cfg["secrets"]}
    cfg["ai"]["swing"]["min_train"] = cfg["ai"]["day"]["min_train"] = 10 ** 9     # skip the slow AI in the demo
    cfg["plan"].update(min_sharpe=-99, min_profit_factor=0, max_drawdown_pct=100, min_trades=0,
                       min_forward_signals=0, min_forward_trades=0)
    return cfg


def build(cfg: dict, seed: int = 7) -> dict:
    """Makes fresh demo data. Returns the demo config (see demo_config)."""
    rng = np.random.default_rng(seed)
    cfg = demo_config(cfg)
    shutil.rmtree(cfg["data_dir"], ignore_errors=True)       # only ever the demo folder
    os.makedirs(cfg["data_dir"])
    store = Store(f"{cfg['data_dir']}/aitrader.sqlite")
    store.set("demo", True)

    last = pd.Timestamp(now_ny().date())
    last = last if last.weekday() < 5 else last - pd.offsets.BDay(1)
    days = pd.bdate_range(end=last, periods=DAYS)
    minutes = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 5 * i) for d in days[-INTRADAY_DAYS:] for i in range(78)])
    market_daily = rng.normal(0.0004, 0.009, len(days))
    market_5m = rng.normal(0.00002, 0.0011, len(minutes))
    daily, intraday = {}, {}
    bench = cfg["benchmark"]
    daily[bench] = _bars(days, 560.0, market_daily, rng, 1.0, 0.0, 0.0)
    intraday[bench] = _bars(minutes, float(daily[bench]["close"].iloc[-INTRADAY_DAYS]), market_5m, rng, 1.0, 0.0, 0.0)
    for t in cfg["desks"]["swing"]["watchlist"]:
        daily[t] = _bars(days, float(rng.uniform(25, 140)), market_daily, rng, rng.uniform(0.6, 1.3), 0.012, 0.0002)
    for t in cfg["desks"]["day"]["watchlist"]:
        intraday[t] = _bars(minutes, float(rng.uniform(8, 60)), market_5m, rng, rng.uniform(0.8, 1.6), 0.0022, 0.0)
    for folder, bars in (("1d", daily), ("5m", intraday)):
        for t, df in bars.items():
            path = f"{cfg['data_dir']}/cache/demo/{folder}"
            os.makedirs(path, exist_ok=True)
            df.to_csv(f"{path}/{t}.csv")

    def upto(bars, t):
        return {k: v[v.index <= t] for k, v in bars.items() if k != bench}, bars[bench][bars[bench].index <= t]

    # 1) the study month (swing: daily opinions; day: shadow trading)
    study_start = days[-(PAPER_DAYS + 25)]
    store.set("study_started_on", study_start.strftime("%Y-%m-%d"))
    for d in days[-(PAPER_DAYS + 25):-PAPER_DAYS]:
        study_swing(cfg, store, *upto(daily, d))
    record_study_day(store, days[-PAPER_DAYS - 1].strftime("%Y-%m-%d"))
    study_day(cfg, store, *upto(intraday, minutes[-(DAY_DESK_PAPER_DAYS + 1) * 78 - 1]))

    # 2) the plans, then paper trading with the plans' strategies
    for desk, bars, fallback in (("swing", daily, "trend_following"), ("day", intraday, "opening_range_breakout")):
        plan = build_plan(cfg, store, desk, *upto(bars, (days[-PAPER_DAYS - 1] if desk == "swing"
                                                         else minutes[-(DAY_DESK_PAPER_DAYS + 1) * 78 - 1])))
        set_phase(store, desk, Phase.PLAN_REVIEW, "demo plan")
        set_phase(store, desk, Phase.PAPER, "demo: plan approved")
        _paper(cfg, store, desk, bars, plan["strategy"] or fallback, upto)
    store.set("autopilot_heartbeat", now_ny().isoformat(timespec="seconds"))     # same clock as the autopilot
    return cfg


def _paper(cfg, store, desk, bars, strategy_name, upto):
    mode = f"paper-{desk}"
    strategy = get_strategy(strategy_name, cfg, desk)
    risk = RiskManager.for_desk(cfg, desk)
    ledger = Ledger(desk_capital(cfg, desk, live=False))
    broker = PaperBroker(ledger, cfg["paper"]["slippage_pct"], mode=mode,
                         cash_account=is_cash_account(cfg))

    def record(f):
        store.record_fill(mode, f)
        pnl = f" (P&L ${f.realized_pnl:+.2f})" if f.side == "SELL" else ""
        store.log(f"[{mode}] {f.side} {f.qty} {f.ticker} @ ${f.price:.2f}{pnl}: {f.reason}", echo=False)
    broker.on_fill = record

    bench = bars[cfg["benchmark"]].index
    if desk == "swing":
        moments = [d + pd.Timedelta(hours=15, minutes=45) for d in bench[-PAPER_DAYS:]]
    else:
        moments = list(bench[-DAY_DESK_PAPER_DAYS * 78:])
    last_day = moments[-1].date() if moments else None
    for now in moments:
        watch, market = upto(bars, now)
        run_cycle(store, broker, strategy, risk, watch, market, now.to_pydatetime(), cfg["desks"][desk],
                  cfg=cfg if now.date() == last_day else None)   # the team's notes on the last day (Thinking tab)
        store.set(f"{mode}_ledger", ledger.to_dict())
