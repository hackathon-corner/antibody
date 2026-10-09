# Repository structure

This is a framework-neutral starting layout. No dependency stack or runtime setup is claimed as complete.

| Path | Owner | Responsibility |
|---|---|---|
| `src/agent/` | A | Agent and repair loop |
| `src/adapters/` | A/B/C | Provider/tool integration boundaries |
| `src/contracts/` | A with B/C | Shared typed interfaces |
| `src/server/`, `src/web/` | C | Host API, actual evidence and UI |
| `tests/unit/`, `tests/integration/` | A/B/C | Focused verification |
| `tests/e2e/`, `tests/fixtures/juice-shop/` | B | Independent behavior suite and synthetic target infrastructure |
| `infra/akash/`, `infra/containers/` | B | Hosting and isolated build/test operations |
| `config/targets/` | B | Authorized target identities |
| `config/policies/` | A/B | Host-owned execution restrictions |
| `config/semgrep/` | A | Pinned scan rules |
| `scripts/` | A/B/C | Setup and verification operations |
| `docs/` | Team | PRD, setup, and decisions |

Runtime state and generated artifacts belong in ignored directories. Version only deliberately redacted evidence when needed. Candidate source never receives provider secrets or permission to edit the verification suite.
