# Aistock

## ⬇️ [Download AI Trader for Mac](https://github.com/pbelfand-dot/Aistock/releases/latest/download/AITrader-mac.zip)

An AI trading bot for **Alpaca** (now) and **Charles Schwab** (later). It studies the market
for a month, writes a plan, proves it with paper money, and only then trades real money,
capped at $1,000. Built and tested automatically by GitHub every time the code changes.

### Install (about 3 minutes)
1. Click the download link above and open **AITrader-mac.zip** (it unzips itself).
2. Drag **AI Trader** into your **Applications** folder.
3. Open it. The first time, macOS blocks apps that aren't from the App Store:
   - Click **Done**, then open **System Settings → Privacy & Security**, scroll down, and click
     **Open Anyway** next to "AI Trader" (you may need your Mac password).
   - Or paste this in Terminal instead:
     `xattr -dr com.apple.quarantine "/Applications/AI Trader.app"`
4. The first time, the app also opens the **Setup menu** in a Terminal window to install Python
   and the bot's libraries (about 2 minutes). The app's window opens your dashboard when it's done.
5. In the Setup menu: **Edit my keys** (paste your Alpaca paper keys) → **Check** →
   **Keep the autopilot running in the background**.

### The app
**AI Trader** is a normal Mac app: its own window, Dock icon and menus (no browser, no web
server). Its window is a brokerage-style dashboard: your account value vs. the S&P 500,
positions, every trade and why, each desk's progress, the watchlist, and **Pause** /
**Emergency stop** buttons. **View → Show Demo Data** shows it with made-up prices right away.
**AI Trader → Setup Menu** (⌘,) opens the Setup menu again for keys, plans and the autopilot.

![The AI Trader app (demo data)](docs/dashboard.png)

It's the bot's own design, not Schwab's or Alpaca's: it never shows or asks for your broker
login, and it can't buy anything. Closing the app doesn't stop the background autopilot.

Everything lives in the **AITrader** folder in your home folder (your keys, settings, and the
bot's memory). Updating is the same: download the new zip and open it; your keys and data stay, and a
running background autopilot restarts on the new version.

### Connect Claude
Menu → **Connect Claude Code** (or **Connect Claude Desktop**). Claude can then see the bot
(status, trades, plans) and pause it, and read your Schwab account once you add Schwab. It can't trade.

### What's in this repo
- [`trader/`](trader/): the bot. [Full guide →](trader/README.md)
- [`mac/`](mac/): the Mac app (a Swift window, `mac/app/main.swift`) and how it is built
- `backend/`, `frontend/`: the earlier stock-suggestion web app

> Not financial advice. Most people who trade actively lose money. The bot's first job is to
> find out safely whether a strategy has an edge, and to say "don't trade" if it doesn't.
