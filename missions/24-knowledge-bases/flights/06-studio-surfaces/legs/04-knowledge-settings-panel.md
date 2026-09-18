# Leg: knowledge-settings-panel

**Status**: landed
**Flight**: [Studio Surfaces](../flight.md)

## Objective

Give the app-wide knowledge settings an operator surface — chunking and
monitoring editable, embedding and vector store shown read-only and honestly —
and land this flight's documentation.

## Context

The settings API shipped in Flights 2 and 4 with no screen at all
(`grep -rn knowledge the_one/interfaces/web/static/js/areas/admin*` returned
nothing at reconnaissance). This leg is DD-7, plus the flight's documentation
ownership.

**DD-7 corrects a stale mission claim, and the correction is the interesting
part.** Mission 24's open questions record that "Flight 2's settings API refuses
a `model_id`/`dim` change while any chunk exists (409)". That is **false**:
`EmbeddingSettings` validates `backend`, `model_id` and `dim` against single
allowed values **unconditionally** — a 422, not a 409, and not conditional on
chunk count. The embedding model is **pinned**, not conditionally locked, and
there is no operator path to change it at all. The panel therefore *displays*
embedding and does not offer to change it, and the mission open question is
answered rather than carried into the next mission.

**This leg is the last autonomous one.** Phase 2d's flight-wide review and
commit follows it.

**What this leg does NOT do**: nothing in Studio, nothing in
`the_one/knowledge/` beyond one stale docstring, no new routes.

## Inputs

- `interfaces/web/api.py::update_knowledge_settings` — accepts **only**
  `{"embedding", "chunking", "monitoring"}` (anything else 422s), 422s a
  non-dict section value, merges per section, and applies monitoring **live**
  through an awaited hook.
- `interfaces/web/api.py::get_knowledge_settings` — returns
  `_knowledge_settings_response(conn, current)`, whose shape is **richer than
  the `KnowledgeSettings` model**: the model carries `embedding` / `chunking` /
  `monitoring` only, while the response also carries `vector_store` and `notes`.
  Read the response, not the model.
- `knowledge/settings.py` — `ChunkingSettings.size_chars` `ge=200, le=2000`;
  `overlap_chars` `ge=0` plus a model validator rejecting
  `overlap_chars > size_chars // 2` (**floor** division);
  `MonitoringSettings.watch_enabled` bool default `True`;
  `reconcile_interval_seconds` `ge=10, le=86400`. Every section is
  `extra="forbid"`.
- `static/js/areas/admin.js` — `categories` is `general` / `providers` /
  `tools` (+ dev-only `design-language`); routed `#admin/{category}`;
  `_confirmLeaveImpl`'s `inEditor` is
  `(currentCategory === 'providers' && providerFormMode) || (currentCategory === 'tools' && toolFormMode)`.
- `static/js/areas/admin/system-page.js` — the panel precedent: one **static
  single-string-literal** `innerHTML` for the chrome, `.admin-system-section` /
  `.section-title admin-section-title` / `.admin-system-text` vocabulary, then
  separate wiring functions that fill values in.
- `legs/01-knowledge-inventory.md` **L1-D3** — the seven
  `tests/test_ui_guards.py` invariants, applying verbatim.

## Outputs

- `static/js/areas/admin/knowledge-settings-page.js` — NEW.
- `static/js/areas/admin.js` — the `knowledge` category, its panel branch, and
  the `inEditor` arm.
- `static/index.html` — script tag.
- `static/css/admin.css` (or wherever the admin vocabulary lives) — any new rules.
- `docs/ui-testid-registry.md` — new rows.
- `tests/browser/test_flow_admin_knowledge_settings.py` — NEW (`system` lane,
  via the `test_flow_admin_*` glob).
- **Documentation** (this leg owns the flight's): `CLAUDE.md`,
  `the_one/agents.md`, `SECURITY-MODEL.md`, and one stale docstring in
  `the_one/knowledge/settings.py`.

## Leg Design Decisions

**L4-D1 — One panel, four sections, two of them read-only.** Editable:
`chunking.size_chars`, `chunking.overlap_chars`,
`monitoring.watch_enabled`, `monitoring.reconcile_interval_seconds`.
Read-only: `embedding` (backend, model id, dimensions) and `vector_store`
(backend, dtype). The read-only sections **say why they are read-only** rather
than rendering disabled inputs: the embedding model is pinned because changing
it would invalidate every stored vector, and the vector store record is written
by the app, not chosen by the operator.

**L4-D2 — The panel states the two editable sections' different application
semantics, because they genuinely differ.** Chunking changes apply to **future
indexing only** — existing chunks are never re-chunked in place, so the corpus
stays mixed until a re-index. Monitoring changes apply **live**, on the same
request, through an awaited hook. An operator who does not know this will read
a chunking change as broken. Both sentences belong on the screen, not only in
the docs.

**L4-D3 — Client validation mirrors the server's bounds exactly, and the server
is still the authority.** `size_chars` 200–2000; `reconcile_interval_seconds`
10–86400; `overlap_chars` at most `floor(size_chars / 2)` — **floor**, so at
`size_chars = 1001` the limit is 500, not 500.5. Render the server's 422
`detail` when one arrives anyway; never show a bare status code. The overlap
bound is **cross-field**, so it must re-evaluate when `size_chars` changes, not
only when `overlap_chars` does.

**L4-D4 — The panel participates in dirty-confirm; Leg 3's forms did not, and
the difference is deliberate.** Add a `(currentCategory === 'knowledge' &&
knowledgeDirty)` arm to `_confirmLeaveImpl`'s `inEditor`, bridged by an
`onDirtyChange` callback exactly as the provider and tools editors already do.
Leg 3 deliberately left its two **single-field, submit-immediately** forms out
of this machinery; this is a **multi-field form with an explicit Save**, which
is precisely the shape the dialog exists for — and Administration has trained
the operator to expect the warning. Consistency inside one area matters more
than minimality here.

**L4-D5 — Static chrome, dynamic values.** Follow `system-page.js`: the layout
is one static single-string-literal `innerHTML` (exempt from the sink freeze),
and every value fetched from the API is written with `textContent` or as an
input `value`. L1-D3's seven guards apply — in particular this panel has
**labelled form fields**, so `find_label_for_without_control` and
`find_invalid_describedby_without_field_error` are live: every `<label for="X">`
needs a real `id="X"` in the same file, and any `.is-invalid` control's
`aria-describedby` must name a real `.field-error` id.

**L4-D6 — Documentation is a deliverable, not a footnote.** Five items, each
with a stated reason:

1. **`CLAUDE.md`** — the new `GET /api/knowledge-bases/{kb_id}/search` route and
   both new operator surfaces, in the M24 knowledge-bases paragraph.
2. **`the_one/agents.md`** — the derived-tool-name contract as it now stands
   after DD-17 (the discriminator is unconditional, so a name is
   `f(kb.name, kb.id)` and does not move with the attached set), the
   `compute_tool_names` public seam and its caller set, and DD-5's rename
   rewrite with its partial-failure semantics.
3. **`SECURITY-MODEL.md`** — DD-6's note that the search route sits behind the
   same credential gate as every other route, so an agent holding an external
   credential can reach it. That is the existing trust model, not a new hole,
   and stating it is the point.
4. **DD-14's delete semantics** — a deleted knowledge base leaves a dangling
   `kb_ids` entry that self-heals on the next save, and an inert
   `disabled_tools` entry that never matches a future knowledge base because the
   discriminator includes `kb_id`. Decided behaviour, so it is written down.
5. **The stale docstring found during Leg 4 groundwork**:
   `knowledge/settings.py::VectorStoreSettings` still says
   `update_knowledge_settings` "already 422s any top-level key outside
   `{"embedding", "chunking"}`". Flight 4 added `monitoring` to that set, so the
   sentence is now wrong about the shipped API.

## Acceptance Criteria

- [x] AC-1 — Administration shows a **Knowledge** category, reachable at
      `#admin/knowledge` including on a full page load, and the existing
      categories still route correctly.
- [x] AC-2 — The panel renders current values from
      `GET /api/knowledge-settings` for all four editable settings and for the
      read-only embedding and vector-store records.
- [x] AC-3 — Editing and saving persists: a subsequent `GET` returns the new
      values, and the panel re-renders them after a reload.
- [x] AC-4 — `embedding` and `vector_store` are **read-only, with a stated
      reason on screen**. There is no control that attempts to change either,
      and no disabled input standing in for an explanation.
- [x] AC-5 — The panel states on screen that chunking applies to **future
      indexing only** and that monitoring applies **live**.
- [x] AC-6 — Out-of-range input is refused client-side with a message naming the
      bound, for each of: `size_chars` outside 200–2000,
      `reconcile_interval_seconds` outside 10–86400, and `overlap_chars` above
      `floor(size_chars / 2)`. The overlap check **re-evaluates when
      `size_chars` changes**, not only on overlap edits.
- [x] AC-7 — A server 422 that arrives anyway renders its `detail` text, not a
      bare status code.
- [x] AC-8 — `monitoring.watch_enabled` can be toggled off and on, and the
      change is reflected by a subsequent `GET`.
- [x] AC-9 — Navigating away from the panel with unsaved changes raises the
      confirm dialog; navigating away with no changes does not (L4-D4).
- [x] AC-10 — `tests/test_ui_guards.py` passes (14/14) and the registry
      matches the sources both ways; all seven L1-D3 invariants hold,
      including the two form-specific ones. **Deviation from the "no new
      dynamic-sink entries" wording, accepted by the Flight Director and
      recorded in the flight log**: the L4-D5 chrome, built from concatenated
      string literals per the `system-page.js` house style, classifies as
      "dynamic" under the guard's own single-literal-only exemption regex —
      the same as every other static-chrome page module already in the
      baseline — so one new `DYNAMIC_SINK_BASELINE` entry was required. See
      flight-log.md's Leg 4 implementation entry, "Deviations" item 1, for
      the verified before/after counts.
- [x] AC-11 — `CLAUDE.md`, `the_one/agents.md` and `SECURITY-MODEL.md` carry
      the five documentation items in L4-D6, and the stale `VectorStoreSettings`
      docstring is corrected.
- [x] AC-12 — `make lint` clean, `make test-unit` green, and the `system` browser
      lane green including the new `test_flow_admin_knowledge_settings.py`.

## Verification Steps

- AC-1 through AC-9: `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane
  system -x`. AC-3 and AC-8 read back through the API rather than trusting the
  rendered form. AC-9 follows `test_flow_dirty_confirm.py`'s existing shape.
- AC-10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_ui_guards.py -x --timeout 30`.
- AC-11: read the diff; `grep -n "embedding\", \"chunking\"" the_one/knowledge/settings.py`
  returns nothing.
- AC-12: `make lint`; `make test-unit` verbatim, alone, foreground; the `system`
  lane.

## Implementation Guidance

1. **`knowledge-settings-page.js`**, modelled on `system-page.js`: static chrome
   as one string literal, then a fetch that fills values. Register each new
   testid in `docs/ui-testid-registry.md` as you add it.
2. **Wire the category** into `admin.js`'s `categories` array and its panel
   branch, plus the `inEditor` arm and the `onDirtyChange` bridge (L4-D4).
3. **Validation** per L4-D3, remembering the cross-field re-evaluation.
4. **Browser test** as `test_flow_admin_knowledge_settings.py` so it lands in
   the `system` lane glob.
5. **Documentation** (L4-D6) — all five items. This is the leg's deliverable,
   not a tidy-up at the end.
6. **Gates**: targeted file, `make lint`, `make test-unit` verbatim, `--lane system`.

## Edge Cases

- **`GET /api/knowledge-settings` fails** — render a load-failure state, not an
  empty form that would save defaults over the operator's stored values.
- **A stored value outside current bounds** (an older record, or one written
  before a bound tightened): `load_knowledge_settings` replaces an invalid stored
  value with the default and logs it, so the panel shows the default. Do not add
  repair logic; just do not crash on it.
- **`overlap_chars` exactly at the bound** — `size_chars // 2` is allowed; one
  above is not. Test the boundary, not just the middle.
- **Saving only one section**: the route merges per section, so a PUT carrying
  only `chunking` leaves `monitoring` alone. Send only what changed, or send both
  — but do not send `embedding` or `vector_store`, which would 422.
- **`vector_store` absent from an older response shape** — read defensively;
  it comes from the response envelope, not the `KnowledgeSettings` model.

## Citation Audit

Verified against the working tree on `flight/06-studio-surfaces` at the Leg 3 tip.

| Citation | Status |
|---|---|
| `interfaces/web/api.py::update_knowledge_settings` — `set(data) - {"embedding", "chunking", "monitoring"}` → 422; per-section non-dict → 422; per-section merge; monitoring applied live via an awaited hook | verified |
| `interfaces/web/api.py::get_knowledge_settings` — returns `_knowledge_settings_response(conn, current)`; `KnowledgeSettings` itself carries only `embedding`/`chunking`/`monitoring`, so `vector_store` comes from the response envelope | verified |
| `knowledge/settings.py::ChunkingSettings` — `size_chars` `ge=200, le=2000`; `overlap_chars` `ge=0`; `_validate_overlap` rejects `overlap_chars > size_chars // 2` (floor) with a prose ValueError → 422 | verified |
| `knowledge/settings.py::MonitoringSettings` — `watch_enabled: bool = True`; `reconcile_interval_seconds` `ge=10, le=86400` | verified |
| `knowledge/settings.py::EmbeddingSettings` — `backend`/`model_id`/`dim` each validated against a single allowed value **unconditionally**, no chunk-count condition (DD-7's correction of the mission's "409 while chunks exist") | verified |
| `knowledge/settings.py::VectorStoreSettings` docstring — still says the route 422s keys outside `{"embedding", "chunking"}`, omitting `monitoring` (L4-D6 item 5) | verified |
| `knowledge/settings.py::load_knowledge_settings` — an invalid stored value is logged and replaced with the default rather than raising (an Edge Case's premise) | verified |
| `static/js/areas/admin.js` — `categories` is `general`/`providers`/`tools` plus dev-only `design-language`; `#admin/{category}` routing | verified |
| `static/js/areas/admin.js::_confirmLeaveImpl` — `inEditor` is `(currentCategory === 'providers' && providerFormMode) \|\| (currentCategory === 'tools' && toolFormMode)`; no `knowledge` arm (L4-D4) | verified |
| `static/js/areas/admin/system-page.js::renderSystemPage` — one static single-string-literal `innerHTML` then `fetchBasePrompt`/`mountThemeToggle`/`wireEncryptionRotate` wiring; `.admin-system-section` / `.section-title admin-section-title` / `.admin-system-text` vocabulary (L4-D5's precedent) | verified |
| `legs/01-knowledge-inventory.md` L1-D3 — the seven `tests/test_ui_guards.py` invariants, including the label-for and aria-describedby guards this leg's form fields make live | verified |
| `scripts/run-tests.sh` — the `system` lane glob is `test_flow_admin_*` / `test_flow_provider_*`, so the new file lands there by name | verified |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`; `--lane system`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [ ] Do NOT commit — Phase 2d follows this leg
