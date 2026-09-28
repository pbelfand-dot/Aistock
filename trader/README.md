# AI Trader for Charles Schwab

A small, readable bot that **studies the market for a month, writes a trading plan,
proves it with fake money, and only then trades real money**, capped at an amount you choose.

The "AI" is a machine-learning model that runs **on your own computer** (no paid API).
An optional local chatbot (Ollama) writes plain-English explanations. It never picks trades.

> Not financial advice. Most people who trade actively lose money. This bot's #1 job
> is to find out *safely* whether you have an edge, and to say "don't trade" if you don't.

---

## The journey (about 3 months before real money, at minimum)

```
 1. STUDY  (≥30 days)      Every trading day, each strategy writes down its opinion on
                           every stock. 5 trading days later the bot grades it.
                           No trades.
          │  python run.py plan
          ▼
 2. PLAN_REVIEW            Bot backtests every strategy on ~8 years of history, combines
                           that with the month's report card, and writes
                           data/trading_plan.md. It may honestly say "NO_TRADE".
          │  python run.py approve-plan   (you type YES)
          ▼
 3. PAPER  (≥30 trading    Trades the plan with fake money and real prices.
            days)
          │  python run.py promote        (every rule must pass, then you type REAL MONEY)
          ▼
 4. LIVE                   Real orders through Schwab, capped at live.max_capital.
                           Kill switch → back to PAPER automatically.
```

"Profitable" is defined in `config.yaml → promotion:`. By default, over at least 30
trading days and 20 closed trades the paper account must: make money, win ≥1.2× what it
loses, never drop more than 10%, **and beat just holding SPY**. If it can't beat SPY,
buy SPY instead. It's cheaper and less work.

## Setup

**1. Python 3.10+**
```bash
cd trader
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

**2. Start studying today.** No Schwab approval needed; it uses free Yahoo data:
```bash
python run.py backtest     # see how each strategy did historically
python run.py daily        # day 1 of the study month
python run.py status       # where am I?
```

**3. Optional: local LLM for write-ups.** Install [Ollama](https://ollama.com), then
`ollama pull qwen3:4b` (~2.5 GB; runs on a normal laptop). If it's not running, the bot
still works and uses a template write-up.

**4. Schwab developer access** (do this during the study month; approval takes days):
1. Have a Schwab brokerage account. **Strongly recommended: open a separate account just
   for the bot** so it can never touch your long-term investments.
2. Sign up at <https://developer.schwab.com> and request **Trader API – Individual**.
3. Dashboard → **Create App** → select **Accounts and Trading Production** and
   **Market Data Production**. Callback URL: `https://127.0.0.1:8182` (exactly; no trailing
   slash, and not `localhost`).
4. Wait until the app says **Ready For Use** ("Approved – Pending" doesn't work yet).
5. Put the App Key and Secret in `.env`, then run `python run.py schwab-login`.
   (On a computer without a screen: `python run.py schwab-login --manual`.)
6. Optional: switch `data.source` to `schwab` in `config.yaml`.

⚠️ **Schwab logins expire every 7 days, and there's no way around it.** Run
`python run.py schwab-login` weekly. `status` shows the days left. If it expires, the bot
stops trading (it fails safe).

## Run it every trading day

The bot is designed to run **once a day at ~3:45pm New York time** (15 minutes before the
close). Your computer must be on.

Mac/Linux (`crontab -e`):
```
CRON_TZ=America/New_York
45 15 * * 1-5  cd /path/to/Aistock/trader && .venv/bin/python run.py daily >> data/bot.log 2>&1
```
Windows: Task Scheduler → daily task at 3:45pm ET on weekdays running
`C:\path\to\Aistock\trader\.venv\Scripts\python.exe run.py daily`, with "Start in" set to the `trader` folder.

## Commands

| Command | What it does |
|---|---|
| `status` | Current phase, study report card, paper/live results, Schwab login days left, recent journal |
| `daily` | Today's job for the current phase (study always; trades in PAPER/LIVE) |
| `backtest` | Tests every strategy on history vs. buy-and-hold (safe, any time) |
| `plan` | After the study month: writes `data/trading_plan.md` |
| `approve-plan` | You approve the plan → paper trading starts |
| `promote` | Checks paper results against the rules → you confirm → LIVE |
| `trade --dry-run` | LIVE: shows exact orders it *would* send, sends nothing |
| `kill` | **Emergency:** cancel orders, sell the bot's positions, halt |
| `resume` | Un-halt after a kill (after you've looked at what happened) |
| `schwab-login` | Weekly Schwab login |

## Safety locks on real money

1. Can only reach LIVE by passing every paper rule **and** typing `REAL MONEY`.
2. `.env` must say `LIVE_TRADING_ENABLED=true`, or no real order is ever sent.
3. **Budget cap:** the bot's own checkbook starts at `live.max_capital`. It never spends more.
4. It only sells shares **it** bought, and checks against Schwab's records before each trading day.
5. Limit orders only (quote ± 0.2%); unfilled orders are cancelled after 60 seconds.
6. Stop-loss per position, daily loss limit, and a **kill switch** (down 15% from peak →
   sell everything, drop back to PAPER, halt).
7. Cash accounts: never spends sale money before it settles (avoids "good faith violations").

## Where to look

- `data/trading_plan.md`: the plan, with the full scorecard and why others were rejected
- `data/aitrader.sqlite`: everything (predictions, trades, daily values, journal).
  Open it with [DB Browser for SQLite](https://sqlitebrowser.org).
- `config.yaml`: every knob, with comments

## Code map

```
run.py                 the commands above
aitrader/
  strategies.py        trading ideas (add yours here)
  brain.py             the local AI (walk-forward; never sees the future)
  features.py          indicators the AI learns from
  engine.py            decide_orders() used by backtest, paper AND live; backtester; trading day
  study.py             daily opinions + grading
  planner.py           picks the strategy, writes the plan
  phases.py            rules for moving between phases
  risk.py              sizing, stop-loss, limits, kill switch
  brokers/paper.py     fake-money broker (also used by the backtest)
  brokers/schwab_broker.py  real orders via schwab-py
  schwab_api.py        Schwab login/connection
  market_data.py       Yahoo or Schwab prices
  storage.py           SQLite memory
  llm.py               optional Ollama write-ups
tests/                 run with: python -m pytest
```

**Add a strategy:** copy `TrendFollowing` in `strategies.py`, change the rules, add it to
`all_strategies()`. It's automatically studied, backtested and considered for the plan.

## Honest limitations (read these)

- **Stops are checked once a day.** An overnight gap or intraday crash can blow through
  the 7% stop. A resting stop order at Schwab would fix this; it's a good next upgrade.
- **Early-close days** (e.g. the day after Thanksgiving) aren't detected; the 3:45pm run
  may find the market already closed.
- **Whole shares only** (Schwab's API has no fractional shares). With a small budget, pricey
  stocks get skipped. That's why the default watchlist leans toward cheaper names and ETFs.
- **Yahoo data is unofficial** and occasionally breaks. Switch to `schwab` once approved.
- **`schwab-py`'s last release was mid-2025.** If Schwab changes its API and it breaks,
  swap in `schwabdev` (only `schwab_api.py` and `brokers/schwab_broker.py` need changing).
- **30 paper days is a small sample.** Passing is evidence, not proof. Start live small.
- **Taxes:** gains on positions held a year or less are taxed as ordinary income, and the
  wash-sale rule can disallow losses if the bot re-buys within 30 days. Keep Schwab's
  1099 and consider a tax pro.
