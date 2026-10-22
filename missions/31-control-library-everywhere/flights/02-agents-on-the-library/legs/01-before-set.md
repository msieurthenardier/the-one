# Leg: before-set

**Status**: landed
**Flight**: [Agents on the library](../flight.md)

## Objective
Extend `scripts/ui_capture.py` with the agent-editor surfaces and the admin Built-in tools editor (flight DD10), then take Flight 2's "before" capture set. No application source changes.

## Context
- **Flight DD10:** captures are local evidence, never committed. The operator approves the before/after set at the HAT. The "before" set must be taken before any agent file changes, and this leg changes none.
- **The tool** (Mission 31 Flight 1, legs 03 and 08):
  - `SURFACES` is a list of `Surface(name, hash, ready, description, prepare, shot, stubs, skipped)` (`scripts/ui_capture.py:211-345`).
  - `seed(base, token)` (about `:454`) seeds one provider per type plus `"Capture agent"` on the mock provider.
  - Each surface gets a fresh context, both themes, full-page capture (the viewport grows by the panes' overflow), and the `THE_ONE_TEST_NETNS=1` re-exec.
  - The safety refusals are pinned by `tests/test_ui_capture_safety.py`.
- **The agent editor** has its route at `#agents/{name}[/{tab}]`. The tab ids are `general`, `rules-and-notes`, `knowledge`, `mcps`, `tools` and `self-configuration` (`js/areas/studio/agent-editor.js:57-64`).

## Inputs
- Branch `flight/02-agents-on-the-library` at `9369fcc` (the flight plan only; no source changes yet).

## Outputs
- `scripts/ui_capture.py`: richer seeding and the new surfaces.
- `tests/test_ui_capture_safety.py`: updated only if the table test needs it.
- The before set at `$HOME/.cache/the-one-ui-capture/m31-f2-before/`, recorded in the flight log.

## Acceptance Criteria
- [ ] **Seeding** adds, through the API, an agent that exercises every tab: `"Capture agent"`, extended, or a second agent `"capture-tabs"`. Each element is added where the API allows it:
  - a description and a system prompt;
  - a knowledge base attached (create one KB through `POST /api/knowledge-bases`; no folder or items needed);
  - an MCP source attached (create a `streamable-http` source pointing at an unreachable loopback URL; the tools list is stubbed in the browser);
  - built-in tools with some enabled and some disabled, so one category is in the mixed state;
  - a stored `tool_overrides` entry for `read_file` with `path_denylist` values;
  - two rules, one disabled;
  - notes enabled, with one note (only if a note can be created through the API without a model run; otherwise skip notes and record why);
  - self-configuration enabled (`POST .../self-configuration/enable`), if that works with no live model. A pending revision cannot be created without the agent acting, so it is `SKIPPED` with that reason unless an API path exists.
- [ ] **New surfaces**, each in light and dark:
  - `agent-general` (`#agents/{agent}/general`);
  - `agent-rules-and-notes`;
  - `agent-knowledge`;
  - `agent-mcps`: the MCP source expanded, with its tools stubbed by a `page.route` on the source-tools endpoint the tab fetches (find it in `mcps-tab.js` / `studio.js` `fetchMcpSourceTools`), returning 3-4 tools;
  - `agent-tools`: the Filesystem category expanded and `read_file`'s Overrides open, showing the chip list;
  - `agent-self-configuration`;
  - `admin-builtin-tool-editor` (`#settings/tools/read_file`, or any tool with a chip-list field), as the guard for the shared chip-list rules (DD3).

  Each surface's ready selector is its settled state, a testid or a stable element, not the shell. The `{agent}` placeholder resolves from the seeded name. A surface that cannot be prepared is `SKIPPED` with a one-line reason.
- [ ] **`--list` prints the new surfaces.** If `tests/test_ui_capture_safety.py`'s surface-table test enumerates names, it is updated. It still passes, as does `make test-unit`.
- [ ] **The before set is taken:** `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f2-before` covers all surfaces (the provider ones too, as a regression base).
  - At least five agent PNGs are opened with the Read tool to confirm they show the intended tab and state: Tools with the override open, MCPs expanded, Rules, General, and the admin editor.
  - The flight log records the path, the surface list and the `SKIPPED` list.
  - `git status` shows no PNG.
- [ ] **No application source file changes.** `git diff --stat 9369fcc -- the_one/` is empty.
- [ ] ruff check and format are clean on `scripts/` and `tests/`.

## Verification Steps
- `.venv/bin/python scripts/ui_capture.py --list`
- `.venv/bin/python -m pytest tests/test_ui_capture_safety.py -x -q`
- `make test-unit`
- The capture run above, then Read five PNGs.
- `git diff --stat 9369fcc -- the_one/` (expect empty), and `git status --short` (expect no PNG).

## Implementation Guidance
1. Read `scripts/ui_capture.py`'s `seed`, `Surface`, `_api` and the prepare helpers.
2. Read the agent APIs:
   - `POST /api/agents` and `PUT /api/agents/{name}` (fields `enabled_tools`, `disabled_tools`, `kb_ids`, `mcp_source_ids`, `tool_overrides`);
   - `/api/agents/{name}/rules`;
   - `/api/agents/{name}/notes/settings`;
   - `/api/agents/{name}/self-configuration/enable`;
   - `/api/knowledge-bases`;
   - `/api/mcp-sources`.

   Use `tests/browser/seeders.py` and the agent browser tests as shape references; do not import them.
3. Add the surfaces with prepares: click the tab, expand the tile, open `<details>`.
4. Run, inspect, record.

## Edge Cases
- **An MCP source that tries to connect at render** must not hang the capture. Stub its tools and status routes, or accept and record the tab's error state as the captured state.
- **Self-configuration enable** may mint a credential and attach a loopback source. That is fine in the scratch instance.
- **Tests:** none are expected to break, since only `scripts/` changes.

## Files Affected
- `scripts/ui_capture.py`, and possibly `tests/test_ui_capture_safety.py`.

## Citation Audit
Checked at `9369fcc`: `scripts/ui_capture.py:200-345` (`Ctx`, `Surface`, the table) and `agent-editor.js:57-64` (tab ids, from the planning survey).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
