# Day desk upgrades: realistic costs, the 3:30 market check, pre-market movers

- **Realistic costs** (config.yaml desks.day.cents_per_share: 2): every simulated day-desk fill (in its head,
  shadow accounts, the study, TJR's history test, the challengers' history) is also 2 cents a share worse,
  about 1-2 cents of slippage plus half the bid-ask spread. The opening-range research (Zarattini, Barbon &
  Aziz 2024) reported results before such costs; a method trading many cheap shares can look good without them
  and lose with them. Real paper and real-money fills at Alpaca are real, so they need no extra cost.
- **Day-desk challengers** (challengers.py, compared with the desk's method, TJR's model): `tjr_model_mim`,
  `orb_5min` (the 5-minute breakout, long only, now with costs) and `orb_5min_mim`.
- **The 3:30 market check (`_mim`)**: market intraday momentum (Gao, Han, Li & Zhou 2018, Journal of Financial
  Economics): the S&P 500's return from the previous close to 10:00am predicted its last half hour. A `_mim`
  method sells everything at 3:30pm when SPY was down at 10am, instead of holding until the 3:50 exit.
  Nothing changes before 3:30. It must prove itself like any challenger.
- **Pre-market movers** (in_play.py, about 9:20am): from the evening scan's pool of busy stocks, the ones gapping
  3%+ from yesterday's close (either way) on 3%+ of a normal day's volume, from Alpaca's SIP feed (all
  exchanges; the free plan reads it 15 minutes late, so the data runs to about 9:05). Shown in the Thinking tab,
  the journal and the report. They're NOT traded at first: a shadow account trades the day desk's method with
  them added, and they join the desk's list only when that account is proven better (20+ days ahead,
  bootstrap p 0.05 or less, deflated Sharpe 0.95+). No history exists for these lists, so it's judged going
  forward only. A real-money desk adds them only when the owner presses Use it.
- **Honest expectations**: with $500 and realistic costs, a day method needs a real edge just to break even.
  These changes make the numbers more truthful, which may make some results look worse.
