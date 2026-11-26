# Squawk 0436: the CLAUDE.md agent contract omits the agent write lock

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report

Mission 37 Flight 2 added `agent_write_lock(name)` (`the_one/agent/service.py`). Every whole-row agent writer must take it, agent lock first, then the store lock, and never inside a `precheck` or `on_commit` hook. That rule is stated only in `the_one/agents.md`. CLAUDE.md's contract bullet "**Agent PUT preserves credentials**" (CLAUDE.md:77) lists the agent-write contracts every change must respect, but does not mention the lock. A future agent writer could therefore miss it.

## Evidence
- `grep agent_write_lock CLAUDE.md` finds nothing.
- `the_one/agents.md` holds the lock rule (Flight 2 Leg 2, AC6).

## Corrective Action
*(written at completion)* Add one clause to the existing CLAUDE.md bullet, for example "a new agent writer takes `agent_write_lock`", pointing to the `agents.md` section. Do not add a new paragraph (squawk 0397).

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
