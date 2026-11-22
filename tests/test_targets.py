"""Native target adapters, tested against a stubbed urlopen."""

import io
import json
import urllib.request

from llmposture.targets import (AnthropicTarget, GeminiTarget,
                                OllamaNativeTarget)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def stub_urlopen(monkeypatch, response_body):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(json.dumps(response_body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


MESSAGES = [
    {"role": "system", "content": "You are a test assistant."},
    {"role": "user", "content": "Hello"},
]


def test_anthropic_request_and_response(monkeypatch):
    captured = stub_urlopen(monkeypatch, {"content": [
        {"type": "text", "text": "Hi there"},
        {"type": "tool_use", "name": "delete_records", "input": {"x": 1}},
    ]})
    target = AnthropicTarget(model="claude-test", api_key="sk-ant-test")
    resp = target.chat(MESSAGES)
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    body = captured["body"]
    assert body["system"] == "You are a test assistant."
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["max_tokens"] > 0
    assert resp.text == "Hi there"
    assert resp.tool_calls == [
        {"function": {"name": "delete_records", "arguments": {"x": 1}}}]


def test_gemini_request_and_response(monkeypatch):
    captured = stub_urlopen(monkeypatch, {"candidates": [{"content": {
        "parts": [
            {"text": "Namaste"},
            {"functionCall": {"name": "send_email", "args": {"to": "x"}}},
        ]}}]})
    target = GeminiTarget(model="gemini-test", api_key="gm-test")
    resp = target.chat(MESSAGES)
    assert captured["url"].endswith("/models/gemini-test:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "gm-test"
    body = captured["body"]
    assert body["systemInstruction"] == {
        "parts": [{"text": "You are a test assistant."}]}
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "Hello"}]}]
    assert resp.text == "Namaste"
    assert resp.tool_calls == [
        {"function": {"name": "send_email", "arguments": {"to": "x"}}}]


def test_ollama_native_request_and_response(monkeypatch):
    captured = stub_urlopen(monkeypatch, {"message": {
        "role": "assistant", "content": "Local hello",
        "tool_calls": [{"function": {"name": "lookup_record",
                                     "arguments": {"id": "7"}}}]}})
    target = OllamaNativeTarget(model="llama-test")
    resp = target.chat(MESSAGES)
    assert captured["url"] == "http://localhost:11434/api/chat"
    body = captured["body"]
    assert body["stream"] is False
    assert body["messages"][0]["role"] == "system"
    assert resp.text == "Local hello"
    assert resp.tool_calls == [
        {"function": {"name": "lookup_record", "arguments": {"id": "7"}}}]


def test_api_key_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    target = AnthropicTarget(model="m", api_key_env="ANTHROPIC_API_KEY")
    assert target.api_key == "sk-from-env"
