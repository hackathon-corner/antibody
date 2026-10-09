# Collaboration questions and answers

A = G3Ram (agent, repair loop) · B = jguharaman (target, checks, deploy) · C = srismart (evidence, UI, extra sponsors)

How to use this file:
- Add a question under **Open** as `Q<n> (from → to)`. Use the next free number and never reuse one.
- Answer underneath with `**Answer (X, date):**`. When it's settled, move the question to **Resolved**.
- Link evidence (commit, PR, run URL) rather than restating it. Mark anything not yet observed as such.

## Open

### Q5 (C → B): Check-suite language
`tests/e2e/juice-shop-checks.mjs` in PR #1 is Node with no dependencies. It's verified against the baseline, the build-spike image, and a search-disabled mutant. B's checklist says the suite should be Python. Are you keeping the `.mjs`, or porting it? If you port it, please keep the fixture file and check IDs, so evidence from both runs stays comparable.

### Q6 (C → B): Public host and image access
- Which public host: Akash, or a fallback? C has no Akash account.
- The spike image is in a **private** GHCR package (`ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b…`). The host either needs a read-only pull token, or we make the package public (it's a deliberately vulnerable app, so prefer the token).
- With Docker unavailable on B's machine, the `build-target` GitHub Actions workflow in PR #1 can produce baseline and candidate images by digest. Want to use it for B1's `baseline_image_digest`?

**Update (C, 2026-10-09):** C has created the Akash account (console.akash.network). B, please don't create a second one. Plan is Akash for both services (B's Juice Shop candidate, C's evidence API + dashboard), with Render/Fly/Railway as fallback only if Akash is slow. Account has $25 credit loaded; no deployment made yet. Image access still open: read-only GHCR pull token preferred.

**Answer (B, 2026-10-09):**
- Host: Akash, from C's account. B won't create a second one. **C submits the deployment through the console.**
- Image access: **make the `antibody-target` GHCR package public.** A pull token in the SDL would be visible to the Akash provider. The image is public upstream source plus our patch, with nothing secret in it. B will flip the visibility.
- Baseline digest: built locally now that Docker works (`sha256:e106dde7…` image ID; see the B checklist). The CI workflow still produces the registry digests we deploy.
- Handoff for C: render the SDL with `python scripts/render_akash_sdl.py --image ghcr.io/hackathon-corner/antibody-target@sha256:<digest>` (digest only; tags are refused), deploy the file it writes, then send B the lease URL. B probes it from outside with `scripts/probe_public.py`. Runbook: [infra/akash/README.md](../infra/akash/README.md). Spike image to deploy (from [run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899) build record): `ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b193d5c9800892992f7e3f93d40c91811bd1602a8f6428ad8020668a8`, served name `OWASP Juice Shop (Antibody build spike)`. The package is still private until B flips it; an anonymous pull currently returns 401.

### Q8 (C → team): Remaining sponsor accounts
ClickHouse is done (srismart). Still needed, each with its own key in the ignored `.env` and never in chat or source:
- **Senso:** C4. This blocks A7.
- **ElevenLabs:** C5. It needs the deployed evidence API first.
- **Pi:** C6. Someone needs to ask the sponsor what integration exists.
- **Akash:** B2. Account created by C (2026-10-09); deployment still pending.

Who creates each, and is the Guild hang (A1) still blocked? Is there anything C can help with on it?

**Answer (A, 2026-10-09):** Still blocked. Guild agent sessions (`guild agent chat` / `guild agent test`) create a real server-side session but never process a turn — `guild session events <id>` / `guild session tasks <id>` show zero events/tasks, and even the CLI's own `--timeout 60` doesn't fire. Ruled out: missing LLM credential (managed tier confirmed active, 50M token balance), workspace credential restriction (disabled, no change), tool complexity (reduced to one zero-dependency `ping` tool, still hangs). Escalated to Guild's sponsor/support contact with five hung session IDs — see `docs/plan-for-A.md` A1 section for the full list. Nothing actionable for C on this right now; it's on Guild's side. Will update this file as soon as there's a response.

**Update (C, 2026-10-09, from A's plan 318db4c):** The Guild hang is resolved. Guild's message accept takes 30–60 s and the CLI blocks before polling. A real `ping` tool call has been confirmed in session `01a1225a-…`. The other Q8 accounts (Senso, ElevenLabs, Pi, Akash) are still open.

## Resolved

### Q10 (C → A): `SemgrepAdapter` exact `check_id` match will miss the finding
When Semgrep runs a rule from a **local file**, it prefixes `check_id` with the file's directory path. Observed today with the pinned rule fetched to a temp directory: `check_id` came back as `private.tmp.<…>.javascript.sequelize.security.audit.sequelize-injection-express.express-sequelize-injection`. `SemgrepAdapter.scan` compares `r.get("check_id") == rule_id`, so on the vulnerable baseline it would report PASS ("no match"). `scripts/semgrep-scan.sh` (now on main) matches with `endswith(rule_id)` for this reason. Suggest the same in the adapter, plus a test with a prefixed `check_id`.

C's `src/server/runner.py` fails the run with "selected rule did not match the baseline" when the scanner reports no FAIL, so this would show up as a failed run rather than a silent pass. It still blocks every run.

**Answer (A, 2026-10-09):** Fixed. `SemgrepAdapter.scan` now matches `r.get("check_id", "").endswith(rule_id)` instead of exact equality (`src/adapters/semgrep.py`). Added `tests/unit/test_semgrep_adapter.py` with 6 cases: prefixed check_id (reproducing exactly what you observed), bare registry ID, no-match-is-pass, a negative case confirming `endswith` doesn't cross-match an unrelated rule ending in similar text, and the existing scan-error/exit-code paths. All pass. Good catch — this would have silently broken every real run.

### Q9 (A → C): `EventSink.emit` vs `ClickHouseEventStore.insert` shape mismatch
Per Q2's resolution, `RepairAgent` now takes an injected `event_sink: EventSink` with `emit(event: Event) -> None` (implemented in `src/agent/loop.py`, 95e8d16). C's `ClickHouseEventStore.insert(events: list[Event]) -> int` (5c53851) is a batch API with a different signature — not a drop-in match for the sink protocol.

Whoever writes `src/server/runner.py` (C, per Q2) needs either:
1. A thin single-event adapter wrapping `ClickHouseEventStore.insert([event])`, or
2. `RepairAgent`/`EventSink` changed to batch (bigger change, affects A's loop).

A suggests (1) — keeps `RepairAgent` emitting per-transition as each happens, and the runner can batch/buffer before calling `insert` if that matters for ClickHouse write volume. Flagging rather than silently leaving it for whoever wires the runner to discover.

**Answer (C, 2026-10-09):** Went with (1). `ClickHouseEventStore.emit(event)` now implements `EventSink` by calling `insert([event])`, so the runner passes the store straight to `RepairAgent(event_sink=...)`. A unit test covers it. Per-event inserts are fine at this volume: a handful of events per run.

Side effect of the new `Event.detail`: the store derives its columns from the `Event` dataclass, so `detail` had to exist in the table. `ensure_schema()` now adds it (`ADD COLUMN IF NOT EXISTS`). It was applied to the live table and existing rows read back with `detail = null`. A new test fails if an `Event` field has no table column, so future contract additions get caught.

### Q1 (A → C): Sign-off on `Event` and `Report` shapes
**Answer (C, 2026-10-09):** `Event` works as-is. C2 implements it column-for-column in `antibody.events` (#2), and a real insert and query were verified. Two requests, which won't be changed unilaterally:
1. Add an optional `detail: str | None` to `Event` for small redacted JSON, such as check counts or image digest. Without it, the dashboard can show only the outcome string.
2. `Report` needs its input identities for PRD §5: baseline/candidate image digests, rule IDs, and the test-suite hash. Today they're only reachable through `checks`. Either add the fields or agree that `Report` is built from `Run` + `Candidate` + `DeployResult`.

A, please confirm or push back. C won't build the report endpoint until this is settled.

**Answer (A, 2026-10-09):** Agreed on both, implemented in `src/contracts/models.py`:
1. `Event.detail: str | None = None` added.
2. Went with "add the fields" — `Report` now carries `baseline_image_digest: str`, `candidate_image_digest: str | None`, `rule_ids: tuple[str, ...]`, `test_suite_hash: str` directly, alongside `checks`/`observations`. Simpler for the report endpoint than re-deriving from `Run`+`Candidate`+`DeployResult`, and matches how `Run` already carries these fields.

### Q2 (A → C): Who emits events, and does `RepairAgent` run inside C's host process?
**Answer (C, 2026-10-09), proposal:**
- Keep the evidence API (`src/server/app.py`) read-only and separate. It must never run the agent or hold deploy credentials.
- Run the agent from a separate host runner process. `RepairAgent` takes an injected `EventSink` with `emit(event: Event) -> None`. C provides the ClickHouse implementation (`ClickHouseEventStore.insert`); tests use an in-memory sink.
- Use `adapters.clickhouse_events.stable_event_id(run_id, event_type, emitter, key)` for IDs, so retries deduplicate.
- Suggested event types: `scan.baseline`, `candidate.proposed`, `candidate.rejected`, `checks.completed`, `deploy.requested`, `deploy.result`, `probe.observed`, `run.state`.

Open point: who owns the host runner? C can write a thin `src/server/runner.py` that wires A's loop, B's worker and connector, and the sink, if A and B agree.

**Answer (A, 2026-10-09):** Agreed on all points. A will add an optional `event_sink` parameter to `RepairAgent.__init__` (an `EventSink` protocol with `emit(event: Event) -> None`, default no-op) and call it at the transitions in `attempt_repair`/`request_deploy` — `candidate.proposed`, `candidate.rejected` (from a `ValidationError`), `checks.completed`, `deploy.requested`. A won't implement `run.state` transitions inside `RepairAgent` itself (see A5 checklist note — that belongs to whatever owns `Run`, likely the host runner). Fine with C owning `src/server/runner.py`; A keeps `RepairAgent` runner-agnostic so it's usable either way.

Runner ownership: C.

### Q3 (A → B/C): Semgrep adapter vs. the pinned registry rule
**Answer (C, 2026-10-09):** PR #1 doesn't commit the rule text, because of its license. `config/semgrep/rules.lock.json` pins the rule's registry IDs and SHA-256, and `scripts/semgrep-scan.sh` fetches the rule, verifies the hash, and scans. `SemgrepAdapter` can call that script, or reuse its fetch-and-verify step and then pass `--config <fetched file>`. Both the local and CI scans produced exactly one finding at `routes/search.ts:23` with 0 errors ([run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899)). B is merging PR #1.

**Answer (A, 2026-10-09):** Works for me — once PR #1 lands, `SemgrepAdapter.__init__` will take a `config_path` already produced by `scripts/semgrep-scan.sh`'s fetch-and-verify step (shell out to it first, then point the adapter at its output), rather than the adapter re-implementing fetch/verify. Small change once the script exists on `main`. Blocked only on the PR merging.

### Q4 (C → A, B): Upstream ships a correct fix for this exact defect
The pinned source contains `data/static/codefixes/unionSqlInjectionChallenge_2_correct.ts` (plus `_1`, `_3` and `.info.yml`), the upstream reference answers for this challenge. If the agent can see them, a "repair" could be a copy of them.
- Proposal: the build path removes or hides `data/static/codefixes/` from the agent's source context, while the built image stays unchanged. The validator already limits edits to `routes/search.ts`.
- The report should disclose that upstream answer files exist, and whether the candidate matches one (C can diff for this).

A, B: agree? Who implements the exclusion?

**Answer (A, 2026-10-09):** Agree, good catch. A owns this: once `GuildPatchAdapter.propose()` is wired to a real session, A will exclude `data/static/codefixes/` from whatever source context gets assembled for the Guild agent (it's A's adapter that builds that context, not B's build path — the built image can keep the files, they're just not fed to the model). C's report-side diff-against-known-answers check is a good second line of defense regardless; please keep that.

**Update (C, 2026-10-09):** The report-side check is `src/server/answer_match.py`. `compare(candidate_search_ts, <source>/data/static/codefixes)` returns, for each `unionSqlInjectionChallenge_*.ts`, whether the candidate's `searchProducts` is an exact match after upstream's own normalization (hidden challenge lines, snippet markers, comments and whitespace removed). Checked against the real pinned files: the unmodified baseline matches none, and a candidate that only swaps in `_2_correct`'s query call matches `_2_correct` exactly. Only `exact` is a signal, since every reference is about 0.9 similar to the vulnerable original. The runner will record it as an `answer.match` event per candidate.

### Q7 (B → A, C): Contract changes to `CheckResult` and `Observation`
From B's checklist: add `image_digest` and `suite_hash` to `CheckResult`, and make `Observation.release_ref` optional.
**Answer (C, 2026-10-09):** Agree with both. The evidence view needs the digest and suite hash per check to show "these checks passed for this revision". A owns the change.

**Answer (A, 2026-10-09):** Done in `src/contracts/models.py`. `CheckResult` gets `image_digest: str | None = None` and `suite_hash: str | None = None` (optional — a static scan like Semgrep has no built image yet). `Observation.release_ref` is now `str | None`. All 9 existing unit tests still pass unaffected.
