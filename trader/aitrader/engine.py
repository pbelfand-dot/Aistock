"""
engine.py: the heart of the bot.

decide_orders()  today's scores + what we own -> list of orders (the core rules)
desk_orders()    adds each desk's timing rules (e.g. the day desk sells everything before the close)
run_backtest()   replays history bar by bar through desk_orders()
run_cycle()      one real moment of paper or live trading

The SAME desk_orders() runs in backtest, paper and live. What you test is
exactly what you trade.

Timing:
  swing desk  decides once a day, 15 minutes before the close. The backtest
              copies that: it decides and fills at each day's close (minus
              slippage), and stop-losses fill during the day like a resting
              stop order at Schwab would.
  day desk    decides every 5 minutes; no new buys in the last 30 minutes;
              sells everything 10 minutes before the close.
"""
import math

import pandas as pd

from .brokers import Ledger, Order, PaperBroker
from .config import desk_capital, is_cash_account
from .market_hours import minutes_to_close
from .performance import summarize
from .risk import RiskManager
from .strategies import current_scores


def decide_orders(scores: pd.Series, prices: pd.Series, positions: dict, buying_power: float,
                  equity: float, strategy, risk: RiskManager, allow_new_buys: bool = True,
                  stops_only: bool = False) -> list:
    orders = []

    # 1) EXITS first: they free up cash and slots.
    for ticker, pos in positions.items():
        price = prices.get(ticker)
        if price is None or math.isnan(price):
            continue
        score = scores.get(ticker, float("nan"))
        if risk.stop_loss_hit(pos.avg_cost, price):
            drop = (1 - price / pos.avg_cost) * 100
            orders.append(Order(ticker, "SELL", pos.qty, price, f"stop-loss: down {drop:.1f}% from our buy price",
                                urgent=True))
        elif not stops_only and not math.isnan(score) and score < strategy.sell_below:
            orders.append(Order(ticker, "SELL", pos.qty, price,
                                f"{strategy.name} says exit (score {score:.2f} < {strategy.sell_below})"))
        elif not stops_only and risk.trim_qty(pos.qty, price, equity):
            share = pos.qty * price / equity * 100
            orders.append(Order(ticker, "SELL", risk.trim_qty(pos.qty, price, equity), price,
                                f"trim: {share:.0f}% of the desk is in {ticker} (limit {risk.max_position_pct:g}%)"))

    if stops_only or not allow_new_buys:
        return orders

    # 2) ENTRIES: strongest scores first, while we have room and cash.
    closing = sum(1 for o in orders if o.qty >= positions[o.ticker].qty)      # a trim keeps the stock
    open_slots = risk.max_open_positions - (len(positions) - closing)
    candidates = scores.dropna()
    candidates = candidates[candidates >= strategy.buy_above].sort_values(ascending=False)
    for ticker, score in candidates.items():
        if open_slots <= 0:
            break
        if ticker in positions:          # already own it (or selling it now): skip
            continue
        price = prices.get(ticker)
        qty = risk.position_size(equity, buying_power, price)
        if qty <= 0:
            continue                     # can't afford a share (or $1 of one, with fractional shares) within the limits
        orders.append(Order(ticker, "BUY", qty, price, f"{strategy.name} score {score:.2f} >= {strategy.buy_above}"))
        buying_power -= qty * price
        open_slots -= 1
    return orders


def sell_all(positions: dict, prices: pd.Series, reason: str, tickers=None) -> list:
    orders = []
    for ticker, pos in positions.items():
        price = prices.get(ticker)
        if (tickers is None or ticker in tickers) and price is not None and not math.isnan(price):
            orders.append(Order(ticker, "SELL", pos.qty, price, reason, urgent=True))
    return orders


def desk_orders(strategy, now, scores: pd.Series, prices: pd.Series, broker, risk: RiskManager,
                yesterday_equity, desk_cfg: dict, stops_only: bool = False, no_buys: str = "") -> list:
    today = now.strftime("%Y-%m-%d")
    positions = broker.positions()
    equity = broker.equity(prices)
    too_late = False
    if strategy.style == "day":
        left = minutes_to_close(now)
        if left <= desk_cfg["flatten_minutes_before_close"]:
            return sell_all(positions, prices, "end of day: day trades are never held overnight")
        leftovers = [t for t, p in positions.items() if p.opened_on != today]
        if leftovers:
            return sell_all(positions, prices, "left over from an earlier day (was the laptop asleep?)", leftovers)
        too_late = left <= desk_cfg["last_entry_minutes_before_close"]
    allowed, _ = risk.new_buys_allowed(equity, yesterday_equity)
    return decide_orders(scores, prices, positions, broker.buying_power(today), equity, strategy, risk,
                         allow_new_buys=allowed and not too_late and not no_buys, stops_only=stops_only)


def execute(orders: list, broker, date: str) -> list:
    """Sells first, then buys. Returns the fills that actually happened."""
    fills = []
    for order in sorted(orders, key=lambda o: o.side != "SELL"):
        fill = broker.submit(order, date)
        if fill:
            fills.append(fill)
    return fills


def price_table(bars: dict, column: str = "close") -> pd.DataFrame:
    return pd.DataFrame({t: df[column] for t, df in bars.items()}).sort_index()


def closes_table(bars: dict) -> pd.DataFrame:
    return price_table(bars, "close")


def resting_stop_fills(broker, risk: RiskManager, opens: pd.Series, lows: pd.Series, date: str) -> list:
    """Backtest only: a stop-loss order resting at the broker sells during the day as soon as
    the price touches it (or at the open, if the stock gaps down below it overnight)."""
    fills = []
    for ticker, pos in broker.positions().items():
        stop = pos.avg_cost * (1 - risk.stop_loss_pct / 100)
        low, open_ = lows.get(ticker), opens.get(ticker)
        if low is None or math.isnan(low) or low > stop:
            continue
        price = min(open_, stop) if open_ is not None and not math.isnan(open_) else stop
        fill = broker.submit(Order(ticker, "SELL", pos.qty, price, f"stop-loss at ${stop:.2f} (resting order)"), date)
        if fill:
            fills.append(fill)
    return fills


def run_backtest(strategy, bars: dict, market: pd.DataFrame, cfg: dict, desk: str,
                 scores: pd.DataFrame = None, start=None) -> dict:
    """Replay history bar by bar with fake money. Returns the scorecard.
    start: only trade from this date on (used for the study month's 'shadow trading')."""
    scores = strategy.scores(bars, market) if scores is None else scores
    closes = closes_table(bars)
    opens, lows = price_table(bars, "open"), price_table(bars, "low")
    scores = scores.reindex(index=closes.index, columns=closes.columns)
    active = scores.dropna(how="all").index
    if start is not None:
        active = active[active >= pd.Timestamp(start)]

    risk = RiskManager.for_desk(cfg, desk)
    broker = PaperBroker(Ledger(desk_capital(cfg, desk, live=False)), cfg["paper"]["slippage_pct"],
                         cfg["paper"]["commission_per_trade"], mode="backtest",
                         cash_account=is_cash_account(cfg))
    curve, all_fills, last_equity, day_start, current_day = {}, [], None, None, None

    for ts in active:
        date = ts.strftime("%Y-%m-%d")
        if date != current_day:
            current_day, day_start = date, last_equity
        prices = closes.loc[ts]
        if strategy.style == "swing":
            all_fills += resting_stop_fills(broker, risk, opens.loc[ts], lows.loc[ts], date)
        orders = desk_orders(strategy, ts, scores.loc[ts], prices, broker, risk, day_start, cfg["desks"][desk])
        all_fills += execute(orders, broker, date)
        curve[ts] = last_equity = broker.equity(prices)

    equity = pd.Series(curve, dtype=float)
    daily = equity.groupby(equity.index.normalize()).last() if len(equity) else equity
    fills = pd.DataFrame([f.__dict__ for f in all_fills]) if all_fills else None
    result = summarize(daily, fills)
    result["start"] = active[0].strftime("%Y-%m-%d") if len(active) else None
    result["end"] = active[-1].strftime("%Y-%m-%d") if len(active) else None
    return result


def remember_thinking(store, mode, now, strategy, risk, scores, prices, broker, orders, why_no_buys, team=None):
    """What it was thinking at this decision, for the after-market report (report.py): its top picks,
    what it did, and why it didn't buy more. The latest one is kept, plus each decision that traded."""
    positions = broker.positions()
    top = scores.dropna().sort_values(ascending=False).head(8)
    price = lambda t: None if t not in prices or pd.isna(prices[t]) else round(float(prices[t]), 2)
    thinking = {
        "time": now.strftime("%Y-%m-%d %H:%M"), "strategy": strategy.name,
        "buy_above": strategy.buy_above, "sell_below": strategy.sell_below,
        "top": [{"ticker": t, "score": round(float(v), 3), "price": price(t), "owned": t in positions}
                for t, v in top.items()],
        "holding": len(positions), "max_positions": risk.max_open_positions, "cash": round(broker.cash(), 2),
        "why_no_buys": why_no_buys,
        "team": team,                                   # the agents' notes on this decision (agents.py)
        "orders": [{"side": o.side, "ticker": o.ticker, "qty": o.qty, "price": round(float(o.price), 2),
                    "reason": o.reason} for o in orders],
    }
    store.set(f"{mode}_thinking", thinking)
    if orders:
        day = now.strftime("%Y-%m-%d")
        saved = store.get(f"{mode}_decisions") or {}
        items = saved.get("items", []) if saved.get("date") == day else []
        store.set(f"{mode}_decisions", {"date": day, "items": (items + [thinking])[-30:]})


def in_play_today(cfg: dict, today: str) -> dict:
    """{ticker: relative volume} of today's stocks in play (in_play.py)."""
    from .in_play import load
    state = load(cfg)
    return {p["symbol"]: p["rvol"] for p in state.get("picks") or []} if state.get("day") == today else {}


def run_cycle(store, broker, strategy, risk: RiskManager, bars: dict, market: pd.DataFrame, now,
              desk_cfg: dict, stops_only: bool = False, no_buys: str = "", cfg: dict = None) -> dict:
    """One moment of paper or live trading. stops_only: just check stop-losses.
    no_buys: a reason not to open new trades now (e.g. a lesson from its own trades, see learning.py).
    cfg: when given, the team (agents.py) looks at the orders before they go."""
    mode = broker.mode
    today = now.strftime("%Y-%m-%d")
    prices = closes_table(bars).ffill().iloc[-1]
    equity = broker.equity(prices)
    peak = max(store.get(f"{mode}_peak_equity") or equity, equity)
    store.set(f"{mode}_peak_equity", peak)
    if risk.kill_switch_tripped(equity, peak):
        return {"kill_switch": True, "equity": equity, "peak": peak, "prices": prices}

    curve = store.equity_curve(mode)
    before_today = curve[curve.index < pd.Timestamp(today)]
    yesterday_equity = float(before_today.iloc[-1]) if len(before_today) else None

    scores = pd.Series(dtype=float)
    if not stops_only:
        scores = current_scores(strategy, bars, market)
        for ticker in broker.blocked:               # e.g. stocks you own yourself
            if ticker not in broker.positions():
                scores[ticker] = float("nan")
        allowed, why_not = risk.new_buys_allowed(equity, yesterday_equity)
        if not allowed and strategy.style == "swing":
            store.log(f"[{mode}] no new buys today: {why_not}")
        if no_buys and store.get(f"{mode}_no_buys_logged") != today:        # once a day, not every 5 minutes
            store.log(f"[{mode}] no new buys today: {no_buys}")
            store.set(f"{mode}_no_buys_logged", today)

    orders = desk_orders(strategy, now, scores, prices, broker, risk, yesterday_equity, desk_cfg, stops_only,
                         no_buys)
    team = None
    if cfg is not None and not stops_only:
        from .agents import review_orders, settings as team_settings
        if team_settings(cfg)["enabled"]:
            from .options_flow import gaps_today
            desk = mode.split("-", 1)[-1]
            try:
                orders, team = review_orders(cfg, orders, scores, prices, broker, bars, gaps_today(store), strategy,
                                             risk.max_open_positions, lessons=store.get(f"mistakes:{desk}") or [],
                                             in_play=in_play_today(cfg, today) if strategy.style == "day" else {})
                from .mistakes import remember_tags
                remember_tags(store, desk, today, {o.ticker: team["tags"][o.ticker] for o in orders
                                                   if o.side == "BUY" and o.ticker in team["tags"]})
            except Exception as e:                  # the notes must never block a trade (above all, a stop-loss)
                team = {"error": f"the team couldn't write its notes ({e!r}); the orders went ahead unchanged"}
    fills = execute(orders, broker, today)       # each fill is saved the moment it happens (broker.on_fill)
    if not stops_only:
        why = no_buys or ("" if allowed else why_not)
        if not why and strategy.style == "day" and minutes_to_close(now) <= desk_cfg["last_entry_minutes_before_close"]:
            why = f"no new day trades in the last {desk_cfg['last_entry_minutes_before_close']} minutes before the close"
        remember_thinking(store, mode, now, strategy, risk, scores, prices, broker, orders, why, team)
    if not orders and not stops_only and strategy.style == "swing":
        store.log(f"[{mode}] no trades today")

    end_equity = broker.equity(prices)
    store.record_equity(mode, today, end_equity, broker.cash())
    return {"kill_switch": False, "fills": fills, "equity": end_equity, "peak": peak, "prices": prices}
