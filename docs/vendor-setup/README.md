# Vendor setup checklist

All entries are pending. Each owner records a redacted actual setup result and artifact reference. A planned integration does not count as sponsor use.

| Vendor | Owner | First completion check |
|---|---|---|
| Guild AI | A | Actual agent invokes a harmless tool and receives its result |
| Semgrep | A | Real finding on the pinned source with confirmed rule ID |
| ClickHouse | C | Real event inserted and queried — **done 2026-10-09.** ClickHouse Cloud service (26.6.1, GCP us-central1), database `antibody`, least-privilege user `antibody_app` (grants on `antibody.*` only). Table `antibody.events` created by `src/adapters/clickhouse_events.py`; 3 events from [build-target run 37983610899](https://github.com/hackathon-corner/antibody/actions/runs/37983610899) inserted and queried back, with re-insert deduplicated by `event_id`. Outcomes in that record are Actions step conclusions, not check verdicts. Credentials only in the ignored `.env`. |
| Akash / fallback public host | B | Rebuilt target image is reachable by HTTP |
| Senso | C, connected by A | Actual guidance retrieval with source references |
| ElevenLabs | C | Spoken question invokes real read-only evidence API |
| Pi Security | C | Sponsor-provided actual assessment/export tied to source or candidate |
| GitHub | B | Correct account can write the team repository and publish artifacts |

Store credentials in ignored local configuration or vendor secret stores. Never record token values here. Keep account/workspace IDs, required permissions, setup blockers, and exercised capability notes. See the PRD for task IDs, deadlines, and fallbacks.
