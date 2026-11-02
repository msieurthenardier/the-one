# Leg: definite-dead-sweep

**Status**: completed
**Flight**: [Dead code](../flight.md)

## Objective
Delete the items the 2026-10-30 inspection found definitely dead (finding #24), each re-verified by a repo-wide grep at leg time, without touching any live code or the traps the report lists.

## Context
- Flight Technical Approach step 1; mission criterion "Dead code removed" (#24). Mission constraint: no coverage loss (each removed test is named in the flight log with the test that covers its regression), no live code removed.
- Flight Design Decision: re-grep each item, excluding `.claude/` (worktree copies), `.git/`, `.venv/` and the planning artifacts (`missions/`, `maintenance/`, `squawks/`, `sorties/`), which mention names as history.
- **Re-grep at leg design (Flight Director, `de03e35f`)**, every item has its definition as its only code reference:
  - `scripts/entrypoint.sh` — no reference anywhere outside planning artifacts (Docker-era, last touched `dc570806`).
  - `scripts/ui_capture.py::_tool_read_file` (`:750`) — no caller, not wired into any `Surface(prepare=...)`.
  - `the_one/db/models.py::VALID_ROUTING_SCOPES` (`:189`).
  - `the_one/mcp/cache_cleanup.py::UV_ENVIRONMENTS_ROOT` (`:68`) and its "retained for backward compatibility" comment (`:62-67`; delete the comment lines that exist only for it, keep any that explain neighbouring constants).
  - `the_one/tools/_search_backends.py::SEARCH_BACKENDS` (`:539`).
  - `static/css/studio.css:236` — `.area-studio .self-configuration-toggle-switch { margin-top: 4px; }` (no emitter; grep the JS for the class string, including string-building like `'self-configuration-toggle-' + …`, before deleting).
  - `tests/conftest.py::make_registry` (`:227`) and CLAUDE.md "Test patterns" bullet "**`make_registry`** fixture: …" (`tests/test_agent_search_integration.py` has its own private `_make_registry`, which stays).
  - `static/js/areas/studio/agent-editor.js:372` — `window.App.studio.AGENT_PANEL_IDS = PANEL_IDS;` (delete the export line only; `PANEL_IDS` itself is used inside the module — check).
  - `tests/_evals_helpers.py::NO_SLEEP_HOOKS` (`:16`), `tests/_mcp_signin_helpers.py::_MISSING` (`:26`), `tests/browser/_nav.py::_origin` (`:282`) — each has only its definition.
- **Medium-confidence CSS variants** `badge--local`, `badge--remote` (`static/css/components.css:1958`, `:1964`) and `ui-list-pane-compact` (`:706`): these classes may be produced by a factory from an option value (`App.ui.badge`'s `KINDS` list and kind→class mapping; `App.ui.listPane`'s density/compact option). Read the factories (`static/js/ui/`) and the call sites. Delete a variant only if no option value, constant or call site can produce it; otherwise leave it and record why in the flight log. The catalogue `docs/ui-control-inventory.md` and `tests/test_ui_ownership.py` / `tests/test_ui_emitted_classes.py` own class lists: a deleted class must leave no catalogue row or allowance stale. Also delete the matching design tokens only if they become unreferenced (`tests/test_token_definitions.py` checks the reverse direction only, so grep the tokens).
- **Do not touch** the traps the report lists: FastAPI handlers (registered by decorator), pydantic hooks (validators called by the framework), the mcp `TokenStorage` methods, Cocoa delegate callbacks and ctypes fields, the `_reset_for_tests` helpers, `StubPlugin.mark_dead`.
- **Leave `tools/resolver.py` alone** (flight Design Decision).

## Inputs
- `main` at `de03e35f` (Flight 2 merged), branch `flight/03-dead-code`.

## Outputs
- The deletions above; CLAUDE.md "Test patterns" without the `make_registry` bullet; the flight log lists every deleted item with the grep that proved it dead, and every item kept with the reason.

## Acceptance Criteria
- [ ] **AC1 — re-verified before each deletion.** For every item, a grep (`grep -rn --exclude-dir={.claude,.git,.venv,missions,maintenance,squawks,sorties} '<name>' .`) run immediately before deleting it shows only its definition (and, for `make_registry`, the CLAUDE.md bullet); the flight log records the command and result per item. An item with any other reference is dropped (Adaptation Criteria) and recorded.
- [ ] **AC2 — deleted.** After the leg, the same grep for every deleted name returns nothing (apart from `_make_registry` in `test_agent_search_integration.py`, `PANEL_IDS` inside `agent-editor.js`, and unrelated `_origin`/`_MISSING` names in other files).
- [ ] **AC3 — CSS variants decided.** Each of `badge--local`, `badge--remote`, `ui-list-pane-compact` is either deleted (no producer exists, with the reasoning) or kept (with the producer named) in the flight log.
- [ ] **AC4 — guards and suites.** `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py` pass; `THE_ONE_TEST_NETNS=1 make test-unit` passes with the same 15 skips; `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/` are clean.
- [ ] **AC5 — browser.** Because `agent-editor.js`, `studio.css` and possibly `components.css` change, the `agents` lane passes (`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents`), and if a `components.css` class is deleted the `contracts` lanes pass too (`THE_ONE_REQUIRE_WEBKIT=1 … --lane contracts`), one lane at a time, never beside the unit suite.
- [ ] **AC6 — vulture.** `uvx vulture the_one/ evals/ scripts/ --min-confidence 60` no longer lists any deleted Python item (record the before/after lines for them; other findings are out of scope).

## Verification Steps
- AC1/AC2/AC3: the greps and the flight log.
- AC4/AC5: the commands above.
- AC6: run vulture before and after; if `uvx` cannot reach the network, record that and skip AC6 (not a blocker).

## Implementation Guidance
1. Run vulture first (AC6 baseline).
2. For each item: grep, delete through the edit tool (a whole file such as `scripts/entrypoint.sh` may be removed with `git rm`), re-grep.
3. CSS variants: read the factories before deciding.
4. Edit CLAUDE.md's "Test patterns" list (remove the `make_registry` bullet only).
5. Run the guards, the unit suite, then the lane(s).

## Edge Cases
- `UV_ENVIRONMENTS_ROOT`'s comment block may also describe a live neighbour; keep any sentence that does.
- `NO_SLEEP_HOOKS` / `_MISSING` / `_origin` may be referenced through `from x import *` or `getattr` strings; the grep on the bare name covers both.
- `scripts/entrypoint.sh` may be named in `.dockerignore` or packaging globs; the repo-wide grep covers them.

## Files Affected
- `scripts/entrypoint.sh` (deleted), `scripts/ui_capture.py`, `the_one/db/models.py`, `the_one/mcp/cache_cleanup.py`, `the_one/tools/_search_backends.py`, `the_one/interfaces/web/static/css/studio.css`, possibly `components.css` and `docs/ui-control-inventory.md`, `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`, `tests/conftest.py`, `tests/_evals_helpers.py`, `tests/_mcp_signin_helpers.py`, `tests/browser/_nav.py`, `CLAUDE.md`, the flight log.

## Citation Audit
Re-grepped at `de03e35f` (Flight Director, 2026-11-02): line numbers drifted from the flight's table — `make_registry` `tests/conftest.py:227` (was 215), `AGENT_PANEL_IDS` `agent-editor.js:372` (was 361); the rest match. Every item still has only its definition as a code reference.
