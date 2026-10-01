# Stops sized to each stock, and earnings (risk.py, earnings.py)

- Day desk stops: half the stock's usual daily range (14-day average true range, from earlier days only),
  at least 1% and at most 5% below the buy price. Unknown range: the fixed 2%. A position keeps the stop
  it was bought with, at the broker too.
- Sizing: a wider stop buys less. No day trade loses more than 0.66% of the desk at its stop (what a full
  33% position with a 2% stop risked), and no position is bigger than 33% of the desk. So a jumpy stock
  gets room AND a smaller position; nothing risks more than before.
- This is a common rule of thumb (volatility-based stops), not a tested edge. The shadow trades and the
  bot's own results show whether it helps.
- Swing desk: keeps the fixed 7% stop it was tested with.
- Earnings: the swing desk doesn't BUY a stock whose next earnings report is within 3 trading days (Yahoo
  Finance dates, looked up each morning). What it owns is kept; the stop still protects it, except that a
  stop can't sell overnight, so a report can gap past it.
- Research: stocks have earned MORE around earnings reports on average (Frazzini & Lamont 2007: over 7% a
  year; later work finds it has shrunk). Skipping reports gives that up for fewer big surprise losses.
  It's a safety choice, not a money-making one. The day desk doesn't need it: it never holds overnight.
