# Kestrel (formerly AI Trader)

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
   the top), unzip it, and drag **Kestrel** into Applications.
2. **First open:** macOS will block it (it isn't from the App Store). Open **System Settings →
   Privacy & Security**, scroll down, click **Open Anyway**. (Or in Terminal:
   `xattr -dr com.apple.quarantine "/Applications/Kestrel.app"`.)
3. The app's window opens. **The first time only**, a Terminal window also opens to install
   Python and the bot's libraries (about 2 minutes). Then the dashboard appears with the **Setup**
   screen on top. The Setup screen is always one click away: the **Setup** button.
4. **Setup → 1. Connect your Alpaca paper account** (free, about 5 minutes):
   - Sign up at <https://app.alpaca.markets>. Paper trading needs no money and no approval.
   - The default paper account holds $100,000. Make a new paper account with **$1,000** so paper
     behaves like your real account (the bot caps itself at $1,000 either way).
   - In the paper account: **API Keys → Generate**. Paste the Key ID and Secret into Setup and
     press **Save and test**. It should show two green checks. The keys are saved only on your Mac
     (`~/AITrader/.env`). Live (real-money) keys are refused here on purpose.
5. **Setup → 2. Autopilot → Turn on.** Done: it studies every trading day, starts when you log
   in, and restarts itself if it crashes (closing the app doesn't stop it).
6. **Setup → 3. What happens next** tells each desk's step in plain English.
7. **Later, when you're ready:** **Setup → Real money, Schwab and Claude.**
   - **Settings:** which broker gets real money, the most real money it may use (e.g. $50), the
     account type, and the paper amount. They're kept when the app updates.
   - **Charles Schwab:** paste the App Key, the Secret and the callback address, then **Open Schwab
     login**. Sign in, then paste the address your browser lands on (that page won't load; that's
     expected). Log in again at least once a week: Schwab's limit is 7 days.
   - **Alpaca real-money keys:** saving them turns nothing on.
   - **Connect Claude** (Code or Desktop).

**Where your keys live:** `~/AITrader/.env`, on your Mac only. Updates never touch it. The same goes
for your Setup settings (`~/AITrader/my_settings.json`) and your Schwab login (`~/AITrader/data/`).
Only deleting the AITrader folder removes them.

**Good faith violations (cash accounts, e.g. Schwab).** Buying with money from a sale that hasn't
settled yet, then selling before it settles, is a good faith violation. Three in 12 months and Schwab
limits the account to settled cash for 90 days. So in a cash account the bot **only ever spends
settled money**:
- Sale money settles one business day later (T+1). Bank holidays like Columbus Day and Veterans Day
  don't count as business days.
- Any position that was somehow bought with unsettled money is held until that money settles. Only
  your typed emergency stop may sell it early, and that's counted and shown in Setup.
- Paper trading follows the same rules, so the paper results match what real money would do.
- Schwab counts as a cash account unless you set Margin. Alpaca covers unsettled money itself, so
  violations don't apply there.

Your files live in **~/AITrader** (your home folder): `.env` = keys, `config.yaml` = settings,
`data/` = the bot's memory, plans and logs (`data/autopilot.log`).

**Updating: automatic.** While the app is open (it can sit minimized), it checks its download page
when it opens and once a day. When there's a newer version, it downloads it, checks the download's
fingerprint and signature, swaps itself and restarts. Your keys and data stay, and a running
background autopilot restarts on the new version.
- **Paper trading only:** it updates by itself.
- **Real money involved** (switched on in `.env`, a desk in LIVE, or real shares owned): it
  **asks you first**, so new code never takes over real money unannounced.
- **Menu:** Kestrel → **Check for Updates…** checks right now. **Update Automatically** turns
  the automatic part off (then it always asks).
- **It must live in your Applications folder** to replace itself.
- **Updates that need new libraries** open the Setup window, as on the first install.
- **Settings:** if the settings file changed, your old one is saved as
  `config.yaml.before-<version>` and the menu tells you.
- **Versions before 1.0.13** can't update themselves: download the zip once more by hand.

## The app (your account, like a brokerage)

**Kestrel** is a normal Mac app: its own window, Dock icon and menus. It's written in Swift and
shows the dashboard with Apple's WebKit (the engine inside Safari), so there's no browser and no
web server: when the window needs numbers, the app asks the bot directly
(`python -m aitrader.app_api`, see `aitrader/app_api.py`).

- **Summary:** account value, today's change, cash, total return, worst drop, win rate; a chart of
  your account vs. the S&P 500 (same starting amount; hover or use the arrow keys for exact values,
  or click **Table**); each desk's progress (Study → Plan → Paper → Live); the watchlist.
- **Positions:** what the bot owns, gain/loss, and each stop-loss (✓ = resting at the broker).
- **Activity:** every buy and sell with the bot's reason. **Research & plans:** the study report
  cards and plans. **Journal:** what it did, and why.
- Switch between the **Paper** and **Live** account at the top. Light and dark mode follow your Mac.
- Menus: **View → Refresh** (⌘R), **View → Show Demo Data** (⌘D: made-up prices run through the
  bot's real code, so you can see everything before it has traded), **Kestrel → Setup Menu** (⌘,:
  the full Terminal menu).

Two buttons, both ask first:
- **Pause:** no new trades. Nothing is sold now; stop-losses keep protecting what it owns, and the
  day desk still sells before the close. **Setup → Resume trading** turns it back on.
- **Emergency stop:** you type `SELL EVERYTHING`; it cancels the bot's orders, sells everything
  the bot owns (never your own stocks) and halts both desks.

Approving plans, going live and Schwab stay in the full Setup menu (Terminal), where you type a
confirmation.
The app only reads the bot's own files (no broker keys). It's the bot's own design, not a copy of
Schwab's or Alpaca's: it never asks for a broker login. If something goes wrong, the bot's
messages are in `data/app.log`.

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
| **ai-trader** (this bot, `mcp_server.py`) | see status, journal, plans, positions, results, your Alpaca account; **pause** trading (no new trades; stop-losses keep working) | buy, sell, resume, approve or go live |
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
| Open the Kestrel app | `dashboard` | opens the app window above |
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
| Resume | `resume` | un-pause / un-halt (after an emergency stop: once it's sold out) |

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
  dashboard.py, web/       what the app's window shows; app_api.py = how the app asks the bot;
                           demo.py = the demo data
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
  claude_setup.py          "Connect Claude Code / Desktop"
tests/                     python -m pytest (84 tests, no internet needed)
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
