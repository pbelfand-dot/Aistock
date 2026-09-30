"""Stocks in play: the day desk's extra stocks each morning, and the research version of the breakout."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from aitrader import in_play, scanner
from aitrader.storage import Store
from conftest import make_intraday_bars

TODAY = "2026-09-30"


def table(rows):
    return pd.DataFrame([{"symbol": s, "price": p, "avg_volume": v, "atr": a, "dollar_volume": p * v}
                         for s, p, v, a in rows])


def test_the_pool_is_the_busiest_stocks_the_day_desk_could_trade(cfg):
    cfg["desks"]["day"]["risk"]["max_position_pct"] = 33              # $5,000 desk: a share can cost up to ~$1,633
    t = table([("BIG", 40, 9_000_000, 1.5), ("CHEAP", 4, 9_000_000, 0.6), ("THIN", 40, 500_000, 1.5),
               ("SLEEPY", 40, 9_000_000, 0.2), ("PRICEY", 2000, 2_000_000, 30), ("MID", 20, 2_000_000, 0.8)])
    assert [r["symbol"] for r in in_play.pool(t, cfg)] == ["BIG", "MID"]   # $5+, 1M+ shares, $0.50+ range, affordable


def test_relative_volume_compares_the_first_5_minutes_with_their_own_usual(cfg):
    past = {f"2026-09-{d:02d}": {"HOT": {"volume": 1000}, "NORMAL": {"volume": 1000}, "NEWISH": {"volume": 1000}}
            for d in range(15, 30) if datetime(2026, 9, d).weekday() < 5}
    past["2026-09-29"]["NEWISH"] = {"volume": 1000}
    for d in list(past)[:-3]:
        past[d].pop("NEWISH")                                          # only 3 days of history
    today = {"HOT": {"volume": 6000, "open": 10, "close": 10.5}, "NORMAL": {"volume": 900, "open": 10, "close": 10},
             "NEWISH": {"volume": 9000, "open": 10, "close": 11}}
    picks = in_play.rank(today, past, cfg)
    assert [(p["symbol"], p["rvol"]) for p in picks] == [("HOT", 6.0)]  # NORMAL: quieter than usual; NEWISH: too new
    assert picks[0]["first_5_min_pct"] == 5.0


def fake_volumes(hot=("HOT",)):
    def get(cfg, symbols, days):
        out = {}
        for i, day in enumerate(days):
            out[day] = {s: {"volume": (8000.0 if s in hot else 1000.0) if i == 0 else 1000.0, "open": 10.0, "close": 10.2}
                        for s in symbols}
        return out
    return get


def with_pool(cfg, symbols):
    scanner.update_list(cfg, [], [], {}, "2026-09-29", [], day_pool=[{"symbol": s, "price": 10, "atr": 1} for s in symbols])


def test_each_morning_the_stocks_in_play_join_the_day_desks_list(cfg, monkeypatch):
    from aitrader import market_data
    cfg["secrets"].update(alpaca_paper_key="k", alpaca_paper_secret="s")
    store = Store(":memory:")
    assert "no pool yet" in in_play.run(cfg, store, TODAY, get_volumes=fake_volumes())
    with_pool(cfg, ["HOT", "COOL", "AAA"])                              # AAA is on the swing desk's watchlist
    store.set("study-swing_ledger", {"positions": {"COOL": {"qty": 1}}})   # COOL: the swing desk owns it
    asked = []

    def volumes(cfg, symbols, days):
        asked.extend(symbols)
        return fake_volumes(("HOT", "COOL", "AAA"))(cfg, symbols, days)
    message = in_play.run(cfg, store, TODAY, get_volumes=volumes, get_news=lambda c, s, d: {})
    assert asked == ["HOT"]                                             # a stock is on one desk only
    assert "HOT 8.0x" in message and in_play.today_picks(cfg, TODAY) == ["HOT"]
    assert in_play.today_picks(cfg, "2026-10-01") == []                 # yesterday's list isn't today's
    assert store.get("in_play_history") == {TODAY: ["HOT"]}

    loaded = []
    cfg["secrets"].update(alpaca_paper_key="", alpaca_paper_secret="")  # prices from the fake below, never the internet
    monkeypatch.setattr(in_play, "today_picks", lambda cfg: ["HOT"])
    monkeypatch.setattr(market_data.MarketData, "history", lambda self, t, i: loaded.append((t, i)) or
                        make_intraday_bars(3, ("X",))[0]["X"])
    bars, _ = market_data.MarketData(cfg).load("day")
    assert "HOT" in bars and ("HOT", "5m") in loaded
    bars, _ = market_data.MarketData(cfg).load("swing")
    assert "HOT" not in bars


def test_danger_news_keeps_a_stock_in_play_off_the_list(cfg):
    cfg["secrets"].update(alpaca_paper_key="k", alpaca_paper_secret="s")
    with_pool(cfg, ["HOT", "WARM"])
    news = {"HOT": [{"headline": "HOT announces $200M stock offering"}], "WARM": []}
    message = in_play.run(cfg, Store(":memory:"), TODAY, get_volumes=fake_volumes(("HOT", "WARM")),
                          get_news=lambda c, s, d: {k: news.get(k, []) for k in s})
    assert in_play.today_picks(cfg, TODAY) == ["WARM"] and "skipped for danger news: HOT (offering)" in message


def test_before_the_first_bars_are_in_it_tries_again(cfg):
    cfg["secrets"].update(alpaca_paper_key="k", alpaca_paper_secret="s")
    with_pool(cfg, ["HOT", "WARM", "MILD", "COOL"])
    with pytest.raises(RuntimeError, match="have a 9:30 bar yet"):
        in_play.run(cfg, Store(":memory:"), TODAY, get_volumes=lambda c, s, days: {days[0]: {}})
    assert in_play.today_picks(cfg, TODAY) == []


def test_without_alpaca_keys_the_day_desk_keeps_its_watchlist(cfg):
    with_pool(cfg, ["HOT"])
    assert "needs Alpaca keys" in in_play.run(cfg, Store(":memory:"), TODAY, get_volumes=fake_volumes())


def test_the_morning_check_runs_at_935_before_the_day_desk():
    import run
    jobs = run.due_jobs(datetime(2026, 9, 30, 9, 35), {"morning:2026-09-30"})
    assert jobs.index("inplay") < jobs.index("day")
    assert "inplay" not in run.due_jobs(datetime(2026, 9, 30, 9, 30), set())
    assert "inplay" not in run.due_jobs(datetime(2026, 9, 30, 9, 40), {"inplay:2026-09-30"})
    assert "inplay" not in run.due_jobs(datetime(2026, 9, 30, 9, 50), set())   # too late: the watchlist it is


def test_the_report_splits_day_trades_by_whether_the_stock_was_in_play(cfg):
    from aitrader.brokers import Fill
    from aitrader.report import in_play_lines
    store = Store(":memory:")
    in_play.save(cfg, {"day": TODAY, "checked": 250, "picks": [{"symbol": "HOT", "rvol": 4.2}]})
    store.set("in_play_history", {TODAY: ["HOT"]})
    for i, (ticker, pnl) in enumerate((("HOT", 5.0), ("HOT", -1.0), ("EEE", -2.0))):
        store.record_fill("study-day", Fill(TODAY, ticker, "SELL", 1, 10.0, "test", pnl, order_id=f"o{i}"))
    text = "\n".join(in_play_lines(cfg, store, TODAY))
    assert "HOT (4.2x usual volume)" in text and "of 250 busy stocks checked" in text
    assert "in play: 2 trades, 1 won, +$4.00" in text and "fixed list: 1 trades, 0 won, -$2.00" in text


def day_with(first, later, days=16):
    """5-minute bars: `days` quiet days (a $1 daily range), then today with the given first candle
    (open, close, high) followed by `later` closes."""
    idx, rows = [], []
    for d in pd.bdate_range(end="2026-09-30", periods=days + 1)[:-1]:
        for i in range(78):
            idx.append(d + pd.Timedelta(minutes=570 + 5 * i))
            rows.append((20.0, 20.5, 19.5, 20.0))
    today = pd.Timestamp("2026-09-30")
    o, c, h = first
    idx.append(today + pd.Timedelta(minutes=570))
    rows.append((o, h, min(o, c) - 0.01, c))
    for i, close in enumerate(later, 1):
        idx.append(today + pd.Timedelta(minutes=570 + 5 * i))
        rows.append((close, close + 0.01, close - 0.01, close))
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=["open", "high", "low", "close"])
    df["volume"] = 1000.0
    return df


def test_the_research_breakout_buys_above_a_green_first_candle_and_stops_out_once():
    from aitrader.strategies import OpeningRange5, daily_atr
    s = OpeningRange5()
    df = day_with((20.0, 20.4, 20.5), [20.45, 20.6, 20.52, 20.39, 20.7])   # ATR $1: the stop is 20.5 - 0.10 = 20.40
    assert daily_atr(df).iloc[-1] == pytest.approx(1.0)
    score = s.scores({"X": df}, None)["X"].iloc[-6:]
    assert np.isnan(score.iloc[0])                                          # the first candle: no opinion
    assert list(score.iloc[1:]) == [0.5, 1.0, 1.0, 0.0, 0.0]                # broke out, held, stopped, no second try

    red = day_with((20.4, 20.0, 20.5), [20.6, 20.8])                        # first candle closed down: no buy
    assert 1.0 not in list(s.scores({"X": red}, None)["X"].iloc[-2:])
    new = day_with((20.0, 20.4, 20.5), [20.6], days=5)                      # under 14 days of history: no opinion
    assert s.scores({"X": new}, None)["X"].iloc[-2:].isna().all()


def test_the_evening_scan_keeps_the_day_desks_pool(cfg, monkeypatch):
    from test_scanner import fake_market, run_scan
    monkeypatch.setattr(scanner, "universe", lambda cfg: list(fake_market()))
    summary = run_scan(cfg, Store(":memory:"))
    pool = scanner.load_list(cfg)["day_pool"]
    assert {r["symbol"] for r in pool} <= {"ROCKET", "STEADY", "SINKER", "NEWCO"} and "busy enough for the day desk" in summary


def test_the_opening_bar_is_930_new_york_time_in_summer_and_winter():
    assert in_play.opening_bar_start("2026-09-30").strftime("%H:%M") == "13:30"      # EDT = UTC-4
    assert in_play.opening_bar_start("2026-12-01").strftime("%H:%M") == "14:30"      # EST = UTC-5
