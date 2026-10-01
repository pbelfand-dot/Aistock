# Weekend practice (weekend.py)

On Saturdays and Sundays, while the stock market is closed, Kestrel practices. Two separate experiments,
each turned on or off in Setup → Settings:

- **Replay** (accounts weekend-swing and weekend-day): real past trading days, from the 5-minute and
  daily prices saved on the Mac, replayed fast (about 30 minutes per trading day, consecutive days, a
  different stretch each weekend) through each desk's own strategy, team and risk rules. The swing desk
  decides at 3:45pm of each replayed day, on that day's closing prices (a 15-minute head start); the day
  desk every 5 minutes. It's practice, not new evidence: the strategies were chosen by testing this same
  history.
- **Crypto** (account weekend-crypto): $500 of pretend money against live crypto prices (Alpaca's free
  crypto data, no keys), the swing desk's momentum method on hourly bars: a decision at the top of each
  hour, stop-losses every 5 minutes, everything sold Sunday at 11:50pm. Nothing goes to a broker. An
  experiment: Kestrel's strategies were only ever tested on stocks.

**None of it counts** toward Stage 1's 30 days, a move to real money, or what the desks learn from their
own trades (mistake memory and lessons only read the in-its-head, paper and real accounts). Each weekend
starts fresh; Monday's journal gets one summary line. The Thinking tab shows it live.
