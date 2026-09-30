# Batch 10: videos 34, 193, 53, 54, 98 (June 2024, May 2024, 2025, 2026)

All 5 were accessed. There are 6 new trades.
- **193** is a weekly recap. Its one trade is 020 #3 (May 3, 2024), which was still open in its
  own video. 193 shows it closed at the target (+1.73R). The outcome moved to 020 #3, and it's
  counted once.
- **098** (Aug 2025) had no trade: the pullback he waited for never came.
- **053** (Feb 2026) and **054** (Jan 2025) are newer live sessions. They show the same model.

No fills, size or account P&L were shown, so every result is unverified.

## 1. Trade records

| Video | Date | Market | Side | Entry | Stop | Target | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|
| 034 #1 | Thu 2024-06-20 ≈10:26 | NQ | long | 20158.25 | 20136.25 | 20172.00 (TP1, hit) | unknown (the rest isn't shown) | unknown (TP1 part 0.63R) |
| 034 #2 | Fri 2024-06-21 ≈10:04 | ES | long | 5527.00 | 5520.50 | 5538.00 | unknown (small partial; 75% still open at breakeven) | unknown (planned 1.69) |
| 034 #3 | 2024-06-21 ≈10:05 | NQ | long | 19961.50 | 19932.25 | 19979.75 (TP1, hit) | win (TP1, then the rest stopped at breakeven) | unknown (between 0 and 0.62) |
| 098 | Wed 2025-08-20 | NQ/ES | no trade | – | – | – | bearish; wanted a 5m pullback that never came | – |
| 054 #1 | Thu 2025-01-23 ≈09:58 | NQ | long | 21897.50 | 21865.75 | 21951.00 | win (heard "made like two hundred") | unknown (planned 1.69) |
| 054 #2 | 2025-01-23 10:11 | ES | short | 6114.00 | 6118.75 | 6098.00 | loss (through the stop ≈10:38; traded while Trump was speaking) | −1.00 (inferred) |
| 053 | Tue 2026-02-17 ≈10:17 | ES | long | 6815.50 | 6800.00 | 6861.00 | win (partial at ≈6830.50, the rest stopped at breakeven) | unknown (between 0 and 0.97) |

**This batch (unverified):** 3 wins, 1 loss, 2 unknown. R is known for only 1 trade.

## 2. What this batch adds
- **His real exits are small.** In 034 ×3 and 053, the first partial came at or below 1R ("poor
  reward-to-risk", in his words). The rest was stopped at breakeven. The drawn boxes plan
  1.7–2.9R, but these wins were worth 0–1R.
- **Speeches are a no-trade.** He calls "don't trade while Trump is speaking" the key lesson of
  054: the ES short taken during the speech lost.
- **Patience rule.** In 098, no 5m retrace meant no trade, and he says "it's fine not to catch
  every trade". In 053: "no entry without an inversion (IFVG) on the indexes".
- **The model is stable from 2024 to 2026:** a sweep at the open, SMT, a 1m IFVG or BOS, a
  partial, then breakeven.

## 3. Checkpoint: what 50 videos say

**The tally (unverified):**
- 50 videos, 55 trades: 32 wins, 15 losses, 8 unknown. That's 68% wins among the 47 with a
  known result.
- R is known for 38 trades, averaging +0.90R (median +1.53R).

**Why the real number is probably lower:**
- **No trade shows broker fills.** Every dollar figure is his words or a video title.
- **R isn't known equally for wins and losses.** It's known for 14 of 15 losses (a stop is −1R)
  but for only 24 of 32 wins. The wins without an R are mostly small partial exits (0–1R).
- **Box R assumes a full exit at the target.** He often took partials below 1R.
- **Recap videos are chosen by him.** Days he didn't record can't be counted.

**What is consistent enough to test:**
1. Trade 09:20–10:30 ET: 41 of 55 entries.
2. Sweep of an obvious level (the pre-market, overnight or prior-day high/low), then a 1m break
   of structure or an IFVG close, then entry. Stop beyond the sweep; target the nearest opposing
   liquidity.
3. ES/NQ SMT at the sweep as a filter (H11, H18). SMT trades with a known result: 9 wins, 0
   losses, 3 unknown (034 #3 is new). This is also the easiest pattern to cherry-pick.
4. News: no entries before a 10:00 release or during a live speech. Wait for the first 5m close
   after the release (H7).
5. No counter-trend entries on a one-way day (H19). No entry before the obvious opposing
   liquidity has been swept (H2a).
6. Exits to compare (H15): a full target vs. a partial at 1R and then breakeven.

**What still can't be coded:** his daily bias. It comes from 15m, 1h, 4h or daily depending on
the day. The 4h-close rule from video 192 (H17) is the best candidate.

**Next:** test these rules on 1-minute ES/NQ history (Stage 2 prep, task H-list), with no
lookahead, commissions and slippage included, then walk-forward. The remaining 150 videos only
refine the list.
