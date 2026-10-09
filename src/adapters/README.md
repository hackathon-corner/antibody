# src/adapters

Owner: A/B/C.

Provider and tool adapters. Keep scanner, retrieval, deployment, and evidence interfaces separate.

Status: `base.py` defines the `ScannerAdapter`/`PatchAdapter`/`GuidanceAdapter` protocols. `semgrep.py` is a real working adapter (shells out to the local `semgrep` CLI, no vendor account needed). `guild.py` is an intentional stub that raises until a real Guild session exists (A1) — it will never fabricate a candidate. See [the PRD](../../docs/PRD.md).

## ClickHouse (C)

`clickhouse_events.py` stores and reads `contracts.Event` rows in `antibody.events` (a ReplacingMergeTree; reads use `LIMIT 1 BY event_id`). Settings come from env vars or the ignored repo-root `.env`: `CLICKHOUSE_HOST` (bare hostname), `CLICKHOUSE_PORT`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`. Requires `clickhouse-connect`. ClickHouse is evidence, not the release authority.
