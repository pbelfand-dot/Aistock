"""
market_data.py: gets daily prices.

Two sources, same output:
  yfinance  free Yahoo data, needs no account (start studying TODAY)
  schwab    Schwab's own data, once your developer app is approved

Output: {ticker: DataFrame[open, high, low, close, volume]} indexed by date.
During market hours the last row is TODAY, and its "close" is the current price.
"""
import time
from datetime import datetime, timedelta

import pandas as pd

from .config import data_path

COLUMNS = ["open", "high", "low", "close", "volume"]


class MarketData:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.source = cfg["data"]["source"]
        self.years = cfg["data"]["history_years"]
        self.cache_minutes = cfg["data"]["cache_minutes"]
        self._schwab = None

    def load(self):
        """Returns (bars for the watchlist, bars for the benchmark)."""
        tickers = list(dict.fromkeys(self.cfg["watchlist"] + [self.cfg["benchmark"]]))
        bars = {}
        for t in tickers:
            try:
                bars[t] = self.history(t)
            except Exception as e:           # one bad ticker shouldn't stop the day
                print(f"  ! could not load {t}: {e}")
        if self.cfg["benchmark"] not in bars:
            raise RuntimeError("Could not load the benchmark; check your internet/data source.")
        if self.source == "schwab":
            self._add_todays_bar(bars)
        market = bars[self.cfg["benchmark"]]
        watch = {t: bars[t] for t in self.cfg["watchlist"] if t in bars}
        return watch, market

    def history(self, ticker: str) -> pd.DataFrame:
        cache = data_path(self.cfg, f"cache/{ticker}.csv")
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists() and time.time() - cache.stat().st_mtime < self.cache_minutes * 60:
            return pd.read_csv(cache, index_col=0, parse_dates=True)

        df = self._from_schwab(ticker) if self.source == "schwab" else self._from_yahoo(ticker)
        df = df[COLUMNS].dropna(subset=["close"]).sort_index()
        df.to_csv(cache)
        return df

    def _from_yahoo(self, ticker: str) -> pd.DataFrame:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=f"{self.years}y", auto_adjust=True)
        if df.empty:
            raise RuntimeError("no data returned")
        df.index = df.index.tz_localize(None).normalize()
        return df.rename(columns=str.lower)

    def _client(self):
        from .schwab_api import get_client
        if self._schwab is None:
            self._schwab = get_client(self.cfg)
        return self._schwab

    def _from_schwab(self, ticker: str) -> pd.DataFrame:
        resp = self._client().get_price_history_every_day(
            ticker, start_datetime=datetime.now() - timedelta(days=365 * self.years),
            end_datetime=datetime.now())
        resp.raise_for_status()
        candles = resp.json().get("candles", [])
        if not candles:
            raise RuntimeError("no data returned")
        df = pd.DataFrame(candles)
        # Schwab timestamps are milliseconds; convert to New York calendar dates.
        dates = pd.to_datetime(df["datetime"], unit="ms", utc=True).dt.tz_convert("America/New_York")
        df.index = pd.DatetimeIndex(dates.dt.tz_localize(None).dt.normalize())
        return df

    def _add_todays_bar(self, bars: dict):
        """Schwab's daily history may not include today's unfinished day. During market
        hours, add it from a live quote so the bot sees the current price. (Not cached.)"""
        resp = self._client().get_quotes(list(bars))
        resp.raise_for_status()
        today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
        for ticker, info in resp.json().items():
            q = info.get("quote", {})
            if ticker not in bars or not q.get("lastPrice") or not q.get("tradeTime"):
                continue
            traded = (pd.Timestamp(q["tradeTime"], unit="ms", tz="UTC")
                      .tz_convert("America/New_York").normalize().tz_localize(None))
            df = bars[ticker]
            if traded == today and df.index[-1] < today:
                row = pd.DataFrame({"open": q.get("openPrice"), "high": q.get("highPrice"),
                                    "low": q.get("lowPrice"), "close": q["lastPrice"],
                                    "volume": q.get("totalVolume")}, index=[today])
                bars[ticker] = pd.concat([df, row])
