"""Report writers: JSON for tooling, Markdown for humans."""

from __future__ import annotations

import json
from dataclasses import asdict


def build_report(meta: dict, results, summary: dict) -> dict:
    return {
        "tool": "llmposture",
        "meta": meta,
        "summary": {
            "posture_score": summary["posture_score"],
            "total_probes": summary["total_probes"],
            "counts": summary["counts"],
            "per_category": summary["per_category"],
        },
        "findings": [
            {
                "probe_id": r.probe_id, "name": r.name, "category": r.category,
                "owasp": r.owasp, "severity": r.severity, "reason": r.reason,
                "payload_summary": r.payload_summary,
                "response_excerpt": r.response_excerpt,
            }
            for r in summary["findings"]
        ],
        "results": [
            {
                "probe_id": r.probe_id, "name": r.name, "category": r.category,
                "owasp": r.owasp, "severity": r.severity, "status": r.status,
                "reason": r.reason, "payload_summary": r.payload_summary,
                "response_excerpt": r.response_excerpt,
                "turns_sent": r.turns_sent,
            }
            for r in results
        ],
    }


def write_json(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


def render_markdown(report: dict) -> str:
    meta = report["meta"]
    summary = report["summary"]
    lines = [
        "# LLMPosture scan report",
        "",
        f"- Target: {meta.get('target', 'unknown')}",
        f"- Model: {meta.get('model', 'n/a')}",
        f"- Date (UTC): {meta.get('date', 'n/a')}",
        f"- Posture score: **{summary['posture_score']} / 100** "
        f"({summary['counts']['fail']} failed, {summary['counts']['pass']} passed, "
        f"{summary['counts']['error']} errors, {summary['total_probes']} probes)",
        "",
        "## Results by category",
        "",
        "| Category | Pass | Fail | Error | Total |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for category, c in sorted(summary["per_category"].items()):
        lines.append(
            f"| {category} | {c['pass']} | {c['fail']} | {c['error']} | {c['total']} |")
    lines += ["", "## Findings", ""]
    if not report["findings"]:
        lines.append("No findings. Every probe was resisted.")
    for f in report["findings"]:
        lines += [
            f"### {f['probe_id']}: {f['name']} ({f['severity']})",
            "",
            f"- Category: {f['category']} ({f['owasp']})",
            f"- Why it failed: {f['reason']}",
            f"- Payload summary: {f['payload_summary']}",
            f"- Response excerpt: {f['response_excerpt']}",
            "",
        ]
    lines += [
        "## Method and limits",
        "",
        "Probes use benign canaries generated per run: a protected marker "
        "token, a planted fake API key, and a planted fake customer record. "
        "A probe fails only when the target produces a canary, leaks planted "
        "content, calls a fake tool, or emits unsafe markup carrying the "
        "marker. Evaluators are heuristics and can miss paraphrased leaks. "
        "A clean score means these probes were resisted, not that the target "
        "is secure. Run LLMPosture only against systems you own or are "
        "authorised to test.",
        "",
    ]
    return "\n".join(lines)


def write_markdown(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))


def result_rows(results) -> list[dict]:
    return [asdict(r) for r in results]
