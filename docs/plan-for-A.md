# Builder A implementation plan — agent and repair loop

Owner: A. Source of task IDs: [PRD section 8](PRD.md#8-three-person-task-board). This file tracks A's actual progress; update checkboxes as work lands, don't let it drift from `git log`.

Blocking dependency: **B1** landed on `main` in `18348ca` (`config/targets/juice-shop.json`, `docs/decisions/0001-target-pin.md`, `docs/tasks/B-checklist.md`). Commit pinned: Juice Shop `v20.2.0` / `5658473cf8814459bf89000ce373b20ed0b4eb37`, allowed path `routes/search.ts`. `baseline_image_digest` is still `null` pending B's build step. Everything below that only needed the pin (not the digest) is now unblocked.

**✅ Guild blocker resolved (2026-10-09, via Cory/Guild support):** not actually hung — Guild's message-accept step currently takes 30-60s and the CLI blocks on that before polling, making it look stuck. Session `01a1225a-e05d-f268-0000-402df81a76a8` did run: the `ping` tool was called and returned `{"echoed": "A1 proof of life", "timestamp": "2026-10-09T20:29:38.868Z"}` at 20:29:38 UTC — confirmed via `guild session events <id>`. A1's Guild tool-execution criterion is met.

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
- [x] `scripts/semgrep-scan.sh`/`config/semgrep/rules.lock.json` merged to `main` (PR #1). Fixed Q10 bug: `SemgrepAdapter` now matches `check_id` by suffix, not exact equality.
- [x] Capture one real baseline JSON finding — done with real pinned source (`python scripts/target.py source --out runtime/source`) and real Semgrep 1.180.0: one finding at `routes/search.ts:23`, 0 errors. Confirmed with both the shell script and the Python adapter independently.
- [x] Guild account: workspace created (`antibody-dev`, `01a1224a-2310-3bb9-0000-99807e6c2ff8`), CLI installed and authenticated as `g3ram`
- [x] Guild: agent created (`antibody-repair-agent`, `01a12248-138c-726e-0000-1fcb7df24304`), one zero-dependency `ping` tool connected (no network/credentials, to isolate the test from tool-side failures)
- [x] Guild: confirm a real session invokes the tool and returns a real result. **Resolved** — root cause was slow (30-60s) message acceptance on Guild's side; the CLI blocks on that before polling, which looked like a hang. Session `01a1225a-e05d-f268-0000-402df81a76a8` actually completed: `ping` tool called, returned `{"echoed": "A1 proof of life", "timestamp": "2026-10-09T20:29:38.868Z"}`. Confirmed via `guild session events <id>`, not just CLI stdout.
- [ ] Confirm Guild agent has outbound access to call our adapters — next real test, now unblocked

## A3 — Scanner and patch-proposal tools

- [x] `ScannerAdapter` / `PatchAdapter` / `GuidanceAdapter` Protocol boundaries — `src/adapters/base.py`. `PatchAdapter.propose` extended with `source_files: Mapping[str, str]` (path -> content at base_commit); this is the agent's entire view of the repo, so excluding `data/static/codefixes/` is automatic — it's simply never in the map (resolves `docs/collab.md` Q4, no separate filter step needed).
- [x] `GuildPatchAdapter` implemented for real — `src/adapters/guild.py`. Works around a real Guild CLI quirk: `guild agent chat`/`test` block synchronously waiting for a reply, but message-accept takes 30-60s and the backend's `session events` endpoint has intermittent connection errors. The adapter launches `guild agent chat` only to capture the printed session ID, terminates that process, then polls `guild session events --events all` independently with its own timeout/retry loop (transient `subprocess.TimeoutExpired` on one poll is retried, not fatal). Extracts the diff from a ` ```diff ` fence in the agent's final message.
- [x] Agent rewritten (`guild-agents/antibody-repair-agent/agent.ts`): structured `inputSchema` (filePath, fileContent, baseCommit, defectSummary, defectLine, guidance), strict system prompt requiring a single unified-diff code block, no tools (pure text generation from supplied content — agent has no filesystem/network access of its own).
- [x] 15 unit tests (`tests/unit/test_guild_adapter.py`): end-to-end diff extraction, session-ID-not-found, no-diff-fence response, full timeout, multi-file-not-supported, transient-poll-retry regression, `_extract_line` parsing. All passing.
- [x] **Live end-to-end run against the real pinned defect, 2026-10-09 ~21:13 UTC**: real Semgrep finding (`routes/search.ts:23`) → real Guild session → real generated diff (parameterized the `sequelize.query` call via named `replacements` instead of string interpolation) → `CandidateValidator.validate()` accepted it, computed hash `7d235cee...`. Confirms the whole A1→A3→A4 chain works with a real candidate.
- [x] Confirm Guild's actual output format — confirmed: fenced ` ```diff ` block with `--- a/<path>` / `+++ b/<path>` headers, matches `CandidateValidator.changed_paths()` as-is, no regex change needed.
- [ ] Note: a second live run hit a sustained Guild backend issue (`session events` erroring repeatedly) and correctly raised `GuildSessionTimeoutError` after its 300s budget — no crash, no fabricated result, exactly the intended behavior. Worth flagging to Guild support as a second, separate issue from the accept-latency one.

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
4. ~~Resolve the two contract change requests from B~~ — done, applied to `src/contracts/models.py` (see `docs/collab.md` Q7).
5. ~~Guild session proof~~ — done (see above).
6. ~~Semgrep rule pin~~ — done, PR #1 merged, real finding captured.
7. ~~Wire `GuildPatchAdapter` for real~~ — done, live end-to-end run succeeded with a real validated candidate.
8. A5: wire a real `run_checks` callable once B4's worker exists (currently only smoke-tested with a fake).
9. A6: wire a real deploy connector call once B5 exists (currently only smoke-tested).
10. Flag the second Guild issue (sustained `session events` errors) to support, separate from the accept-latency one already resolved.
11. Decide `Run.state` transition ownership with C (open item under "Cross-cutting").
