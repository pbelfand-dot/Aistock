# Mistakes: fine once, not twice (mistakes.py)

The owner's rule: this is the learning stage, so making mistakes is fine; making the same mistake again
isn't.

- Every buy is written down with its situation: the stock itself; a stock in play or from the fixed
  list; under $5 a share; the first 30 minutes or after 2pm; chasing (day: up 3%+ since the open;
  swing: up 10%+ in 5 days); moving with a stock it owns; option bets against it.
- A situation becomes a lesson when its recent trades (last 60 days) keep losing:
  - the same stock: 3+ trades, at most 1 won, losing money overall;
  - any other situation: 8+ trades, losing on average, worse than the desk's other trades, and
    clearly (1 standard error below zero);
  - a relapse: a lesson learned before that loses again later comes back at once.
- The Risk agent then skips new buys in that situation and says why. Sales are never blocked.
- Lessons come from every account the desk traded (in its head, paper, real), so practice mistakes
  aren't repeated with paper or real money. They fade after 60 days unless confirmed again, so the bot
  can find out when things change.
- The thresholds are small on purpose (the owner prefers learning fast to waiting for proof), but a
  lesson only ever makes the bot more careful.
