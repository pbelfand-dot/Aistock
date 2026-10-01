# Hard safety rules (always true)

- **Never borrows.** It spends only cash, and never more than the real-money cap set in Setup
  (planned: $50 per broker).
- **Real money needs three locks:**
  - the desk earned it: study, then plan, then paper results that pass;
  - the owner typed the confirmation;
  - `LIVE_TRADING_ENABLED=true` is set on the Mac.
- **Emergency stop:** the owner types SELL EVERYTHING; the bot sells what it owns and halts.
  **Pause:** no new trades; stop-losses still protect positions.
- **Stop-losses** rest at the broker, so a sleeping laptop can't stop a falling position from being sold.
- **Good faith violations (cash accounts, e.g. Schwab).**
  - What one is: buying with money from a sale that hasn't settled yet, then selling before it
    settles. Three in 12 months and Schwab restricts the account for 90 days.
  - The bot spends settled money only. Sale money settles T+1 (one business day). Bank holidays
    such as Columbus Day and Veterans Day don't count.
  - A position bought with unsettled money (it shouldn't happen) is held until the money settles.
    Only the typed emergency stop may sell it early, and that's counted.
  - With $50 at Schwab, this means about one full round trip per day at most.
- **Alpaca:** it covers unsettled money itself, so there are no good faith violations there. It
  dropped the pattern-day-trader limit in 2026 (FINRA retired the rule).
- **Fractional shares:** Alpaca (and the simulation) buy parts of a share, at least $1 at a time, only
  for stocks Alpaca allows; a swing position's overnight stop covers its whole shares and the bot watches
  the fraction itself. Schwab's API trades whole shares only (with $50, only stocks under about $50 fit);
  Webull's fractional orders aren't confirmed, so Webull gets whole shares too. The $50 real-money test
  starts at Alpaca.
- **Schwab login lasts 7 days.** The owner logs in again from Setup; an expired login means no Schwab trading.
- **Keys and settings live only on the Mac** (`~/AITrader`) and survive updates.
