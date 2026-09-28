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
DATA_DIR = ROOT / "data"                        # database, price cache, plan, Schwab token


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
    return cfg


def data_path(cfg: dict, name: str) -> Path:
    """Path to a file inside the data/ folder (created if missing)."""
    folder = Path(cfg["data_dir"])
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
