"""Report writers: JSON for tooling, Markdown and HTML for humans."""

from __future__ import annotations

import html
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


def render_html(report: dict) -> str:
    """A self-contained HTML report.

    Every value taken from the report (which includes raw model output) is
    escaped before interpolation: a scanner report that rendered model
    output unescaped would itself be an output-handling vulnerability.
    """
    esc = html.escape
    meta = report["meta"]
    summary = report["summary"]
    counts = summary["counts"]
    cat_rows = []
    for category, c in sorted(summary["per_category"].items()):
        cat_rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td></tr>".format(
                esc(str(category)), c["pass"], c["fail"], c["error"],
                c["total"]))
    finding_blocks = []
    if not report["findings"]:
        finding_blocks.append("<p>No findings. Every probe was resisted.</p>")
    for f in report["findings"]:
        finding_blocks.append(
            "<section class='finding'>"
            f"<h3>{esc(str(f['probe_id']))}: {esc(str(f['name']))} "
            f"({esc(str(f['severity']))})</h3>"
            f"<p><strong>Category:</strong> {esc(str(f['category']))} "
            f"({esc(str(f['owasp']))})<br>"
            f"<strong>Why it failed:</strong> {esc(str(f['reason']))}<br>"
            f"<strong>Payload summary:</strong> "
            f"{esc(str(f['payload_summary']))}<br>"
            f"<strong>Response excerpt:</strong> "
            f"{esc(str(f['response_excerpt']))}</p></section>")
    return "\n".join([
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'>",
        "<title>LLMPosture scan report</title>",
        "<style>body{font-family:-apple-system,'Segoe UI',Roboto,Helvetica,"
        "Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;"
        "color:#1a2332;line-height:1.5}table{border-collapse:collapse}"
        "td,th{border:1px solid #d9e0ea;padding:6px 10px;text-align:left}"
        ".finding{border:1px solid #d9e0ea;border-radius:8px;"
        "padding:10px 14px;margin:10px 0}h3{margin:4px 0}</style>",
        "</head><body>",
        "<h1>LLMPosture scan report</h1>",
        f"<p>Target: {esc(str(meta.get('target', 'unknown')))}<br>"
        f"Model: {esc(str(meta.get('model', 'n/a')))}<br>"
        f"Date (UTC): {esc(str(meta.get('date', 'n/a')))}<br>"
        f"Posture score: <strong>{summary['posture_score']} / 100</strong> "
        f"({counts['fail']} failed, {counts['pass']} passed, "
        f"{counts['error']} errors, {summary['total_probes']} probes)</p>",
        "<h2>Results by category</h2>",
        "<table><tr><th>Category</th><th>Pass</th><th>Fail</th>"
        "<th>Error</th><th>Total</th></tr>",
        *cat_rows,
        "</table>",
        "<h2>Findings</h2>",
        *finding_blocks,
        "<h2>Method and limits</h2>",
        "<p>Probes use benign canaries generated per run: a protected "
        "marker token, a planted fake API key, and a planted fake customer "
        "record. A probe fails only when the target produces a canary, "
        "leaks planted content, calls a fake tool, or emits unsafe markup "
        "carrying the marker. Evaluators are heuristics and can miss "
        "paraphrased leaks. A clean score means these probes were "
        "resisted, not that the target is secure. Run LLMPosture only "
        "against systems you own or are authorised to test.</p>",
        "</body></html>",
        "",
    ])


def write_html(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(report))


def result_rows(results) -> list[dict]:
    return [asdict(r) for r in results]
