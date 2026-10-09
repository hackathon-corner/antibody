# infra/akash

Owner: B.

Authorized Akash deployment definitions and setup notes. No credentials.

- `juice-shop.sdl.template.yaml`: one Juice Shop service, port 3000 exposed globally as 80, 1 CPU, 2 GiB memory, 4 GiB storage. The image is a placeholder; render it with `scripts/render_akash_sdl.py --image ghcr.io/hackathon-corner/antibody-target@sha256:<digest>`, which refuses tags and writes to the ignored `runtime/akash/`.
- `scripts/probe_public.py --url <lease URL> --mode baseline|candidate [--expect-name <name>]`: external probe (`src/adapters/public_probe.py`). It checks the application name of our rebuilt image, all ordinary searches from the B3 fixture, the single-quote case and the selected injection (`baseline`: must reproduce; `candidate`: must not leak). It prints one `Observation` per probe.
- B5 connector: `src/adapters/akash_deploy.py` deploys a verified candidate by registry digest through the Akash Console API (`AKASH_API_KEY`) and probes it with `observe(attempt_id)`.

## B2 runbook (prove a rebuilt image is publicly served)

1. Image: the `build-target` workflow's `spike-marker.patch` image, by digest from its build record (`image` field). The marker sets the app name to `OWASP Juice Shop (Antibody build spike)`, so upstream's own image can't pass the probe.
2. Pull access: both GHCR packages are public (2026-10-09), so the lease pulls anonymously. If a package goes private again, attach `credentials: {host: ghcr.io, username, password}` with a `read:packages` token; the provider can read it, so it never goes in this repo or in `runtime/akash/`. See Q6 in [collab.md](../../docs/collab.md).
3. Render the SDL for that digest and create the deployment from C's Akash Console account (C created it; don't create a second one). Accept a bid and note the lease URL.
4. From outside the lease: `python scripts/probe_public.py --url <lease URL> --mode baseline --expect-name "OWASP Juice Shop (Antibody build spike)" --release-ref <digest>`. Record the output, lease ID and URL in [the B checklist](../../docs/tasks/B-checklist.md).
5. Close the lease when it's no longer needed. Juice Shop is deliberately vulnerable.

Status: SDL template, renderer and probe written and tested locally (probe against the local baseline, renderer against tag/digest input). SDL rendered for the spike digest (`runtime/akash/juice-shop-2b20151b193d.sdl.yaml`, 2026-10-09). Juice Shop not deployed yet. See [the PRD](../../docs/PRD.md).

## Files

- Juice Shop target SDL (owner: B, B2): `juice-shop.sdl.template.yaml`, rendered per digest into `runtime/akash/`.

## Evidence API + dashboard (owner: C)

- `evidence-api.sdl.template.yaml`: one service, port 8000 exposed as 80, 0.5 CPU, 512 MiB memory. Render with `python scripts/render_evidence_sdl.py --image ghcr.io/hackathon-corner/antibody-evidence-api@sha256:<digest>` (digest from the `build-evidence-api` workflow summary).
- The SDL's env is readable by the Akash provider, so it carries a **read-only** ClickHouse user (`CLICKHOUSE_READER_USER`/`CLICKHOUSE_READER_PASSWORD` in `.env`, `SELECT` on `antibody.events` only). The renderer refuses the read-write app user and writes only to the ignored `runtime/akash/`.
- Latest built image: `ghcr.io/hackathon-corner/antibody-evidence-api@sha256:4a10c0f4dd41ce18de3a3fcfff16b63e8105f78203262980621627730d88c29a` (smoke-tested in CI: serves the dashboard, `/api/health` is 503 without ClickHouse settings).
- **Deployed (2026-10-09):** http://d0ischq47pee1b61pmtjbh3ido.ingress.h6i-dedicated.eu-se-1.digitalfrontier.so , from C's console account. Verified from outside: `/` serves the dashboard, `/api/health` 200 (ClickHouse 26.6.1), `/api/runs` and `/api/runs/<id>/events` 200 with the recorded spike run. Known gap: this lease was created with the read-write `antibody_app` user, not the reader user; to be switched to the reader and the app password rotated.
