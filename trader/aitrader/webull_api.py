"""
webull_api.py: connecting to Webull (keys, the in-app approval, a read-only connection test, and the
signed requests). Orders are placed by brokers/webull_broker.py, with the same safety rules as Alpaca and
Schwab; nothing in this file places, changes or cancels an order.

Webull's OpenAPI needs three things:
  App Key + App Secret  from the Webull website after Webull approves your API application
                        (API Management -> My Application; review takes about 1-2 business days).
  An access token       Kestrel asks Webull for one; you approve it ONCE in the Webull app with a
                        text-message code, within 5 minutes (Menu -> Messages -> OpenAPI Notifications
                        -> Check Now). It stays good as long as it's used at least every 15 days, so the
                        autopilot uses it once each morning.

Paper vs real money: Webull's test ("paper") keys only work on its test server (api.sandbox.webull.com),
and real-money keys only on api.webull.com. WEBULL_ENVIRONMENT says which (paper / live); if the keys
belong to the other one, the connection test finds out and switches.

Every request is signed with the App Secret (HMAC-SHA256) exactly the way Webull's own Python SDK
(webull-openapi-python-sdk) signs it, so Kestrel doesn't need that package and its many dependencies.
"""
import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from .config import data_path

HOSTS = {"live": "api.webull.com",                  # Webull US, real money
         "paper": "api.sandbox.webull.com"}         # Webull US test environment ("paper")
NAMES = {"live": "real money", "paper": "paper"}
TOKEN_FILE = "webull_token.json"
APPROVE = ("Approve Kestrel in the Webull app within 5 minutes: open Webull on your phone → Menu → Messages → "
           "OpenAPI Notifications → tap the newest message → Check Now → enter the text-message code. "
           "Then press Test Webull again.")
CASH_FIELDS = ("total_cash_balance", "cash_balance", "settled_cash", "total_cash", "cash")


class WebullError(RuntimeError):
    def __init__(self, text: str, status: int = None):
        super().__init__(text)
        self.status = status

    @property
    def keys_refused(self) -> bool:
        """Webull didn't accept these keys (as opposed to being offline, or another problem)."""
        text = str(self).lower()
        return self.status in (401, 403) or any(w in text for w in ("credential", "app key", "appkey", "app_key"))


def has_keys(cfg) -> bool:
    s = cfg["secrets"]
    return bool(s.get("webull_app_key") and s.get("webull_app_secret"))


def environment(cfg) -> str:
    env = str(cfg["secrets"].get("webull_env") or "").strip().lower()
    return env if env in HOSTS else "live"


def signed_headers(app_key: str, app_secret: str, path: str, query: dict = None, body: dict = None,
                   host: str = HOSTS["live"], now: datetime = None, nonce: str = None) -> dict:
    """The x-* headers Webull checks: the same string-to-sign and HMAC-SHA256 as Webull's SDK."""
    headers = {"x-app-key": app_key,
               "x-timestamp": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "x-signature-version": "1.0",
               "x-signature-algorithm": "HMAC-SHA256",
               "x-signature-nonce": nonce or str(uuid.uuid4())}
    params = {k.lower(): v for k, v in headers.items()}
    params["host"] = host
    for k, v in (query or {}).items():
        params[k] = f"{params[k]}&{v}" if k in params else str(v)
    text = path + "&" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    if body is not None:
        text += "&" + hashlib.sha256(_compact(body).encode()).hexdigest().upper()
    digest = hmac.new((app_secret + "&").encode(), quote(text, safe="").encode(), hashlib.sha256).digest()
    headers["x-signature"] = base64.b64encode(digest).decode()
    return headers


def _compact(body: dict) -> str:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def call(cfg, method: str, path: str, query: dict = None, body: dict = None, token: str = None, wait: float = 20,
         env: str = None, headers: dict = None):
    """One signed request to Webull; the answer as JSON. Raises WebullError with Webull's own message."""
    s = cfg["secrets"]
    host = HOSTS[env or environment(cfg)]
    extra = dict(headers or {})                         # e.g. Webull's "category" header on orders (not signed)
    headers = signed_headers(s["webull_app_key"], s["webull_app_secret"], path, query, body, host=host)
    headers.update({"x-version": "v3", "x-webull-client-source": "sdk", "Accept": "application/json",
                    "User-Agent": "Kestrel (python)"})
    data = None
    if body is not None:
        data = _compact(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["x-access-token"] = token
    headers.update(extra)
    url = f"https://{host}{path}" + (f"?{urlencode(query)}" if query else "")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=wait) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        try:
            info = json.loads(e.read() or b"{}")
        except ValueError:
            info = {}
        why = info.get("message") or info.get("error_code") or e.reason
        raise WebullError(f"{why} (HTTP {e.code})", e.code) from None
    except urllib.error.URLError as e:
        raise WebullError(f"couldn't reach Webull ({e.reason}). Is the Mac online?") from None
    return json.loads(raw) if raw else {}


# ---------------------------------------------------------------- the access token (owner-only file in data/)
def load_token(cfg) -> dict:
    """The saved approval for the current environment (a paper approval doesn't count for real money)."""
    path = data_path(cfg, TOKEN_FILE)
    try:
        saved = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}
    return saved if saved.get("env", "live") == environment(cfg) else {}


def save_token(cfg, state: dict):
    path = data_path(cfg, TOKEN_FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({**{k: state.get(k) for k in ("token", "expires", "status")}, "env": environment(cfg)}))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def forget_token(cfg):
    data_path(cfg, TOKEN_FILE).unlink(missing_ok=True)


def token_state(cfg, create: bool = True) -> dict:
    """{"token", "status"}: NORMAL = approved, PENDING = waiting for you in the Webull app.
    Asks Webull for a new token (a new approval) only when there's none, or it expired / went unused 15 days,
    and only when create=True (you pressed Test Webull)."""
    if not call(cfg, "GET", "/openapi/config").get("token_check_enabled", False):
        return {"token": None, "status": "NORMAL"}     # this app key doesn't use tokens
    saved = load_token(cfg)
    state = None
    if saved.get("token"):
        try:
            state = call(cfg, "POST", "/auth/tokens/check", body={"token": saved["token"]})
        except WebullError:
            if not create:                             # e.g. offline: keep what's saved, try again later
                raise
    if not create and not state:
        return {"token": None, "status": None}
    if create and (not state or state.get("status") in ("INVALID", "EXPIRED")):
        state = call(cfg, "POST", "/auth/tokens/create", body={})
    state = {**state, "token": state.get("token") or saved.get("token")}
    save_token(cfg, state)
    return state


# ---------------------------------------------------------------- reading the account
def _items(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "accounts", "items", "list", "subscriptions"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _find_number(data, names):
    """The first of these fields found anywhere in Webull's answer (it nests them differently by account)."""
    if isinstance(data, dict):
        for name in names:
            try:
                if data.get(name) not in (None, ""):
                    return float(data[name])
            except (TypeError, ValueError):
                pass
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            found = _find_number(item, names)
            if found is not None:
                return found
    return None


def accounts(cfg, token) -> list:
    return [a for a in _items(call(cfg, "GET", "/trading/accounts/list", token=token))
            if isinstance(a, dict) and a.get("account_id")]


def pick_account(cfg, found: list) -> dict:
    wanted = str(cfg["secrets"].get("webull_account_id") or "").strip()
    if not found:
        raise WebullError("no accounts came back. Check that your API application is approved for this account.")
    if not wanted:
        return found[0]
    for a in found:
        if wanted in (str(a.get("account_id")), str(a.get("account_number"))):
            return a
    names = ", ".join("..." + str(a.get("account_number") or a["account_id"])[-4:] for a in found)
    raise WebullError(f"account {wanted} isn't one of this key's accounts ({names}). Fix or clear the account number.")


def use_environment(cfg, env: str):
    """Remembers paper / live in .env (the keys belong to that server)."""
    from .app_api import env_file, write_env
    write_env(env_file(), {"WEBULL_ENVIRONMENT": env})
    os.environ["WEBULL_ENVIRONMENT"] = env
    cfg["secrets"]["webull_env"] = env


def connect(cfg) -> dict:
    """The read-only connection test: {"ok", "waiting", "text"} (+ "switched_to"). Never trades.
    If Webull refuses the keys, tries its other server once: paper keys pasted as real money (or the
    reverse) then just work, and Kestrel remembers which they are."""
    if not has_keys(cfg):
        return {"ok": False, "waiting": False, "text": "Webull: no keys yet."}
    first = environment(cfg)
    try:
        call(cfg, "GET", "/openapi/config")             # does this server know these keys?
        return _connect(cfg)
    except WebullError as e:
        if not e.keys_refused:
            return {"ok": False, "waiting": False, "text": f"Webull ({NAMES[first]}): {e}"}
        refused = e
    other = "paper" if first == "live" else "live"
    try:
        call(cfg, "GET", "/openapi/config", env=other)
    except WebullError:
        return {"ok": False, "waiting": False, "text": (
            f"Webull said: {refused}. Its paper and real-money servers both refused these keys. Check that "
            "(1) the App Key and App Secret aren't swapped and were copied whole, (2) Webull approved your API "
            "application, and (3) they're the newest pair: generating keys again replaces the old ones.")}
    use_environment(cfg, other)
    result = _connect(cfg)
    result["switched_to"] = other
    result["text"] = f"These are {NAMES[other]} keys, so Kestrel uses Webull's {NAMES[other]} server. " + result["text"]
    return result


def _connect(cfg) -> dict:
    name = NAMES[environment(cfg)]
    try:
        state = token_state(cfg)
        if state.get("status") != "NORMAL":
            return {"ok": False, "waiting": True, "text": f"Webull ({name}): keys accepted. " + APPROVE}
        found = accounts(cfg, state["token"])
        account = pick_account(cfg, found)
        label = "..." + str(account.get("account_number") or account["account_id"])[-4:]
        kind = " ".join(str(account.get(k)) for k in ("account_type", "account_class") if account.get(k))
        cash = None
        try:
            cash = _find_number(call(cfg, "GET", "/trading/assets/balances/get",
                                     query={"account_id": account["account_id"]}, token=state["token"]), CASH_FIELDS)
        except WebullError:
            pass
        return {"ok": True, "waiting": False,
                "text": f"Webull ({name}): connected (read-only). Account {label}" + (f" ({kind})" if kind else "")
                        + (f", cash ${cash:,.2f}" if cash is not None else "")
                        + (f"; {len(found)} accounts on this key" if len(found) > 1 else "")
                        + ". " + trading_note(cfg)}
    except WebullError as e:
        return {"ok": False, "waiting": False, "text": f"Webull ({name}): {e}"}


def trading_note(cfg) -> str:
    """Whether Kestrel trades here, in one sentence."""
    from .config import paper_broker
    if environment(cfg) == "paper":
        return ("Paper trading happens here." if paper_broker(cfg) == "webull" else
                "To paper trade here: Settings -> Paper trading happens at: Webull.")
    return ("Real money goes here once a desk passes paper and you confirm it." if cfg["broker"] == "webull" else
            "For real money here: Settings -> Broker for real money: Webull.")


def keep_alive(cfg) -> str:
    """Once a morning (autopilot): uses the approved token so it doesn't lapse after 15 idle days.
    Never asks for a new approval by itself (that needs you); says so instead."""
    if not has_keys(cfg) or load_token(cfg).get("status") != "NORMAL":
        return ""
    try:
        state = token_state(cfg, create=False)
        if state.get("status") != "NORMAL":
            return "Webull: the app login lapsed. Open Setup → Test Webull and approve it in the Webull app."
        accounts(cfg, state["token"])
        return ""
    except WebullError as e:
        return f"Webull: couldn't check the connection ({e})."
