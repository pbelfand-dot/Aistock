"""Day desk upgrades: realistic costs, the market-intraday-momentum exit (a challenger), and the pre-market
movers, shadow traded until they prove they help. Nothing goes online."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

import run
from aitrader import challengers, in_play, scanner
from aitrader.brokers import Ledger, Order, PaperBroker
from aitrader.config import cents_per_share
from aitrader.storage import Store
from aitrader.strategies import (CloseWithTheMarket, OpeningRange5, get_strategy, market_first_half_hour,
                                 minutes_since_open)
from conftest import make_intraday_bars


def test_simulated_day_trades_pay_a_few_cents_a_share(cfg):
    assert cents_per_share(cfg, "day") == 2 and cents_per_share(cfg, "swing") == 0
    broker = PaperBroker(Ledger(1000.0), slippage_pct=0.05, cents_per_share=2)
    buy = broker.submit(Order("AAA", "BUY", 10, 20.0, "test"), "2026-10-01")
    assert buy.price == pytest.approx(20.0 * 1.0005 + 0.02)
    sell = broker.submit(Order("AAA", "SELL", 10, 20.0, "test"), "2026-10-01")
    assert sell.price == pytest.approx(20.0 * 0.9995 - 0.02)
    assert sell.realized_pnl == pytest.approx(10 * (sell.price - buy.price))      # about 6 cents a share lost


def test_the_markets_first_half_hour_is_known_only_after_10am():
    bars, market = make_intraday_bars(n_days=5, tickers=("A",))
    first = market_first_half_hour(market)
    days = market.index.normalize().unique()
    today = market[market.index.normalize() == days[2]]
    prev = market[market.index.normalize() == days[1]]["close"].iloc[-1]
    assert np.isnan(first.loc[today.index[5]])                                   # the 9:55 bar: not known yet
    assert first.loc[today.index[6]] == pytest.approx(today["close"].iloc[5] / prev - 1)
    assert first.loc[today.index[-1]] == first.loc[today.index[6]]
    assert first.loc[market.index[:78]].isna().all()                             # day one: no previous close


def test_the_mim_exit_sells_at_330_only_when_the_market_started_down(cfg):
    bars, market = make_intraday_bars(n_days=12, tickers=("A", "B", "C"))
    base, mim = OpeningRange5().scores(bars, market), CloseWithTheMarket(OpeningRange5()).scores(bars, market)
    first = market_first_half_hour(market).reindex(mim.index)
    late = pd.Series(minutes_since_open(pd.DataFrame(index=mim.index)).to_numpy() >= 360, index=mim.index)
    assert mim[~late].equals(base[~late])                                         # nothing changes before 3:30
    down, up = late & (first <= 0), late & (first > 0)
    assert down.any() and up.any()
    assert (mim[down].fillna(0) == 0).all().all()                                 # down start: sell at 3:30
    assert mim[up].equals(base[up])                                               # up start: hold as usual
    strategy = get_strategy("orb_5min_mim", cfg, "day")
    assert strategy.style == "day" and "market intraday momentum" in strategy.description


POOL = [{"symbol": s, "price": 20.0, "atr": 1.0, "avg_volume": 1_000_000} for s in ("UPX", "DNX", "SLEEPY", "THIN")]


def test_premarket_movers_need_a_big_gap_on_heavy_early_volume(cfg):
    volumes = {"UPX": {"volume": 80_000, "last": 21.4},      # +7% on 8% of a day's volume
               "DNX": {"volume": 50_000, "last": 18.8},      # -6% on 5%
               "SLEEPY": {"volume": 90_000, "last": 20.2},   # heavy, but only +1%
               "THIN": {"volume": 5_000, "last": 23.0}}      # +15% on 0.5%: too thin
    picks = in_play.premarket_rank(volumes, POOL, cfg)
    assert [p["symbol"] for p in picks] == ["UPX", "DNX"]
    assert picks[0] == {"symbol": "UPX", "gap_pct": 7.0, "volume_pct": 8.0, "price": 21.4}


@pytest.fixture
def morning(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(in_play, "is_on", lambda cfg: True)
    monkeypatch.setattr(scanner, "load_list", lambda cfg: {"day_pool": POOL})
    monkeypatch.setattr(scanner, "news_on", lambda cfg: False)
    import aitrader.alpaca_api as alpaca_api
    monkeypatch.setattr(alpaca_api, "has_keys", lambda cfg, paper: True)
    store = Store(tmp_path / "aitrader.sqlite")
    fake = lambda cfg, symbols, today, now: {"UPX": {"volume": 80_000, "last": 21.4}}
    return cfg, store, fake


def test_premarket_movers_are_shadow_traded_until_proven(morning):
    cfg, store, fake = morning
    message = in_play.premarket(cfg, store, "2026-10-02", datetime(2026, 10, 2, 9, 20), get_volumes=fake)
    assert message.startswith("pre-market movers (4 busy stocks checked): UPX +7.0% on 8% of a day's volume")
    assert "shadow account" in message
    assert in_play.premarket_today(cfg, "2026-10-02") == ["UPX"]
    assert in_play.today_picks(cfg, "2026-10-02") == []                           # not traded yet
    store.set("list_on:day:premarket", {"on": "2026-09-30"})
    in_play.premarket(cfg, store, "2026-10-02", datetime(2026, 10, 2, 9, 20), get_volumes=fake)
    assert in_play.today_picks(cfg, "2026-10-02") == ["UPX"]                      # proven: on the list


def test_the_premarket_job_runs_before_the_open(cfg):
    assert "premarket" in run.due_jobs(datetime(2026, 10, 2, 9, 21), set())
    assert "premarket" not in run.due_jobs(datetime(2026, 10, 2, 9, 31), set())
    assert "premarket" not in run.due_jobs(datetime(2026, 10, 2, 9, 21), {"premarket:2026-10-02"})


def curve(store, mode, daily_returns, start="2026-08-03"):
    days = pd.bdate_range(start=start, periods=len(daily_returns) + 1)
    value = 500.0
    store.record_equity(mode, days[0].strftime("%Y-%m-%d"), value, value)
    for d, r in zip(days[1:], daily_returns):
        value *= 1 + r
        store.record_equity(mode, d.strftime("%Y-%m-%d"), value, value)


def test_a_stock_list_is_judged_on_shadow_trading_alone(cfg, tmp_path):
    cfg["challengers"] = {"day": [], "lists": {"day": ["premarket"]}}
    store = Store(tmp_path / "aitrader.sqlite")
    bars, market = make_intraday_bars(n_days=5, tickers=("A",))
    rng = np.random.default_rng(3)
    base = rng.normal(0, 0.004, 30)
    curve(store, "shadow-day-tjr_model", base[:10])
    curve(store, "shadow-day-list-premarket", base[:10] + 0.003)
    report = challengers.evaluate(cfg, store, "day", bars, market, "tjr_model", "tjr_model", today="2026-08-17")
    row = report["rows"][0]
    assert row["kind"] == "list" and row["history"] is None and row["verdict"] == "too early"
    assert "no history" in row["why"]
    curve(store, "shadow-day-tjr_model", base)
    curve(store, "shadow-day-list-premarket", base + 0.003)
    report = challengers.evaluate(cfg, store, "day", bars, market, "tjr_model", "tjr_model", today="2026-09-14")
    row = report["rows"][0]
    assert row["verdict"] == "proven", row["why"]
    assert challengers.list_on(store, "day", "premarket") and report["lists_on"] == ["premarket"]
    assert any("CHALLENGER WON (day desk): the pre-market movers join its list" in m for _, m in store.journal(5))
    text = "\n".join(challengers.lines(store, ["day"]))
    assert "`pre-market movers`: **proven**. No history to replay (a stock list)." in text


def test_a_real_money_desk_adds_a_proven_list_only_when_you_press_use_it(cfg, tmp_path):
    cfg["challengers"] = {"day": [], "lists": {"day": ["premarket"]}}
    store = Store(tmp_path / "aitrader.sqlite")
    bars, market = make_intraday_bars(n_days=5, tickers=("A",))
    base = np.random.default_rng(4).normal(0, 0.004, 30)
    curve(store, "shadow-day-tjr_model", base)
    curve(store, "shadow-day-list-premarket", base + 0.003)
    report = challengers.evaluate(cfg, store, "day", bars, market, "tjr_model", "tjr_model", real_money=True,
                                  today="2026-09-14")
    assert report["waiting_for_you"] == "list-premarket" and not challengers.list_on(store, "day", "premarket")
    assert challengers.use(store, "day", "list-premarket").startswith("The day desk now also trades the pre-market movers")
    assert challengers.list_on(store, "day", "premarket")


def test_list_shadows_run_next_to_the_current_method(cfg, tmp_path):
    cfg["challengers"] = {"day": ["tjr_model", "orb_5min"], "lists": {"day": ["premarket"]}}
    store = Store(tmp_path / "aitrader.sqlite")
    bars, market = make_intraday_bars(n_days=3, tickers=("A", "B"))
    more, _ = make_intraday_bars(n_days=3, tickers=("A", "B", "MOVER"))
    now = market.index[-30].to_pydatetime()
    ran = challengers.run_shadows(cfg, store, "day", {t: df[df.index <= now] for t, df in bars.items()},
                                  market[market.index <= now], now, "tjr_model",
                                  lists={"premarket": {t: df[df.index <= now] for t, df in more.items()}})
    assert ran == ["shadow-day-tjr_model", "shadow-day-orb_5min", "shadow-day-list-premarket"]
    store.set("list_on:day:premarket", {"on": "x"})
    ran = challengers.run_shadows(cfg, store, "day", {t: df[df.index <= now] for t, df in bars.items()},
                                  market[market.index <= now], now, "tjr_model", lists={"premarket": more})
    assert "shadow-day-list-premarket" not in ran                                 # in use: no shadow needed
