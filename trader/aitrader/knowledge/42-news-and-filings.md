# News, SEC filings and big economic news

- **Headlines** (scanner.py): Alpaca's news feed (Benzinga), or Yahoo without keys. Danger headlines
  (share offering, bankruptcy, halt, delisting, fraud) stop buying that stock. News never makes it buy.
- **SEC filings** (sec_filings.py): official filings from the SEC's EDGAR system, free, no key. The SEC asks
  every program for a contact email (Setup → AI & news). Every 30 minutes on trading days it checks what it owns
  or considers (watchlists, the top of the scan, stocks in play). The stock card shows the last two weeks of
  filings with links. Serious ones block buying for 30 days: 8-K item 1.03 (bankruptcy), 3.01 (delisting
  notice), 4.02 (past financial statements can't be relied on), 1.05 (a material cyber attack), and late
  annual/quarterly reports (NT 10-K / NT 10-Q). On a stock it owns, that's a WARNING; the stop-loss still
  protects it.
- **Big economic news** (macro.py): the dates of CPI (8:30am), the jobs report (8:30am) and the Fed's rate
  decisions (2pm), from FRED with a free key (Setup → AI & news). A countdown in the Thinking tab and the report.
  Kestrel does NOT avoid these days by rule: the famous pre-Fed rally (Lucca & Moench, 2015) faded after 2015,
  and other releases showed no such pattern. Instead every buy on those days is tagged ("on a CPI day"),
  so the mistake memory learns from the desk's own results whether they lose, and skips them if they do.
- **Why it moved**: the stock card and the report show a stock's move today and over 5 days, next to the
  latest headlines and filings. A hint, not proof: news can follow a move as well as cause it.
