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
- **Challengers** (Thinking tab): new versions of a desk's method race the current one. The swing desk's
  `momentum` has four: `momentum_plus` (residual momentum, smooth climbs, near 52-week highs),
  `momentum_calm` (smaller buys when its stocks get stormy), both together, and `momentum_quality` (see
  below). Each is replayed on all 8 years of saved prices and shadow trades with pretend money next to
  the desk. It takes over only when tests built to catch luck say it's really better (a bootstrap test,
  and a deflated Sharpe ratio whose bar rises with every idea ever tried), its worst drop isn't much
  deeper, and it isn't behind after 20 days of shadow trading. Pretend-money desks switch by themselves
  and tell you; a real-money desk waits for you to press **Use it**.
- **Day desk upgrades**: simulated day trades now pay realistic costs (2 cents a share each way, about the
  slippage plus half the spread), so its tests stop flattering it. Its challengers: the 5-minute breakout,
  and both methods with a 3:30pm market check (sell when the S&P 500 was down at 10am: market intraday
  momentum). About 9:20am it lists the **pre-market movers** (a 3%+ gap on heavy early volume); they're
  shadow traded and join the day desk's list only once that proves better.
- **Beyond the price** (each stock card, and the team's notes): company quality (gross profits / assets
  from the SEC, ranked against every US company), recent open-market buys by its officers and directors
  (Form 4s), and short interest (% of the float sold short, days to cover). The `momentum_quality`
  challenger skips low-quality and heavily shorted stocks and favors fresh insider buys; the mistake
  memory tags buys with these facts so it learns whether they lose.
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
  - **Alert me if Kestrel stops** (a dead-man's switch). A Mac that's asleep, unplugged or offline can't
    warn you itself, so Kestrel checks in with [healthchecks.io](https://healthchecks.io) (free for up to
    20 checks) every 5 minutes. If the check-ins stop, or trading keeps failing for 15 minutes,
    healthchecks.io alerts you (Pushover, Telegram or email, set up there). Give the check the Cron
    schedule `*/5 9-15 * * 1-5` in the `America/New_York` time zone with 15 minutes of grace, then paste
    its Ping URL into Setup.
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
  full year of prices for the actively traded ones, reused from the day before where it can). It saves
  its work as it goes, so a restart or an update doesn't make it start over. The swing desk considers the 30 strongest it can
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
