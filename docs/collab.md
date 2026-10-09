# Collaboration questions and answers

A = G3Ram (agent, repair loop) · B = jguharaman (target, checks, deploy) · C = srismart (evidence, UI, extra sponsors)

How to use this file:
- Add a question under **Open** as `Q<n> (from → to)`. Use the next free number and never reuse one.
- Answer underneath with `**Answer (X, date):**`. When it's settled, move the question to **Resolved**.
- Link evidence (commit, PR, run URL) rather than restating it. Mark anything not yet observed as such.

## Open

### Q1 (A → C): Sign-off on `Event` and `Report` shapes
**Answer (C, 2026-10-09):** `Event` works as-is. C2 implements it column-for-column in `antibody.events` (#2), and a real insert and query were verified. Two requests, which won't be changed unilaterally:
1. Add an optional `detail: str | None` to `Event` for small redacted JSON, such as check counts or image digest. Without it, the dashboard can show only the outcome string.
2. `Report` needs its input identities for PRD §5: baseline/candidate image digests, rule IDs, and the test-suite hash. Today they're only reachable through `checks`. Either add the fields or agree that `Report` is built from `Run` + `Candidate` + `DeployResult`.

A, please confirm or push back. C won't build the report endpoint until this is settled.

### Q2 (A → C): Who emits events, and does `RepairAgent` run inside C's host process?
**Answer (C, 2026-10-09), proposal:**
- Keep the evidence API (`src/server/app.py`) read-only and separate. It must never run the agent or hold deploy credentials.
- Run the agent from a separate host runner process. `RepairAgent` takes an injected `EventSink` with `emit(event: Event) -> None`. C provides the ClickHouse implementation (`ClickHouseEventStore.insert`); tests use an in-memory sink.
- Use `adapters.clickhouse_events.stable_event_id(run_id, event_type, emitter, key)` for IDs, so retries deduplicate.
- Suggested event types: `scan.baseline`, `candidate.proposed`, `candidate.rejected`, `checks.completed`, `deploy.requested`, `deploy.result`, `probe.observed`, `run.state`.

Open point: who owns the host runner? C can write a thin `src/server/runner.py` that wires A's loop, B's worker and connector, and the sink, if A and B agree.

### Q3 (A → B/C): Semgrep adapter vs. the pinned registry rule
**Answer (C, 2026-10-09):** PR #1 doesn't commit the rule text, because of its license. `config/semgrep/rules.lock.json` pins the rule's registry IDs and SHA-256, and `scripts/semgrep-scan.sh` fetches the rule, verifies the hash, and scans. `SemgrepAdapter` can call that script, or reuse its fetch-and-verify step and then pass `--config <fetched file>`. Both the local and CI scans produced exactly one finding at `routes/search.ts:23` with 0 errors ([run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899)). B is merging PR #1.

### Q4 (C → A, B): Upstream ships a correct fix for this exact defect
The pinned source contains `data/static/codefixes/unionSqlInjectionChallenge_2_correct.ts` (plus `_1`, `_3` and `.info.yml`), the upstream reference answers for this challenge. If the agent can see them, a "repair" could be a copy of them.
- Proposal: the build path removes or hides `data/static/codefixes/` from the agent's source context, while the built image stays unchanged. The validator already limits edits to `routes/search.ts`.
- The report should disclose that upstream answer files exist, and whether the candidate matches one (C can diff for this).

A, B: agree? Who implements the exclusion?

### Q5 (C → B): Check-suite language
`tests/e2e/juice-shop-checks.mjs` in PR #1 is Node with no dependencies. It's verified against the baseline, the build-spike image, and a search-disabled mutant. B's checklist says the suite should be Python. Are you keeping the `.mjs`, or porting it? If you port it, please keep the fixture file and check IDs, so evidence from both runs stays comparable.

### Q6 (C → B): Public host and image access
- Which public host: Akash, or a fallback? C has no Akash account.
- The spike image is in a **private** GHCR package (`ghcr.io/hackathon-corner/antibody-target@sha256:2b20151b…`). The host either needs a read-only pull token, or we make the package public (it's a deliberately vulnerable app, so prefer the token).
- With Docker unavailable on B's machine, the `build-target` GitHub Actions workflow in PR #1 can produce baseline and candidate images by digest. Want to use it for B1's `baseline_image_digest`?

### Q7 (B → A, C): Contract changes to `CheckResult` and `Observation`
From B's checklist: add `image_digest` and `suite_hash` to `CheckResult`, and make `Observation.release_ref` optional.
**Answer (C, 2026-10-09):** Agree with both. The evidence view needs the digest and suite hash per check to show "these checks passed for this revision". A owns the change.

### Q8 (C → team): Remaining sponsor accounts
ClickHouse is done (srismart). Still needed, each with its own key in the ignored `.env` and never in chat or source:
- **Senso:** C4. This blocks A7.
- **ElevenLabs:** C5. It needs the deployed evidence API first.
- **Pi:** C6. Someone needs to ask the sponsor what integration exists.
- **Akash:** B2.

Who creates each, and is the Guild hang (A1) still blocked? Is there anything C can help with on it?

## Resolved

_None yet._
