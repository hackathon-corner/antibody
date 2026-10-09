# guild-agents

Guild-managed agent sources. Each subdirectory is its own `guild agent init`/`clone` checkout with a nested `.git` remote pointing at Guild's server — gitignored here, tracked on Guild instead. Pull a fresh checkout with `guild agent clone <owner>~<agent-name>`.

## antibody-repair-agent

- Guild agent: `g3ram~antibody-repair-agent` (`01a12248-138c-726e-0000-1fcb7df24304`)
- Workspace: `g3ram~antibody-dev` (`01a1224a-2310-3bb9-0000-99807e6c2ff8`)
- Status: scaffolded with one zero-dependency `ping` tool, used to prove a real Guild session/tool-call round trip for A1. Currently blocked — see `docs/plan-for-A.md` for details and escalation status.
- Clone locally: `guild agent clone antibody-repair-agent`
