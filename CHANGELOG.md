# Changelog

## 1.3.0, 23 November 2026

- Web app: "Scan your LLM" is now the primary flow. Paste an endpoint
  URL and model, optionally add an API key, pick probe packs, confirm
  you own the endpoint or are authorised to test it, and the full suite
  runs against it with live progress, running pass/fail counts, and a
  cancel button. Adapters: OpenAI-compatible plus native Anthropic,
  Gemini and Ollama, auto-detected from the URL with a manual override.
  Findings are grouped by pack and expandable with the OWASP mapping,
  the evidence excerpt, and remediation guidance; reports download as
  JSON or HTML, generated client-side, and never contain the API key.
  The built-in mock targets remain, labelled as demos.
- API: new `POST /api/scan/batch` runs up to 10 probes per call against
  a caller-supplied target with bounded concurrency (4) and a per-batch
  deadline, reusing the existing engine and adapters. The probe
  catalogue now also carries each probe's description and remediation.
  Existing endpoints are unchanged in shape.
- Web safety: the batch endpoint is SSRF-guarded (http and https only,
  no embedded credentials, hosts must resolve only to public addresses;
  loopback, private, link-local, reserved and cloud metadata addresses
  and hostnames are refused) and outbound redirects are disabled.
  Result text is scrubbed of the caller's API key before it is
  returned. A best-effort per-IP rate limit applies to batch scans (30
  calls per 10 minutes, in-memory, so a blunt instrument rather than a
  hard quota). The batch time limits are env-configurable for
  self-hosted deployments; the public deployment runs the defaults
  (30 s per call, 50 s per batch).
- Probe metadata: per-pack remediation guidance, shown in web reports.
- 73 tests, 26 of them new for the batch endpoint, the SSRF guard, key
  redaction, and rate limiting. Verified end to end locally: a full
  76-probe scan driven through the web batch flow against llama3.2:1b
  on local Ollama scored 57.6 with 35 findings and no errors (batch
  time limits raised via the environment for the slow local machine,
  as a self-hoster scanning a local model would); mock-weak still
  scores 0.0 and mock-strict 100.0.

## 1.2.0, 22 November 2026

- Probes: 44 to 76, all still canary-based. New `rag_memory` pack (7
  probes: poisoned retrieved passages, planted false memories, citation
  laundering, conflicting sources, stored-preference poisoning, memory
  write-then-trigger). Native multi-turn probes (Crescendo escalation,
  context stuffing, persona stacking, instruction drift). New
  indirect-injection carriers (calendar invite, code comment, JSON and
  YAML data blocks, search results). Hindi and Hinglish injection and
  leakage probes. More output handling (reference-style links, HTML
  entity tricks, HTML comments) and more encodings (hex, Morse code,
  letter spacing).
- Targets: native Anthropic Messages and Google Gemini adapters, plus an
  Ollama native adapter, alongside the OpenAI-compatible one.
- Evaluators: leak similarity now also uses word n-gram containment, so
  leaks that keep the system prompt's phrasing are caught even when the
  token overlap is diluted.
- Reports: HTML format next to JSON and Markdown, with all model output
  escaped. New `compare` command diffs two JSON reports (posture delta
  overall and per category, per-probe status changes).
- CI mode: `scan --fail-under <score>` exits 1 when the score lands below
  the threshold. Bounded concurrency for probe execution via `--jobs`
  (default 4).
- 47 tests. The web app serves the same 76 probes; mock-weak still scores
  0.0 and mock-strict 100.0 on the larger set.

## 1.1.0, 22 November 2026

- Web app: a one-page UI and JSON API (FastAPI, `api/index.py`) deployed at
  https://llmposture.vercel.app. Full scans against the built-in mock
  targets run server-side; scans of real endpoints run one probe per
  request from the browser, with the caller's API key used per request and
  never stored or logged. Reports assembled in the browser match the CLI
  report shape and scoring.
- Example results: two more live local-model runs, qwen2.5:1.5b (score
  50.8, 23 findings) and gemma2:2b (score 35.6, 30 findings), with full
  reports in `examples/`.
- 33 tests, including 9 new tests for the web API.

## 1.0.0, 22 November 2026

- First release: 44 canary probes in 8 packs mapped to the OWASP Top 10
  for LLM Applications (2025), an OpenAI-compatible target adapter,
  built-in mock-weak and mock-strict targets, severity-weighted posture
  scoring, JSON and Markdown reports, and a CLI (`scan`, `list-probes`,
  `serve-mock`).
- Live local run: llama3.2:1b via Ollama scored 56.8 with 21 findings.
- Research survey with a verified CVE table in `docs/research.md`.
- 24 tests.
