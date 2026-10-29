"""Minimal OpenAI chat client (gpt-4o-mini by default). The key comes from .env."""
import json
import os

import httpx


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def chat(system: str, user: str, json_mode: bool = False, max_tokens: int = 600) -> str:
    """Return the assistant's reply text. Raises RuntimeError on any failure."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set (add it to .env)")
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        response = httpx.post("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key}"},
                              json=body, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # Never include the request (it carries the key) in the error.
        raise RuntimeError(f"OpenAI request failed: {exc.__class__.__name__}") from None


def chat_json(system: str, user: str) -> dict:
    return json.loads(chat(system, user, json_mode=True))
