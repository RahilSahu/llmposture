"""Target adapters.

A target is anything that accepts a list of chat messages and returns the
assistant's reply. The main adapter speaks to any OpenAI-compatible chat
completions endpoint (OpenAI, xAI Grok, OpenRouter, Together, Ollama, vLLM,
and most gateways) using only the Python standard library.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class TargetResponse:
    text: str
    tool_calls: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class TargetError(RuntimeError):
    pass


class OpenAICompatibleTarget:
    """Chat completions target for any OpenAI-compatible endpoint."""

    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 api_key_env: str | None = None, timeout: float = 60.0,
                 temperature: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        if api_key is None and api_key_env:
            api_key = os.environ.get(api_key_env)
        self.api_key = api_key

    def chat(self, messages: list[dict]) -> TargetResponse:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise TargetError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TargetError(f"could not reach {url}: {exc}") from exc
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TargetError(f"unexpected response shape from {url}") from exc
        text = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        return TargetResponse(text=text, tool_calls=tool_calls, raw=body)
