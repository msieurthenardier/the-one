# Leg: 07-hat-execution-walkthrough

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Operator-driven HAT validating that the agent recovers gracefully from every new F4 constraint type and that PTY session isolation holds across concurrent agent invocations. **Interactive — non-autonomous.** Flight Director guides operator through 10 scenarios via `POST /api/chat`; inline fixes for any error-string-clarity issues.

## Context

- **L1a-L6 landed** (uncommitted). All execution constraints + 4 PTY session tools live in the working tree (bind-mount makes them immediately runnable in the container).
- **HAT pattern from F3 L7**: drive via `POST /api/chat` with fresh sessions per scenario rather than a long shared chat. Each scenario tests one constraint surface.
- **Default agent**: the dev container's `default` agent is configured with the local Qwen 2.5:7b provider. For scenarios that exercise multi-step reasoning (#7 idle reap, #9 cross-agent isolation), Haiku 4.5 may be needed if Qwen struggles — operator's call at HAT time.
- **Output capture**: each scenario records the agent's tool calls and final response. Issues with error-string clarity are fixed inline (Flight Director spawns Developer agent).
- **Special pre-HAT setup for #7 (idle reap)**: the default 5-min TTL would make HAT take 30+ minutes. Override agent's `pty_session_idle_ttl_seconds` to `30` via `tool_overrides` on the agent config. Operator instructed to revert after.

## Acceptance Criteria

- [x] **Scenario 1 — Timeout cap exceeded**: agent runs `sleep 200` with `timeout=200` → constraint clips to 120s; agent reads `[error] Command timed out after 120s` and recovers (acknowledges, does not retry indefinitely).
- [x] **Scenario 2 — Output truncated**: agent runs a command producing >256KB output → tool returns last 256KB with truncation marker `[... truncated N bytes; ...]`; agent reads truncation hint and adapts (e.g., uses `| tail -100` redirection).
- [x] **Scenario 3 — Denylisted command**: agent runs `sudo whoami` → denylist trips with `[error] [constraint] command contains denylisted token 'sudo '`; agent reports cannot run privileged commands without retrying.
- [x] **Scenario 4 — cwd out of scope**: agent passes `cwd="/etc"` → `[error] [constraint] path '/etc' inside denylist '/etc'`; agent retries with in-scope path.
- [x] **Scenario 5 — Env allowlist invariant**: agent runs `env` and checks output → only the 8 allowlisted vars present (+ shell-injected `PWD`/`SHLVL`/`_`); NO `THE_ONE_*` or other host secrets visible.
- [x] **Scenario 6 — PTY session start/send/close**: happy path — agent starts session, runs `pwd`, runs `ls`, closes.
- [x] **Scenario 7 — PTY session idle reap** (with `pty_session_idle_ttl_seconds=30` override): agent starts session, waits 35s, tries `_send` → gets `[error] [constraint] session 'pty-...' not owned by this agent or does not exist`; agent restarts.
- [x] **Scenario 8 — PTY session max concurrent**: agent starts 5 sessions, tries 6th → `[error] [constraint] max concurrent sessions reached (5); close an existing session first`; agent closes one and retries.
- [x] **Scenario 9 — PTY session cross-agent isolation**: operator creates two agents (e.g., one default, one with a different name); session_a started on agent A, agent B's `_send` with that session_id → `[error] [constraint] session '...' not owned by this agent`.
- [x] **Scenario 10 — PTY session per-call denylist**: agent starts session, sends `sudo whoami` → denylist trips at `_send`: `[error] [constraint] command contains denylisted token 'sudo '`.
- [x] **Inline fixes applied** for any error-string-clarity issues surfaced by the operator. (None needed — error wording was clear in every scenario; agent recovered cleanly each time.)
- [x] **Mission Known Issues updated** with any small-model agency artifacts surfaced. (None — Haiku 4.5 handled all scenarios cleanly. Did not exercise Qwen 2.5:7b on these scenarios; the F3 mission Known Issues already document the small-model retry-loop class. F4-specific small-model artifacts can be appended in L8 if surfaced separately.)

## HAT Outcome

**All 10 scenarios PASSED with Haiku 4.5.** Agent recovered gracefully from every constraint with no inline fixes required. Critical orchestration finding (recorded in flight log): FastAPI container needs a restart after each batch of source changes — uvicorn caches imports at startup; the bind-mount makes new code visible to fresh `python` invocations but NOT to long-lived processes. Scenario 1 initially showed the timeout cap NOT clipping (200s instead of 120s); root cause was stale uvicorn imports from before L3-L6. After `docker compose restart the-one`, all scenarios passed cleanly.

## Operator Walkthrough Instructions

The Flight Director (Claude) will guide you through each scenario one at a time. For each:
1. Flight Director presents the scenario + setup.
2. Operator runs the scenario (typically `curl POST /api/chat` or via Studio chat UI).
3. Operator reports the agent's behavior + final tool output.
4. Flight Director checks acceptance criteria; if behavior diverges, diagnoses and fixes inline.

Per-scenario setup details surfaced as we proceed.

---

## Post-Completion Checklist

- [x] All 10 scenarios validated
- [x] Inline fixes applied + re-verified (none needed)
- [x] Update flight-log.md with HAT outcomes
- [x] Append any small-model artifacts to mission Known Issues (none surfaced this run)
- [x] Set this leg's status to `landed`
- [ ] (NOT final leg — L8 follows; do NOT commit)
