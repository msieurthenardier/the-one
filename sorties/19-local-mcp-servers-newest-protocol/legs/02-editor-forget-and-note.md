# Leg: editor-forget-and-note

**Status**: completed
**Flight**: [Local-command MCP servers: newest protocol and Forget](../flight.md)

## Objective
In the Library MCP server editor, "Forget tools list" is shown on a local-command server that has a stored tools list, and the Server section shows one warning line under the facts when the stored record says the connection fell back to an older protocol for lack of an answer.

## Context
- Flight decisions DD4 (the note: an `App.ui.banner`, tone `warning`, role `note`, testid `mcp-server-protocol-fallback`, built once and toggled) and DD5 (the Forget rule for a local-command server), and the operator-approved Mockup. Read them first.
- Leg 1 (`patient-discover`) stores `protocol_fallback: "no_answer"` in a source's `_cache` beside `protocol_version` when a Test of a local-command server fell back for lack of an answer, deletes the key on every other successful Test, and drops it when the server behind the record changes. This leg only reads that key. Nothing in this leg depends on a real slow server.
- The route behind the button, `DELETE /api/mcp-sources/{id}/connection`, already accepts a local-command source: it drops `_cache`, the per-agent tool lists and the remembered protocol, and closes pooled connections. It does not change here, apart from its docstring.
- This reverses Mission 31 Flight 5's DD6 ("stdio gets neither"). Reset connection stays HTTP-only: it is the sign-in's button.
- Squawk 0371's lesson holds for the new case: after a Forget and a Test, the button must come back at rest, not armed.
- The editor's Server section is updated in place (squawk 0102): `mcp-server-info.js::update(cache)` runs after every Test's refetch and after a Forget (`update(null)`, which hides the section).

## Inputs
- Leg 1 landed in the working tree (uncommitted): the `protocol_fallback` key is written and deleted by `api.py`.
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-status.js`, `mcp-server-info.js`; `tests/browser/test_flow_studio_mcp_editor_status.py`, `test_flow_studio_mcp_editor_server_info.py`, `tests/browser/_mcp_editor.py`; `docs/ui-testid-registry.md`; `the_one/agents.md`; `scripts/ui_capture.py`.

## Outputs
- The button rule, the note, their tests, the documents and a re-captured `mcp-edit-stdio` surface, as listed under Files Affected.
- No change to any Python behaviour (one docstring in `api.py`), to `js/ui/*`, or to any control's catalogue row.

## Acceptance Criteria
- [ ] **AC1 (the rule).** `mcp-connection-status.js::updateButtons` shows "Forget tools list" for an HTTP server exactly as today, and also for a source with `type === 'stdio'` whose cache holds a tools list (`Array.isArray(cache.tools)`). It is not shown for a local-command server with no cache, or with a cache that holds only `last_check`. Reset connection is never shown for a local-command server.
- [ ] **AC2 (Forget on a local-command server).** On a local-command server with a seeded tools list: the button reads "Forget tools list", sits beside the status line, arms as "Forget tools list?", and on the second press sends `DELETE /api/mcp-sources/{id}/connection`. Then, with no remount of the editor (a marker on `.editor-title` survives): the button is hidden, the status line reads as not connected, the Server section is hidden, the Tools section shows its "Press Test…" hint, the message "Tools list forgotten" is shown, an unsaved edit in another field and the "Unsaved changes" caption survive, keyboard focus lands on Test, and the stored record has no `_cache`.
- [ ] **AC3 (back at rest after a Test).** After that Forget, a Test that connects brings the button back, labelled "Forget tools list" and not armed (no `confirm-delete` class): one press arms it and does not delete.
- [ ] **AC4 (the note is shown).** For a source whose cache holds `protocol_version` and `protocol_fallback: "no_answer"`, the Server section shows, after the facts and before the Instructions disclosure, one `App.ui.banner` with tone `warning`, role `note` and testid `mcp-server-protocol-fallback`, whose text is exactly: "This server did not answer the newer-protocol check in time, so this connection uses an older protocol and may offer fewer tools. Press Test again once the server has started." The Protocol row still shows the stored revision.
- [ ] **AC5 (the note is hidden).** The banner is hidden (present in the DOM, `hidden`) when the key is absent, when it holds any other value, and when the cache has no `protocol_version`. It can never show while the Server section itself is hidden.
- [ ] **AC6 (the note follows the record in place).** With the note shown: a Forget hides it with the section; a Test whose refetched record has no key hides it; a Test whose refetched record has the key shows it. None of these remounts the section (a marker on the section's element survives).
- [ ] **AC7 (the pinned predicate test).** `test_flow_studio_mcp_editor_status.py::test_reset_and_forget_predicates` is rewritten in place: its docstring no longer says "neither for stdio", and it gains a local-command case with a stored tools list (Forget shown, Reset not), a local-command case whose cache holds only `last_check` (neither), and keeps the uncached local-command case (neither). The HTTP cases are unchanged.
- [ ] **AC8 (nothing owned, nothing new).** The note uses `App.ui.banner` through its options only (`tone`, `role`, `text`, `testid`, `hidden`, and `show()` / `hide()`); no class owned by a `js/ui` control is written in the area module, no new control, no new CSS unless spacing inside the section needs one consumer class that no catalogue row owns. `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass.
- [ ] **AC9 (documents).** `docs/ui-testid-registry.md`: the `forget-mcp-connection-btn` row says it is also shown for a local-command server with a stored tools list, and a new row describes `mcp-server-protocol-fallback`. `the_one/agents.md`: the MCP editor notes state the new Forget rule, the note and its key, and the two accepted gaps of the flight's DD4 (a fallback in a chat shows no note until a Test; the agent Test route with per-agent credentials can store a shorter tool list with no note). `api.py::reset_mcp_connection`'s docstring no longer says the UI hides the action for stdio sources. The module header comments of the two JS files say what they now do.
- [ ] **AC10 (the capture).** `scripts/ui_capture.py`'s `mcp-edit-stdio` surface is captured in both themes, outside the repo, and shows "Forget tools list" beside the status line with nothing else moved; every selector that script uses on the MCP editor still resolves.
- [ ] **AC11 (gates).** Green: the lanes `mcp-connection`, `mcp`, `library`, `agents` and `agent-tabs` (`THE_ONE_TEST_NETNS=1`, one at a time); `THE_ONE_TEST_NETNS=1 make test-unit` with the expected skip count; `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- AC1, AC7: the rewritten predicate test.
- AC2: a new test beside `test_forget_tools_list_patches_in_place`, seeded with a local-command source and a cache (`_cache()` from `tests/browser/_mcp_editor.py`; confirm that `POST /api/mcp-sources` keeps a seeded `_cache` for a `stdio` source as it does for an HTTP one, and say so in the flight log). Read the stored record back through the authenticated `GET /api/mcp-sources/{id}` the file already uses.
- AC3: preferred, a real Test of a real local-command server, as `test_forget_then_test_brings_the_button_back_at_rest` does for HTTP with its `real_http_server` fixture: the stdio fixture is `python -m tests.fixtures.mcp.hello_server --stdio` run with the test process's interpreter (see how `scripts/ui_capture.py` seeds its connected local-command server and what sandbox settings it gives it). If a real local-command Test cannot be made reliable inside a browser test, intercept the Test request and the record refetch that follows it with Playwright routes instead, and say in the flight log which was used and why.
- AC4 to AC6: new tests in `test_flow_studio_mcp_editor_server_info.py` with seeded caches; for AC6's Test cases intercept the Test response and the refetch (no real slow server). Assert the banner by its testid, its `role` attribute, its exact text and its position relative to `mcp-server-facts` and `mcp-server-instructions`; assert "hidden" as not visible, with the element present.
- Falsification, each by editing the mechanism out, seeing the named test fail, and editing it back (report yes or no for each):
  1. the `stdio` branch of the rule removed → the AC2 test and the cached local-command case of AC7 fail;
  2. the banner's visibility left unset in `update` → an AC5 case fails;
  3. `Array.isArray(cache.tools)` loosened to "any cache" → the `last_check`-only case of AC7 fails.
- AC8: the five guard files, through `scripts/run-tests.sh`.
- AC10: `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <a folder under the home folder, outside the repo> …` for the one surface (see `--list`); look at the PNGs; delete the folder when done and say so.
- AC11: the lanes one at a time, never while another test run is on the host; then the unit tier; then the lint pair.

## Implementation Guidance

1. **Before editing, re-run the consumer search** recorded in the flight's Prerequisites (`forget-mcp-connection-btn`, `Forget tools list`, `neither for stdio`, `Tools list forgotten`, `mcp-server-facts`, `mcp-server-instructions`, in quoted and unquoted selector spellings, across `tests/`, `scripts/`, `docs/`, `evals/`, `tests/behavior/` and `the_one/`), and say in the flight log if anything new turned up since the Architect's list.

2. **The rule** (`mcp-connection-status.js::updateButtons`): add the local-command branch of AC1 beside the existing expression; keep the HTTP expression's text as it is. Update the module header comment. `runDelete` needs no change: its success path (clear the two sign-in flags, delete `config._cache`, empty the tools, `serverInfo.update(null)`, the message, focus to Test, and squawk 0371's `revert()`) is correct for a local-command source.

3. **The note** (`mcp-server-info.js`): build the banner once in `create`, hidden, and append it to `server.body` after `facts.el` and before `instructions.el`. In `update`, on the path that shows the section, set its visibility from `f.protocol && cache.protocol_fallback === 'no_answer'` on every call (read the key in `readInfo` with the other fields). The early return that hides the whole section needs no banner handling: a hidden section hides it. `cacheHasServerInfo` and `hasContent` do not change (the note never shows without a Protocol row). Update the module header comment.

4. **Tests** per Verification; the rewritten test keeps its place in the file. Then **documents** (AC9), the **capture** (AC10), the **gates** (AC11).

5. **Stop and report** rather than widen the leg if: the banner cannot be placed or toggled through its options without an owned class; `POST /api/mcp-sources` does not keep a seeded cache for a local-command source and no test seam does; or leg 1's key is not in the record the editor reads.

## Edge Cases
- **A local-command server tested with unsaved changes**: the Test writes the cache as today; the button follows the refetched record.
- **A Forget during a Test in flight**: the existing identity and latest-wins guards apply; nothing new.
- **The optimistic state after a Test** (`recordLocally` runs before the refetch): the note keeps its previous state for the moment until the refetch lands, then follows the record. Accepted; do not add a second source of truth.
- **A cache with the key and no tools list** (not written by any current path): the note follows the key and the Protocol row; the button follows the tools list. They are independent.
- **An HTTP server**: no stored key can exist for one after leg 1 (its writers delete it, and a type change drops it); the editor rule reads the cache only and needs no type check.
- **Consent sessions**: a local-command server has none, so the button is never disabled by the session hold.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-status.js` - the rule, header comment
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-info.js` - the banner, header comment
- `the_one/interfaces/web/api.py` - `reset_mcp_connection`'s docstring only
- `tests/browser/test_flow_studio_mcp_editor_status.py`, `tests/browser/test_flow_studio_mcp_editor_server_info.py`, `tests/browser/_mcp_editor.py` (a local-command seeding helper with a cache, if needed) - tests
- `docs/ui-testid-registry.md`, `the_one/agents.md` - documents
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md` - the leg's entry

## Citation Audit

Checked against the working tree at `c78cbb5c`. Leg 1 edits `api.py` and `the_one/agents.md`; the citations into those files were re-checked after leg 1 landed (2026-11-18, leg 1's changes uncommitted in the tree): `api.py::reset_mcp_connection`'s docstring still ends "but UI hides the affordance"; the stored key is `protocol_fallback` with the one value `"no_answer"`, written by `_build_and_test_stdio_mcp` through `_protocol_fallback_of(client)` and deleted by that writer, by the two HTTP writers and by `update_mcp_source`'s server-changed rule; `the_one/agents.md` names the key once, in the negotiation paragraph, and says nothing yet about the editor.

- `mcp-connection-status.js::updateButtons` - `forget = !!(source && source.type === 'streamable-http' && source.oauth_active !== true && cache && (cache.auth_posture || cache.tools))`; `reset = hasOAuthState(source)`, which requires `type === 'streamable-http'` - verified
- `mcp-connection-status.js::runDelete` - `DELETE …/connection`; on success `revert()`, flags cleared, `delete s.config._cache`, `emptyTools()`, `render()`, `serverInfo.update(null)`, `App.ui.flash(doneText)`, focus restored to Test - verified
- `mcp-connection-status.js::syncFromServer` - after a Test, refetches the record, `applyServerState`, `render()`, `serverInfo.update(cacheOf(source))` - verified
- `mcp-server-info.js::create` - appends to `server.body` in order: identity, `facts.el`, `instructions.el`, `meta.el`; optional parts are built once and toggled with `hidden` - verified
- `mcp-server-info.js::update` - returns early with the section hidden when `hasContent` is false; otherwise sets the rows and each optional part's `hidden` - verified
- `mcp-server-info.js::readInfo` - `protocol: cache.protocol_version || ''` - verified
- `the_one/interfaces/web/static/js/ui/page.js::App.ui.banner` - options `tone` (`info`, `warning`, `error`), `role` (`note` default, `status`, `alert`), `text`, `hidden`, `testid`; returns `{el, set, setChildren, show, hide}` - verified
- `tests/browser/test_flow_studio_mcp_editor_status.py::test_reset_and_forget_predicates` - cases `oauth`, `cached`, `posture`, `bare`, `stdio`; the `stdio` case uses `_seed_stdio`, which seeds no cache - verified
- `tests/browser/_mcp_editor.py::_cache`, `::_seed_state`, `::_seed_stdio` - `_seed_state` puts `_cache` into an HTTP source's config through `POST /api/mcp-sources`; `_seed_stdio` seeds `{"command": "echo", "env": {}}` with no cache - verified (that the POST keeps a cache for a `stdio` source is for the Developer to confirm)
- `api.py::reset_mcp_connection` - no type check; docstring "stdio sources have no OAuth state; calling on a stdio source is harmless (zero keys match) but UI hides the affordance" - verified at `c78cbb5c`; re-check after leg 1
- `scripts/ui_capture.py` - surface `mcp-edit-stdio` ("connected stdio"), prepared by `_mcp_ready` - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
