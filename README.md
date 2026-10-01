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
- **Your phone** (Setup steps 5 and 6):
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
- **View → Show Demo Data** shows it with made-up prices right away.
- **Setup** (the button) connects Alpaca, switches the autopilot and says what's next.
- **Stage 2: TJR's model** (day desk). It waits for a sweep below a low, a break back up, then buys
  the pullback into the gap, 9:35-11:30am, with the hourly trend. The day desk practices it in its
  head. A weekly history test on your Mac's 5-minute data compares it with random buys; once it
  passes, **Setup → Start Stage 2** paper trades it next to Stage 1. Results are in Research.
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
