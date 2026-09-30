# TJR's model (learned from his videos)

## Evidence so far
- Videos analyzed: 45 of 200. Trades recorded: 49 (29 wins, 14 losses, 6 unclear).
- Average R where known (37 trades): +0.95.
- Verified by fills or broker P&L: 0. Everything else is his drawings and words.
- The bot does NOT trade this yet: it trades only after an intraday history test passes, and then only in Stage 2 paper trading.

## The rulebook (draft)
Every rule here is exact enough to code. Where the videos so far leave something open, the rule
shows the **default we chose** and it's listed under "Open questions" until a later video settles
it. Notes per video: [`notes/`](notes/).

## The model in one line
Price **sweeps a prominent liquidity level**, then **breaks structure the other way**, then comes
back into the **fair value gap** that break left behind: that's the entry. Stop beyond the sweep,
target the opposite liquidity. (Days 10, 12, 14)

## 1. Liquidity levels (what can be swept)
- **Prominent swing highs/lows** (Day 12): a swing high is a bar whose high is the highest of the
  `k` bars on each side (default `k = 3`). It's *prominent* if price later broke structure from it
  (it started a leg), not just any wiggle.
- **Previous day high / low** (Day 10's "on every timeframe").
- **Pre-market high / low** for US stocks (his "session highs/lows": Asia/London in forex).
- Stops and breakout orders sit just beyond these levels (Day 10); that's why they get swept.

## 2. The sweep
- **Bearish sweep:** a bar trades above a level (high > level) and the move up doesn't continue.
  **Bullish sweep:** a bar trades below a level and doesn't continue.
- Default: the sweep counts if a break of structure (below) follows within `N = 12` bars.

## 3. Confirmation: break of structure (Day 12)
- After a bearish sweep: a bar **closes below the most recent swing low that formed the swept
  high** ("the low that created the high"). Mirror for bullish.
- No break of structure, no trade. "Don't trade just because a level was swept."

## 4. Entry: the fair value gap (Days 12, 14)
- A **bearish gap**: three consecutive bars where bar 1's low is above bar 3's high; the gap is the
  space between them. **Bullish gap:** bar 1's high below bar 3's low.
- Use the gap created inside the break-of-structure move. Enter when price trades back into it
  (default: a limit order at the gap's near edge).
- Default minimum gap size: 0.05% of price (ignore tiny gaps). The gap expires if not reached
  within `M = 24` bars or if price closes through its far edge.

## 5. Stop, target, size (Days 12, 13)
- **Stop:** just beyond the sweep's extreme (the high of the swept bar for shorts).
- **Target:** the next prominent level on the other side (opposite liquidity). If that gives less
  than 2× the risk, skip the trade (default minimum reward/risk = 2).
- **Size from the stop:** shares = (account × risk per trade) ÷ (entry − stop), capped by cash
  (fractional where the broker allows).
- **Risk per day: 1–3% of the account in total** (default 2%, split across at most 2 trades).
  The bot's own limits (daily loss limit, kill switch) still apply on top.

## 6. Timeframes
- He says it works on every timeframe. For the bot:
  - **Day desk (Stage 2):** levels from the previous day and pre-market; sweep + break of
    structure on 5-minute bars; entry on 1-minute bars inside the gap. Flat by the close.
  - **Swing desk (Stage 2):** the same logic on daily bars (sweep of a prominent daily high/low,
    break of structure, daily gap), held for days.

## 7. When not to trade (Days 11, 13)
- **No new trades on major scheduled US news days** (Fed decision, CPI, jobs report): default rule,
  to be tested.
- No more trades once the day's risk budget or trade count is used ("never overtrade").
- No bigger size after losses (no revenge trading).

## 8. How we'll know if it works
- Backtest on history first (5-minute data for the day desk, daily for swing), with costs.
- Then Stage 2 paper for 30 trading days, next to Stage 1, and it must make money and beat holding
  SPY. Judge on many trades, not one (Day 11).

## Open questions (defaults above until a video settles them)
- Exact definition of "prominent" (how big a swing counts). Default: pivot `k = 3` that later
  caused a break of structure.
- Does the sweep bar have to *close back* inside the level, or is a wick through enough?
- How deep into the gap to enter (near edge, middle, or wait for a lower-timeframe reaction)?
- Which timeframe pairs he uses for stocks (e.g. 15-minute sweep, 1-minute entry)?
- Order blocks and "equilibrium" (his next lessons): how they add to or replace the gap entry.
- His exact time windows (New York open? first 2 hours?) and his news-day rule.

## What seems to drive wins and losses (hypotheses to test)
Updated after each batch. Each hypothesis says what would test it on historical data. Counts are
from `trades.csv`. Nothing here is proven: the trades are unverified recap drawings.

| # | Hypothesis | Evidence so far | How to test |
|---|---|---|---|
| H1 | Trading only in the direction of the 4h+1h structure is the core filter | Every trade with a stated bias went with it: 27 of 28 (023's wasn't stated). The bias timeframe varies, 15m to daily (batch 5) | Backtest the 5m entry model with and without the HTF-bias filter |
| H2 | Entry = 5m BOS in the bias direction, then a retrace into the 5m FVG/IFVG from that leg, then entry on rejection | 8/8 described this way; sweep first in 5/8; Jul 18: entered before the obvious sell-side level was swept and got stopped by that sweep | Code the entry exactly; run variants: (a) sweep required, (b) no sweep |
| H3 | Stops just beyond the last 5m swing get wicked on noise; a buffer helps | 5 of 11 losses stopped by a few points or one spike before the move worked (Feb 21 ×2, Mar 22, May 13, Jun 26) | Compare stop = last swing vs. session extreme vs. swing + 0.5×ATR(5m) |
| H4 | Targets = next HTF liquidity (prior 15m/1h/4h swing), not a fixed R | Planned R:R from 0.61 to 6.19 | Compare liquidity target vs fixed 1R/2R/3R, and a minimum-R filter |
| H5 | The first ~90 minutes after the 9:30 ET open is his main window | 35 of 49 entries 09:20–10:30; 1 unclear; 8 at 10:30–12:30; 5 in the afternoon (14:23–15:00) | Split results by entry time bucket |
| H6 | ES and NQ at the same time = one bet, twice the risk | 2 days with both; both lost together once | Treat same-direction ES+NQ as one position in sizing |
| H7 | Red-news days are worse | Both Feb 21 losses on an FOMC-minutes day; Feb 22 (news-heavy) was a win; he sat out Mar 6, 7, 8, 12 (Powell, NFP, CPI) | Tag each session with red-impact US releases (CPI, NFP, FOMC, Powell, PPI, ISM, JOLTS). Refined in batch 6: he waits for the 10:00 release, then trades the reaction (4 wins, 2 losses, 2 unknown after it, incl. Powell day Jul 9; the entry one minute after the release lost). Compare the 30 min before vs after a release, and entries before vs after the first 5m close |
| H8 | Two-step trigger: price reaches a pre-marked level (sweep or pullback into a zone), then a lower-timeframe close confirms (BOS/IFVG); a touch alone = no trade | Every plan in batch 2 was stated this way | Code both steps; compare with entering on the touch |
| H9 | Entries inside an intraday range that already chopped for over an hour do worse | Mar 22 NQ short: entered mid-chop, stopped by one spike | Measure range width/touch count in the 60 min before entry; compare results |
| H10 | Add-ons (a second entry while the first is open) do worse than first entries | Mixed: the May 6 NQ add-on lost (he says he shouldn't have); the May 23 ES add-on won 1.86R but came within 0.7 pt of the stop | Compare first entries only vs allowing add-ons |
| H11 | An ES/NQ SMT divergence at the sweep improves results | SMT trades with a known result: 8 wins, 0 losses (Apr 29, May 16, May 23 ×2, May 29, Jun 27, Jul 8, Jul 9); 2 unknown. Easy to cherry-pick in recaps: test every NY-open sweep | Tag sweeps where only one index made a new extreme; compare |
| H12 | One re-entry after a stop-out is fine if price closes back through the same zone within 15 minutes | May 13: stopped at −1R, re-entered the same zone and won 2.89R | Allow 0 vs 1 re-entry per zone |
| H13 | Trades without a fresh trigger ("forcing it") do worse | 5 losses fit: Jul 17 (long into a news-driven sell-off, "catching a falling knife"), Jun 26 (1m trigger alone, one minute after the news), May 17 ("trying to find a reason to get into a trade"), May 28 (sold "way too late" after the expansion), May 29 NQ ("wanted this one a little bit too bad"); May 23 #2 ("purely on price coming off") was the smallest win | Require a coded trigger (BOS or IFVG close); forbid entries more than ~1.5×ATR(5m) from the move's start |
| H14 | The equilibrium entry (retrace to the 50% of the morning range or of a 5m FVG, then a 1m BOS) is his best setup | 3 wins with a known result: Jun 3 NQ short at the range 50% (4.55R), May 29 ES long at the FVG 50%, Jul 9 NQ long at the 1h 50% (1.62R first partial) | Entry at the 50% level vs at the gap's edge |
| H15 | Half off at the first target and the rest to breakeven beats one full target | Stated as his rule on May 29 and Jun 6/25/27, never shown with prices; Jun 17 reached +1.25R before losing 1R | Simulate both exits on the same entries |
| H16 | A 1m trigger needs a confirming 5m close before entry | Jun 26 and Jul 17: 1m-only entries lost, and both times he says he should have waited for the 5m / higher timeframe | 1m trigger alone vs 1m trigger plus a 5m close in the same direction |
| H17 | A 4h-close bias rule works: bullish until a bearish 4h close below the last 4h higher low (and vice versa) | Stated as his weekly plan (Jul 6 forecast) | Code it as the only bias filter under H2's entry; compare with no bias filter |
| H18 | Two-index confirmation: for a long, the weaker index inverts its bearish gap while the stronger breaks structure up (reverse for shorts) | Stated as his rule in the Apr 2026 live session; the confirmed long won | One-index trigger vs two-index confirmation |
| H19 | No counter-trend entries on a one-way (trend or news) day | Jul 17 and Jul 18 counter-trend longs both lost 1R | Skip entries against the day's direction when the first hour moved more than ~2×ATR(1h) and there's no 5m BOS |
