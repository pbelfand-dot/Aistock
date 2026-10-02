"""
storage.py: the bot's memory.

Everything goes into ONE file: data/aitrader.sqlite. You can open it with any
SQLite viewer (e.g. "DB Browser for SQLite") and see exactly what the bot did.

Tables:
  state        small settings the bot remembers (current phase, dates, account ledgers)
  predictions  every opinion the bot made during study, and how it turned out
  fills        every buy/sell (paper, live, or backtest)
  equity       account value at the end of each trading day
  journal      a plain-English diary of what the bot did and why
  trials       every challenger ever compared with a desk's method, and how it did (challengers.py)
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY,
    made_on TEXT, ticker TEXT, strategy TEXT,
    score REAL, price REAL, horizon_days INTEGER,
    actual_return REAL, resolved_on TEXT,
    UNIQUE(made_on, ticker, strategy)
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY,
    mode TEXT, date TEXT, ticker TEXT, side TEXT,
    qty INTEGER, price REAL, realized_pnl REAL, reason TEXT, order_id TEXT
);

CREATE TABLE IF NOT EXISTS equity (
    mode TEXT, date TEXT, equity REAL, cash REAL,
    PRIMARY KEY (mode, date)
);

CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, ts TEXT, message TEXT);

CREATE TABLE IF NOT EXISTS trials (
    desk TEXT, name TEXT, against TEXT, first_tried TEXT, last_tested TEXT,
    days INTEGER, sharpe REAL, p_value REAL, deflated_sharpe REAL, verdict TEXT,
    PRIMARY KEY (desk, name, against)
);
"""


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        with self.db:
            # Older versions could reuse a paper order id; make them unique before the index.
            self.db.execute("UPDATE fills SET order_id = order_id || '-' || id WHERE id NOT IN "
                            "(SELECT MIN(id) FROM fills GROUP BY mode, order_id)")
            self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_row_per_order ON fills (mode, order_id)")

    # ---- simple key/value memory ----------------------------------------
    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                            (key, json.dumps(value)))

    # ---- diary ------------------------------------------------------------
    on_log = None                                       # e.g. phone alerts (phone.forwarder), set by the autopilot

    def log(self, message: str, echo: bool = True):
        ts = datetime.now().isoformat(timespec="seconds")
        with self.db:
            self.db.execute("INSERT INTO journal (ts, message) VALUES (?, ?)", (ts, message))
        if echo:
            print(f"[{ts}] {message}")
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:                           # an alert must never stop the bot
                pass

    def journal(self, limit: int = 15) -> list:
        rows = self.db.execute("SELECT ts, message FROM journal ORDER BY id DESC LIMIT ?", (limit,))
        return list(reversed(rows.fetchall()))

    # ---- study-phase predictions -------------------------------------------
    def add_prediction(self, made_on, ticker, strategy, score, price, horizon_days):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO predictions (made_on, ticker, strategy, score, price, horizon_days) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (made_on, ticker, strategy, float(score), float(price), int(horizon_days)))

    def resolve_prediction(self, pred_id, actual_return, resolved_on):
        with self.db:
            self.db.execute("UPDATE predictions SET actual_return = ?, resolved_on = ? WHERE id = ?",
                            (float(actual_return), resolved_on, int(pred_id)))

    def predictions(self, only_open: bool = False) -> pd.DataFrame:
        sql = "SELECT * FROM predictions"
        if only_open:
            sql += " WHERE actual_return IS NULL"
        return pd.read_sql_query(sql, self.db)

    def study_dates(self) -> list:
        rows = self.db.execute("SELECT DISTINCT made_on FROM predictions ORDER BY made_on")
        return [r[0] for r in rows]

    # ---- trades and account value -------------------------------------------
    def record_fill(self, mode: str, fill):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO fills (mode, date, ticker, side, qty, price, realized_pnl, reason, order_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mode, fill.date, fill.ticker, fill.side, fill.qty, fill.price,
                 fill.realized_pnl, fill.reason, fill.order_id))

    def fills(self, mode: str) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM fills WHERE mode = ? ORDER BY id", self.db, params=(mode,))

    def record_equity(self, mode: str, date: str, equity: float, cash: float):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO equity (mode, date, equity, cash) VALUES (?, ?, ?, ?)",
                            (mode, date, float(equity), float(cash)))

    def equity_curve(self, mode: str) -> pd.Series:
        df = pd.read_sql_query("SELECT date, equity FROM equity WHERE mode = ? ORDER BY date",
                               self.db, params=(mode,))
        return pd.Series(df["equity"].values, index=pd.to_datetime(df["date"]), dtype=float)

    # ---- every idea tried (challengers.py) -------------------------------------
    def record_trial(self, desk, name, against, day, days, sharpe, p_value):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO trials (desk, name, against, first_tried) VALUES (?, ?, ?, ?)",
                            (desk, name, against, day))
            self.db.execute("UPDATE trials SET last_tested = ?, days = ?, sharpe = ?, p_value = ? "
                            "WHERE desk = ? AND name = ? AND against = ?",
                            (day, int(days), float(sharpe), float(p_value), desk, name, against))

    def finish_trial(self, desk, name, against, deflated_sharpe, verdict):
        with self.db:
            self.db.execute("UPDATE trials SET deflated_sharpe = ?, verdict = ? WHERE desk = ? AND name = ? AND against = ?",
                            (float(deflated_sharpe), verdict, desk, name, against))

    def trials(self, desk) -> list:
        rows = self.db.execute("SELECT name, against, first_tried, last_tested, days, sharpe, p_value, deflated_sharpe, "
                               "verdict FROM trials WHERE desk = ? ORDER BY first_tried, name", (desk,))
        keys = ("name", "against", "first_tried", "last_tested", "days", "sharpe", "p_value", "deflated_sharpe", "verdict")
        return [dict(zip(keys, r)) for r in rows.fetchall()]

    def clear_mode(self, mode: str):
        """Wipe the paper (or live) track record so a fresh period starts from zero."""
        with self.db:
            self.db.execute("DELETE FROM fills WHERE mode = ?", (mode,))
            self.db.execute("DELETE FROM equity WHERE mode = ?", (mode,))
