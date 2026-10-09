# src/contracts

Owner: A with B/C review.

Shared typed run, candidate, check, deployment, observation, and report contracts. Agree these before implementation.

Status: Draft contracts implemented in `models.py` per PRD section 6. Pending B/C review before other modules build against them.

## Contents

- `models.py` — `Run`, `Candidate`, `CheckResult`, `DeployRequest`, `DeployResult`, `Observation`, `Event`, `Report` dataclasses, plus `RunState` and `CheckStatus`/`DeployStatus` enums.

Host assigns identity fields (hashes, IDs); a candidate's own claimed hash is never trusted. See [the PRD](../../docs/PRD.md) section 6 for the full field rationale and the state transition diagram.
