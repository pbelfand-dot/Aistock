"""The dead-man's switch: Kestrel pings healthchecks.io every cycle, says "fail" when trading keeps
failing, and Setup checks the address before saving it. Nothing goes online: healthchecks.io is faked."""
import pytest

from aitrader import app_api, uptime
from aitrader.storage import Store

URL = "https://hc-ping.com/0f8b1a2c-3d4e-4f50-8a6b-7c8d9e0f1a2b"


class Answer:
    def __init__(self, status=200):
        self.status_code = status


@pytest.fixture
def pings(monkeypatch):
    sent = []
    monkeypatch.setattr(uptime, "_post", lambda url, data, timeout: sent.append((url, data.decode())) or Answer())
    uptime._result.clear()
    return sent


def test_only_ping_addresses_are_accepted():
    assert uptime.valid(URL) and uptime.valid(URL + "/")
    assert uptime.valid("https://hc-ping.com/abcdefghijklmnopqrstuv/kestrel")        # ping key + slug
    assert not uptime.valid("http://hc-ping.com/" + URL[-36:])                          # not https
    assert not uptime.valid("hc-ping.com") and not uptime.valid("https://hc-ping.com/")


def test_every_cycle_pings_and_trading_that_keeps_failing_says_fail(cfg, pings, tmp_path):
    store = Store(tmp_path / "aitrader.sqlite")
    assert uptime.after_cycle(cfg, store, {}, background=False) == "" and pings == []   # not set up: nothing sent
    cfg["secrets"]["healthcheck_url"] = URL
    uptime.after_cycle(cfg, store, {}, background=False)
    assert pings[-1] == (URL, "ok") and store.get("uptime_last")["ok"]
    uptime.after_cycle(cfg, store, {"scan": "boom"}, background=False)                 # not a trading job
    assert pings[-1] == (URL, "ok")
    for _ in range(2):
        assert uptime.after_cycle(cfg, store, {"swing-stops": "ConnectionError()"}, background=False) == ""
        assert pings[-1] == (URL, "ok")                                                 # one hiccup isn't an alert
    reason = uptime.after_cycle(cfg, store, {"swing-stops": "ConnectionError()"}, background=False)
    assert pings[-1][0] == URL + "/fail" and "swing-stops failed: ConnectionError()" in pings[-1][1]
    assert reason.endswith("(3 cycles in a row)") and store.get("uptime_last")["fail"] == reason
    uptime.after_cycle(cfg, store, {}, background=False)
    assert pings[-1] == (URL, "ok") and store.get("uptime_fail_streak") == 0           # recovered: clears it


def test_a_ping_that_cant_get_through_is_shown_in_setup(cfg, monkeypatch, tmp_path):
    cfg["secrets"]["healthcheck_url"] = URL

    def down(url, data, timeout):
        raise ConnectionError("no internet")
    monkeypatch.setattr(uptime, "_post", down)
    store = Store(tmp_path / "aitrader.sqlite")
    uptime.after_cycle(cfg, store, {}, background=False)
    assert uptime.status(cfg, store)["last"]["problem"] == "couldn't reach healthchecks.io (ConnectionError)"


def test_setup_tries_the_address_before_saving_it(cfg, pings, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: None)
    with pytest.raises(ValueError, match="Ping URL"):
        app_api.save_healthcheck(cfg, {"url": "my check"})
    monkeypatch.setattr(uptime, "_post", lambda url, data, timeout: Answer(404))
    with pytest.raises(ValueError, match="said 404"):
        app_api.save_healthcheck(cfg, {"url": URL})
    assert not env.exists()                                                             # nothing saved
    monkeypatch.setattr(uptime, "_post", lambda url, data, timeout: pings.append(url) or Answer())
    assert "first ping went through" in app_api.save_healthcheck(cfg, {"url": URL + "/"})["message"]
    assert f"HEALTHCHECK_URL={URL}\n" in env.read_text() and pings == [URL]
    assert "save-healthcheck" in app_api.STDIN_ACTIONS                                 # never on the command line
