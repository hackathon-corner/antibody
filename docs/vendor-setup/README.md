# Vendor setup checklist

All entries are pending. Each owner records a redacted actual setup result and artifact reference. A planned integration does not count as sponsor use.

| Vendor | Owner | First completion check |
|---|---|---|
| Guild AI | A | Actual agent invokes a harmless tool and receives its result |
| Semgrep | A | Real finding on the pinned source with confirmed rule ID |
| ClickHouse | C | Real event inserted and queried |
| Akash / fallback public host | B | Rebuilt target image is reachable by HTTP |
| Senso | C, connected by A | Actual guidance retrieval with source references |
| ElevenLabs | C | Spoken question invokes real read-only evidence API |
| Pi Security | C | Sponsor-provided actual assessment/export tied to source or candidate |
| GitHub | B | Correct account can write the team repository and publish artifacts |

Store credentials in ignored local configuration or vendor secret stores. Never record token values here. Keep account/workspace IDs, required permissions, setup blockers, and exercised capability notes. See the PRD for task IDs, deadlines, and fallbacks.
