# Squawk 0131: Document focus-after's re-render finding in agents.md

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

## Report

Mission 25 Flight 6 leg 1b found that editors handle a held save differently:
- an editor that **re-renders on save** (the agent editor) loses a field's focus to the re-render itself;
- an editor that **patches in place** (the provider editor) keeps it.

So `App.focusAfter`'s never-steal rule, and any test of it, must target an element that survives the re-render, such as the Agents list filter. The finding is in the flight log only. Put it in `agents.md`'s "Focus after an in-place action".

## Evidence

- The Flight 6 flight log, "Leg 1b: focus-after-action".
- The Flight 6 debrief, Documentation.
- `the_one/agents.md`, section "Focus after an in-place action".

## Corrective Action
Added a paragraph, "What a held save can steal", to `the_one/agents.md` under "Focus after an in-place action": a re-rendering editor (agent) loses an inner field's focus to the re-render; an in-place patching editor (provider) keeps it; never-steal tests must target a surviving element (the Agents list filter `agents-filter` for the agent, `#pf-name` for the provider). CLAUDE.md untouched.

## Verification

Doc-only. The paragraph names both editor kinds and cites the leg 1b tests (`test_flow_agents_focus_after.py`, `test_flow_settings_focus_after.py`). `make test-unit` and ruff were run; see the developer report.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
