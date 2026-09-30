# Boot Camp Day 14: Fair Value Gaps, part 1

Source: video (≈10 min, talking to camera, no charts). Rough offline transcript. Part 2 ("how to
spot them") is the next lesson.

## What he teaches
- A **fair value gap** (he also calls it a void or an imbalance) is a price range the market went
  through so fast that almost no orders traded there, e.g. a sharp move up because there were no
  sellers in that range, or a sharp drop "with no hesitation".
- Price tends to **come back into those gaps**; that's where large players fill their orders.
- **How he uses them:** liquidity sweeps tell him the *direction* (where price is drawn to); the
  fair value gap is the *entry*. When price retraces into a gap in the trend's direction and reacts
  on a lower timeframe, he enters with the trend. Gaps also give "continuation" entries after a
  break of structure.
- He prefers this to plain support/resistance ("bounced off a floor") because it explains *why*
  price reacts there.
- Works on any market and timeframe, in his view.

## What this means for the bot (to confirm with part 2)
- Standard definition to code: a 3-candle pattern where candle 1's high is below candle 3's low
  (bullish gap = the space between them), or candle 1's low is above candle 3's high (bearish).
- Entry: price trades back into the gap in the direction of the trend/sweep; stop beyond the gap
  (or beyond the sweep); open questions: minimum gap size, how deep into the gap, how long a gap
  stays valid.
