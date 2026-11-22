import json

from llmposture.report import build_report, render_markdown, write_json
from llmposture.runner import ProbeResult
from llmposture.scoring import summarize


def result(pid, category, severity, status):
    return ProbeResult(probe_id=pid, name=pid, category=category,
                       owasp="LLM01:2025 Prompt Injection", severity=severity,
                       status=status, reason="r", payload_summary="p",
                       response_excerpt="e", turns_sent=1)


def test_scoring_weighted():
    results = [
        result("A", "jailbreak", "high", "pass"),     # weight 3
        result("B", "jailbreak", "high", "fail"),     # weight 3
        result("C", "encoding", "low", "pass"),       # weight 1
        result("D", "encoding", "low", "error"),      # excluded
    ]
    s = summarize(results)
    assert s["counts"] == {"pass": 2, "fail": 1, "error": 1}
    assert s["posture_score"] == round(100.0 * 4 / 7, 1)
    assert [f.probe_id for f in s["findings"]] == ["B"]
    assert s["per_category"]["jailbreak"]["total"] == 2


def test_report_json_roundtrip(tmp_path):
    results = [result("A", "jailbreak", "high", "fail")]
    summary = summarize(results)
    report = build_report({"target": "t", "model": "m", "date": "2026-01-01"},
                          results, summary)
    path = str(tmp_path / "r.json")
    write_json(path, report)
    loaded = json.loads(open(path).read())
    assert loaded["summary"]["posture_score"] == 0.0
    assert loaded["findings"][0]["probe_id"] == "A"


def test_report_markdown_contents():
    results = [result("A", "jailbreak", "high", "fail"),
               result("B", "encoding", "low", "pass")]
    report = build_report({"target": "mock", "model": "m", "date": "d"},
                          results, summarize(results))
    md = render_markdown(report)
    assert "Posture score" in md
    assert "jailbreak" in md
    assert "### A:" in md
