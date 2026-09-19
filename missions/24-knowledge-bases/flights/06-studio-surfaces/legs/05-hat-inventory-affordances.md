# Leg: hat-inventory-affordances

**Status**: landed
**Flight**: [Studio Surfaces](../flight.md)

## Objective

Close three affordance gaps the operator found while walking the HAT: a
registered folder cannot be removed, a knowledge base's description cannot be
set or edited, and the per-item actions crowd the row.

## Context

Raised at the HAT, 2026-09-19, walking step 2 of the mission-closing walk.
Classified at the fix-vs-feature gate by the Flight Director, out loud:

- **Remove a source — FIX.** `DELETE /knowledge-bases/{kb_id}/items/{item_id}`
  already exists and works; the UI never exposes it, so an operator who registers
  the wrong folder must delete the whole knowledge base. Registration without
  deregistration is half an affordance, and it falls inside Leg 1's own stated
  scope.
- **Description + Save — FEATURE.** `KnowledgeBase.description` exists on the
  model and the API accepts it; only the UI omits it. But replacing "Rename" with
  a general edit form touches the flight's one cross-entity write, so it is
  designed, not improvised.
- **Kebab menu — FEATURE.** **No overflow-menu component exists anywhere in the
  tree** (verified). This introduces one.

A fourth finding — a native folder picker — was **deferred to Flight 7** by the
operator. Recorded in Deferred Scope with the reason: a browser cannot supply a
server-side absolute path (`webkitdirectory` yields only relative paths;
`showDirectoryPicker()` yields a handle with a name and no path), while the
pywebview desktop shell **can** via `create_file_dialog(FOLDER_DIALOG)` — which
makes it two different behaviours in two shells, and a design decision rather
than a control.

## Leg Design Decisions

**L5-D1 — Removing a registered folder is a two-step confirm; the BUTTON stays
terse and a CAPTION carries the consequence.** A remove control on each folder
row, using the same `App.confirmDelete` two-step pattern the rest of the app uses.

**An earlier draft of this decision contradicted itself** and the contradiction is
worth recording, because it is the kind that ships: it demanded the confirm state
a full consequence sentence *and* cited "Confirm remove?" as the label. Verified
at design review that `App.confirmDelete` only swaps one short label via
`opts.confirmLabel`, and that **every caller in the codebase** — `studio.js`,
`provider-editor.js`, `mcp-server-editor.js`, `system-page.js`,
`self-configuration-tab.js` — passes 2-4 words ("Confirm Delete?", "Confirm
Purge?", "Confirm revoke?"). Cramming a sentence in would be a first-of-its-kind
long inline label inside a single-line folder row, with no precedent for how it
wraps.

**Resolved**: the button label is **`Confirm remove?`**, matching precedent. The
consequence lives in a **static caption rendered beside the control**, present
before any click rather than only in the armed state — "Removes this folder and
every file indexed from it, with their chunks and search entries." A button label
is not where a cascade gets explained.

The cascade itself was verified at review, not assumed: `KBItemRepository.delete`
selects chunks for the item **and** for `parent_id = item_id` in one query, purges
their FTS rows, deletes the item, and `kb_items.parent_id ... ON DELETE CASCADE`
removes the children; the route also calls the vector store's delete. The item
hierarchy is genuinely flat — a folder's children are only ever file rows — so the
one-level query is exactly sufficient. An operator who thinks this merely
"unregisters" a path will be wrong in a way they cannot undo.

**L5-D2 — The detail view gains an edit form; the server needs no change.** Name
and Description in one form with a single **Save**, replacing the rename-only
affordance. The create form gains Description too.

**The rename rewrite stays correctly gated with no server work**, and this is the
load-bearing part: `update_knowledge_base` already carries L2-D9's two early
returns — raw name unchanged, then derived name unchanged — so a PUT carrying
both fields fires the cross-entity `disabled_tools` rewrite **only when the name
actually moved**. Changing only the description touches no agent. Verify this
rather than assume it; it is the difference between an edit form and an
accidental fan-out write on every keystroke-worth of description.

DD-16's advisory length hint applies to the **name** field in both forms, at 43
code points, unchanged. The description field carries no length rule — nothing
derives from it.

**L5-D3 — The inventory's edit form joins dirty-confirm, reversing a Leg 3
non-goal deliberately.** Leg 3 kept the inventory's forms out of
`_confirmLeaveImpl` because they were **single-field and submit-immediately**.
This is a multi-field form with an explicit Save — the exact shape the dialog
exists for, and the same reasoning that put Leg 4's settings panel in. Add a
`knowledge`-section arm to Studio's `inEditor` predicate, bridged by an
`onDirtyChange` callback, matching the `mcp-sources`/`connectors` pattern already
there. Recorded as a reversal so it does not read as an inconsistency.

**L5-D4 — The overflow menu is built minimal and LOCAL, not promoted to the
design system.** "View chunks" and "View source" move behind a per-row overflow
control; the remove action for **item** rows, if any, stays out of scope — this
menu carries the two read affordances only.

Build it in `knowledge-section.js`, **not** in `components.css` as a shared
component. There is exactly one consumer; promoting it to the shared design
system on speculation would put an unproven interaction pattern where every
surface inherits it. A second consumer is the trigger for promotion, not the
first.

Accessibility is not optional here, because a menu is a keyboard trap if done
carelessly: the trigger carries `aria-haspopup="menu"` and `aria-expanded`, the
menu has `role="menu"` with `role="menuitem"` children, **Escape closes and
returns focus to the trigger**, arrow keys move between items, and a click
outside closes it. The seven `tests/test_ui_guards.py` invariants apply —
in particular every data-derived node stays `createElement`/`textContent`, and
each new `data-testid` needs a `docs/ui-testid-registry.md` row.

## Acceptance Criteria

- [x] AC-1 — A registered folder row carries a remove control. Activating it
      twice (the existing two-step confirm) removes the folder, and the item list
      and status counts reflect it without a reload — via an **immediate**
      `refreshStatusNow()` on the success path, **not** by waiting on the 5-second
      poll. Relying on the poll would satisfy this criterion's wording while
      leaving up to five seconds of stale display; AC-9's post-reindex refresh is
      the precedent.
- [x] AC-2 — The confirm state **states the consequence** — that items discovered
      under the folder, and their chunks, are removed too — rather than a bare
      "Confirm?".
- [x] AC-3 — Removing a folder does **not** delete the knowledge base itself; the
      knowledge base remains in the inventory with its other folders intact.
- [x] AC-4 — The create form accepts a description, and it is persisted
      (`GET /api/knowledge-bases/{id}` returns it).
- [x] AC-5 — The detail view offers **Save** over Name + Description together.
      Saving a changed description **with the name untouched** leaves every
      attached agent's `disabled_tools` **byte-identical** — asserted at the API,
      because this is the cross-entity write and a regression here is silent.
- [x] AC-6 — Saving a changed **name** still rewrites `disabled_tools` across
      attached agents, exactly as before. The existing rename behaviour is not
      lost in the refactor.
- [x] AC-6b — **A name change that leaves the derived name identical performs no
      agent I/O.** The only shape that does this is a same-position substitution
      between two *different* disallowed characters — L2-D9's own precedent pair,
      `My Notes` → `My/Notes`, both normalising to `My_Notes`. Assert
      `disabled_tools` is byte-identical across that save. This is the **second**
      early return, and nothing else in the suite reaches it.
- [x] AC-7 — DD-16's advisory hint still fires on the name field, at 43 code
      points, in both create and edit. An empty name is still refused.
- [x] AC-8 — Navigating away from the edit form with unsaved changes raises the
      confirm dialog; navigating away clean does not.
- [x] AC-9 — "View chunks" and "View source" are reachable from a per-row
      overflow control. Both still work, and both still fetch **only on
      activation** (DD-8's on-demand rule is not lost).
- [x] AC-10 — The menu is keyboard-operable: opens from the keyboard, Escape
      closes it and **returns focus to the trigger**, arrows move between items.
- [x] AC-11 — `tests/test_ui_guards.py` passes with **no new dynamic-sink
      entries** and a registry matching the sources both ways.
- [x] AC-12 — `make lint` clean, `make test-unit` green, `--lane studio` green.

## Verification Steps

- AC-1 through AC-10: new/extended tests in
  `tests/browser/test_flow_studio_knowledge_inventory.py`.
- **AC-5, AC-6 and AC-6b belong in `tests/test_db_api.py`, not the browser lane.**
  Committing to that definitively rather than leaving it a toss-up: this is pure
  server-side cross-entity logic, fully reachable through
  `PUT /api/knowledge-bases/{id}` plus `GET /api/agents/{name}` with no UI
  involved. A Playwright round-trip is slower and flakier, and this is the
  assertion that matters most — a slow path is the wrong default for it. Together
  the three cover every branch of `update_knowledge_base`: rewrite fires, first
  early return, second early return.
- AC-11: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py -x --timeout 30`.
- AC-12: `make lint`; `make test-unit` verbatim, alone, foreground; then the lane.

## Edge Cases

- **Removing the only folder** leaves the knowledge base with zero items — it
  must render the empty state, not a broken list.
- **Removing a folder while its items are still indexing** — the route stops the
  worker and cascades; the UI must not assume a settled state.
- **A description containing markup** — rendered with `textContent`, never a
  sink.
- **A name change that does NOT move the derived name** — see AC-6b. The
  mechanism was **described wrongly in an earlier draft** and the correction
  matters for how it is tested: `_normalize_kb_name` is
  `re.sub(r"[^a-zA-Z0-9_-]", "_", name)`, which maps **each character
  individually** and does **not** collapse runs. So trimming a trailing space, or
  collapsing a double space, **does** move the derived name — a test built on the
  intuitive reading of "whitespace-only change" would exercise the *first* early
  return, not the second, and prove nothing about it.
- **The overflow menu open when the list re-renders** (the poll's
  signature-based invalidation fires): the menu must close or survive, not leak a
  detached element.

## Files Affected

- `static/js/areas/studio/knowledge-section.js` — remove control, edit form, menu
- `static/js/areas/studio.js` — `inEditor` arm + `onDirtyChange` bridge
- `static/css/studio.css` — menu and form styles
- `docs/ui-testid-registry.md` — new rows
- `tests/browser/test_flow_studio_knowledge_inventory.py` — extended
- `tests/test_db_api.py` — the description-only-save assertion, if cheaper there

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`; `--lane studio`)
- [x] Update flight-log.md
- [x] Set status to `landed`
- [x] Do NOT commit — the Flight Director commits (honored — nothing committed)
