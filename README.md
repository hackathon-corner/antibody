# Antibody

An autonomous repair agent that closes a security hole without closing the business.

Antibody will repair one SQL-injection defect in a team-owned OWASP Juice Shop deployment, run independent behavior checks, deploy the passing candidate to a public endpoint, and publish observed evidence.

Status: PRD and folder structure in place. Shared contracts (`src/contracts/`) implemented and pending B/C review. No agent, vendor setup, repair, or deployment has been implemented or verified yet.

## Start here

- [PRD and three-person task board](docs/PRD.md)
- [Vendor setup checklist](docs/vendor-setup/README.md)
- [Repository structure](docs/STRUCTURE.md)

A owns agent/repair; B owns target, independent verification, and deployment; C owns evidence, UI, and additional sponsor integrations. Names will be assigned by the team.

The required sponsor core is Guild AI, Semgrep, and ClickHouse. Additional integrations target Senso, Akash, ElevenLabs, and Pi when actual access works. Zyras is an optional private service integration; its source and credentials are not part of this repository.

Before implementation, resolve the new account's vendor access, pin the target revision, confirm event rules, and agree contracts. Do not reuse credentials from another project. Keep secrets in ignored local configuration and server-side vendor stores.

## Handoff: B and C pick up here

A has drafted the shared contracts in [`src/contracts/models.py`](src/contracts/models.py): `Run`, `Candidate`, `CheckResult`, `DeployRequest`, `DeployResult`, `Observation`, `Event`, `Report`, plus `RunState`/`CheckStatus`/`DeployStatus` enums. These are Python dataclasses (backend stack; `src/web` stays React/TS and consumes them over the API, not by import).

Review before building against them — the host assigns identity fields (hashes, IDs); nothing trusts a model- or candidate-claimed value.

- **B**: your `B4` (verification worker) and `B5` (deploy connector) should emit `CheckResult`/`DeployResult`/`DeployRequest` matching these shapes exactly. Flag any field you need that's missing before you implement around a workaround.
- **C**: your `C2`/`C3` (ClickHouse schema, evidence API) should consume `Event`/`Report` as defined here. Flag schema concerns now, before data starts flowing.
- Project is Python (`pyproject.toml` at root, package under `src/`); install with `pip install -e .` once you add real dependencies.
- Still blocking A: **B1** (pinned Juice Shop source commit + baseline image digest) — A can't start Guild/Semgrep baseline work until that lands.
