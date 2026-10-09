# 0002: Pinned target, scanner rule, and independent checks

- Date: 2026-10-09
- Drafted by: srismart (C) with Claude Code, for review by B (jguharaman) and A (G3Ram)
- Status: Proposed

## Target

OWASP Juice Shop `v20.2.0`, commit `5658473cf8814459bf89000ce373b20ed0b4eb37` (MIT). Latest upstream release at selection time.
Repair path: `routes/search.ts`. The defect is the template-literal `sequelize.query` on line 23.
Candidates are patches against this commit. No fork is needed for the build path; one can be added if the team wants a browsable source branch.

## Scanner

Semgrep OSS CLI 1.180.0 with registry rule
`javascript.sequelize.security.audit.sequelize-injection-express.express-sequelize-injection` (rv_id 1263241).
The rule text is pinned by SHA-256 and fetched at scan time, because it is under the Semgrep Rules License and is not committed here.
Observed on 2026-10-09: one finding at `routes/search.ts:23`, zero errors. A custom rule was not needed.

## Independent checks (`tests/e2e/juice-shop-checks.mjs`)

| Check | Observed on local baseline (upstream release package, darwin/arm64) |
|---|---|
| `setup.canary-user`: registers a per-run synthetic canary user | pass |
| `search.ordinary`: 6 queries, exact product ID order and object keys | pass |
| `search.edge-cases`: quote, double quote, over-limit input | observed: quote → HTTP 500 (the defect); others 200 `[]` |
| `security.injection`: UNION payload; leak = canary email or credential-shaped rows | baseline mode pass (reproduced: canary leaked, 25 credential-shaped rows) |
| `access.boundary`: `/api/Users` 401 unauthenticated, 200 authenticated | pass |

Negative controls, both run locally:

- Candidate mode against the unrepaired baseline fails (injection, edge cases).
- A supplied mutant whose search query is `WHERE 1=0` fails `search.ordinary` while passing injection. This is the "closed the hole by closing the business" case, and it is rejected.

These are selected cases, not proof that the application is free of injection. Juice Shop intentionally contains other vulnerabilities.

## Not yet established

- The baseline above used the upstream release package, not a source-built image. The GitHub Actions spike produces the source-built image digest that becomes the baseline identity.
- Public endpoint and host.
- Candidate-mode expectations for edge cases are declared here, not yet observed on any candidate.
