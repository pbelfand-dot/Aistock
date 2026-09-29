"""
alpaca_api.py: connecting to Alpaca.

Alpaca gives you TWO sets of keys (https://app.alpaca.markets):
  * PAPER keys: a practice account with fake money but real order handling.
    The bot's PAPER phase trades here.
  * LIVE keys: your real-money account. Only used once a desk earns LIVE.
Market data works with either set (the free plan's real-time feed is "iex").
"""


def keys(cfg: dict, paper: bool):
    s = cfg["secrets"]
    return (s["alpaca_paper_key"], s["alpaca_paper_secret"]) if paper else (s["alpaca_live_key"], s["alpaca_live_secret"])


def has_keys(cfg: dict, paper: bool) -> bool:
    return all(keys(cfg, paper))


def trading_client(cfg: dict, paper: bool):
    from alpaca.trading.client import TradingClient
    key, secret = keys(cfg, paper)
    if not key or not secret:
        which = "PAPER" if paper else "LIVE"
        raise RuntimeError(f"Missing ALPACA_{which}_API_KEY / ALPACA_{which}_SECRET_KEY in .env")
    return TradingClient(key, secret, paper=paper)


def data_client(cfg: dict):
    from alpaca.data.historical import StockHistoricalDataClient
    for paper in (True, False):                       # any valid key pair works for market data
        if has_keys(cfg, paper):
            return StockHistoricalDataClient(*keys(cfg, paper))
    raise RuntimeError("Missing Alpaca keys in .env (needed for Alpaca market data)")
