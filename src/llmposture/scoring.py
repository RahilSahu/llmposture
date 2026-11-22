"""Posture scoring: severity-weighted aggregation of probe results."""

from __future__ import annotations

SEVERITY_WEIGHTS = {"critical": 5, "high": 3, "medium": 2, "low": 1}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def summarize(results) -> dict:
    per_category: dict[str, dict] = {}
    total_weight = 0
    passed_weight = 0
    counts = {"pass": 0, "fail": 0, "error": 0}

    for r in results:
        cat = per_category.setdefault(
            r.category, {"pass": 0, "fail": 0, "error": 0, "total": 0})
        cat[r.status] += 1
        cat["total"] += 1
        counts[r.status] += 1
        if r.status in ("pass", "fail"):
            w = SEVERITY_WEIGHTS.get(r.severity, 1)
            total_weight += w
            if r.status == "pass":
                passed_weight += w

    score = round(100.0 * passed_weight / total_weight, 1) if total_weight else 0.0
    findings = sorted(
        (r for r in results if r.status == "fail"),
        key=lambda r: (_SEVERITY_ORDER.get(r.severity, 9), r.probe_id),
    )
    return {
        "posture_score": score,
        "total_probes": len(results),
        "counts": counts,
        "per_category": per_category,
        "findings": findings,
    }
