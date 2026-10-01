"""Click a stock: what it is (the company) and what Kestrel knows about it (stock_info.py)."""
import json

import pytest

from aitrader import app_api, in_play, scanner, stock_info
from aitrader.brokers.base import Fill
from aitrader.config import data_path
from aitrader.storage import Store

TODAY = "2026-10-01"


def test_only_real_stock_symbols_are_looked_up():
    assert stock_info.clean(" nio ") == "NIO" and stock_info.clean("BRK.B") == "BRK.B"
    for bad in ("", "<script>", "NIO; rm", "A" * 12):
        with pytest.raises(ValueError, match="isn't a stock symbol"):
            stock_info.clean(bad)


def test_the_company_is_looked_up_once_then_remembered(cfg):
    asked = []

    def alpaca(cfg, t):
        asked.append("alpaca")
        return {"name": "NIO Inc. American Depositary Shares", "exchange": "NYSE", "tradable": True}

    def yahoo(t):
        asked.append("yahoo")
        return {"name": "NIO Inc.", "kind": "stock", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers",
                "summary": "NIO designs and sells smart electric vehicles in China."}
    first = stock_info.company(cfg, "NIO", alpaca=alpaca, yahoo=yahoo)
    assert first["name"] == "NIO Inc." and first["exchange"] == "NYSE" and first["sector"] == "Consumer Cyclical"
    again = stock_info.company(cfg, "NIO", alpaca=lambda *a: 1 / 0, yahoo=lambda *a: 1 / 0)
    assert again["name"] == "NIO Inc." and asked == ["alpaca", "yahoo"]           # remembered for 30 days

    offline = stock_info.company(cfg, "XYZ", alpaca=lambda *a: 1 / 0, yahoo=lambda *a: 1 / 0)
    assert offline == {} and "XYZ" not in json.loads(data_path(cfg, stock_info.CACHE).read_text())


def test_long_descriptions_are_cut_at_a_sentence():
    text = "First sentence here. " * 60
    short = stock_info._short(text, 100)
    assert short.endswith(".") and len(short) <= 100


def test_it_says_what_kestrel_knows_about_the_stock(cfg):
    store = Store(data_path(cfg, "aitrader.sqlite"))
    cfg["desks"]["day"]["watchlist"].append("NIO")
    scanner.update_list(cfg, [{"symbol": "NIO", "price": 3.5, "momentum_pct": 85.0, "return_1m_pct": 4.0}], [], {
        "NIO": [{"headline": "NIO prices $500M share offering", "url": "https://example.com/a", "source": "Benzinga"}]},
        TODAY, [{"symbol": "NIO", "price": 3.5}], day_pool=[{"symbol": "NIO", "price": 3.5, "atr": 0.3}])
    in_play.save(cfg, {"day": TODAY, "picks": [{"symbol": "NIO", "rvol": 4.2}]})
    store.set("too_pricey:swing", {"limit": 61.88, "tickers": {"NIO": 70.0}})
    store.set("study-day_ledger", {"cash": 300, "positions": {"NIO": {"ticker": "NIO", "qty": 72, "avg_cost": 3.44,
                                                                     "opened_on": TODAY}}})
    store.record_fill("study-day", Fill("2026-09-30", "NIO", "BUY", 10, 3.5, "orb score 1.00", 0.0, "b1"))
    store.record_fill("study-day", Fill("2026-09-30", "NIO", "SELL", 10, 3.6, "end of day", 1.0, "s1"))
    store.set("study-day_thinking", {"strategy": "tjr_model", "buy_above": 0.9, "sell_below": 0.2, "time": "2026-10-01 10:05",
                                     "top": [{"ticker": "NIO", "score": 0.95}]})
    store.set("mistakes:day", [{"tag": "buying NIO", "why": "3 trades in the last 60 days, 1 won, -$4.00"}])
    k = stock_info.kestrel_view(cfg, store, "NIO", today=TODAY)
    text = " | ".join(k["lists"])
    assert "On the day desk's watchlist" in text and "#1 on the stocks it likes: up 85.0%" in text
    assert "The swing desk considers it" in text and "Busy enough for the day desk" in text
    assert "In play today: 4.2x" in text and "Too pricey for the swing desk" in text
    assert k["holding"] == [{"account": "in its head", "desk": "day", "qty": 72, "avg_cost": 3.44, "since": TODAY}]
    assert k["finished"] == 1 and k["won"] == 1 and k["trades"][0]["gain"] == 1.0
    assert k["scores"][0]["score"] == 0.95 and k["scores"][0]["strategy"] == "tjr_model"
    assert k["danger"] == ["offering"] and k["news"][0]["source"] == "Benzinga"
    assert k["lessons"] == ["Won't buy it again for now: 3 trades in the last 60 days, 1 won, -$4.00"]


def test_the_app_and_the_phone_can_ask_about_a_stock(cfg, monkeypatch):
    from aitrader import phone_screen
    monkeypatch.setattr(stock_info, "company", lambda cfg, t: {"name": "Ford Motor Company", "kind": "stock"})
    r = app_api.handle("stock-info", cfg, payload={"ticker": "f"})
    assert r["ticker"] == "F" and r["company"]["name"] == "Ford Motor Company" and "lists" in r["kestrel"]
    assert "stock-info" in app_api.STDIN_ACTIONS and "stock-info" in phone_screen.ALLOWED
    from aitrader import config
    monkeypatch.setattr(config, "load_config", lambda: cfg)
    monkeypatch.setattr(phone_screen, "access_key", lambda cfg: "k")
    code, body = phone_screen.answer(cfg, json.dumps({"action": "stock-info", "input": json.dumps({"ticker": "F"})}).encode(), "k")
    assert code == 200 and json.loads(body)["ticker"] == "F"
