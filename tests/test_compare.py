"""Report comparison: score delta, per-category delta, changed probes."""

from llmposture.compare import compare_reports, render_compare_markdown


def _report(score, results, per_category):
    return {
        "meta": {"target": "t", "model": "m", "date": "2026-01-01"},
        "summary": {"posture_score": score,
                    "total_probes": len(results),
                    "counts": {}, "per_category": per_category},
        "findings": [],
        "results": results,
    }


def _result(pid, status):
    return {"probe_id": pid, "name": pid, "category": "jailbreak",
            "owasp": "LLM01:2025 Prompt Injection", "severity": "high",
            "status": status, "reason": "r", "payload_summary": "p",
            "response_excerpt": "e", "turns_sent": 1}


CATS_OLD = {"jailbreak": {"pass": 1, "fail": 1, "error": 0, "total": 2}}
CATS_NEW = {"jailbreak": {"pass": 2, "fail": 0, "error": 0, "total": 2}}


def test_compare_detects_improvement():
    old = _report(50.0, [_result("A", "fail"), _result("B", "pass")], CATS_OLD)
    new = _report(100.0, [_result("A", "pass"), _result("B", "pass")], CATS_NEW)
    comp = compare_reports(old, new)
    assert comp["score_delta"] == 50.0
    assert comp["counts"]["improved"] == 1
    assert comp["counts"]["regressed"] == 0
    changed = {c["probe_id"]: c for c in comp["changed"]}
    assert changed["A"]["direction"] == "improved"
    assert "B" not in changed
    assert comp["per_category"]["jailbreak"]["pass_delta"] == 1
    assert comp["per_category"]["jailbreak"]["fail_delta"] == -1


def test_compare_detects_regression_and_new_probes():
    old = _report(100.0, [_result("A", "pass")], CATS_NEW)
    new = _report(50.0, [_result("A", "fail"), _result("C", "pass")], CATS_OLD)
    comp = compare_reports(old, new)
    assert comp["score_delta"] == -50.0
    changed = {c["probe_id"]: c for c in comp["changed"]}
    assert changed["A"]["direction"] == "regressed"
    assert changed["C"]["direction"] == "added"


def test_compare_markdown_contents():
    old = _report(50.0, [_result("A", "fail")], CATS_OLD)
    new = _report(100.0, [_result("A", "pass")], CATS_NEW)
    md = render_compare_markdown(compare_reports(old, new))
    assert "Posture delta" in md
    assert "A" in md and "improved" in md
