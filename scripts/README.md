# scripts

Owner: A/B/C.

Repository setup, verification, and artifact operations with bounded arguments.

- `target.py` (B): pinned target operations. Requires git, Python 3.11+, and Docker for `build`/`run`/`stop`.
  - `python scripts/target.py source --out runtime/source`: export the allowed repair path(s) at the pinned commit (for scanning).
  - `python scripts/target.py build [--patch FILE]`: build baseline or a candidate; writes a record to `runtime/builds/`.
  - `python scripts/target.py run --image <image id>` then `python scripts/target.py smoke`: start locally and confirm search answers.

See [the PRD](../docs/PRD.md).
