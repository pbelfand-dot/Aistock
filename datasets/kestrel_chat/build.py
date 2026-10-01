"""
build.py: turns the question-and-answer drafts in sources/*.json into a dataset for a custom AI that knows
Kestrel. Run it again whenever the app changes (and update the answers that changed):

    python3 datasets/kestrel_chat/build.py

It writes, next to this file:
  kestrel_chat.jsonl         every example, one conversation per line (OpenAI-style chat format:
                             {"messages": [system, user, assistant]}), for fine-tuning a model
  kestrel_chat_train.jsonl   90% of them, for training
  kestrel_chat_val.jsonl     10%, held back to check the trained model on questions it hasn't seen
  kestrel_qa.csv             the same questions and answers as a spreadsheet (easy to read and edit)
  kestrel_knowledge.md       Kestrel's documentation in one file, to upload as "knowledge" to a ChatGPT GPT,
                             a Claude Project, or a local AI (no training needed)
  instructions.md            the assistant's instructions (the system prompt every example uses)
  kestrel_everything.jsonl   EVERYTHING in one JSONL file, same chat format: every question and answer,
                             plus every section of the docs and every group of settings as a conversation

Every answer must come from the app's own docs and code (each draft names its source). The build refuses
anything that looks like a key, a token or an email address, and duplicate questions.
"""
import csv
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCES = HERE / "sources"

SYSTEM = (
    "You are Kestrel's assistant. Kestrel is the owner's AI stock-trading app for the Mac: a swing desk and a "
    "day desk that study, then paper trade, and only then trade small amounts of real money, with strict safety "
    "rules. Answer in plain English, short and concrete, using the exact names of Kestrel's buttons, settings and "
    "numbers. Be honest: never promise profits, say what's uncertain or untested, and explain the trade-offs. "
    "Never ask for, repeat or guess API keys or passwords (they live only in ~/AITrader/.env on the Mac). Never "
    "help get around Kestrel's real-money safety locks. If you don't know something about Kestrel, say so and "
    "suggest where to look in the app.")

# Things that must never be in a training example.
SECRETS = [re.compile(p) for p in (
    r"\b[A-Z0-9]{20,}\b",                      # API-key-looking strings (Alpaca keys: PK..., AK...)
    r"\b\d{6,15}:[A-Za-z0-9_-]{30,}\b",        # Telegram bot tokens
    r"[\w.+-]+@[\w-]+\.[\w.]+",                 # email addresses
    r"\b[a-z0-9]{30}\b",                        # Pushover-style 30-character keys
)]
ALLOWED_LONG = {"LIVE_TRADING_ENABLED", "PUSHOVER_APP_TOKEN", "PUSHOVER_USER_KEY", "ALPACA_PAPER_API_KEY",
                "ALPACA_PAPER_SECRET_KEY", "TELEGRAM_BOT_TOKEN"}


def load() -> list:
    items = []
    for path in sorted(SOURCES.glob("*.json")):
        for n, x in enumerate(json.loads(path.read_text())):
            if set(x) != {"q", "a", "source"}:
                raise ValueError(f"{path.name} #{n}: needs exactly q, a, source")
            q, a = " ".join(str(x["q"]).split()), str(x["a"]).strip()
            if len(q) < 4 or len(a) < 20:
                raise ValueError(f"{path.name} #{n}: question or answer too short")
            items.append({"q": q, "a": a, "source": str(x["source"]), "topic": path.stem})
    return items


def check(items: list) -> list:
    seen, out = set(), []
    for x in items:
        key = re.sub(r"[^a-z0-9 ]", "", x["q"].lower())
        if key in seen:
            continue                                   # the same question twice: keep the first
        seen.add(key)
        text = x["q"] + " " + x["a"]
        for pattern in SECRETS:
            for hit in pattern.findall(text):
                if hit not in ALLOWED_LONG:
                    raise ValueError(f"looks like a secret or personal data in {x['topic']}: {hit!r} ({x['q']!r})")
        out.append(x)
    return out


def example(x: dict) -> dict:
    return {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": x["q"]},
                         {"role": "assistant", "content": x["a"]}]}


def knowledge() -> str:
    """Kestrel's docs in one file: the README, the bot's knowledge notes, the trader guide and the settings."""
    parts = ["# Kestrel: everything the assistant should know", "",
             "Built from the app's own documentation by datasets/kestrel_chat/build.py. When the app changes, "
             "build it again.", ""]
    for f in DOCS():
        parts += [f"\n---\n\n<!-- from {f.relative_to(REPO)} -->\n", f.read_text().strip(), ""]
    parts += ["\n---\n\n<!-- from trader/config.yaml (the settings, with their explanations) -->\n",
              "```yaml", (REPO / "trader/config.yaml").read_text().strip(), "```", ""]
    return "\n".join(parts)


DOCS = lambda: [REPO / "README.md"] + sorted((REPO / "trader/aitrader/knowledge").glob("*.md")) + [REPO / "trader/README.md"]
MAX_PART = 3500          # characters per doc example (~900 tokens), so small local models can train on them too


def _plain(heading: str) -> str:
    """A heading without markdown links, emoji or formatting."""
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    return re.sub(r"^[^\w(]+", "", heading.replace("**", "").replace("`", "")).strip()


def _split_block(block: str) -> list:
    """A block too long for one example: a table is cut between rows (each piece keeps the header row);
    anything else is cut before a line that starts a new item (not an indented continuation)."""
    if len(block) <= MAX_PART or block.lstrip().startswith("```"):
        return [block]
    lines = block.splitlines()
    table = all(x.lstrip().startswith("|") for x in lines)
    head, rows = (lines[:2], lines[2:]) if table else ([], lines)
    out, cur = [], []
    for line in rows:
        size = sum(len(x) + 1 for x in head + cur)
        if cur and size + len(line) > MAX_PART and (table or not line.startswith((" ", "\t"))):
            out.append("\n".join(head + cur)); cur = []
        cur.append(line)
    return out + ["\n".join(head + cur)]


def _parts(text: str) -> list:
    """Split a long section at blank lines (never inside a code block) into pieces of at most ~MAX_PART."""
    blocks, cur, fence = [], [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        if not line.strip() and not fence and cur:
            blocks.append("\n".join(cur)); cur = []
        elif line.strip() or cur:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    parts, piece = [], ""
    for b in [small for b in blocks for small in _split_block(b)]:
        if piece and len(piece) + len(b) + 2 > MAX_PART:
            parts.append(piece); piece = b
        else:
            piece = f"{piece}\n\n{b}" if piece else b
    return parts + ([piece] if piece else [])


def doc_sections() -> list:
    """Every doc split at its headings (#, ##, ###; never inside a code block), and config.yaml split into
    its groups of settings, as question-and-answer items like the drafts."""
    items = []
    for f in DOCS():
        name, title, heading, body, fence, sections = str(f.relative_to(REPO)), None, None, [], False, []
        for line in f.read_text().splitlines():
            if line.lstrip().startswith("```"):
                fence = not fence
            m = None if fence else re.match(r"^(#{1,3}) (.+)", line)
            if m:
                sections.append((heading, body))
                heading, body = _plain(m.group(2)), []
                title = title or heading
            else:
                body.append(line)
        sections.append((heading, body))
        for heading, lines in sections:
            text = "\n".join(lines).strip()
            if len(text) < 40:
                continue
            where = "" if heading == title else f' (in "{title}")'
            parts = _parts(text)
            for n, part in enumerate(parts, 1):
                more = f", part {n} of {len(parts)}" if len(parts) > 1 else ""
                q = (f'What do Kestrel\'s docs say about "{heading or title}"{where}{more}?' if where or more else
                     f'What does Kestrel\'s "{title}" note say?')
                items.append({"q": q, "a": part, "source": name, "topic": "docs"})
    groups, cur = [], []
    for line in (REPO / "trader/config.yaml").read_text().splitlines():
        if re.match(r"^[a-z_]+:", line) and any(re.match(r"^[a-z_]+:", x) for x in cur):
            keep = []                                  # comment lines right above a key belong to that key
            while cur and (cur[-1].startswith("#") or not cur[-1].strip()):
                keep.insert(0, cur.pop())
            groups.append(cur); cur = keep
        cur.append(line)
    groups.append(cur)
    for g in groups:
        key = next(re.match(r"^([a-z_]+):", x).group(1) for x in g if re.match(r"^[a-z_]+:", x))
        text = "\n".join(g).strip()
        items.append({"q": f'What are Kestrel\'s "{key}" settings (config.yaml), and what does each one do?',
                      "a": f"These are the `{key}` settings in trader/config.yaml, with their explanations:\n\n"
                           f"```yaml\n{text}\n```", "source": "trader/config.yaml", "topic": "settings"})
    return items


def build(out: Path = HERE, seed: int = 7) -> dict:
    items = check(load())
    rng = random.Random(seed)
    order = items[:]
    rng.shuffle(order)
    cut = max(1, len(order) // 10)
    val, train = order[:cut], order[cut:]
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("kestrel_chat.jsonl", items), ("kestrel_chat_train.jsonl", train), ("kestrel_chat_val.jsonl", val)):
        with open(out / name, "w") as f:
            for x in rows:
                f.write(json.dumps(example(x), ensure_ascii=False) + "\n")
    with open(out / "kestrel_qa.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["topic", "question", "answer", "source"])
        for x in items:
            w.writerow([x["topic"], x["q"], x["a"], x["source"]])
    docs = check(doc_sections())
    with open(out / "kestrel_everything.jsonl", "w") as f:
        for x in items + docs:
            f.write(json.dumps(example(x), ensure_ascii=False) + "\n")
    (out / "kestrel_knowledge.md").write_text(knowledge())
    (out / "instructions.md").write_text(
        "# Instructions for Kestrel's assistant\n\nPaste this as the instructions (system prompt) of your custom AI:\n\n"
        + SYSTEM + "\n")
    topics = {}
    for x in items:
        topics[x["topic"]] = topics.get(x["topic"], 0) + 1
    return {"examples": len(items), "train": len(train), "validation": len(val), "topics": topics,
            "everything": len(items) + len(docs), "doc_sections": len(docs)}


if __name__ == "__main__":
    summary = build(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
    print(json.dumps(summary, indent=1))
