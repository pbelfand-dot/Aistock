"""
alpaca_api.py: connecting to Alpaca.

Alpaca gives you TWO sets of keys (https://app.alpaca.markets):
  * PAPER keys: a practice account with fake money but real order handling.
    The bot's PAPER phase trades here.
  * LIVE keys: your real-money account. Only used once a desk earns LIVE.
Market data works with either set (the free plan's real-time feed is "iex").
"""


TIMEOUT = (10, 60)          # seconds to connect, seconds to wait for each part of the answer


def timed(client):
    """alpaca-py waits FOREVER for an answer (its requests have no time limit, and the autopilot's default
    socket timeout doesn't reach them). After a dropped connection (Wi-Fi, the Mac sleeping) a call could
    then never return, freezing the scan or a check-in. Every request gets a time limit instead, so it
    fails and is tried again."""
    session = getattr(client, "_session", None)
    if session is not None and not getattr(session, "kestrel_timeout", False):
        plain = session.request

        def request(method, url, **kwargs):
            kwargs.setdefault("timeout", TIMEOUT)
            return plain(method, url, **kwargs)
        session.request, session.kestrel_timeout = request, True
    return client


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
    return timed(TradingClient(key, secret, paper=paper))


def data_client(cfg: dict):
    from alpaca.data.historical import StockHistoricalDataClient
    for paper in (True, False):                       # any valid key pair works for market data
        if has_keys(cfg, paper):
            return timed(StockHistoricalDataClient(*keys(cfg, paper)))
    raise RuntimeError("Missing Alpaca keys in .env (needed for Alpaca market data)")
