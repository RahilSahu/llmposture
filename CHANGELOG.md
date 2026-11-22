# Changelog

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
