"""
config.py: loads your settings.

  config.yaml  normal settings (safe to share)
  .env         secrets (Alpaca, Schwab and Webull keys), never shared or committed
  my_settings.json  the settings you change in the app (kept across updates; see user_settings.py)
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
        "alpaca_paper_key": os.environ.get("ALPACA_PAPER_API_KEY", ""),
        "alpaca_paper_secret": os.environ.get("ALPACA_PAPER_SECRET_KEY", ""),
        "alpaca_live_key": os.environ.get("ALPACA_LIVE_API_KEY", ""),
        "alpaca_live_secret": os.environ.get("ALPACA_LIVE_SECRET_KEY", ""),
        "app_key": os.environ.get("SCHWAB_APP_KEY", ""),
        "app_secret": os.environ.get("SCHWAB_APP_SECRET", ""),
        "callback_url": os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        "account_number": os.environ.get("SCHWAB_ACCOUNT_NUMBER", ""),
        "webull_app_key": os.environ.get("WEBULL_APP_KEY", ""),          # Webull (webull_api.py, brokers/webull_broker.py)
        "webull_app_secret": os.environ.get("WEBULL_APP_SECRET", ""),
        "webull_account_id": os.environ.get("WEBULL_ACCOUNT_ID", ""),
        "webull_env": os.environ.get("WEBULL_ENVIRONMENT", ""),          # paper (Webull's test server) or live
        "telegram_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),      # phone alerts (phone.py)
        "telegram_chat": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "pushover_user": os.environ.get("PUSHOVER_USER_KEY", ""),        # push alerts (pushover.py)
        "pushover_token": os.environ.get("PUSHOVER_APP_TOKEN", ""),
        "fred_key": os.environ.get("FRED_API_KEY", ""),                 # big economic news dates (macro.py)
        "sec_email": os.environ.get("SEC_CONTACT_EMAIL", ""),           # SEC filings: who's asking (sec_filings.py)
        "healthcheck_url": os.environ.get("HEALTHCHECK_URL", ""),       # the dead-man's switch (uptime.py)
    }
    cfg["live_trading_enabled"] = os.environ.get("LIVE_TRADING_ENABLED", "").strip().lower() == "true"
    cfg.setdefault("data_dir", str(DATA_DIR))
    cfg.setdefault("broker", "alpaca")
    from .user_settings import apply                    # your choices from the app (my_settings.json)
    apply(cfg)
    check_config(cfg)
    return cfg


def data_source(cfg: dict) -> str:
    """Where prices come from. "auto" = Alpaca if its keys are set, otherwise free Yahoo data."""
    source = cfg["data"]["source"]
    if source != "auto":
        return source
    s = cfg["secrets"]
    has_alpaca = (s["alpaca_paper_key"] and s["alpaca_paper_secret"]) or (s["alpaca_live_key"] and s["alpaca_live_secret"])
    return "alpaca" if has_alpaca else "yfinance"


def paper_broker(cfg: dict) -> str:
    """Where paper trading happens: "alpaca" (Alpaca's paper account), "webull" (Webull's paper/test
    environment) or "local" (simulated on this Mac). Setting paper.broker: auto (the old rule: Alpaca's
    paper account when Alpaca is the broker and its paper keys are saved), alpaca, webull or local.
    A broker is only used when its (paper) keys are saved; otherwise it's simulated here."""
    s = cfg["secrets"]
    choice = str(cfg["paper"].get("broker") or "auto").lower()
    alpaca = bool(s["alpaca_paper_key"] and s["alpaca_paper_secret"])
    webull = bool(s.get("webull_app_key") and s.get("webull_app_secret")) and \
        str(s.get("webull_env") or "").lower() == "paper"
    if choice == "webull":
        return "webull" if webull else "local"
    if choice == "alpaca":
        return "alpaca" if alpaca else "local"
    if choice == "local":
        return "local"
    return "alpaca" if (cfg["broker"] == "alpaca" and cfg["paper"].get("use_broker_paper", True) and alpaca) else "local"


def fractional_allowed(cfg: dict, live: bool = False) -> bool:
    """Fractional shares (parts of a share), where the orders go can do them: Alpaca and the simulation
    on this Mac can; Schwab's API can't, and Webull's isn't confirmed yet, so those buy whole shares.
    Real money follows the real-money broker; paper (and practice in its head) follow the paper account.
    Setting fractional.enabled: off = whole shares everywhere."""
    setting = str((cfg.get("fractional") or {}).get("enabled", True)).strip().lower()
    if setting in ("off", "false", "no", "0"):
        return False
    return (cfg.get("broker", "alpaca") if live else paper_broker(cfg)) in ("alpaca", "local")


def uses_broker_paper(cfg: dict) -> bool:
    """Paper trade inside a broker's paper account (real order handling) instead of simulating it here."""
    return paper_broker(cfg) != "local"


def check_config(cfg: dict):
    """Catch setting mistakes early, with a plain-English message."""
    seen = {}
    for desk in DESKS:
        for ticker in cfg["desks"][desk]["watchlist"]:
            if not isinstance(ticker, str):              # YAML reads ON/OFF/YES/NO/Y/N as true/false
                raise ValueError(f"The {desk} watchlist has {ticker!r}, not a ticker. Put tickers that are also "
                                 f'yes/no words in quotes, like "ON".')
            if ticker in seen:
                raise ValueError(f"{ticker} is on both the {seen[ticker]} and {desk} watchlists; pick one.")
            seen[ticker] = desk
    if sum(cfg["desks"][d]["budget_pct"] for d in DESKS) > 100:
        raise ValueError("desks budget_pct add up to more than 100%.")
    if cfg.get("broker", "alpaca") not in ("alpaca", "schwab", "webull"):
        raise ValueError("broker must be alpaca, schwab or webull.")


def is_cash_account(cfg: dict) -> bool:
    """Cash-account rules (only settled money is spent: no good faith violations). "auto": Schwab = cash
    (the safe assumption: in a margin account these rules only cost a day's wait), Alpaca = margin (Alpaca
    lends the unsettled money itself, so there are no good faith violations there). Webull = cash too
    (the safe assumption until you set the account type)."""
    kind = cfg["live"].get("account_type", "auto")
    return kind == "cash" or (kind == "auto" and cfg.get("broker", "alpaca") in ("schwab", "webull"))


def active_desks(cfg: dict) -> list:
    return [d for d in DESKS if cfg["desks"][d].get("enabled", True)]


def desk_capital(cfg: dict, desk: str, live: bool) -> float:
    """How much money this desk gets (paper or live)."""
    total = cfg["live"]["max_capital"] if live else cfg["paper"]["starting_cash"]
    return total * cfg["desks"][desk]["budget_pct"] / 100


def cents_per_share(cfg: dict, desk: str) -> float:
    """Extra cost per share on each simulated fill (config.yaml desks.<desk>.cents_per_share): day trades pay
    the spread and some slippage on every trade, which a percentage alone understates for cheap stocks."""
    return float(((cfg.get("desks") or {}).get(desk) or {}).get("cents_per_share") or 0)


def data_path(cfg: dict, name: str) -> Path:
    """Path to a file inside the data/ folder (created if missing)."""
    path = Path(cfg["data_dir"]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
