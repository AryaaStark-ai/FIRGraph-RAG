"""Tiny client for the LOCAL Ollama server (http://localhost:11434).

Only the Python standard library is used, so nothing extra to install.
FIR text sent here never leaves the laptop: Ollama runs the model on this machine.

Change the model without editing code:   $env:FIRGRAPH_MODEL = "qwen2.5:7b"
"""
import json
import os
import urllib.error
import urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("FIRGRAPH_MODEL", "qwen2.5:7b")


def chat(system: str, user: str, as_json: bool = False, num_ctx: int = 4096, timeout: int = 600) -> str:
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": num_ctx},   # temperature 0 = repeatable output
    }
    if as_json:
        body["format"] = "json"
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))["message"]["content"]
    except urllib.error.URLError as e:
        raise SystemExit(f"Can't reach Ollama at {OLLAMA} ({e}). Is the Ollama app running? "
                         f"Is the model pulled?  ollama pull {MODEL}")


def chat_json(system: str, user: str, **kw) -> dict:
    raw = chat(system, user, as_json=True, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
