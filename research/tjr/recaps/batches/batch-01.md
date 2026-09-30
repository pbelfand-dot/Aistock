# Batch 1: videos 2–6 (dated trade recaps, Feb 20–28, 2024)

All 5 videos were accessed and analyzed from full-size chart pictures plus a rough offline
transcript. Full records: `records/002.json` … `records/006.json`. Cumulative table: `trades.csv`.

## 1. Trade records

Prices are from TradingView's position tool, read off the chart. **No video showed broker fills,
position size or account P&L, so nothing here is verified P&L.** The boxes are drawn during the
recap, after the fact.

| Video | Date | Market | Side | Timeframes (bias → setup → entry) | Entry | Stop | Target | Exit | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|---|---|
| 002 #1 | Tue 2024-02-20 ~09:55 ET | ES | short | 1h/4h → 5m → 5m | 4991.25 | 4995.25 | 4969.25 | stopped (seen) | loss | −1.0 (computed) |
| 002 #2 | 02-20 ~11:55 | ES | short | 1h/4h → 5m → 5m | 4988.25 | 4994.75 | 4969.25 | unclear; target only touched | win? (inferred) | unknown (planned 2.9) |
| 002 #3 | 02-20 ~11:55 | NQ | short | 1h/4h → 5m → 5m | 17545.50 | 17581.25 | 17466.25 | target hit (seen) | win | +2.22 (computed) |
| 003 #1 | Wed 02-21 ~10:45 | ES | short | 1h/4h → 5m → 5m | 4976.75 | 4983.25 | ≈4936.5 | stopped | loss | −1.0 (computed from the tool) |
| 003 #2 | 02-21 ~10:25 | NQ | short | 1h/4h → 5m → 5m | 17464.25 | 17512.75 | 17329.00 | stopped (inferred) | loss | −1.0 (inferred) |
| 004 #1 | Thu 02-22 ~10:00 | NQ | long | 4h/1h → 5m → 5m/1m | 17922.25 | 17863.75 | 18026.25 | target reached (inferred) | win | +1.78 (computed, assumes exit at target) |
| 005 #1 | Mon 02-26 ~15:00 | NQ | short | 1h/4h → 15m → 5m | 18013.75 | 18046.75 | 17922.00 | manual ≈17960 (inferred) | win | +1.6 (inferred; +1.15 vs original stop) |
| 006 #1 | Wed 02-28 ~09:20 | NQ | short | 4h/1h → 5m → 5m | 17925.50 | 17958.00 | 17905.75 | target (inferred) | win | +0.61 (computed) |

**Tally (unverified):**
- 8 trades: 5 wins (3 of them inferred), 3 losses.
- R is known for 7 trades. They sum to +3.2R, an average of +0.46R, and several values are
  inferred.

**Missing in all 5 videos:**
- position size or contracts;
- fills and the actual exit, except where price visibly hit the stop or target;
- $ P&L.

## 2. Recurring setup patterns
1. **Only index futures:** ES and NQ (NQ in 6 of 8).
2. **The same timeframe stack every time:** bias from **4h + 1h** structure, entry on the
   **5m**. The 15m is used for the target or for confirmation.
3. **The trade always goes with the 1h/4h bias** (8 of 8): 7 shorts in a down-leg, and 1 long
   after the 4h broke structure up.
4. **The entry sequence:**
   - a 5m break of structure (BOS) in the bias direction;
   - then price comes back into the 5m fair value gap (FVG) or inverted gap (IFVG) left by that
     move;
   - he enters on the rejection.
   - A liquidity sweep came first in 5 of 8 trades. He says it's "not strictly required" (Feb 20).
5. **Stop:** just beyond the latest 5m swing high/low or the rejection wick. It's tight: 4–6.5
   points on ES and 33–58 points on NQ.
6. **Target:** the next higher-timeframe liquidity: prior 15m, 1h or 4h swing lows/highs.
   Planned reward-to-risk varies widely, from 0.61 to 6.19.
7. **Time of day:**
   - 5 of 8 entries were within about 90 minutes of the 9:30 open;
   - 2 were around 11:50;
   - 1 was in the afternoon (15:00).
8. **The same idea on ES and NQ at once** (Feb 20 and Feb 21). On Feb 21 both were stopped by the
   same push.

## 3. Contradictions and missing information
- **The sweep rule.** He teaches sweep → BOS → FVG, but the Feb 20 NQ trade had no sweep.
- **Minimum reward-to-risk.** Our draft rulebook assumed 2R. The Feb 28 trade planned only 0.61R,
  and targets come from liquidity, not a fixed multiple.
- **News.** He says to wait out news (FOMC minutes, Feb 21), yet traded a news-heavy Feb 22 with
  entry around the 10:00 release. The Feb 21 losses came on an FOMC-minutes day.
- **Exits.**
  - Some exits were manual (Feb 26, about 17960 instead of the 17922 target).
  - One is unknown (Feb 20 #2, maybe partial profits).
  - "Target hit" is often inferred from candles, not from a fill.
- **Hindsight risk.** The boxes are drawn after the fact and were edited on screen (Feb 26 and
  Feb 28). Nothing proves they are the live orders.
- **The transcript** is too rough to confirm reasons, size or partial exits.

## 4. Hypotheses (updated) → see `HYPOTHESES.md`
- **Losses so far:** 2 of 3 came from stops placed just inside the morning range (Feb 21). Price
  wicked a few points past the swing high, then moved in the trade's direction. **Hypothesis:** a
  stop beyond the session high/low or with a volatility buffer turns some of these into wins.
  Test this against the tighter stop.
- **Wins so far:** all went with the 1h/4h bias, with entries in the first 90 minutes or at a clear
  range edge. Not yet separable from luck, with 8 trades.
- **The Feb 21 losses** came on a red-news day (FOMC minutes at 14:00). **Hypothesis:** red-news
  days are worse. Needs many more days.
