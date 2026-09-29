# Learning from TJR's videos

The plan: turn TJR's teaching into exact rules the bot can test, then trade them on paper.

## How a video becomes rules
1. **Get the words.** Either a transcript (YouTube: *…more → Show transcript*, or a free
   transcript site), or the video file itself:
   `python research/tjr/ingest_video.py video.mp4` writes a timestamped transcript plus a
   picture of the charts every 20 seconds to `research/tjr/raw/` (not committed: it's TJR's
   content). With `huggingface.co` allowed in the environment's network settings it uses the
   accurate Whisper model; otherwise a rougher offline one.
2. **Take notes.** One file per video in `notes/`, in our own words: the concepts, the exact
   conditions, and anything vague that needs a decision.
3. **Write the rulebook.** [`RULES.md`](RULES.md) collects every rule precisely enough to code:
   what counts as a "sweep", how big a gap is a "fair value gap", which time windows, where the
   stop goes, where the target is, how much to risk.
4. **Code and test it.** The rules become a strategy in `trader/aitrader/`, tested on history
   first, then on paper.

## The paper-trading plan (agreed)
| Stage | What trades | How long | To pass |
|---|---|---|---|
| 1. Free ball | The bot's own picks across many stocks, big and niche; it keeps a growing list of the ones it likes | 30 trading days | makes money and beats holding SPY |
| 2. Combined | Stage 1 **plus** TJR's rules | 30 trading days | same |
| Live | $50 of real money, tried at both Alpaca (fractional shares) and Schwab (whole shares only) | | |

Honest caveat: a teacher's method is a hypothesis. The paper stages are what prove or disprove
it, with real prices and costs.
