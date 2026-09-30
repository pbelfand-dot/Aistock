# Batch 5: videos 22–26 (May 7 – May 23, 2024)

All 5 were accessed. There are 8 trades and no no-trade days. No fills, size or account P&L were
shown, so every result is unverified. The only trade evidence is TradingView position boxes, and
the transcripts are badly garbled in all five.

## 1. Trade records

| Video | Date | Market | Side | Timeframes | Entry | Stop | Target | Result | R (basis) |
|---|---|---|---|---|---|---|---|---|---|
| 022 | Tue 05-07 ≈14:43 | NQ | long | 15m → 5m → 1m | 18185.75 | 18173.25 | 18213.75 | win (inferred) | +2.24 (computed, assumes exit at target) |
| 023 #1 | Mon 05-13 ≈09:51 | NQ | long | 5m/1m imbalance → 1m | 18276.00 | 18258.50 | 18303.00 | loss (tool: closed P&L −17.50) | −1.00 (computed) |
| 023 #2 | 05-13 ≈10:00 | NQ | long (re-entry) | 1m | 18276.25 | 18267.00 | 18303.00 | win (inferred; the tool label may say "open P&L") | +2.89 (inferred, matches the tool) |
| 024 | Thu 05-16 10:15 | NQ | long | 1h/4h → 5m → 1m | 18700.75 | 18690.75 | 18716.00 | win (box shows target hit) | +1.53 (computed) |
| 025 | Fri 05-17 ≈10:07 | NQ | short | 4h → 15m/5m → 1m | 18634.75 | 18648.25 | 18617.00 | loss (tool: closed P&L −13.50) | −1.00 (computed) |
| 026 #1 | Thu 05-23 ≈12:05 | ES | short | daily gap / 5m → 1m | 5338.00 | 5341.25 | 5334.00 | win (box shows target hit) | +1.23 (computed) |
| 026 #2 | 05-23 ≈12:17 | ES | short | 5m → 1m | 5333.50 | 5341.50 | 5325.75 (from the box's R:R) | win (inferred) | +0.97 (computed) |
| 026 #3 | 05-23 ≈12:22 | ES | short (add-on) | 5m SMT + BOS → 1m | 5336.00 | 5341.50 | 5325.75 | win (box shows target hit) | +1.86 (computed) |

**This batch (unverified):** 6 wins, 2 losses; average +1.09R over 8 trades.

**Running tally, batches 1–5 (unverified):**
- 28 trades: 18 wins, 7 losses, 3 unknown.
- R is known for 23 trades; the average is about +0.97R (sum +22.2R).

## 2. Recurring setup patterns
- **The core sequence is unchanged:** a liquidity sweep, then a break of structure on a lower
  timeframe, then an entry at a fair value gap or an **inversion FVG** (a gap that price closes
  back through). He says his afternoon method is "pretty much the exact same" as the morning one
  (022).
- **ES/NQ SMT divergence** is now used as a trigger, not just extra confluence (024, 026). In 026
  he shorts the weaker index (ES).
- **Entries are on the 1m chart** in all 8 trades. The setup timeframe is 5m.
- **Short targets:** planned R:R ranged from about 1.0 to 2.9. Targets are the nearest liquidity
  (the session high, the London low, the pre-market high).
- **Time of day:** 4 of 8 entries were 09:51–10:15 ET. There was one afternoon entry (022, 14:43)
  and three at midday (026, 12:05–12:22).

## 3. Contradictions and missing information
- **Re-entries.** After being stopped (023 #1), he re-entered the same zone minutes later and won
  2.89R. Before this he had said add-ons were a mistake (021). **The rule for a second try is not
  stated.**
- **Forced trades.** In 025 he says he was "trying to find a reason to get into a trade". It lost
  1R. There's still no objective filter for "don't force it".
- **The bias timeframe varies:** 15m (022), 1h/4h (024), 4h (025), a daily gap (026), and
  "unknown" (023). H1 says 4h+1h. In practice, the bias source isn't fixed.
- **Add-ons again.** In 026 #3 he added a second short with the same stop while the first was
  losing. Both won, but the combined position came within about 0.7 points of the stop.
- **Exits.** 026 #1 took about 1:1 and missed the bigger move. It's still unclear when he holds
  and when he takes profit.

## 4. Hypotheses (updated)
- **H1 (bias filter):** every trade with a stated bias went with it (27 of 28; 023's bias wasn't
  stated). But the bias timeframe changes (15m to daily). **Test:** fix one definition (4h+1h structure) and test it alone.
- **H3 (stop buffer):** 023 #1 was stopped by a retest about 5 minutes after entry, then price
  went to the target. The stop was above the sweep wick, under the candle body. That makes 4 of 7
  losses stopped by a small overshoot. **Test:** stop at the sweep extreme vs. at the candle body.
- **H5 (time window):** now 17 of 28 entries before 10:30 ET, 6 at midday, 5 in the afternoon.
- **H10 (add-ons):** mixed. The 021 add-on lost; the 026 #3 add-on won. **Test** as planned.
- **H11 (SMT):** 3 more SMT trades, all winners (024, 026 #1, #3). **Test** as planned.
- **New H12:** one re-entry after a stop-out is allowed if price closes back through the same
  zone within 15 minutes. It worked once (023). **Test:** allow 0 vs. 1 re-entry per zone.
- **New H13:** "forcing" trades (no fresh trigger) do worse. 025 lost, and 026 #2 (entry
  "purely on price coming off") had the smallest win. **Test:** require every entry to have a
  coded trigger (BOS or IFVG close); drop entries without one.
