# src/adapters

Owner: A/B/C.

Provider and tool adapters. Keep scanner, retrieval, deployment, and evidence interfaces separate.

Status: `base.py` defines the `ScannerAdapter`/`PatchAdapter`/`GuidanceAdapter` protocols. `semgrep.py` is a real working adapter (shells out to the local `semgrep` CLI, no vendor account needed). `guild.py` is an intentional stub that raises until a real Guild session exists (A1) — it will never fabricate a candidate. See [the PRD](../../docs/PRD.md).
