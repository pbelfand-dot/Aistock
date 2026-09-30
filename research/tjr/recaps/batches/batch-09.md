# Batch 9: videos 40–43 (July 17–25, 2024) and video 1 (April 17, 2026)

All 5 were accessed. There are 6 trades. No fills, size or account P&L were shown, so every
result is unverified. The transcripts are almost unreadable.

Video 1 is a 100-minute live stream from 2026. It produced only one picture, the final frame, so
its first trade has no prices at all. The long's R is known only for its last portion (≈+12R,
from an estimated stop). The whole-trade R is recorded as unknown, like the other partial-exit
trades, so one estimate doesn't swing the average.

## 1. Trade records

| Video | Date | Market | Side | Timeframes | Entry | Stop | Target | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|---|
| 040 | Wed 07-17 ≈10:26 | NQ | long (against the day's drop) | 4h/1h discount → 5m → 1m | 20138.25 | 20098.00 | ≈20207 | loss (price went through the stop from ≈11:05; he says "unfortunately") | −1.00 (inferred) |
| 041 | Thu 07-18 ≈10:04 | NQ | long | 1h/15m → 1m zone | 20075.75 | 20043.00 | 20162.25 | loss (stopped ≈10:29, after reaching +0.95R) | −1.00 (computed) |
| 042 | Mon 07-22 ≈09:55 | NQ | short | 4h/1h → sweep of Friday's high → 1m BOS/IFVG | 20002.25 | 20027.75 | 19932.00 | win (tool: closed P&L 70.25 pts) | +2.75 (computed, matches the tool) |
| 043 | Thu 07-25 ≈09:53 | ES | short | 4h → 1m imbalance rejected | 5465.50 | 5470.75 | 5451.00 | win (target reached ≈10:00) | +2.76 (computed, matches the tool) |
| 001 #1 | Fri 2026-04-17 ≈09:47 | NQ | short | 1m BOS confirmed by ES | – | – | – | loss (heard "we lost on the first initial short") | unknown |
| 001 #2 | 2026-04-17 ≈09:50 | NQ | long | all-time-high context → 1m IFVG + ES BOS | 26704.00 | ≈26694 | 26863.50 | win (claims $75,210 for the day, unverified) | unknown (last portion ≈+12R) |

**This batch (unverified):** 3 wins, 3 losses. R is known for 4 trades; their average is
+0.88R.

**Running tally, batches 1–9 (unverified):**
- 45 videos, 49 trades: 29 wins, 14 losses, 6 unknown.
- R is known for 37 trades; the average is about +0.95R (sum +35.1R).
- This includes one correction: video 193 (batch 10) showed that 020 #3 (May 3, ES long), open in
  its own video, closed at its target for +1.73R. It's counted once, under 020.

## 2. Recurring setup patterns
- **The simplest setup won twice:** a sweep of an obvious high (042: Friday's high), then a 1m
  break of structure or inverse FVG, then an entry with the target at the nearest swing. He
  calls it probably "the most simple" setup.
- **All 6 entries were 09:47–10:26 ET.**
- **Two-index confirmation (001).** To go long, he waits for the *weaker* index (NQ) to invert
  its bearish gap while the stronger one (ES) breaks structure up. For a short it's the reverse.
  This is SMT used as a confirmation rule.

## 3. Contradictions and missing information
- **Counter-trend longs lost both times** (040, 041). 040 was a news-driven, one-way sell-off;
  he calls it "catching a falling knife" and says he entered without the higher-timeframe
  confirmation he wants. In 041, the obvious sell-side level below hadn't been taken yet; price
  swept it right after his entry and stopped him.
- **Trading against his own bias:** 043 shorted against a bullish pre-session bias and won 2.76R.
  In 001 he shorted against his bullish view and lost. So far the bias isn't applied the same
  way every time.
- **Stated rule vs. what he did (001):** he says ES was the better index to buy but traded NQ.

## 4. Hypotheses (updated)
- **H2 (sweep required):** 041 supports variant (a): enter only after the nearest opposing
  liquidity has been swept. Entering before the sweep got him stopped by it.
- **H5 (time window):** 35 of 49 entries before 10:30 ET, 1 unclear, 8 from 10:30 to 12:30, 5 in
  the afternoon.
- **H13/H16 (forcing, 5m confirmation):** 040 fits both, by his own account. That's 5 losses for
  H13 (025, 027, 028 #1, 036, 040).
- **New H18:** for a long, both indexes must confirm: the weaker index inverts its bearish gap and
  the stronger one breaks structure up (the reverse for shorts). **Test:** one-index trigger vs a
  two-index confirmation.
- **New H19:** no counter-trend entry on a one-way trend day. **Test:** skip entries against the
  day's direction when the first hour's move is over about 2×ATR(1h) and no 5m break of
  structure has formed.
