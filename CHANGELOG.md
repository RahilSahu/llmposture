# Changelog

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
