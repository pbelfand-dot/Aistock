# AI Trader for Charles Schwab

A small, readable bot that **studies the market for a month, writes a trading plan,
proves it with fake money, and only then trades real money**, capped at $1,000.

It trades **two ways** ("desks"), each earning trust on its own:

| Desk | Style | When it decides | Money |
|---|---|---|---|
| **swing** | holds days to weeks | once a day, 3:45pm New York time | $500 |
| **day** | in and out the same day, never overnight | every 5 minutes | $500 |

The "AI" is a machine-learning model that runs **on your own laptop** (no paid API).
An optional local chatbot (Ollama) writes plain-English explanations. It never picks trades.

> Not financial advice. Most people who trade actively lose money, and day traders
> do worst of all. This bot's #1 job is to find out *safely* whether you have an edge,
> and to say "don't trade" if you don't.

---

## The journey (each desk separately; about 3 months before real money, at minimum)

```
 1. STUDY  (≥30 days)      Swing: each strategy writes down an opinion on every stock
                           daily; 5 days later it's graded. Day: each strategy
                           "shadow trades" every day with fake money. No real trades.
          │  python run.py plan
          ▼
 2. PLAN_REVIEW            Backtests every strategy, combines that with the study month,
                           writes data/trading_plan_<desk>.md. May honestly say "NO_TRADE".
          │  python run.py approve-plan   (you type YES)
          ▼
 3. PAPER  (≥30 trading    Trades the plan with fake money and real prices.
            days)
          │  python run.py promote        (every rule must pass, then you type REAL MONEY)
          ▼
 4. LIVE                   Real orders through Schwab, capped at the desk's budget.
                           Kill switch → back to PAPER automatically.
```

"Profitable" is defined in `config.yaml → promotion:`. Over at least 30 trading days and
20 closed trades, a desk's paper account must: make money, win ≥1.2× what it loses, never
drop more than 10%, **and beat just holding SPY**. A desk that can't do that stays on paper.

## Setup (once)

**1. Python 3.10+**
```bash
cd trader
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

**2. Optional: local LLM for write-ups.** Install [Ollama](https://ollama.com), then
`ollama pull qwen3:4b` (~2.5 GB). If it's not running, the bot still works.

**3. Schwab developer access** (start now; approval takes days, and real money needs it):
1. Sign up at <https://developer.schwab.com> and request **Trader API – Individual**.
2. Dashboard → **Create App** → select **Accounts and Trading Production** and
   **Market Data Production**. Callback URL: `https://127.0.0.1:8182` (exactly; no
   trailing slash, and not `localhost`).
3. Wait until the app says **Ready For Use** ("Approved – Pending" doesn't work yet).
4. Put the App Key and Secret in `.env`, then run `python run.py schwab-login`.
5. Set `data.source: schwab` in `config.yaml`. Real money requires Schwab's real-time
   prices. Yahoo is fine for study and paper.

⚠️ **Schwab logins expire every 7 days, and there's no way around it.** Run
`python run.py schwab-login` weekly. `status` shows the days left, and the autopilot warns you.

## Run it: one command, leave it running

```bash
python run.py autopilot
```
Every trading day it:
- **9:30am to 3:50pm:** runs the day desk every 5 minutes and watches the swing desk's stop-losses
- **3:45pm:** makes the swing desk's daily decision
- **3:50pm:** the day desk sells everything (it never holds overnight)
- **4:10pm:** studies (grades opinions, shadow trades) and gets smarter

It handles early-close days (1pm), weekends and holidays, and it never crashes on an
error: it logs it and tries again in 5 minutes.

### Keep the laptop awake (important!)
The bot can only work while the laptop is **awake, plugged in and online**.

**Mac.** Closing the lid puts a MacBook to sleep, even with `caffeinate`. Pick one:
- Keep the lid **open**, plugged in, and start the bot with
  `caffeinate -i python run.py autopilot` (stops idle sleep while the bot runs), **or**
- Clamshell mode: lid closed, with an **external monitor + power** connected, **or**
- The free app **Amphetamine** (Mac App Store), with its "closed display" option.

**Windows.** Settings → System → Power: when plugged in, **Sleep = Never**. Then Control
Panel → Power Options → "Choose what closing the lid does": **Plugged in = Do nothing**.

If the laptop sleeps anyway: the day desk sells leftovers the moment it wakes, the journal
flags a missed swing decision, and in LIVE the **resting stop-loss orders at Schwab** keep
protecting your positions.

## Commands

| Command | What it does |
|---|---|
| `autopilot` | **The main one.** Runs everything, every trading day |
| `status` | Each desk's phase, report card, paper/live results, Schwab login days left, journal |
| `backtest` | Tests every strategy on history vs. buy-and-hold (safe, any time) |
| `plan` | After the study month: writes each desk's plan |
| `approve-plan` | You approve a desk's plan → it starts paper trading |
| `promote` | Checks a desk's paper results against the rules → you confirm → LIVE |
| `kill` | **Emergency:** cancel the bot's orders, sell everything it owns, halt |
| `resume` | Un-halt after a kill (after you've looked at what happened) |
| `schwab-login` | Weekly Schwab login (`--manual` if no browser opens) |
| `trade --desk day --anyway` | Testing: one paper cycle even if the market is closed |
| `trade --dry-run` | LIVE: shows exact orders it *would* send, sends nothing |

Add `--desk swing` or `--desk day` to act on one desk only.

## Your money and your shared Schwab account

The bot trades inside **your normal Schwab account**, alongside your own investing. So:

1. **Budget cap:** each desk has its own checkbook ($500 each). The bot never spends more,
   and never more than the cash Schwab says is actually available. **It never borrows.**
2. **Hands off your stuff:** it only sells shares **it** bought, and it **won't buy a stock
   you already own**. Schwab sells a stock's oldest shares first by default, so sharing a
   ticker could sell *your* shares and mess up your taxes. So don't buy the bot's stocks yourself.
3. **Only its own orders:** `kill` and cleanup only cancel orders the bot placed, never yours.
4. **Resting stop-loss at Schwab** for every live position, in case the laptop sleeps or crashes.
   If a sell doesn't fill, the stop goes right back on. The bot never sells shares while an
   old stop for them might still be live, so it can't sell the same shares twice.
5. **Never loses track of an order:** it only forgets an order once Schwab confirms it's
   finished. Every fill is saved the moment it happens, and after a crash or sleep it
   checks what happened before doing anything else.
6. **Urgent exits** (stop-loss, the day desk's end-of-day sell, emergency) use market orders.
   After a kill or kill switch, a live desk stays **LIVE + HALTED** and keeps selling until it
   truly owns nothing, and only then drops back to PAPER.
7. **Cash-account safe:** it never re-spends same-day sale money, which avoids Schwab
   "good faith violations". In practice each dollar can be used for one day trade per day.
8. Real money only after every paper rule passes, you type `REAL MONEY`, `.env` says
   `LIVE_TRADING_ENABLED=true`, and prices come from Schwab.
9. Stop-loss per position (swing 7%, day 2%), daily loss limit, and a **kill switch** (desk
   down 15% from peak → sell everything, back to PAPER, halt).

**Whole shares only** (Schwab's API can't buy fractions). With $500 per desk, one position
is about $170 (swing) or $250 (day), so pricier stocks are skipped automatically.
`status` lists which ones.

## Where to look

- `data/trading_plan_swing.md` / `data/trading_plan_day.md`: the plans and their scorecards
- `data/aitrader.sqlite`: everything (opinions, trades, daily values, journal). Open it
  with [DB Browser for SQLite](https://sqlitebrowser.org).
- `config.yaml`: every knob, with comments

## Code map

```
run.py                 the commands above, including the autopilot schedule
aitrader/
  strategies.py        trading ideas for both desks (add yours here)
  brain.py             the local AI (walk-forward; never sees the future)
  features.py          indicators the AI learns from
  engine.py            decide_orders()/desk_orders(), used by backtest, paper AND live
  study.py             swing opinion grading + day shadow trading
  planner.py           picks each desk's strategy, writes the plan
  phases.py            rules for moving between phases (per desk)
  risk.py              sizing, stop-loss, limits, kill switch
  market_hours.py      open/close times incl. early-close days
  market_data.py       Yahoo or Schwab prices (daily + 5-minute), saved locally
  brokers/paper.py     fake-money broker (also used by backtests)
  brokers/schwab_broker.py  real orders via schwab-py, with shared-account protections
  schwab_api.py        Schwab login/connection
  storage.py           SQLite memory
  llm.py               optional Ollama write-ups
tests/                 run with: python -m pytest
```

**Add a strategy:** copy a class in `strategies.py` (set `style = "day"` for day trading),
change the rules, and add it to `all_strategies()`. It's studied, backtested and considered
for the plan automatically.

## Honest limitations (read these)

- **Day trading history is short.** Yahoo keeps only ~60 days of 5-minute prices (Schwab
  about 9 months). The bot saves every bar it downloads, so its history grows over time,
  but early day-desk backtests rest on thin evidence.
- **Swing stops in paper are checked every 5 minutes**; in LIVE a real stop order rests at
  Schwab. A big overnight gap can still blow through any stop.
- **Early closes are rule-based** (day after Thanksgiving, July 3, Christmas Eve). Check
  NYSE's calendar each year.
- **Yahoo data is unofficial** and can break. That's why real money requires Schwab data.
- **`schwab-py`'s last release was mid-2025.** If Schwab changes its API, swap in
  `schwabdev` (only `schwab_api.py` and `brokers/schwab_broker.py` need changing).
- **The stop-order and cash-balance code is tested against a fake Schwab**, not a real
  account. Before real money, run `python run.py trade --dry-run` and read the journal.
- **30 paper days is a small sample.** Passing is evidence, not proof.
- **Taxes:** gains on positions held a year or less are taxed as ordinary income, and the
  wash-sale rule can disallow losses when the bot re-buys within 30 days. Day trading
  triggers it a lot. Keep Schwab's 1099 and consider a tax pro.
