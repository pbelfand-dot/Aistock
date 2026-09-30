# The owner's plan

1. **Stage 1: paper trading, 30 trading days, "free ball".**
   - Trade what the research says works, and build a growing list of stocks the bot likes, from
     niche names to big ones.
   - Proposed method (waiting for the owner's OK): each month, own the 10 stocks that rose most
     over the past 12 months (skipping the latest month), equal weight. Move to cash-like bonds
     when SPY is below its 200-day average.
2. **Stage 2: paper, 30 trading days:** Stage 1 plus TJR's model. TJR's rules only trade after
   they pass an intraday history test.
3. **Real money:** $50 at Alpaca and $50 at Schwab. More only if it makes money.

**Pass rule the owner set:** make money and beat SPY over the stage.
- Caveat from the research: over any 30 trading days, even the best method did that only about
  6 times in 10.
- So a single stage can catch a broken method, but can't prove a good one.

**Where the code is now:** each desk goes study (30 days) → plan review → paper → live. Reworking
this into the stages above is planned.
