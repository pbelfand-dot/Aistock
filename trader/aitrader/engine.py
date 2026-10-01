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
from .market_hours import minutes_to_close, now_ny
from .performance import summarize
from .risk import RiskManager
from .strategies import current_scores


def decide_orders(scores: pd.Series, prices: pd.Series, positions: dict, buying_power: float,
                  equity: float, strategy, risk: RiskManager, allow_new_buys: bool = True,
                  stops_only: bool = False, atr_pct: dict = None) -> list:
    """atr_pct: {ticker: its usual daily range in %} for stops sized to how much each stock moves."""
    orders = []

    # 1) EXITS first: they free up cash and slots.
    for ticker, pos in positions.items():
        price = prices.get(ticker)
        if price is None or math.isnan(price):
            continue
        score = scores.get(ticker, float("nan"))
        own = getattr(pos, "stop_pct", 0) or None
        if risk.stop_loss_hit(pos.avg_cost, price, own):
            drop = (1 - price / pos.avg_cost) * 100
            sized = f" (its stop: {own:g}%, sized to how much it moves)" if own else ""
            orders.append(Order(ticker, "SELL", pos.qty, price, f"stop-loss: down {drop:.1f}% from our buy price{sized}",
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
        stop = risk.stop_for((atr_pct or {}).get(ticker)) if risk.stop_atr_multiple else None
        qty = risk.position_size(equity, buying_power, price, stop)
        if qty <= 0:
            continue                     # can't afford a share (or $1 of one, with fractional shares) within the limits
        orders.append(Order(ticker, "BUY", qty, price, f"{strategy.name} score {score:.2f} >= {strategy.buy_above}",
                            stop_pct=stop))
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
                yesterday_equity, desk_cfg: dict, stops_only: bool = False, no_buys: str = "",
                atr_pct: dict = None) -> list:
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
                         allow_new_buys=allowed and not too_late and not no_buys, stops_only=stops_only,
                         atr_pct=atr_pct)


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


def atr_pct_table(bars: dict, intraday: bool, recent: bool = False) -> pd.DataFrame:
    """Each stock's usual daily range (its 14-day average true range) as % of its price, known at each bar
    from EARLIER days only. recent=True looks at just the last few weeks (enough for today's number)."""
    from .strategies import daily_atr
    out = {}
    for ticker, df in bars.items():
        if recent:
            df = df.tail(78 * 20 if intraday else 30)
        if intraday:
            atr = daily_atr(df)
        else:
            prev = df["close"].shift(1)
            true_range = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
                                   axis=1).max(axis=1)
            atr = true_range.rolling(14).mean().shift(1)
        out[ticker] = atr / df["close"] * 100
    return pd.DataFrame(out)


def latest_atr_pct(bars: dict, intraday: bool) -> dict:
    table = atr_pct_table(bars, intraday, recent=True)
    if table.empty:
        return {}
    last = table.ffill().iloc[-1]
    return {t: float(v) for t, v in last.items() if pd.notna(v)}


def resting_stop_fills(broker, risk: RiskManager, opens: pd.Series, lows: pd.Series, date: str) -> list:
    """Backtest only: a stop-loss order resting at the broker sells during the day as soon as
    the price touches it (or at the open, if the stock gaps down below it overnight)."""
    fills = []
    for ticker, pos in broker.positions().items():
        stop = pos.avg_cost * (1 - (pos.stop_pct or risk.stop_loss_pct) / 100)
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
    atr = atr_pct_table(bars, strategy.style == "day").reindex(closes.index) if risk.stop_atr_multiple else None

    for ts in active:
        date = ts.strftime("%Y-%m-%d")
        if date != current_day:
            current_day, day_start = date, last_equity
        prices = closes.loc[ts]
        if strategy.style == "swing":
            all_fills += resting_stop_fills(broker, risk, opens.loc[ts], lows.loc[ts], date)
        orders = desk_orders(strategy, ts, scores.loc[ts], prices, broker, risk, day_start, cfg["desks"][desk],
                             atr_pct=atr.loc[ts].dropna().to_dict() if atr is not None and ts in atr.index else None)
        all_fills += execute(orders, broker, date)
        curve[ts] = last_equity = broker.equity(prices)

    equity = pd.Series(curve, dtype=float)
    daily = equity.groupby(equity.index.normalize()).last() if len(equity) else equity
    fills = pd.DataFrame([f.__dict__ for f in all_fills]) if all_fills else None
    result = summarize(daily, fills)
    result["start"] = active[0].strftime("%Y-%m-%d") if len(active) else None
    result["end"] = active[-1].strftime("%Y-%m-%d") if len(active) else None
    return result


def say_step(store, mode: str, text: str):
    """What the autopilot is doing this very moment (a few words), for the live Thinking tab."""
    store.set("autopilot_step", {"mode": mode, "text": text, "at": now_ny().isoformat(timespec="seconds")})


def remember_watch(store, mode, now, risk, prices, broker):
    """What it owns and how far each one is from its stop-loss, at every check (stop-loss checks too)."""
    holdings = []
    for t, pos in broker.positions().items():
        price = None if t not in prices or pd.isna(prices[t]) else float(prices[t])
        stop = pos.avg_cost * (1 - (pos.stop_pct or risk.stop_loss_pct) / 100)
        holdings.append({"ticker": t, "qty": pos.qty, "avg_cost": round(pos.avg_cost, 2),
                         "price": round(price, 2) if price else None, "stop": round(stop, 2),
                         "above_stop_pct": round((price / stop - 1) * 100, 1) if price and stop else None})
    store.set(f"{mode}_watch", {"time": now.strftime("%Y-%m-%d %H:%M"), "holdings": holdings})


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
    day = now.strftime("%Y-%m-%d")
    saved = store.get(f"{mode}_checks") or {}                # today's checks, one line each (the live feed)
    checks = saved.get("items", []) if saved.get("date") == day else []
    checks.append({"time": thinking["time"][-5:], "top": thinking["top"][:3], "orders": thinking["orders"],
                   "why": why_no_buys, "holding": thinking["holding"]})
    store.set(f"{mode}_checks", {"date": day, "items": checks[-120:]})
    if orders:
        saved = store.get(f"{mode}_decisions") or {}
        items = saved.get("items", []) if saved.get("date") == day else []
        store.set(f"{mode}_decisions", {"date": day, "items": (items + [thinking])[-30:]})


def in_play_today(cfg: dict, today: str) -> dict:
    """{ticker: relative volume} of today's stocks in play (in_play.py)."""
    from .in_play import load
    state = load(cfg)
    return {p["symbol"]: p["rvol"] for p in state.get("picks") or []} if state.get("day") == today else {}


def run_cycle(store, broker, strategy, risk: RiskManager, bars: dict, market: pd.DataFrame, now,
              desk_cfg: dict, stops_only: bool = False, no_buys: str = "", cfg: dict = None,
              practice: bool = False) -> dict:
    """One moment of paper or live trading. stops_only: just check stop-losses.
    no_buys: a reason not to open new trades now (e.g. a lesson from its own trades, see learning.py).
    cfg: when given, the team (agents.py) looks at the orders before they go.
    practice: weekend practice (weekend.py): the team doesn't see today's real option bets or stocks in
    play, and nothing is written to the desk's mistake memory."""
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
    say_step(store, mode, f"checking the stop-losses on {len(broker.positions())} holdings" if stops_only
             else f"scoring {len(bars)} stocks with {strategy.name}")
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

    atr = latest_atr_pct(bars, strategy.style == "day") if risk.stop_atr_multiple and not stops_only else None
    orders = desk_orders(strategy, now, scores, prices, broker, risk, yesterday_equity, desk_cfg, stops_only,
                         no_buys, atr_pct=atr)
    team = None
    if cfg is not None and not stops_only:
        from .agents import review_orders, settings as team_settings
        if team_settings(cfg)["enabled"]:
            say_step(store, mode, "the team (Scout, Analyst, Trader, Risk) is going over "
                     + (f"{len(orders)} order{'s' if len(orders) != 1 else ''}" if orders else "the scores"))
            from .options_flow import gaps_today
            desk = mode.split("-", 1)[-1]
            try:
                orders, team = review_orders(cfg, orders, scores, prices, broker, bars,
                                             {} if practice else gaps_today(store), strategy,
                                             risk.max_open_positions, lessons=store.get(f"mistakes:{desk}") or [],
                                             in_play=in_play_today(cfg, today) if strategy.style == "day"
                                             and not practice else {})
                if not practice:
                    from .mistakes import remember_tags
                    remember_tags(store, desk, today, {o.ticker: team["tags"][o.ticker] for o in orders
                                                       if o.side == "BUY" and o.ticker in team["tags"]})
            except Exception as e:                  # the notes must never block a trade (above all, a stop-loss)
                team = {"error": f"the team couldn't write its notes ({e!r}); the orders went ahead unchanged"}
    if orders:
        say_step(store, mode, "sending " + ", ".join(f"{o.side} {o.ticker}" for o in orders[:4])
                 + (" and more" if len(orders) > 4 else ""))
    fills = execute(orders, broker, today)       # each fill is saved the moment it happens (broker.on_fill)
    remember_watch(store, mode, now, risk, prices, broker)
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
