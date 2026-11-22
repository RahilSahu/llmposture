"""End-to-end scans against the built-in mock targets."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from llmposture.canary import CanarySet, default_system_prompt
from llmposture.mock import MockTarget
from llmposture.probes import load_probes
from llmposture.runner import run_scan
from llmposture.scoring import summarize
from llmposture.targets import OpenAICompatibleTarget


def scan(mode):
    canaries = CanarySet.generate()
    target = MockTarget(mode, canaries)
    results = run_scan(target, load_probes(), canaries,
                       default_system_prompt(canaries))
    return summarize(results), results


def test_mock_weak_is_flagged():
    summary, _ = scan("weak")
    assert summary["counts"]["fail"] >= 20
    assert summary["posture_score"] < 50


def test_mock_strict_scores_clean():
    summary, results = scan("strict")
    assert summary["counts"]["fail"] == 0
    assert summary["counts"]["error"] == 0
    assert summary["posture_score"] == 100.0


def test_http_end_to_end_against_served_mock():
    canaries = CanarySet.generate()
    mock = MockTarget("weak", canaries)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            resp = mock.chat(body.get("messages", []))
            payload = {"choices": [{"message": {
                "role": "assistant", "content": resp.text}}]}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = OpenAICompatibleTarget(
            base_url=f"http://127.0.0.1:{port}/v1", model="mock-weak")
        probes = [p for p in load_probes() if p.id in ("DI-001", "SP-001")]
        results = run_scan(target, probes, canaries,
                           default_system_prompt(canaries))
        assert all(r.status == "fail" for r in results)
    finally:
        server.shutdown()
