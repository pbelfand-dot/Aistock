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
                           with pretend money. No orders at all. Each desk also trades "in its
                           head" (swing: momentum, day: opening range breakout; config.yaml
                           study.in_its_head), and the app's Trades tab reports every trade.
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

**Stage 1 shortcut (your plan):** Setup → **Start Stage 1 paper trading** (or `python run.py
start-stage1`) skips steps 1–2 for the swing desk. It paper trades the `momentum` method right
away: the strongest stocks on the watchlist plus the top of the daily all-stocks scan (12-month
rise, skipping the latest month), only above their 200-day averages, and no new buys while SPY is
below its own. Pretend money only; the day desk keeps studying. The evidence is the 16-year test
in `research/history/RESULTS-methods.md`.

"Profitable" means your rule (see `config.yaml → promotion:`): over at least 30 trading days
of paper trading, the desk **made money and beat just holding SPY** over the same days, and never
dropped more than 10% from its best day. (A minimum number of closed trades and a profit factor
can be switched back on there; they're off because momentum trades rarely.) If it can't beat
SPY, buying SPY is the better deal.

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
7. **Later, when you're ready:** **Setup → Real money, Schwab, Webull and Claude.**
   - **Settings:** which broker gets real money, the most real money it may use (e.g. $50), the
     account type, and the paper amount. They're kept when the app updates.
   - **Charles Schwab:** paste the App Key, the Secret and the callback address, then **Open Schwab
     login**. Sign in, then paste the address your browser lands on (that page won't load; that's
     expected). Log in again at least once a week: Schwab's limit is 7 days.
   - **Webull:** apply on the Webull website (API Management → My Application; Webull reviews it in
     about 1–2 business days). Once approved, Generate Key and paste the App Key and App Secret, with
     **Paper** for Webull test-environment keys or **Real money** (a wrong pick is fixed by the test). Press
     **Test Webull**, then approve Kestrel in the Webull app within 5 minutes (Menu → Messages →
     OpenAPI Notifications → Check Now → the text-message code). The autopilot uses that approval each
     morning so it doesn't lapse (Webull drops it after 15 unused days). For now Kestrel only reads the
     Webull account; it doesn't trade there.
   - **Alpaca real-money keys:** saving them turns nothing on.
   - **Connect Claude** (Code or Desktop).

**Where your keys live:** `~/AITrader/.env`, on your Mac only. Updates never touch it. The same goes
for your Setup settings (`~/AITrader/my_settings.json`) and your Schwab and Webull logins (`~/AITrader/data/`).
Only deleting the AITrader folder removes them.

**It scans all US stocks every day, and reads the news.**
- **When:** after the close, the autopilot looks at every tradable US stock and ETF. With Alpaca
  keys it uses Alpaca's full list; without them, about 400 popular names.
- **What makes the list:** $3+ a share, actively traded, and in an uptrend. The list is ranked by
  the past year's rise, skipping the latest month: the one stock-picking method the research
  supported.
- **Where you see it:** Research & plans → *Stocks it likes*. Each stock shows when it joined, how
  long it has stayed, and how it has done since.
- **New listings** (under a year of history) go on a separate watch-only list.
- **How the swing desk uses it:** it considers the 30 strongest stocks it can afford (with fractional
  shares, any price; with whole shares, ones where a share fits a position), not the day desk's
  stocks, and holds up to 8. Its own rules and budget still decide every trade.
- **If a scan doesn't finish** (the Mac slept, an update restarted it, Alpaca refused too many
  requests), it tries again in 5 minutes, up to 3 times, and again the next morning if the list is
  old. The after-market report says when the list was last made, or why not.
- **Stocks in play (day desk):** the evening scan also keeps a pool of the busiest stocks the day
  desk could trade. At 9:35am it compares each one's first 5 minutes of trading with its usual first
  5 minutes (14-day average) and adds the top 10 (at least 1x usual, no danger news, not the swing
  desk's) to the day desk's list for that day. The report shows whether trades in them did better
  than trades in the fixed list (in_play.py, knowledge/36-stocks-in-play.md).
- **News:** it reads headlines from Alpaca's news feed (Benzinga, free with your keys), or Yahoo's
  without keys.
  - A stock with **danger headlines** in the last 3 days (share offering, bankruptcy, trading halt,
    delisting, fraud charges...) isn't bought.
  - Headlines show next to each stock, and the local AI can explain them.
  - **News never makes it buy.**
- **Switch either off** in Setup → Settings.

**It learns from its own trades.** Every finished trade (paper or real) is reviewed: which strategy
bought it, how it ended, and what the market was like when it bought (the S&P 500 above or below its
200-day average; calm or wild). From those reviews:
- **Under 12 finished trades:** nothing changes. That's too few to tell skill from luck.
- **A strategy losing so far:** it trades at **half size**.
- **A strategy clearly losing over 30+ trades:** it's **paused**, and the journal says so.
- **A market condition where its trades clearly lost (20+ trades):** no new buys while that
  condition holds.
- **It never gets bolder:** a winning streak doesn't raise the size.
- **Every lesson is rechecked after each trade,** so a wrong one fades away.
- **The lessons show in Research & plans** and go into the notes its local AI reads.
- **Its price-predicting model keeps learning too,** re-training on new market data on its own
  schedule.

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
already stops *idle* sleep, but **closing the lid puts a MacBook to sleep** unless you turn on:

**Setup → 2. Autopilot → Keep trading with the lid closed.** It asks for your Mac password once.
- **Plugged in:** the Mac stays awake with the lid closed, day and night. The autopilot keeps
  trading. A closed, idle MacBook uses a few watts.
- **On battery:** the Mac sleeps as usual. If the lid is closed, Kestrel puts it to sleep right away,
  so it never runs hot in a bag.
- **Backup:** it also sets a weekday 8:30am (New York time) wake-up in case the Mac fell asleep.
  Wake-ups with the lid closed aren't guaranteed, so plugged in and awake is the dependable setup.
- **What the password is for:** it adds one rule, `/etc/sudoers.d/kestrel-lid`, checked by `visudo`
  first. The rule lets Kestrel run exactly `pmset -a disablesleep 1`, `pmset -a disablesleep 0` and
  `pmset repeat cancel`, nothing else.
- **Sleeping it yourself:** while it's on and plugged in, Apple menu → Sleep does nothing. Turn it off
  first. Turning it off (or turning the autopilot off) lets the Mac sleep normally again.

Other ways: keep the lid **open** with the charger in, or use clamshell mode (lid closed with an
external monitor and power).

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
| Start Stage 1 | `start-stage1` | swing desk paper trades momentum now (skips the study month) |
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
8. **Fractional shares at Alpaca** (and in the simulation): parts of a share, at least $1 at a time,
   only for stocks Alpaca allows. Alpaca keeps fractional orders for one day only, so a swing position's
   overnight stop covers its whole shares and the bot checks the fraction itself every 5 minutes.
   **Schwab and Webull: whole shares only** (Schwab's API can't; Webull's isn't confirmed), so pricey
   stocks are skipped there (`status` lists which). Setup -> Settings -> Fractional shares turns it off.

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
