# Beyond the price: quality, insider buys, short interest

- **Where** (fundamentals.py): three free facts per company, shown on each stock card ("Beyond the price"),
  in the team's Analyst notes, and used by the `momentum_quality` challenger. Momentum alone decides trades
  until that challenger is proven better (challengers.py).
- **Quality**: gross profits / total assets (Novy-Marx 2013, "The other side of value": more profitable
  companies earned higher returns). From the SEC's XBRL frames, every US company, 2017 on; a year counts
  from 90 days after it ended. Ranked against all US companies. Banks and funds: no number, no opinion.
- **Insider buys**: an officer or director buying on the open market (Form 4, code P), not under a 10b5-1
  plan (Lakonishok & Lee 2001; Cohen, Malloy & Pomorski 2012). Read from the Form 4s in the SEC filings
  check every 30 minutes; collected from the day this was added, so the history test can't judge it yet.
- **Short interest**: % of the float sold short and days to cover, from Yahoo Finance (FINRA's twice-monthly
  numbers), saved daily from now on. Heavily shorted = 8+ days to cover or 20%+ of the float (Kestrel's own
  line). Heavily shorted stocks did worse on average (Boehmer, Huszar & Jordan 2010).
- **momentum_quality**: never BUYS the bottom 30% by quality or a heavily shorted stock (holdings are not
  forced out), and adds 0.1 to the score of a stock an insider bought in the last 30 days.
- **The mistake memory** tags buys with these facts ("heavily shorted", "weak quality ..."), so the desk
  learns from its own results whether such buys lose.
- **Needs**: the SEC contact email (Setup → AI & news) for quality and insider buys; short interest needs nothing.
