# AI Trader

A small, readable bot that **studies the market for a month, writes a trading plan,
proves it with paper money, and only then trades real money**, capped at $1,000.
It trades through **Alpaca** now, and **Charles Schwab** later (switch with one setting).

It trades **two ways** ("desks"), and each one has to earn trust on its own:

| Desk | Style | When it decides | Money |
|---|---|---|---|
| **swing** | holds days to weeks | once a day, 3:45pm New York time | $500 |
| **day** | in and out the same day, never overnight | every 5 minutes | $500 |

The "AI" is a machine-learning model that runs **on your own Mac** (no paid AI service).
It learns only from the past, and a test proves it can't peek at future prices.

> Not financial advice. Most people who trade actively lose money, and day traders do worst
> of all. This bot's #1 job is to find out *safely* whether a strategy has an edge, and to say
> "don't trade" if it doesn't.

---

## The journey (each desk separately; about 3 months before real money, at minimum)

```
 1. STUDY  (≥30 days)      Swing: every strategy writes down an opinion on each stock daily,
                           graded 5 days later. Day: every strategy "shadow trades" each day
                           with pretend money. No orders at all.
          │  menu: Write the trading plans
          ▼
 2. PLAN_REVIEW            Backtests every strategy on years of history, adds the study month,
                           writes data/trading_plan_<desk>.md. May honestly say "NO_TRADE".
          │  menu: Approve a plan   (you type YES)
          ▼
 3. PAPER  (≥30 trading    Trades the plan in your Alpaca PAPER account: real order handling,
            days)          fake money.
          │  menu: Promote a desk to REAL money   (every rule must pass, then you type REAL MONEY)
          ▼
 4. LIVE                   Real orders, capped at the desk's budget. Kill switch → back to PAPER.
```

"Profitable" means (see `config.yaml → promotion:`): over at least 30 trading days and 20
closed trades, the desk made money, won at least 1.2× what it lost, never dropped more than
10%, **and beat just holding SPY**. If it can't beat SPY, buying SPY is the better deal.

## Setup on a Mac (the easy way)

1. **Download the app** from the [GitHub page](https://github.com/pbelfand-dot/Aistock) (big link at
   the top), unzip it, and drag **AI Trader** into Applications.
2. **First open:** macOS will block it (it isn't from the App Store). Open **System Settings →
   Privacy & Security**, scroll down, click **Open Anyway**. (Or in Terminal:
   `xattr -dr com.apple.quarantine "/Applications/AI Trader.app"`.)
3. A Terminal window opens and installs Python plus the bot's libraries (about 2 minutes, once).
   Then you get the **menu**. From then on, opening the app just opens the menu.
4. **Alpaca keys** (free, about 5 minutes):
   - Sign up at <https://app.alpaca.markets>. Paper trading needs no money and no approval.
   - The default paper account holds $100,000. Make a new paper account with **$1,000** so paper
     behaves like your real account (the bot caps itself at $1,000 either way).
   - In the paper account: **API Keys → Generate**. Menu → **Edit my keys**, paste them as
     `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY`, save, close TextEdit.
   - Menu → **Check my Alpaca keys** should say "connected".
5. Menu → **Keep the autopilot running in the BACKGROUND**. Done: it studies every trading day,
   starts when you log in, and restarts itself if it crashes.

Your files live in **~/AITrader** (your home folder): `.env` = keys, `config.yaml` = settings,
`data/` = the bot's memory, plans and logs (`data/autopilot.log`).

**Updating:** download the new zip and open it. Your keys and data stay. If the settings file
changed, your old one is saved as `config.yaml.before-<version>` and the menu tells you.

### Keep the Mac awake
The bot only works while the Mac is **awake, online and plugged in**. The background autopilot
already stops *idle* sleep, but **closing the lid still puts a MacBook to sleep**. So:
- keep the lid **open** and the charger in, **or**
- use clamshell mode (lid closed with an external monitor and power), **or**
- use the free app **Amphetamine** with its closed-display option.

On a MacBook also check **System Settings → Battery → Options → "Prevent automatic sleeping on
power adapter when the display is off"**.

If it sleeps anyway, the day desk sells any leftovers the moment it wakes, the journal flags a
missed swing decision, and every real position has a **stop-loss order resting at the broker**.

## Connect Claude (MCP)

- **Claude Code:** menu → **Connect Claude Code**, then start a new Claude Code session and type
  `/mcp` to see the connections. They work in every project.
- **Claude Desktop:** menu → **Connect Claude Desktop**, then quit Claude Desktop (Cmd+Q) and reopen it.

Then ask things like *"how is my bot doing?"*, *"why did it sell KO?"*, *"show me the day desk's plan"*.

| Connection | What Claude can do | What it can't |
|---|---|---|
| **ai-trader** (this bot, `mcp_server.py`) | see status, journal, plans, positions, results, your Alpaca account; **pause** trading | buy, sell, resume, approve or go live |
| **schwab** ([schwab-mcp](https://github.com/jkoelker/schwab-mcp), community, MIT) | read quotes, accounts, positions, orders | trade (it's set up **read-only**) |

There's no official Schwab MCP server; `schwab-mcp` is the most actively maintained community
one. It's only added once your Schwab keys are in `.env`, reuses the bot's Schwab login, and
refuses logins older than 5 days, so use menu → **Log in to Schwab** about every 5 days.
Your Schwab key and secret are written into Claude Desktop's settings file on your Mac.

By hand in Terminal (Claude Code):
`claude mcp add --scope user ai-trader -- ~/AITrader/.venv/bin/python ~/AITrader/mcp_server.py`

## Setup without the app (any computer, Python 3.11+)
```bash
cd trader
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your keys into .env
python run.py menu            # or: python run.py check / autopilot / status ...
```

## The menu (and the matching commands)

| Menu item | Command | What it does |
|---|---|---|
| Status | `status` | each desk's phase, report card, results, journal |
| Check my keys | `check` | tests Alpaca/Schwab keys and price data |
| Start the autopilot | `autopilot` | runs everything, every trading day |
| Background autopilot on/off | | same, as a Mac service (starts at login) |
| Backtest | `backtest` | every strategy vs. buy-and-hold, on history |
| Write the trading plans | `plan` | after the study month |
| Approve a plan | `approve-plan` | you say YES → that desk starts paper trading |
| Promote to real money | `promote` | checks the paper rules → you type REAL MONEY |
| Connect Claude Code / Desktop | | adds the MCP connections above |
| Log in to Schwab | `schwab-login` | only once you use Schwab |
| EMERGENCY | `kill` | cancels the bot's orders, sells everything it owns, halts |
| Resume | `resume` | un-halt after you've looked at what happened |

`python run.py trade --desk day --anyway` runs one paper cycle for testing;
`trade --dry-run` shows the exact real orders it *would* send.

## Safety rules (built in, tested)

1. **Budget cap:** each desk has its own checkbook ($500). It never spends more, and never more
   than the cash the broker says is available. **It never borrows.**
2. **Hands off your stuff:** it only sells shares **it** bought, never buys a stock you already
   own in that account, and only cancels its **own** orders. With Alpaca every bot order carries
   an `aitrader-` tag.
3. **Never loses track of an order:** it only forgets an order once the broker confirms it's
   finished. Every fill is saved the moment it happens. With Alpaca the order is written down
   *before* it's sent, so even a dropped connection can't create a mystery order.
4. **Resting stop-loss at the broker** for every live/paper-broker position (swing 7%, day 2%).
   If a sell fails, the stop goes back on. It never sells while an old stop might still be live.
5. **Urgent exits** (stop-loss, the day desk's end-of-day sell, emergency) use market orders.
   After a kill or kill switch the desk keeps selling until it truly owns nothing.
6. **Real money only** after every paper rule passes, you type `REAL MONEY`, `.env` says
   `LIVE_TRADING_ENABLED=true`, and prices are real-time (Alpaca or Schwab data).
7. Daily loss limit (3%) and a **kill switch** (desk down 15% from its best day).
8. **Whole shares only**, so with $500 per desk, pricey stocks are skipped automatically
   (`status` lists which).

**Alpaca notes:** every Alpaca account is a "margin" type (there are no cash accounts), but
under $2,000 it can't borrow, and sale money is usable right away (no good-faith violations).
Alpaca dropped the old $25k day-trading rule on June 4, 2026.

## Where to look
- `data/trading_plan_swing.md` / `data/trading_plan_day.md`: the plans and scorecards
- `data/aitrader.sqlite`: everything (opinions, trades, daily values, journal). Open it with
  [DB Browser for SQLite](https://sqlitebrowser.org).
- `data/autopilot.log`: what the background autopilot printed
- `config.yaml`: every knob, with comments

## Code map
```
run.py                     the menu and every command, incl. the autopilot schedule
mcp_server.py              lets Claude see (and pause) the bot
aitrader/
  strategies.py            trading ideas for both desks (add yours here)
  brain.py / features.py   the local AI (walk-forward; never sees the future)
  engine.py                decide_orders()/desk_orders(): same rules in backtest, paper and live
  study.py / planner.py    the study month and the plans
  phases.py / risk.py      phase rules; sizing, stops, limits, kill switch
  market_data.py           Alpaca / Yahoo / Schwab prices (daily + 5-minute), saved locally
  market_hours.py          open/close times incl. early-close days
  brokers/live.py          the safety rules for real broker accounts (shared)
  brokers/alpaca_broker.py, brokers/schwab_broker.py   thin translators for each broker
  brokers/paper.py         pretend broker for backtests (and paper without Alpaca keys)
  mac_service.py           the background autopilot on a Mac (launchd)
  claude_setup.py          "Connect Claude Desktop"
tests/                     python -m pytest (75 tests, no internet needed)
```
**Add a strategy:** copy a class in `strategies.py` (`style = "day"` for day trading), change the
rules, add it to `all_strategies()`. It's studied, backtested and considered automatically.

## Honest limitations
- **Free Alpaca data is the "IEX" feed**: real-time, but only one exchange's trades (about 2–3%
  of volume). Prices track the market closely; volumes are smaller. History starts mid-2020.
  Alpaca's paid plan (`alpaca_feed: sip`) sees every exchange.
- **Alpaca paper fills are simplified** (no market impact or slippage), so paper looks a bit
  better than reality. That's why real money starts small.
- **Early closes are rule-based** (day after Thanksgiving, July 3, Christmas Eve).
- **The app isn't signed by Apple** (that costs $99/year), hence the "Open Anyway" step.
- **30 paper days is a small sample.** Passing is evidence, not proof.
- **Taxes:** short-term gains are taxed as ordinary income, and the wash-sale rule can disallow
  losses when the bot re-buys within 30 days (day trading triggers it a lot). Keep the broker's
  1099 and consider a tax pro.
