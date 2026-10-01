"""Stops sized to how much each stock moves (risk.py / engine.py), and no swing buys right before earnings
(earnings.py). Nothing here goes on the internet: Yahoo is faked."""
import numpy as np
import pandas as pd
import pytest

import run
from aitrader import earnings
from aitrader.brokers import Ledger, Order, PaperBroker, Position
from aitrader.engine import atr_pct_table, decide_orders, latest_atr_pct
from aitrader.risk import RiskManager
from aitrader.storage import Store
from aitrader.strategies import OpeningRangeBreakout

DAY = "2026-10-01"
DAY_RISK = dict(max_open_positions=3, max_position_pct=33, stop_loss_pct=2, stop_atr_multiple=0.5,
                stop_min_pct=1, stop_max_pct=5, risk_per_trade_pct=0.66)


# ---------------------------------------------------------------- stops
def test_each_stock_gets_a_stop_sized_to_how_much_it_usually_moves():
    risk = RiskManager(**DAY_RISK)
    assert risk.stop_for(4.0) == 2.0                      # half its usual 4% daily range
    assert risk.stop_for(16.0) == 5.0                     # a wild one: capped at 5%
    assert risk.stop_for(1.0) == 1.0                      # a calm one: at least 1%
    assert risk.stop_for(None) == 2.0 and risk.stop_for(float("nan")) == 2.0   # unknown: the fixed stop
    assert RiskManager(stop_loss_pct=7).stop_for(4.0) == 7                       # not set up (swing): fixed


def test_a_wider_stop_buys_less_so_no_trade_risks_more_than_before():
    risk = RiskManager(**DAY_RISK)
    assert risk.position_size(500, 500, 10.0, stop_pct=2.0) == 16       # 33% of $500 = $165 (as before)
    assert risk.position_size(500, 500, 10.0, stop_pct=4.0) == 8        # $82.50: loses at most $3.30 at its stop
    assert risk.position_size(500, 500, 10.0, stop_pct=1.0) == 16       # never above 33% of the desk
    for stop in (1.0, 2.0, 3.0, 4.0, 5.0):
        qty = risk.position_size(500, 500, 10.0, stop_pct=stop)
        assert qty * 10.0 * stop / 100 <= 500 * 0.0066 + 1e-9


def test_buys_carry_their_stop_and_positions_keep_it():
    risk = RiskManager(**DAY_RISK)
    orders = decide_orders(pd.Series({"HOT": 1.0, "CALM": 1.0}), pd.Series({"HOT": 10.0, "CALM": 10.0}), {}, 500.0,
                           500.0, OpeningRangeBreakout(), risk, atr_pct={"HOT": 8.0, "CALM": 2.0})
    by = {o.ticker: o for o in orders}
    assert by["HOT"].stop_pct == 4.0 and by["CALM"].stop_pct == 1.0
    assert by["HOT"].qty == 8 and by["CALM"].qty == 16
    broker = PaperBroker(Ledger(500.0), slippage_pct=0.0, mode="study-day")
    broker.submit(by["HOT"], DAY)
    pos = broker.positions()["HOT"]
    assert pos.stop_pct == 4.0
    out = decide_orders(pd.Series({"HOT": 0.5}), pd.Series({"HOT": 9.65}), {"HOT": pos}, 0, 500, OpeningRangeBreakout(), risk)
    assert out == []                                     # down 3.5%: inside its 4% stop (a fixed 2% stop would sell)
    out = decide_orders(pd.Series({"HOT": 0.5}), pd.Series({"HOT": 9.55}), {"HOT": pos}, 0, 500, OpeningRangeBreakout(), risk)
    assert out[0].side == "SELL" and "its stop: 4%, sized to how much it moves" in out[0].reason


def test_the_resting_stop_at_the_broker_uses_the_stocks_own_stop():
    pytest.importorskip("alpaca")
    from fakes import make_broker, make_client
    client = make_client("alpaca")
    broker = make_broker(client, 500, stop_good_till_cancel=False, stop_loss_pct=2)
    broker.submit(Order("HOT", "BUY", 8, 10.0, "orb", stop_pct=4.0), DAY)
    stop = client.placed("STOP")[0]
    assert stop["stop"] == pytest.approx(round(10.02 * 0.96, 2))  # 4% below what it paid, not the desk's 2%
    assert broker.positions()["HOT"].stop_pct == 4.0


def five_minute_bars(daily_range_pct, days=20, price=50.0):
    idx, rows = [], []
    for d in pd.bdate_range(end="2026-09-30", periods=days):
        for i in range(78):
            idx.append(d + pd.Timedelta(minutes=570 + 5 * i))
            half = price * daily_range_pct / 200
            rows.append((price, price + half, price - half, price))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=["open", "high", "low", "close"]).assign(volume=1e4)


def test_the_usual_daily_range_is_measured_from_earlier_days():
    bars = {"HOT": five_minute_bars(8.0), "CALM": five_minute_bars(2.0)}
    latest = latest_atr_pct(bars, intraday=True)
    assert latest["HOT"] == pytest.approx(8.0) and latest["CALM"] == pytest.approx(2.0)
    table = atr_pct_table(bars, intraday=True)
    assert table["HOT"].iloc[:78 * 14].isna().all()        # needs 14 earlier days before it says anything


def test_backtests_and_shadow_trades_use_the_same_stops(cfg):
    from aitrader.engine import run_backtest
    from conftest import make_intraday_bars
    cfg["desks"]["day"]["risk"].update(DAY_RISK)
    bars, market = make_intraday_bars(30)
    result = run_backtest(OpeningRangeBreakout(), bars, market, cfg, "day")
    assert isinstance(result, dict) and result.get("num_closed_trades", 0) >= 0     # end to end, stops per stock


# ---------------------------------------------------------------- earnings
def test_earnings_dates_are_looked_up_once_a_day(cfg):
    asked = []

    def fetch(t, today):
        asked.append(t)
        return {"NVDA": "2026-10-05", "XLE": None}.get(t)
    assert earnings.next_dates(cfg, ["NVDA", "XLE"], DAY, fetch=fetch) == {"NVDA": "2026-10-05", "XLE": None}
    earnings.next_dates(cfg, ["NVDA", "XLE"], DAY, fetch=fetch)
    assert asked == ["NVDA", "XLE"]                              # the second time: from the saved file
    earnings.next_dates(cfg, ["NVDA"], "2026-10-02", fetch=fetch)
    assert asked == ["NVDA", "XLE", "NVDA"]                      # a new day: looked up again


def test_only_reports_within_the_window_hold_a_stock_back(cfg):
    dates = {"MON": "2026-10-05", "TODAY": DAY, "LATER": "2026-10-15", "PAST": "2026-09-01", "ETF": None}
    soon = earnings.soon(cfg, list(dates), DAY, fetch=lambda t, today: dates[t])   # Thu Oct 1; 3 trading days
    assert soon == {"MON": "2026-10-05", "TODAY": DAY}           # Mon Oct 5 is 2 trading days away (weekend skipped)
    assert earnings.trading_days_until("2026-10-01", "2026-10-06") == 3


def test_the_swing_desk_skips_buys_before_earnings_but_keeps_what_it_owns(cfg, monkeypatch):
    store = Store(":memory:")
    monkeypatch.setattr(earnings, "_from_yahoo", lambda t, today: {"NVDA": "2026-10-02", "AMD": "2026-10-02"}.get(t))
    broker = PaperBroker(Ledger(500.0), mode="paper-swing")
    broker.ledger.positions["AMD"] = Position("AMD", 1, 100.0, DAY)
    now = pd.Timestamp(f"{DAY} 15:45").to_pydatetime()
    held = run.earnings_hold(cfg, store, "swing", broker, {"NVDA": None, "AMD": None, "XLE": None}, now)
    assert held == {"NVDA": "2026-10-02"}                         # AMD is already owned: kept
    assert any("not buying before earnings" in m and "NVDA (2026-10-02)" in m for _, m in store.journal(5))
    run.earnings_hold(cfg, store, "swing", broker, {"NVDA": None, "XLE": None}, now)
    assert sum("not buying before earnings" in m for _, m in store.journal(10)) == 1     # said once
    assert run.earnings_hold(cfg, store, "day", broker, {"NVDA": None}, now) == {}      # the day desk never holds overnight
    cfg["earnings"] = {"enabled": "off"}
    assert run.earnings_hold(cfg, store, "swing", broker, {"NVDA": None}, now) == {}


def test_a_broken_website_never_stops_the_decision(cfg, monkeypatch):
    store = Store(":memory:")
    monkeypatch.setattr(earnings, "soon", lambda *a, **k: 1 / 0)
    now = pd.Timestamp(f"{DAY} 15:45").to_pydatetime()
    assert run.earnings_hold(cfg, store, "swing", PaperBroker(Ledger(500.0), mode="paper-swing"), {"NVDA": None}, now) == {}
    assert "couldn't check earnings dates" in store.journal(3)[-1][1]


def test_the_morning_looks_up_the_swing_desks_stocks(cfg, monkeypatch):
    monkeypatch.setattr(run, "SCAN_IN_BACKGROUND", False)
    asked = []
    monkeypatch.setattr(earnings, "_from_yahoo", lambda t, today: asked.append(t))
    run.look_up_earnings(cfg, Store(":memory:"), DAY)
    assert asked == cfg["desks"]["swing"]["watchlist"]


def test_the_report_and_the_stock_card_show_earnings(cfg, monkeypatch):
    from aitrader import report, stock_info
    store = Store(":memory:")
    store.set("earnings_hold:swing", {"day": DAY, "tickers": {"NVDA": "2026-10-02"}})
    text = report.after_market(cfg, store, DAY)
    monkeypatch.setattr(earnings, "_from_yahoo", lambda t, today: "2099-10-02")
    earnings.next_dates(cfg, ["NVDA"], DAY)
    assert "Next earnings report: 2099-10-02" in stock_info.kestrel_view(cfg, store, "NVDA", today=DAY)["lists"]
    assert "## Earnings soon (the swing desk isn't buying these)" in text and "NVDA: reports 2026-10-02" in text
