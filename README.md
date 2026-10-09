# Antibody

An autonomous repair agent that closes a security hole without closing the business.

Antibody will repair one SQL-injection defect in a team-owned OWASP Juice Shop deployment, run independent behavior checks, deploy the passing candidate to a public endpoint, and publish observed evidence.

Status: PRD and folder structure in place. Shared contracts (`src/contracts/`) implemented and pending B/C review. Host validation (unit-tested) and bounded repair loop (`src/agent/`), plus the Semgrep adapter (`src/adapters/`), are implemented; the Guild patch adapter is an honest stub. **Guild agent sessions are currently hanging indefinitely (zero server-side events) — escalated to Guild's team, see `docs/plan-for-A.md` for evidence.** No vendor deployment has been implemented or verified yet.

## Start here

- [PRD and three-person task board](docs/PRD.md)
- [Builder A implementation plan and checklist](docs/plan-for-A.md)
- [Vendor setup checklist](docs/vendor-setup/README.md)
- [Repository structure](docs/STRUCTURE.md)

A owns agent/repair; B owns target, independent verification, and deployment; C owns evidence, UI, and additional sponsor integrations. Names will be assigned by the team.

The required sponsor core is Guild AI, Semgrep, and ClickHouse. Additional integrations target Senso, Akash, ElevenLabs, and Pi when actual access works. Zyras is an optional private service integration; its source and credentials are not part of this repository.

Before implementation, resolve the new account's vendor access, pin the target revision, confirm event rules, and agree contracts. Do not reuse credentials from another project. Keep secrets in ignored local configuration and server-side vendor stores.

## Tech stack

- **Backend / agent** (A's `src/agent/`, `src/adapters/`, `src/contracts/`): Python 3.11+, plain dataclasses for contracts, no framework imposed yet. Packaged via `pyproject.toml`; install with `pip install -e .`.
- **Target under repair** (B's `tests/fixtures/juice-shop/`): OWASP Juice Shop — Node.js/TypeScript, its own Dockerfile/build (per PRD). Treat it as an external pinned revision, not part of this repo's own stack.
- **Host API / dashboard** (C's `src/server/`, `src/web/`): backend owner's choice for `src/server/` (align with A's Python if reused for the host API — confirm with C); `src/web/` is **React + TypeScript**.
- **Evidence store**: ClickHouse (C), queried from the host API, not written to directly by the agent.
- **Scanner**: Semgrep CLI (local, no account needed) — already wired in `src/adapters/semgrep.py`.
- **Agent runtime**: Guild AI (pending A1 account/session setup).
- Cross-boundary contract: the Python dataclasses in `src/contracts/models.py` are the source of truth for shapes; anything crossing into `src/web` goes over an HTTP API as JSON, not as a shared import.

## Handoff: B and C pick up here

A has drafted the shared contracts in [`src/contracts/models.py`](src/contracts/models.py): `Run`, `Candidate`, `CheckResult`, `DeployRequest`, `DeployResult`, `Observation`, `Event`, `Report`, plus `RunState`/`CheckStatus`/`DeployStatus` enums. These are Python dataclasses (backend stack; `src/web` stays React/TS and consumes them over the API, not by import).

Review before building against them — the host assigns identity fields (hashes, IDs); nothing trusts a model- or candidate-claimed value.

- **B**: your `B4` (verification worker) and `B5` (deploy connector) should emit `CheckResult`/`DeployResult`/`DeployRequest` matching these shapes exactly. Flag any field you need that's missing before you implement around a workaround.
- **C**: your `C2`/`C3` (ClickHouse schema, evidence API) should consume `Event`/`Report` as defined here. Flag schema concerns now, before data starts flowing.
- Project is Python (`pyproject.toml` at root, package under `src/`); install with `pip install -e .` once you add real dependencies.
- Still blocking A: **B1** (pinned Juice Shop source commit + baseline image digest) — A can't start Guild/Semgrep baseline work until that lands.
