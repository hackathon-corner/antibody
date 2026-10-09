# src/adapters

Owner: A/B/C.

Provider and tool adapters. Keep scanner, retrieval, deployment, and evidence interfaces separate.

Status: `base.py` defines the `ScannerAdapter`/`PatchAdapter`/`GuidanceAdapter` protocols. `semgrep.py` is a real working adapter (shells out to the local `semgrep` CLI, no vendor account needed). `guild.py` is an intentional stub that raises until a real Guild session exists (A1) — it will never fabricate a candidate. See [the PRD](../../docs/PRD.md).

## ClickHouse (C)

`clickhouse_events.py` stores and reads `contracts.Event` rows in `antibody.events` (a ReplacingMergeTree; reads use `LIMIT 1 BY event_id`). Settings come from env vars or the ignored repo-root `.env`: `CLICKHOUSE_HOST` (bare hostname), `CLICKHOUSE_PORT`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`. Requires `clickhouse-connect`. ClickHouse is evidence, not the release authority.

## Check worker (B4, B)

`check_worker.py` is B's isolated candidate verification worker. `load_worker().run_checks(candidate)` is the `run_checks` callable for A's `RepairAgent`; `build_candidate(candidate)` is the callable for C's `HostRunner` and returns only an image the worker already verified. Steps: recompute the patch hash, reject anything outside `allowed_paths` (including deletes, renames and binary patches) before building, build through `scripts/target.py build`, run the target on a per-check `--internal` Docker network with resource limits and dropped capabilities, then run `tests/e2e/juice-shop-checks.mjs` in candidate mode in the pinned Node image with the suite mounted read-only from the host checkout. Each `CheckResult` carries the candidate hash, the local image ID, and the suite hash. Timeouts, unparseable output, a suite-hash mismatch or a target that never starts are `ERROR` and block release. Subprocesses get an allowlisted environment (no vendor or deploy secrets). Evidence lands in ignored `runtime/checks/<hash12>/`. Needs Docker and Python on `PATH`; no network egress for the target during checks.
