"""Weekend practice (weekend.py): real past days replayed fast, and crypto with pretend money at live
prices. Practice never touches the real accounts or what the desks learn, and each weekend starts fresh."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from aitrader import dashboard, weekend
from aitrader.config import data_path, data_source
from aitrader.storage import Store
from conftest import make_bars, make_intraday_bars

SATURDAY = datetime(2026, 10, 3, 10, 2)


@pytest.fixture
def practice(cfg, monkeypatch):
    """Prices saved on this Mac (as market_data.py saves them), a Saturday, and no waiting."""
    intraday, market5 = make_intraday_bars(n_days=12, end="2026-09-11")
    daily, market1 = make_bars(n_days=400, end="2026-09-11")
    folder = f"cache/{data_source(cfg)}"
    for t, df in {**intraday, cfg["benchmark"]: market5}.items():
        df.to_csv(data_path(cfg, f"{folder}/5m/{t}.csv"))
    for t, df in {**daily, cfg["benchmark"]: market1}.items():
        df.to_csv(data_path(cfg, f"{folder}/1d/{t}.csv"))
    monkeypatch.setattr(weekend, "_clock", lambda: SATURDAY)
    monkeypatch.setattr(weekend, "_pause", lambda s: None)
    monkeypatch.setattr(weekend, "IN_BACKGROUND", False)
    return Store(data_path(cfg, "aitrader.sqlite"))


def test_a_weekend_replays_real_past_days_without_touching_the_real_accounts(cfg, practice):
    store = practice
    st = weekend.start(cfg, store, SATURDAY)
    assert st["days"] and all(d <= "2026-09-23" for d in st["days"])     # not the last two weeks
    store.set("weekend_state", {**st, "days": st["days"][:2]})           # two days are enough for a test
    played = weekend.replay(cfg, data_path(cfg, "aitrader.sqlite"))
    assert played == 2 * 78
    t = store.get("weekend-day_thinking")
    assert t["time"][:10] == st["days"][1] and t["time"][-5:] == "15:55"   # the last moment of the 2nd day
    assert store.get("weekend-swing_thinking")["time"].endswith("15:45")   # the swing desk decided at 3:45pm
    assert len(store.get("weekend-day_checks")["items"]) == 78
    after = weekend.state(store)
    assert after["i"] == 2 and after["done"] == st["days"][:2]
    assert set(st["days"][:2]) <= set(store.get("weekend_replayed"))      # next weekend: somewhere else
    # practice stays practice: the real accounts and the mistake memory are untouched
    for kind in ("study", "paper", "live"):
        assert not len(store.fills(f"{kind}-day")) and not store.get(f"{kind}-day_ledger")
    assert store.get("entry_tags:day") is None
    lines = [m for _, m in store.journal(50)]
    assert sum("[weekend] replayed" in m for m in lines) == 2
    assert not any(m.startswith("[weekend-") for m in lines)              # no flood of per-moment lines


def test_the_replay_stops_when_the_weekend_ends(cfg, practice, monkeypatch):
    weekend.start(cfg, practice, SATURDAY)
    monkeypatch.setattr(weekend, "_clock", lambda: datetime(2026, 10, 5, 9, 0))     # Monday
    assert weekend.replay(cfg, data_path(cfg, "aitrader.sqlite")) == 0


def hourly_coins(n=800, end="2026-10-03 10:00"):
    idx = pd.date_range(end=end, periods=n, freq="h")
    rng = np.random.default_rng(3)
    def frame(drift):
        close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.002, n))
        return pd.DataFrame({"open": close, "high": close * 1.001, "low": close * 0.999, "close": close,
                             "volume": 1000.0}, index=idx)
    return {"BTC/USD": frame(0.0006), "ETH/USD": frame(0.0012), "DOGE/USD": frame(-0.0008),
            "LTC/USD": frame(0.0002), "LINK/USD": frame(0.0009)}


def test_crypto_decides_each_hour_checks_stops_and_sells_everything_sunday_night(cfg, practice):
    store = practice
    weekend.start(cfg, store, SATURDAY)
    fetch = lambda cfg, coins, days: hourly_coins()
    assert weekend.crypto_check(cfg, store, SATURDAY, fetch) == "crypto: decided"
    assert store.get("weekend-crypto_thinking")["strategy"] == "momentum"
    owned = (store.get("weekend-crypto_ledger") or {}).get("positions", {})
    assert owned and "DOGE/USD" not in owned                            # the strongest coins, not the weakest
    assert any(p["qty"] != int(p["qty"]) for p in owned.values())       # coins are bought in parts
    assert weekend.crypto_check(cfg, store, datetime(2026, 10, 3, 10, 7), fetch) == "crypto: checked stop-losses"
    assert weekend.crypto_check(cfg, store, datetime(2026, 10, 4, 23, 52), fetch).startswith("crypto: sold")
    assert not store.get("weekend-crypto_ledger")["positions"]
    assert weekend.crypto_check(cfg, store, datetime(2026, 10, 4, 23, 57), fetch) == ""   # over for this weekend
    r = weekend.results(store, cfg)["weekend-crypto"]
    assert r["trades"] == len(owned) and r["start"] == 500 and r["change"] == round(r["value"] - 500, 2)


def test_each_weekend_starts_fresh_and_monday_gets_one_summary(cfg, practice):
    store = practice
    weekend.start(cfg, store, SATURDAY)
    store.set("weekend-day_ledger", {"cash": 480.0, "positions": {}})
    monday = datetime(2026, 10, 5, 9, 0)
    line = weekend.summarize(cfg, store, monday)
    assert line.startswith("[weekend] practice over") and "counts toward" in line
    assert weekend.summarize(cfg, store, monday) == ""                  # once
    assert store.get("weekend_history")[-1]["weekend"] == "2026-10-03"
    weekend.start(cfg, store, datetime(2026, 10, 10, 9, 0))              # next Saturday: fresh accounts
    assert store.get("weekend-day_ledger") is None and weekend.state(store)["weekend"] == "2026-10-10"


def test_the_thinking_tab_shows_the_weekend(cfg, practice):
    store = practice
    st = weekend.start(cfg, store, SATURDAY)
    store.set("weekend_state", {**st, "days": st["days"][:1]})
    weekend.replay(cfg, data_path(cfg, "aitrader.sqlite"), until=20)
    t = dashboard.thinking(cfg, store, now=SATURDAY)
    w = t["weekend"]
    assert w["active"] and w["replay"]["day"] == st["days"][0] and w["replay"]["running"] is True
    assert t["live"]["text"].startswith("Weekend practice: replaying")
    assert any(c["mode"] == "weekend-day" and c["today"] for c in w["cards"])
    assert set(w["results"]) == set(weekend.MODES)


def test_you_can_turn_each_one_off(cfg):
    from aitrader import user_settings
    assert {"weekend_replay", "weekend_crypto"} <= set(user_settings.SETTINGS)
    cfg["weekend"] = {"replay": False, "crypto": "off"}
    s = weekend.settings(cfg)
    assert s["replay"] is False and s["crypto"] is False
