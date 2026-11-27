# Contributing

Every contribution to this project must be planned and built through the [Mission Control](https://github.com/msieurthenardier/mission-control) plugin for Claude Code. A pull request that was not is closed without merge, however good the code.

This is how the project has been built since April 2026 (see "How it was built" in the [README](README.md)). The plan, the review and the test evidence are part of the change, not extras.

## The rule

Pick the route that fits the work:

| Work | Route | Artifacts live in |
|---|---|---|
| A mission: one outcome, a few flights | `/mission-control:mission`, then `/mission-control:flight` for each flight, run with `/mission-control:agentic-workflow` | `missions/{NN}-{slug}/` |
| A standalone feature, too big for a squawk and too small for a mission | `/mission-control:sortie` | `sorties/{NN}-{slug}/` |
| A small defect or routine update, with no design decisions | `/mission-control:squawk` | `squawks/{id}-{slug}.md` |

A pull request must carry the artifacts the plugin produces for its route:

- **A flight or sortie:** `flight.md`, the leg specs under `legs/`, `flight-log.md`, `flight-briefing.md` and `flight-debrief.md` (a flight inside a mission sits under that mission's `flights/`).
- **A squawk:** the completed squawk file, with its corrective action, verification and sign-off.

The work must also have been reviewed by an independent Reviewer agent, never the agent that implemented it. The plugin's `agentic-workflow` skill runs this cycle. A pull request with missing artifacts, or with no independent review, is closed.

## Install the plugin

From a Claude Code session:

```
/plugin marketplace add msieurthenardier/mission-control
/plugin install mission-control@flight-control
```

Then, from the repository root, run `/mission-control:preflight-check`. It confirms that this project's methodology files match the installed plugin version. The repository is already initialised for Flight Control (its `.flightops/` directory is committed), so do not run `/mission-control:init-project` on a fresh clone; preflight-check reports any drift. Plugin docs: <https://github.com/msieurthenardier/mission-control>.

## Where to start reading

1. [.flightops/README.md](.flightops/README.md)
2. [.flightops/FLIGHT_OPERATIONS.md](.flightops/FLIGHT_OPERATIONS.md), the workflow you must follow
3. [.flightops/ARTIFACTS.md](.flightops/ARTIFACTS.md), where every artifact goes and its format
4. [.flightops/agent-crews/](.flightops/agent-crews/), the crew for each phase
5. [CLAUDE.md](CLAUDE.md), the working rules, then [the_one/agents.md](the_one/agents.md), the architecture

## Talk first

Open a [GitHub issue](https://github.com/msieurthenardier/the-one/issues) before you start a mission, sortie or flight. The operator agrees each mission's outcome, or a sortie's charter, before any design starts, and every flight belongs to an agreed mission or is itself an agreed sortie.

## Host and gate

Development and the required gate run on Linux or Windows WSL2. `scripts/run-tests.sh`, and so `make test-browser` and `make gate`, needs Bash 4 or later (it uses `declare -A`) and `setsid`. Stock macOS has neither. Running `python -m pytest` directly on the browser tests does not count as the gate.

```bash
pip install -e ".[all-llms,dev]"
pre-commit install
make gate            # unit tests, then every browser lane
```

On WSL2 with mirrored networking, browser runs need `THE_ONE_TEST_NETNS=1`; see "Testing" in [CLAUDE.md](CLAUDE.md). Lint and format must be clean:

```bash
ruff check the_one/ tests/ scripts/ evals/
ruff format --check the_one/ tests/ scripts/ evals/
```

## Safety rules

The full list is in [CLAUDE.md](CLAUDE.md) ("Safety rules"). In short:

- Never point tests, probes or evals at port 8484 or 8485, or at the default data directory. Use port 8486 or higher and a scratch data directory under `$HOME`.
- Never commit `.env` files, credentials or tokens. Never print the API credential.
- Edit source, tests and docs with the editor tools the project's hook allows, not shell redirects (see CLAUDE.md "Shell-write rule").
