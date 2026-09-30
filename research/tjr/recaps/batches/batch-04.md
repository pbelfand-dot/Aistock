# Batch 4: videos 17–21 (Apr 4 – May 6, 2024)

All 5 were accessed. There are 7 trades and 2 no-trade days. No fills, size or account P&L were
shown, so every result is unverified.

## 1. Trade records

| Video | Date | Market | Side | Timeframes | Entry | Stop | Target | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|---|
| 017 | Thu 04-04 | ES/NQ | no trade | 4h → 1h imbalance → 5m | – | – | – | the retrace entry never came | – |
| 018 | Mon 04-29 ~10:03 | NQ | long | 4h/1h → 5m → 1m | 17867.00 | 17848.50 | 17904.00 | win (inferred) | +2.00 (computed) |
| 019 | Tue 04-30 / Wed 05-01 (FOMC) | ES/NQ | no trade | – | – | – | – | "not enough confluence"; sat out FOMC | – |
| 020 #1 | Thu 05-02 ~11:00 | NQ | long | 4h/1h → 15m breaker → 5m | ≈17524 | ≈17444 | 17674.75 | win (inferred) | unknown (partials; ≈1.9 planned) |
| 020 #2 | 05-02 ~11:45 | ES | long | 4h → 15m breaker → 5m/15m close | 5064.00 | 5047.00 | 5090.00 | win (inferred) | +1.53 (computed) |
| 020 #3 | Fri 05-03 ~12:00 (NFP day) | ES | long | 4h/1h → 1h FVG → 5m | 5148.50 | 5141.00 | 5161.50 | still open at video end | unknown (1.73 planned) |
| 021 #1 | Mon 05-06 14:23 | ES | long | 4h/1h → 5m lows → 1m | 5193.25 | ≈5189.5 | 5198.50 | win (heard) | ≈+1.4 (inferred) |
| 021 #2 | 05-06 14:23 | NQ | long | 4h/1h → 5m lows → 1m | 18134.75 | 18123.50 | 18158.50 | win (inferred) | +2.11 (computed) |
| 021 #3 | 05-06 14:52 | NQ | long (add-on) | 1m | 18142.00 | 18134.25 | 18158.50 | loss (heard) | −1.00 (computed) |

**Running tally, batches 1–4 (unverified):**
- 20 trades: 12 wins, 5 losses, 3 unknown.
- R is known for 15 trades; the average is about +0.9R.

## 2. Recurring setup patterns
- **Still 100% with the 4h/1h bias:** 20 of 20 trades. This batch was all longs, in a
  rising late-April/May market.
- **The trigger:** a sweep of lows (the NY-open flush, 1h or 5m lows), then a lower-timeframe
  confirmation. The confirmation varies:
  - a 5m or 1m break of structure;
  - a 1m **inverse FVG** (a close back through a gap);
  - a bullish candle closing out of a 15m **breaker block** or the range midpoint.
- **SMT divergence** between ES and NQ appears as extra confluence (018).
- **Afternoon trades show up:** the PM session at 14:23–14:52 (021). Morning entries still
  dominate overall.

## 3. Contradictions and missing information
- **The time window.** He had said he prefers the first hour and avoids slow afternoons; 021 is
  an afternoon session with 3 trades, 2 wins and 1 loss.
- **Adding to a winner.** The 021 add-on lost, and he says he shouldn't have taken it. There's no
  stated rule for when adding is allowed.
- **Exits.** 020 #1 took partial profits at unshown levels, and 020 #3 was left running while he
  left for a flight. Neither exit can be verified.
- **News.** He sat out FOMC day (019) but traded late morning on NFP day (020 #3). The rule is
  still not objective.

## 4. Hypotheses (updated)
- **H1 (bias filter):** 20/20. It's strongly consistent, but untested against trades he skipped.
- **H5 (time window):** 13 of 20 entries before 10:30 ET; now 3 afternoon entries too. Test by
  time bucket.
- **New H10:** add-ons (a second entry in the same direction while the first is open) have lower
  expectancy than first entries. **Test:** first entry only vs. allowing add-ons.
- **New H11:** an ES/NQ SMT divergence at the sweep improves results. **Test:** tag the sweeps
  where only one index made a new extreme.
