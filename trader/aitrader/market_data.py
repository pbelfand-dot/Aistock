"""
market_data.py: gets prices.

  daily bars     (one per day)      for the swing desk
  5-minute bars  (78 per day)       for the day desk

Sources, same output (config.yaml -> data.source):
  alpaca    Alpaca data: free real-time "iex" feed, years of 5-minute history
  yfinance  free Yahoo data, no account needed (fine for study and paper)
  schwab    Schwab's real-time data

The bot keeps its own copy of every price it downloads (data/cache/), and
after the first download of the day it only fetches the newest bars. That's
faster, kinder to the data source, and it lets the 5-minute history grow
beyond what Yahoo/Schwab keep.

Output: ({ticker: DataFrame[open, high, low, close, volume]}, benchmark DataFrame).
During market hours the last row is the bar in progress: its close = the current price.
"""
import json
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import data_path, data_source

COLUMNS = ["open", "high", "low", "close", "volume"]


class MarketData:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.source = data_source(cfg)
        self._schwab = None
        self._alpaca = None
        self._memo = {}                          # avoid downloading the same thing twice in a minute

    # ---- public ---------------------------------------------------------------
    def load(self, desk: str, extra=()):
        """Prices for one desk's watchlist (+ `extra` tickers, e.g. ones the bot still owns) + the benchmark."""
        interval = "5m" if desk == "day" else "1d"
        scanned = []
        if desk == "swing":                          # the top of the daily all-stocks scan (scanner.py)
            from .scanner import trade_candidates
            scanned = trade_candidates(self.cfg)
        elif desk == "day":                          # today's stocks in play (in_play.py), from 9:35
            from .in_play import today_picks
            scanned = today_picks(self.cfg)
        wanted = list(dict.fromkeys(self.cfg["desks"][desk]["watchlist"] + scanned + list(extra)))
        tickers = list(dict.fromkeys(wanted + [self.cfg["benchmark"]]))
        bars = {}
        for t in tickers:
            try:
                bars[t] = self.history(t, interval)
            except Exception as e:               # one bad ticker shouldn't stop the day
                print(f"  ! could not load {t} ({interval}): {e}")
        if self.cfg["benchmark"] not in bars:
            raise RuntimeError("Could not load the benchmark; check your internet/data source.")
        if self.source == "schwab" and interval == "1d":
            self._add_todays_bar(bars)
        if self.source == "alpaca" and interval == "1d":
            self._add_todays_bar_alpaca(bars)
        market = bars[self.cfg["benchmark"]]
        return {t: bars[t] for t in wanted if t in bars}, market

    def history(self, ticker: str, interval: str) -> pd.DataFrame:
        key = (ticker, interval)
        if key in self._memo and time.time() - self._memo[key][0] < 60:
            return self._memo[key][1]

        # Each source gets its own folder: e.g. Yahoo and Alpaca volumes aren't comparable.
        path = data_path(self.cfg, f"cache/{self.source}/{interval}/{ticker}.csv")
        cached = pd.read_csv(path, index_col=0, parse_dates=True) if path.exists() else None
        if cached is None or not self._refreshed_today(key):
            df = self._download(ticker, interval, recent=False)   # first time today: full history
            if interval == "5m" and cached is not None:
                df = _merge(cached, df)                         # keep older 5-min bars we saved
            self._mark_refreshed(key)
        else:
            df = _merge(cached, self._download(ticker, interval, recent=True))

        df = df[COLUMNS].dropna(subset=["close"]).sort_index()
        df.to_csv(path)
        self._memo[key] = (time.time(), df)
        return df

    # ---- cache bookkeeping -------------------------------------------------------
    def _refreshed_today(self, key) -> bool:
        log = data_path(self.cfg, "cache/refreshed.json")
        done = json.loads(log.read_text()) if log.exists() else {}
        return done.get(f"{self.source}:{key[1]}:{key[0]}") == datetime.now().strftime("%Y-%m-%d")

    def _mark_refreshed(self, key):
        log = data_path(self.cfg, "cache/refreshed.json")
        done = json.loads(log.read_text()) if log.exists() else {}
        done[f"{self.source}:{key[1]}:{key[0]}"] = datetime.now().strftime("%Y-%m-%d")
        log.write_text(json.dumps(done))

    # ---- sources -----------------------------------------------------------
    def _download(self, ticker, interval, recent) -> pd.DataFrame:
        if self.source == "demo":                     # made-up prices (demo.py): never download anything
            path = data_path(self.cfg, f"cache/demo/{interval}/{ticker}.csv")
            return pd.read_csv(path, index_col=0, parse_dates=True) if path.exists() else pd.DataFrame(columns=COLUMNS)
        if self.source == "schwab":
            return self._from_schwab(ticker, interval, recent)
        if self.source == "alpaca":
            return self._from_alpaca(ticker, interval, recent)
        return self._from_yahoo(ticker, interval, recent)

    def _alpaca_client(self):
        from .alpaca_api import data_client
        if self._alpaca is None:
            self._alpaca = data_client(self.cfg)
        return self._alpaca

    def _alpaca_feed(self):
        from alpaca.data.enums import DataFeed
        return DataFeed(self.cfg["data"].get("alpaca_feed", "iex"))

    def _from_alpaca(self, ticker, interval, recent) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        if interval == "1d":
            days, timeframe = (5 if recent else 365 * self.cfg["data"]["history_years"]), TimeFrame.Day
        else:
            days, timeframe = (2 if recent else self.cfg["data"]["intraday_days"]), TimeFrame(5, TimeFrameUnit.Minute)
        request = StockBarsRequest(symbol_or_symbols=ticker, timeframe=timeframe, adjustment=Adjustment.ALL,
                                   start=datetime.now(timezone.utc) - timedelta(days=days), feed=self._alpaca_feed())
        df = self._alpaca_client().get_stock_bars(request).df
        if df.empty:
            raise RuntimeError("no data returned")
        df = df.xs(ticker, level="symbol") if "symbol" in df.index.names else df
        df.index = pd.DatetimeIndex(pd.to_datetime(df.index, utc=True).tz_convert("America/New_York").tz_localize(None))
        if interval == "1d":
            df.index = df.index.normalize()
        else:
            df = df.between_time("09:30", "15:59")         # regular session only
        return df

    def _add_todays_bar_alpaca(self, bars: dict):
        """Make sure today's (unfinished) daily bar is there, with the latest trade as its close."""
        from alpaca.data.requests import StockSnapshotRequest
        snaps = self._alpaca_client().get_stock_snapshot(
            StockSnapshotRequest(symbol_or_symbols=list(bars), feed=self._alpaca_feed()))
        today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
        for ticker, snap in snaps.items():
            day, trade = getattr(snap, "daily_bar", None), getattr(snap, "latest_trade", None)
            if ticker not in bars or day is None or trade is None:
                continue
            day_date = pd.Timestamp(day.timestamp).tz_convert("America/New_York").normalize().tz_localize(None)
            if day_date != today:
                continue
            row = pd.DataFrame({"open": day.open, "high": max(day.high, trade.price), "low": min(day.low, trade.price),
                                "close": trade.price, "volume": day.volume}, index=[today])
            df = bars[ticker]
            bars[ticker] = pd.concat([df[df.index < today], row])

    def _from_yahoo(self, ticker, interval, recent) -> pd.DataFrame:
        import yfinance as yf
        if interval == "1d":
            period = "5d" if recent else f"{self.cfg['data']['history_years']}y"
        else:
            # Yahoo keeps only ~60 days of 5-minute bars; ask for 59 to stay inside the limit.
            period = "2d" if recent else f"{min(self.cfg['data']['intraday_days'], 59)}d"
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            raise RuntimeError("no data returned")
        df.index = pd.DatetimeIndex(df.index.tz_convert("America/New_York").tz_localize(None))
        if interval == "1d":
            df.index = df.index.normalize()
        return df.rename(columns=str.lower)

    def _client(self):
        from .schwab_api import get_client
        if self._schwab is None:
            self._schwab = get_client(self.cfg)
        return self._schwab

    def _from_schwab(self, ticker, interval, recent) -> pd.DataFrame:
        if interval == "1d":
            days = 5 if recent else 365 * self.cfg["data"]["history_years"]
            fetch = self._client().get_price_history_every_day
        else:
            days = 2 if recent else self.cfg["data"]["intraday_days"]
            fetch = self._client().get_price_history_every_five_minutes
        resp = fetch(ticker, start_datetime=datetime.now() - timedelta(days=days), end_datetime=datetime.now(),
                     need_extended_hours_data=False)
        resp.raise_for_status()
        candles = resp.json().get("candles", [])
        if not candles:
            raise RuntimeError("no data returned")
        df = pd.DataFrame(candles)
        # Schwab timestamps are milliseconds; convert to New York time.
        stamps = pd.to_datetime(df["datetime"], unit="ms", utc=True).dt.tz_convert("America/New_York")
        stamps = stamps.dt.tz_localize(None)
        df.index = pd.DatetimeIndex(stamps.dt.normalize() if interval == "1d" else stamps)
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


def _merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Old bars + new bars; where both have the same time, the new one wins."""
    both = pd.concat([old[COLUMNS], new[COLUMNS]])
    return both[~both.index.duplicated(keep="last")].sort_index()
