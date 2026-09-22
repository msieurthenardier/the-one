# Leg: knowledge-inventory

**Status**: landed
**Flight**: [Studio Surfaces](../flight.md)

## Objective

Replace Studio's Knowledge stub with the global knowledge-base inventory — create
and delete a knowledge base, register a folder, and inspect one down to
individual chunks and source text — and add the operator-facing search route
(DD-6) that makes the inventory a non-agent consumer of Flight 5's hybrid
retrieval.

## Context

**Design decisions this leg implements**: DD-2 (the Knowledge section is the
global inventory), DD-6 (`GET /api/knowledge-bases/{kb_id}/search`), DD-7's
read-only sibling is *not* here (Leg 3), DD-8 (source fetched on demand only),
DD-9 (standalone-inside-folder badge via `parent_id`), DD-10 (the registration
form renders refusal reasons), DD-16 (advisory name-length hint at 43 code
points; empty name refused), and the `folders[].watch` / `watch_error` rendering
carried from Flight 4 (recon R5).

**Explicitly NOT in this leg**:

- **Rename.** DD-5's argument is that the flight adding rename owns its
  consequence, so the affordance ships in Leg 2 beside the `disabled_tools`
  rewrite. Do not add a name-edit control here — a knowledge base is created
  and deleted in this leg, not renamed.
- The per-agent Knowledge tab, `kb_ids`, `disabled_tools`, and
  `_compute_tool_names` (all Leg 2).
- The Administration settings panel (Leg 3).

**Prior-leg learnings**: none — this is the flight's first leg. The flight log's
Reconnaissance Report is the ground truth for what each carried item actually
requires; R18 in particular records that `retrieval.search` has no HTTP entry
point at all, which is why DD-6 exists.

**Environment**: host-native. Any manual check runs against a dedicated dev
instance (`THE_ONE_PORT=8485` with a scratch `THE_ONE_DATA_DIR`), never port
8484 and never the operator's default data dir. Source edits need
`make restart` — there is no hot reload.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js` —
  `renderKnowledgeStub(container)`, a `.page-header` plus one
  `.empty-canvas` one-liner carrying `data-testid="studio-knowledge-stub"`.
- `the_one/interfaces/web/static/js/areas/studio.js::renderKnowledgeSection` —
  clears `sectionContentEl` and calls `App.studio.renderKnowledgeStub`.
- Every knowledge-base route this leg consumes, shipped and tested:
  `GET`/`POST /api/knowledge-bases`, `DELETE /api/knowledge-bases/{kb_id}`,
  `GET`/`POST /api/knowledge-bases/{kb_id}/items`,
  `POST /api/knowledge-bases/{kb_id}/items/{item_id}/retry`,
  `DELETE .../items/{item_id}`, `GET .../status`, `POST .../reindex`,
  `GET .../items/{item_id}/chunks`, `GET .../items/{item_id}/source`.
- `the_one/knowledge/retrieval.py::search` — keyword-only `chunk_repo`,
  `item_repo`, `store`, `backend`; returns `SearchResult(hits, degraded)`.
- `api.py` helpers `_kb_repo()`, `_kb_item_repo()`, `_kb_chunk_repo()`,
  `_vector_store()`; `the_one/knowledge/tool.py` shows the full wiring
  including `await asyncio.to_thread(get_embedding_backend)`.
- `docs/ui-testid-registry.md` carries a `studio-knowledge-stub` row.
- Eight browser-test assertions across three files key off `studio-knowledge-stub` (see Edge Cases).

## Outputs

- `static/js/areas/studio/knowledge-section.js` — NEW. The inventory (grid +
  detail). `stub-knowledge.js` is **deleted**, and its `<script>` tag in
  `static/index.html` replaced in place so load order is unchanged.
- `static/js/areas/studio.js` — `renderKnowledgeSection` becomes a real
  section: fetch wrapper, section-local cache, stale-then guards, detail
  routing, poll lifecycle.
- `static/css/studio.css` (or `components.css` where the vocabulary is already
  canonical) — styles for the new rows/badges.
- `the_one/interfaces/web/api.py` — `GET /api/knowledge-bases/{kb_id}/search`.
- `docs/ui-testid-registry.md` — `studio-knowledge-stub` row removed, new rows
  added.
- `tests/test_ui_guards.py` — `areas/studio/stub-knowledge.js` baseline entry
  pruned (the file is gone).
- `tests/browser/test_flow_studio_knowledge_inventory.py` — NEW (`studio` lane).
- `tests/browser/test_flow_studio_navigation.py`,
  `tests/browser/test_flow_hash_routing.py`,
  `tests/browser/test_flow_dirty_confirm.py` — re-pointed off the stub testid.
- `tests/test_db_api.py` (the module that already covers the knowledge-base routes) —
  unit coverage for the search route.

## Leg Design Decisions

**L1-D1 — The section mirrors the MCP Servers section's two-branch shape.**
A grid branch (`renderKnowledgeSection` with no selection) and a detail branch
(one knowledge base selected), with hash sub-routing `#studio/knowledge` and
`#studio/knowledge/{kb_id}`, exactly as `mcp-sources` does. Rationale: DD-2's
whole argument is that the operator meets one mental model twice; the routing,
stale-then guards and `serializeState`/`hydrateState` handling already exist in
pattern form in `studio.js::renderMcpSourcesSection` / `fetchMcpSources_`.

**L1-D2 — The detail view polls `GET .../status` every 5 seconds while
mounted.** This is a requirement, not a nicety: `kb-studio-round-trip` step 8
asserts that a file added on disk is "reflected in the inventory **without any
operator action in the UI**", so a refresh button alone fails the spec. Rules:

- One module-scoped timer handle; every mount clears the previous handle before
  setting a new one, so re-renders cannot stack timers.
- Cleared at **three named sites**, not "on teardown" in the abstract:
  1. **`studio.js::setActiveSection`** — a `prevSection === 'knowledge' &&
     section !== 'knowledge'` reset block, mirroring the existing `mcp-sources`
     and `connectors` blocks immediately above it. That block **also clears the
     detail-view selection**, so re-entering `#studio/knowledge` mounts the grid
     — the same contract those two sections already have, and the one the
     navigation tests' round-trip assertions expect.
  2. **`studio.js::deactivate`** (currently `function () {}`) — `app.js`'s
     `performCrossAreaSwitch` calls it on *every* cross-area transition, so
     without this, opening a detail view and clicking Chat leaves the 5-second
     timer running for the life of the page. **This leg is the first to need
     `deactivate()` filled in**; every prior Studio section issues one-shot
     fetches, not intervals. Note the in-file warning at the `beforeunload`
     registration: it forbids *removing the beforeunload listener* in
     `deactivate()` — it does not forbid giving `deactivate()` a body. Keep the
     listener registered; add only the poll-clear.
  3. Navigating from the detail view back to the grid.
- Each response passes a stale-then guard (`self._activeSection !== 'knowledge'`
  or the selected id changed → discard) before touching the DOM, mirroring
  `fetchMcpSources_`.
- A failed poll leaves the last rendered state and does not blank the view; a
  run of failures is not escalated to a flash (the operator is looking at it).
- Precedent for the lifecycle discipline:
  `mcp-server-editor.js` (`pollTimer` / `cleanup()` / state guard). That poll is
  bounded by an attempt cap because it awaits a one-shot event; this one is
  bounded by mount lifetime instead, which is why the clear-on-unmount rule is
  stated explicitly rather than inherited.

**Cache declaration** (required risk check): source of truth is the API. The
section-local knowledge-base list rebuilds on section mount and after create or
delete. The detail view's status rebuilds on mount and on the 5-second poll;
maximum staleness visible to the operator is one poll interval. Items, chunks
and source text are **not** cached — each is fetched at the moment it is
displayed.

**L1-D3 — No new dynamic HTML sinks.** `tests/test_ui_guards.py` freezes the
`innerHTML`/`outerHTML`/`insertAdjacentHTML` baseline and **fails on any new
dynamic site**; only a single string literal (including `= ''`) is exempt. So
the static chrome may be assigned as one literal template, and **every value
derived from data — names, paths, statuses, errors, chunk text, search hits —
must be built with `createElement` + `textContent` + `setAttribute`**. The
obvious precedent to copy, `mcp-servers-grid.js`, is wall-to-wall dynamic
`innerHTML` and is grandfathered into the baseline; copying its style will fail
the guard.

`tests/test_ui_guards.py` enforces **seven** separate invariants, and this leg
can trip all seven — a Developer who reads only the sink rule will still fail
`make test-unit`. The full set in scope:

| Guard | What it fails on | Where this leg meets it |
|---|---|---|
| dynamic-sink freeze | any NEW concatenated `innerHTML`/`outerHTML`/`insertAdjacentHTML` site | the whole new render module |
| testid registry sync | a testid in the sources with no `docs/ui-testid-registry.md` row, **or the reverse** | every new id; the retired stub row |
| backtick tripwire | a backtick-quoted `data-testid`, or a template literal feeding an HTML sink | keep the ES5 IIFE `window.App.studio.*` shape every sibling uses |
| `find_label_for_without_control` | a `<label for="X">` with no `id="X"` in the same file | **AC-2's name field and AC-6's folder-path field** |
| `find_invalid_describedby_without_field_error` | an `.is-invalid` control whose `aria-describedby` names no real `.field-error` id | **AC-2's length hint and AC-6's refusal messages**, if rendered as field errors |
| `find_banned_css_vocabulary` | retired class/token vocabulary, scanned line-by-line, comments included | the new `studio.css` / `components.css` rules |
| `find_js_dead_css_var_refs` | a `var(--x)` named in a JS string with no definition in `tokens.css`/`fonts.css` | class and style strings in the new render module |

The last three are the easy ones to miss: the leg adds its first *forms*, and
the project wires `.field-group` / `.field-error` / `aria-describedby` by hand
at every site. Build the two forms against an existing `.field-group` consumer
as the template rather than from scratch.

**L1-D4 — Source text is fetched only when the operator asks for it.** DD-8:
`get_kb_item_source` re-reads and re-extracts from disk on every call, so it is
behind an explicit per-item control and is never fetched while rendering a list.
Chunks (`GET .../chunks`, paged, `seq` order) are likewise on demand.

**L1-D5 — `studio-knowledge-stub` is retired, not repurposed.** The new
inventory root carries `data-testid="studio-knowledge-inventory"`, and the
**eight** existing browser assertions (across three files) that used the stub as
a "the Knowledge section rendered" marker are re-pointed at it in this leg. Rationale: those tests assert
navigation and dirty-confirm behaviour, not stub content — re-pointing preserves
their intent, while leaving the old id alive on a real surface would be a lie.
The `docs/ui-testid-registry.md` row moves with it; the guard diffs the registry
against the sources in **both** directions, so a missed row fails the unit gate.

## Acceptance Criteria

- [x] AC-1 — Studio's Knowledge section renders a real inventory: a page header,
      an always-visible "New knowledge base" CTA, and either a list of knowledge
      bases or an empty state. The string "in a future mission" appears nowhere
      in the rendered section, and `data-testid="studio-knowledge-stub"` is
      absent from the codebase.
- [x] AC-2 — A knowledge base can be created from the section and appears in the
      list without a page reload. The name field shows an **advisory** hint when
      the name exceeds **43 code points** (counted as `[...name].length`, not
      `name.length`), and creation still succeeds; an **empty** name is refused
      client-side and no request is sent.
- [x] AC-3 — A knowledge base can be deleted from the section behind the
      project's existing confirm affordance, and disappears from the list.
- [x] AC-4 — Selecting a knowledge base opens a detail view addressable at
      `#studio/knowledge/{kb_id}`; a full page load of that URL lands directly on
      it, and navigating back reaches `#studio/knowledge`.
- [x] AC-5 — The detail view renders, from `GET .../status`: the per-status file
      item counts, the chunk count, the indexer state word, and one row per
      registered folder carrying its path, walk `status`, `indexed_at`, `error`,
      **`watch`** and **`watch_error`**. All four watch state words the watch
      manager can report — `off`, `starting`, `watching`, `unavailable`
      (`knowledge/watcher.py`) — are rendered as the API reports them.
      `unavailable` requires a real notifier failure and need not be reached
      live by the browser test: a unit-level assertion over the four-word
      mapping is acceptable evidence for that one, with the browser test
      covering the states a fixture folder actually reaches.
- [x] AC-6 — A folder can be registered from the detail view. Each refusal the
      route can return renders its `detail` message to the operator rather than
      a bare status code: 422 non-existent/not-a-directory, 422 filesystem root,
      422 data-directory overlap, 409 overlap with an already-registered folder,
      422 body validation. (DD-10)
- [x] AC-7 — The item list renders every item with its `status` and, for a
      `failed` item, its `error` text visible in the UI. A `file` item whose
      `parent_id` is null but whose path lies inside a registered folder carries
      a visible "standalone" badge. (DD-9) The containment test is
      **separator-aware**: a bare `itemPath.startsWith(folderPath)` is wrong at
      directory boundaries (folder `/data/foo` would falsely claim item
      `/data/foobar/x.txt`). Compare either on split path segments, or as
      `itemPath === folderPath || itemPath.startsWith(folderPath + sep)` with
      `sep` taken from the folder path's own separator — the server stores
      `str(canonical)` in OS-native form with no guaranteed trailing separator,
      and item paths come from the walker independently.
- [x] AC-8 — An item's chunks can be opened and render in `seq` order; its
      source text can be opened separately. Neither is requested while rendering
      the item list — the source request is issued only on the operator's
      explicit action. (DD-8)
- [x] AC-9 — Re-index can be triggered at both scopes (`changed` and `all`) and
      the resulting indexer state is visible in the detail view. The `reindex`
      response carries only `{"scope", "requeued"}` and no indexer state, so the
      view issues **one immediate `GET .../status` when the POST resolves**
      rather than leaving up to a full poll interval of visible lag.
- [x] AC-10 — `GET /api/knowledge-bases/{kb_id}/search` exists and returns
      `{"hits": [...], "degraded": str | null, "indexer": str}`. `q` is
      `Query(..., min_length=1)` — **omitted or empty is 422**; `limit` is
      `Query(10, ge=1, le=20)`; an unknown `kb_id` is 404. A **whitespace-only**
      `q` passes the route bound and falls through to `retrieval.search`'s
      documented no-op (`stripped = query.strip(); if not stripped: return
      SearchResult(hits=[], degraded=None)`) — a 200 with zero hits. That split
      is deliberate and both halves are asserted: the route rejects the
      malformed request, and a real query that matches nothing is not an error. Each hit carries the fields of `SearchHit` including `score`. The
      route renders **no per-hit provenance** and `SearchHit` is **not** widened.
- [x] AC-11 — `get_embedding_backend()` is resolved under `asyncio.to_thread`
      in the new route, as `knowledge/tool.py` does.
- [x] AC-12 — The detail view has a search control that renders the returned
      hits with their `score`, and — when `degraded` is non-null — a single line
      naming the degrade cause **alongside the `indexer` state word** from the
      same response.
- [x] AC-13 — The detail view refreshes its status **without operator action**:
      a file added to a registered folder on disk becomes visible in the open
      detail view within one poll interval of the backend reflecting it. The
      poll timer is cleared on navigating away and cannot stack across
      re-renders. (L1-D2)
- [x] AC-13b — With a detail view open and polling, **navigating to another
      Studio section and to another area entirely (Chat) each stop the poll**.
      Asserted by observing that no further `GET .../status` request is issued
      after the transition. Re-entering `#studio/knowledge` mounts the grid, not
      the previously-selected detail view.
- [x] AC-14 — `make test-unit` is green. `tests/test_ui_guards.py` passes with
      **no new dynamic-sink entries added to `DYNAMIC_SINK_BASELINE`**, and
      `docs/ui-testid-registry.md` matches the sources in both directions.
- [x] AC-15 — The `studio` browser lane is green, including a new
      `tests/browser/test_flow_studio_knowledge_inventory.py` and the three
      re-pointed existing files.

## Verification Steps

- AC-1, AC-2, AC-3, AC-4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  --lane studio -x` — the new browser test drives create → list → select →
  delete and asserts the hint's advisory outcome (over-length name is created).
  Plus `grep -rn "studio-knowledge-stub" the_one/ tests/ docs/` returns nothing.
- AC-5, AC-7, AC-9, AC-12, AC-13: the same browser test against a seeded
  knowledge base; AC-13 asserts the polled update with no UI interaction between
  the backend change and the assertion.
- AC-6: browser test drives the data-directory refusal (the deterministic case —
  the instance's own scratch data dir) and asserts the rendered message names
  the application data directory. **Never `$HOME`**: the guard refuses only
  overlap with `settings.data_dir`, so registering `$HOME` against a scratch
  data dir returns 201 and walks the operator's whole home directory.
- AC-8: browser test opens chunks and asserts `seq` order; asserts no request to
  `/source` is issued during item-list render (route-level assertion via
  Playwright request interception).
- AC-10, AC-11: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_db_api.py -x --timeout 30` — unit tests for the happy path,
  missing `q`, **empty `q` → 422**, **whitespace-only `q` → 200 with zero
  hits**, `limit` at 0 and at 21 → 422, and unknown `kb_id` → 404.
- AC-13b: browser test using `page.on("request", ...)` to collect `/status`
  request URLs, asserting the count stops growing after **each** transition —
  the cross-section one (Knowledge detail → MCP Servers) and the cross-area one
  (Knowledge detail → Chat). These exercise the two disjoint clear sites: a
  same-area section change never calls `deactivate()`, and a cross-area switch
  never runs `setActiveSection`'s reset block, so a test covering only one of
  them passes with the other site missing. Reuse the interception pattern in
  `tests/browser/test_flow_studio_tools_overrides.py::test_studio_override_panel_lazy_loads_schema`
  (collect into a list on `page.on("request")`, then assert the length). Wait
  **longer than one poll interval** (>5s) after the transition before asserting,
  or the assertion passes vacuously on timing rather than on the clear.
- AC-14: `make test-unit` verbatim, alone, in the foreground.
- AC-15: `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio`.

## Implementation Guidance

1. **Add the search route first** (`api.py`, beside the other knowledge-base
   routes). Copy the dependency wiring from `the_one/knowledge/tool.py`:
   `_kb_chunk_repo()`, `_kb_item_repo()`, `await _vector_store()`, and
   `backend = await asyncio.to_thread(get_embedding_backend)`. 404 the unknown
   `kb_id` through `_kb_repo().get` exactly as `get_kb_status` does. Return
   `{"hits": [dataclasses.asdict(h) for h in result.hits], "degraded":
   result.degraded, "indexer": manager.state(kb_id) if manager else "idle"}` —
   reusing `get_indexing_manager()` the same way `get_kb_status` does.
   `SearchHit` is a frozen dataclass, and **`dataclasses` is not currently
   imported in `api.py`** — add the import. Land its unit tests in the same
   pass: happy path, missing `q`, empty `q` → 422, whitespace-only `q` → 200
   with zero hits, `limit` at 0 and at 21 → 422, unknown `kb_id` → 404.

2. **Write `knowledge-section.js`** as an ES5 IIFE exporting
   `App.studio.renderKnowledgeGrid(container, kbs, callbacks)` and
   `App.studio.renderKnowledgeDetail(container, kb, state, callbacks)`.
   Static chrome may be one string-literal `innerHTML`; everything data-derived
   is `createElement`/`textContent` (L1-D3). Give each new testid a registry row
   as you add it, not at the end.

3. **Rewire `studio.js::renderKnowledgeSection`** along the
   `renderMcpSourcesSection` / `fetchMcpSources_` / `populateMcpSourcesGrid`
   shape: a section-local list, a fetch wrapper with a stale-then guard, a
   selection function that calls `App.router.replaceSub(self.serializeState())`,
   and `serializeState`/`hydrateState` handling for `knowledge/{kb_id}`.

4. **Add the poll** per L1-D2 — single handle, cleared before every set, and
   cleared at all three named sites: the new `prevSection === 'knowledge'` reset
   block in `setActiveSection` (which also clears the detail selection), the
   body you give `studio.js::deactivate`, and the return-to-grid path. Verify by
   navigating Knowledge-detail → Chat and confirming the `/status` requests stop.

5. **Delete `stub-knowledge.js`**, swap its `<script>` tag in
   `static/index.html` for `knowledge-section.js` at the same position, prune
   its `DYNAMIC_SINK_BASELINE` entry, and re-point the five browser assertions.

6. **Run the gates**: `make lint`, the targeted unit file, then `make test-unit`
   verbatim, then the `studio` lane. Record counts and timings in the flight log.

## Edge Cases

- **Seven of the eight stub-testid consumers are pure navigation/visibility
  assertions** — `test_flow_studio_navigation.py` (5), `test_flow_hash_routing.py`
  (2), `test_flow_dirty_confirm.py` (1). Those seven need only a stable
  "Knowledge section rendered" marker. Re-point, do not delete: deleting them
  would drop real navigation coverage.
- **The eighth is not, and a mechanical testid swap leaves it permanently red.**
  `test_flow_studio_navigation.py::test_studio_click_knowledge_section` asserts
  `expect(stub).to_have_text(KNOWLEDGE_TEXT)`, where the module-level constant
  `KNOWLEDGE_TEXT` is *exactly* the stub sentence AC-1 requires be absent from
  the codebase. Re-pointing its selector alone yields an assertion that can
  never pass. **Delete that content assertion** (the surrounding
  hash/`aria-current` assertions are the test's real subject and stay), and
  **delete the now-unused `KNOWLEDGE_TEXT` constant** — leaving it would
  reintroduce the forbidden string and fail AC-1's grep.
- **Class-string assertions sit right beside two of them.**
  `test_flow_studio_navigation.py::test_studio_section_round_trip_returns_to_agent_listing`
  pins `.studio-editor` to the literal class string `"studio-editor is-hidden"`,
  and `::test_studio_editor_hidden_on_knowledge_section` navigates straight to
  `#studio/knowledge` and pins the same string. Do not change the section
  container's class plumbing while re-pointing the testid, and keep
  `#studio/knowledge` (no id) rendering the grid branch — L1-D1's new
  `#studio/knowledge/{kb_id}` form is additive.
- **Registering a folder fails with 409 against an overlapping folder**, which
  the route distinguishes from the 422s. Render the message, not the code.
- **An unsupported file extension never becomes an item** (`walk.py` filters it
  with `continue`, "by-design filter — never counted"). The inventory therefore
  cannot show it as skipped, and must not imply it can — that is recon R8,
  deferred to the closing flight.
- **An indexing manager may be absent** (tests without one injected):
  `get_kb_status` already degrades to `"idle"` / `"off"`, and the search route
  must degrade the same way rather than assuming a manager exists.
- **The status route excludes folders from `items` counts** by design, so a
  registered folder must never be rendered as a document.
- **Empty knowledge base, empty folder, zero chunks** — each renders an empty
  state rather than a broken table.
- **The two new forms are deliberately NOT wired into the dirty-confirm
  machinery — stated as a non-goal, not an oversight.**
  `studio.js::_confirmLeaveImpl`'s `inEditor` predicate covers
  `agents` + `_selectedAgent`, `mcp-sources` + `mcpSourceFormMode`, and
  `connectors` + `connectorFormMode`; nothing for `knowledge`. So unsaved text
  in the create-knowledge-base field or the folder-path field is discarded on
  navigation with no confirm dialog. Accepted: both are single-field forms that
  submit immediately and hold no accumulated work, unlike the agent and MCP
  source editors the dialog exists for. Widening that predicate would extend the
  confirm-dialog surface that `test_flow_dirty_confirm.py` pins — a file this
  leg already touches — and is not worth it for two single fields in a mission's
  last flight. Do not add `knowledge` to `inEditor`.
- **A knowledge base deleted while its detail view is open** (another tab, or
  the poll racing a delete): the poll's 404 must return the operator to the grid
  rather than leaving a dead view or looping on the error.

## Files Affected

- `the_one/interfaces/web/api.py` — new search route.
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js` — NEW.
- `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js` — DELETED.
- `the_one/interfaces/web/static/js/areas/studio.js` — section rewiring, routing, poll.
- `the_one/interfaces/web/static/index.html` — script tag swap.
- `the_one/interfaces/web/static/css/studio.css` / `components.css` — new styles.
- `docs/ui-testid-registry.md` — testid rows.
- `tests/test_ui_guards.py` — baseline prune.
- `tests/browser/test_flow_studio_knowledge_inventory.py` — NEW.
- `tests/browser/test_flow_studio_navigation.py`, `test_flow_hash_routing.py`,
  `test_flow_dirty_confirm.py` — re-pointed assertions.
- `tests/test_db_api.py` — search-route unit tests.

## Citation Audit

Every citation above verified against the working tree at `d3c122b`
(`flight/06-studio-surfaces`, cut from `mission/24-knowledge-bases`; no source
commits since). Squawk 0079 records that the leg template lacks this section —
it is included here regardless, per the flight-level precedent.

| Citation | Status |
|---|---|
| `static/js/areas/studio/stub-knowledge.js::renderKnowledgeStub` — `.page-header` + `h1` + one `.empty-canvas` carrying `data-testid="studio-knowledge-stub"`; fetches nothing | verified |
| `static/js/areas/studio.js::renderKnowledgeSection` — clears `sectionContentEl`, calls `App.studio.renderKnowledgeStub` | verified |
| `static/js/areas/studio.js::renderMcpSourcesSection` / `fetchMcpSources_` / `populateMcpSourcesGrid` — grid-vs-editor branch, section-local cache, `self._activeSection !== 'mcp-sources'` stale-then guard, `.admin-loading` failure line (L1-D1's precedent) | verified |
| `static/js/areas/studio/mcp-servers-grid.js` — builds every tile via concatenated `innerHTML` with `escapeHtml`/`escapeAttr`; grandfathered in `DYNAMIC_SINK_BASELINE` (L1-D3's "do not copy this style") | verified |
| `tests/test_ui_guards.py` docstring + `DYNAMIC_SINK_BASELINE` — fails on any **new** dynamic sink, snippet-level per file; a single string literal (incl. `= ''`) is exempt; removing a site does not fail; `"areas/studio/stub-knowledge.js"` is a live baseline key | verified |
| `tests/_ui_guard_helpers.py::classify_sinks` — static iff `_SINGLE_STRING_LITERAL` matches the whole RHS / payload | verified |
| `tests/_ui_guard_helpers.py::find_backtick_tripwire_hits` — bans backtick-quoted `data-testid` and backtick payloads feeding an HTML sink | verified |
| `docs/ui-testid-registry.md` — carries `studio-knowledge-stub` (line 173) and `agent-knowledge-tab-stub` (line 33); the guard diffs registry↔sources in both directions | verified |
| `tests/browser/test_flow_studio_navigation.py` (5), `test_flow_hash_routing.py` (2), `test_flow_dirty_confirm.py` (1) — eight `studio-knowledge-stub` assertions | verified |
| `tests/browser/test_flow_studio_navigation.py::test_studio_section_round_trip_returns_to_agent_listing` and `::test_studio_editor_hidden_on_knowledge_section` — both pin the literal class string `"studio-editor is-hidden"`; the latter navigates to `#studio/knowledge` | verified |
| `static/js/areas/studio/mcp-server-editor.js` — `pollTimer` + `cleanup()` + `state === 'DONE'` guard; bounded by `maxPollAttempts`, not by mount lifetime (L1-D2's precedent and the difference from it) | verified |
| `interfaces/web/api.py::get_kb_status` — returns `items` (file-typed only), `folders[]` with `id`/`path`/`status`/`indexed_at`/`error`/`watch`/`watch_error`, `chunks`, `indexer`; degrades to `"off"`/`"idle"` with no manager installed | verified |
| `interfaces/web/api.py::create_kb_item` — folder guard order is existence → filesystem root → data-dir overlap (422 each) → overlap with a registered folder (409); each raises an `HTTPException` with a prose `detail` (AC-6) | verified |
| `interfaces/web/api.py::create_kb_item` — the data-dir guard is `is_within(settings.data_dir, canonical) or is_within(canonical, settings.data_dir)`, so `$HOME` is **not** refused against a scratch data dir | verified |
| `interfaces/web/api.py::get_kb_item_source` — re-reads and re-extracts from disk per call; 422 for non-`file` items and missing extractors, 413 over `MAX_FILE_BYTES` (DD-8, AC-8) | verified |
| `interfaces/web/api.py::get_kb_item_chunks` — paged `offset`/`limit`, `seq` order, cross-KB item reads as 404 | verified |
| `interfaces/web/api.py::reindex_knowledge_base` — `scope` is `Literal["changed","all"]`, 202, returns `{"scope", "requeued"}` | verified |
| `interfaces/web/api.py::list_kb_items` — full `model_dump()` per item, `parent_id` included (DD-9's read path) | verified |
| `interfaces/web/api.py` — `_kb_repo()`, `_kb_item_repo()`, `_kb_chunk_repo()`, `_vector_store()` helpers exist in-module (AC-10 wiring) | verified |
| `knowledge/tool.py` — `backend = await asyncio.to_thread(get_embedding_backend)`; `store = await get_vector_store()` (AC-11) | verified |
| `knowledge/retrieval.py::search` — keyword-only `chunk_repo`/`item_repo`/`store`/`backend`, returns `SearchResult(hits, degraded)`; `SearchHit` carries `chunk_id, item_id, path, seq, char_start, char_end, text, score` and no membership fields | verified at flight level (`d3c122b`) |
| `knowledge/walk.py` — an unsupported suffix is skipped with `continue` and never becomes an item ("by-design filter — never counted") | verified at flight level (`d3c122b`) |
| `tests/test_db_api.py` — the module carrying the existing `/knowledge-bases` route tests (`grep -rln "knowledge-bases" tests/*.py` returns it alone) | verified |
| `static/js/app.js` — exports `escapeHtml` / `escapeAttr`; `App.icon` is the shared icon helper | verified |
| `static/index.html` — `<script src="/static/js/areas/studio/stub-knowledge.js">` at line 48, between the chat modules and `studio.js` | verified |
| `static/js/areas/studio.js::deactivate` — `function () {}`, a live no-op; `app.js::performCrossAreaSwitch` calls `areas[currentId].deactivate()` on every cross-area transition (L1-D2 site 2) | verified, cycle 1 |
| `static/js/areas/studio.js::setActiveSection` — carries `prevSection === 'mcp-sources'` and `prevSection === 'connectors'` reset blocks that null out section-local state; **no `knowledge` block exists** (L1-D2 site 1) | verified, cycle 1 |
| `static/js/areas/studio.js` — the `beforeunload` comment forbids *removing the listener* in `deactivate()`; it does not forbid giving `deactivate()` a body (L1-D2's safety note) | verified, cycle 1 |
| `tests/browser/test_flow_studio_navigation.py::test_studio_click_knowledge_section` — asserts `to_have_text(KNOWLEDGE_TEXT)`; `KNOWLEDGE_TEXT` (module level) is the exact stub sentence AC-1 requires be absent (the eighth consumer is not a pure visibility check) | verified, cycle 1 |
| `knowledge/watcher.py::WatchManager.state` — returns `"off"` for an unknown folder; entries take `"starting"`, `"watching"`, `"unavailable"` (AC-5's four words) | verified, cycle 1 |
| `knowledge/retrieval.py::search` — `stripped = query.strip(); if not stripped: return SearchResult(hits=[], degraded=None)` — an empty/whitespace query is a documented 200 no-op, not an error (AC-10's split) | verified, cycle 1 |
| `knowledge/retrieval.py::SearchHit` — `@dataclasses.dataclass(frozen=True)`, so `dataclasses.asdict` is the correct serialization | verified, cycle 1 |
| `interfaces/web/api.py` — **`dataclasses` is not imported**; the module imports `asyncio, contextlib, hashlib, json, logging, os, re, time, uuid` (step 1's added import) | verified, cycle 1 |
| `tests/_ui_guard_helpers.py` — exports `find_label_for_without_control`, `find_invalid_describedby_without_field_error`, `find_banned_css_vocabulary`, `find_js_dead_css_var_refs` alongside the sink and testid guards (L1-D3's seven-guard table) | verified, cycle 1 |
| `tests/browser/test_flow_studio_tools_overrides.py::test_studio_override_panel_lazy_loads_schema` — collects request URLs via `page.on("request", ...)` and asserts `len(requests_seen) == 1`; the in-project precedent AC-13b reuses | verified, cycle 2 |
| `static/js/areas/studio.js::_confirmLeaveImpl` — `inEditor` is `agents && _selectedAgent`, `mcp-sources && mcpSourceFormMode`, `connectors && connectorFormMode`; **no `knowledge` arm** (the dirty-tracking non-goal) | verified, cycle 2 |
| `static/js/app.js::performCrossAreaSwitch` — calls `deactivate()` only on cross-**area** transitions; a same-area section change routes through `hydrateState` → `setActiveSection` and never calls it (why L1-D2's sites 1 and 2 are disjoint, not redundant) | verified, cycle 2 |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`; `--lane studio`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director commits at flight end)
- [x] Do NOT commit — the flight defers review and commit to Phase 2d
