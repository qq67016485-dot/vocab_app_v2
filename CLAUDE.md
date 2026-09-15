# CLAUDE.md

This project's agent rules live in **[AGENTS.md](AGENTS.md)** — the single source of
truth for project overview, tech stack, commands, configuration, hard rules,
architecture summary, testing setup, and code conventions.

Full architecture detail lives in
**[docs/architecture-decisions.md](docs/architecture-decisions.md)** (AGENTS.md is the
compressed summary; consult the architecture doc before modifying a subsystem).

This file intentionally holds no duplicated rules — it exists so tools that look for
`CLAUDE.md` by name are routed to `AGENTS.md`, preventing the two files from drifting
apart (they diverged once already; AGENTS.md won as the maintained copy).
