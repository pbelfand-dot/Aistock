# How each video is analyzed (brief for the video analysts)

Goal: turn each video into **objective, testable trade records**, never vague advice. Every fact
carries where it came from. Unknown is a valid answer; a guess presented as fact is not.

## Inputs (per video, in `research/tjr/raw/recaps/NNN/`)
- `info.json`: file name, duration, resolution, `title_claim` (the P&L the title claims: a
  **claim**, not evidence).
- `sheets/sheet_XXX.jpg`: four chart pictures per page, labeled `#index mm:ss`. Too small to read
  prices, but good for spotting which pictures matter.
- `shots/NNNN_<start>-<end>.jpg`: each picture at full size (1280×720): the last picture of each
  "scene", so drawings are complete. At full size the TradingView legend (instrument · timeframe ·
  exchange), the price axis, the x-axis date/time and the position-tool boxes are readable.
- `transcript.txt`: offline speech-to-text in 15-second lines. **Very rough**: many words are
  wrong ("break juncture" = "break of structure"). Use it for gist and timestamps. Never take a
  number from it alone unless it's plausible and matches the chart.

## Method
1. Look at every sheet first to map the video. Then open the full-size shots you need (typically
   5–15) to read instruments, timeframes, dates, prices and position boxes.
2. Read the transcript alongside to learn what he says he did and why.
   Budget: open at most ~15 full-size shots per video, and don't re-open the same picture. If a
   number still can't be read, mark it unknown instead of hunting for it.
3. Record each trade separately (a video can have 0, 1 or several trades). Market-analysis
   videos with no trade get `trades: []`, `no_trade_reason`, and their analysis in
   `market_context` / `lessons_stated`.

## Evidence tags (use on every field)
Each field is `{"value": ..., "src": "...", "ref": "..."}`.

| `src` | Meaning | What goes in `ref` |
|---|---|---|
| `seen` | Read directly off a picture | The picture (`#12 03m20s`) and what was read ("legend: E-mini S&P 500 · 5 · CME") |
| `heard` | From the rough transcript | Timestamp plus the transcript words, e.g. `[02:15] "five minute break juncture"`, and how you read them |
| `inferred` | Your own reasoning from seen or heard facts | The reasoning, in short |
| `unknown` | Not determinable | Leave `value` null |

**Prices:**
- A price is `seen` only if it is read off the axis or a label.
- A price estimated from where a candle sits between axis labels is `inferred`, with its precision
  (e.g. "≈5,501 ±2").

**P&L, win rates and "screenshots of profits" are never verified:**
- by the title;
- by his words;
- by a P&L number flashed without the position it belongs to.

`pnl_verified` is "yes" only when a broker/platform panel shows the P&L together with the matching
position or fills. Otherwise it is "no" with the reason.

## Record format: write `research/tjr/recaps/records/NNN.json`
```json
{
  "video": {
    "n": 2, "file": "...", "kind": "dated recap/analysis | live session | breakdown | lifestyle",
    "accessed": true, "access_note": "what you could and couldn't use (e.g. transcript unusable)",
    "duration_min": 5.6, "title_claim": "...",
    "session_date": {"value": "2024-02-20", "src": "seen", "ref": "#3 00m08s x-axis 'Tue 20 Feb 24'"}
  },
  "market_context": {
    "regime": {"value": "e.g. trending up on 4h/1h, ranging on 5m", "src": "...", "ref": "..."},
    "news": {"value": "e.g. CPI 8:30 ET; FOMC 14:00; none mentioned", "src": "...", "ref": "..."},
    "bias": {"value": "bullish/bearish/neutral + why (draw on liquidity)", "src": "...", "ref": "..."}
  },
  "trades": [
    {
      "date": {"value": "2024-02-20", "src": "...", "ref": "..."},
      "instrument": {"value": "ES (E-mini S&P 500 futures)", "src": "seen", "ref": "..."},
      "direction": {"value": "long|short", "src": "...", "ref": "..."},
      "timeframes": {"value": {"bias": "1h", "setup": "5m", "entry": "1m"}, "src": "...", "ref": "..."},
      "setup": {"value": "one-line name, e.g. 'sweep of 15m low -> 5m BOS -> 5m FVG entry'", "src": "...", "ref": "..."},
      "entry_conditions": [
        {"value": "each objective condition, e.g. 'price traded below the prior 15m swing low (sweep)'", "src": "...", "ref": "..."}
      ],
      "entry_time": {"value": "09:47 ET", "src": "...", "ref": "..."},
      "entry": {"value": 5501.25, "src": "...", "ref": "..."},
      "stop": {"value": 5493.0, "src": "...", "ref": "..."},
      "stop_rule": {"value": "e.g. below the sweep low", "src": "...", "ref": "..."},
      "target": {"value": 5520.0, "src": "...", "ref": "..."},
      "target_rule": {"value": "e.g. previous 1h high (liquidity)", "src": "...", "ref": "..."},
      "exit": {"value": "price or 'stopped' / 'target hit' / 'manual at ...'", "src": "...", "ref": "..."},
      "size_or_leverage": {"value": "e.g. 10 ES contracts; or null", "src": "...", "ref": "..."},
      "result": {"value": "win|loss|breakeven|unknown", "src": "...", "ref": "..."},
      "r_multiple": {"value": 2.1, "src": "computed|stated|inferred|unknown", "ref": "(exit-entry)/(entry-stop) with the numbers used"},
      "claimed_pnl": {"value": "$ amount he states or shows", "src": "...", "ref": "..."},
      "pnl_verified": {"value": "yes|no", "src": "...", "ref": "why"},
      "mistakes": [ {"value": "execution mistake or risk issue, e.g. 'moved stop', 'oversized after loss', 'traded into news'", "src": "...", "ref": "..."} ],
      "evidence_summary": "one line: what was seen vs heard vs inferred for this trade"
    }
  ],
  "no_trade_reason": "only when trades is empty",
  "lessons_stated": [ {"value": "a rule he states, as he states it", "src": "heard|seen", "ref": "..."} ],
  "quality_notes": "what limits confidence (e.g. prices unreadable, transcript garbled at 03:00-05:00)"
}
```
Keep the JSON valid. Keep text short and factual. Times: say whether it's the chart's timezone
(read it off the chart if shown) or ET.

## Glossary (his words → meaning)
- **Liquidity / sweep / raid:** price runs past a prior high or low (stops rest there), then reverses.
- **BOS / break of structure** (transcript: "break juncture"): a candle **closes** beyond the most
  recent swing point. **CHoCH:** the first BOS against the trend.
- **FVG / fair value gap / imbalance:** a 3-candle gap. **IFVG:** an inverted FVG (price closes
  through a gap, and it flips from support to resistance or the reverse).
- **Order block, equilibrium** (50% of a range), **premium/discount.**
- **SMT:** divergence between ES and NQ, e.g. one makes a new low and the other doesn't.
- **Draw on liquidity:** the level price is expected to reach. **Sessions:** Asia, London, NY
  (9:30 ET open), PM session.
- **Instruments:** ES1!/MES (S&P 500 futures), NQ1!/MNQ (Nasdaq futures), YM, GC (gold).
  **"Funded"** = prop-firm evaluation accounts.
