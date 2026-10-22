# Leg: main-merge-and-overrides-port

**Status**: landed
**Flight**: [Agents on the library](../flight.md)

## Objective
Bring `main` (squawk 0223, `f6b2ed0`) into the flight branch. Port 0223's client rule into the split `agent-form-data.js`, and add the override tests 0223 left open. After this leg, DD9-2 is complete on the flight branch, before the Tools-tab rebuild (08b).

## Context
- **Squawk 0223 is merged to `main`:**
  - `update_agent` preserves `tool_overrides` when the key is omitted; `null` clears; a map replaces;
  - tests: `tests/test_agent_tool_overrides_round_trip.py` (omit, null, map) and `tests/browser/test_flow_studio_tool_overrides_preserved.py`.
- **Its client rule** lives in `main`'s `studio.js` `collectFormData`:
  - `loadedTools` is the set of `data-tool-override-tool` values among `[data-tool-override-tool][data-tool-override-field]` elements in the editor;
  - **empty** set: omit `tool_overrides`;
  - **non-empty** set: send the edited map plus the stored entries (`self._selectedAgent.tool_overrides`) of tools whose panel was not loaded.
- **On this branch**, `collectFormData` moved to `js/areas/studio/agent-form-data.js` (leg 03).
- **Conflict surface** (design review; `f6b2ed0` touches six files):
  - `studio.js` conflicts hard;
  - `CLAUDE.md` may conflict (the branch edits it too);
  - `api.py`, the two tests and the squawk file apply cleanly;
  - `tests/_ui_ownership_allowance.py` and `tests/test_ui_guards.py` are untouched by `main`.
- **The FD commits the landed legs (01-07b) on the flight branch before this leg**, so the tree is clean for the merge. The flight review still runs over the whole flight at the end.

## Acceptance Criteria
- [ ] **The merge.** `git fetch origin && git merge origin/main` on the flight branch (no rebase, no force):
  - `studio.js`: resolve with the branch's version (`git checkout --ours`), then **port** the 0223 block into `agent-form-data.js` `collectFormData` by hand, with identical semantics;
  - `CLAUDE.md`: keep both sides (the branch's edits plus `main`'s `tool_overrides` watch-out clause);
  - every other file takes `main`'s version.

  The merge commit message names squawk 0223.
- [ ] **The 0223 tests pass unchanged on the flight branch:** `tests/test_agent_tool_overrides_round_trip.py` and `tests/browser/test_flow_studio_tool_overrides_preserved.py`.
- [ ] **New tests:**
  - **API test:** a PUT with `"tool_overrides": {}` stores an empty map, or clears it; record which, since the server writes it as given;
  - **Browser, partial merge:** an agent with overrides on two tools. Open one tool's Overrides, edit it, Save, and read it back: the edited tool shows its new value and the other tool's stored overrides are intact;
  - **Browser, stale stored entries:** Save once with one tool opened, then open a *different* tool, edit it, Save again, and read it back: the first tool's value from the first save is intact. This proves `_selectedAgent` is refreshed after Save and the merge does not use stale stored entries;
  - **Browser, locked chips:** for an operator NarrowSuperset list (`path_denylist`), the locked chips are sent as part of the union and the save is accepted.
- [ ] **Gates:** `make test-unit`; the `agents` lane under netns; ruff. The full gate is not required here (08b runs lanes; leg 11 runs the full gate).
- [ ] **Flight log:** the merge resolution per file, the port diff summary, the `{}` outcome.

## Files Affected
- Merge: `CLAUDE.md`, `the_one/interfaces/web/api.py`, `squawks/0223-*.md`, `tests/test_agent_tool_overrides_round_trip.py`, `tests/browser/test_flow_studio_tool_overrides_preserved.py` (from `main`).
- Port: `the_one/interfaces/web/static/js/areas/studio/agent-form-data.js`.
- New tests in the agents lane and the unit API test file.

## Citation Audit
From the leg 08 design review (2026-10-21; it fetched `origin/main` `f6b2ed0`).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
