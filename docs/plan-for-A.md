# Builder A implementation plan — agent and repair loop

Owner: A. Source of task IDs: [PRD section 8](PRD.md#8-three-person-task-board). This file tracks A's actual progress; update checkboxes as work lands, don't let it drift from `git log`.

Blocking dependency: **B1** landed on `main` in `18348ca` (`config/targets/juice-shop.json`, `docs/decisions/0001-target-pin.md`, `docs/tasks/B-checklist.md`). Commit pinned: Juice Shop `v20.2.0` / `5658473cf8814459bf89000ce373b20ed0b4eb37`, allowed path `routes/search.ts`. `baseline_image_digest` is still `null` pending B's build step. Everything below that only needed the pin (not the digest) is now unblocked.

**🛑 Current hard blocker (2026-10-09):** Guild agent sessions hang indefinitely with zero server-side events — not a config issue on our end (ruled out credentials, tool complexity, client timeouts). Escalated to Guild's team with session IDs. See A1 below for full evidence. This blocks A3 end-to-end and any real candidate proposal; A4/A5/A6 logic and tests proceed independently using fakes.

**Note:** `setup/pin-scan-baseline-spike` (B/C's earlier branch) is now stale relative to `main` — it has the Semgrep registry-rule pin (`config/semgrep/rules.lock.json`, `scripts/semgrep-scan.sh`) and B3's e2e check suite (`tests/e2e/juice-shop-checks.mjs`) that haven't landed on `main` yet. B is working on reconciling it. The Semgrep rule file is the one thing A still needs from it.

**`docs/collab.md` resolved (2026-10-09):** all five questions needing A's input answered and applied:
- `CheckResult.image_digest`/`suite_hash` (both `str | None = None`) and `Observation.release_ref: str | None` — done in `src/contracts/models.py`
- `Event.detail: str | None = None` added; `Report` now carries `baseline_image_digest`, `candidate_image_digest`, `rule_ids`, `test_suite_hash` directly
- `RepairAgent` takes an optional `event_sink: EventSink` (protocol with `emit(event) -> None`, default no-op) and emits `candidate.proposed`/`candidate.rejected`/`checks.completed`/`deploy.requested` — `src/agent/loop.py`, smoke-tested
- Agreed: A owns excluding `data/static/codefixes/` from the Guild agent's source context once A3 wires a real session (tracked below under A3)
- `SemgrepAdapter` will shell out to B/C's `scripts/semgrep-scan.sh` fetch-and-verify step once PR #1 merges, rather than reimplementing registry-rule fetch

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
- [x] Unit tests in `tests/unit/test_validator.py`: empty patch, multi-file patch (allowed/forbidden mix), malformed diff text, stale commit, hash determinism (9 cases, all passing)
- [ ] Confirm diff format assumption (`+++ b/<path>` unified diff) matches what Guild will actually emit — revisit if Guild returns full-file replacement instead of a diff

## A1 — Prove Guild tool execution and Semgrep baseline detection

- [x] `SemgrepAdapter`: real CLI wrapper, JSON parse, maps rule matches → `CheckResult` — `src/adapters/semgrep.py`
- [x] B1 merged to `main` — pinned commit/path available: `routes/search.ts` at `5658473cf8814459bf89000ce373b20ed0b4eb37`
- [ ] ⏳ BLOCKED ON `setup/pin-scan-baseline-spike` reconciliation — the pinned Semgrep registry rule (`config/semgrep/rules.lock.json`) only exists on that stale branch. Note: it uses a registry rule ID (`javascript.sequelize.security.audit...`, fetched by SHA-256 at scan time), not a local `--config <path>` rule file like `SemgrepAdapter` currently assumes — adapter needs a small update once this lands.
- [ ] Capture one real baseline JSON finding (file, line, rule ID) as evidence artifact
- [x] Guild account: workspace created (`antibody-dev`, `01a1224a-2310-3bb9-0000-99807e6c2ff8`), CLI installed and authenticated as `g3ram`
- [x] Guild: agent created (`antibody-repair-agent`, `01a12248-138c-726e-0000-1fcb7df24304`), one zero-dependency `ping` tool connected (no network/credentials, to isolate the test from tool-side failures)
- [ ] 🛑 BLOCKED — Guild: confirm a real session invokes the tool and returns a real result. **Every attempt hangs indefinitely.** `guild agent chat` and `guild agent test` both create a real server-side session and print "Processing input 1/1..." but never return; `guild session events <id>` / `guild session tasks <id>` show **zero events, zero tasks** for every attempt — the turn never starts server-side. Tried: disabling workspace "restrict account credentials" toggle (no change), confirmed managed LLM tier is active with 50M token balance (not a billing issue), confirmed via `guild agent test --timeout 60` that even the CLI's own internal timeout doesn't fire.
  - Hung session IDs for reference: `01a1224a-3674-f268-0000-828bd84b3467`, `01a1224b-3d75-f268-0000-a7d6eaed013a`, `01a12258-df18-f268-0000-f2d21e6b6128`, `01a12259-ede6-f268-0000-92eb28018fbe`, `01a1225a-e05d-f268-0000-402df81a76a8` (ran via `guild agent test`, didn't honor its own `--timeout 60`)
  - Escalated to Guild's sponsor/support team with the above evidence (2026-10-09, afternoon). Awaiting response.
- [ ] Confirm Guild agent has outbound access to call our adapters — cannot test until the above unblocks

## A3 — Scanner and patch-proposal tools

- [x] `ScannerAdapter` / `PatchAdapter` / `GuidanceAdapter` Protocol boundaries — `src/adapters/base.py`
- [x] `GuildPatchAdapter` stub — raises `GuildNotConfiguredError`/`NotImplementedError` rather than fabricating a candidate
- [ ] ⏳ BLOCKED ON A1 — wire real Guild session into `GuildPatchAdapter.propose()`
- [ ] Confirm Guild's actual output format (diff vs full-file) and adjust `CandidateValidator.changed_paths()` regex if needed
- [ ] Exclude `data/static/codefixes/` (upstream reference answer files) from whatever source context gets assembled for the Guild agent (agreed with C in `docs/collab.md` Q4) — do this in the same pass as wiring the real session
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

- [x] Emit `Event` rows at each real transition — `RepairAgent` takes an injected `EventSink`, emits `candidate.proposed`/`candidate.rejected`/`checks.completed`/`deploy.requested`. Resolved with C: C owns the host runner (`src/server/runner.py`) and the ClickHouse-backed sink implementation; A's `RepairAgent` stays runner-agnostic (default no-op sink).
- [ ] `run.state` transitions (`validating` → `failed`/`unresolved` etc.) are not emitted by `RepairAgent` itself — belongs to whoever owns `Run`, i.e. C's host runner. Confirm C is picking this up.
- [x] Fallback plan recorded: Guild blocker documented above with full evidence and escalated, per PRD's own framing of a vendor failure as a legitimate run outcome.

## Immediate next actions (in order)

1. ~~Ping B for B1 ETA~~ — done, B1 merged (`18348ca`).
2. ~~Start Guild account/auth~~ — done; blocked on Guild's response to the hung-session escalation (see above).
3. ~~Write the A4 unit tests~~ — done, 9 cases passing.
4. Resolve the two contract change requests from B (`CheckResult.image_digest`/`suite_hash`, `Observation.release_ref` optionality) via `docs/collab.md`, then apply to `src/contracts/models.py`.
5. Once `setup/pin-scan-baseline-spike` reconciles: point `SemgrepAdapter` at the real pinned Semgrep rule, capture the finding artifact.
6. Once Guild session works: wire `GuildPatchAdapter`, replace the fake adapter in a real end-to-end run.
