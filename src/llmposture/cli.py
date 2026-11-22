"""LLMPosture command line interface.

Usage:
    llmposture scan --target mock-weak
    llmposture scan --target openai-compatible --base-url http://localhost:11434/v1 --model llama3.2:1b
    llmposture scan --target openai-compatible --base-url https://api.openai.com/v1 --model gpt-4o-mini --api-key-env OPENAI_API_KEY
    llmposture list-probes
    llmposture serve-mock --mode weak --port 8000
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .canary import CanarySet, default_system_prompt
from .mock import MockTarget
from .probes import CATEGORIES, load_probes
from .report import build_report, write_json, write_markdown
from .runner import run_scan
from .scoring import summarize
from .targets import OpenAICompatibleTarget


def _cmd_list_probes(args) -> int:
    probes = load_probes(args.categories)
    for p in probes:
        print(f"{p.id:<8} {p.category:<22} {p.severity:<9} {p.name}")
    print(f"\n{len(probes)} probes")
    return 0


def _build_target(args, canaries: CanarySet):
    if args.target == "mock-weak":
        return MockTarget("weak", canaries), "mock-weak (built-in)"
    if args.target == "mock-strict":
        return MockTarget("strict", canaries), "mock-strict (built-in)"
    if not args.base_url or not args.model:
        raise SystemExit("--base-url and --model are required for "
                         "the openai-compatible target")
    target = OpenAICompatibleTarget(
        base_url=args.base_url, model=args.model,
        api_key_env=args.api_key_env, timeout=args.timeout)
    return target, f"{args.base_url} model={args.model}"


def _cmd_scan(args) -> int:
    canaries = CanarySet.generate()
    probes = load_probes(args.categories)
    target, target_label = _build_target(args, canaries)

    if args.no_system_prompt:
        system_prompt = None
    elif args.system_prompt_file:
        with open(args.system_prompt_file, "r", encoding="utf-8") as fh:
            system_prompt = canaries.substitute(fh.read())
    elif args.target in ("mock-weak", "mock-strict"):
        system_prompt = default_system_prompt(canaries)
    else:
        system_prompt = default_system_prompt(canaries)

    print(f"LLMPosture {__version__} scanning {target_label}")
    print(f"{len(probes)} probes loaded; canaries generated for this run")
    results = run_scan(target, probes, canaries, system_prompt, judge=args.judge)
    summary = summarize(results)

    meta = {
        "target": target_label,
        "model": args.model or args.target,
        "date": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "judge": bool(args.judge),
        "system_prompt_under_test": bool(system_prompt),
    }
    report = build_report(meta, results, summary)
    write_json(args.out + ".json", report)
    write_markdown(args.out + ".md", report)

    for category, c in sorted(summary["per_category"].items()):
        print(f"  {category:<22} pass {c['pass']:<3} fail {c['fail']:<3} "
              f"error {c['error']}")
    print(f"Posture score: {summary['posture_score']} / 100 "
          f"({summary['counts']['fail']} findings)")
    print(f"Reports written to {args.out}.json and {args.out}.md")
    return 0


def _cmd_serve_mock(args) -> int:
    canaries = CanarySet(
        marker=args.marker or "LLMP-CANARY-DEMO0001",
        secret=args.secret or "sk-llmposture-test-demo000000000001",
        codename=args.codename or "ZEPHYR-DEMO01",
        record_token=args.record_token or "CUST-REC-DEMO0001",
    )
    mock = MockTarget(args.mode, canaries)
    system_prompt = default_system_prompt(canaries)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep stdout clean
            pass

        def do_POST(self):
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return
            messages = body.get("messages", [])
            resp = mock.chat(messages)
            payload = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": body.get("model", f"mock-{args.mode}"),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": resp.text},
                    "finish_reason": "stop",
                }],
            }
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Serving mock-{args.mode} on http://127.0.0.1:{args.port}/v1")
    print("System prompt in use (save it and pass --system-prompt-file "
          "to a scan to align canaries):")
    print(system_prompt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="llmposture",
        description="Behavioural security scanner for LLMs. Authorised use only.")
    parser.add_argument("--version", action="version",
                        version=f"llmposture {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="run probes against a target")
    p_scan.add_argument("--target", default="mock-weak",
                        choices=["mock-weak", "mock-strict", "openai-compatible"])
    p_scan.add_argument("--base-url", help="OpenAI-compatible base URL, e.g. http://localhost:11434/v1")
    p_scan.add_argument("--model", help="model name for the target endpoint")
    p_scan.add_argument("--api-key-env", default="OPENAI_API_KEY",
                        help="environment variable holding the API key (default OPENAI_API_KEY)")
    p_scan.add_argument("--timeout", type=float, default=60.0)
    p_scan.add_argument("--categories", nargs="*", choices=list(CATEGORIES),
                        help="restrict to these probe categories")
    p_scan.add_argument("--system-prompt-file",
                        help="file with the system prompt under test (canary placeholders are substituted)")
    p_scan.add_argument("--no-system-prompt", action="store_true",
                        help="do not send a system prompt with the probes")
    p_scan.add_argument("--judge", action="store_true",
                        help="enable the optional LLM-as-judge second pass (off by default)")
    p_scan.add_argument("--out", default="llmposture-report",
                        help="report path prefix (writes .json and .md)")
    p_scan.set_defaults(func=_cmd_scan)

    p_list = sub.add_parser("list-probes", help="list loaded probes")
    p_list.add_argument("--categories", nargs="*", choices=list(CATEGORIES))
    p_list.set_defaults(func=_cmd_list_probes)

    p_serve = sub.add_parser("serve-mock", help="serve a mock target over HTTP")
    p_serve.add_argument("--mode", default="weak", choices=["weak", "strict"])
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--marker")
    p_serve.add_argument("--secret")
    p_serve.add_argument("--codename")
    p_serve.add_argument("--record-token")
    p_serve.set_defaults(func=_cmd_serve_mock)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
