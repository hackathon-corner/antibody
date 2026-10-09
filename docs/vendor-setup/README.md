# Vendor setup checklist

Each owner records a redacted actual setup result and artifact reference. A planned integration does not count as sponsor use.

Builders: A = G3Ram, B = jguharaman, C = srismart.

| Vendor | Owner | First completion check | Status (2026-10-09) |
|---|---|---|---|
| Guild AI | A | Actual agent invokes a harmless tool and receives its result | **Pending.** No Guild account/credentials provisioned for this project. |
| Semgrep | A | Real finding on the pinned source with confirmed rule ID | **Baseline confirmed (OSS CLI, no account).** Semgrep 1.180.0, rule `express-sequelize-injection` (rv_id 1263241) matches `routes/search.ts:23` at the pinned commit; 0 scan errors. See [config/semgrep](../../config/semgrep/README.md). Candidate rescan pending a candidate. Semgrep AppSec Platform account not set up. |
| ClickHouse | C | Real event inserted and queried | **Done 2026-10-09.** ClickHouse Cloud service (26.6.1, GCP us-central1), database `antibody`, least-privilege user `antibody_app` (grants on `antibody.*` only). Table `antibody.events` created by `src/adapters/clickhouse_events.py`; 3 events from [build-target run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899) inserted and queried back, with re-insert deduplicated by `event_id`. Outcomes in that record are Actions step conclusions, not check verdicts. Credentials only in the ignored `.env`. |
| Akash / fallback public host | B | Rebuilt target image is reachable by HTTP | **Pending.** Source→image→HTTP spike runs in GitHub Actions ([build-target](../../.github/workflows/build-target.yml)); no public host or Akash account yet. |
| Senso | C, connected by A | Actual guidance retrieval with source references | **Retrieval verified 2026-10-09.** Org `Hackathon-antibody` (free tier), signed in with `senso login`; no key in the repo. Folder **Antibody repair guidance** (`kb_node_id 1b56f841-d854-411c-887b-99ef684e39d5`) holds 2 unmodified, attributed sources: OWASP SQL Injection Prevention Cheat Sheet (CC BY-SA 4.0; content `54036268-5be8-4cee-96e2-97e52ae95ab2`) and Sequelize v6 Raw Queries (content `2fc71565-db91-41a7-8c6d-f15b1abda7ed`). A scoped test search returned the Sequelize page as top source with `replacements`/`bind` examples. Not yet wired into a candidate (A7). A second folder, **shared-context** (`310f989c-65a5-4af8-8672-3d47db34180a`), holds the team's settled decisions as tagged notes (see collab Q12). |
| ElevenLabs | C | Spoken question invokes real read-only evidence API | **Pending.** No key; also depends on evidence API. |
| Pi Security | C | Sponsor-provided actual assessment/export tied to source or candidate | **Pending.** Integration method unknown; ask sponsor. |
| GitHub | B | Correct account can write the team repository and publish artifacts | **Partial.** `srismart` and `jguharaman` are admins on `hackathon-corner/antibody` (private). `G3Ram` is not yet a collaborator. Actions enabled; GHCR push via workflow token. |

Store credentials in ignored local configuration or vendor secret stores. Never record token values here. Keep account/workspace IDs, required permissions, setup blockers, and exercised capability notes. See the PRD for task IDs, deadlines, and fallbacks.
