"""Day-trading rules, market hours and the autopilot schedule."""
from datetime import date, datetime

import pandas as pd

from aitrader.brokers import Fill, Ledger, PaperBroker
from aitrader.engine import desk_orders, run_backtest
from aitrader.market_hours import is_early_close, session_close
from aitrader.risk import RiskManager
from aitrader.strategies import OpeningRangeBreakout, Strategy
from run import due_jobs

from conftest import make_intraday_bars


class AlwaysBuy(Strategy):
    name, style, buy_above, sell_below = "always_buy", "day", 0.5, 0.1

    def scores(self, bars, market, since=None):
        return pd.DataFrame(1.0, index=market.index, columns=list(bars))


def test_day_desk_never_holds_overnight(cfg, monkeypatch):
    import aitrader.engine as engine
    bars, market = make_intraday_bars(n_days=5)
    fills, original = [], engine.execute

    def record_fills(orders, broker, date):          # watch every fill the backtest makes
        result = original(orders, broker, date)
        fills.extend(result)
        return result

    monkeypatch.setattr(engine, "execute", record_fills)
    result = run_backtest(AlwaysBuy(), bars, market, cfg, "day")
    assert result["num_closed_trades"] > 0
    per_day = pd.DataFrame([f.__dict__ for f in fills]).groupby("date")
    for day, day_fills in per_day:
        bought = day_fills[day_fills.side == "BUY"]["qty"].sum()
        sold = day_fills[day_fills.side == "SELL"]["qty"].sum()
        assert bought == sold, f"positions left open overnight on {day}"


def test_day_desk_timing_rules(cfg):
    desk_cfg = cfg["desks"]["day"]
    broker = PaperBroker(Ledger(5000), slippage_pct=0)
    risk = RiskManager.for_desk(cfg, "day")
    prices = pd.Series({"EEE": 50.0, "FFF": 50.0})
    scores = pd.Series({"EEE": 0.9, "FFF": 0.9})
    at = lambda hhmm: datetime(2026, 9, 21, *hhmm)

    assert any(o.side == "BUY" for o in desk_orders(AlwaysBuy(), at((11, 0)), scores, prices, broker, risk, None, desk_cfg))
    assert desk_orders(AlwaysBuy(), at((15, 35)), scores, prices, broker, risk, None, desk_cfg) == []   # too late to buy

    broker.ledger.apply(Fill("2026-09-21", "EEE", "BUY", 10, 50.0, "seed"))
    flatten = desk_orders(AlwaysBuy(), at((15, 50)), scores, prices, broker, risk, None, desk_cfg)
    assert [(o.side, o.ticker) for o in flatten] == [("SELL", "EEE")]

    broker = PaperBroker(Ledger(5000), slippage_pct=0)
    broker.ledger.apply(Fill("2026-09-18", "FFF", "BUY", 10, 50.0, "seed"))      # left over from Friday
    morning = desk_orders(AlwaysBuy(), at((9, 40)), scores, prices, broker, risk, None, desk_cfg)
    assert [(o.side, o.ticker) for o in morning] == [("SELL", "FFF")]


def test_opening_range_has_no_opinion_in_first_30_minutes():
    bars, market = make_intraday_bars(n_days=2)
    scores = OpeningRangeBreakout().scores(bars, market)
    first_half_hour = scores.index.time < pd.Timestamp("10:00").time()
    assert scores[first_half_hour].isna().all().all()
    assert scores[~first_half_hour].notna().any().any()


def test_early_close_days():
    assert is_early_close(date(2026, 11, 27))        # day after Thanksgiving 2026
    assert is_early_close(date(2026, 12, 24))        # Christmas Eve, a Thursday
    assert is_early_close(date(2025, 7, 3))          # July 3, a Thursday
    assert not is_early_close(date(2026, 7, 3))      # a Friday: markets are closed that day instead
    assert not is_early_close(date(2026, 9, 28))
    assert session_close(date(2026, 11, 27)).hour == 13


def test_autopilot_schedule():
    done = set()
    at = lambda h, m: datetime(2026, 9, 28, h, m)        # a Monday
    assert due_jobs(at(9, 0), done) == []
    assert due_jobs(at(9, 30), done) == ["morning", "day", "swing-stops"]
    done.add("morning:2026-09-28")
    assert due_jobs(at(12, 0), done) == ["day", "swing-stops"]
    assert due_jobs(at(15, 45), done) == ["day", "swing"]
    done.add("swing:2026-09-28")
    assert due_jobs(at(15, 50), done) == ["day", "swing-stops"]      # keeps protecting after deciding
    assert due_jobs(at(16, 5), done) == []
    assert due_jobs(at(16, 10), done) == ["study"]
    assert due_jobs(datetime(2026, 9, 26, 12, 0), set()) == []          # Saturday
    assert "swing" in due_jobs(datetime(2026, 11, 27, 12, 45), {"morning:2026-11-27"})   # early close


def test_only_one_process_trades_at_a_time(cfg):
    import pytest
    from run import trading_lock
    with trading_lock(cfg):
        with pytest.raises(RuntimeError):
            with trading_lock(cfg, wait_seconds=0):
                pass
    with trading_lock(cfg, wait_seconds=0):            # released afterwards
        pass


def test_price_history_is_kept_separately_per_source(cfg, monkeypatch):
    from aitrader.market_data import MarketData
    from conftest import make_bars
    daily, _ = make_bars(n_days=30, tickers=("AAA",))
    md = MarketData({**cfg, "data": {**cfg["data"], "source": "yfinance"}})
    monkeypatch.setattr(md, "_download", lambda t, i, recent: daily["AAA"])
    md.history("AAA", "1d")
    md.source = "alpaca"
    md._memo.clear()
    md.history("AAA", "1d")
    from pathlib import Path
    assert (Path(cfg["data_dir"]) / "cache/yfinance/1d/AAA.csv").exists()
    assert (Path(cfg["data_dir"]) / "cache/alpaca/1d/AAA.csv").exists()
