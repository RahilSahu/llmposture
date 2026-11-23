"""LLMPosture web app: the Vercel entrypoint.

A single FastAPI application that serves the one-page UI and a small JSON
API around the ``llmposture`` scanner package:

- ``GET  /``                the scanner UI
- ``GET  /api/health``      liveness check
- ``GET  /api/probes``      the probe catalogue
- ``POST /api/scan/mock``   a full scan against a built-in mock target
- ``POST /api/scan/probe``  one probe against a caller-supplied endpoint
- ``POST /api/scan/batch``  up to 10 probes against a caller-supplied
  endpoint, the endpoint the "Scan your LLM" flow in the UI is built on

The browser drives a full scan in batches because serverless functions
are short lived: each batch runs a handful of probes concurrently inside
one function call, the browser shows progress between batches, and the
full report is assembled client-side in the same shape the CLI writes.

Bring-your-own-key scans take the caller's API key in the request body.
The key is used only for that request's outbound calls to the provider
the caller chose. It is never logged, stored, or included in any
response; result text is scrubbed of the key before it is returned.

The batch endpoint is SSRF-guarded: the target URL must be http or
https, must not carry embedded credentials, and its host must resolve
only to public addresses. Loopback, private, link-local and reserved
ranges are rejected, including the cloud metadata address
169.254.169.254 and metadata hostnames. Redirects are disabled for all
outbound calls this app makes, so a target cannot bounce a scan into a
private address after validation. For local development against a local
model only, the guard can be relaxed by setting the environment variable
LLMPOSTURE_ALLOW_PRIVATE_TARGETS=1; never set it on a public deployment.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import ipaddress
import os
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

# When the project is pip-installed (as on Vercel) ``import llmposture``
# just works. From a bare source checkout the package lives in ``src/``;
# add it as a fallback so this module also runs uninstalled.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from llmposture import __version__  # noqa: E402
from llmposture.canary import CanarySet, default_system_prompt  # noqa: E402
from llmposture.mock import MockTarget  # noqa: E402
from llmposture.probes import load_probes  # noqa: E402
from llmposture.report import build_report  # noqa: E402
from llmposture.runner import ProbeResult, run_probe, run_scan  # noqa: E402
from llmposture.scoring import summarize  # noqa: E402
from llmposture.targets import (AnthropicTarget, GeminiTarget,  # noqa: E402
                                OllamaNativeTarget,
                                OpenAICompatibleTarget)

app = FastAPI(title="LLMPosture", version=__version__)

_UI_PATH = Path(__file__).resolve().parent / "index.html"
_PROBES = None

# Batch scan limits. A batch is capped so one serverless call stays well
# inside the function time limit (vercel.json sets maxDuration 60): each
# outbound call times out after BATCH_PER_CALL_TIMEOUT seconds (30 is
# enough for slow hosted models and for endpoints that queue concurrent
# requests), probes run BATCH_MAX_WORKERS at a time, and any probe still
# running at the batch deadline comes back as an error instead of a
# verdict. The two time limits can be raised through the environment
# when the app is self-hosted for slow local models
# (LLMPOSTURE_BATCH_PER_CALL_TIMEOUT, LLMPOSTURE_BATCH_DEADLINE_SECONDS);
# the defaults are what the public deployment runs.
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


BATCH_MAX_PROBES = 10
BATCH_MAX_WORKERS = 4
BATCH_PER_CALL_TIMEOUT = _env_float("LLMPOSTURE_BATCH_PER_CALL_TIMEOUT",
                                    30.0)
BATCH_DEADLINE_SECONDS = _env_float("LLMPOSTURE_BATCH_DEADLINE_SECONDS",
                                    50.0)
BATCH_ADAPTERS = ("openai", "anthropic", "gemini", "ollama")

# Best-effort per-IP rate limit for the batch endpoint. The counters live
# in process memory, and serverless processes are short lived and not
# shared between concurrent invocations, so this only blunts casual
# abuse; it is not a hard quota. It is sized so one full scan (the UI
# sends the 76 probes in batches of 8, i.e. 10 calls) fits comfortably.
RATE_LIMIT_BATCH_MAX = 30
RATE_LIMIT_WINDOW_SECONDS = 600.0


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on outbound calls.

    A target that answers with a redirect to a private address would
    otherwise bypass the SSRF check, which validates the original URL.
    Returning None makes urllib raise HTTPError for any redirect.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


urllib.request.install_opener(
    urllib.request.build_opener(_NoRedirectHandler()))


def _probes():
    global _PROBES
    if _PROBES is None:
        _PROBES = load_probes()
    return _PROBES


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
    "instance-data",
    "instance-data-compute",
}


def _ip_is_blocked(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _private_targets_allowed() -> bool:
    """Local-development escape hatch; never set on a public deployment."""
    return os.environ.get("LLMPOSTURE_ALLOW_PRIVATE_TARGETS") == "1"


def validate_target_url(url: str, resolver=None) -> str:
    """Validate a caller-supplied target URL for the batch endpoint.

    Returns the URL unchanged when it is acceptable. Raises ValueError
    with a caller-safe message otherwise: non-http(s) scheme, embedded
    credentials, a blocked metadata hostname, an unresolvable host, or a
    host that resolves to any non-public address.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url must start with http:// or https://")
    host = parsed.hostname
    if not host:
        raise ValueError("base_url must include a host")
    if parsed.username or parsed.password:
        raise ValueError("base_url must not contain embedded credentials")
    if _private_targets_allowed():
        return url
    host_l = host.lower()
    if host_l in _BLOCKED_HOSTNAMES or host_l.endswith(".localhost"):
        raise ValueError(f"refusing to scan blocked host: {host}")
    if resolver is None:
        resolver = socket.getaddrinfo
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = resolver(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ValueError(f"could not resolve host: {host}") from None
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise ValueError(f"could not resolve host: {host}")
    for address in addresses:
        if _ip_is_blocked(address):
            raise ValueError(
                f"refusing to scan {host}: it resolves to a non-public "
                f"address ({address}). The hosted scanner only scans "
                "public endpoints; run LLMPosture locally to scan "
                "private or local models.")
    return url


# ---------------------------------------------------------------------------
# Per-IP rate limit (best effort, in-memory; see the note at the top)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


def _rate_limit_check(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(ip, [])
                if now - t < RATE_LIMIT_WINDOW_SECONDS]
        if len(hits) >= RATE_LIMIT_BATCH_MAX:
            _rate_hits[ip] = hits
            return False
        hits.append(now)
        _rate_hits[ip] = hits
        return True


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
         "title": p.name, "owasp": p.owasp, "description": p.description,
         "remediation": p.remediation}
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


def _result_payload(result, probe) -> dict:
    return {
        "probe_id": result.probe_id, "name": result.name,
        "category": result.category, "owasp": result.owasp,
        "severity": result.severity, "status": result.status,
        "reason": result.reason,
        "payload_summary": result.payload_summary,
        "response_excerpt": result.response_excerpt,
        "turns_sent": result.turns_sent,
        "description": probe.description if probe else "",
        "remediation": probe.remediation if probe else "",
    }


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
    return _result_payload(result, probe)


# ---------------------------------------------------------------------------
# Batch scanning: the "Scan your LLM" flow
# ---------------------------------------------------------------------------

class BatchTarget(BaseModel):
    base_url: str = ""
    model: str
    api_key: str | None = None
    adapter: str = "openai"


class BatchRequest(BaseModel):
    target: BatchTarget
    probe_ids: list[str]


def _effective_base_url(spec: BatchTarget) -> str:
    base = (spec.base_url or "").strip()
    if spec.adapter == "anthropic":
        return base or "https://api.anthropic.com/v1"
    if spec.adapter == "gemini":
        return base or "https://generativelanguage.googleapis.com/v1beta"
    if spec.adapter == "ollama":
        return base or "http://localhost:11434"
    return base


def _build_batch_target(spec: BatchTarget, base_url: str):
    key = spec.api_key or None
    if spec.adapter == "anthropic":
        return AnthropicTarget(model=spec.model, api_key=key,
                               base_url=base_url,
                               timeout=BATCH_PER_CALL_TIMEOUT)
    if spec.adapter == "gemini":
        return GeminiTarget(model=spec.model, api_key=key,
                            base_url=base_url,
                            timeout=BATCH_PER_CALL_TIMEOUT)
    if spec.adapter == "ollama":
        return OllamaNativeTarget(model=spec.model, base_url=base_url,
                                  timeout=BATCH_PER_CALL_TIMEOUT)
    return OpenAICompatibleTarget(base_url=base_url, model=spec.model,
                                  api_key=key,
                                  timeout=BATCH_PER_CALL_TIMEOUT)


def _run_batch(target, probes, canaries, system_prompt) -> list:
    """Run a batch concurrently with a hard deadline.

    Probes still running at the deadline come back as errors; their
    threads are left to finish in the background (the pool is not joined)
    so the response stays inside the function time limit.
    """
    by_id: dict[str, ProbeResult] = {}
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=BATCH_MAX_WORKERS)
    try:
        futures = {
            pool.submit(run_probe, target, p, canaries, system_prompt): p
            for p in probes
        }
        done, not_done = concurrent.futures.wait(
            futures, timeout=BATCH_DEADLINE_SECONDS)
        for fut in done:
            probe = futures[fut]
            try:
                by_id[probe.id] = fut.result()
            except Exception as exc:  # one bad probe must not sink the batch
                by_id[probe.id] = ProbeResult(
                    probe_id=probe.id, name=probe.name,
                    category=probe.category, owasp=probe.owasp,
                    severity=probe.severity, status="error",
                    reason=f"probe failed unexpectedly: {exc}",
                    payload_summary=probe.turns[0][:160],
                    response_excerpt="", turns_sent=0)
        for fut in not_done:
            probe = futures[fut]
            by_id[probe.id] = ProbeResult(
                probe_id=probe.id, name=probe.name,
                category=probe.category, owasp=probe.owasp,
                severity=probe.severity, status="error",
                reason="probe exceeded the batch time limit",
                payload_summary=probe.turns[0][:160],
                response_excerpt="", turns_sent=0)
    finally:
        pool.shutdown(wait=False)
    return [by_id[p.id] for p in probes]


def _scrub(text: str, secret: str | None) -> str:
    if secret and text and secret in text:
        return text.replace(secret, "[redacted]")
    return text


@app.post("/api/scan/batch")
def scan_batch(req: BatchRequest, request: Request) -> dict:
    if not _rate_limit_check(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="rate limit reached for batch scans; wait a few "
                   "minutes or run the CLI locally")
    spec = req.target
    if spec.adapter not in BATCH_ADAPTERS:
        raise HTTPException(
            status_code=400,
            detail=f"adapter must be one of {', '.join(BATCH_ADAPTERS)}")
    if not spec.model.strip():
        raise HTTPException(status_code=400, detail="model is required")
    if not req.probe_ids:
        raise HTTPException(
            status_code=400, detail="probe_ids must not be empty")
    if len(req.probe_ids) > BATCH_MAX_PROBES:
        raise HTTPException(
            status_code=400,
            detail=f"at most {BATCH_MAX_PROBES} probes per batch")
    catalogue = {p.id: p for p in _probes()}
    wanted, seen = [], set()
    for probe_id in req.probe_ids:
        if probe_id not in catalogue:
            raise HTTPException(
                status_code=404, detail=f"unknown probe id: {probe_id}")
        if probe_id not in seen:
            seen.add(probe_id)
            wanted.append(catalogue[probe_id])
    base_url = _effective_base_url(spec)
    if spec.adapter == "openai" and not base_url:
        raise HTTPException(
            status_code=400, detail="base_url is required")
    try:
        validate_target_url(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    target = _build_batch_target(spec, base_url)
    canaries = CanarySet.generate()
    results = _run_batch(target, wanted, canaries,
                         default_system_prompt(canaries))
    key = spec.api_key or None
    payload = []
    for probe, result in zip(wanted, results):
        item = _result_payload(result, probe)
        if key:
            for field in ("reason", "payload_summary", "response_excerpt"):
                item[field] = _scrub(item[field], key)
        payload.append(item)
    return {"results": payload, "count": len(payload)}
