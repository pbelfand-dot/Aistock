"""Webull: saving the keys, the in-app approval, and a read-only connection test (it never trades)."""
from datetime import datetime, timezone

import pytest

import run
from aitrader import app_api, webull_api
from aitrader.storage import Store

NOW = datetime(2026, 9, 30, 15, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("path,query,body,expected", [
    ("/trading/accounts/list", {}, None, "Y8HKicmTjWEqRUzFQayR1EP/OAVwJ2MufxNR6DoPvT4="),
    ("/trading/assets/balances/get", {"account_id": "ABC123"}, None, "TedsIa6qZmSsOI+xRpiXbC7MlAetxrok1frImGGIPzc="),
    ("/auth/tokens/create", {}, {}, "DQL9BUpREhB/Ys7KkHvLAE7u/ZL1UDJyvSZvVkzypcQ="),
    ("/auth/tokens/check", {}, {"token": "tok-1/2+x"}, "/RLexeCm3S8osmkvPAn3+NFSuk3cPnEF0CJ/O83D8U4="),
])
def test_requests_are_signed_exactly_like_webulls_own_sdk(path, query, body, expected):
    # The expected values came from webull-openapi-python-sdk 3.0.2's own signer, same inputs.
    h = webull_api.signed_headers("myappkey123", "mysecret456", path, query, body, now=NOW, nonce="nonce-1")
    assert h["x-signature"] == expected
    assert h["x-timestamp"] == "2026-09-30T15:00:00Z" and h["x-signature-algorithm"] == "HMAC-SHA256"


class FakeWebull:
    """Webull's side: the token goes PENDING -> (you approve in the app) -> NORMAL."""
    def __init__(self, token_check=True):
        self.token_check, self.status, self.calls = token_check, None, []

    def __call__(self, cfg, method, path, query=None, body=None, token=None, wait=20):
        self.calls.append(path)
        if path == "/openapi/config":
            return {"token_check_enabled": self.token_check}
        if path == "/auth/tokens/create":
            self.status = "PENDING"
            return {"token": "tok-1", "expires": 1, "status": "PENDING"}
        if path == "/auth/tokens/check":
            return {"token": body["token"], "expires": 1, "status": self.status}
        assert path.startswith("/trading/") and method == "GET"           # read-only: never an order
        assert token == ("tok-1" if self.token_check else None)
        if path == "/trading/accounts/list":
            return [{"account_id": "ID-A", "account_number": "5MX01234", "account_type": "CASH"},
                    {"account_id": "ID-B", "account_number": "5MX09999", "account_type": "MARGIN"}]
        return {"account_currency_assets": [{"currency": "USD", "cash_balance": "51.25"}]}


def test_webull_keys_are_saved_privately_then_you_approve_kestrel_in_the_webull_app(cfg, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("LIVE_TRADING_ENABLED=false\n")
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    monkeypatch.setattr(app_api, "restart_autopilot", lambda: False)
    webull = FakeWebull()
    monkeypatch.setattr(webull_api, "call", webull)

    with pytest.raises(ValueError, match="App Key"):
        app_api.handle("save-webull-keys", cfg, payload={"app_key": "bad key!", "app_secret": "s" * 32})
    with pytest.raises(ValueError, match="account ID"):
        app_api.handle("save-webull-keys", cfg, payload={"app_key": "k" * 32, "app_secret": "s" * 32,
                                                         "account_id": "12\nLIVE_TRADING_ENABLED=true"})
    assert app_api.handle("check-webull", cfg, payload={})["text"] == "Webull: no keys yet."

    msg = app_api.handle("save-webull-keys", cfg, payload={"app_key": " " + "k" * 32, "app_secret": "s" * 32})
    assert "approve Kestrel in the Webull app" in msg["message"]
    text = env.read_text()
    assert f"WEBULL_APP_KEY={'k' * 32}\n" in text and f"WEBULL_APP_SECRET={'s' * 32}\n" in text
    assert "LIVE_TRADING_ENABLED=false" in text and env.stat().st_mode & 0o777 == 0o600

    first = app_api.handle("check-webull", cfg, payload={})              # Test Webull: asks for an approval
    assert first["waiting"] and not first["ok"] and "OpenAPI Notifications" in first["text"]
    token_file = tmp_path / "webull_token.json"
    assert token_file.stat().st_mode & 0o777 == 0o600
    store = Store(tmp_path / "aitrader.sqlite")
    assert app_api.setup_status(cfg, store)["webull"] == {"keys": True, "account_id": False, "approval": "PENDING"}

    creates = webull.calls.count("/auth/tokens/create")
    assert app_api.handle("check-webull", cfg, payload={"poll": True})["waiting"]      # still waiting
    webull.status = "NORMAL"                                             # you approved it in the Webull app
    done = app_api.handle("check-webull", cfg, payload={"poll": True})
    assert done["ok"] and "connected (read-only)" in done["text"] and "...1234 (CASH)" in done["text"]
    assert "cash $51.25" in done["text"] and "2 accounts" in done["text"]
    assert webull.calls.count("/auth/tokens/create") == creates           # polling never asked for a new approval
    assert app_api.setup_status(cfg, store)["webull"]["approval"] == "NORMAL"

    cfg["secrets"]["webull_account_id"] = "5MX09999"                      # the account you picked
    assert "...9999 (MARGIN)" in webull_api.connect(cfg)["text"]
    cfg["secrets"]["webull_account_id"] = "nope"
    assert "isn't one of this key's accounts (...1234, ...9999)" in webull_api.connect(cfg)["text"]

    app_api.handle("save-webull-keys", cfg, payload={"app_key": "n" * 32, "app_secret": "s" * 32})
    assert not token_file.exists()                                       # a new key needs a new approval


def test_an_approval_that_times_out_is_not_renewed_by_itself(cfg, monkeypatch):
    cfg["secrets"].update(webull_app_key="k" * 32, webull_app_secret="s" * 32)
    webull = FakeWebull()
    monkeypatch.setattr(webull_api, "call", webull)
    assert webull_api.connect(cfg)["waiting"]
    webull.status = "EXPIRED"                                             # not approved within 5 minutes
    late = app_api.handle("check-webull", cfg, payload={"poll": True})
    assert not late["waiting"] and "timed out" in late["text"]
    assert webull.calls.count("/auth/tokens/create") == 1
    assert webull_api.connect(cfg)["waiting"]                             # pressing Test Webull asks again
    assert webull.calls.count("/auth/tokens/create") == 2


def test_the_autopilot_keeps_an_approved_webull_login_alive_but_never_asks_for_a_new_one(cfg, tmp_path, monkeypatch):
    cfg["secrets"].update(webull_app_key="k" * 32, webull_app_secret="s" * 32)
    webull = FakeWebull()
    monkeypatch.setattr(webull_api, "call", webull)
    assert webull_api.keep_alive(cfg) == "" and webull.calls == []        # nothing approved yet: leaves Webull alone
    webull_api.connect(cfg)
    webull.status = "NORMAL"
    webull_api.connect(cfg)
    webull.calls.clear()
    assert webull_api.keep_alive(cfg) == "" and "/trading/accounts/list" in webull.calls   # used: won't lapse
    webull.status = "INVALID"                                             # went unused for 15 days anyway
    assert "Test Webull" in webull_api.keep_alive(cfg) and "/auth/tokens/create" not in webull.calls

    def offline(*a, **k):
        raise webull_api.WebullError("couldn't reach Webull")
    monkeypatch.setattr(webull_api, "call", offline)
    webull_api.save_token(cfg, {"token": "tok-1", "status": "NORMAL"})
    store = Store(tmp_path / "aitrader.sqlite")
    monkeypatch.setattr(run, "first_scan", lambda *a: None)
    run.run_job("morning", cfg, store, None, datetime(2026, 9, 30, 9, 0), set())      # the day still starts
    assert any("WARNING: Webull: couldn't check" in m for _, m in store.journal(5))
    assert webull_api.load_token(cfg)["status"] == "NORMAL"               # offline doesn't forget the approval


def test_no_token_needed_when_webull_says_so(cfg, monkeypatch):
    cfg["secrets"].update(webull_app_key="k" * 32, webull_app_secret="s" * 32)
    webull = FakeWebull(token_check=False)
    monkeypatch.setattr(webull_api, "call", webull)
    assert webull_api.connect(cfg)["ok"] and "/auth/tokens/create" not in webull.calls
