# Workstream claim: B4 isolated candidate verification worker

- Status: COMPLETE (worker); wiring by A and C pending
- Assistant: Claude Code, operated by jguharaman (Builder B)
- Branch: main (small, additive)
- Started: 2026-10-09
- Owned paths: src/adapters/check_worker.py, tests/unit/test_check_worker.py, this claim.
- Not touched: infra/containers/juice-shop/Dockerfile, scripts/target.py (baseline build in progress in another session), src/contracts/ (no contract change), src/agent/, src/server/.
- Purpose: `run_checks(candidate)` for A's RepairAgent and `build_candidate(candidate)` for C's HostRunner. Independent scope check, build through `scripts/target.py build`, run the B3 suite in candidate mode against the built image on an internal Docker network, emit `CheckResult` bound to candidate hash, image ID and suite hash. Errors and unknowns never pass.

## Verification

- Unit tests with a fake command runner (no Docker needed).
- Real end-to-end run against a candidate once the baseline build is confirmed working.
