"""LLMPosture web app: the Vercel entrypoint.

A single FastAPI application that serves the one-page UI and a small JSON
API around the ``llmposture`` scanner package:

- ``GET  /``                the scanner UI
- ``GET  /api/health``      liveness check
- ``GET  /api/probes``      the probe catalogue
- ``POST /api/scan/mock``   a full scan against a built-in mock target
- ``POST /api/scan/probe``  one probe against a caller-supplied endpoint

The per-probe endpoint exists because serverless functions are short
lived: the browser runs the probes one at a time, shows progress, and
assembles the full report client-side in the same shape the CLI writes.

Bring-your-own-key scans take the caller's API key in the request body.
The key is used only for that request's outbound call to the provider the
caller chose. It is never logged, stored, or included in any response.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

# When the project is pip-installed (as on Vercel) ``import llmposture``
# just works. From a bare source checkout the package lives in ``src/``;
# add it as a fallback so this module also runs uninstalled.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from llmposture import __version__  # noqa: E402
from llmposture.canary import CanarySet, default_system_prompt  # noqa: E402
from llmposture.mock import MockTarget  # noqa: E402
from llmposture.probes import load_probes  # noqa: E402
from llmposture.report import build_report  # noqa: E402
from llmposture.runner import run_probe, run_scan  # noqa: E402
from llmposture.scoring import summarize  # noqa: E402
from llmposture.targets import OpenAICompatibleTarget  # noqa: E402

app = FastAPI(title="LLMPosture", version=__version__)

_UI_PATH = Path(__file__).resolve().parent / "index.html"
_PROBES = None


def _probes():
    global _PROBES
    if _PROBES is None:
        _PROBES = load_probes()
    return _PROBES


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _UI_PATH.read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__,
            "probes": len(_probes())}


@app.get("/api/probes")
def probes() -> dict:
    return {"probes": [
        {"id": p.id, "pack": p.category, "severity": p.severity,
         "title": p.name, "owasp": p.owasp}
        for p in _probes()
    ]}


class MockScanRequest(BaseModel):
    target: str


@app.post("/api/scan/mock")
def scan_mock(req: MockScanRequest) -> dict:
    if req.target not in ("weak", "strict"):
        raise HTTPException(
            status_code=400, detail="target must be 'weak' or 'strict'")
    canaries = CanarySet.generate()
    target = MockTarget(req.target, canaries)
    results = run_scan(target, _probes(), canaries,
                       default_system_prompt(canaries))
    summary = summarize(results)
    meta = {
        "target": f"mock-{req.target} (built-in)",
        "model": f"mock-{req.target}",
        "date": _utcnow(),
        "judge": False,
        "system_prompt_under_test": True,
    }
    return build_report(meta, results, summary)


class ProbeRequest(BaseModel):
    probe_id: str
    base_url: str
    model: str
    api_key: str | None = None


@app.post("/api/scan/probe")
def scan_probe(req: ProbeRequest) -> dict:
    probe = next((p for p in _probes() if p.id == req.probe_id), None)
    if probe is None:
        raise HTTPException(
            status_code=404, detail=f"unknown probe id: {req.probe_id}")
    if not req.base_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="base_url must start with http:// or https://")
    if not req.model.strip():
        raise HTTPException(status_code=400, detail="model is required")
    canaries = CanarySet.generate()
    target = OpenAICompatibleTarget(
        base_url=req.base_url, model=req.model,
        api_key=req.api_key or None, timeout=50.0)
    result = run_probe(target, probe, canaries,
                       default_system_prompt(canaries))
    return {
        "probe_id": result.probe_id, "name": result.name,
        "category": result.category, "owasp": result.owasp,
        "severity": result.severity, "status": result.status,
        "reason": result.reason,
        "payload_summary": result.payload_summary,
        "response_excerpt": result.response_excerpt,
        "turns_sent": result.turns_sent,
    }
