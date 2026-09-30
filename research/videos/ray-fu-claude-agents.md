# Two "Claude trading" TikToks (@ray_fu), Sept 2026: what we took and why

Our own notes; the videos themselves aren't stored here.

## Video B: "How to analyze the entire stock market with Claude" (agents)
- **Claim:** three Claude agents in a chain. A data agent pulls prices and "institutional options
  flow"; an analysis agent scores the gap between the price trend and the options bias (e.g. 78%
  calls while the price is flat); a trade agent calls "buy calls" or "buy puts", and "no edge" when
  they agree.
- **Evidence:**
  - Stocks with low put/call ratios from **buyer-initiated, opening** option trades beat high ones
    by ~40bp the next day and ~1% the next week (Pan & Poteshman 2006,
    https://www.nber.org/papers/w10925). The effect is stronger in small caps and far out-of-the-money
    options.
  - Large option trades in general are **not** predictive; only narrow kinds are (Jiang & Strong,
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3618427).
  - Options-based predictability disappears once real stock-borrow fees are counted (Illinois Gies, 2026).
- **Problems as shown:**
  - Public volume doesn't say who bought, so "78% calls" includes call sellers and hedgers.
  - The stocks shown (NVDA, AAPL, SPY) are where the effect is weakest.
  - The screens show SPY at $566.71; the real SPY closed at $764.20 on Sep 29, 2026, so the screens
    are mock-ups.
  - Trading options needs approval, doesn't fit $50, and loses to time decay.
- **Costs:** Alpaca's full options feed is $99/month; Unusual Whales' API is $150-375/month (2025).
  Alpaca's free "indicative" feed has each contract's daily volume, trades 15 minutes late. That's
  enough for a once-a-day check.
- **What we built:** `trader/aitrader/options_flow.py`, a daily watcher that flags gaps and grades
  them 5 trading days later against SPY. It never trades. We also built `trader/aitrader/agents.py`,
  the team (Scout, Analyst, Trader, Risk, Reviewer), so each decision's thinking is written down step
  by step.

## Video A: "Her Claude Fable trading bot makes her $3K/month" (advice, taken loosely)
- **Claim:**
  - Five markets: S&P 500, Nasdaq, Bitcoin, gold, oil.
  - Methods: a 15-minute mean-reversion "snap-back" (about -2.3 sigma from the 20-bar average),
    1-hour breakouts for Bitcoin, and 4-hour EMA 20/50 trend following for gold and oil.
  - Risk: a hard 1% stop, ATR-based position sizing, and a correlation filter (no new risk-on trade
    while S&P and Nasdaq are both long).
  - Two Claude briefings a day.
- **Red flags:**
  - The "live" SPX is 5,474 when the real level is about 7,640.
  - Gold shows $2,336 when GLD is at $383 (gold about $4,150).
  - A BTC price shows $32 trillion.
  - The morning brief's prices change between two frames of the same message.
  - "1% risk = $480" implies a $48K account, which doesn't fit a "+$118 day (+0.7%)".
  - The SPX stop is 6 points when the 15-minute ATR on its own screen is 28 points.
  - Both videos end in "comment STOCK for the guide", a lead-generation funnel.
- **Worth borrowing later:**
  - ATR-based sizing and stops (fixed % stops ignore how much each stock normally moves).
  - A correlation cap (8 momentum stocks can all be the same sector). This is now a Risk-agent
    check, warn-only by default.
  - A morning brief.
  - The snap-back as another method for the day desk to compare in its head.
