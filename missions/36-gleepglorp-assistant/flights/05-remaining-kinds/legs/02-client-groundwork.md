# Leg: 02-client-groundwork

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

Extract what the MCP and provider fill, follow and kind modules repeat into shared helpers in
`static/js/areas/shared/`, split the Plan sign-in flow out of `provider-editor.js`, and fix
squawk 0401. The agent, MCP and provider fills and follows behave exactly as before, so Legs 3b
and 4b add each kind as constants plus its write logic.

## Context

- **Flight DD4** (client gaps), **DD14** (no new placements in this leg) and **DD13** (lanes
  and pins). This is the Flight 4 debrief's recommendation 2, client half.
- **Designed after Leg 1a and Leg 1b landed.** This leg uses Leg 1b's three `gleepglorp-*`
  lanes. Leg 1a changed only server code.
- **What repeats today** (FD read, `180c4c40` plus Legs 1a and 1b):
  - **`mcp-editor-fill.js` (349 lines) and `provider-editor-fill.js` (317 lines)** share:
    - the module scaffolding: `attach(getController)`, `activeFill`, the route check,
      `timeoutMs_` with the dev seam `__ggFillSettleTimeoutMs`, `isOpen`, `whenSettled` (a 25 ms
      poll, the `ready()`/`saving()` states and the microtask re-check), and the module export
      with `apply` delegating to the active fill;
    - the per-controller note bookkeeping: `placed`, `noteSeq`, `dead`, `buildNote_`
      (`<p class="agent-filled-note">` + bot icon + text), `whenText_`, the `aria-describedby`
      link and unlink, and `removeNotes_` by testid;
    - the write helpers: `same`, `has`, the `record` `{at, values}`, `keep` / `wrote`,
      `operatorScalar(k)` ("differs from the baseline AND from what a fill wrote"), and
      `finish_`, which runs `checkDirty`, then `redraw`, then returns `{unavailable, written,
      kept}`.

    They differ in the constants (the testid, `ALLOWED`), the route segment (`mcp` vs
    `providers`), `write_` and what `redraw` / `wanted_` draws. The provider module's `wanted_`
    plus a `drawnSig` short-circuit is the better redraw shape.
  - **`mcp-editor-follow.js` (80 lines) and `provider-editor-follow.js` (98 lines)** share:
    - `buildNote_`, the "Changed by a change you approved in a GleepGlorp chat · time · Open
      chat" note, which is also a third copy in `agent-editor-follow.js:97-119` (that copy adds
      `data-field` / `data-item`);
    - the `onIdle` → fetch → saving-retry → rebase skeleton;
    - `onEvent` (kind and `target_id` filter) and the once-per-page `attach` listener on
      `App.approvals.CONFIG_CHANGED`.
  - **`mcp-kinds.js` and `provider-kinds.js` (61 lines each)** differ only in names, the Library
    section, the store and the fill module.
- **What stays per kind (flight DD4):**
  - the `setType` rebase;
  - the MCP Sensitive-row piece (`mcp-editor-fill.js` rows logic);
  - the provider key logic;
  - agent-editor-fill (its own record and group logic).

  Agent-editor-follow adopts only the shared note builder.
- **The route check must not assume Library.** Leg 4b's editors live under `#settings/…`. So the
  core takes a `routeIs(key)` function from the kind module, not a section name. The MCP and
  provider modules pass a small Library helper.
- **`provider-editor.js` is at 894 of its 895 allowance** (`tests/test_area_module_size.py:24-26`).
  The Plan sign-in block (`:535-805`: `pendingAutoSignInId`,
  `clearProviderSignInHandoff`, `wirePlanSignIn` and its inner functions) moves to
  `provider-sign-in.js`. The token-expiry helpers (`:488-534`) move with it, or to their own
  file, whichever keeps each file coherent. That brings `provider-editor.js` under 800, and its
  `ALLOWANCE` entry is removed.
- **Squawk 0401.** After an approved type change on a dirty provider editor, the editor shows
  "This provider's type changed; Cancel to see it" (`provider-editor-follow.js:64-69`). But Save
  still sends the old type and reverts the approval.
  - **The fix (flight DD4):** Save is refused in the editor's existing save-error line
    (`h.shell.setError`) with that same sentence, until Cancel re-mounts.
  - **Placement:** the existing save-error line, so no new placement.

## Inputs

- The tree after Legs 1a and 1b (landed, uncommitted).
- **The modules:**
  - `static/js/areas/studio/{mcp-editor-fill,provider-editor-fill,mcp-editor-follow,provider-editor-follow,agent-editor-follow,mcp-kinds,provider-kinds,provider-editor,provider-editor-controller}.js`;
  - `static/js/gleepglorp-kinds.js`;
  - `static/index.html` (the script order).
- `squawks/0401-dirty-provider-editor-reverts-an-approved-type-change.md`.

## Outputs

- **New shared helpers:**
  - `static/js/areas/shared/gleepglorp-fill-core.js` — `App.gleepglorpFill`:
    - `module(opts)`, which builds the module-level object (`attach`, `isOpen`, `whenSettled`,
      `apply`, `create`) from `{routeIs(key), handle(ctl) -> per-kind handle parts}`;
    - `notes(ctl, {testid, idPrefix})`, the per-controller note bookkeeping: `place(field, text,
      controlsFn)`, `removeAll()`, `whenText(record)`, the describedby link and unlink, and the
      `drawnSig` short-circuit;
    - `writer(values, baseline, record)`, which gives `keep`, `wrote`, `operatorScalar`, `result()`;
    - `libraryRoute(section)`, which returns a `routeIs(key)` for `#library/{section}/~new|{id}`.

    Names are indicative; the Developer may refine them, keeping one core.
  - `static/js/areas/shared/gleepglorp-follow-core.js` — `App.gleepglorpFollow`:
    - `buildNote(detail, {testid, text?, field?, item?})`;
    - `listen(kindName, handler)`, the once-per-page `CONFIG_CHANGED` listener with the kind and
      `target_id` filter;
    - `refetchThen(ctl, url, ctx, fn)`, the `onIdle` → fetch → saving-retry skeleton.
  - `App.gleepglorpKinds.registerLibraryKind({name, section, store, noun, fill: () =>
    App.studio.xEditorFill})`, which builds today's MCP and provider registration specs. It is
    added to `gleepglorp-kinds.js` or a new `areas/shared/gleepglorp-kind-specs.js`.
- **Modules rewritten on the helpers:**
  - `mcp-editor-fill.js`, `provider-editor-fill.js`, `mcp-editor-follow.js` and
    `provider-editor-follow.js`;
  - `agent-editor-follow.js`, adopting `buildNote` only;
  - `mcp-kinds.js` and `provider-kinds.js`, via `registerLibraryKind`.
- **The provider-editor split:** `static/js/areas/studio/provider-sign-in.js` (new), which takes
  the Plan sign-in and, if it fits, the token expiry. `provider-editor.js` drops below 800 lines.
- **Squawk 0401:** the controller gains a save block (`blockSave(text)` / cleared on re-mount or
  Cancel), and `performSave` honours it.
- `static/index.html` loads the new files in dependency order.
- **Tests:**
  - `tests/test_area_module_size.py` `ALLOWANCE` loses its entry;
  - `tests/test_store_static.py` `test_oauth_and_provider_mutations_invalidate_providers`
    counts the invalidations over `provider-editor.js` + `provider-sign-in.js` (authorized
    re-target);
  - a new browser test for squawk 0401 in `tests/browser/test_flow_gleepglorp_follow_provider.py`;
  - a static test that the three follow notes come from one builder.
- **Docs:**
  - **`the_one/agents.md`:** "GleepGlorp client kinds registry (M36 F4 L2)" gains a "Shared
    fill and follow helpers (M36 F5 L2)" paragraph, and the Adding-a-kind checklist's client
    pointer names the helpers;
  - **`docs/ui-control-inventory.md`:** only if a test requires it. The helpers are not UI
    controls.
- **The 0401 squawk file:** `in-progress`, with Corrective Action and Verification.

## Acceptance Criteria

- [ ] **AC1. One core.**
  - `mcp-editor-fill.js` and `provider-editor-fill.js` contain no copy of the scaffolding,
    notes or writer helpers listed in Context.
    - **Scoped to those two files,** a grep for `__ggFillSettleTimeoutMs`, `aria-describedby`
      and `function whenSettled` returns nothing.
    - **In the core,** `gleepglorp-fill-core.js` holds each.
    - **Out of scope:** `agent-editor-fill.js` keeps its own (DD4), and other files use
      `aria-describedby` for their own reasons.
  - `mcp-editor-follow.js`, `provider-editor-follow.js` and `agent-editor-follow.js` build the
    approval note through `App.gleepglorpFollow.buildNote`. A grep under `static/js/areas/` for
    `Changed by a change you approved in a GleepGlorp chat` finds it once, in the follow core.
  - `mcp-kinds.js` and `provider-kinds.js` register through `registerLibraryKind`.
- [ ] **AC2. No behaviour change for agent, MCP and provider.** These lanes pass with their
  assertion lines unedited:
  - `gleepglorp-chat`, `gleepglorp-fill` and `gleepglorp-kinds`;
  - `mcp` and `mcp-connection`;
  - `providers`;
  - `agents` and `agent-tabs`.

  The DOM each module produces is identical: testids, classes, ids, `data-field` / `data-item`,
  text and the `aria-describedby` links. The browser assertions already pin it.
- [ ] **AC3. `provider-editor.js` is under 800 lines.** Its `ALLOWANCE` entry is removed, and no
  new `ALLOWANCE` entry is added (`tests/test_area_module_size.py` passes). Every new or changed
  file under `static/js/areas/` is ≤ 800 lines.
- [ ] **AC4. The sign-in still works.** The plan sign-in and token browser tests pass unedited:
  - `tests/browser/test_flow_provider_plan_signin.py`;
  - `tests/browser/test_flow_provider_plan_token.py`;
  - `tests/browser/test_flow_provider_editor.py`.

  Grep for their lanes. `App.studio.clearProviderSignInHandoff` and
  `App.studio.planTokenExpiry` keep their names and signatures. Grep every caller under
  `static/` and `tests/`.
- [ ] **AC5. Squawk 0401.** A browser test, falsified:
  1. open an existing provider's editor and make it dirty (change its name);
  2. approve a proposal that changes its type, seeding the proposal and approving through the
     existing helpers in `test_flow_gleepglorp_follow_provider.py`;
  3. see the type-changed note;
  4. click Save:
     - the editor's error line shows "This provider's type changed; Cancel to see it". Locate it
       by `role=alert` inside the editor shell (`.ui-editor-error-row`); no new testid is added;
     - no PUT is sent (the `_mcp_editor` PUT counter);
     - the stored type is unchanged (`_get(base, pid)["type"]`);
     - the form stays dirty;
  5. click Cancel: the editor re-mounts on the new type. Edit the name and Save: the PUT
     succeeds.

  **Build it on the existing test.**
  `test_a_type_change_by_approval_leaves_a_dirty_editor_alone_and_cancel_shows_it`
  (`test_flow_gleepglorp_follow_provider.py:324`) already does steps 1-3 and the Cancel half.
  Extend it as a new test beside it, using the same helpers. The old one stays unedited.

  **Also covered:**
  - **A later same-type approval clears the block.** A second approval that changes the type
    back takes the rebase path. Save then works, and the stale message is gone.
  - **A clean editor's type-change re-mount** is unchanged.
- [ ] **AC6. The static guards pass:**
  - `tests/test_ui_guards.py`;
  - `tests/test_token_definitions.py`;
  - `tests/test_design_tokens_a11y.py`;
  - `tests/test_ui_ownership.py`;
  - `tests/test_ui_control_inventory.py`;
  - `tests/test_store_static.py`;
  - any script-order or static-asset test (grep `index.html` in `tests/`).
- [ ] **AC7.** `THE_ONE_TEST_NETNS=1 make test-unit` passes (expected 15 skips).
- [ ] **AC8. Docs and squawk file** updated as listed in Outputs.
- [ ] **AC9.** `ruff check` / `ruff format --check` are clean (tests touched).

## Verification Steps

- **AC1:** run the greps and paste their output.
- **AC2, AC4, AC5:** run each lane on its own, one at a time and never with the unit tier:
  `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`.
  Report the counts and walls; solo walls move no budget. Then run `git diff -- tests/browser/`:
  it shows only the new 0401 test.
- **AC3:** `wc -l` on the changed JS files, plus `tests/test_area_module_size.py`.
- **AC5:** report the test and its falsification. Remove the Save block by editing, run, see it
  fail, then put it back.
- **AC6, AC7:** run the listed files, then `make test-unit` in the background, waiting for
  completion.
- **AC8:** quote the changed docs.

## Implementation Guidance

1. **Read first.**
   - The five fill and follow modules and the two kind modules in full, plus
     `agent-editor-follow.js:90-125`.
   - **How the controllers call into the fill modules:**
     - `mcp-server-editor.js` calls `App.studio.mcpEditorFill.create(ctl)`;
     - `provider-editor-controller.js` does the same for providers;
     - the glues call `attach(...)`.

     Grep `EditorFill.` and `EditorFollow.` under `static/` to list every consumer. Every
     consumer API stays: `create`, `attach`, `whenSettled`, `isOpen`, `apply`, `ALLOWED`, and
     `buildNote` on `providerEditorFollow`.
   - **The drawer's applier** (`js/gleepglorp-drawer/fill.js`) reads only the kind spec's
     `fill` members. Keep those unchanged.

2. **`gleepglorp-fill-core.js`** (in `areas/shared/`, loaded before the studio fill modules).
   - **Module level.** `App.gleepglorpFill.module({routeIs, testHook?})` returns `{attach,
     isOpen, whenSettled, apply, activeFill}`. It holds `getController` and keeps the exact
     poll, timeout, dev-seam and microtask semantics of today's `whenSettled`.
   - **The two `whenSettled` implementations are identical** (the design review `diff`; the
     provider's "models panel" remark is only a comment). No `ready` override is needed.
   - **Notes.** `App.gleepglorpFill.notes(ctl, {testid, idPrefix, skipIfUnchanged})`. Its
     `redraw(wantedList)` places each `{field, text}` through `ctl.placeNote(field, el)`, or
     through `ctl.placeTableNote(el)` for an entry flagged `table: true` (MCP's row note).
     - **The `drawnSig` short-circuit is opt-in** (`skipIfUnchanged: true`). The provider
       module opts in. **MCP does not.** MCP's rows re-render on `rebase`, `setType` and
       `setRows`, which discards the notes inside them, and today's always-redraw rebuilds them
       on the next input. A short-circuit would leave them gone.
     - `removeNotes_` resets `drawnSig` before clearing `placed`, as today.
   - **Testids stay extractable.** `tests/test_ui_guards.py` checks `docs/ui-testid-registry.md`
     against the testid literals it finds in JS. So each kind module passes its testids as
     string literals the extractor sees (for example `testid: 'mcp-filled-note'` in the call),
     not only through a variable. Check the extractor's patterns first: the provider
     controller's `FOLLOW_TESTID` variable form passes today, so confirm which forms count.
     Run `test_ui_guards.py` after the move.
     - **`buildNote_`** keeps the exact element: `p`, `id = idPrefix + '-' + seq`, `className
       'agent-filled-note'`, `data-testid`, `data-field`, the bot icon, then a text node with a
       leading space.
   - **Writer.** `App.gleepglorpFill.writer(c, b, record)` gives `keep(k)`, `wrote(k)`,
     `operatorScalar(k)`, `written`, `kept`.
     - MCP's `keep` only records keys present in `vals`, while the provider's keeps any key. So
       `keep` takes the `vals` filter as an option (`onlyIn: vals`), or the MCP module wraps
       it. Keep both behaviours exactly.
   - **`libraryRoute(section)`** reproduces `routeIsEditor_` (`destination === 'library'`,
     `segs[1] === section`, `~new` for create, the decoded id for `edit:{id}`).

3. **Rewrite `mcp-editor-fill.js` and `provider-editor-fill.js` on the core.** Each keeps its
   doc header (trimmed to what is kind-specific), constants, `apply` (allowlist + warning),
   `write_`, and its `wanted` list builder. Each should shrink by about 100 to 150 lines.

4. **`gleepglorp-follow-core.js`.**
   - **`buildNote(detail, opts)`** reproduces each of the three variants exactly:
     - the MCP and provider testids;
     - the provider's `text` override (the type-changed sentence has no time or link);
     - the agent's `data-field`, `data-item` and the `--item` class.
   - **`listen(kind, onEvent)`** registers once per page per kind and filters on `detail.kind
     === kind && detail.target_id`. The agent follow (any agent field, keyed by agent name)
     keeps its own listener; only its note builder moves.
   - **`refetchThen(ctl, url, isCurrent, fn)`** reproduces `follow_`'s `onIdle` → `fetchJson`
     → "saving again, retry" loop.
   - **Rewrite the MCP and provider follow modules on it.**
     - The provider module keeps its type-change branch.
     - `providerEditorFollow.buildNote(detail, text)` stays exported **with that signature**, as
       a wrapper over the core. `providers-section.js:131` calls it with one argument.
     - The core guards a null `detail`, as the provider copy does; the MCP and agent copies
       don't need it, and the guard harms nothing.

5. **`registerLibraryKind`.** Produces exactly today's spec:
   - the `labels` texts from `noun`, with the casing as today: "MCP server" and "model
     provider", which needs a `Noun` for the sentence-initial form. Pass both strings rather
     than derive them.
   - `openLink` with `proposal-open-item`, `store`, `recordKey`, and `fill` with
     `routeFor`, `openKey`, `exists` (a forced store fetch, `true` on error), `isOpen`,
     `whenSettled`, the no-op `select` / `beforeNavigate` / `afterNavigate`, and `apply`.

   The MCP and provider kind files become a few lines each. Registration order (`agent, rule,
   routine, mcp_server, provider`) is unchanged: keep the script order.

6. **The provider-editor split.**
   - Move `pendingAutoSignInId`, `clearProviderSignInHandoff` and `wirePlanSignIn` (with its
     inner functions) to `provider-sign-in.js` as `App.studio.wirePlanSignIn` (and keep
     `App.studio.clearProviderSignInHandoff`). Load it before `provider-editor.js`.
   - `provider-editor.js` calls `App.studio.wirePlanSignIn(...)` where it called the local one.
   - **Leave the token-expiry helpers in `provider-editor.js`.** Moving the sign-in alone (about
     270 lines) brings it to about 625 lines. `renderTokenExpiry` is called from the save path,
     so moving it would add a cross-file call.
   - `provider-sign-in.js` needs its own `var util = App.ui.util` and any constants the block
     uses (check for `MASKED_SENTINEL`, `PLAN_TOKEN_TYPE`).
   - The callers of `clearProviderSignInHandoff` and `planTokenExpiry` are
     `providers-section.js:275` and `test_flow_provider_plan_token.py:211-226`. Run `grep -rn
     "clearProviderSignInHandoff\|planTokenExpiry" the_one/interfaces/web/static tests` to
     confirm.
   - Re-target `tests/test_store_static.py::test_oauth_and_provider_mutations_invalidate_providers`
     to count over both files. It is authorized: the assertion's meaning (code, reset and save
     each invalidate `providers`) is unchanged. Also check the `test_store_static.py:405` table
     entry, which reads `provider-editor.js` for the save's create and save strings. Those
     stay in `provider-editor.js`.
   - Grep `tests/` for other readers of `provider-editor.js` text (`test_admin_reasoning_effort_field.py`,
     `tests/_app_routes.py`, `test_gleepglorp_kind_provider.py`) and confirm each still finds
     what it reads.

7. **Squawk 0401.**
   - The provider controller gains `blockSave(text)`. A blocked `performSave` calls
     `h.shell.setError(text)` and returns without sending, keeping the dirty state. The block
     clears on re-mount (a new controller) and on Cancel.
   - In `provider-editor-follow.js`, the dirty type-change branch calls
     `ctl.blockSave("This provider's type changed; Cancel to see it")` alongside the note.
   - **Where the check goes:** in `performSave` (`provider-editor.js:357`), right after
     `h.shell.setError('')` (`:359`), before `busy(true)` and `collectFormData`. That way no
     PUT is sent and `saving` is untouched.
   - **Only edit mode needs it.** A create form never gets a follow, and the plan sign-in's
     `requestCreateSave` is create-only.
   - **No separate clear-on-Cancel is needed.** `onCancelClick` runs `ctl.clearNotes()`, and the
     controller's `cancelHook` re-mounts into a new controller, so the block dies with the old
     one.
   - **The rebase path clears it.** In `provider-editor-follow.js`, the same-type rebase
     branch calls `ctl.blockSave(null)`, so a second approval that changes the type back
     unblocks Save.
   - Add the AC5 test, then falsify it.

8. **Docs and the squawk file** (Outputs).

9. **Run:**
   - the static guards and `test_store_static.py`;
   - `make test-unit` (background);
   - then each listed lane alone: `gleepglorp-chat`, `gleepglorp-fill`, `gleepglorp-kinds`,
     `mcp`, `mcp-connection`, `providers`, `agents` and `agent-tabs`.

   Run the contracts lanes too if any shared control changed (it should not). Update the flight
   log, mark `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **Script order.** The cores load before every module that uses them, and
  `gleepglorp-kinds.js` before the kind files, as today. A module that captures a core function
  at IIFE time needs the core loaded first. Prefer late-bound calls (`App.gleepglorpFill.x(...)`
  inside functions) where the old code was late-bound.
- **`dead` and `destroy`.** A destroyed handle stops drawing, as today. The core's notes object
  needs `destroy()`, or the handle keeps the flag.
- **The provider `drawnSig`** is reset in `removeNotes_`. Keep that order, so `clear()` followed
  by `redraw()` draws again.
- **`aria-describedby` with several notes on one control.** The link and unlink code appends
  and removes only its own id. Keep it byte-for-byte.
- **A follow event for another kind.** Each `listen` filters by kind, so no cross-talk.
- **The 0401 block and a later approval.** A later approval that keeps the changed type comes
  in through the type-change branch, and the block stays. One that changes the type back to the
  mounted type takes the rebase path and clears the block (step 7). `afterCancel` holds one
  hook, so a second type-change event overwrites the first. That is harmless: both re-mount
  from the latest row.
- **Don't touch Leg 1's new test.** `tests/test_gleepglorp_kind_hooks.py` is untracked, from
  Leg 1a; leave it as it is.
- **Squawk 0334 sweep.** Grep `tests/browser/` for other users of the provider editor and the
  MCP editor in the `settings` and `library` lanes. Run any lane that matches.

## Files Affected

- `static/js/areas/shared/gleepglorp-fill-core.js` — new
- `static/js/areas/shared/gleepglorp-follow-core.js` — new
- `static/js/gleepglorp-kinds.js` (or a new `areas/shared/gleepglorp-kind-specs.js`) —
  `registerLibraryKind`
- `static/js/areas/studio/mcp-editor-fill.js`, `provider-editor-fill.js` — on the core
- `static/js/areas/studio/mcp-editor-follow.js`, `provider-editor-follow.js`,
  `agent-editor-follow.js` — on the follow core
- `static/js/areas/studio/mcp-kinds.js`, `provider-kinds.js` — via `registerLibraryKind`
- `static/js/areas/studio/provider-sign-in.js` — new (the split)
- `static/js/areas/studio/provider-editor.js`, `provider-editor-controller.js` — split and the
  0401 block
- `static/index.html` — script order
- `tests/test_area_module_size.py` — the `ALLOWANCE` entry removed
- `tests/test_store_static.py` — the one authorized re-target
- `tests/browser/test_flow_gleepglorp_follow_provider.py` — the 0401 test
- `tests/` — a static test for the one follow-note builder (optional, if the grep in AC1 is not
  enough)
- `the_one/agents.md`, `squawks/0401-*.md`
- **Registries and pins checked:**
  - the client registry order (`test_flow_gleepglorp_kinds.py:118/179`), unchanged;
  - `ALLOWANCE`;
  - the script-order tests;
  - the seam-import guard (no server change).

## Citation Audit

Checked by the FD against the working tree after Legs 1a and 1b (2026-11-23). Neither leg
touched `static/`.

- `mcp-editor-fill.js` (349 lines): the scaffolding `:49-102`; the notes `:106-199`; `write_` and
  the helpers `:224-326`; the export `:338-348` - verified
- `provider-editor-fill.js` (317 lines): the same skeleton; `wanted_` plus `drawnSig`; `keep`
  without the `vals` filter; `routeIsEditor_` with the `'providers'` segment - verified by `diff`
- `mcp-editor-follow.js` (80 lines) and `provider-editor-follow.js` (98 lines): `buildNote_` /
  `buildNote`, `follow_`, `onEvent`, `attach`. The provider's dirty type-change branch is
  `:64-69`, and `buildNote` is exported - verified
- `agent-editor-follow.js:97-119`: the third note builder with `data-field` / `data-item`;
  `:326` its own once-per-page listener - verified
- `mcp-kinds.js` / `provider-kinds.js` (61 lines each): identical but for names, section, store
  and fill module - verified by `diff`
- `provider-editor.js` (894 lines): the Plan sign-in `:535-805` (`wirePlanSignIn` `:572`); token
  expiry `:488-534`; `performSave` `:357`; `h.shell.setError` used for save errors (`:359`,
  `:405`) - verified
- `provider-editor-controller.js:31`: `placeFollowNote`, `clearNotes`, `isDirty`, `rebase`,
  `afterCancel` - verified
- `tests/test_area_module_size.py:21` `LIMIT = 800`, `:24-26` `ALLOWANCE` - verified
- `tests/test_store_static.py:303-309`: counts `App.store.invalidate('providers')` ≥ 3 in
  `provider-editor.js` (code, reset, save); `:405` reads the save strings there - verified
- `static/index.html:93-94`: `areas/shared/` scripts load early; `:166-173` the MCP and provider
  studio script order - verified
