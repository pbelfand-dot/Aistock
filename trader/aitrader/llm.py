"""
llm.py: an OPTIONAL local chatbot (via Ollama) that writes plain-English explanations.

It runs on your own computer: install Ollama (free) from https://ollama.com/download and open it once.
Kestrel then downloads its model by itself (config.yaml llm.model: Google's Gemma 4 12B, about 8 GB).
A Mac with less memory than llm.min_memory_gb uses the small model (llm.small_model) instead, so the AI
never slows down trading; the small model is also used, if it's there, while the big one downloads.

It never decides trades. If Ollama isn't running, the bot still works; you
just get a plainer, template-written plan instead.

Every request carries the knowledge pack (knowledge.py) as background, so the write-ups know the
owner's plan, the safety rules, the research and what TJR's videos taught.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

DOWNLOAD_FILE = "llm_download.json"      # the model download's progress, in data/
STALE_SECONDS = 120                      # a download that hasn't reported for this long has stopped
RETRY_SECONDS = 3600                     # after a failed download, try again on its own an hour later
_no_think = set()                        # models that refuse the "think" setting (they don't think anyway)


def mac_memory_gb():
    """This computer's memory in GB, or None if it can't tell."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (ValueError, OSError, AttributeError):
        pass
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
        return int(out) / 2 ** 30
    except Exception:
        return None


def wanted_model(cfg: dict) -> str:
    """The model this Mac should run: the big one, unless the Mac has too little memory for it next to trading."""
    llm = cfg.get("llm", {})
    memory, small = mac_memory_gb(), llm.get("small_model")
    if small and memory is not None and memory < llm.get("min_memory_gb", 16) - 0.5:   # a "16 GB" Mac is 16.0
        return small
    return llm["model"]


def _ollama(cfg: dict, path: str, body: dict = None, timeout: float = 5):
    request = urllib.request.Request(cfg["llm"]["url"].rstrip("/") + path,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(request, timeout=timeout)


def downloaded(cfg: dict):
    """The models Ollama has on this Mac, or None if Ollama isn't running."""
    try:
        with _ollama(cfg, "/api/tags", timeout=3) as resp:
            return [m.get("name") or m.get("model") for m in json.loads(resp.read()).get("models", [])]
    except Exception:
        return None


def has(names: list, model: str) -> bool:
    return bool(model) and (model in names or (":" not in model and f"{model}:latest" in names))


def download_state(cfg: dict) -> dict:
    from .config import data_path
    try:
        state = json.loads(data_path(cfg, DOWNLOAD_FILE).read_text())
    except (OSError, ValueError):
        return {}
    state["running"] = bool(state.get("running")) and time.time() - state.get("updated", 0) < STALE_SECONDS
    return state


def _save_state(cfg: dict, model: str, **fields):
    from .config import data_path
    data_path(cfg, DOWNLOAD_FILE).write_text(json.dumps({"model": model, "updated": time.time(), **fields}))


def _spawn(model: str):
    """Download in a separate background process, so it keeps going after this one finishes."""
    from .config import ROOT
    subprocess.Popen([sys.executable, "-m", "aitrader.llm", "pull", model], cwd=ROOT, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_download(cfg: dict, model: str, force: bool = False) -> bool:
    """Start downloading `model` in the background, unless it's already downloading (or just failed, when not
    forced). True if a download is now under way."""
    state = download_state(cfg)
    if state.get("model") == model:
        if state["running"]:
            return True
        if state.get("error") and not force and time.time() - state.get("updated", 0) < RETRY_SECONDS:
            return False
    _save_state(cfg, model, running=True, percent=0, status="starting")
    _spawn(model)
    return True


def pull(cfg: dict, model: str) -> bool:
    """Download a model through Ollama, writing the progress to data/llm_download.json."""
    last = 0.0
    try:
        with _ollama(cfg, "/api/pull", {"model": model, "stream": True}, timeout=600) as resp:
            for line in resp:
                if not line.strip():
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise RuntimeError(msg["error"])
                if msg.get("status") == "success":
                    _save_state(cfg, model, running=False, done=True, percent=100, status="success")
                    announce(cfg, f"[local AI] ready: {model} is downloaded, and the plain-English write-ups "
                                  "use it from now on")
                    return True
                if time.time() - last > 2:
                    total, done = msg.get("total"), msg.get("completed")
                    _save_state(cfg, model, running=True, status=msg.get("status", ""),
                                percent=round(100 * done / total) if total and done else None,
                                gb_done=round(done / 1e9, 1) if total and done else None,
                                gb_total=round(total / 1e9, 1) if total else None)
                    last = time.time()
        raise RuntimeError("the download stopped before it finished")
    except Exception as e:
        why = str(e) or type(e).__name__
        if isinstance(e, urllib.error.HTTPError):
            why = (json.loads(e.read() or b"{}").get("error") if e.fp else None) or f"Ollama said {e.code}"
        elif isinstance(e, urllib.error.URLError):
            why = "Ollama isn't running"
        _save_state(cfg, model, running=False, error=why)
        return False


def announce(cfg: dict, text: str):
    """The download finished: a line in the Activity tab, and a message to your phone if it's set up.
    (This runs in the download's own process, so it sends straight away instead of queueing.)"""
    from . import phone, pushover
    from .config import data_path
    from .storage import Store
    try:
        store = Store(data_path(cfg, "aitrader.sqlite"))
        store.log(text, echo=False)
        store.db.close()
        if phone.connected(cfg):
            phone.send(cfg, text)
        if pushover.has_keys(cfg):
            pushover.send(cfg, text, title="Kestrel: local AI ready", priority=0)
    except Exception:
        pass                                            # a notice must never fail the download


def pick_model(cfg: dict, names: list):
    """The model to answer with now: the wanted one if it's downloaded; otherwise start downloading it and use
    the small model meanwhile, if that one is here. None = nothing usable yet."""
    want, small = wanted_model(cfg), cfg["llm"].get("small_model")
    if has(names, want):
        return want
    start_download(cfg, want)
    return small if has(names, small) else None


def _generate(cfg: dict, body: dict) -> str:
    with _ollama(cfg, "/api/generate", body, timeout=cfg["llm"].get("timeout_seconds", 300)) as resp:
        return json.loads(resp.read())["response"]


def ask_local_llm(cfg: dict, prompt: str):
    """Returns the model's answer, or None if the local LLM is off/unavailable."""
    llm = cfg.get("llm", {})
    if not llm.get("enabled"):
        return None
    names = downloaded(cfg)
    if names is None:
        print("  (local AI not available: Ollama isn't running; using the template write-up instead)")
        return None
    model = pick_model(cfg, names)
    if not model:
        print(f"  (local AI: downloading {wanted_model(cfg)} first; using the template write-up for now)")
        return None
    request_body = {"model": model, "prompt": prompt, "stream": False}
    if model not in _no_think:
        request_body["think"] = bool(llm.get("think", False))   # short write-ups: answer, don't think out loud
    if llm.get("use_knowledge", True):                  # the owner's plan, safety rules, research, TJR notes
        from .knowledge import pack
        request_body["system"] = pack(cfg)
        request_body["options"] = {"num_ctx": llm.get("context_tokens", 8192)}
    try:
        try:
            answer = _generate(cfg, request_body)
        except urllib.error.HTTPError as e:
            if e.code != 400 or "think" not in request_body:
                raise
            _no_think.add(model)                        # "does not support thinking": ask again without it
            request_body.pop("think")
            answer = _generate(cfg, request_body)
        return re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
    except Exception as e:
        print(f"  (local LLM not available: {e}; using the template write-up instead)")
        return None


def status(cfg: dict) -> dict:
    """For Setup: is Ollama running, which model this Mac uses, and how its download is going."""
    llm = cfg.get("llm", {})
    want, small = wanted_model(cfg), llm.get("small_model")
    names = downloaded(cfg) if llm.get("enabled") else None
    state = download_state(cfg)
    mine = state if state.get("model") == want else {}
    memory = mac_memory_gb()
    return {"enabled": bool(llm.get("enabled")), "ollama": names is not None, "model": want,
            "big_model": llm.get("model"), "small_model": small, "memory_gb": round(memory) if memory else None,
            "min_memory_gb": llm.get("min_memory_gb", 16), "ready": names is not None and has(names, want),
            "using": None if names is None else want if has(names, want) else small if has(names, small) else None,
            "downloading": bool(mine.get("running")), "percent": mine.get("percent"), "error": mine.get("error"),
            "gb_done": mine.get("gb_done"), "gb_total": mine.get("gb_total")}


if __name__ == "__main__":                             # python -m aitrader.llm pull <model>  (started by _spawn)
    if len(sys.argv) == 3 and sys.argv[1] == "pull":
        from .config import load_config
        sys.exit(0 if pull(load_config(), sys.argv[2]) else 1)
    print("usage: python -m aitrader.llm pull <model>")
    sys.exit(2)
