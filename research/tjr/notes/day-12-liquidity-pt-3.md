# Boot Camp Day 12: Liquidity, part 3 (using it to trade)

Source: video (≈20 min, TradingView: S&P 500 daily, 4h, 1h and 5-minute; gold). Rough offline
transcript + chart pictures.

## What he teaches
- The course builds in blocks: **liquidity → fair value gaps → order blocks → equilibrium**, then
  the full strategy. Liquidity alone is "a piece you plug into a strategy", not a strategy.
- **Mark the prominent highs and lows, not every one.** Prominent = the swing that started a trend
  or that caused a break of structure. Not every high/low will be used.
- **Liquidity is a magnet:** price is drawn toward the next pool of orders.
- **Don't trade just because a level was swept.** Wait for:
  1. the sweep of a prominent high (or low),
  2. **confirmation: a break of structure the other way**, i.e. price closes beyond the most recent
     swing low that created that high (mirror for lows),
  3. then a reaction from a **fair value gap / imbalance** (or an order block) formed by that move.
  "A sweep of liquidity + a break of structure + a reaction off a gap = an entry. Simple."
- **Targets = the opposite liquidity:** after a short from a swept high, aim for the previous
  prominent lows (that's where the big players close their positions). Mirror for longs.
- Examples: the S&P 500 daily (sweeps, then breaks of structure, then imbalances filled before the
  move), the 1-hour and 4-hour, gold.

## For the bot (this is the core of the TJR model)
1. Find prominent swing highs/lows (pivots that led to a break of structure).
2. Sweep: price goes beyond one of them.
3. Break of structure in the opposite direction: a close beyond the swing point that formed the
   swept level.
4. Entry when price comes back into a fair value gap left by the break.
5. Stop beyond the sweep's extreme; target the next prominent level on the other side.
