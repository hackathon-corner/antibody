# src/agent

Owner: A.

Repair agent and bounded orchestration. Runtime integration follows vendor setup.

Status: `validator.py` (A4 — host diff validation, immutable content hash) and `loop.py` (A5 bounded 2-attempt repair loop, A6 gated deploy request) implemented and smoke-tested. Still blocked on A1 (real Guild session) before `GuildPatchAdapter` can propose real candidates. See [the PRD](../../docs/PRD.md).
