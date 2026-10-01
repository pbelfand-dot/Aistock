# Shorting: why Kestrel doesn't (and what would have to change)

Kestrel only buys (long only). It never sells short and never borrows. The owner asked to add shorting
"if it benefits the AI"; the answer for now is no, for these reasons:

- **The real-money plan can't short.** Alpaca only allows short selling with $2,000 or more of account
  equity, and only for easy-to-borrow stocks (Alpaca's "Margin and Short Selling" docs). The plan's real
  money is $50. Kestrel runs Schwab and Webull as cash accounts, and short selling needs a margin account.
- **Paper shorts would test something the real account can't do,** so their results wouldn't carry over.
- **The evidence is weak or negative:**
  - TJR's model on daily charts: shorts lost (-0.24R per trade); see 30-research-findings.md.
  - The stocks-in-play breakout study (Zarattini, Barbon & Aziz 2024) traded long AND short and never
    reported the short side on its own.
  - Momentum's short side is where "momentum crashes" come from: after a market drop, beaten-down stocks
    can rebound violently, and a strategy short those losers loses badly exactly when the market recovers
    (Daniel & Moskowitz, "Momentum Crashes", Journal of Financial Economics, 2016).
- **A short's loss has no ceiling** (a stock can keep rising), and the busy stocks in play are the kind
  that get squeezed.

What could change it: pretend-only short trades in the strategy comparison (proposed, not built yet) to
measure whether shorting would have helped, AND an account of $2,000+ at a broker that allows it.
