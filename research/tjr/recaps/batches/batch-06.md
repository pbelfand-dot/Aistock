# Batch 6: videos 27–31 (May 28 – June 5, 2024)

All 5 were accessed. There are 6 trades and 1 no-trade day (030). No fills, size or account P&L
were shown, so every result is unverified. The transcripts are badly garbled in all five. Prices
come from chart labels and position-box edges.

## 1. Trade records

| Video | Date | Market | Side | Timeframes | Entry | Stop | Target | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|---|
| 027 | Tue 05-28 ≈10:13 | ES | short | 4h → 5m imbalance → 1m | 5319.75 | ≈5323.50 | ≈5307.50 | loss (heard "after I got stopped") | −1.00 (inferred) |
| 028 #1 | Wed 05-29 ≈09:40 | NQ | short | 5m → 1m | 18796.75 | ≈18819.00 | ≈18722.50 | loss (price went through the stop by ≈09:50) | −1.00 (inferred, assumes no partial) |
| 028 #2 | 05-29 ≈10:24 | ES | long | 15m/5m → 5m FVG 50% → 1m | 5291.75 | ≈5286.50 | ≈5298.40 | win (inferred; target reached ≈10:38) | unknown (half off, rest to breakeven; exits not shown) |
| 029 #1 | Mon 06-03 ≈10:01 | NQ | short | 4h → 5m FVG → 1m | 18676.25 | ≈18729.00 | 18617.00 (moved from 18638.25) | unknown (he may have got out early) | unknown |
| 029 #2 | 06-03 10:31 | NQ | short | 4h → range equilibrium → 1m BOS | 18681.75 | 18702.25 | 18588.50 | win (tool: closed P&L 93.25) | +4.55 (computed, matches the tool) |
| 030 | Tue 06-04 | NQ/ES | no trade | – | – | – | – | range day; the long he wanted after JOLTS never came (a drawn example would have lost) | – |
| 031 | Wed 06-05 ≈10:27 | ES | long | 1h → 1m BOS + FVG | 5321.75 | 5315.25 | 5330.75 | win (inferred; target hit, stop untouched) | +1.38 (computed) |

**This batch (unverified):** 3 wins, 2 losses, 1 unknown. R is known for 4 trades; their average
is +0.98R, most of it from one 4.55R win.

**Running tally, batches 1–6 (unverified):**
- 30 videos, 34 trades: 21 wins, 9 losses, 4 unknown.
- R is known for 27 trades; the average is about +0.97R (sum +26.2R).

## 2. Recurring setup patterns
- **The 10:00 ET release is the clock.** Four of five days had a 10:00 release (CB Consumer
  Confidence, ISM twice, JOLTS). He says he "always waits for the news release to come out" before
  trading (029, 030, 031). Five of the six entries came 10:01–10:31.
- **Equilibrium entries.** He waits for price to retrace to the 50% of the morning range or of a
  5m FVG, then needs a 1m break of structure (029 #2, 028 #2). The best trade of the batch (4.55R)
  was this setup.
- **SMT again:** 028 #2 used it (ES made a lower low, NQ a higher low) and won.
- **Stated exit rule:** take half off at the first target and move the stop to breakeven for the
  rest (028). That's the first explicit partial-profit rule in the videos.

## 3. Contradictions and missing information
- **News days.** H7 said red-news days are worse. This batch he trades right after the 10:00
  release and does well (2 wins, 1 loss, 1 unknown after 10:00). The difference may be
  *before* the release (skip) vs *after* it (trade the reaction).
- **Chasing.** 027 lost because he sold "way too late off of that extension down". 028 #1 lost
  because he "wanted this one a little bit too bad" and got "overconfident". Both are the same
  failure as 025 (forcing): no fresh, patient trigger.
- **Exits.** The partial-profit rule (028) isn't followed or shown in other trades, where boxes
  run to a single target. 029 #1's target was moved mid-trade.

## 4. Hypotheses (updated)
- **H5 (time window):** 22 of 34 entries before 10:30 ET, 7 from 10:30 to 12:30, 5 in the
  afternoon.
- **H7 (news):** refine to *before vs. after*. **Test:** skip the 30 minutes before a red 10:00
  release; compare entries in the 30 minutes after it with the same setup on non-news days.
- **H13 (forcing/chasing):** now 3 losses fit (025, 027, 028 #1). **Test:** require a coded
  trigger, and forbid entries more than about 1.5×ATR(5m) from the move's start (chasing).
- **New H14:** the equilibrium entry (the 50% of the morning range or of a 5m FVG, then a 1m
  BOS) is his highest-quality setup. **Test:** entry at the 50% level vs. at the gap's edge.
- **New H15:** half off at the first target, rest to breakeven, beats a single full target.
  **Test:** simulate both exits on the same entries.
