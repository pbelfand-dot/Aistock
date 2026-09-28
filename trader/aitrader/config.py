"""
config.py: loads your settings.

  config.yaml  normal settings (safe to share)
  .env         secrets (Schwab keys), never shared or committed
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent   # the trader/ folder
DATA_DIR = ROOT / "data"                        # database, price cache, plans, Schwab token
DESKS = ("swing", "day")


def load_config(path=None) -> dict:
    load_dotenv(ROOT / ".env")
    path = Path(path or os.environ.get("AITRADER_CONFIG", ROOT / "config.yaml"))
    with open(path) as f:
        cfg = yaml.safe_load(f)

    cfg["secrets"] = {
        "app_key": os.environ.get("SCHWAB_APP_KEY", ""),
        "app_secret": os.environ.get("SCHWAB_APP_SECRET", ""),
        "callback_url": os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        "account_number": os.environ.get("SCHWAB_ACCOUNT_NUMBER", ""),
    }
    cfg["live_trading_enabled"] = os.environ.get("LIVE_TRADING_ENABLED", "").strip().lower() == "true"
    cfg.setdefault("data_dir", str(DATA_DIR))
    check_config(cfg)
    return cfg


def check_config(cfg: dict):
    """Catch setting mistakes early, with a plain-English message."""
    seen = {}
    for desk in DESKS:
        for ticker in cfg["desks"][desk]["watchlist"]:
            if ticker in seen:
                raise ValueError(f"{ticker} is on both the {seen[ticker]} and {desk} watchlists; pick one.")
            seen[ticker] = desk
    if sum(cfg["desks"][d]["budget_pct"] for d in DESKS) > 100:
        raise ValueError("desks budget_pct add up to more than 100%.")


def active_desks(cfg: dict) -> list:
    return [d for d in DESKS if cfg["desks"][d].get("enabled", True)]


def desk_capital(cfg: dict, desk: str, live: bool) -> float:
    """How much money this desk gets (paper or live)."""
    total = cfg["live"]["max_capital"] if live else cfg["paper"]["starting_cash"]
    return total * cfg["desks"][desk]["budget_pct"] / 100


def data_path(cfg: dict, name: str) -> Path:
    """Path to a file inside the data/ folder (created if missing)."""
    path = Path(cfg["data_dir"]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
