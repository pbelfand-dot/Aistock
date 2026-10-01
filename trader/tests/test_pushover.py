"""Pushover push alerts (pushover.py). Pushover itself is faked here: nothing leaves the test."""
import io
import json
import urllib.error
import urllib.parse

import pytest

import run
from aitrader import app_api, phone, pushover
from aitrader.config import data_path
from aitrader.storage import Store

USER, TOKEN = "u" * 30, "a" * 30


class FakePushover:
    """Stands in for api.pushover.net: records each request's form fields."""
    def __init__(self, refuse=None):
        self.requests, self.refuse = [], refuse

    def __call__(self, request, timeout=20):
        fields = dict(urllib.parse.parse_qsl(request.data.decode()))
        self.requests.append((request.full_url, fields))
        if self.refuse:
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {},
                                         io.BytesIO(json.dumps({"status": 0, "errors": [self.refuse]}).encode()))
        answer = {"status": 1, "request": "r1"}
        if request.full_url.endswith("users/validate.json"):
            answer["devices"] = ["iphone"]
        return io.BytesIO(json.dumps(answer).encode())


@pytest.fixture
def push(cfg, tmp_path, monkeypatch):
    fake = FakePushover()
    monkeypatch.setattr(pushover.urllib.request, "urlopen", fake)
    cfg["secrets"].update(pushover_user=USER, pushover_token=TOKEN)
    return cfg, fake


def test_alerts_are_as_loud_as_they_need_to_be():
    assert pushover.priority_of("[live-day] KILL SWITCH TRIPPED: sold everything") == 2    # real money: until you look
    assert pushover.priority_of("[study-day] KILL SWITCH (in its head): sold everything") == 1
    assert pushover.priority_of("!!! swing: evening stop check failed") == 1
    assert pushover.priority_of("[paper-swing] BUY 1 XLE @ $61.59 (spent $61.59): momentum") == 0
    assert pushover.priority_of("WARNING: the swing desk missed today's decision") == 0
    assert pushover.priority_of("[study-day] LEARNED: won't repeat buying NIO") == -1      # quiet


def test_a_push_alert_carries_the_keys_the_text_and_its_priority(push):
    cfg, fake = push
    assert pushover.send(cfg, "[live-day] KILL SWITCH TRIPPED " + "x" * 2000)
    url, fields = fake.requests[0]
    assert url == "https://api.pushover.net/1/messages.json"
    assert fields["token"] == TOKEN and fields["user"] == USER and fields["title"] == "Kestrel"
    assert len(fields["message"]) == 1024                                             # Pushover's limit
    assert fields["priority"] == "2" and fields["retry"] == "60" and fields["expire"] == "3600"
    assert pushover.sent_this_month(cfg) == 1


def test_a_failed_alert_never_stops_trading_and_the_monthly_limit_is_respected(cfg, monkeypatch):
    cfg["secrets"].update(pushover_user=USER, pushover_token=TOKEN)
    monkeypatch.setattr(pushover.urllib.request, "urlopen", FakePushover(refuse="application token is invalid"))
    assert pushover.send(cfg, "[paper-day] BUY 1 F") is False                          # no exception
    with pytest.raises(RuntimeError, match="application token is invalid"):
        pushover.validate(cfg)

    fake = FakePushover()
    monkeypatch.setattr(pushover.urllib.request, "urlopen", fake)
    data_path(cfg, pushover.COUNT_FILE).write_text(json.dumps({"month": pushover._count(cfg)["month"], "sent": 9_600}))
    assert pushover.send(cfg, "[paper-day] BUY 1 F") is False                          # near the limit: skipped
    assert pushover.send(cfg, "!!! something is wrong") is True                        # urgent still goes
    assert len(fake.requests) == 1


def test_the_journal_lines_that_matter_reach_pushover_and_telegram(push, monkeypatch):
    cfg, fake = push
    queued, told = [], []
    monkeypatch.setattr(pushover, "send_later", lambda cfg, message, **kw: queued.append((message, kw)))
    monkeypatch.setattr(phone, "send", lambda cfg, text, chat=None: told.append(text) or True)
    forward = phone.forwarder(cfg)
    forward("[paper-day] BUY 3 F @ $12.00 (spent $36.00): tjr_model score 1.00")
    forward("Daily check-in. Desks: swing STUDY, day STUDY")                           # routine: not sent
    assert [m for m, _ in queued] == ["[paper-day] BUY 3 F @ $12.00 (spent $36.00): tjr_model score 1.00"]
    assert told == []                                                                 # Telegram isn't set up

    report = data_path(cfg, "reports/after-market-2026-10-01.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# After-market report\n\n## In plain English\n\nA quiet day: one win.\n\n## The market\n\nSPY up.\n")
    forward("After-market report for 2026-10-01 written")
    assert queued[-1] == ("A quiet day: one win.", {"title": "Kestrel: after-market report 2026-10-01", "priority": 0})

    cfg["secrets"].update(telegram_token="1:x", telegram_chat="42")                  # both set up: both get it
    phone.forwarder(cfg)("!!! swing: evening stop check failed")
    assert told == ["!!! swing: evening stop check failed"] and queued[-1][0] == "!!! swing: evening stop check failed"


def test_setup_checks_the_keys_with_pushover_saves_them_privately_and_sends_a_test(cfg, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LIVE_TRADING_ENABLED=false\n")
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: False)
    fake = FakePushover()
    monkeypatch.setattr(pushover.urllib.request, "urlopen", fake)
    with pytest.raises(ValueError, match="30 letters and digits"):
        app_api.handle("save-pushover", cfg, payload={"user": "short", "token": TOKEN})
    with pytest.raises(ValueError, match="are the same"):
        app_api.handle("save-pushover", cfg, payload={"user": TOKEN, "token": TOKEN})
    done = app_api.handle("save-pushover", cfg, payload={"user": USER, "token": TOKEN})
    assert "A test alert is on its way on iphone" in done["message"]
    text = env.read_text()
    assert f"PUSHOVER_USER_KEY={USER}\n" in text and f"PUSHOVER_APP_TOKEN={TOKEN}\n" in text
    assert "LIVE_TRADING_ENABLED=false" in text and env.stat().st_mode & 0o777 == 0o600
    assert [u.rsplit("/", 1)[1] for u, _ in fake.requests] == ["validate.json", "messages.json"]
    status = app_api.setup_status(cfg, Store(tmp_path / "aitrader.sqlite"))["phone"]["pushover"]
    assert status == {"keys": True, "sent": 1, "limit": 10_000}
    assert app_api.handle("pushover-test", cfg)["ok"]

    monkeypatch.setattr(pushover.urllib.request, "urlopen", FakePushover(refuse="user identifier is not a valid user"))
    with pytest.raises(ValueError, match="didn't accept them"):
        app_api.handle("save-pushover", cfg, payload={"user": "b" * 30, "token": TOKEN})
    assert not pushover.has_keys(cfg)                                                  # refused keys aren't kept


def test_the_autopilot_forwards_alerts_with_only_pushover(push, monkeypatch):
    cfg, _ = push
    started = []
    monkeypatch.setattr(phone, "listen", lambda *a, **k: started.append("telegram"))
    store = Store(":memory:")
    run.start_phone(cfg, store)
    assert store.on_log is not None and started == []                                  # alerts yes; no Telegram listener
