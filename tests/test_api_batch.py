"""Tests for the batch scan endpoint, the SSRF guard, and key redaction.

The batch endpoint is what the "Scan your LLM" web flow uses. These
tests never make real outbound calls: target adapter classes are
replaced with fakes, and public URLs use an IP literal so the SSRF
guard's resolver needs no network.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llmposture.targets import TargetError, TargetResponse

_API_PATH = Path(__file__).resolve().parent.parent / "api" / "index.py"

# example.com's public IP as a literal: resolves locally, no DNS needed,
# and passes the SSRF guard.
PUBLIC_URL = "https://93.184.216.34/v1"


def _load_api_module():
    spec = importlib.util.spec_from_file_location("llmposture_web_api_batch",
                                                  _API_PATH)
    module = importlib.util.module_from_spec(spec)
    # Registered so pydantic can resolve the nested BatchTarget reference
    # inside BatchRequest through the module namespace.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


api = _load_api_module()
client = TestClient(api.app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LLMPOSTURE_ALLOW_PRIVATE_TARGETS", raising=False)
    api._rate_hits.clear()


class _EchoMarkerTarget:
    """Fake target: complies by echoing the protected marker it was given."""

    last_kwargs = None
    instances = 0

    def __init__(self, **kwargs):
        _EchoMarkerTarget.last_kwargs = kwargs
        _EchoMarkerTarget.instances += 1

    def chat(self, messages):
        joined = "\n".join(m.get("content", "") for m in messages)
        match = re.search(r"LLMP-CANARY-[0-9A-F]+", joined)
        return TargetResponse(text=match.group(0) if match else "ok")


def _batch_body(probe_ids, **target_overrides):
    target = {"base_url": PUBLIC_URL, "model": "some-model",
              "api_key": "sk-test-do-not-leak", "adapter": "openai"}
    target.update(target_overrides)
    return {"target": target, "probe_ids": probe_ids}


def test_batch_runs_probes_and_returns_structured_results(monkeypatch):
    monkeypatch.setattr(api, "OpenAICompatibleTarget", _EchoMarkerTarget)
    resp = client.post("/api/scan/batch",
                       json=_batch_body(["DI-001", "DI-002"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    results = {r["probe_id"]: r for r in body["results"]}
    for probe_id in ("DI-001", "DI-002"):
        r = results[probe_id]
        assert r["status"] == "fail"
        assert r["category"] == "direct_injection"
        assert r["severity"] in ("high", "medium", "low", "critical")
        assert r["owasp"].startswith("LLM")
        assert r["response_excerpt"]
        assert r["remediation"]  # findings carry remediation guidance
    assert _EchoMarkerTarget.last_kwargs["api_key"] == "sk-test-do-not-leak"
    assert "sk-test-do-not-leak" not in resp.text


def test_batch_supports_native_adapters(monkeypatch):
    monkeypatch.setattr(api, "AnthropicTarget", _EchoMarkerTarget)
    # Keep the real guard, but with deterministic DNS: this environment
    # cannot resolve public hostnames.
    real_validate = api.validate_target_url
    monkeypatch.setattr(
        api, "validate_target_url",
        lambda url: real_validate(
            url, resolver=_resolver_returning("93.184.216.34")))
    resp = client.post("/api/scan/batch", json=_batch_body(
        ["DI-001"], base_url="https://api.anthropic.com/v1",
        adapter="anthropic"))
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "fail"


def test_batch_rejects_more_than_the_cap():
    ids = [p["id"] for p in client.get("/api/probes").json()["probes"]]
    resp = client.post("/api/scan/batch",
                       json=_batch_body(ids[:api.BATCH_MAX_PROBES + 1]))
    assert resp.status_code == 400


def test_batch_rejects_empty_probe_list():
    resp = client.post("/api/scan/batch", json=_batch_body([]))
    assert resp.status_code == 400


def test_batch_unknown_probe_id():
    resp = client.post("/api/scan/batch", json=_batch_body(["XX-999"]))
    assert resp.status_code == 404


def test_batch_rejects_unknown_adapter():
    resp = client.post("/api/scan/batch",
                       json=_batch_body(["DI-001"], adapter="carrier-pigeon"))
    assert resp.status_code == 400


def test_batch_requires_model():
    resp = client.post("/api/scan/batch",
                       json=_batch_body(["DI-001"], model="  "))
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# SSRF guard: endpoint level
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434/v1",
    "http://localhost:11434/v1",
    "http://10.0.0.5/v1",
    "http://192.168.1.10/v1",
    "http://172.16.0.9/v1",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/v1",
    "http://metadata.google.internal/v1",
    "ftp://93.184.216.34/v1",
    "https://user:pass@93.184.216.34/v1",
])
def test_batch_rejects_non_public_targets(url):
    resp = client.post("/api/scan/batch",
                       json=_batch_body(["DI-001"], base_url=url))
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# SSRF guard: unit level, with a fake resolver
# ---------------------------------------------------------------------------

def _resolver_returning(*addresses):
    def resolve(host, port, proto=0):
        return [(None, None, None, None, (address, port))
                for address in addresses]
    return resolve


def test_guard_blocks_host_resolving_to_private_address():
    with pytest.raises(ValueError):
        api.validate_target_url(
            "https://evil.example/v1",
            resolver=_resolver_returning("10.1.2.3"))


def test_guard_blocks_host_resolving_to_metadata_address():
    with pytest.raises(ValueError):
        api.validate_target_url(
            "https://evil.example/v1",
            resolver=_resolver_returning("169.254.169.254"))


def test_guard_blocks_if_any_resolved_address_is_private():
    with pytest.raises(ValueError):
        api.validate_target_url(
            "https://evil.example/v1",
            resolver=_resolver_returning("93.184.216.34", "192.168.0.1"))


def test_guard_allows_public_host():
    url = api.validate_target_url(
        "https://api.example/v1",
        resolver=_resolver_returning("93.184.216.34"))
    assert url == "https://api.example/v1"


def test_guard_rejects_unresolvable_host():
    def boom(host, port, proto=0):
        raise OSError("name or service not known")
    with pytest.raises(ValueError):
        api.validate_target_url("https://nope.invalid/v1", resolver=boom)


def test_guard_ip_classification():
    for blocked in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "172.31.255.1",
                    "192.168.0.1", "169.254.169.254", "0.0.0.0", "::1",
                    "fe80::1", "224.0.0.1", "240.0.0.1", "not-an-ip"):
        assert api._ip_is_blocked(blocked), blocked
    for allowed in ("93.184.216.34", "8.8.8.8", "1.1.1.1",
                    "2606:4700:4700::1111"):
        assert not api._ip_is_blocked(allowed), allowed


def test_no_redirect_handler_refuses_redirects():
    handler = api._NoRedirectHandler()
    assert handler.redirect_request(
        None, None, 302, "Found", {}, "http://127.0.0.1/") is None


# ---------------------------------------------------------------------------
# Key redaction and rate limiting
# ---------------------------------------------------------------------------

class _LeakyErrorTarget:
    """Fake target whose errors echo the API key, as a provider might."""

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")

    def chat(self, messages):
        raise TargetError(f"HTTP 401 from provider: bad key {self.api_key}")


def test_batch_scrubs_the_key_from_error_results(monkeypatch):
    monkeypatch.setattr(api, "OpenAICompatibleTarget", _LeakyErrorTarget)
    resp = client.post("/api/scan/batch", json=_batch_body(["DI-001"]))
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["status"] == "error"
    assert "sk-test-do-not-leak" not in resp.text
    assert "[redacted]" in result["reason"]


def test_batch_rate_limit(monkeypatch):
    monkeypatch.setattr(api, "OpenAICompatibleTarget", _EchoMarkerTarget)
    monkeypatch.setattr(api, "RATE_LIMIT_BATCH_MAX", 2)
    for _ in range(2):
        resp = client.post("/api/scan/batch", json=_batch_body(["DI-001"]))
        assert resp.status_code == 200
    resp = client.post("/api/scan/batch", json=_batch_body(["DI-001"]))
    assert resp.status_code == 429
