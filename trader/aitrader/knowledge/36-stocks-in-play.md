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
