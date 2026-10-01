"""The local AI (llm.py): Gemma 4 12B on a Mac with enough memory, the small model otherwise, downloaded by
itself in the background, answers without "thinking" out loud, and never in the way when Ollama is missing."""
import io
import json
import urllib.error

import pytest

from aitrader import app_api, llm


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def ollama(cfg, monkeypatch, tmp_path):
    """A pretend Ollama: `have` is what's downloaded (None = not running); requests are recorded."""
    fake = {"have": [], "sent": [], "spawned": [], "reject_think": False, "answer": "Plain answer."}
    cfg["data_dir"] = str(tmp_path)
    cfg["llm"].update(enabled=True, url="http://localhost:11434", model="gemma4:12b", small_model="qwen3:4b",
                      min_memory_gb=16, think=False)

    def urlopen(request, timeout):
        if fake["have"] is None:
            raise urllib.error.URLError("connection refused")
        if request.full_url.endswith("/api/tags"):
            return Reply(json.dumps({"models": [{"name": n} for n in fake["have"]]}).encode())
        body = json.loads(request.data)
        fake["sent"].append(body)
        if fake["reject_think"] and "think" in body:
            raise urllib.error.HTTPError(request.full_url, 400, "does not support thinking", {}, None)
        return Reply(json.dumps({"response": fake["answer"]}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(llm, "_spawn", lambda model: fake["spawned"].append(model))
    monkeypatch.setattr(llm, "mac_memory_gb", lambda: 16.0)
    llm._no_think.clear()
    return fake


def test_a_16_gb_mac_runs_gemma_and_a_smaller_one_the_small_model(cfg, monkeypatch):
    cfg["llm"].update(model="gemma4:12b", small_model="qwen3:4b", min_memory_gb=16)
    for memory, model in ((8.0, "qwen3:4b"), (15.0, "qwen3:4b"), (16.0, "gemma4:12b"), (64.0, "gemma4:12b"),
                          (None, "gemma4:12b")):
        monkeypatch.setattr(llm, "mac_memory_gb", lambda m=memory: m)
        assert llm.wanted_model(cfg) == model, memory


def test_it_answers_with_gemma_without_thinking_out_loud(cfg, ollama):
    ollama["have"] = ["gemma4:12b", "qwen3:4b"]
    ollama["answer"] = "<think>let me see...</think>\nThe desk bought two stocks."
    assert llm.ask_local_llm(cfg, "Summarize today.") == "The desk bought two stocks."
    sent = ollama["sent"][-1]
    assert sent["model"] == "gemma4:12b" and sent["think"] is False and sent["stream"] is False
    assert not ollama["spawned"]


def test_a_missing_model_downloads_by_itself_and_the_small_one_fills_in(cfg, ollama):
    ollama["have"] = ["qwen3:4b"]
    assert llm.ask_local_llm(cfg, "Summarize today.") == "Plain answer."
    assert ollama["sent"][-1]["model"] == "qwen3:4b" and ollama["spawned"] == ["gemma4:12b"]
    llm.ask_local_llm(cfg, "And again.")
    assert ollama["spawned"] == ["gemma4:12b"]                         # one download, not one per question
    ollama["have"] = []
    assert llm.ask_local_llm(cfg, "Nothing downloaded yet.") is None   # template text until a model is here


def test_no_ollama_means_template_text_and_no_download(cfg, ollama):
    ollama["have"] = None
    assert llm.ask_local_llm(cfg, "Summarize today.") is None
    assert not ollama["spawned"] and not ollama["sent"]


def test_a_model_that_cant_think_is_asked_again_without_the_setting(cfg, ollama):
    ollama["have"] = ["gemma4:12b"]
    ollama["reject_think"] = True
    assert llm.ask_local_llm(cfg, "Summarize today.") == "Plain answer."
    assert "think" in ollama["sent"][0] and "think" not in ollama["sent"][1]
    llm.ask_local_llm(cfg, "Again.")
    assert "think" not in ollama["sent"][2]                            # remembered: no failed request each time


def test_the_download_reports_its_progress_and_its_failures(cfg, ollama, monkeypatch):
    lines = [{"status": "pulling manifest"}, {"status": "pulling abc", "total": 200, "completed": 50},
             {"status": "success"}]
    monkeypatch.setattr(llm, "_ollama", lambda cfg, path, body=None, timeout=5:
                        Reply(b"\n".join(json.dumps(x).encode() for x in lines)))
    assert llm.pull(cfg, "gemma4:12b") is True
    state = llm.download_state(cfg)
    assert state["done"] and state["percent"] == 100 and not state["running"]

    lines[:] = [{"status": "pulling abc", "total": 200, "completed": 20}, {"error": "disk is full"}]
    assert llm.pull(cfg, "gemma4:12b") is False
    assert llm.download_state(cfg)["error"] == "disk is full"
    assert llm.start_download(cfg, "gemma4:12b") is False             # just failed: waits an hour on its own
    assert not ollama["spawned"]
    assert llm.start_download(cfg, "gemma4:12b", force=True) is True  # ...unless you press the button
    assert ollama["spawned"] == ["gemma4:12b"]


def test_setup_shows_the_local_ai_and_can_start_the_download(cfg, ollama):
    ollama["have"] = None
    s = llm.status(cfg)
    assert s["enabled"] and not s["ollama"] and s["model"] == "gemma4:12b" and not s["ready"]
    with pytest.raises(RuntimeError, match="ollama.com/download"):
        app_api.llm_download(cfg)

    ollama["have"] = ["qwen3:4b"]
    assert "Downloading gemma4:12b" in app_api.llm_download(cfg)["message"]
    s = llm.status(cfg)
    assert s["downloading"] and s["using"] == "qwen3:4b" and not s["ready"]

    ollama["have"] = ["gemma4:12b", "qwen3:4b"]
    assert "already downloaded" in app_api.llm_download(cfg)["message"]
    assert llm.status(cfg)["ready"] and llm.status(cfg)["using"] == "gemma4:12b"
