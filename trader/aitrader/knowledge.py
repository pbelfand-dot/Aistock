"""
knowledge.py: the background the bot's local AI (and Claude) reads.

The notes in knowledge/ hold the owner's plan, the hard safety rules, what 16 years of history
showed, and what TJR's videos taught (refreshed after each batch of videos by
research/tjr/recaps.py knowledge). Every update of the app ships the latest notes.

The local AI gets them with every request, so its write-ups use the same background. It still
never decides trades: only coded, tested rules do.
"""
from pathlib import Path

FOLDER = Path(__file__).resolve().parent / "knowledge"


def topics() -> list:
    return [p.stem for p in sorted(FOLDER.glob("*.md"))]


def read(topic: str) -> str:
    path = FOLDER / f"{topic}.md"
    if topic not in topics():
        raise ValueError(f"No note called {topic!r}. Notes: {', '.join(topics())}")
    return path.read_text()


def pack(max_chars: int = 24000) -> str:
    """All notes, in order, as one text (cut off at max_chars so a small local model can hold it)."""
    text = "\n\n".join(p.read_text().strip() for p in sorted(FOLDER.glob("*.md")))
    return text if len(text) <= max_chars else text[:max_chars] + "\n\n[... notes cut here to fit ...]"
