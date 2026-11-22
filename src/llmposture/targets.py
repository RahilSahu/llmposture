"""Target adapters.

A target is anything that accepts a list of chat messages and returns the
assistant's reply. The main adapter speaks to any OpenAI-compatible chat
completions endpoint (OpenAI, xAI Grok, OpenRouter, Together, Ollama, vLLM,
and most gateways) using only the Python standard library. Native adapters
cover the Anthropic Messages API, the Google Gemini API, and Ollama's own
chat endpoint, whose request and response shapes differ.
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


def _post_json(url: str, payload: dict, headers: dict,
               timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise TargetError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise TargetError(f"could not reach {url}: {exc}") from exc


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Separate system messages from the conversation.

    Anthropic and Gemini take the system prompt outside the message list.
    Returns (system_text, remaining_messages).
    """
    system_parts = [m.get("content", "") for m in messages
                    if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return "\n\n".join(p for p in system_parts if p), rest


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


class AnthropicTarget:
    """Native adapter for the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None,
                 api_key_env: str | None = None,
                 base_url: str = "https://api.anthropic.com/v1",
                 timeout: float = 60.0, max_tokens: int = 1024):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        if api_key is None and api_key_env:
            api_key = os.environ.get(api_key_env)
        self.api_key = api_key

    def chat(self, messages: list[dict]) -> TargetResponse:
        system, rest = _split_system(messages)
        convo = [{
            "role": "assistant" if m.get("role") == "assistant" else "user",
            "content": m.get("content", ""),
        } for m in rest]
        payload: dict = {"model": self.model, "max_tokens": self.max_tokens,
                         "messages": convo, "temperature": 0.0}
        if system:
            payload["system"] = system
        headers = {"anthropic-version": "2023-06-01"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        body = _post_json(self.base_url + "/messages", payload, headers,
                          self.timeout)
        texts, tool_calls = [], []
        for block in body.get("content") or []:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({"function": {
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {})}})
        if not texts and not tool_calls:
            raise TargetError("unexpected response shape from "
                              + self.base_url + "/messages")
        return TargetResponse(text="\n".join(texts), tool_calls=tool_calls,
                              raw=body)


class GeminiTarget:
    """Native adapter for the Google Gemini generateContent API."""

    name = "gemini"

    def __init__(self, model: str, api_key: str | None = None,
                 api_key_env: str | None = None,
                 base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        if api_key is None and api_key_env:
            api_key = os.environ.get(api_key_env)
        self.api_key = api_key

    def chat(self, messages: list[dict]) -> TargetResponse:
        system, rest = _split_system(messages)
        contents = [{
            "role": "model" if m.get("role") == "assistant" else "user",
            "parts": [{"text": m.get("content", "")}],
        } for m in rest]
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": 0.0},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        headers = {}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        url = f"{self.base_url}/models/{self.model}:generateContent"
        body = _post_json(url, payload, headers, self.timeout)
        try:
            parts = body["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TargetError(f"unexpected response shape from {url}") from exc
        texts, tool_calls = [], []
        for part in parts:
            if "text" in part:
                texts.append(part["text"])
            elif "functionCall" in part:
                call = part["functionCall"]
                tool_calls.append({"function": {
                    "name": call.get("name", ""),
                    "arguments": call.get("args", {})}})
        return TargetResponse(text="\n".join(texts), tool_calls=tool_calls,
                              raw=body)


class OllamaNativeTarget:
    """Native adapter for Ollama's own /api/chat endpoint."""

    name = "ollama-native"

    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict]) -> TargetResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.get("role", "user"),
                          "content": m.get("content", "")} for m in messages],
            "stream": False,
            "options": {"temperature": 0.0},
        }
        body = _post_json(self.base_url + "/api/chat", payload, {},
                          self.timeout)
        try:
            message = body["message"]
        except (KeyError, TypeError) as exc:
            raise TargetError("unexpected response shape from "
                              + self.base_url + "/api/chat") from exc
        tool_calls = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            tool_calls.append({"function": {
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", {})}})
        return TargetResponse(text=message.get("content") or "",
                              tool_calls=tool_calls, raw=body)
