# Collaboration questions and answers

A = G3Ram (agent, repair loop) · B = jguharaman (target, checks, deploy) · C = srismart (evidence, UI, extra sponsors)

How to use this file:
- Add a question under **Open** as `Q<n> (from → to)`. Use the next free number and never reuse one.
- Answer underneath with `**Answer (X, date):**`. When it's settled, move the question to **Resolved**.
- Link evidence (commit, PR, run URL) rather than restating it. Mark anything not yet observed as such.

## Open

### Q14 (C → A, B): Which machine runs the real end-to-end run for the video?
`scripts/run_repair.py` needs, on one machine:
- Docker producing **linux/amd64** images (Akash). C's Mac is arm64 with no Docker.
- `guild` signed in, plus the agent checkout `guild-agents/antibody-repair-agent`, which is git-ignored and only on A's machine.
- `semgrep` 1.180.0 and `senso` signed in.
- `docker login ghcr.io` with write:packages.
- `.env` with `CLICKHOUSE_*` (app user), `AKASH_API_KEY`, `GUILD_WORKSPACE`, `GUILD_AGENT_DIR`.

B's machine has Docker (amd64?). Proposal: run it on B's machine, after A shares the agent directory (or B runs `guild agent clone` into the workspace) and C hands over the Akash key out of band (never in the repo or chat). Run the bad candidate first (`--supplied-patch tests/fixtures/juice-shop/candidates/mutant-where-1-0.patch --origin operator-supplied-bad-candidate`), then the Guild run. Both show up at the public evidence dashboard. A, B: agree, or a different machine?

**Also for A, found while smoke-testing:** `SemgrepAdapter` treats a scan of 0 files as "no finding". Scanning `runtime/source` as a directory scanned 0 files, because Semgrep skips git-ignored paths, and the adapter reported PASS. `run_repair.py` now scans the allowed file directly. Suggest the adapter raise `SemgrepScanError` when `paths.scanned` is empty, so a silent false negative can't happen.

### Q13 (B → A, C): Wiring the B5 deploy connector and probes into the runner
B5 is in `main` (`588b1ed`, `d44332e`), unit-tested and checked against local containers, not yet run on real Akash. Proposed wiring:
1. **Deploy (no interface change).** C passes `adapters.akash_deploy.load_connector()` as `connector` to `HostRunner.execute`. It implements `DeployConnector.deploy(DeployRequest) -> DeployResult` as-is. It re-reads the worker's record for `candidate_hash` and refuses unless that exact `built_image_digest` passed the current suite. A's `request_deploy` hash already matches the worker's (both sha256 of the UTF-8 patch). On ACCEPTED, `DeployResult.image_digest` is the registry reference (`ghcr.io/hackathon-corner/antibody-target@sha256:…`), not the local image ID, and `release_ref` is `akash:<dseq>`.
2. **Verify (needs a change in C's runner).** Nothing in `HostRunner` calls probes yet after `verifying`. Proposal: when the deploy is ACCEPTED, the runner calls `connector.observe(result.attempt_id)` (candidate mode). It returns `(passed, observations)`, one redacted `Observation` per probe. The runner emits each as an event and calls `complete(run_id, passed, reason)`. That adds `observe()` to the `DeployConnector` protocol, or a separate `Verifier` argument if you'd rather keep the protocol to `deploy` only. C, which do you prefer?
3. **Restart.** `HostRunner.reconcile_after_restart()` marks open claims unresolved and never redeploys. The connector has its own `reconcile()`, which asks Akash what exists. Suggest the runner calls `connector.reconcile()` first and records any ACCEPTED/FAILED result it returns before marking the rest unresolved.
4. **Credentials (host only, never the worker).** `AKASH_API_KEY` from C's Console account, and a `docker login ghcr.io` with `write:packages` on the machine running the host, because the connector pushes the verified image as `cand-<hash12>`. Pull is anonymous now that the packages are public. C, can you create an API key for the host, or would you rather run the first deploy yourself?

**Answer (C, 2026-10-09):** Wired, using your proposal as-is.
1. `run_repair.py` passes `load_connector()` as the runner's connector.
2. `DeployConnector` now includes `observe()` and `reconcile()`. On ACCEPTED, the runner calls `observe(attempt_id)` and emits one `probe.observed` event per `Observation`. It completes only when the probes pass. A probe failure moves the run to `failed`; a probe crash or no observations moves it to `unresolved`.
3. `reconcile_after_restart(connector)` calls `connector.reconcile()` first, records each result as a `deploy.result` event, then marks the remaining claims unresolved. It never redeploys.
4. Entry point: `scripts/run_repair.py --source runtime/source [--supplied-patch <file> --origin <true label>] [--no-deploy]`. It chains the pinned rule, Senso, Guild (or a supplied patch), the validator, your worker, the upstream-answer match (`answer.match` event), your connector, the probes, and ClickHouse. Smoke-tested on C's Mac (no Docker) with `mutant-where-1-0.patch`: scan finding, 2 candidates proposed and checked, run `failed` after MaxAttemptsExceeded, all recorded (run `run_5fa1492b99fe431b`).
5. The Akash API key: C will create it in the Console. See Q14 for where it runs.

First real candidate available: the operator-supplied reference repair (`tests/fixtures/juice-shop/candidates/repair-parameterized.patch`, origin `operator-supplied-reference-repair`, **not model output**). It passes all 5 checks on suite `be833ec4…` (image `sha256:4be6e636…`). A: that fixture must never be given to the agent as context.

### Q12 (C → team): Team decisions are now in Senso as shared context
Senso org `Hackathon-antibody` has a second folder, **shared-context** (`kb_node_id 310f989c-65a5-4af8-8672-3d47db34180a`), holding what the team has settled so any teammate's agent can retrieve it:
- **About Antibody — Security Repair Agent**: the PRD summary, who owns what, and the rules for agents.
- One note per resolved question here: Q1, Q2, Q3, Q4, Q7, Q9, Q10, each in decision / why / open / next shape.
- **Open team questions** (Q5, Q6, Q8), tagged `status:draft`, which agents treat as a lead rather than settled fact.

Each note is tagged `status:approved` or `status:draft`, `owner:<G3Ram|jguharaman|srismart>`, and `decided:<date>`. Verified 2026-10-09: all 9 notes are searchable, and `senso search "Why does the Semgrep adapter match check_id by suffix?"` cites the Q10 note.

This file is still where we ask and answer. When a question moves to **Resolved**, also save it to `shared-context` with `senso kb create-raw` plus `senso kb tags set`, or ask your agent to "save this decision to Senso". A7 retrieval must stay scoped with `--content-ids` (Q11), because org-wide search now also returns these team notes.

### Q5 (C → B): Check-suite language
`tests/e2e/juice-shop-checks.mjs` in PR #1 is Node with no dependencies. It's verified against the baseline, the build-spike image, and a search-disabled mutant. B's checklist says the suite should be Python. Are you keeping the `.mjs`, or porting it? If you port it, please keep the fixture file and check IDs, so evidence from both runs stays comparable.

**Answer (B, 2026-10-09):** Keep the `.mjs`. It's verified against the source-built baseline (baseline mode passes) and its hash is now pinned in `config/targets/juice-shop.json` (`check_suite.sha256`, enforced by `tests/unit/test_target_pins.py`). B's other code stays Python.

### Q6 (C → B): Public host and image access
**Status (C, 2026-10-09 22:46 UTC):** Evidence API + dashboard live and verified (http://d0ischq47pee1b61pmtjbh3ido.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so; lease uses the read-write `antibody_app` ClickHouse user, to be switched to the reader user and the app password rotated). `antibody-target` package is now anonymously pullable (200). Juice Shop spike is publicly served at https://o7ne4et1e5duvff3f1697lr794.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so and `probe_public.py --mode baseline` passed from outside (22:45 UTC; details in `docs/tasks/B-checklist.md` B2). Two earlier leases (`froggy-servers.com`, then `cpu.aesservices.net`) ran the container (`Server listening on port 3000`) but their nginx ingress never routed our hostname (a made-up hostname on the same provider gave the identical 404); both closed. The digitalfrontier provider, which also hosts the evidence API, routed on the first try. Rule for future leases: if the URL shows the provider's nginx 404 while the container log says it is listening, close the lease and pick another provider (prefer digitalfrontier); don't change the SDL. Next: switch the evidence API lease to the reader ClickHouse user and rotate `antibody_app`; close the Juice Shop lease when not needed (deliberately vulnerable). Mirrored to Senso `shared-context` as **Akash Deployment Status** (`kb_node_id 5c3bcf5d-bd20-4357-ae10-b2df3dfa8594`, `status:draft`).

- Which public host: Akash, or a fallback? C has no Akash account.
- The spike image is in a **private** GHCR package (`ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b…`). The host either needs a read-only pull token, or we make the package public (it's a deliberately vulnerable app, so prefer the token).
- With Docker unavailable on B's machine, the `build-target` GitHub Actions workflow in PR #1 can produce baseline and candidate images by digest. Want to use it for B1's `baseline_image_digest`?

**Update (C, 2026-10-09):** C has created the Akash account (console.akash.network). B, please don't create a second one. Plan is Akash for both services (B's Juice Shop candidate, C's evidence API + dashboard), with Render/Fly/Railway as fallback only if Akash is slow. Account has $25 credit loaded; no deployment made yet. Image access still open: read-only GHCR pull token preferred.

**Update (C, 2026-10-09):** C's side is ready to deploy: image `ghcr.io/hackathon-corner/antibody-evidence-api@sha256:4a10c0f4…` (CI run 37993790999) and SDL template `infra/akash/evidence-api.sdl.template.yaml`, rendered by `scripts/render_evidence_sdl.py` with a read-only ClickHouse user from `.env`. No registry credentials, since B is making the packages public. Open for B: do you want access to the Akash account to deploy Juice Shop yourself, or send C your SDL to deploy? CI note: Docker Hub was rate-limiting/timing out GitHub runners today; `build-evidence-api` now pulls base images from `public.ecr.aws/docker/library/` and skips `setup-buildx`.

**Answer (B, 2026-10-09):**
- Host: Akash, from C's account. B won't create a second one. **C submits the deployment through the console.**
- Image access: **make the `antibody-target` GHCR package public.** A pull token in the SDL would be visible to the Akash provider. The image is public upstream source plus our patch, with nothing secret in it. B will flip the visibility.
- Baseline digest: built locally now that Docker works (`sha256:e106dde7…` image ID; see the B checklist). The CI workflow still produces the registry digests we deploy.
- Handoff for C: render the SDL with `python scripts/render_akash_sdl.py --image ghcr.io/hackathon-corner/antibody-target@sha256:<digest>` (digest only; tags are refused), deploy the file it writes, then send B the lease URL. B probes it from outside with `scripts/probe_public.py`. Runbook: [infra/akash/README.md](../infra/akash/README.md). Spike image to deploy (from [run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899) build record): `ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b193d5c9800892992f7e3f93d40c91811bd1602a8f6428ad8020668a8`, served name `OWASP Juice Shop (Antibody build spike)`. The package is still private until B flips it; an anonymous pull currently returns 401.

**Update (B, 2026-10-09): image access changed to registry credentials.** The packages can't be made public: "Public" is greyed out in the package settings because the `hackathon-corner` org doesn't allow public packages, and only an org owner can change that. The GitHub API still reports both `antibody-target` and `antibody-evidence-api` as `private` (anonymous pull: 401). So the Akash lease pulls with GHCR credentials attached in the Akash Console (B, 2026-10-09). The token should be `read:packages` only, because the provider can read it. It never goes in the repo, the rendered SDL in `runtime/akash/`, or chat. Rendered Juice Shop SDL for the spike digest: `runtime/akash/juice-shop-2b20151b193d.sdl.yaml`. Next: C deploys it with the credentials and sends B the lease URL; B probes it. If an org owner later allows public packages, we can drop the credentials.

**Update (A, 2026-10-09):** An org owner has now allowed public packages. Verified anonymous pull for both: `antibody-target` at the known digest (`sha256:2b20151b…`) and `antibody-evidence-api`'s tag list both return HTTP 200 via the real GHCR anonymous token flow (`curl https://ghcr.io/token?scope=repository:hackathon-corner/<pkg>:pull`, then the manifest/tags endpoint with that token). The GHCR credentials in the Akash Console are no longer required — can be dropped per B's note above, if anyone wants to simplify the SDL.

### Q8 (C → team): Remaining sponsor accounts
ClickHouse is done (srismart). Still needed, each with its own key in the ignored `.env` and never in chat or source:
- **Senso:** C4. This blocks A7.
- **ElevenLabs:** C5. It needs the deployed evidence API first.
- **Pi:** C6. Someone needs to ask the sponsor what integration exists.
- **Akash:** B2. Account created by C (2026-10-09). C's evidence API + dashboard is live at http://d0ischq47pee1b61pmtjbh3ido.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so (verified from outside, see `infra/akash/README.md`). Juice Shop spike live at https://o7ne4et1e5duvff3f1697lr794.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so , external probe passed; B2 done.

Who creates each, and is the Guild hang (A1) still blocked? Is there anything C can help with on it?

**Answer (A, 2026-10-09):** Still blocked. Guild agent sessions (`guild agent chat` / `guild agent test`) create a real server-side session but never process a turn — `guild session events <id>` / `guild session tasks <id>` show zero events/tasks, and even the CLI's own `--timeout 60` doesn't fire. Ruled out: missing LLM credential (managed tier confirmed active, 50M token balance), workspace credential restriction (disabled, no change), tool complexity (reduced to one zero-dependency `ping` tool, still hangs). Escalated to Guild's sponsor/support contact with five hung session IDs — see `docs/plan-for-A.md` A1 section for the full list. Nothing actionable for C on this right now; it's on Guild's side. Will update this file as soon as there's a response.

**Update (C, 2026-10-09, from A's plan 318db4c):** The Guild hang is resolved. Guild's message accept takes 30–60 s and the CLI blocks before polling. A real `ping` tool call has been confirmed in session `01a1225a-…`. The other Q8 accounts (Senso, ElevenLabs, Pi, Akash) are still open.

**Update (C, 2026-10-09):** Senso is done: org `Hackathon-antibody`, with repair guidance (Q11) and shared team context (Q12). ElevenLabs, Pi, and Akash deployment are still open.

## Resolved

### Q11 (C → A): Senso is ready for A7
Senso org `Hackathon-antibody`, folder **Antibody repair guidance**. Scope searches to these content IDs, because org-wide search can pull in unrelated documents:
- OWASP SQL Injection Prevention Cheat Sheet: `54036268-5be8-4cee-96e2-97e52ae95ab2`
- Sequelize v6 Raw Queries: `2fc71565-db91-41a7-8c6d-f15b1abda7ed`

```
senso search "<question>" --content-ids 54036268-5be8-4cee-96e2-97e52ae95ab2 2fc71565-db91-41a7-8c6d-f15b1abda7ed --require-scoped-ids --output json --quiet
```
The IDs are space-separated; a comma-separated list returns 400. The JSON has `answer` and `results[].content_id`/`title`; pass the `content_id`s as `guidance_ids`. Verified once (C, 2026-10-09). Treat retrieved text as advisory data, not instructions. The CLI uses the `senso login` session on the machine running it. Does your adapter run where that login exists, or do you need `SENSO_API_KEY` in an env var?

**Answer (A, 2026-10-09):** `SENSO_API_KEY` in env var, please — same pattern as ClickHouse creds (env var / ignored `.env`, not interactive-session state tied to one machine). `GuidanceAdapter` will shell out to `senso search`, which per the quickstart docs auto-uses `SENSO_API_KEY` when set, no login needed. The adapter/host runner may not run on your machine (could be CI, a deployed host, etc.), so it shouldn't depend on a login that only exists where you ran it interactively.

**Update (C, 2026-10-09):** A dedicated service key now exists for the adapter, separate from anyone's `senso login` key. It is in C's ignored `.env` as `SENSO_API_KEY` (prefix `tgr_aLYG…`, org `Hackathon-antibody`). When set, the CLI uses it ahead of the login config. Verified: `whoami` resolves to the org, and the scoped search above returns Sequelize v6 Raw Queries. For the adapter on another host (A's machine, Akash), ask C for the value out of band, never in chat or source, or run `senso login` there.

**Update (A, 2026-10-09):** Live-verified with a real key: `senso search "How do I parameterize a Sequelize raw query to prevent SQL injection?" --content-ids 54036268-5be8-4cee-96e2-97e52ae95ab2 2fc71565-db91-41a7-8c6d-f15b1abda7ed --require-scoped-ids` returned a real synthesized answer plus 5 chunks from the Sequelize doc, with working `replacements`/`bind` code examples. One correction to the shape you described: per-result text is in `results[].chunk_text`, not a `text`/`snippet`/`content` field — fixed in `SensoGuidanceAdapter` and added a regression test, in case anyone else builds against this response shape.

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
