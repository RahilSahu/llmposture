"""Compare two scan reports: posture delta per category and per probe.

Used to answer the regression question: the same target scanned twice
(before and after a model update, a prompt change, or a guardrail fix),
what actually changed?
"""

from __future__ import annotations

_STATUS_RANK = {"fail": 0, "error": 1, "pass": 2}


def _direction(old_status: str, new_status: str) -> str:
    old_rank = _STATUS_RANK.get(old_status, 1)
    new_rank = _STATUS_RANK.get(new_status, 1)
    if new_rank > old_rank:
        return "improved"
    if new_rank < old_rank:
        return "regressed"
    return "changed"


def compare_reports(old: dict, new: dict) -> dict:
    """Diff two report dicts of the shape build_report produces."""
    old_results = {r["probe_id"]: r for r in old.get("results", [])}
    new_results = {r["probe_id"]: r for r in new.get("results", [])}

    changed = []
    for probe_id in sorted(set(old_results) | set(new_results)):
        old_r = old_results.get(probe_id)
        new_r = new_results.get(probe_id)
        old_status = old_r["status"] if old_r else "absent"
        new_status = new_r["status"] if new_r else "absent"
        if old_status == new_status:
            continue
        ref = new_r or old_r
        changed.append({
            "probe_id": probe_id,
            "name": ref["name"],
            "category": ref["category"],
            "severity": ref["severity"],
            "old_status": old_status,
            "new_status": new_status,
            "direction": ("added" if old_r is None else
                          "removed" if new_r is None else
                          _direction(old_status, new_status)),
        })

    old_cats = old.get("summary", {}).get("per_category", {})
    new_cats = new.get("summary", {}).get("per_category", {})
    per_category = {}
    for category in sorted(set(old_cats) | set(new_cats)):
        o = old_cats.get(category, {"pass": 0, "fail": 0, "error": 0,
                                    "total": 0})
        n = new_cats.get(category, {"pass": 0, "fail": 0, "error": 0,
                                    "total": 0})
        per_category[category] = {
            "old": o, "new": n,
            "pass_delta": n["pass"] - o["pass"],
            "fail_delta": n["fail"] - o["fail"],
        }

    old_score = old.get("summary", {}).get("posture_score", 0.0)
    new_score = new.get("summary", {}).get("posture_score", 0.0)
    return {
        "tool": "llmposture-compare",
        "old": {"target": old.get("meta", {}).get("target"),
                "date": old.get("meta", {}).get("date"),
                "posture_score": old_score},
        "new": {"target": new.get("meta", {}).get("target"),
                "date": new.get("meta", {}).get("date"),
                "posture_score": new_score},
        "score_delta": round(new_score - old_score, 1),
        "per_category": per_category,
        "changed": changed,
        "counts": {
            "improved": sum(1 for c in changed
                            if c["direction"] == "improved"),
            "regressed": sum(1 for c in changed
                             if c["direction"] == "regressed"),
            "other_changes": sum(1 for c in changed
                                 if c["direction"] not in
                                 ("improved", "regressed")),
        },
    }


def render_compare_markdown(comp: dict) -> str:
    lines = [
        "# LLMPosture report comparison",
        "",
        f"- Old: {comp['old']['target']} ({comp['old']['date']}), "
        f"score {comp['old']['posture_score']}",
        f"- New: {comp['new']['target']} ({comp['new']['date']}), "
        f"score {comp['new']['posture_score']}",
        f"- Posture delta: **{comp['score_delta']:+}** "
        f"({comp['counts']['improved']} improved, "
        f"{comp['counts']['regressed']} regressed, "
        f"{comp['counts']['other_changes']} other changes)",
        "",
        "## Per category",
        "",
        "| Category | Old pass/fail | New pass/fail | Pass delta | Fail delta |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for category, c in sorted(comp["per_category"].items()):
        lines.append(
            f"| {category} | {c['old']['pass']}/{c['old']['fail']} | "
            f"{c['new']['pass']}/{c['new']['fail']} | "
            f"{c['pass_delta']:+} | {c['fail_delta']:+} |")
    lines += ["", "## Changed probes", ""]
    if not comp["changed"]:
        lines.append("No probe changed status between the two runs.")
    for c in comp["changed"]:
        lines.append(
            f"- {c['probe_id']}: {c['name']} ({c['category']}, "
            f"{c['severity']}): {c['old_status']} -> {c['new_status']} "
            f"({c['direction']})")
    lines.append("")
    return "\n".join(lines)
