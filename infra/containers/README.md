# infra/containers

Owner: B.

Isolated candidate build/test infrastructure and pinned target image definitions.

- `juice-shop/Dockerfile`: fetches the pinned commit inside the build (verifying the SHA), applies an optional `candidate.patch`, builds, and produces a distroless runtime image. Adapted from upstream's Dockerfile with two deviations: the server compile (`npm run build:server`) fails the build instead of being swallowed by upstream's `postinstall`, and the SBOM step is omitted. Run it through `scripts/target.py build`, which supplies all pins from `config/targets/juice-shop.json`.

Status: Dockerfile written, not yet built. See [the PRD](../../docs/PRD.md).
