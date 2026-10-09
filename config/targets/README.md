# config/targets

Owner: B.

Explicit authorized target definitions and revision identities.

- `juice-shop.json`: the pinned target. Upstream tag `v20.2.0`, commit `5658473cf8814459bf89000ce373b20ed0b4eb37`, allowed repair path `routes/search.ts`, base images pinned by digest. `routes/search.ts` at this commit has sha256 `de09bfc4040fc88073dbb85a7d1ef0171388abb4775eedc78578a48167853057`.
- `baseline_image_digest` stays `null` until a baseline build is actually run and recorded (see `scripts/target.py build`).

Status: B1 pins recorded. Baseline image not yet built (Docker not yet available on the B workstation); team fork not yet created. See [the PRD](../../docs/PRD.md).
