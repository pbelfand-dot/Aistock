"""
engine.py: the heart of the bot.

decide_orders()    looks at today's scores + what we own -> list of orders
run_backtest()     replays years of history through decide_orders()
run_trading_day()  one real day of paper or live trading

The SAME decide_orders() runs in backtest, paper and live. What you test is
exactly what you trade.

Timing: the bot is meant to run once a day, about 15 minutes before the close
(3:45pm New York time). The backtest copies that: it decides and fills at each
day's closing price (minus slippage).
"""
import math

import pandas as pd

from .brokers import Ledger, Order, PaperBroker
from .performance import summarize
from .risk import RiskManager


def decide_orders(scores: pd.Series, prices: pd.Series, positions: dict, buying_power: float,
                  equity: float, strategy, risk: RiskManager, allow_new_buys: bool = True) -> list:
    orders = []

    # 1) EXITS first: they free up cash and slots.
    for ticker, pos in positions.items():
        price = prices.get(ticker)
        if price is None or math.isnan(price):
            continue
        score = scores.get(ticker, float("nan"))
        if risk.stop_loss_hit(pos.avg_cost, price):
            drop = (1 - price / pos.avg_cost) * 100
            orders.append(Order(ticker, "SELL", pos.qty, price,
                                f"stop-loss: down {drop:.1f}% from our buy price"))
        elif not math.isnan(score) and score < strategy.sell_below:
            orders.append(Order(ticker, "SELL", pos.qty, price,
                                f"{strategy.name} says exit (score {score:.2f} < {strategy.sell_below})"))

    if not allow_new_buys:
        return orders

    # 2) ENTRIES: strongest scores first, while we have room and cash.
    open_slots = risk.max_open_positions - (len(positions) - len(orders))
    candidates = scores.dropna()
    candidates = candidates[candidates >= strategy.buy_above].sort_values(ascending=False)
    for ticker, score in candidates.items():
        if open_slots <= 0:
            break
        if ticker in positions:          # already own it (or selling it today): skip
            continue
        price = prices.get(ticker)
        qty = risk.position_size(equity, buying_power, price)
        if qty < 1:
            continue                     # can't afford one whole share within the limits
        orders.append(Order(ticker, "BUY", qty, price,
                            f"{strategy.name} score {score:.2f} >= {strategy.buy_above}"))
        buying_power -= qty * price
        open_slots -= 1
    return orders


def execute(orders: list, broker, date: str) -> list:
    """Sells first, then buys. Returns the fills that actually happened."""
    fills = []
    for order in sorted(orders, key=lambda o: o.side != "SELL"):
        fill = broker.submit(order, date)
        if fill:
            fills.append(fill)
    return fills


def closes_table(bars: dict) -> pd.DataFrame:
    return pd.DataFrame({t: df["close"] for t, df in bars.items()}).sort_index()


def run_backtest(strategy, bars: dict, market: pd.DataFrame, cfg: dict, scores: pd.DataFrame = None) -> dict:
    """Replay history day by day with fake money. Returns the scorecard."""
    scores = strategy.scores(bars, market) if scores is None else scores
    closes = closes_table(bars)
    scores = scores.reindex(closes.index)
    active_days = scores.dropna(how="all").index

    risk = RiskManager.from_config(cfg)
    broker = PaperBroker(Ledger(cfg["paper"]["starting_cash"]), cfg["paper"]["slippage_pct"],
                         cfg["paper"]["commission_per_trade"], mode="backtest",
                         cash_account=cfg["live"]["account_type"] == "cash")
    curve, all_fills, yesterday = {}, [], None

    for day in active_days:
        date = day.strftime("%Y-%m-%d")
        prices = closes.loc[day]
        equity = broker.equity(prices)
        allowed, _ = risk.new_buys_allowed(equity, yesterday)
        orders = decide_orders(scores.loc[day], prices, broker.positions(), broker.buying_power(date),
                               equity, strategy, risk, allowed)
        all_fills += execute(orders, broker, date)
        curve[day] = yesterday = broker.equity(prices)

    fills = pd.DataFrame([f.__dict__ for f in all_fills]) if all_fills else None
    result = summarize(pd.Series(curve, dtype=float), fills)
    result["start"] = active_days[0].strftime("%Y-%m-%d") if len(active_days) else None
    result["end"] = active_days[-1].strftime("%Y-%m-%d") if len(active_days) else None
    return result


def run_trading_day(store, broker, strategy, risk: RiskManager, bars: dict, market: pd.DataFrame,
                    today: str) -> dict:
    """One day of paper or live trading. Returns what happened."""
    mode = broker.mode
    closes = closes_table(bars)
    prices = closes.iloc[-1]
    equity = broker.equity(prices)
    peak = max(store.get(f"{mode}_peak_equity") or equity, equity)
    store.set(f"{mode}_peak_equity", peak)

    if risk.kill_switch_tripped(equity, peak):
        return {"kill_switch": True, "equity": equity, "peak": peak}

    curve = store.equity_curve(mode)
    yesterday = curve[curve.index < pd.Timestamp(today)]
    yesterday_equity = float(yesterday.iloc[-1]) if len(yesterday) else None
    allowed, why_not = risk.new_buys_allowed(equity, yesterday_equity)
    if not allowed:
        store.log(f"[{mode}] no new buys today: {why_not}")

    scores = strategy.scores(bars, market).reindex(closes.index).iloc[-1]
    orders = decide_orders(scores, prices, broker.positions(), broker.buying_power(today),
                           equity, strategy, risk, allowed)
    fills = execute(orders, broker, today)
    for f in fills:
        store.record_fill(mode, f)
        pnl = f" (P&L ${f.realized_pnl:+.2f})" if f.side == "SELL" else ""
        store.log(f"[{mode}] {f.side} {f.qty} {f.ticker} @ ${f.price:.2f}{pnl}: {f.reason}")
    if not orders:
        store.log(f"[{mode}] no trades today")

    end_equity = broker.equity(prices)
    store.record_equity(mode, today, end_equity, broker.cash())
    return {"kill_switch": False, "fills": fills, "equity": end_equity, "peak": peak}
