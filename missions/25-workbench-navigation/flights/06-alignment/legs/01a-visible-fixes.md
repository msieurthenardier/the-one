# Leg: visible-fixes

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

Fix the operator-visible defects confirmed by reconnaissance, and the one the operator
found at planning, so the walk (leg 4) starts on a clean surface:
- the create routes' 500s (squawks 0112 and 0081);
- two sets of unnamed controls (0113 and 0114);
- the Settings tile title row (0116);
- the unlabelled sidebar before the router runs (A5);
- the missing page `h1` at the Agents and Library roots;
- the provider Models list that reads like a picker (DD10).

Focus after an in-place action (DD2) is its own leg, 1b.

## Context

- **The flight's design decisions are the contract:** DD3 (the tile title row), DD4 (the
  422s and their display), DD10 (the Models list label) and DD11 (the root `h1`). Read
  them in `flight.md`.
- **The reconnaissance** (flight log) confirmed every item live on `main` at `aaee705`.
  The Architect's review corrected the citations: 0114 has six sites, and 0081 duplicates
  and widens 0112.
- **Leg split (2026-10-06).** The flight's `visible-fixes` leg is split. This leg (1a)
  holds the independent fixes. Leg 1b (`focus-after-action`, DD2) changes focus across
  six editors and gets its own design review. Leg 1b runs after this one, and both touch
  `provider-editor.js`, so they run in sequence, not in parallel.
- **The completion rule for squawks.** Each squawk this leg fixes gets its Corrective
  Action and Verification written into its file, with status `completed`. The commit
  reference is added at the flight's legs 1–3 commit.

## Inputs

- `main` at `aaee705` plus the planning commit `07ed2c4`, on branch `flight/06-alignment`.
- Squawk files: `squawks/0081-*.md`, `0112-*.md`, `0113-*.md`, `0114-*.md`, `0116-*.md`.

## Outputs and acceptance criteria

- [ ] **The create routes return 422** (DD4; squawks 0112 and 0081).
  - **The routes.** `the_one/interfaces/web/api.py` `create_provider` (around line 4651,
    `LLMProviderConfig.model_validate(data)`) and `create_chat_session` (around line
    4319, `ChatSession.model_validate(data)`) catch `ValidationError` and raise
    `HTTPException(422, detail=e.errors(include_context=False, include_input=False))`,
    the same pattern as their sibling routes.
  - **Unit tests:**
    - a provider POST missing `base_url` returns 422;
    - a provider POST with an `api_key` and a missing field returns 422, and the response
      text does **not** contain the `api_key` value;
    - an invalid chat-session POST returns 422.

    Use the existing credentialed client fixtures (`tests/_credential_helpers.py`).
  - **The provider form's display.** `areas/admin/provider-editor.js` `performSave` sends
    through `App.api.fetchJson`, so a 422 detail list shows as "field: message", not
    "[object Object]". The success path (the flash, `onCreateSuccess`, `onSaveSuccess`,
    the edit→edit header refresh) is unchanged.
  - **Browser test** (`settings` lane): a `page.route`-intercepted 422 on save shows the
    flattened message in `.editor-error`.
  - **The seeder docstring** (`tests/browser/seeders.py`, the provider seeder that claims
    a 422) is now accurate.
- [ ] **Accessible names** (squawks 0113 and 0114).
  - **The master toggles.** The Tools tab's category master checkbox
    (`areas/studio/tools-tab.js`, around lines 125–137) has an accessible name, for
    example `aria-label="Enable all {category} tools"`.
  - **The info icons.** All six `field-info-icon` buttons have an accessible name from
    their description: `provider-editor.js` (3), `tools-editor.js` (1),
    `tools-form-helpers.js` (1), `mcp-server-editor.js` (1).
    - They are HTML strings: add `aria-label` with `escapeAttr`, adding no new sink, and
      keep `title`.
  - **Tests.** Contract or browser tests use `tests/browser/_a11y_resolve.js` to assert a
    non-empty name on a master toggle and on each kind of info icon.
- [ ] **The Settings tile title row** (DD3, squawk 0116).
  - **The fix.** Both tile kinds put the name and the badge in a flex title row. The
    name takes `flex: 1 1 auto; min-width: 0` with an ellipsis, and the badge is
    `flex: none`. The badge is no longer absolutely positioned over the name.
    - `providers-list.js` (DOM) and `tools-grid.js` (HTML string) each gain the wrapper
      element.
    - The CSS lives in `admin.css`; remove the `calc(100% - 128px)` reserve.
  - **The sink check.** If `tools-grid.js`'s HTML-string change trips the UI-guard sink
    baseline, keep the change inside the existing sink rather than adding one.
  - **Tests.** The squawk's bounding-box tests: in both themes, at viewports 1024 and
    1440, a long provider name and a long tool name never overlap their badge, and a
    short name is not truncated early (`settings` lane).
- [ ] **A5: an initial sidebar label.**
  - `index.html`'s `<aside id="app-sidebar">` has an initial `aria-label`, for example
    "Sidebar", so it is never unlabelled before the router's first commit.
    `router.js:573` still sets the destination label after that.
  - `index.html` is read once per process, so this needs a restart to show.
  - **Test:** a unit or static check that the served `index.html`'s aside carries an
    `aria-label`.
- [ ] **The root `h1`** (DD11).
  - **What renders.** At `#agents` and at each `#library/{section}` root with no editor
    open, the page has exactly one `h1`: visually hidden (the global `.visually-hidden`
    utility), with the text "Agents" or "Library".
  - **When an editor is open,** that `h1` is absent, and `.editor-title` is the only
    `h1`. The empty states keep `headingLevel: 2` (`studio.js` around lines 923 and 2483).
  - **The list pane's lifetime.** `setActiveSection` owns it (CLAUDE.md "Agents list and
    detail"). Put the `h1` where it is created and removed with the root state, without
    adding a document listener.
  - **The spec contract change.** `tests/behavior/list-and-detail.md` step 2 ("no editor
    and no `h1`" at `#agents`) is re-authored to expect the visually hidden "Agents"
    `h1`, with an `Updated` line. The same change applies to any browser test that
    asserts no `h1` at a root.
  - **Browser tests** (`agents` and `library` lanes): one visually hidden `h1` at each
    root, and exactly one `h1` (the editor title) with an item open.
- [ ] **The provider Models label** (DD10).
  - **The section** in the provider editor is headed "Available models", not "Models"
    (`provider-editor.js` around line 108, plus its header comment), with one line of
    help: "Each agent chooses one of these in its Model section." The line links "Agents"
    to `#agents`, or is plain text if a link does not fit the section style.
  - **The rows** are styled as plain information, not options:
    - `.admin-pf-model-item` in `admin.css` loses any affordance that suggests selection;
    - plain text with a muted separator is enough;
    - no hover or cursor change.
  - **Both forms** of the section get the label: the basic list (`renderBasicModels`) and
    the Ollama list (`renderOllamaModels`).
  - **Test:** a browser test (`settings` lane) on a seeded non-Ollama provider (mock)
    reads the label text.
- [ ] **Each squawk file** (0081, 0112, 0113, 0114, 0116) has its Corrective Action and
  Verification written and is marked `completed`, with the commit reference left
  "pending the flight commit". 0081 and 0112 can cross-reference each other.
- [ ] **Docs.** `CLAUDE.md` and `the_one/agents.md` are updated where they describe these
  surfaces:
  - the Settings tiles (CLAUDE.md "Settings item pages");
  - the create routes' 422;
  - the root `h1`;
  - the Models label.

  Keep it brief.
- [ ] **Gates.**
  - `ruff check` and `ruff format --check` pass.
  - `TEST_TIMEOUT=3000 make test-unit` passes.
  - The static guards pass: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`
    and `tests/test_design_tokens_a11y.py`.
  - The `settings`, `agents` and `library` browser lanes pass (`THE_ONE_TEST_NETNS=1`).
  - The `shared` lane passes (`TEST_TIMEOUT=3600`), since `index.html` changed.
  - The `contracts` lane passes (`THE_ONE_REQUIRE_WEBKIT=1`) if any `ui/` file changed.

## Verification Steps

- **Units:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh <new and changed unit
  files> -x --timeout 60`, then `TEST_TIMEOUT=3000 make test-unit` (in the background).
- **Browser:** `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh
  --lane settings` (then `agents`, `library`, and `shared` with `TEST_TIMEOUT=3600`), run
  in the background and polled.
- **Specs:** re-read `list-and-detail.md` step 2 against the new behaviour.

## Implementation Guidance

1. **The backend 422s and their unit tests first.** Then switch the provider form to
   `fetchJson` and add its intercepted-422 browser test.
2. **The accessible names** (0113, 0114) and their name assertions.
3. **The tile title row** (0116) and its bounding-box tests. Look at how
   `providers-list.js` builds the tile (`link` and `badge` as `kids`) and
   `tools-grid.js`'s tile string.
4. **A5** (`index.html`) and its check.
5. **The root `h1`** (DD11), with `list-and-detail.md` step 2 and any test asserting no
   root `h1`.
6. **The Models label** (DD10).
7. **Squawk files, docs, gates;** then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **`update_provider`'s 422s** also start displaying legibly through `fetchJson`. That is
  good; don't regress its `__MASKED__` handling, because the payload is unchanged.
- **Test-connection errors** in `provider-editor.js` keep their own path. Only
  `performSave` changes here.
- **A tool category name with a quote or `&`** in the `aria-label`: use `escapeAttr`.
- **The Ollama models panel** has its own header (Refresh, Pull). The label sits above it
  without breaking the pull layout.
- **A knowledge-base root** (`#library/knowledge`) with zero knowledge bases still
  renders the hidden `h1` beside its empty state.

## Files Affected

- `the_one/interfaces/web/api.py`, plus a unit test file (new or existing provider and
  session route tests).
- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`,
  `provider-models.js`, `providers-list.js`, `tools-grid.js`, `tools-editor.js`,
  `tools-form-helpers.js`.
- `the_one/interfaces/web/static/js/areas/studio/tools-tab.js`, `mcp-server-editor.js`,
  `areas/studio.js`.
- `the_one/interfaces/web/static/css/admin.css`, `the_one/interfaces/web/static/index.html`.
- Browser tests in the `settings`, `agents` and `library` lanes; `tests/browser/seeders.py`
  (docstring).
- `tests/behavior/list-and-detail.md`.
- Squawks 0081, 0112, 0113, 0114, 0116; `CLAUDE.md`, `the_one/agents.md`; the flight log.

## Citation Audit

Checked on 2026-10-06 against `07ed2c4`:
- **`api.py`:** `create_provider` (line 4638, `model_validate` at 4651), `create_chat_session`
  (line 4315, `model_validate` at 4319), the sibling `include_context=False` pattern (for
  example line 1494).
- **`provider-editor.js`:** `performSave` (line 811), the `e.detail` throw (line 824), the
  Models section (line 108).
- **`api.js`:** `fetchJson` (line 22), which flattens detail lists.
- **`providers-list.js`:** the badge and link kids (lines 78–92). **`tools-grid.js`:** the
  tile string (line 50).
- **`studio.js`:** `headingLevel: 2` (lines 923 and 2483).
- **`index.html`:** `<aside id="app-sidebar">` (line 27).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
