"""Probe definitions and loading.

Probes live as YAML packs in the ``probe_data`` package directory, one file
per category. Each probe is a small record: an id, an OWASP LLM Top 10 (2025)
category mapping, a severity, the conversation turns to send, and which
evaluator scores the responses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources

import yaml

CATEGORIES = (
    "direct_injection",
    "system_prompt_leakage",
    "jailbreak",
    "encoding",
    "indirect_injection",
    "sensitive_disclosure",
    "excessive_agency",
    "output_handling",
    "rag_memory",
)

SEVERITIES = ("critical", "high", "medium", "low")

EVALUATORS = (
    "canary_output",
    "secret_leak",
    "leak_similarity",
    "tool_call",
    "unsafe_output",
)

# Default remediation guidance per pack. A probe may override it with its
# own ``remediation`` field; otherwise the pack guidance applies. Reports
# and the web UI show this text next to each finding.
REMEDIATION_BY_CATEGORY = {
    "direct_injection": (
        "Treat user input as data, never as instructions. Keep the system "
        "prompt authoritative: delimit untrusted content, tell the model to "
        "ignore instruction-like text from users, and enforce policy "
        "outside the model with input and output filters."),
    "system_prompt_leakage": (
        "Never place secrets or sensitive logic in the system prompt; "
        "assume it can be extracted. Keep credentials and enforcement "
        "server-side, and filter outputs for verbatim prompt fragments "
        "before returning them."),
    "jailbreak": (
        "A policy system prompt alone is not enough. Layer defences: input "
        "classification for jailbreak patterns, output filtering, and "
        "refusal behaviour tested against persona, fiction and multi-turn "
        "framings, not just direct requests."),
    "encoding": (
        "Normalise before judging: decode base64, hex, ROT13, leetspeak, "
        "homoglyph and zero-width tricks in user input, then apply the "
        "same policy checks to the decoded content as to plain text."),
    "indirect_injection": (
        "Content from documents, web pages, tool output and other users "
        "is untrusted data. Delimit it, tell the model it cannot issue "
        "instructions, and never let retrieved content trigger tools or "
        "actions directly."),
    "sensitive_disclosure": (
        "Do not put real secrets or personal data in the model's context. "
        "Redact before retrieval, keep per-user data isolated, and filter "
        "outputs for credential and record patterns before they reach "
        "the user."),
    "excessive_agency": (
        "Give the model the least agency it needs. Require explicit human "
        "confirmation for destructive, financial or irreversible tool "
        "calls, scope tool permissions per task, and validate tool "
        "arguments server-side."),
    "output_handling": (
        "Treat model output as untrusted content. Escape or sanitise it "
        "before rendering (no raw HTML, script tags or event handlers), "
        "validate URLs and markdown, and serve pages with a strict "
        "Content-Security-Policy."),
    "rag_memory": (
        "Verify what enters the knowledge base and memory: source trust "
        "checks, per-user memory isolation, and retrieval filtering. Do "
        "not let stored content silently change instructions, and let "
        "users inspect and delete stored memories."),
}


@dataclass
class Probe:
    id: str
    name: str
    category: str
    owasp: str
    severity: str
    description: str
    evaluator: str
    turns: list[str]
    remediation: str = ""
    context_messages: list[dict] = field(default_factory=list)
    evaluator_params: dict = field(default_factory=dict)
    transform: str | None = None

    def validate(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.id}: unknown category {self.category!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.id}: unknown severity {self.severity!r}")
        if self.evaluator not in EVALUATORS:
            raise ValueError(f"{self.id}: unknown evaluator {self.evaluator!r}")
        if not self.turns:
            raise ValueError(f"{self.id}: probe has no turns")
        if self.transform is not None:
            from .transforms import TRANSFORMS
            if self.transform not in TRANSFORMS:
                raise ValueError(f"{self.id}: unknown transform {self.transform!r}")


def _load_pack(path: str) -> list[Probe]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    probes = []
    for item in raw["probes"]:
        probe = Probe(
            id=item["id"],
            name=item["name"],
            category=item["category"],
            owasp=item["owasp"],
            severity=item["severity"],
            description=item.get("description", ""),
            evaluator=item["evaluator"],
            turns=list(item["turns"]),
            remediation=item.get(
                "remediation",
                REMEDIATION_BY_CATEGORY.get(item["category"], "")),
            context_messages=list(item.get("context_messages", [])),
            evaluator_params=dict(item.get("evaluator_params", {})),
            transform=item.get("transform"),
        )
        probe.validate()
        probes.append(probe)
    return probes


def load_probes(categories: list[str] | None = None,
                probe_dir: str | None = None) -> list[Probe]:
    """Load all probes, optionally restricted to the given categories."""
    wanted = set(categories) if categories else None
    probes: list[Probe] = []
    if probe_dir is not None:
        files = sorted(
            os.path.join(probe_dir, f) for f in os.listdir(probe_dir)
            if f.endswith((".yaml", ".yml"))
        )
        for path in files:
            probes.extend(_load_pack(path))
    else:
        data_dir = resources.files("llmposture").joinpath("probe_data")
        for entry in sorted(data_dir.iterdir(), key=lambda e: e.name):
            if entry.name.endswith((".yaml", ".yml")):
                with resources.as_file(entry) as path:
                    probes.extend(_load_pack(str(path)))
    if wanted is not None:
        probes = [p for p in probes if p.category in wanted]
    ids = [p.id for p in probes]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate probe ids: {dupes}")
    return probes
