# tests/unit

Owner: A/B/C.

Focused contract, patch-scope, state-transition, and report-redaction checks.

Status: `test_validator.py` covers `CandidateValidator` (A4) — in-scope/forbidden-path patches, stale base commit, empty/malformed diffs, multi-file patches, hash determinism. Run with `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/unit/`. See [the PRD](../../docs/PRD.md).
