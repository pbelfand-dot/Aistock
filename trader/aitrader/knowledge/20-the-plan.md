# The owner's plan

1. **Stage 1: paper trading, 30 trading days, "free ball".**
   - Trade what the research says works, and build a growing list of stocks the bot likes, from
     niche names to big ones.
   - Method (`momentum`, swing desk): rank every stock on the list (the watchlist plus the top
     15 of the daily all-stocks scan) by its 12-month return, skipping the latest month. Buy from
     the top 20% while the stock is above its 200-day average; sell when it drops out of the top
     half or below its 200-day average. No new buys while SPY is below its 200-day average.
   - Whole shares only, at most 3 positions of up to 34% of the desk's money each, 7% stop-loss.
     Stocks too expensive for one whole share are skipped.
   - The owner starts it with **Start Stage 1 paper trading** in Setup (or `python run.py
     start-stage1`). It skips the study month; the day desk keeps studying.
2. **Stage 2: paper, 30 trading days:** Stage 1 plus TJR's model. TJR's rules only trade after
   they pass an intraday history test.
3. **Real money:** $50 at Alpaca and $50 at Schwab. More only if it makes money.

**Pass rule the owner set (this is what `promote` checks):** over at least 30 trading days of
paper trading, make money and beat SPY over the same days, without dropping more than 10% from
the best day. No minimum number of trades. Then the owner still confirms by hand.
- Caveat from the research: over any 30 trading days, even the best method did that only about
  6 times in 10 (58%), and momentum with the trend filter about half the time (49%).
- So a single stage can catch a broken method, but can't prove a good one.

**Reports the owner sees (Trades tab):** every trade with what was spent, what came back, the gain
or loss in $ and %, win or lose; each day's % change; and the totals vs SPY. The same report
exists for three accounts: "in its head" (a studying desk trades with pretend money on this Mac:
swing = momentum, day = opening range breakout), paper, and real money. After each close the
journal gets one line per account with today's result and the running totals.

**Where the code is now:** Stage 1 is a button. Otherwise each desk still goes study (30 days) →
plan review → paper → live. Real money always needs the promotion rules to pass and the owner's
typed confirmation.
