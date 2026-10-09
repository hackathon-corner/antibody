# 0001: Target pin

- Date: 2026-10-09
- Owner: B

Pin OWASP Juice Shop release `v20.2.0`, commit `5658473cf8814459bf89000ce373b20ed0b4eb37` (committed 2026-08-10), the latest release tag on 2026-10-09. A release tag over moving `master` gives a stable, citable identity.

At this commit `routes/search.ts` still interpolates `req.query.q` into a raw SQL string (`unionSqlInjectionChallenge`, `dbSchemaChallenge`), served at `GET /rest/products/search?q=`. Search responds `{ "status": "success", "data": [...] }`.

Upstream's Node engine range is 22–26 and its Dockerfile uses `node:24` and distroless `nodejs24-debian13`; we use the same, pinned by digest. Source is fetched inside the Docker build because a full checkout fails under default Windows git (long paths).

Open: team fork (switch `source.repo`, keep the commit), baseline image digest, Semgrep rule match (A1).
