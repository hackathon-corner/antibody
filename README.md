# Antibody

An autonomous repair agent that closes a security hole without closing the business.

Antibody will repair one SQL-injection defect in a team-owned OWASP Juice Shop deployment, run independent behavior checks, deploy the passing candidate to a public endpoint, and publish observed evidence.

Status: PRD and folder structure only. No application, vendor setup, repair, or deployment has been implemented or verified.

## Start here

- [PRD and three-person task board](docs/PRD.md)
- [Vendor setup checklist](docs/vendor-setup/README.md)
- [Repository structure](docs/STRUCTURE.md)

A owns agent/repair; B owns target, independent verification, and deployment; C owns evidence, UI, and additional sponsor integrations. Names will be assigned by the team.

The required sponsor core is Guild AI, Semgrep, and ClickHouse. Additional integrations target Senso, Akash, ElevenLabs, and Pi when actual access works. Zyras is an optional private service integration; its source and credentials are not part of this repository.

Before implementation, resolve the new account's vendor access, pin the target revision, confirm event rules, and agree contracts. Do not reuse credentials from another project. Keep secrets in ignored local configuration and server-side vendor stores.
