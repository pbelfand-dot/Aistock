# Challengers: new ideas must prove themselves before they trade

- **What** (challengers.py): other versions of a desk's method race the current one. The swing desk's
  challengers of `momentum`:
  - `momentum_plus`: ranks by residual momentum (the stock's own 12-1 month climb with the market's part
    taken out, divided by how jumpy it was; Blitz, Huij & Martens 2011), then prefers smooth climbs made of
    many small up days (frog in the pan; Da, Gurun & Warachka 2014) and stocks near their 52-week high
    (George & Hwang 2004). Same buy/sell bars, 200-day filter and S&P 500 filter.
  - `momentum_calm`: plain momentum with volatility scaling (Barroso & Santa-Clara 2015): new buys shrink
    (down to 30%) when its stocks have been much jumpier than usual over 6 months; below half size,
    holdings over twice the smaller limit are trimmed. Momentum's worst crashes came in stormy markets.
  - `momentum_plus_calm`: both.
- **Evidence, two kinds, always against the current method on the same stocks, money, rules and costs:**
  - history: all 8 years of daily prices replayed after every close. The stock list is today's (survivors),
    which flatters momentum; comparing two methods on the same list cancels much of that, not all.
  - forward: a shadow account per method (pretend money, simulated on the Mac) deciding at the desk's real
    decision time from the day the challenger was added. Journal lines from shadows are dropped.
- **Proven better means all of:** ahead over the history by a bootstrap p-value of 0.05 or less (stationary
  bootstrap, Politis & Romano 1994, keeps streaks together); a deflated Sharpe ratio of 0.95+ (Bailey & Lopez
  de Prado 2014: every idea ever tried is logged in the `trials` table and raises the bar); a worst drop at
  most 5 points deeper; at least 20 trading days of shadow trading and not behind there.
- **Then:** a pretend-money desk (in its head, paper) switches by itself ("CHALLENGER WON", journal and
  phone). A real-money desk never switches by itself: "CHALLENGER PROVEN", and the owner presses Use it in
  the Thinking tab. The old method stays in the race and can win its place back the same way.
- **Honest expectations:** most challengers will stay "not better" or "promising" for a long time. Thirty
  days of shadow trading can't prove a small edge; the history test does the heavy lifting, and the
  research effects shrink once published (McLean & Pontiff 2016: on average 26% lower out of sample and
  58% lower after publication).
- Where to see it: Thinking tab → Challengers, the after-market report, Research tab (the plan notes a switch).
