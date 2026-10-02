# Kestrel: everything the assistant should know

Built from the app's own documentation by datasets/kestrel_chat/build.py. When the app changes, build it again.


---

<!-- from README.md -->

# Aistock

## ⬇️ [Download Kestrel for Mac](https://github.com/pbelfand-dot/Aistock/releases/latest/download/Kestrel-mac.zip)

**Kestrel** (formerly "AI Trader") is an AI trading bot for **Alpaca** (now) and **Charles Schwab**
(later). It studies the market for a month, writes a plan, proves it with paper money, and only
then trades real money, capped at $1,000. GitHub builds and tests it automatically every time the
code changes.

### Install (about 3 minutes)
1. Click the download link above and open **Kestrel-mac.zip** (it unzips itself).
2. Drag **Kestrel** into your **Applications** folder. It must live there to update itself.
3. Open it. The first time, macOS blocks apps that aren't from the App Store:
   - Click **Done**, then open **System Settings → Privacy & Security**, scroll down, and click
     **Open Anyway** next to "Kestrel" (you may need your Mac password).
   - Or paste this in Terminal instead:
     `xattr -dr com.apple.quarantine "/Applications/Kestrel.app"`
4. **The first time only**, a Terminal window installs Python and the bot's libraries (about
   2 minutes). Then the dashboard appears with the **Setup** screen on top.
5. In **Setup**: paste your Alpaca paper keys → **Save and test** → **Autopilot: Turn on** →
   **Start Stage 1 paper trading** (pretend money; it decides 15 minutes before each close).

### The app
**Kestrel** is a normal Mac app: its own window, Dock icon and menus (no browser, no web server).
- **Its window** is a brokerage-style dashboard: your account value vs. the S&P 500, positions,
  every trade and why, each desk's progress, the watchlist, and **Pause** / **Emergency stop**
  buttons.
- **Thinking** (a tab) shows what the bot is thinking, live: what it's doing this moment (getting prices,
  scoring stocks, the team going over the orders), and for each desk its latest check: the top scores next
  to the buy and sell lines, what it decided and why (or why not), the team's notes (Scout, Analyst,
  Trader, Risk), how far each holding is from its stop-loss, and every check so far today. It refreshes
  every 5 seconds, also on the phone screen.
- **News and data sources** (Setup → AI & news): SEC filings for what it owns or considers (free; the SEC asks for
  your email), with links on each stock card; serious ones (bankruptcy, delisting, restated financials) stop
  it buying. The dates of CPI, the jobs report and Fed decisions (a free FRED key), with a countdown; buys on
  those days are tagged so it learns whether they lose. Each stock card and the report also show **why it
  moved**: the move next to the latest headlines and filings.
- **Weekend practice** (Saturday and Sunday, on or off in Setup → Settings): Kestrel replays real past
  trading days from the prices saved on your Mac, fast (about 30 minutes per day), through the desks' own
  rules, and runs a crypto experiment with $500 of pretend money at live prices. Watch it in the Thinking
  tab. It's practice only: it never counts toward Stage 1, real money, or what the desks learn.
- **Trades** (a tab) shows every trade: what it spent, what it got back, the gain or loss in $ and %,
  win or lose, each day's % change, and the totals vs. the S&P 500. It works the same for all three
  accounts (pick one at the top of the Summary tab): *In its head* (pretend trades while a desk
  studies), *Paper* and *Real money*.
- **After-market report** (top of the Journal tab), written about 25 minutes after each close. For each
  desk it covers:
  - what it traded and why, and how that went;
  - what it was thinking: its top picks and why it didn't buy more;
  - what it learned from its own trades;
  - how the strategies it compares are doing;
  - changes to its stock list, and what's next.
  It's also saved in `~/AITrader/data/reports/`, and you can print it with `python run.py report`.
- **Your phone** (Setup → Your phone):
  - **Pushover push alerts.** Install [Pushover](https://apps.apple.com/app/id506088175) (free for 30
    days, then a one-time $4.99 per platform; sending is free up to 10,000 messages a month). Paste
    your User Key and the API Token of an application named Kestrel
    ([pushover.net/apps/build](https://pushover.net/apps/build)) into Setup. Every buy and sell, the
    after-market summary and anything urgent arrive as push notifications. A real-money kill switch
    or emergency stop repeats every minute until you open it. Near the monthly limit, only urgent
    alerts go out. Pushover only delivers alerts; commands stay on Telegram.
  - **Telegram alerts and commands.** Your own private bot messages you every buy and sell, the
    after-close results and the after-market report. Send it `/status`, `/trades`, `/report`,
    `/pause`, `/resume`, or `/kill SELL EVERYTHING`. It only answers the phone you paired with the
    code from Setup.
  - **The Kestrel screen on your iPhone.** It works over Tailscale, a free private network between
    your own devices. It's served only on the Mac's Tailscale address and needs Kestrel's access key.
    Add it to your Home Screen and it opens like an app. Keys and settings stay on the Mac.
- **Local AI** (Setup → AI & news): a free AI on your Mac writes the plain-English parts (the plan, the
  report's summary, the team's notes). It never decides trades and nothing leaves the Mac. Install
  [Ollama](https://ollama.com/download) and Kestrel downloads Google's Gemma 4 12B (about 8 GB) by itself.
  A Mac with less than 16 GB of memory uses the small Qwen3 4B instead, so trading never slows down.
- **View → Show Demo Data** shows it with made-up prices right away.
- **Setup** (the button) has a sidebar of sections: **Start here** (what's connected and what happens next),
  **Autopilot**, **Brokers & keys**, **Your phone**, **AI & news**, **Settings** and **More**. Green dots are set up,
  amber ones need you.
- **Stage 2: TJR's model** (day desk). It waits for a sweep below a low, a break back up, then buys
  the pullback into the gap, 9:35-11:30am, with the hourly trend. The day desk practices it in its
  head. A weekly history test on your Mac's 5-minute data compares it with random buys; once it
  passes, **Setup → Start here → Start Stage 2** paper trades it next to Stage 1. Results are in Research.
- **The team.** Every decision passes through five agents, each writing a short note: **Scout** (the
  facts), **Analyst** (what agrees and what conflicts), **Trader** (the tested strategy's orders),
  **Risk** (checks each buy) and **Reviewer** (after the close). The notes are in the after-market
  report. The rules still decide the trades. The Scout and Analyst also note today's stocks in play.
- **Stops sized to each stock (day desk).** Each stock's stop is half its usual daily range (14-day
  ATR), between 1% and 5%, so a jumpy stock in play gets room and a calm one a tight stop. A wider
  stop means a smaller position: no trade can lose more than 0.66% of the desk at its stop (the old
  33% position with a 2% stop), so nothing risks more than before. The swing desk keeps its tested 7% stop.
- **No swing buys right before earnings.** A report can jump a stock 10-20% overnight, past its stop.
  The swing desk doesn't open a position within 3 trading days of a report (dates from Yahoo, each
  morning); what it owns is kept. The honest trade-off: stocks have on average done slightly better
  around earnings, so this gives up a little of that for fewer big surprise losses. Setup -> Settings
  turns it off.
- **Mistakes: fine once, not twice.** Every buy is written down with its situation (the stock, in
  play or the fixed list, under $5, the first 30 minutes or after 2pm, chasing a stock already up a
  lot, moving with one it owns, option bets against it). When the same situation keeps losing (the
  same stock 3+ times with at most 1 win, or any situation clearly losing over 8+ trades in the last
  60 days), the Risk agent skips new buys in it and the journal says so. A lesson that fades and
  then loses again comes back at the first loss. Lessons learned while practicing carry into paper
  and real money. They only ever make it more careful, and never block a sale.
- **P&L calendar** (Trades tab): each weekday of the month with the money made or lost on trades that
  finished that day (or switch to the account value's daily change), how many trades and how many won,
  and each week's total. Deeper color = a bigger day; blue is a gain and red a loss (readable with
  color-blindness), and every day shows its signed amount. Hover for details, click a day for its trades,
  ‹ › for other months. Works for in its head, paper and real money.
- **Click any stock symbol** (watchlist, positions, trades, activity, the stock list) to see what it
  is: the company's name, what it does, its sector, industry and size (Alpaca and Yahoo Finance,
  looked up once a month), and what Kestrel knows about it: which lists it's on and why, if it's in
  play today, what each account holds, its trades, its latest score, news and danger headlines, and
  any mistake it won't repeat with it. It works on the phone screen too.
- **Scanning the market.** Every evening it checks all US stocks (a quick look at every one, then a
  full year of prices for the actively traded ones). The swing desk considers the 30 strongest it can
  afford. At 9:35am the day desk adds today's **stocks in play**: the busiest stocks whose first 5
  minutes traded far more than usual (relative volume), minus any with danger news. The after-market
  report says whether the scan worked, and whether day trades in stocks in play did better than the
  fixed list. The day desk also compares the research version of the breakout (5-minute range, long
  only).
- **Options-gap watcher** (Research tab, testing only). After each close it flags stocks whose option
  bets disagree with the price (calls piling up while the price is flat, or the reverse), using
  Alpaca's free data, and grades each flag 5 days later against the S&P 500. It never trades.
- **Lid closed** (Setup → 2. Autopilot → "Keep trading with the lid closed"): while plugged in, the
  Mac stays awake with the lid closed and keeps trading. On battery it sleeps as usual, so it never
  runs hot in a bag. It asks for your Mac password once.
- **Webull** (Setup → "Real money, Schwab, Webull and Claude"): paste the App Key and App Secret
  from Webull's API Management page once Webull approves your application, and pick **Paper** for
  Webull test-environment keys or **Real money** (Test Webull switches it if you pick wrong). Press **Test Webull**,
  then approve Kestrel in the Webull app within 5 minutes. To **paper trade at Webull**: Setup →
  Settings → "Paper trading happens at: Webull" (needs the paper keys, approved). Real money at Webull
  needs its real-money keys, "Broker for real money: Webull", and the same locks as Alpaca and Schwab
  (paper results first, LIVE_TRADING_ENABLED, the typed OK). Every order is a limit order with a
  resting stop, tagged "kst" so Kestrel never touches your own orders. Webull accounts are treated
  as cash accounts (settled money only) unless you set the account type.
- **Kestrel → Setup Menu** (⌘,) opens the full Terminal menu (plans, real money, Schwab).

![The Kestrel app (demo data)](docs/dashboard.png)

It's the bot's own design, not Schwab's or Alpaca's: it never shows or asks for your broker
login, and it can't buy anything. Closing the app doesn't stop the background autopilot.

Everything lives in the **AITrader** folder in your home folder (your keys, settings, and the
bot's memory).

**Updates are automatic.** While the app is open, it checks once a day and when it opens. Paper
only: it updates by itself. Real money involved: it asks first. Your keys and data stay.

### Connect Claude
Menu → **Connect Claude Code** (or **Connect Claude Desktop**). Claude can then see the bot
(status, trades, plans) and pause it, and read your Schwab account once you add Schwab. It can't trade.

### What's in this repo
- [`trader/`](trader/): the bot. [Full guide →](trader/README.md)
- [`mac/`](mac/): the Mac app (a Swift window, `mac/app/main.swift`) and how it is built
- `backend/`, `frontend/`: the earlier stock-suggestion web app

> Not financial advice. Most people who trade actively lose money. The bot's first job is to
> find out safely whether a strategy has an edge, and to say "don't trade" if it doesn't.


---

<!-- from trader/aitrader/knowledge/00-how-to-use.md -->

# Kestrel's background knowledge (read this first)

You are the local AI inside Kestrel, a trading bot that runs on the owner's Mac. These notes give
you the background: the owner's plan, the hard safety rules, what the research found, and what was
learned from TJR's trading videos.

How to use them:
- **You explain and write; you never decide trades.** Trades come only from coded rules that were
  tested on history and then paper-traded. If a note describes an idea that isn't tested yet, say so.
- **Never invent numbers.** Use the numbers in the data you're given and in these notes. If
  something isn't known, say it isn't known.
- **Claims aren't facts.** Profits in video titles or a trader's words are claims until fills prove them.
- **Safety rules beat everything else.** If a plan would break one, say so plainly.
- **Write plainly.** Short sentences for someone who isn't a trader.


---

<!-- from trader/aitrader/knowledge/10-safety-rules.md -->

# Hard safety rules (always true)

- **Never borrows.** It spends only cash, and never more than the real-money cap set in Setup
  (planned: $50 per broker).
- **Real money needs three locks:**
  - the desk earned it: study, then plan, then paper results that pass;
  - the owner typed the confirmation;
  - `LIVE_TRADING_ENABLED=true` is set on the Mac.
- **Emergency stop:** the owner types SELL EVERYTHING; the bot sells what it owns and halts.
  **Pause:** no new trades; stop-losses still protect positions.
- **Stop-losses** rest at the broker, so a sleeping laptop can't stop a falling position from being sold.
- **Good faith violations (cash accounts, e.g. Schwab).**
  - What one is: buying with money from a sale that hasn't settled yet, then selling before it
    settles. Three in 12 months and Schwab restricts the account for 90 days.
  - The bot spends settled money only. Sale money settles T+1 (one business day). Bank holidays
    such as Columbus Day and Veterans Day don't count.
  - A position bought with unsettled money (it shouldn't happen) is held until the money settles.
    Only the typed emergency stop may sell it early, and that's counted.
  - With $50 at Schwab, this means about one full round trip per day at most.
- **Alpaca:** it covers unsettled money itself, so there are no good faith violations there. It
  dropped the pattern-day-trader limit in 2026 (FINRA retired the rule).
- **Fractional shares:** Alpaca (and the simulation) buy parts of a share, at least $1 at a time, only
  for stocks Alpaca allows; a swing position's overnight stop covers its whole shares and the bot watches
  the fraction itself. Schwab's API trades whole shares only (with $50, only stocks under about $50 fit);
  Webull's fractional orders aren't confirmed, so Webull gets whole shares too. The $50 real-money test
  starts at Alpaca.
- **Schwab login lasts 7 days.** The owner logs in again from Setup; an expired login means no Schwab trading.
- **Keys and settings live only on the Mac** (`~/AITrader`) and survive updates.


---

<!-- from trader/aitrader/knowledge/20-the-plan.md -->

# The owner's plan

1. **Stage 1: paper trading, 30 trading days, "free ball".**
   - Trade what the research says works, and build a growing list of stocks the bot likes, from
     niche names to big ones.
   - Method (`momentum`, swing desk): rank every stock on the list (the watchlist plus the 30
     strongest stocks from the daily all-stocks scan that it can afford) by its 12-month return, skipping the latest month. Buy from
     the top 20% while the stock is above its 200-day average; sell when it drops out of the top
     half or below its 200-day average. No new buys while SPY is below its 200-day average.
   - At most 8 positions of up to 12.5% of the desk's money each, 7% stop-loss. Fractional shares at
     Alpaca and in the simulation (so a pricey stock can be bought in part); whole shares at Schwab and Webull.
     (Was 3: holding 8 trades about 3x as often with about the same return and a smaller worst drop
     in the bot's own 2011-2026 backtest. The scan hands it the 30 strongest stocks it can afford.)
     With whole shares (Schwab, Webull), stocks too expensive for one share are skipped.
   - The owner starts it with **Start Stage 1 paper trading** in Setup (or `python run.py
     start-stage1`). It skips the study month; the day desk keeps studying.
2. **Stage 2: paper, 30 trading days:** Stage 1 plus TJR's model on the day desk (`tjr_model`,
   tjr.py).
   - The rules: only with the stock's hourly trend up (a higher hourly low, closing above it).
     Wait for a sweep below a low where stops sit (yesterday's low or a 5-minute swing low), then a
     5-minute close above the last swing high. Buy the pullback into the gap that move left,
     9:35-11:30am. Stop below the sweep minus 1/4 of the 5-minute ATR, target 2R, one trade per
     stock a day, long only.
   - The day desk practices it in its head now.
   - A weekly history test on the Mac's own 5-minute data must pass before it paper trades: 30+
     trades, a profit factor of 1.15+, making money, and a better profit factor than random buys
     with the same stop and target.
   - Then the owner starts it: Setup -> Start Stage 2.
3. **Real money:** $50 at Alpaca and $50 at Schwab (Webull can be the real-money broker too, later).
   More only if it makes money. Paper trading can run in Alpaca's or Webull's paper account, or be
   simulated on the Mac (Setup -> Settings -> Paper trading happens at).

**Pass rule the owner set (this is what `promote` checks):** over at least 30 trading days of
paper trading, make money and beat SPY over the same days, without dropping more than 10% from
the best day. No minimum number of trades. Then the owner still confirms by hand.
- Caveat from the research: over any 30 trading days, even the best method did that only about
  6 times in 10 (58%), and momentum with the trend filter about half the time (49%).
- So a single stage can catch a broken method, but can't prove a good one.

**Reports the owner sees (Trades tab):** every trade with what was spent, what came back, the gain
or loss in $ and %, win or lose; each day's % change; and the totals vs SPY. The same report
exists for three accounts: "in its head" (a studying desk trades with pretend money on this Mac:
swing = momentum, day = TJR's model), paper, and real money. After each close the
journal gets one line per account with today's result and the running totals.

**After-market report (every trading day, ~25 minutes after the close):** per desk, it covers:
- what it traded and why, and the result;
- its thinking at the last check: its top scores and why it didn't buy more;
- its lessons;
- how the strategies it compares are doing;
- its stock-list changes, and what's next.
When the local AI is on, it writes a short plain-English summary at the top, using only the
report's facts. The report is saved as data/reports/after-market-<date>.md.

**The owner's phone:**
- **Telegram (phone.py):** alerts for trades, the daily results, the after-market report and anything
  urgent. It answers /status /trades /report /pause /resume, and `/kill SELL EVERYTHING` only with
  that exact phrase.
- **Tailscale (phone_screen.py):** the Kestrel screen, with watching and safety buttons only.
- Keys and settings are never changed from the phone.

**Where the code is now:** Stage 1 is a button. Otherwise each desk still goes study (30 days) →
plan review → paper → live. Real money always needs the promotion rules to pass and the owner's
typed confirmation.


---

<!-- from trader/aitrader/knowledge/30-research-findings.md -->

# What 16 years of history showed (2011–2026)

**Setup of the test:**
- A $1,000 account, buying only, trading at the next day's open, with costs.
- Funds were real the whole time, so those results are trustworthy.
- The stock list only holds today's survivors, which flatters stock picking: buying all of them
  equally made 17.6%/yr, against 11.6% for the real equal-weight S&P fund (RSP).

**Funds (trustworthy):**
- Holding SPY: 14.0%/yr, worst drop −33.7%.
- Holding QQQ: 18.9%/yr (partly hindsight: tech's decade).
- SPY 200-day trend rule: 9.5%/yr, worst drop only −21.7%. It works as insurance, not as profit.
- Sector rotation, dual momentum, the monthly 10-month rule and RSI-2 dip buying all lagged SPY.

**The bot's old swing rules** made 0.7–1.6%/yr on their watchlist, about what Treasury bills
paid. They must not be used as is.

**Momentum:**
- Buying the top 10 stocks by 12-month return made 40.5%/yr in the flattered test.
- The real momentum fund MTUM made about 16%/yr since 2013, against 14.4% for SPY.
- Realistic expectation: the market plus 1–2 points a year, with bigger drops.

**TJR's model on daily charts (2010–2026):**
- Longs: +0.24R per trade, but random entries with the same stop and target got +0.18R. The edge
  is small, and shrank after 2018.
- Shorts lost (−0.24R).
- As an account: 13.1%/yr against 14.4% for SPY; in 2018–2026, 9.0% against 14.4%.
- His real method is intraday on futures (ES/NQ), so the daily test is only a rough check. The
  intraday test is still to do.


---

<!-- from trader/aitrader/knowledge/35-team-and-options-gap.md -->

# The team and the options-gap watcher

**The team (agents.py).** Every decision goes through five agents, each with one job and a short note:
Scout (the facts: scores, holdings, cash, danger news, option gaps), Analyst (a view per stock: what
agrees, what conflicts), Trader (the orders from the desk's tested strategy), Risk (checks every buy:
size, stocks that move together, option bets against it), Reviewer (after the close: the day, the
lessons, the watcher's scorecard). Rules decide trades. Risk only warns unless the owner switches on
a veto (config: agents.risk_vetoes), and it can only skip a buy, never add one.

**Options-gap watcher (options_flow.py): testing only, never trades.** After each close: the share
of each watched stock's option volume that was calls (Alpaca's free data, next 45 days of expirations)
against its own normal share and its last 5 days of price. Bullish gap = calls unusually heavy while
the price is flat; bearish gap = puts unusually heavy while the price holds up. Each gap is graded 5
trading days later against SPY. "Shows an edge" needs 20+ graded calls, right 55%+, positive average.
Why only watching: option BUYERS' bets predicted next-week returns in research (Pan & Poteshman 2006),
but public volume can't tell buyers from sellers, large option trades in general don't predict
(Jiang & Strong), and the effect is weakest in the biggest stocks.


---

<!-- from trader/aitrader/knowledge/36-stocks-in-play.md -->

# Scanning the market: stocks in play (in_play.py)

- Every evening the bot checks all US stocks (scanner.py). The swing desk considers the strongest 30 it
  can afford. The day desk gets a pool: the busiest stocks it could trade ($5+, 1M+ shares a day, a
  14-day average daily range of $0.50+).
- At 9:35am ET: relative volume = shares traded 9:30-9:35 today / the average of the same 5 minutes
  over the last 14 days. The top 10 at 1.0x or more join the day desk's list for that day (not ones
  with danger news, not the swing desk's stocks). The fixed watchlist stays.
- Why: Zarattini, Barbon & Aziz (2024, SSRN 4729284), about 7,000 US stocks 2016-2023. The 5-minute
  opening-range breakout on all stocks: +3.2% a year. On the top 20 by relative volume: +41.6% a year.
  Trades averaged -0.02R below 1x relative volume and +0.08R above it. A 30-minute range did much worse
  than 5 minutes. Caveats: tested on the same data it was tuned on, long AND short, 4x borrowed money,
  no slippage, tight stops. So the bot tests it itself:
  - `orb_5min` (the paper's rules, long only) is one of the day methods it compares in shadow trades.
  - The report splits day trades into "in play" and "fixed list", so its own results show whether
    stocks in play help.
- TJR's sweep setups: no study tests them with a relative-volume filter. Research on stop-loss cascades
  and high-volume days points to breakouts continuing, not reversing, so in-play stocks may help
  breakouts more than sweeps. Unproven either way.
- On the free Alpaca plan, today's opening volume is IEX-only (about 2.5% of all trading), so the bot
  compares IEX with IEX. Full-market (SIP) data is 15 minutes late.


---

<!-- from trader/aitrader/knowledge/37-mistakes.md -->

# Mistakes: fine once, not twice (mistakes.py)

The owner's rule: this is the learning stage, so making mistakes is fine; making the same mistake again
isn't.

- Every buy is written down with its situation: the stock itself; a stock in play or from the fixed
  list; under $5 a share; the first 30 minutes or after 2pm; chasing (day: up 3%+ since the open;
  swing: up 10%+ in 5 days); moving with a stock it owns; option bets against it.
- A situation becomes a lesson when its recent trades (last 60 days) keep losing:
  - the same stock: 3+ trades, at most 1 won, losing money overall;
  - any other situation: 8+ trades, losing on average, worse than the desk's other trades, and
    clearly (1 standard error below zero);
  - a relapse: a lesson learned before that loses again later comes back at once.
- The Risk agent then skips new buys in that situation and says why. Sales are never blocked.
- Lessons come from every account the desk traded (in its head, paper, real), so practice mistakes
  aren't repeated with paper or real money. They fade after 60 days unless confirmed again, so the bot
  can find out when things change.
- The thresholds are small on purpose (the owner prefers learning fast to waiting for proof), but a
  lesson only ever makes the bot more careful.


---

<!-- from trader/aitrader/knowledge/38-stops-and-earnings.md -->

# Stops sized to each stock, and earnings (risk.py, earnings.py)

- Day desk stops: half the stock's usual daily range (14-day average true range, from earlier days only),
  at least 1% and at most 5% below the buy price. Unknown range: the fixed 2%. A position keeps the stop
  it was bought with, at the broker too.
- Sizing: a wider stop buys less. No day trade loses more than 0.66% of the desk at its stop (what a full
  33% position with a 2% stop risked), and no position is bigger than 33% of the desk. So a jumpy stock
  gets room AND a smaller position; nothing risks more than before.
- This is a common rule of thumb (volatility-based stops), not a tested edge. The shadow trades and the
  bot's own results show whether it helps.
- Swing desk: keeps the fixed 7% stop it was tested with.
- Earnings: the swing desk doesn't BUY a stock whose next earnings report is within 3 trading days (Yahoo
  Finance dates, looked up each morning). What it owns is kept; the stop still protects it, except that a
  stop can't sell overnight, so a report can gap past it.
- Research: stocks have earned MORE around earnings reports on average (Frazzini & Lamont 2007: over 7% a
  year; later work finds it has shrunk). Skipping reports gives that up for fewer big surprise losses.
  It's a safety choice, not a money-making one. The day desk doesn't need it: it never holds overnight.


---

<!-- from trader/aitrader/knowledge/39-shorting.md -->

# Shorting: why Kestrel doesn't (and what would have to change)

Kestrel only buys (long only). It never sells short and never borrows. The owner asked to add shorting
"if it benefits the AI"; the answer for now is no, for these reasons:

- **The real-money plan can't short.** Alpaca only allows short selling with $2,000 or more of account
  equity, and only for easy-to-borrow stocks (Alpaca's "Margin and Short Selling" docs). The plan's real
  money is $50. Kestrel runs Schwab and Webull as cash accounts, and short selling needs a margin account.
- **Paper shorts would test something the real account can't do,** so their results wouldn't carry over.
- **The evidence is weak or negative:**
  - TJR's model on daily charts: shorts lost (-0.24R per trade); see 30-research-findings.md.
  - The stocks-in-play breakout study (Zarattini, Barbon & Aziz 2024) traded long AND short and never
    reported the short side on its own.
  - Momentum's short side is where "momentum crashes" come from: after a market drop, beaten-down stocks
    can rebound violently, and a strategy short those losers loses badly exactly when the market recovers
    (Daniel & Moskowitz, "Momentum Crashes", Journal of Financial Economics, 2016).
- **A short's loss has no ceiling** (a stock can keep rising), and the busy stocks in play are the kind
  that get squeezed.

What could change it: pretend-only short trades in the strategy comparison (proposed, not built yet) to
measure whether shorting would have helped, AND an account of $2,000+ at a broker that allows it.


---

<!-- from trader/aitrader/knowledge/40-tjr-playbook.md -->

# TJR's model (learned from his videos)

## Evidence so far
- Videos analyzed: 50 of 200. Trades recorded: 55 (32 wins, 15 losses, 8 unclear).
- Average R where known (38 trades): +0.90.
- Verified by fills or broker P&L: 0. Everything else is his drawings and words.
- The bot does NOT trade this yet: it trades only after an intraday history test passes, and then only in Stage 2 paper trading.

## The rulebook (draft)
Every rule here is exact enough to code. Where the videos so far leave something open, the rule
shows the **default we chose** and it's listed under "Open questions" until a later video settles
it. Notes per video: [`notes/`](notes/).

## The model in one line
Price **sweeps a prominent liquidity level**, then **breaks structure the other way**, then comes
back into the **fair value gap** that break left behind: that's the entry. Stop beyond the sweep,
target the opposite liquidity. (Days 10, 12, 14)

## 1. Liquidity levels (what can be swept)
- **Prominent swing highs/lows** (Day 12): a swing high is a bar whose high is the highest of the
  `k` bars on each side (default `k = 3`). It's *prominent* if price later broke structure from it
  (it started a leg), not just any wiggle.
- **Previous day high / low** (Day 10's "on every timeframe").
- **Pre-market high / low** for US stocks (his "session highs/lows": Asia/London in forex).
- Stops and breakout orders sit just beyond these levels (Day 10); that's why they get swept.

## 2. The sweep
- **Bearish sweep:** a bar trades above a level (high > level) and the move up doesn't continue.
  **Bullish sweep:** a bar trades below a level and doesn't continue.
- Default: the sweep counts if a break of structure (below) follows within `N = 12` bars.

## 3. Confirmation: break of structure (Day 12)
- After a bearish sweep: a bar **closes below the most recent swing low that formed the swept
  high** ("the low that created the high"). Mirror for bullish.
- No break of structure, no trade. "Don't trade just because a level was swept."

## 4. Entry: the fair value gap (Days 12, 14)
- A **bearish gap**: three consecutive bars where bar 1's low is above bar 3's high; the gap is the
  space between them. **Bullish gap:** bar 1's high below bar 3's low.
- Use the gap created inside the break-of-structure move. Enter when price trades back into it
  (default: a limit order at the gap's near edge).
- Default minimum gap size: 0.05% of price (ignore tiny gaps). The gap expires if not reached
  within `M = 24` bars or if price closes through its far edge.

## 5. Stop, target, size (Days 12, 13)
- **Stop:** just beyond the sweep's extreme (the high of the swept bar for shorts).
- **Target:** the next prominent level on the other side (opposite liquidity). If that gives less
  than 2× the risk, skip the trade (default minimum reward/risk = 2).
- **Size from the stop:** shares = (account × risk per trade) ÷ (entry − stop), capped by cash
  (fractional where the broker allows).
- **Risk per day: 1–3% of the account in total** (default 2%, split across at most 2 trades).
  The bot's own limits (daily loss limit, kill switch) still apply on top.

## 6. Timeframes
- He says it works on every timeframe. For the bot:
  - **Day desk (Stage 2):** levels from the previous day and pre-market; sweep + break of
    structure on 5-minute bars; entry on 1-minute bars inside the gap. Flat by the close.
  - **Swing desk (Stage 2):** the same logic on daily bars (sweep of a prominent daily high/low,
    break of structure, daily gap), held for days.

## 7. When not to trade (Days 11, 13)
- **No new trades on major scheduled US news days** (Fed decision, CPI, jobs report): default rule,
  to be tested.
- No more trades once the day's risk budget or trade count is used ("never overtrade").
- No bigger size after losses (no revenge trading).

## 8. How we'll know if it works
- Backtest on history first (5-minute data for the day desk, daily for swing), with costs.
- Then Stage 2 paper for 30 trading days, next to Stage 1, and it must make money and beat holding
  SPY. Judge on many trades, not one (Day 11).

## Open questions (defaults above until a video settles them)
- Exact definition of "prominent" (how big a swing counts). Default: pivot `k = 3` that later
  caused a break of structure.
- Does the sweep bar have to *close back* inside the level, or is a wick through enough?
- How deep into the gap to enter (near edge, middle, or wait for a lower-timeframe reaction)?
- Which timeframe pairs he uses for stocks (e.g. 15-minute sweep, 1-minute entry)?
- Order blocks and "equilibrium" (his next lessons): how they add to or replace the gap entry.
- His exact time windows (New York open? first 2 hours?) and his news-day rule.

## What seems to drive wins and losses (hypotheses to test)
Updated after each batch. Each hypothesis says what would test it on historical data. Counts are
from `trades.csv`. Nothing here is proven: the trades are unverified recap drawings.

| # | Hypothesis | Evidence so far | How to test |
|---|---|---|---|
| H1 | Trading only in the direction of the 4h+1h structure is the core filter | Every trade with a stated bias went with it: 27 of 28 (023's wasn't stated). The bias timeframe varies, 15m to daily (batch 5) | Backtest the 5m entry model with and without the HTF-bias filter |
| H2 | Entry = 5m BOS in the bias direction, then a retrace into the 5m FVG/IFVG from that leg, then entry on rejection | 8/8 described this way; sweep first in 5/8; Jul 18: entered before the obvious sell-side level was swept and got stopped by that sweep | Code the entry exactly; run variants: (a) sweep required, (b) no sweep |
| H3 | Stops just beyond the last 5m swing get wicked on noise; a buffer helps | 5 of 11 losses stopped by a few points or one spike before the move worked (Feb 21 ×2, Mar 22, May 13, Jun 26) | Compare stop = last swing vs. session extreme vs. swing + 0.5×ATR(5m) |
| H4 | Targets = next HTF liquidity (prior 15m/1h/4h swing), not a fixed R | Planned R:R from 0.61 to 6.19 | Compare liquidity target vs fixed 1R/2R/3R, and a minimum-R filter |
| H5 | The first ~90 minutes after the 9:30 ET open is his main window | 41 of 55 entries 09:20–10:30; 1 unclear; 8 at 10:30–12:30; 5 in the afternoon (14:23–15:00) | Split results by entry time bucket |
| H6 | ES and NQ at the same time = one bet, twice the risk | 2 days with both; both lost together once | Treat same-direction ES+NQ as one position in sizing |
| H7 | Red-news days are worse | Both Feb 21 losses on an FOMC-minutes day; Feb 22 (news-heavy) was a win; he sat out Mar 6, 7, 8, 12 (Powell, NFP, CPI) Jan 2025: a short taken while Trump was speaking lost; he calls not trading during speeches the day's key lesson. | Tag each session with red-impact US releases (CPI, NFP, FOMC, Powell, PPI, ISM, JOLTS). Refined in batch 6: he waits for the 10:00 release, then trades the reaction (4 wins, 2 losses, 2 unknown after it, incl. Powell day Jul 9; the entry one minute after the release lost). Compare the 30 min before vs after a release, and entries before vs after the first 5m close |
| H8 | Two-step trigger: price reaches a pre-marked level (sweep or pullback into a zone), then a lower-timeframe close confirms (BOS/IFVG); a touch alone = no trade | Every plan in batch 2 was stated this way | Code both steps; compare with entering on the touch |
| H9 | Entries inside an intraday range that already chopped for over an hour do worse | Mar 22 NQ short: entered mid-chop, stopped by one spike | Measure range width/touch count in the 60 min before entry; compare results |
| H10 | Add-ons (a second entry while the first is open) do worse than first entries | Mixed: the May 6 NQ add-on lost (he says he shouldn't have); the May 23 ES add-on won 1.86R but came within 0.7 pt of the stop | Compare first entries only vs allowing add-ons |
| H11 | An ES/NQ SMT divergence at the sweep improves results | SMT trades with a known result: 9 wins, 0 losses (Apr 29, May 16, May 23 ×2, May 29, Jun 21, Jun 27, Jul 8, Jul 9); 3 unknown. Easy to cherry-pick in recaps: test every NY-open sweep | Tag sweeps where only one index made a new extreme; compare |
| H12 | One re-entry after a stop-out is fine if price closes back through the same zone within 15 minutes | May 13: stopped at −1R, re-entered the same zone and won 2.89R | Allow 0 vs 1 re-entry per zone |
| H13 | Trades without a fresh trigger ("forcing it") do worse | 5 losses fit: Jul 17 (long into a news-driven sell-off, "catching a falling knife"), Jun 26 (1m trigger alone, one minute after the news), May 17 ("trying to find a reason to get into a trade"), May 28 (sold "way too late" after the expansion), May 29 NQ ("wanted this one a little bit too bad"); May 23 #2 ("purely on price coming off") was the smallest win | Require a coded trigger (BOS or IFVG close); forbid entries more than ~1.5×ATR(5m) from the move's start |
| H14 | The equilibrium entry (retrace to the 50% of the morning range or of a 5m FVG, then a 1m BOS) is his best setup | 3 wins with a known result: Jun 3 NQ short at the range 50% (4.55R), May 29 ES long at the FVG 50%, Jul 9 NQ long at the 1h 50% (1.62R first partial) | Entry at the 50% level vs at the gap's edge |
| H15 | Half off at the first target and the rest to breakeven beats one full target | Stated as his rule on May 29 and Jun 6/25/27; in practice (Jun 20-21 ×3, Feb 2026) his first partial came at or below 1R and the rest was stopped at breakeven, so real wins were 0–1R, not the drawn 1.7–2.9R. Jun 17 reached +1.25R before losing 1R | Simulate both exits on the same entries |
| H16 | A 1m trigger needs a confirming 5m close before entry | Jun 26 and Jul 17: 1m-only entries lost, and both times he says he should have waited for the 5m / higher timeframe | 1m trigger alone vs 1m trigger plus a 5m close in the same direction |
| H17 | A 4h-close bias rule works: bullish until a bearish 4h close below the last 4h higher low (and vice versa) | Stated as his weekly plan (Jul 6 forecast) | Code it as the only bias filter under H2's entry; compare with no bias filter |
| H18 | Two-index confirmation: for a long, the weaker index inverts its bearish gap while the stronger breaks structure up (reverse for shorts) | Stated as his rule in the Apr 2026 live session; the confirmed long won | One-index trigger vs two-index confirmation |
| H19 | No counter-trend entries on a one-way (trend or news) day | Jul 17 and Jul 18 counter-trend longs both lost 1R | Skip entries against the day's direction when the first hour moved more than ~2×ATR(1h) and there's no 5m BOS |


---

<!-- from trader/aitrader/knowledge/41-weekend-practice.md -->

# Weekend practice (weekend.py)

On Saturdays and Sundays, while the stock market is closed, Kestrel practices. Two separate experiments,
each turned on or off in Setup → Settings:

- **Replay** (accounts weekend-swing and weekend-day): real past trading days, from the 5-minute and
  daily prices saved on the Mac, replayed fast (about 30 minutes per trading day, consecutive days, a
  different stretch each weekend) through each desk's own strategy, team and risk rules. The swing desk
  decides at 3:45pm of each replayed day, on that day's closing prices (a 15-minute head start); the day
  desk every 5 minutes. It's practice, not new evidence: the strategies were chosen by testing this same
  history.
- **Crypto** (account weekend-crypto): $500 of pretend money against live crypto prices (Alpaca's free
  crypto data, no keys), the swing desk's momentum method on hourly bars: a decision at the top of each
  hour, stop-losses every 5 minutes, everything sold Sunday at 11:50pm. Nothing goes to a broker. An
  experiment: Kestrel's strategies were only ever tested on stocks.

**None of it counts** toward Stage 1's 30 days, a move to real money, or what the desks learn from their
own trades (mistake memory and lessons only read the in-its-head, paper and real accounts). Each weekend
starts fresh; Monday's journal gets one summary line. The Thinking tab shows it live.


---

<!-- from trader/aitrader/knowledge/42-news-and-filings.md -->

# News, SEC filings and big economic news

- **Headlines** (scanner.py): Alpaca's news feed (Benzinga), or Yahoo without keys. Danger headlines
  (share offering, bankruptcy, halt, delisting, fraud) stop buying that stock. News never makes it buy.
- **SEC filings** (sec_filings.py): official filings from the SEC's EDGAR system, free, no key. The SEC asks
  every program for a contact email (Setup → AI & news). Every 30 minutes on trading days it checks what it owns
  or considers (watchlists, the top of the scan, stocks in play). The stock card shows the last two weeks of
  filings with links. Serious ones block buying for 30 days: 8-K item 1.03 (bankruptcy), 3.01 (delisting
  notice), 4.02 (past financial statements can't be relied on), 1.05 (a material cyber attack), and late
  annual/quarterly reports (NT 10-K / NT 10-Q). On a stock it owns, that's a WARNING; the stop-loss still
  protects it.
- **Big economic news** (macro.py): the dates of CPI (8:30am), the jobs report (8:30am) and the Fed's rate
  decisions (2pm), from FRED with a free key (Setup → AI & news). A countdown in the Thinking tab and the report.
  Kestrel does NOT avoid these days by rule: the famous pre-Fed rally (Lucca & Moench, 2015) faded after 2015,
  and other releases showed no such pattern. Instead every buy on those days is tagged ("on a CPI day"),
  so the mistake memory learns from the desk's own results whether they lose, and skips them if they do.
- **Why it moved**: the stock card and the report show a stock's move today and over 5 days, next to the
  latest headlines and filings. A hint, not proof: news can follow a move as well as cause it.


---

<!-- from trader/README.md -->

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
                           head" (swing: momentum, day: TJR's model; config.yaml
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
   screen on top. The Setup screen is always one click away: the **Setup** button. It has a sidebar of
   sections: **Start here** (what's connected, and what happens next), **Autopilot**, **Brokers & keys**,
   **Your phone**, **AI & news**, **Settings** and **More**. A dot by each one shows green when it's set up
   and amber when it needs you.
4. **Setup → Brokers & keys → Alpaca paper account** (free, about 5 minutes):
   - Sign up at <https://app.alpaca.markets>. Paper trading needs no money and no approval.
   - The default paper account holds $100,000. Make a new paper account with **$1,000** so paper
     behaves like your real account (the bot caps itself at $1,000 either way).
   - In the paper account: **API Keys → Generate**. Paste the Key ID and Secret into Setup and
     press **Save and test**. It should show two green checks. The keys are saved only on your Mac
     (`~/AITrader/.env`). Live (real-money) keys are refused here on purpose.
5. **Setup → Autopilot → Turn on.** Done: it studies every trading day, starts when you log
   in, and restarts itself if it crashes (closing the app doesn't stop it).
6. **Setup → Start here → What happens next** tells each desk's step in plain English.
7. **Later, when you're ready:**
   - **Setup → Settings:** which broker gets real money, the most real money it may use (e.g. $50), the
     account type, the paper amount, and what it looks at. They're kept when the app updates.
   - **Setup → Brokers & keys → Charles Schwab:** paste the App Key, the Secret and the callback address, then **Open Schwab
     login**. Sign in, then paste the address your browser lands on (that page won't load; that's
     expected). Log in again at least once a week: Schwab's limit is 7 days.
   - **Setup → Brokers & keys → Webull:** apply on the Webull website (API Management → My Application; Webull reviews it in
     about 1–2 business days). Once approved, Generate Key and paste the App Key and App Secret, with
     **Paper** for Webull test-environment keys or **Real money** (a wrong pick is fixed by the test). Press
     **Test Webull**, then approve Kestrel in the Webull app within 5 minutes (Menu → Messages →
     OpenAPI Notifications → Check Now → the text-message code). The autopilot uses that approval each
     morning so it doesn't lapse (Webull drops it after 15 unused days). To paper trade at Webull:
     Settings → Paper trading happens at → Webull (needs the paper keys, approved). Real money at Webull
     needs its real-money keys, Broker for real money: Webull, and the usual locks. Whole shares only there.
   - **Setup → Brokers & keys → Alpaca real-money keys:** saving them turns nothing on.
   - **Setup → More → Connect Claude** (Code or Desktop).

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


---

<!-- from trader/config.yaml (the settings, with their explanations) -->

```yaml
# =====================================================================
#  AI TRADER SETTINGS
#  Every "knob" of the bot lives here. Secrets (every key) go in ~/AITrader/.env,
#  never in this file.
# =====================================================================

# Where REAL-money orders go: "alpaca", "schwab" or "webull" (Setup -> Settings). Paper trading
# happens in the Alpaca or Webull paper account, or simulated on this Mac (Schwab has no paper
# trading). All of them use the same safety rules.
broker: alpaca

# The yardstick (never traded). If a desk can't beat simply holding
# this, it doesn't earn real money.
benchmark: SPY

# ---- Money -------------------------------------------------------------
paper:
  use_broker_paper: true   # alpaca: paper trade INSIDE your Alpaca paper account (real order
                           # handling, fake money). false = simulate on this laptop instead.
  starting_cash: 1000      # keep EQUAL to live.max_capital so paper results are realistic
  slippage_pct: 0.05       # assume we fill a bit worse than the quoted price
  commission_per_trade: 0.0

live:
  max_capital: 1000        # the bot NEVER uses more than this, whatever else is in your account
  account_type: auto       # auto = Schwab and Webull: cash rules, Alpaca: margin. "cash": only SETTLED money is spent
                           # (T+1, bank holidays counted), so there are never good faith violations.
                           # "margin": Alpaca under $2,000 can't borrow, and it covers unsettled money itself.
                           # The bot never borrows either way.
  limit_buffer_pct: 0.2    # limit orders at quote +/- 0.2%: they fill, but never at crazy prices
  fill_timeout_seconds: 60 # cancel an order if it isn't filled in time
  resting_stops: true      # ALSO leave a stop-loss order sitting at the broker, so a sleeping or
                           # crashed laptop can't stop a falling position from being sold

# ---- Two desks share the money -----------------------------------------
# Each desk is studied, planned, paper traded and promoted SEPARATELY, so a
# losing desk can never hide behind a winning one.
#   * A ticker can be on only ONE desk.
#   * DON'T list stocks you own yourself. In your shared account the bot skips
#     them anyway, to keep your shares and tax lots separate from its own.
#   * Fractional shares (parts of a share) where the orders go can do them: Alpaca and the
#     simulation on this Mac. Schwab's API can't, and Webull's isn't confirmed yet: there it's
#     whole shares, and stocks where 1 share costs more than a position's budget are skipped.
fractional:
  enabled: true            # off = whole shares everywhere (Setup -> Settings)

desks:
  swing:                   # holds days to weeks; decides once a day, 15 min before the close
    enabled: true
    budget_pct: 50         # $500 of the $1,000
    watchlist: [XLF, XLE, XLU, XLP, KRE, SCHD, KO, BAC, WFC, PFE, CSCO, VZ]
    risk:
      # 8 stocks, not 3: in the bot's own backtest (2011-2026) momentum with 8-10 holdings traded ~3x
      # as often as with 3, made about the same, and had a smaller worst drop (-42..-47% vs -57%).
      max_open_positions: 8
      max_position_pct: 12.5   # % of this desk's money in any one stock (so a share can cost up to ~$62)
      stop_loss_pct: 7         # sell if a position falls 7% below what we paid
      daily_loss_limit_pct: 3  # desk down 3% today -> no new buys today
      max_drawdown_pct: 15     # desk down 15% from its best day -> KILL SWITCH
      cash_buffer_pct: 1

  day:                     # in and out the SAME day; decides every 5 minutes; never holds overnight
    enabled: true
    budget_pct: 50
    # Liquid stocks that move a lot within a day (the second row: $500M+ traded a day, 3-6% daily
    # range, under $160 a share, as of Sep 2026). More stocks = more breakouts to trade.
    # (Tickers that are also yes/no words, like "ON", must be in quotes, or they're read as true/false.)
    watchlist: [SOFI, F, INTC, AAL, SNAP, RIVN, NIO, T,
                HPE, ORCL, SHOP, "ON", RBLX, HPQ, PCG, FCX]
    last_entry_minutes_before_close: 30    # no new trades in the last 30 minutes
    flatten_minutes_before_close: 10       # sell everything 10 minutes before the close
    risk:
      max_open_positions: 3
      max_position_pct: 33
      stop_loss_pct: 2         # day trades get a much tighter stop (used when a stock's daily range is unknown)
      # Stops sized to how much each stock usually moves: half its usual daily range (14-day ATR),
      # between 1% and 5%. A jumpy stock in play gets room; a calm one gets a tight stop. And a wider stop
      # means a smaller position: never more than 0.66% of the desk lost at the stop (= a full 33%
      # position with a 2% stop, the old rule), so nothing risks more than before.
      stop_atr_multiple: 0.5
      stop_min_pct: 1
      stop_max_pct: 5
      risk_per_trade_pct: 0.66
      daily_loss_limit_pct: 3
      max_drawdown_pct: 15
      cash_buffer_pct: 1

# ---- Market data ---------------------------------------------------------
data:
  # "auto"     = Alpaca if your Alpaca keys are in .env, otherwise Yahoo.
  # "alpaca"   = Alpaca data (free plan: real-time "iex" feed, years of 5-minute history)
  # "yfinance" = free Yahoo data, no account needed (study and paper only)
  # "schwab"   = Schwab's real-time data
  # Real money requires alpaca or schwab (real-time prices).
  source: auto
  alpaca_feed: iex         # free. "sip" (all exchanges) needs Alpaca's paid data plan
  history_years: 8         # daily prices for the swing desk
  intraday_days: 180       # 5-minute prices for the day desk (Alpaca: years available;
                           # Yahoo: only ~60 days). The bot saves them, so its history grows.

# ---- Phase 1: STUDY (watch & learn, no trades) ----------------------------
study:
  min_calendar_days: 30    # "a month of analyzing"
  min_study_days: 20       # ...and at least this many trading days studied
  horizon_days: 5          # swing opinions are graded 5 trading days later
  # While a desk studies it also trades "in its head": pretend money, simulated on this Mac, the
  # same rules as paper trading. Every trade and the daily results show up in the app (Trades tab).
  in_its_head: true
  # The day desk practices TJR's model (Stage 2, tjr.py) in its head; the study still compares it with
  # the other day methods, and a weekly history test decides if it may paper trade.
  in_its_head_strategy: {swing: momentum, day: tjr_model}

# ---- The local AI model (one per desk) -------------------------------------
ai:
  swing:                   # counted in DAYS
    buy_above: 0.56        # AI must be >= 56% sure the price rises to buy
    sell_below: 0.48       # ...and sells when it drops below 48%
    retrain_every: 21      # re-learn about once a month
    min_train: 500         # don't trust it until it has ~2 years to learn from
  day:                     # counted in 5-MINUTE BARS (78 bars = 1 trading day)
    buy_above: 0.55
    sell_below: 0.48
    horizon: 12            # predicts: higher in 1 hour (and never past today's close)?
    retrain_every: 390     # re-learn about once a week
    min_train: 1560        # needs ~20 trading days of 5-minute history first

# ---- How a trading plan gets picked after the study month -------------------
plan:
  min_sharpe: 0.5          # risk-adjusted return in the backtest
  min_profit_factor: 1.15  # $ won / $ lost on closed trades
  max_drawdown_pct: 25     # worst peak-to-bottom drop allowed in the backtest
  min_trades: 30           # need enough trades for the numbers to mean anything
  min_forward_signals: 10  # swing: graded "buy" opinions in the study month
  min_forward_trades: 10   # day: shadow trades in the study month

# ---- Your phone -----------------------------------------------------------------
# Alerts and commands: a private Telegram bot (set up in the app's Setup screen, phone.py).
# The Kestrel screen on your phone over your private Tailscale network (phone_screen.py): on/off.
phone:
  screen: off

# ---- Rules to go from PAPER -> LIVE ("once you're profitable") -------------
# Checked per desk. ALL must pass, and you must still confirm by hand.
# Your rule: over the stage (30 trading days), make money AND beat SPY. The drawdown limit stays.
# min_closed_trades / min_profit_factor: blank = not checked (momentum trades rarely, so a
# 30-day stage may only close a few trades). Put numbers back to require them again.
promotion:
  min_trading_days: 30
  min_closed_trades:
  min_total_return_pct: 0.0
  min_profit_factor:
  max_drawdown_pct: 10
  must_beat_benchmark: true

# ---- The daily all-stocks scan (scanner.py) -------------------------------
# After the close: every tradable US stock (Alpaca), or ~400 popular names without Alpaca keys.
# Ranked by 12-month momentum, uptrends only. The swing desk also considers the top of the list.
scanner:
  enabled: true
  top: 30                  # stocks on the list
  new_listings: 5          # newly listed stocks (under a year of history): watch only
  min_price: 3             # no penny stocks
  min_dollar_volume: 5000000   # average $ traded per day (20 days): easy to get in and out
  trade_top: 30            # the swing desk considers the 30 strongest stocks it can afford
                           # (enough for its 8 slots: it buys from the top 20% of what it considers)

# ---- Earnings (earnings.py): don't open a swing position right before an earnings report --------
# A report can move a stock 10-20% overnight, past the stop-loss. The swing desk doesn't BUY a stock
# whose report is within days_before trading days (what it already owns is kept). The day desk never
# holds overnight, so it doesn't need this. Dates: Yahoo Finance, once a day.
earnings:
  enabled: true
  days_before: 3
  desks: [swing]

# ---- Stocks in play (in_play.py): the day desk's extra stocks each morning ----------------------
# At 9:35 ET: which of the busiest stocks traded far more than usual in their first 5 minutes (relative
# volume). The top ones join the day desk's list for that day; its watchlist above stays.
in_play:
  enabled: true
  pool: 300                # the busiest stocks it checks (from the evening scan of all US stocks)
  picks: 10                # added to the day desk's list each morning
  min_rvol: 1.0            # at least as busy as usual in the first 5 minutes (the research used 1.0)
  min_price: 5             # the research's filters: $5+ a share,
  min_avg_volume: 1000000  # 1M+ shares a day (14-day average),
  min_atr: 0.5             # and moving at least $0.50 a day (14-day average true range)
  history_days: 14         # "usual" = the average of the last 14 days' first 5 minutes

# ---- The team (agents.py) ------------------------------------------------------
# Every decision goes through five agents that each write a short note: Scout (facts), Analyst (views),
# Trader (the tested strategy's orders), Risk (checks every buy), Reviewer (after the close).
# Rules still decide the trades. Risk only warns, unless you list checks it may act on (skip a buy):
#   correlation  = the stock moves with one we already own (return correlation >= correlation_limit)
#   options_gap  = option bets lean against it (only once the options-gap watcher shows an edge!)
agents:
  enabled: true
  learn_from_mistakes: true   # skip a buy that repeats a mistake the desk already made (mistakes.py)
  risk_vetoes: []
  correlation_limit: 0.85
  correlation_bars: 60     # swing: 60 days; day desk: 60 five-minute bars

# ---- Options-gap watcher (options_flow.py): watches and grades, never trades --------
# After each close: calls vs puts in each watched stock's options (Alpaca's free data, next 45 days of
# expirations) against the last 5 days of price. A gap = the bets and the price disagree. Graded 5
# trading days later against SPY; the scorecard is in the after-market report.
options_watch:
  enabled: true
  expiry_days: 45
  min_volume: 2000         # contracts a day; less is too thin to mean anything
  horizon_days: 5
  max_symbols: 60

# ---- News (you can turn this off in Setup) ---------------------------------
# Headlines from Alpaca's news feed (Benzinga; free with your Alpaca keys), or Yahoo without keys.
# Used to AVOID buying a stock with danger headlines (share offering, bankruptcy, halt, delisting,
# fraud...) and to explain things. News never makes it buy.
news:
  enabled: true
  days: 3

# ---- SEC filings (sec_filings.py; free, no key: needs your contact email in Setup step 8) -------------
# Every 30 minutes on trading days: the official filings of what it owns or is considering. Serious
# ones (bankruptcy, delisting notice, "past financials can't be relied on", a cyber attack, a late
# annual/quarterly report) stop it buying that stock for 30 days, like danger headlines.
sec:
  enabled: on

# ---- Big economic news (macro.py; a free FRED key in Setup step 8) ----------------------------------
# CPI, the jobs report and Fed decisions: a countdown in the Thinking tab and the report, and every buy
# on those days is tagged so the mistake memory learns whether they lose. No rule avoids them.

# ---- Weekend practice (Saturday and Sunday; weekend.py) ----------------------
# Practice only: none of it counts toward Stage 1, real money, or what the desks learn from their
# own trades. Each weekend starts fresh. Watch it live in the Thinking tab. (Setup -> Settings)
weekend:
  replay: on                 # replay real past trading days from the prices saved on this Mac
  replay_minutes_per_day: 30 # one trading day in about 30 minutes (78 five-minute moments)
  crypto: on                 # crypto with pretend money at live prices (Alpaca's free crypto data)
  crypto_budget: 500         # pretend dollars
  crypto_strategy: momentum  # the swing desk's method, on hourly bars: own the strongest coins
  crypto_coins: [BTC/USD, ETH/USD, LTC/USD, DOGE/USD, AVAX/USD, LINK/USD, BCH/USD, DOT/USD, UNI/USD, AAVE/USD]
  crypto_risk: {max_open_positions: 3, max_position_pct: 33, stop_loss_pct: 5, daily_loss_limit_pct: 5,
                max_drawdown_pct: 20, cash_buffer_pct: 1}

# ---- Optional local LLM (Ollama) for plain-English write-ups ----------------
# It WRITES the plan, the report summary and the team's notes. It does NOT decide trades.
# Install Ollama (free, ollama.com/download); Kestrel downloads the model by itself (Setup step 7).
llm:
  enabled: true
  url: http://localhost:11434
  model: gemma4:12b        # Google's Gemma 4 12B (Apache 2.0, ~8 GB download): needs a 16 GB Mac
  small_model: qwen3:4b    # ~2.5 GB: used on a Mac with less memory, and while the big one downloads
  min_memory_gb: 16        # below this, the small model, so the AI never slows down trading
  think: false             # answer straight away instead of "thinking" first (faster short write-ups)
  timeout_seconds: 300     # a bigger model takes longer, the first time each day most of all
  use_knowledge: true      # give it the background notes (aitrader/knowledge): plan, safety rules, research, TJR
  context_tokens: 8192     # room for those notes plus the question
```
