"""Your phone: a private Telegram bot for alerts and commands (Telegram itself is faked here)."""
import threading

import pytest

from aitrader import app_api, phone
from aitrader.brokers.base import Fill
from aitrader.config import data_path
from aitrader.storage import Store

TOKEN = "1234567890:AAbbccddeeffgghhiijjkkllmmnnooppqq"


class FakeTelegram:
    """Stands in for api.telegram.org: records what the bot sends, and hands out queued messages."""
    def __init__(self, updates=()):
        self.sent, self.updates, self.stop = [], list(updates), threading.Event()

    def __call__(self, cfg, method, wait=20, **params):
        if method == "sendMessage":
            self.sent.append((str(params["chat_id"]), params["text"]))
            return {}
        if method == "getMe":
            return {"username": "my_kestrel_bot"}
        if method == "getUpdates":
            if not self.updates:
                self.stop.set()
                return []
            batch, self.updates = self.updates, []
            return batch
        raise AssertionError(method)


def message(n, chat, text):
    return {"update_id": n, "message": {"chat": {"id": chat}, "text": text}}


@pytest.fixture
def bot(cfg, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=\n")
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "load_config", lambda: cfg)
    cfg["secrets"].update(telegram_token=TOKEN, telegram_chat="")
    return cfg, env


def run_listener(cfg, fake, monkeypatch):
    monkeypatch.setattr(phone, "call", fake)
    phone.listen(cfg, lambda: Store(data_path(cfg, "aitrader.sqlite")), fake.stop)


def test_only_the_phone_that_sends_the_pairing_code_is_ever_answered(bot, monkeypatch):
    cfg, env = bot
    code = phone.pairing_code(cfg, new=True)
    fake = FakeTelegram([message(1, 99, "/start 000000"), message(2, 42, f"/start {code}"),
                         message(3, 99, "/status"), message(4, 42, "/status")])
    run_listener(cfg, fake, monkeypatch)
    assert fake.sent[0][0] == "99" and "pairing code" in fake.sent[0][1]      # wrong code: told how, not paired
    assert fake.sent[1] == ("42", fake.sent[1][1]) and fake.sent[1][1].startswith("Paired.")
    assert "TELEGRAM_CHAT_ID=42" in env.read_text() and phone.owner(cfg) == "42"
    assert all(chat == "42" for chat, _ in fake.sent[1:])                      # the stranger gets nothing
    assert fake.sent[-1][1].startswith("Kestrel status")


def test_commands_status_trades_report_pause_and_a_guarded_kill(bot, monkeypatch):
    cfg, _ = bot
    cfg["secrets"]["telegram_chat"] = "42"
    store = Store(data_path(cfg, "aitrader.sqlite"))
    store.record_fill("paper-swing", Fill("2026-09-23", "AAA", "BUY", 2, 50.0, "momentum", order_id="1"))
    store.record_fill("paper-swing", Fill("2026-09-25", "AAA", "SELL", 2, 55.0, "exit", 10.0, "2"))
    assert "AAA (swing, paper): spent $100.00, got $110.00, WIN +$10.00 (+10.0%)" in phone.handle(cfg, store, "/trades")
    assert "No after-market report" in phone.handle(cfg, store, "/report")
    assert phone.handle(cfg, store, "/pause").startswith("Paused")
    assert all(store.get(f"halted:{d}") for d in ("swing", "day"))
    killed = []
    monkeypatch.setattr(app_api, "handle", lambda action, cfg, confirm=None: killed.append((action, confirm)) or {"message": "stopped"})
    assert "send exactly: /kill SELL EVERYTHING" in phone.handle(cfg, store, "/kill")
    assert killed == []                                                         # no phrase, no emergency stop
    assert phone.handle(cfg, store, "/kill SELL EVERYTHING") == "stopped" and killed == [("kill", "SELL EVERYTHING")]
    assert "/status" in phone.handle(cfg, store, "hello")                         # anything else: the help


def test_trades_the_daily_line_and_the_report_reach_the_phone_but_routine_lines_dont(bot, monkeypatch):
    cfg, _ = bot
    cfg["secrets"]["telegram_chat"] = "42"
    fake = FakeTelegram()
    monkeypatch.setattr(phone, "call", fake)
    store = Store(data_path(cfg, "aitrader.sqlite"))
    store.on_log = phone.forwarder(cfg)
    store.log("[paper-swing] BUY 2 AAA @ $50.00 (spent $100.00): momentum score 0.95 >= 0.8")
    store.log("[study-day] 2026-09-29: value $509.30, today +1.62% (+$8.10); since the start +1.86% (+$9.30)")
    store.log("Daily check-in. Desks: swing STUDY, day STUDY")                 # routine: not sent
    data_path(cfg, "reports/after-market-2026-09-29.md").write_text("# After-market report: x\n\nbody")
    store.log("After-market report for 2026-09-29 is ready (Journal tab; after-market-2026-09-29.md)")
    texts = [t for _, t in fake.sent]
    assert texts[0].startswith("[paper-swing] BUY 2 AAA") and "since the start" in texts[1]
    assert texts[2].startswith("# After-market report") and len(texts) == 3


def test_a_broken_alert_never_stops_the_bot(cfg):
    store = Store(data_path(cfg, "aitrader.sqlite"))
    store.on_log = lambda m: 1 / 0
    store.log("[paper-swing] BUY 1 AAA @ $1.00 (spent $1.00): x")              # no exception
    assert store.journal(1)[0][1].startswith("[paper-swing] BUY")


def test_setup_checks_the_token_with_telegram_and_shows_the_pairing_code(bot, monkeypatch, capsys):
    import json
    cfg, env = bot
    cfg["secrets"]["telegram_token"] = ""
    monkeypatch.setattr(phone, "call", FakeTelegram())
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: False)
    with pytest.raises(ValueError, match="doesn't look like"):
        app_api.save_phone(cfg, {"token": "nope"})
    r = app_api.save_phone(cfg, {"token": TOKEN})
    assert r["bot"] == "my_kestrel_bot" and f"/start {r['code']}" in r["message"]
    assert f"TELEGRAM_BOT_TOKEN={TOKEN}" in env.read_text()
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    status = app_api.phone_status(cfg)
    assert (status["token"], status["paired"], status["code"]) == (True, False, r["code"])
    capsys.readouterr()
    app_api.main(["phone-test"])
    assert "Not paired yet" in json.loads(capsys.readouterr().out)["text"]


# ---------------------------------------------------------------- the Kestrel screen on your phone
def test_the_phone_screen_needs_the_key_and_only_watches_and_uses_the_safety_buttons(cfg, monkeypatch):
    import json
    from aitrader import phone_screen
    monkeypatch.setattr(app_api, "load_config", lambda: cfg)
    import aitrader.config as config_module
    monkeypatch.setattr(config_module, "load_config", lambda: cfg)
    key = phone_screen.access_key(cfg, new=True)
    code, text = phone_screen.answer(cfg, b'{"action": "snapshot"}', "wrong")
    assert code == 401 and "link from the Mac" in json.loads(text)["error"]
    code, text = phone_screen.answer(cfg, b'{"action": "snapshot"}', key)
    assert code == 200 and "accounts" in json.loads(text)
    assert "on the Mac" in json.loads(phone_screen.answer(cfg, b'{"action": "save-keys"}', key)[1])["error"]
    assert "SELL EVERYTHING" in json.loads(phone_screen.answer(cfg, b'{"action": "kill"}', key)[1])["error"]
    assert json.loads(phone_screen.answer(cfg, b'{"action": "pause"}', key)[1])["message"].startswith("Paused")


def test_the_phone_gets_the_same_screen_over_http(cfg, monkeypatch):
    import http.server
    import json
    import urllib.error
    import urllib.request
    from aitrader import phone_screen
    import aitrader.config as config_module
    monkeypatch.setattr(config_module, "load_config", lambda: cfg)
    key = phone_screen.access_key(cfg, new=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), phone_screen.make_handler(cfg))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "window.kestrelPhone = true" in page and "X-Kestrel-Key" in page and 'id="hero"' in page
        assert json.loads(urllib.request.urlopen(base + "/manifest.json").read())["name"] == "Kestrel"
        ask = lambda k: urllib.request.urlopen(urllib.request.Request(
            base + "/api", data=b'{"action": "snapshot"}', headers={"X-Kestrel-Key": k}))
        assert "accounts" in json.loads(ask(key).read())
        with pytest.raises(urllib.error.HTTPError) as no:
            ask("guess")
        assert no.value.code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_the_phone_screen_is_never_served_without_tailscale(cfg, monkeypatch):
    from aitrader import phone_screen
    real = phone_screen.tailscale_ip()                    # this test machine has no Tailscale
    assert real is None or real.startswith("100.")
    monkeypatch.setattr(phone_screen, "tailscale_ip", lambda: None)
    started = []
    monkeypatch.setattr(phone_screen.http.server, "ThreadingHTTPServer", lambda *a: started.append(a))
    stop = threading.Event()
    stop.set()
    phone_screen.serve_forever(cfg, stop)
    assert started == [] and phone_screen.link(cfg) is None


def test_setup_shows_the_phone_screen_switch_and_link(bot, monkeypatch):
    from aitrader import phone_screen
    cfg, _ = bot
    monkeypatch.setattr(phone_screen, "tailscale_ip", lambda: "100.101.102.103")
    assert app_api.phone_status(cfg)["screen"] == {"on": False, "tailscale": True, "link": None}
    cfg["phone"] = {"screen": "on"}
    link = app_api.phone_status(cfg)["screen"]["link"]
    assert link.startswith("http://100.101.102.103:8765/#key=") and phone_screen.access_key(cfg) in link
    cfg["secrets"]["telegram_chat"] = "42"
    fake = FakeTelegram()
    monkeypatch.setattr(phone, "call", fake)
    assert app_api.phone_screen_send(cfg)["ok"] and link in fake.sent[0][1]
