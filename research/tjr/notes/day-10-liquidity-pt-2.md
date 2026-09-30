# Boot Camp Day 10: Liquidity, part 2 (where liquidity lives)

Source: video (≈16 min, TradingView charts: gold weekly/4h, GBP/USD, GBP/JPY, S&P 500 daily,
15-minute examples). Rough offline transcript + chart pictures.

## What he teaches
- **Where the orders sit.** In an uptrend (higher highs, higher lows) traders buy breakouts
  *above* highs (buy stops), and people who are short keep their stop-losses above the same highs.
  So above a high = a pile of buy orders. Below a low = sell stops plus the stop-losses of longs.
- **Why that matters.** Big players need someone on the other side to fill millions of orders.
  When price runs through a high, those stops and breakout orders fire, and that's the liquidity
  they sell into. Result: "sweep of the highs → collapse"; "sweep of the lows → rally".
- **Why it's useful.** It catches the *turn*: the end of one move and the start of the next,
  instead of joining a trend late.
- **Every timeframe:** monthly/yearly down to 15-minute. Examples: the S&P 500 taking out a
  3-year high on the daily and then selling off; Asian-session lows swept on the 15-minute and
  then price pushing higher.
- Homework he gives: find 5 sweeps on 3 timeframes on 3 markets.

## For the bot
- Liquidity levels to track: swing highs/lows (see Day 12 for which ones), previous day high/low,
  session highs/lows (for US stocks: pre-market high/low).
- A "sweep" = price trades beyond the level and then turns back (the orders got used). The turn is
  only confirmed by a break of structure (Day 12).
