# Batch 7: videos 32, 33, 35, 36, 37 (June 6 – June 27, 2024)

All 5 were accessed. (Video 34 is in batch 10.) There are 6 trades, all ES. No fills, size or
account P&L were shown, so every result is unverified. The prices come from drawn position boxes;
in 032 a chat overlay hides most labels. The transcripts are badly garbled.

## 1. Trade records

| Video | Date | Market | Side | Timeframes | Entry | Stop | Target | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|---|
| 032 #1 | Thu 06-06 ≈09:47 | ES | short | 15m levels → 1m FVG | ≈5370.00 | ≈5373.25 | 5363.00 | win (inferred; target reached ≈09:59, stop untouched; took a contract off at the lows) | unknown (planned 2.15) |
| 032 #2 | 06-06 ≈10:21–10:38 | ES | short (second trade in the range) | 15m → 1m | 5365.25 | ≈5372.00 | ≈5337.25 (moved) | unknown (still open at video end) | unknown (planned ≈4.1) |
| 033 | Mon 06-17 ≈09:46 | ES | short | 4h → 5m premium → 1m | 5494.75 | 5498.75 | ≈5486.00 (webcam covers the label) | loss (heard "stopped out"; chart agrees) | −1.00 (computed) |
| 035 | Tue 06-25 ≈10:05 | ES | long | 4h/1h → 5m → 1m | 5524.50 | 5520.25 | 5535.00 | unknown (still open; ≈+1.5R at video end) | unknown (planned 2.47) |
| 036 | Wed 06-26 10:01 | ES | long | 15m/1h/4h → 1m | 5528.25 | 5524.00 | 5535.00 | loss (tool: closed P&L −4.25) | −1.00 (computed) |
| 037 | Thu 06-27 ≈10:19 | ES | short | 1h ES/NQ SMT → 1m BOS | 5548.00 | 5555.00 | 5532.25 | win (inferred; target reached ≈11:35–11:43, stop untouched) | +2.25 (inferred, assumes a full exit at target) |

**This batch (unverified):** 2 wins, 2 losses, 2 unknown. R is known for 3 trades: +0.08R on
average. That's the weakest batch so far.

**Running tally, batches 1–7 (unverified):**
- 35 videos, 40 trades: 23 wins, 11 losses, 6 unknown.
- R is known for 30 trades; the average is about +0.88R (sum +26.4R). The average is falling as
  the sample grows: +0.97R after batches 5 and 6.

## 2. Recurring setup patterns
- **The 10:00 release again.** Three of five days had a 10:00 ET release (035, 036, 037), and
  the entries came 10:01–10:19. He repeats "wait for the 10am news".
- **SMT divergence as the bias source** (037): NQ took its 1h high while ES didn't, so he looked
  for shorts and waited for a 1m break of structure down. It won 2.25R. 035 also used SMT (open).
- **Sweep, then imbalance:** a sweep of the pre-open high or low, then an entry in the 1m/5m
  imbalance it left (032 #1, 036).
- **Partial profits are stated three times** (032, 035, 037) but never shown with prices.

## 3. Contradictions and missing information
- **Entering one minute after the release.** 036 went long at 10:01, one minute after New Home
  Sales, on a 1m trigger alone. He says he should have waited for 5m confirmation. It was stopped
  by a sweep of the 15m low, then price rallied through his target. That was the right idea with
  the wrong timing.
- **A wrong daily bias.** 033 shorted a day he later calls bullish. The trade reached about
  +1.25R and then was stopped, because he held for the full target.
- **Trading without a bias.** He says he ideally has a strong daily bias; 037 had none going in
  (it came from the SMT after the news) and still won.
- **A second trade with double the risk** inside the range while the first was open (032 #2). He
  calls it wrong. The result is unknown.

## 4. Hypotheses (updated)
- **H3 (stop buffer):** 036 was stopped by a sweep of the 15m low before the move. That makes
  5 of 11 losses stopped by a small overshoot.
- **H5 (time window):** 27 of 40 entries before 10:30 ET, 1 unclear (10:21–10:38), 7 from 10:30
  to 12:30, 5 in the afternoon.
- **H7 (news, before vs after):** after a 10:00 release: 3 wins, 2 losses, 2 unknown. Entries in
  the first minute after the release look worse (036). **Test:** wait at least one 5m close
  after the release.
- **H11 (SMT):** SMT trades with a known result: 5 wins, 0 losses (035 still open).
- **H13 (forcing, no confirmation):** 4 losses fit now (025, 027, 028 #1, 036).
- **H15 (partials):** 033 was up about +1.25R before it lost 1R. Half off at +1R would have
  turned it into roughly breakeven. That supports testing H15.
- **New H16:** a 1m trigger needs a 5m close in the same direction before entry. **Test:** 1m
  trigger alone vs 1m trigger plus a confirming 5m close.
