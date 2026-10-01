"""
user_settings.py: the few settings you change from the app. They survive updates.

config.yaml holds the defaults and is replaced by every app update. Your own choices live in
my_settings.json next to it (in ~/AITrader) and are applied on top when the bot starts.
"""
import json
import os

from .config import ROOT

# name: (where it goes in config.yaml, what's allowed, plain-English label)
SETTINGS = {
    "broker": (("broker",), ("alpaca", "schwab", "webull"), "Broker for real money"),
    "paper_broker": (("paper", "broker"), ("auto", "alpaca", "webull", "local"), "Where paper trading happens"),
    "fractional": (("fractional", "enabled"), ("on", "off"), "Fractional shares (where the broker allows)"),
    "real_money_cap": (("live", "max_capital"), (10, 100000), "Most real money the bot may use ($)"),
    "account_type": (("live", "account_type"), ("auto", "cash", "margin"), "Account type"),
    "paper_cash": (("paper", "starting_cash"), (100, 1000000), "Paper (practice) money ($)"),
    "scan_all_stocks": (("scanner", "enabled"), ("on", "off"), "Scan all US stocks every day"),
    "read_news": (("news", "enabled"), ("on", "off"), "Let Kestrel read the news"),
    "phone_screen": (("phone", "screen"), ("on", "off"), "Kestrel screen on your phone (Tailscale)"),
    "lid_closed": (("mac", "lid_closed"), ("on", "off"), "Keep trading with the lid closed (plugged in)"),
}


def settings_file():
    return ROOT / "my_settings.json"


def load() -> dict:
    path = settings_file()
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def apply(cfg: dict) -> dict:
    """Your saved choices on top of config.yaml (anything invalid is ignored, never half-applied)."""
    for name, value in load().items():
        if name in SETTINGS:
            try:
                value = check(name, value)
            except ValueError:
                continue
            where = SETTINGS[name][0]
            target = cfg
            for key in where[:-1]:
                target = target.setdefault(key, {})
            target[where[-1]] = value
    return cfg


def check(name: str, value):
    where, allowed, label = SETTINGS[name]
    if isinstance(allowed[0], str):
        value = str(value).strip().lower()
        if value not in allowed:
            raise ValueError(f"{label}: pick one of {', '.join(allowed)}.")
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: type a number.") from None
    low, high = allowed
    if not low <= number <= high:
        raise ValueError(f"{label}: between ${low:,} and ${high:,}.")
    return round(number, 2)


def save(changes: dict) -> dict:
    """Checks every change first; saves all of them or none."""
    current = load()
    for name, value in changes.items():
        if name not in SETTINGS:
            raise ValueError(f"unknown setting {name!r}")
        current[name] = check(name, value)
    path = settings_file()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(current, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return current


def current(cfg: dict) -> dict:
    """What the bot is using now, for the Setup screen."""
    out = {}
    for name, (where, allowed, label) in SETTINGS.items():
        value = cfg
        for key in where:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, bool):
            value = "on" if value else "off"
        out[name] = value if value is not None else ("auto" if name == "account_type" else None)
    return out
