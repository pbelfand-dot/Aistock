# What drives TJR's winning and losing trades: living hypotheses

Updated after each batch. Each hypothesis says what would test it on historical data. Counts are
from `trades.csv`. Nothing here is proven: the trades are unverified recap drawings.

| # | Hypothesis | Evidence so far | How to test |
|---|---|---|---|
| H1 | Trading only in the direction of the 4h+1h structure is the core filter | 8/8 trades went with the bias (batch 1) | Backtest the 5m entry model with and without the HTF-bias filter |
| H2 | Entry = 5m BOS in the bias direction, then a retrace into the 5m FVG/IFVG from that leg, then entry on rejection | 8/8 described this way; sweep first in 5/8 | Code the entry exactly; run variants: (a) sweep required, (b) no sweep |
| H3 | Stops just beyond the last 5m swing get wicked on noise; a buffer helps | 3 of 4 losses stopped by a few points or one spike before the move worked (Feb 21 ×2, Mar 22) | Compare stop = last swing vs. session extreme vs. swing + 0.5×ATR(5m) |
| H4 | Targets = next HTF liquidity (prior 15m/1h/4h swing), not a fixed R | Planned R:R from 0.61 to 6.19 | Compare liquidity target vs fixed 1R/2R/3R, and a minimum-R filter |
| H5 | The first ~90 minutes after the 9:30 ET open is his main window | 10 of 13 entries 09:20–10:30; 2 near 11:50; 1 at 15:00 | Split results by entry time bucket |
| H6 | ES and NQ at the same time = one bet, twice the risk | 2 days with both; both lost together once | Treat same-direction ES+NQ as one position in sizing |
| H7 | Red-news days are worse | Both Feb 21 losses on an FOMC-minutes day; Feb 22 (news-heavy) was a win; he sat out Mar 6, 7, 8, 12 (Powell, NFP, CPI) | Tag each session with red-impact US releases (CPI, NFP, FOMC, Powell, PPI); compare |
| H8 | Two-step trigger: price reaches a pre-marked level (sweep or pullback into a zone), then a lower-timeframe close confirms (BOS/IFVG); a touch alone = no trade | Every plan in batch 2 was stated this way | Code both steps; compare with entering on the touch |
| H9 | Entries inside an intraday range that already chopped for over an hour do worse | Mar 22 NQ short: entered mid-chop, stopped by one spike | Measure range width/touch count in the 60 min before entry; compare results |
