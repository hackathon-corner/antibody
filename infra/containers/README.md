# infra/containers

Owner: B.

Isolated candidate build/test infrastructure and pinned target image definitions.

- `juice-shop/Dockerfile`: fetches the pinned commit inside the build (verifying the SHA), applies the host-owned `build-fixes/*.patch`, then an optional `candidate.patch`, builds, and produces a distroless runtime image. Adapted from upstream's Dockerfile with two deviations: the server compile (`npm run build:server`) fails the build instead of being swallowed by upstream's `postinstall`, and the image SBOM step is omitted. Run it through `scripts/target.py build`, which supplies all pins from `config/targets/juice-shop.json`.
- `evidence-api/Dockerfile` (owner: C): the evidence API and dashboard in one image. CI: `.github/workflows/build-evidence-api.yml`.
- `patches/`: build inputs for `.github/workflows/build-target.yml`. `spike-marker.patch` changes only the displayed app name to prove a modified-source build is what is served.

Status: Dockerfile written, not yet built. The CI spike workflow builds from `patches/` and `build-fixes/`. See [the PRD](../../docs/PRD.md).

## Build fixes (host-owned, applied before any candidate patch)

Upstream v20.2.0 ships no npm lockfile, so dependencies resolve at build time. On 2026-10-09 the resolved Angular builder no longer wrote `dist/frontend/stats.json`. The frontend `sbom` step then failed with `Missing metafile` ([run 37982608827](https://github.com/hackathon-corner/antibody/actions/runs/37982608827)).
`build-fixes/frontend-sbom.patch` drops that SBOM step from the frontend build. The served app is unchanged.
The workflow records `buildBaseTree` (pinned commit + build fixes) separately from `sourceTree` (+ candidate patch), so a candidate's change scope is measured against the build base.

Known risk: because dependencies float, two builds can resolve different packages. Compare a candidate with a baseline image built in the same window, or build candidates from a cached installer stage.
