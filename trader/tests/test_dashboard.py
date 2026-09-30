"""The app's dashboard: its numbers, the bridge the app uses to ask the bot, and what Pause means."""
import json
from datetime import datetime

import pandas as pd
import pytest

from aitrader import dashboard
from aitrader.brokers.base import Fill
from aitrader.phases import Phase, set_phase
from aitrader.storage import Store


@pytest.fixture
def filled(cfg, monkeypatch):
    """A paper swing desk that has traded for a few days, plus saved prices. It's 4:30pm on the 25th."""
    monkeypatch.setattr(dashboard, "now_ny", lambda: datetime(2026, 9, 25, 16, 30))
    cfg["data"]["source"] = "yahoo"
    cfg["paper"]["starting_cash"] = 1000                # $500 per desk, like the real setup
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    set_phase(store, "swing", Phase.PAPER, "test")
    for date, value in (("2026-09-23", 500.0), ("2026-09-24", 505.0), ("2026-09-25", 498.0)):
        store.record_equity("paper-swing", date, value, 400.0)
    store.record_fill("paper-swing", Fill("2026-09-23", "AAA", "BUY", 2, 50.0, "test buy", order_id="1"))
    store.record_fill("paper-swing", Fill("2026-09-24", "BBB", "SELL", 1, 20.0, "test sell", 3.0, "2"))
    store.set("paper-swing_ledger", {"cash": 400.0, "unsettled": {}, "pending": [], "positions": {
        "AAA": {"ticker": "AAA", "qty": 2, "avg_cost": 50.0, "opened_on": "2026-09-23", "stop_order_id": ""}}})
    for ticker, closes in (("AAA", [48.0, 49.0, 49.0]), ("MKT", [100.0, 101.0, 102.0])):
        path = dashboard.data_path(cfg, f"cache/yahoo/1d/{ticker}.csv")
        pd.DataFrame({"close": closes}, index=pd.to_datetime(["2026-09-23", "2026-09-24", "2026-09-25"])).to_csv(path)
    return cfg, store


def test_snapshot_reads_like_a_brokerage_account(filled):
    cfg, store = filled
    snap = json.loads(json.dumps(dashboard.snapshot(cfg, store)))         # must be plain JSON
    paper = snap["accounts"]["paper"]
    assert paper["active"] and not snap["accounts"]["live"]["active"]
    assert paper["dates"] == ["2026-09-23", "2026-09-24", "2026-09-25"]
    assert paper["series"]["total"] == [1000.0, 1005.0, 998.0]           # day desk not started = its $500 cash
    assert paper["series"]["benchmark"] == [1000.0, 1010.0, 1020.0]      # SPY-style line, same starting amount
    assert paper["value"] == 998.0 and paper["day_change"] == -7.0 and paper["total_return_pct"] == -0.2
    (pos,) = paper["positions"]
    assert pos["ticker"] == "AAA" and pos["last"] == 49.0 and pos["gain"] == -2.0 and pos["stop"] == 46.5
    assert [a["side"] for a in paper["activity"]] == ["SELL", "BUY"]      # newest first
    assert paper["win_rate_pct"] == 100.0 and paper["closed_trades"] == 1
    assert {d["desk"]: d["step"] for d in snap["desks"]} == {"swing": 3, "day": 1}
    assert next(w for w in snap["watchlist"] if w["ticker"] == "AAA")["change_pct"] == 0.0


def ask(monkeypatch, capsys, cfg, *args):
    """What the app does: run `python -m aitrader.app_api ...` and read the JSON it prints."""
    from aitrader import app_api
    monkeypatch.setattr(app_api, "load_config", lambda: cfg)
    capsys.readouterr()
    assert app_api.main(list(args)) == 0
    return json.loads(capsys.readouterr().out)          # only JSON: the bot's own messages go elsewhere


def test_the_app_asks_the_bot_directly_and_gets_json(filled, monkeypatch, capsys):
    cfg, store = filled
    assert ask(monkeypatch, capsys, cfg, "snapshot")["accounts"]["paper"]["value"] == 998.0

    answer = ask(monkeypatch, capsys, cfg, "kill")                        # no typed phrase: nothing happens
    assert "SELL EVERYTHING" in answer["error"] and not store.get("halted:swing")
    assert "error" in ask(monkeypatch, capsys, cfg, "kill", "--confirm", "sell everything")

    answer = ask(monkeypatch, capsys, cfg, "pause")                       # Pause: every desk, nothing sold
    assert "no new trades" in answer["message"]
    assert store.get("halted:swing") and store.get("halted:day") and not store.get("exiting:swing")
    assert "PAUSED by you, from the app" in store.journal(1)[0][1]
    assert store.get("paper-swing_ledger")["positions"]                   # still owns its stock



def test_the_app_updates_itself_only_while_no_real_money_is_involved(filled, monkeypatch, capsys):
    cfg, store = filled
    assert ask(monkeypatch, capsys, cfg, "update-policy") == {"real_money": False, "reasons": []}   # paper only

    cfg["live_trading_enabled"] = True                                     # switched on in .env
    assert ask(monkeypatch, capsys, cfg, "update-policy")["real_money"]
    cfg["live_trading_enabled"] = False

    set_phase(store, "day", Phase.LIVE, "test")                           # a desk trading real money
    assert "day desk is trading real money" in ask(monkeypatch, capsys, cfg, "update-policy")["reasons"][0]
    set_phase(store, "day", Phase.PAPER, "test")

    store.set("live-swing_ledger", {"cash": 0, "unsettled": {}, "pending": [], "positions": {"AAA": {"qty": 1}}})
    answer = ask(monkeypatch, capsys, cfg, "update-policy")                # still owns real shares
    assert answer["real_money"] and "owns real shares" in answer["reasons"][0]


# ---------------------------------------------------------------- the Setup screen in the app
def test_setup_screen_saves_paper_keys_privately_and_refuses_live_ones(filled, tmp_path, monkeypatch, capsys):
    import io
    from aitrader import app_api
    cfg, store = filled
    env = tmp_path / ".env"
    env.write_text("# my keys\nALPACA_PAPER_API_KEY=\nSCHWAB_APP_KEY=abc\nLIVE_TRADING_ENABLED=false\n")
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: False)

    def save(key_id, secret):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"key_id": key_id, "secret": secret})))
        return ask(monkeypatch, capsys, cfg, "save-keys")

    assert "Saved on this Mac only" in save(" PKABCDEFGHIJ123456 ", "s" * 40)["message"]
    text = env.read_text()
    assert "ALPACA_PAPER_API_KEY=PKABCDEFGHIJ123456\n" in text and f"ALPACA_PAPER_SECRET_KEY={'s' * 40}" in text
    assert "# my keys" in text and "SCHWAB_APP_KEY=abc" in text              # everything else kept
    assert env.stat().st_mode & 0o777 == 0o600                              # only you can read it

    assert "LIVE (real money) key" in save("AKABCDEFGHIJ123456", "s" * 40)["error"]
    assert "error" in save("PK12", "s" * 40)                                 # too short: a bad copy-paste
    assert "error" in save("PKABCDEFGHIJ\nLIVE_TRADING_ENABLED=true", "s" * 40)
    assert "LIVE_TRADING_ENABLED=false" in env.read_text() and "PKABCDEFGHIJ123456" in env.read_text()


def test_setup_screen_says_what_is_next_and_can_resume(filled, monkeypatch, capsys):
    from aitrader import mac_service
    cfg, store = filled
    monkeypatch.setattr(mac_service, "is_running", lambda: False)
    status = ask(monkeypatch, capsys, cfg, "setup-status")
    assert status["autopilot_on"] is False
    swing = next(d for d in status["desks"] if d["desk"] == "swing")
    assert swing["phase"] == "PAPER" and "Paper trading" in swing["next"]

    ask(monkeypatch, capsys, cfg, "pause")
    assert all(d["halted"] for d in ask(monkeypatch, capsys, cfg, "setup-status")["desks"])
    assert ask(monkeypatch, capsys, cfg, "resume")["message"].startswith("Resumed")
    assert not any(store.get(f"halted:{d}") for d in cfg["desks"])


def test_setup_screen_checks_prices_and_says_when_keys_are_missing(filled, monkeypatch, capsys):
    from aitrader import market_data
    cfg, store = filled
    cfg["secrets"].update(alpaca_paper_key="", alpaca_paper_secret="")
    frame = pd.DataFrame({"close": [101.5]}, index=pd.to_datetime(["2026-09-25"]))
    monkeypatch.setattr(market_data.MarketData, "history", lambda self, *a, **k: frame)
    result = ask(monkeypatch, capsys, cfg, "check-keys")
    assert result["prices"]["ok"] and "$101.50" in result["prices"]["text"]
    assert not result["paper"]["ok"] and "no keys yet" in result["paper"]["text"]

# ---------------------------------------------------------------- what "paused" means
@pytest.fixture
def paused_desk(cfg, monkeypatch):
    """A paused day desk that owns a stock at the broker, with the trading steps recorded."""
    import run
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    set_phase(store, "day", Phase.PAPER, "test")
    store.set("paper-day_ledger", {"cash": 400.0, "unsettled": {}, "pending": [], "positions": {
        "EEE": {"ticker": "EEE", "qty": 2, "avg_cost": 50.0, "opened_on": "2026-09-28", "stop_order_id": ""}}})
    store.set("halted:day", True)
    calls = []
    monkeypatch.setattr(run, "broker_backed", lambda cfg, phase: True)
    monkeypatch.setattr(run, "continue_exit", lambda *a: calls.append("sell everything") or "getting out")
    monkeypatch.setattr(run, "_trade_desk", lambda cfg, store, data, desk, phase, now, stops_only, *a:
                        calls.append(f"cycle stops_only={stops_only}") or "value $500")
    return run, cfg, store, calls


def test_paused_desk_never_trades_but_keeps_guarding_what_it_owns(paused_desk):
    run, cfg, store, calls = paused_desk
    message = run.trade_desk(cfg, store, None, "day", datetime(2026, 9, 28, 11, 0))
    assert calls == ["cycle stops_only=True"]         # stop-losses + the day desk's sell-before-close only
    assert "HALTED" in message


def test_emergency_exit_keeps_selling_until_flat(paused_desk):
    run, cfg, store, calls = paused_desk
    store.set("exiting:day", True)
    run.trade_desk(cfg, store, None, "day", datetime(2026, 9, 28, 11, 0))
    assert calls == ["sell everything"]


def test_resume_waits_until_an_emergency_exit_is_finished(paused_desk):
    import argparse
    run, cfg, store, _ = paused_desk
    store.set("exiting:day", True)
    run.cmd_resume(cfg, store, argparse.Namespace(desk="day"))
    assert store.get("halted:day")                     # still selling: stays halted
    store.set("paper-day_ledger", {"cash": 500.0, "unsettled": {}, "pending": [], "positions": {}})
    run.cmd_resume(cfg, store, argparse.Namespace(desk="day"))
    assert not store.get("halted:day") and not store.get("exiting:day")


def test_demo_runs_the_real_code_and_never_touches_your_data(cfg, tmp_path, monkeypatch, capsys):
    from aitrader import demo
    monkeypatch.setattr(demo, "DAYS", 300)
    monkeypatch.setattr(demo, "INTRADAY_DAYS", 6)
    monkeypatch.setattr(demo, "PAPER_DAYS", 5)
    monkeypatch.setattr(demo, "DAY_DESK_PAPER_DAYS", 2)
    cfg["desks"]["swing"]["watchlist"] = cfg["desks"]["swing"]["watchlist"][:3]
    cfg["desks"]["day"]["watchlist"] = cfg["desks"]["day"]["watchlist"][:3]
    assert "isn't built" in ask(monkeypatch, capsys, cfg, "snapshot", "--demo")["error"]

    assert ask(monkeypatch, capsys, cfg, "demo-build")["message"] == "Demo data is ready."
    assert not (tmp_path / "aitrader.sqlite").exists()                    # your real data: untouched
    snap = ask(monkeypatch, capsys, cfg, "snapshot", "--demo")
    assert snap["demo"] and snap["prices"] == "demo"
    assert [d["phase"] for d in snap["desks"]] == ["PAPER", "PAPER"]
    assert len(snap["accounts"]["paper"]["dates"]) == 5 and snap["accounts"]["paper"]["series"]["benchmark"]

    ask(monkeypatch, capsys, cfg, "kill", "--confirm", "SELL EVERYTHING", "--demo")   # works offline
    store = Store(tmp_path / "demo" / "aitrader.sqlite")
    assert store.get("paper-swing_ledger")["positions"] == {} == store.get("paper-day_ledger")["positions"]
    assert store.get("halted:swing") and not store.get("exiting:swing")
    paper = ask(monkeypatch, capsys, cfg, "snapshot", "--demo")["accounts"]["paper"]
    assert paper["value"] == paper["cash"]            # sold out: the headline value is just the cash
    assert not (tmp_path / "aitrader.sqlite").exists()


# ---------------------------------------------------------------- Setup: real money, Schwab, settings (for later)
def _stdin(monkeypatch, payload):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))


def test_settings_you_change_in_the_app_survive_updates_and_bad_values_are_refused(filled, tmp_path, monkeypatch, capsys):
    from aitrader import app_api, user_settings
    from aitrader.config import load_config
    cfg, store = filled
    monkeypatch.setattr(user_settings, "settings_file", lambda: tmp_path / "my_settings.json")
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: False)
    _stdin(monkeypatch, {"broker": "schwab", "real_money_cap": "50", "account_type": "cash"})
    assert "stay when the app updates" in ask(monkeypatch, capsys, cfg, "save-settings")["message"]
    fresh = load_config()                                                    # config.yaml + your settings
    assert fresh["broker"] == "schwab" and fresh["live"]["max_capital"] == 50 and fresh["live"]["account_type"] == "cash"

    _stdin(monkeypatch, {"real_money_cap": "5", "broker": "alpaca"})         # below the $10 floor: nothing saved
    assert "between" in ask(monkeypatch, capsys, cfg, "save-settings")["error"]
    assert load_config()["broker"] == "schwab"
    (tmp_path / "my_settings.json").write_text('{"broker": "robinhood", "real_money_cap": 75}')   # edited by hand
    fresh = load_config()
    assert fresh["broker"] == "alpaca" and fresh["live"]["max_capital"] == 75  # the bad one ignored, not half-applied


def test_real_money_keys_and_schwab_keys_are_saved_privately(filled, tmp_path, monkeypatch, capsys):
    from aitrader import app_api
    cfg, store = filled
    env = tmp_path / ".env"
    env.write_text("LIVE_TRADING_ENABLED=false\n")
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: False)

    _stdin(monkeypatch, {"key_id": "PKABCDEFGHIJ123456", "secret": "s" * 40})
    assert "PAPER key" in ask(monkeypatch, capsys, cfg, "save-live-keys")["error"]
    _stdin(monkeypatch, {"key_id": "AKABCDEFGHIJ123456", "secret": "s" * 40})
    assert "Nothing trades real money" in ask(monkeypatch, capsys, cfg, "save-live-keys")["message"]
    assert "ALPACA_LIVE_API_KEY=AKABCDEFGHIJ123456" in env.read_text()
    assert "LIVE_TRADING_ENABLED=false" in env.read_text()                   # saving keys never switches it on

    _stdin(monkeypatch, {"app_key": "A" * 32, "app_secret": "B" * 16, "callback_url": "https://127.0.0.1:8182/"})
    assert "no slash at the end" in ask(monkeypatch, capsys, cfg, "save-schwab-keys")["error"]
    _stdin(monkeypatch, {"app_key": "A" * 32, "app_secret": "B" * 16, "callback_url": "https://127.0.0.1:8182",
                         "account_number": "12345678"})
    assert "Open Schwab login" in ask(monkeypatch, capsys, cfg, "save-schwab-keys")["message"]
    text = env.read_text()
    assert f"SCHWAB_APP_KEY={'A' * 32}" in text and "SCHWAB_ACCOUNT_NUMBER=12345678" in text
    assert env.stat().st_mode & 0o777 == 0o600


def test_schwab_login_from_the_app_open_the_page_then_paste_where_you_landed(filled, monkeypatch, capsys):
    pytest.importorskip("schwab")
    import schwab
    cfg, store = filled
    cfg["secrets"].update(app_key="A" * 32, app_secret="B" * 16, callback_url="https://127.0.0.1:8182")
    _stdin(monkeypatch, {"url": "https://127.0.0.1:8182/?code=abc"})
    assert "first" in ask(monkeypatch, capsys, cfg, "schwab-login-finish")["error"]      # step 1 wasn't done

    url = ask(monkeypatch, capsys, cfg, "schwab-login-start")["url"]
    assert url.startswith("https://api.schwabapi.com/v1/oauth/authorize") and "state=" in url
    _stdin(monkeypatch, {"url": "https://google.com/?code=abc"})
    assert "address bar" in ask(monkeypatch, capsys, cfg, "schwab-login-finish")["error"]

    def fake_exchange(api_key, secret, ctx, received, write):              # Schwab's server, pretend
        assert "code=abc" in received and ctx.callback_url == "https://127.0.0.1:8182"
        import time
        write({"creation_timestamp": int(time.time()), "token": {"refresh_token": "r"}})
    monkeypatch.setattr(schwab.auth, "client_from_received_url", fake_exchange)
    _stdin(monkeypatch, {"url": "https://127.0.0.1:8182/?code=abc&session=x"})
    answer = ask(monkeypatch, capsys, cfg, "schwab-login-finish")
    assert "Logged in to Schwab" in answer.get("message", answer)
    status = ask(monkeypatch, capsys, cfg, "setup-status")
    assert 6.9 < status["schwab"]["days_left"] <= 7


def test_setup_shows_good_faith_violations_and_cash_rules(filled, monkeypatch, capsys):
    from aitrader.brokers import Ledger
    cfg, store = filled
    cfg["broker"], cfg["live"]["account_type"] = "schwab", "auto"
    ledger = Ledger(50)
    ledger.gfv_events = ["2020-01-02", __import__("datetime").date.today().isoformat()]
    store.set("live-day_ledger", ledger.to_dict())
    gfv = ask(monkeypatch, capsys, cfg, "setup-status")["gfv"]
    assert gfv == {"cash_rules": True, "violations": 1, "limit": 3}          # only the last 12 months count
