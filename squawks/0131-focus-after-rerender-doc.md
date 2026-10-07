# Squawk 0131: Document focus-after's re-render finding in agents.md

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

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
*(written at completion)*

## Verification
Doc-only. The section names the two editor kinds, and the never-steal targeting rule cites the leg 1b tests.

## Sign-Off
*(written at completion)*
