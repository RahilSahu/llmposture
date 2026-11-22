# Contributing to LLMPosture

Contributions are welcome: new probes, new target adapters, evaluator
improvements, and documentation. Please open an issue first for anything
larger than a single probe so the design can be discussed.

## Development setup

```bash
git clone https://github.com/RahilSahu/llmposture
cd llmposture
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

## Adding a probe

Probes live in `src/llmposture/probe_data/`, one YAML file per category.
Each probe needs: a unique id, a name, the category, the OWASP LLM Top 10
(2025) mapping, a severity, a short description, an evaluator, and one or
more turns.

Rules for new probes:

1. **Canaries only.** A probe's success signal must be a benign canary: the
   protected marker, a planted fake secret, a fake tool call, or unsafe
   markup carrying the marker. Never submit a probe that asks a model for
   real harmful content (weapons, malware, exploitation instructions, real
   phishing text, real personal data). Probes that cross this line will be
   closed without discussion.
2. **Reference canaries by placeholder**: `{marker}`, `{secret}`,
   `{codename}`, `{record_token}`. Values are generated per run.
3. **Encoded payloads use transforms**, not pre-encoded text, because the
   canary is random per run. See `transforms.py` and the `encoding` pack.
4. **Test it**: the probe must fail against `mock-weak` (or have a comment
   in the PR explaining why the mock legitimately resists it) and pass
   against `mock-strict`. The test suite checks pack integrity; run the two
   demo scans before submitting.

## Pull requests

- Keep changes focused; one probe pack or one feature per PR.
- Run the full test suite and both mock scans.
- Describe what the change does and how you verified it.
- No em dashes in documentation or commit messages, please; the project
  style is plain hyphens.

## Code of conduct

Be professional and constructive. Security research is welcome here;
harassment and bad-faith contributions are not.
