# The team and the options-gap watcher

**The team (agents.py).** Every decision goes through five agents, each with one job and a short note:
Scout (the facts: scores, holdings, cash, danger news, option gaps), Analyst (a view per stock: what
agrees, what conflicts), Trader (the orders from the desk's tested strategy), Risk (checks every buy:
size, stocks that move together, option bets against it), Reviewer (after the close: the day, the
lessons, the watcher's scorecard). Rules decide trades. Risk only warns unless the owner switches on
a veto (config: agents.risk_vetoes), and it can only skip a buy, never add one.

**Count bets, not tickers.** Stocks whose daily returns move together (60-day correlation 0.85+) are one
bet, however many tickers it is. The Scout says how many separate bets the desk holds, and the same_bet
veto (on by default) keeps at most 2 stocks in one bet. Why: on Oct 8, 2026 the swing desk held MU and
SNDK and bought MUU and MULL (2x Micron funds); on Oct 12 MUU, MULL and SNDK hit their stop-losses on
the same day (-$15.30 of the desk's -$25.84 day). The 12.5% limit per stock was meant to cap one idea at
12.5%; four tickers of one idea made it about 44% of the desk, and two of them were 2x funds. The scan
also leaves out 2x/3x and inverse funds.

**Options-gap watcher (options_flow.py): testing only, never trades.** After each close: the share
of each watched stock's option volume that was calls (Alpaca's free data, next 45 days of expirations)
against its own normal share and its last 5 days of price. Bullish gap = calls unusually heavy while
the price is flat; bearish gap = puts unusually heavy while the price holds up. Each gap is graded 5
trading days later against SPY. "Shows an edge" needs 20+ graded calls, right 55%+, positive average.
Why only watching: option BUYERS' bets predicted next-week returns in research (Pan & Poteshman 2006),
but public volume can't tell buyers from sellers, large option trades in general don't predict
(Jiang & Strong), and the effect is weakest in the biggest stocks.
