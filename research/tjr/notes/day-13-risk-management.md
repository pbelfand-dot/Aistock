# Boot Camp Day 13: Risk Management

Source: video (≈17 min, talking to camera, no charts). Rough offline transcript; the points
below are clear despite that.

## What he teaches
- **Risk 1–3% of the account per DAY in total**, not per trade. Split it: e.g. 2 trades at 1.5%
  each, or 3 trades at 1%. Fewer setups is fine; some days there are none.
- **Size every trade from the stop:** position size = money you're willing to lose ÷ distance to
  the stop (he points to any "position size calculator").
- Why: at 1% risk you'd need ~100 losses in a row to blow up the account. Risking 20–30% a trade
  empties it in days.
- **Discipline over excitement:** decide the day's trades in advance and don't add more. The moment
  emotion takes over (revenge trades, "one more"), you lose. Treat a small account as if it were
  large.
- Expect losses early: he says most people lose money in their first year or two ("tuition").
  Learn the skill; the money follows. No get-rich-quick.

## What this means for the bot
- Add risk-based sizing: size = (account × risk%) ÷ (entry − stop), capped by cash.
- A **daily risk budget**: stop opening trades once the day's planned risk (default 2%) is used,
  on top of the bot's existing 3% daily loss limit.
- A cap on trades per day (default 2 for TJR-style entries).
- The bot already can't feel emotions; the rules above are what keep it from "overtrading" when a
  strategy fires too often.
