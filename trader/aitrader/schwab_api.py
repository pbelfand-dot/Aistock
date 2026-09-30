"""
schwab_api.py: logging in to Schwab and connecting.

Uses the open-source `schwab-py` library (https://github.com/alexgolec/schwab-py).
All Schwab-specific login code lives in this one file, so switching libraries
later (e.g. to `schwabdev`) only means changing this file and brokers/schwab.py.

THE 7-DAY LOGIN: Schwab's login ("refresh token") expires every 7 days, and
there's no way to extend it. About once a week you MUST run:
    python run.py schwab-login
If you forget, the bot can't trade (it fails safe; it does NOT trade blindly).
"""
import json
import os
import time

from .config import data_path

TOKEN_FILE = "schwab_token.json"
TOKEN_LIFETIME_DAYS = 7


def _check_secrets(cfg):
    s = cfg["secrets"]
    if not s["app_key"] or not s["app_secret"]:
        raise RuntimeError("Missing SCHWAB_APP_KEY / SCHWAB_APP_SECRET in .env")
    return s


def login(cfg, manual: bool = False):
    """Log in to Schwab and save a fresh 7-day token. Run about once a week.

    manual=False opens your browser automatically.
    manual=True  prints a link to paste into any browser (for computers with no screen)."""
    import schwab
    s = _check_secrets(cfg)
    token_path = data_path(cfg, TOKEN_FILE)
    new_path = data_path(cfg, "schwab_token.new.json")   # keep the old token until the new one works
    flow = schwab.auth.client_from_manual_flow if manual else schwab.auth.client_from_login_flow
    flow(s["app_key"], s["app_secret"], s["callback_url"], str(new_path))
    new_path.replace(token_path)
    print(f"Logged in. Token saved to {token_path}. It expires in {TOKEN_LIFETIME_DAYS} days.")


LOGIN_STATE = "schwab_login_pending.json"
LOGIN_WINDOW_MINUTES = 15


def login_start(cfg) -> str:
    """Step 1 of logging in from the app: the Schwab login page to open in your browser."""
    import schwab
    s = _check_secrets(cfg)
    ctx = schwab.auth.get_auth_context(s["app_key"], s["callback_url"])
    path = data_path(cfg, LOGIN_STATE)
    path.write_text(json.dumps({"callback_url": ctx.callback_url, "authorization_url": ctx.authorization_url,
                                "state": ctx.state, "started": time.time()}))
    os.chmod(path, 0o600)
    return ctx.authorization_url


def login_finish(cfg, received_url: str) -> float:
    """Step 2: after you log in, your browser lands on your callback address (the page itself won't load;
    that's expected). That full address carries a one-time code; this trades it for a 7-day login."""
    import schwab
    s = _check_secrets(cfg)
    path = data_path(cfg, LOGIN_STATE)
    if not path.exists():
        raise RuntimeError("Press 'Open Schwab login' first.")
    saved = json.loads(path.read_text())
    if time.time() - saved["started"] > LOGIN_WINDOW_MINUTES * 60:
        path.unlink()
        raise RuntimeError("That login took too long. Press 'Open Schwab login' again.")
    received_url = received_url.strip()
    if not received_url.startswith(saved["callback_url"]) or "code=" not in received_url:
        raise ValueError(f"Paste the whole address from your browser's address bar after logging in: it starts "
                         f"with {saved['callback_url']} and contains code=.")
    ctx = schwab.auth.AuthContext(saved["callback_url"], saved["authorization_url"], saved["state"])
    token_path, new_path = data_path(cfg, TOKEN_FILE), data_path(cfg, "schwab_token.new.json")

    def write(token, *args, **kwargs):
        new_path.write_text(json.dumps(token))
        os.chmod(new_path, 0o600)

    schwab.auth.client_from_received_url(s["app_key"], s["app_secret"], ctx, received_url, write)
    new_path.replace(token_path)                              # the old login stays until the new one works
    path.unlink()
    return token_days_left(cfg)


def get_client(cfg):
    """Connects using the saved token. Never opens a browser (safe for schedules)."""
    import schwab
    s = _check_secrets(cfg)
    token_path = data_path(cfg, TOKEN_FILE)
    if not token_path.exists():
        raise RuntimeError("Not logged in to Schwab. Run: python run.py schwab-login")
    days_left = token_days_left(cfg)
    if days_left is not None and days_left <= 0:
        raise RuntimeError("Schwab login expired (7-day limit). Run: python run.py schwab-login")
    return schwab.auth.client_from_token_file(str(token_path), s["app_key"], s["app_secret"])


def token_days_left(cfg):
    """Days until the weekly Schwab login expires (None if never logged in)."""
    token_path = data_path(cfg, TOKEN_FILE)
    if not token_path.exists():
        return None
    created = json.loads(token_path.read_text()).get("creation_timestamp", 0)
    return TOKEN_LIFETIME_DAYS - (time.time() - created) / 86400


def account_hash(client, account_number: str) -> str:
    """Schwab's API uses a scrambled 'hash' instead of your account number."""
    resp = client.get_account_numbers()
    resp.raise_for_status()
    accounts = resp.json()
    if account_number:
        for a in accounts:
            if a["accountNumber"] == account_number:
                return a["hashValue"]
        raise RuntimeError(f"Account {account_number} not found in this Schwab login")
    if len(accounts) != 1:
        raise RuntimeError("You have several accounts; set SCHWAB_ACCOUNT_NUMBER in .env")
    return accounts[0]["hashValue"]
