# Squawk 0223: An agent's stored tool overrides are wiped on Save when Overrides was never opened

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-10-21
**Completed**: 2026-10-21

## Report
Saving an agent from the Agents editor (for example, changing only its description) erases its stored per-tool overrides (`tool_overrides`), unless the operator opened a tool's "Overrides" panel during that edit. It is silent data loss.

**Reproduce:**
1. Give an agent a `read_file` `path_denylist` override.
2. Reload, open the agent, change its description, and Save.
3. `GET /api/agents/{name}`: `tool_overrides` is `null`.

Found during Mission 31 Flight 2 planning, where the Architect review confirmed it. The operator asked for a hotfix on `main` (2026-10-21). Flight 2 leg 08 reconciles its Tools-tab rebuild with this fix.

## Evidence
- **Server.** `the_one/interfaces/web/api.py` `update_agent` (about `:946-974`) preserves omitted keys only for `mcp_overrides`, `self_revision_requires_approval`, `notes_enabled` and `kb_ids` (`:969-974`, the `kb_ids` pattern).
  - `AgentConfig.tool_overrides` defaults to `None`.
  - The repository upsert writes it unconditionally (`the_one/db/repositories.py` about `:255,273`).
  - So both an omitted key and `null` clear it.
- **Client.** `the_one/interfaces/web/static/js/areas/studio.js` `collectFormData` (about `:3614`) sends `null` for an empty overrides map. The override inputs exist only after a tool's `<details>` opens (`studio/tools-tab.js` about `:379`), so an unopened panel always yields `null`.

## Corrective Action
- `the_one/interfaces/web/api.py` `update_agent`: `tool_overrides` omitted from the PUT body now preserves the stored map (the `kb_ids` pattern). Explicit `null` clears; a map replaces. Other `AgentConfig(` write paths untouched.
- `the_one/interfaces/web/static/js/areas/studio.js` `collectFormData`: `tool_overrides` is omitted when no override input was rendered this mount; otherwise the edited map is sent (`{}` if all cleared), and tools whose panel was never opened keep their stored entry from `self._selectedAgent`, so opening one tool's panel cannot wipe another's overrides.
- `CLAUDE.md`: agent-PUT watch-out notes `tool_overrides` is preserved when omitted.
- Tests: `tests/test_agent_tool_overrides_round_trip.py` (3 new), `tests/browser/test_flow_studio_tool_overrides_preserved.py` (new).

## Verification
- `the_one.__file__` with `PYTHONPATH=$PWD` resolves to `~/projects/the-one-squawk-wt/the_one/__init__.py`.
- API unit tests: with the `api.py` fix stashed, `test_omitted_key_preserves` fails (1 failed, 8 passed); with it, 9 passed.
- Browser test: before the api.py + studio.js fix it fails (`tool_overrides` is `None`); after, passes.
- Per the Flight Director's amendment (host lane policy), the full agents lane was NOT run; instead, sequentially under netns: new preserve test (1 passed), `test_flow_studio_tools_overrides.py` (12 passed), `test_flow_studio_time_tool.py` (7 passed), `test_flow_agent_tabs.py` (12 passed).
- Unit tier (incl. ui guards, token and a11y tests, no allowance changes needed): 6728 passed, 15 skipped, excluding `tests/test_webkitgtk_probe_safety.py`, whose 2 failures are environmental (the worktree has no `.venv`) and reproduce on the unmodified baseline.
- ruff check and format clean on changed files.
- Original (pre-fix) spec detail: - **Unit tests** (API level):
  - omitting `tool_overrides` from the PUT keeps the stored value;
  - an explicit `null` clears it;
  - a supplied map replaces it.
- **Browser test:** seed overrides, change only the description, Save, read the agent back: the overrides are intact.
- The client sends no `tool_overrides` key when no override body was loaded, and sends the edited map (`{}` when every value was cleared) when one was.

## Sign-Off
*(written at completion)*
**Reviewer**: independent Reviewer (Sonnet tier: agent update API, encrypted-at-rest overrides)
**Verdict**: confirmed, no blocking issues. A non-blocking gap: the partial-merge path (one tool's panel opened, the others' stored overrides kept) has no browser test yet. It is carried to Mission 31 Flight 2 leg 08, which rebuilds this code.
**Commit**: squawk/0223 commit on branch `squawk/0223-tool-overrides-wiped-on-save` (see git log)
