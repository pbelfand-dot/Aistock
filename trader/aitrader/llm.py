"""
llm.py: an OPTIONAL local chatbot (via Ollama) that writes plain-English explanations.

It runs on your own computer: install Ollama from https://ollama.com and run
`ollama pull qwen3:4b` (or whatever model is set in config.yaml).

It never decides trades. If Ollama isn't running, the bot still works; you
just get a plainer, template-written plan instead.

Every request carries the knowledge pack (knowledge.py) as background, so the write-ups know the
owner's plan, the safety rules, the research and what TJR's videos taught.
"""
import json
import urllib.request


def ask_local_llm(cfg: dict, prompt: str):
    """Returns the model's answer, or None if the local LLM is off/unavailable."""
    llm = cfg.get("llm", {})
    if not llm.get("enabled"):
        return None
    request_body = {"model": llm["model"], "prompt": prompt, "stream": False}
    if llm.get("use_knowledge", True):                  # the owner's plan, safety rules, research, TJR notes
        from .knowledge import pack
        request_body["system"] = pack()
        request_body["options"] = {"num_ctx": llm.get("context_tokens", 8192)}
    body = json.dumps(request_body).encode()
    request = urllib.request.Request(f"{llm['url'].rstrip('/')}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=llm.get("timeout_seconds", 180)) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception as e:
        print(f"  (local LLM not available: {e}; using the template write-up instead)")
        return None
