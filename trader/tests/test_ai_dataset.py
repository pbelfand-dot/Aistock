"""The Kestrel chat dataset (datasets/kestrel_chat): valid fine-tuning files, sources that exist, no secrets."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "datasets/kestrel_chat/build.py"
READY = BUILD.exists() and any((REPO / "datasets/kestrel_chat/sources").glob("*.json"))


def builder():
    spec = importlib.util.spec_from_file_location("kestrel_dataset_build", BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not READY, reason="no dataset (or no answers yet) in this checkout")
def test_the_dataset_builds_into_valid_chat_files(tmp_path):
    b = builder()
    summary = b.build(tmp_path)
    assert summary["examples"] >= 150 and summary["validation"] >= 10
    assert summary["train"] + summary["validation"] == summary["examples"]
    lines = (tmp_path / "kestrel_chat.jsonl").read_text().splitlines()
    assert len(lines) == summary["examples"]
    for line in lines:
        roles = [m["role"] for m in json.loads(line)["messages"]]
        assert roles == ["system", "user", "assistant"]
    systems = {json.loads(line)["messages"][0]["content"] for line in lines}
    assert systems == {b.SYSTEM}                                       # one system message for all examples
    rows = list(csv.DictReader(open(tmp_path / "kestrel_qa.csv")))
    assert len(rows) == summary["examples"]
    knowledge = (tmp_path / "kestrel_knowledge.md").read_text()
    assert "Kestrel" in knowledge and "stop_atr_multiple" in knowledge


@pytest.mark.skipif(not READY, reason="no dataset (or no answers yet) in this checkout")
def test_every_answer_names_a_source_that_exists():
    b = builder()
    missing = []
    for x in b.load():
        paths = [p for p in __import__("re").findall(r"[\w./-]+\.(?:py|md|yaml|html|swift)", x["source"])]
        assert paths, f"no source file named for {x['q']!r}"
        for p in paths:
            candidates = [REPO / p, REPO / "trader" / p, REPO / "trader/aitrader" / p, REPO / "trader/aitrader/knowledge" / p,
                          REPO / "trader/aitrader/brokers" / p, REPO / "mac/app" / p]
            if not any(c.exists() for c in candidates):
                missing.append((x["q"], p))
    assert not missing, missing[:5]


@pytest.mark.skipif(not READY, reason="no dataset (or no answers yet) in this checkout")
def test_secrets_never_get_into_the_dataset():
    b = builder()
    with pytest.raises(ValueError, match="secret"):
        b.check([{"q": "what's my key", "a": "It's PKABCDEFGHIJKLMNOPQRST, keep it safe", "source": "x.md", "topic": "t"}])
    with pytest.raises(ValueError, match="secret"):
        b.check([{"q": "who made it", "a": "Email someone@example.com for help with that", "source": "x.md", "topic": "t"}])
