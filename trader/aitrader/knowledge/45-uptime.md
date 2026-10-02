# Alert me if Kestrel stops (the dead-man's switch)

- **Why**: a Mac that's asleep, unplugged, offline or frozen can't send its own alert, so an outside service
  has to notice the silence.
- **How** (uptime.py): after every autopilot cycle (every 5 minutes) Kestrel pings the owner's check on
  healthchecks.io (free for up to 20 checks). If the pings stop, healthchecks.io alerts the owner through
  what they connected there (Pushover, Telegram, email). If a trading job (day desk, swing decision, swing
  stop checks) fails 3 cycles in a row (about 15 minutes), Kestrel pings "fail" with the reason; the next good
  cycle clears it.
- **Setup → Your phone → Alert me if Kestrel stops**: the check's Ping URL (https://hc-ping.com/...) is tried
  with one ping before it's saved to ~/AITrader/.env (HEALTHCHECK_URL). Recommended check: Cron schedule
  `*/5 9-15 * * 1-5`, time zone America/New_York, grace time 15 minutes, so it only expects Kestrel while the
  market is open.
- Pings go out in the background with a 10-second timeout: they never slow down or block trading.
