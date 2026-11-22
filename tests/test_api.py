"""Tests for the web API in api/index.py (the Vercel entrypoint)."""

import importlib.util
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llmposture.probes import load_probes
from llmposture.targets import TargetResponse

TOTAL_PROBES = len(load_probes())

_API_PATH = Path(__file__).resolve().parent.parent / "api" / "index.py"


def _load_api_module():
    spec = importlib.util.spec_from_file_location("llmposture_web_api",
                                                  _API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = _load_api_module()
client = TestClient(api.app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["probes"] == TOTAL_PROBES


def test_index_serves_the_ui():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "LLMPosture" in resp.text
    assert "/api/scan/probe" in resp.text


def test_probes_catalogue():
    resp = client.get("/api/probes")
    assert resp.status_code == 200
    probes = resp.json()["probes"]
    assert len(probes) == TOTAL_PROBES
    for p in probes:
        assert set(p) >= {"id", "pack", "severity", "title"}
    ids = [p["id"] for p in probes]
    assert len(ids) == len(set(ids))


def test_scan_mock_weak_scores_zero():
    resp = client.post("/api/scan/mock", json={"target": "weak"})
    assert resp.status_code == 200
    report = resp.json()
    assert report["summary"]["posture_score"] == 0.0
    assert report["summary"]["counts"]["fail"] == TOTAL_PROBES
    assert len(report["findings"]) == TOTAL_PROBES
    assert len(report["results"]) == TOTAL_PROBES


def test_scan_mock_strict_scores_100():
    resp = client.post("/api/scan/mock", json={"target": "strict"})
    assert resp.status_code == 200
    report = resp.json()
    assert report["summary"]["posture_score"] == 100.0
    assert report["findings"] == []


def test_scan_mock_rejects_unknown_target():
    resp = client.post("/api/scan/mock", json={"target": "bogus"})
    assert resp.status_code == 400


def test_scan_probe_unknown_probe_id():
    resp = client.post("/api/scan/probe", json={
        "probe_id": "XX-999", "base_url": "https://example.invalid/v1",
        "model": "whatever", "api_key": "test-key"})
    assert resp.status_code == 404


def test_scan_probe_rejects_bad_base_url():
    resp = client.post("/api/scan/probe", json={
        "probe_id": "DI-001", "base_url": "ftp://example.invalid",
        "model": "whatever"})
    assert resp.status_code == 400


class _EchoMarkerTarget:
    """Fake target: complies by echoing the protected marker it was given."""

    last_kwargs = None

    def __init__(self, **kwargs):
        _EchoMarkerTarget.last_kwargs = kwargs

    def chat(self, messages):
        joined = "\n".join(m.get("content", "") for m in messages)
        match = re.search(r"LLMP-CANARY-[0-9A-F]+", joined)
        return TargetResponse(text=match.group(0) if match else "ok")


def test_scan_probe_runs_one_probe_and_never_returns_the_key(monkeypatch):
    monkeypatch.setattr(api, "OpenAICompatibleTarget", _EchoMarkerTarget)
    resp = client.post("/api/scan/probe", json={
        "probe_id": "DI-001", "base_url": "https://provider.example/v1",
        "model": "some-model", "api_key": "sk-test-do-not-leak"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["probe_id"] == "DI-001"
    assert body["status"] == "fail"
    assert "marker" in body["reason"]
    assert _EchoMarkerTarget.last_kwargs["api_key"] == "sk-test-do-not-leak"
    assert "sk-test-do-not-leak" not in resp.text
