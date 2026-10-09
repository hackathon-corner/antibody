# Builder A implementation plan — agent and repair loop

Owner: A. Source of task IDs: [PRD section 8](PRD.md#8-three-person-task-board). This file tracks A's actual progress; update checkboxes as work lands, don't let it drift from `git log`.

Blocking dependency: **B1** (pinned Juice Shop commit + baseline image digest) blocks real Semgrep scanning and real candidate proposals. Everything markable without it is marked `[x]`; everything blocked by it is flagged `⏳ BLOCKED ON B1`.

## A2 — Shared contracts (done first, unblocks everyone)

- [x] Draft `Run`, `Candidate`, `CheckResult`, `DeployRequest`, `DeployResult`, `Observation`, `Event`, `Report` dataclasses — `src/contracts/models.py`
- [x] `RunState`, `CheckStatus`, `DeployStatus` enums
- [x] Package scaffolding (`pyproject.toml`, `src/contracts/__init__.py`)
- [x] Circulate to B/C via README handoff section
- [ ] B sign-off on `CheckResult`/`DeployRequest`/`DeployResult` shapes (needed before B4/B5 lock in)
- [ ] C sign-off on `Event`/`Report` shapes (needed before C2/C3 lock in)

## A4 — Host diff validation and immutable candidate identity

- [x] `CandidateValidator`: recompute content hash independently, never trust model-claimed hash — `src/agent/validator.py`
- [x] Reject on stale `base_commit`
- [x] Reject on any changed path outside `allowed_paths` (regex-parsed from real diff text, not declared metadata)
- [x] Smoke-tested: forbidden-path patch rejected, in-scope patch accepted and hashed
- [ ] Unit tests in `tests/unit/` covering: empty patch, multi-file patch (one allowed + one forbidden), malformed diff text
- [ ] Confirm diff format assumption (`+++ b/<path>` unified diff) matches what Guild will actually emit — revisit if Guild returns full-file replacement instead of a diff

## A1 — Prove Guild tool execution and Semgrep baseline detection

- [x] `SemgrepAdapter`: real CLI wrapper, JSON parse, maps rule matches → `CheckResult` — `src/adapters/semgrep.py`
- [ ] ⏳ BLOCKED ON B1 — point `SemgrepAdapter` at B's pinned `routes/search.ts`, confirm a stock rule matches the SQLi, or author a narrow custom rule in `config/semgrep/`
- [ ] Capture one real baseline JSON finding (file, line, rule ID) as evidence artifact
- [ ] Guild account: create workspace, authenticate CLI
- [ ] Guild: create an agent, connect one narrowly-scoped tool
- [ ] Guild: confirm a real session invokes a harmless tool and returns a real result (not a mock) — record session reference
- [ ] Confirm Guild agent has outbound access to call our adapters (resolve at first setup checkpoint; escalate to sponsor reps if blocked)

## A3 — Scanner and patch-proposal tools

- [x] `ScannerAdapter` / `PatchAdapter` / `GuidanceAdapter` Protocol boundaries — `src/adapters/base.py`
- [x] `GuildPatchAdapter` stub — raises `GuildNotConfiguredError`/`NotImplementedError` rather than fabricating a candidate
- [ ] ⏳ BLOCKED ON A1 — wire real Guild session into `GuildPatchAdapter.propose()`
- [ ] Confirm Guild's actual output format (diff vs full-file) and adjust `CandidateValidator.changed_paths()` regex if needed
- [ ] End-to-end: real Semgrep finding → real Guild candidate → validator accepts/rejects

## A5 — Connect B's verification response to bounded agent revision

- [x] `RepairAgent.attempt_repair()`: bounded at `MAX_ATTEMPTS = 2`, each rejected-before-build attempt still counts against budget — `src/agent/loop.py`
- [x] Smoke-tested with fake adapter + fake `run_checks`
- [ ] ⏳ BLOCKED ON B4 — swap fake `run_checks` for B's real isolated worker call
- [ ] Confirm `run_checks` failure modes (timeout, worker crash, partial results) are surfaced as real `CheckStatus.ERROR`/`UNKNOWN`, not silently treated as fail-and-retry
- [ ] Decide and implement what happens to the `Run.state` transition (`validating` → `failed`/`unresolved`) when `MaxAttemptsExceeded` is raised — currently just an exception, needs a host-level catch that updates `Run`/`Event`

## A6 — Narrow deploy tool guarded by actual required results

- [x] `RepairAgent.request_deploy()`: refuses unless a candidate actually passed `attempt_repair` in this process — `src/agent/loop.py`
- [ ] ⏳ BLOCKED ON B5 — call B's real deploy connector with the `DeployRequest`, handle its `DeployResult`
- [ ] Confirm deploy gating survives a process restart (per PRD §6: "a restart or timeout must reconcile with actual deployment state before retrying") — current in-memory `_last_passing_hash` does not survive a restart; needs durable state once B's host coordinator exists
- [ ] Verify host enforces the gate even if Guild asks to skip validation (adversarial test using the intentionally-overbroad candidate from PRD §4)

## A7 — Senso retrieval (stretch, after core)

- [ ] ⏳ BLOCKED ON C4 — Senso provisioned by C
- [ ] Implement `GuidanceAdapter` for Senso in `src/adapters/`
- [ ] Wire retrieved guidance IDs into `PatchAdapter.propose(guidance_ids=...)` (already a parameter)
- [ ] Ensure report marks guidance as advisory, not authoritative (PRD §5/§7)

## Cross-cutting / do not skip

- [ ] Emit `Event` rows at each real transition (scan done, candidate proposed, candidate rejected/accepted, checks run, deploy requested) for C's evidence pipeline — not yet implemented anywhere; needs a decision on who calls C's event sink (A's loop, or a host wrapper around it)
- [ ] Confirm with C whether `RepairAgent` lives inside C's host process or is called by it — affects whether `Event` emission belongs in `loop.py` or a thin wrapper
- [ ] Record a fallback plan: if Guild access is blocked past the first checkpoint, document real failure (per PRD, a vendor failure is a legitimate run outcome, not something to fake)

## Immediate next actions (in order)

1. Ping B for B1 ETA — unblocks A1's real Semgrep scan and the rest of the chain.
2. Start Guild account/auth now (no B1 dependency) — A1 Guild checkpoints.
3. Write the A4 unit tests (no external dependency, pure function, fast win).
4. Once B1 lands: run Semgrep against the real pinned file, capture the finding artifact.
5. Once Guild session works: wire `GuildPatchAdapter`, replace the fake adapter in a real end-to-end run.
