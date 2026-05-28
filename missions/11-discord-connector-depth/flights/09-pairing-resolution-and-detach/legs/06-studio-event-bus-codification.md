# Leg: studio-event-bus-codification

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Extract the inline `document.dispatchEvent(new CustomEvent(...))` / `document.addEventListener` pattern across the Studio area into a shared `studio-event-bus` module exposing `emit(name, detail)` and `on(name, handler)`. Refactor all 4 emit sites and 4 listener sites to use the bus. Codify the convention in `agents.md`.

## Context

**Why this leg.** F9 L5 added the 4th `CustomEvent` emit site (`connector-agent-detached`) — pushing the total to 4 emit sites + 4 listener sites across 4 files in `static/js/areas/studio/`. F7 Recommendation #3(c) flagged this as the n=3 threshold for extraction; L5's addition put it past n=4. The pattern is mechanical (one-line emit, one-line listener) but the proliferation creates two problems: (a) typo'd event names cause silent listener-miss bugs (no central registry to typo-check against); (b) listener teardown and dedup discipline are now copy-pasted across files. A shared `studio-event-bus` module gives one place to add observability (e.g. dev-mode logging of every emit) and one place to enforce event-name validity.

**Decision recap (flight §8)**: extract a shared module; refactor all 8 sites; cite F7 Rec #3(c) as the trigger (no n-threshold framing per cycle-1 architect — drop the threshold rule from the convention text).

**Module shape** (mirrors small-module conventions in `static/js/areas/studio/`):

```javascript
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, {detail: detail}));
  }

  function on(name, handler) {
    document.addEventListener(name, handler);
  }

  window.App.studio.eventBus = {emit: emit, on: on};
})();
```

**Why so thin**: the bus is intentionally a one-line abstraction. Its value is **the named seam**, not the layer's logic — a shared site to add logging / event-name validation / unit-test capture if those grow needed later, without changing every caller.

**No `off` (removeEventListener)**: the existing codebase NEVER tears down `document.addEventListener` handlers for Studio events. The precedent at `connectors-tab.js:73` explicitly documents why ("Registered ONCE at module init — registering inside `_renderAccountTile` would leak handlers on every re-render"). L5 followed the same pattern. L6 preserves it — `off` is not in the API. If a future need arises (e.g. dev-mode hot-reload), add then.

**Event-name freeze**: the 4 event names stay byte-identical — `connector-account-always-listen-changed`, `connector-account-pool-warmed`, `connector-agent-detached`, `connector-account-discoverable-refresh-requested`. No renames. The bus just hides the dispatch/listen mechanics; consumers still know the strings.

**Inventory** (verified at design time via grep on `the_one/interfaces/web/static/js/areas/studio/`):

**4 emit sites** (all in `connector-account-editor.js`):
| Line | Event |
|------|-------|
| 1092 | `connector-account-always-listen-changed` |
| 1741 | `connector-account-pool-warmed` |
| 2956 | `connector-agent-detached` (NEW from L5) |
| 3348-3349 | `connector-account-discoverable-refresh-requested` |

**4 listener sites** (across 4 files):
| File:Line | Event |
|-----------|-------|
| `studio.js:360` | `connector-agent-detached` (NEW from L5) |
| `connectors-tab.js:73` | `connector-account-always-listen-changed` |
| `discoverable-dropdown.js:697` | `connector-account-pool-warmed` |
| `discoverable-dropdown.js:719-722` | `connector-account-discoverable-refresh-requested` |
| `connector-account-editor.js:3379` | `connector-account-pool-warmed` |

(That's actually 5 listener sites — `discoverable-dropdown.js` has two, and `connector-account-editor.js` has its own listener for `connector-account-pool-warmed`. The recon scan missed the 5th. L6 refactors all 5.)

**Script-tag load order**: the new `studio-event-bus.js` must load BEFORE every consumer (i.e., before `connector-account-editor.js`, `connectors-tab.js`, `discoverable-dropdown.js`, `studio.js`). Place the `<script>` tag adjacent to the existing studio modules in `static/index.html` (the same area where `message-bubble.js` lives — there's likely a `<script src="js/areas/studio/...">` block).

**agents.md convention**: add a `studio-event-bus` convention citation in `the_one/agents.md`. The citation is paragraph-form (matches sibling conventions). Cite F7 Rec #3(c) as the trigger. NO n-threshold framing per cycle-1 architect.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1092` — emit site 1 (always-listen-changed).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1741` — emit site 2 (pool-warmed).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2956` — emit site 3 (agent-detached, L5).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:3348-3349` — emit site 4 (discoverable-refresh-requested).
- `the_one/interfaces/web/static/js/areas/studio.js:360` — listener site 1 (agent-detached, L5).
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:73` — listener site 2 (always-listen-changed).
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js:697` — listener site 3 (pool-warmed).
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js:719-722` — listener site 4 (discoverable-refresh-requested).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:3379` — listener site 5 (pool-warmed).
- `the_one/interfaces/web/static/index.html` — script-tag load site (the `static/index.html` template hosting studio JS modules).
- `the_one/agents.md` — conventions catalog (existing conventions at lines 30-273+; new citation appends at the end).
- `tests/browser/test_flow_*.py` — existing browser tests are the regression net for the event wiring; they don't import the bus directly but their assertions exercise the live broadcast → listener → render path.

## Outputs

- NEW `the_one/interfaces/web/static/js/areas/studio/studio-event-bus.js` — IIFE exposing `App.studio.eventBus.emit(name, detail)` and `App.studio.eventBus.on(name, handler)`.
- `the_one/interfaces/web/static/index.html` — `<script>` tag for the new module, placed BEFORE all consumer modules in the load order.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — 4 emit sites + 1 listener site refactored to use `App.studio.eventBus`.
- `the_one/interfaces/web/static/js/areas/studio.js` — 1 listener site refactored.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — 1 listener site refactored.
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — 2 listener sites refactored.
- `the_one/agents.md` — append `studio-event-bus` convention citation.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L6 progress entry.

NO new tests. The 4 events are exercised by existing browser tests (`test_flow_chat_pending_approval.py`, `test_flow_connector_account_detach.py` from L5, plus the F7-era tests for always-listen and pool-warmed). The refactor is purely mechanical — behavior unchanged. The existing tests are the regression net.

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/areas/studio/studio-event-bus.js` exists, is an IIFE, exposes `window.App.studio.eventBus = {emit, on}` with the two functions as defined in the Context "Module shape" snippet.
- [ ] `the_one/interfaces/web/static/index.html` includes a `<script src="...studio-event-bus.js">` tag, loaded BEFORE all the consumer modules.
- [ ] All 4 emit sites in `connector-account-editor.js` (lines 1092, 1741, 2956, 3348-3349) use `App.studio.eventBus.emit(name, detail)` — NO remaining `document.dispatchEvent(new CustomEvent(...))` calls in the file (verified by grep).
- [ ] All 5 listener sites refactored to use `App.studio.eventBus.on(name, handler)` — NO remaining `document.addEventListener('connector-...', ...)` calls in the studio area files (verified by grep).
- [ ] **Carve-out for the bus module itself**: `studio-event-bus.js` IS allowed to contain the literal `document.dispatchEvent` and `document.addEventListener` calls — that IS its implementation. The grep verifying "no remaining inline calls" excludes this file.
- [ ] Event names are byte-identical to pre-L6 — no renames.
- [ ] Existing browser tests pass unchanged. Specifically:
  - `tests/browser/test_flow_connector_account_detach.py` (L5) — exercises `connector-agent-detached`.
  - `tests/browser/test_flow_chat_pending_approval.py` (L4) — does NOT touch studio events directly but the page load exercises the connector-account-editor module init.
  - Any F7/F8 browser test that exercises `connector-account-always-listen-changed` or `connector-account-pool-warmed` or `connector-account-discoverable-refresh-requested`.
- [ ] `the_one/agents.md` has a new `studio-event-bus` convention entry, paragraph-form, citing F7 Rec #3(c) as the trigger; NO n-threshold framing.
- [ ] Existing pre-L4 / L5 browser tests still pass.
- [ ] No new tests (the refactor is mechanical; existing tests are the regression net).

## Verification Steps

```bash
# Verify all CustomEvent / dispatchEvent calls are gone from studio/
docker exec the-one bash -lc 'grep -rn "document\.dispatchEvent\|new CustomEvent\|document\.addEventListener" the_one/interfaces/web/static/js/areas/studio*.js the_one/interfaces/web/static/js/areas/studio/ 2>/dev/null'
# Expected: zero matches (or only matches INSIDE studio-event-bus.js itself).

# Run browser tests that exercise the events
docker exec the-one pytest tests/browser/test_flow_connector_account_detach.py tests/browser/test_flow_chat_pending_approval.py -x --timeout 120 -v

# Run all studio-related browser tests
docker exec the-one pytest tests/browser -k "connector or chat or studio" -x --timeout 120 -v

# Full backend suite (post-L5 baseline: 2721)
docker exec the-one pytest --timeout 60 -q
```

Expected: green; suite count unchanged (no new tests).

## Implementation Guidance

### Sub-step A — Create the bus module

Create `the_one/interfaces/web/static/js/areas/studio/studio-event-bus.js` with the exact snippet from the Context "Module shape" section. Add a 4-line header comment documenting the F7 Rec #3(c) / F9 L6 lineage:

```javascript
// App.studio.eventBus — Studio cross-module CustomEvent bus.
//
// Shared seam for inter-module event dispatch within the Studio area.
// F7 Recommendation #3(c) triggered the extraction; F9 L6 lands it
// alongside the 4th emit site (connector-agent-detached, L5).
//
// Public API:
//   App.studio.eventBus.emit(name, detail)
//   App.studio.eventBus.on(name, handler)
//
// No `off` primitive — Studio listeners are registered ONCE at module
// init (matches connectors-tab.js:73 precedent) and never torn down.
//
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, {detail: detail}));
  }

  function on(name, handler) {
    document.addEventListener(name, handler);
  }

  window.App.studio.eventBus = {emit: emit, on: on};
})();
```

### Sub-step B — Add the script tag

Edit `the_one/interfaces/web/static/index.html`. Find the script-tag block where the existing studio modules are loaded (search for one of: `connector-account-editor.js`, `connectors-tab.js`, `discoverable-dropdown.js`, `studio.js`). Add the new tag ABOVE the first studio-area script — load order matters because the consumers reference `App.studio.eventBus.{emit,on}` at module init.

```html
<script src="/static/js/areas/studio/studio-event-bus.js"></script>
```

**Absolute path with leading `/`** — verified against existing tags at `static/index.html:40-55` which all use `/static/...`. **Insertion point**: at line 47, immediately after the chat.js tag (line 46) and BEFORE the first studio module (`stub-knowledge.js` at line 47). This puts the bus before all consumers.

### Sub-step C — Refactor emit sites

Edit `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`. Each emit site converts FROM:

```javascript
document.dispatchEvent(new CustomEvent('event-name', {detail: {key: value, ...}}));
```

TO:

```javascript
App.studio.eventBus.emit('event-name', {key: value, ...});
```

(The second argument to `emit` IS the detail dict directly — `emit` wraps it in `{detail: ...}` internally.)

Specific sites:
- **Line 1092** (`connector-account-always-listen-changed`): keep the detail object verbatim.
- **Line 1741** (`connector-account-pool-warmed`): keep the detail object verbatim.
- **Line 2956** (`connector-agent-detached`, L5): keep the `{agent_name, account_id}` detail.
- **Line 3348-3349** (`connector-account-discoverable-refresh-requested`): note this is a two-line emit currently; collapses to one line.

For multi-line emit sites with extra spread (e.g. `{detail: someObj}` where `someObj` is a complex expression), the conversion is still `App.studio.eventBus.emit('event-name', someObj)`.

### Sub-step D — Refactor listener sites

Each listener site converts FROM:

```javascript
document.addEventListener('event-name', handler);
```

TO:

```javascript
App.studio.eventBus.on('event-name', handler);
```

(The `event` object passed to the handler is unchanged — it's still a standard CustomEvent; `event.detail` works as before.)

Sites:
- `studio.js:360` (`connector-agent-detached`).
- `connectors-tab.js:73` (`connector-account-always-listen-changed`).
- `discoverable-dropdown.js:697` (`connector-account-pool-warmed`).
- `discoverable-dropdown.js:719-722` (multi-line `addEventListener` call — collapses to single line if the handler is a single identifier).
- `connector-account-editor.js:3379` (`connector-account-pool-warmed`).

The handler functions themselves DO NOT change — only the registration call does.

### Sub-step E — agents.md convention citation

Insert into `the_one/agents.md` after the `encryptor-parameter-receive-but-not-consume` convention block (currently ending around line 396) and BEFORE the `## Subsystem contracts` heading (~line 398). The file's project-conventions section is bounded; appending at EOF would land inside testing/performance sections. Place inside the project-conventions zone:

```markdown
### `studio-event-bus`

Studio-area cross-module communication uses the shared `App.studio.eventBus` (defined in `the_one/interfaces/web/static/js/areas/studio/studio-event-bus.js`) — `emit(name, detail)` and `on(name, handler)` — rather than inline `document.dispatchEvent(new CustomEvent(...))` and `document.addEventListener(...)` calls. F7 Recommendation #3(c) flagged the inline pattern as the trigger; F9 L6 extracted the bus when L5 added the 4th emit site. The bus is intentionally a thin one-line abstraction — its value is the named seam (a place to add dev-mode logging or event-name validation later), not the layer's logic. Listeners register ONCE at module init and are never torn down (matches the `connectors-tab.js:73` precedent which documents the per-render-leak rationale).
```

(Match the surrounding convention paragraphs' tone.)

### Sub-step F — Verify

Run the grep at the top of Verification Steps to confirm all CustomEvent / addEventListener calls are gone from studio. Run the browser tests.

If any browser test fails because the load order is wrong (consumer modules running before the bus), confirm the script-tag placement. The bus module has no dependencies — it can load first.

### Sub-step G — Flight log

```
### {date} — L6 studio-event-bus-codification (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `the_one/interfaces/web/static/js/areas/studio/studio-event-bus.js` — NEW module; `App.studio.eventBus.emit/on`.
- `the_one/interfaces/web/static/index.html` — script tag for the bus, loaded before consumer modules.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — 4 emit sites + 1 listener site refactored.
- `the_one/interfaces/web/static/js/areas/studio.js` — 1 listener site refactored.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — 1 listener site refactored.
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — 2 listener sites refactored.
- `the_one/agents.md` — added `studio-event-bus` convention citation.

**Test outcomes**: existing browser tests pass unchanged. Grep confirms no remaining inline CustomEvent / addEventListener calls in studio area files.

**No new tests**: refactor is mechanical; existing browser tests are the regression net.

**Anomalies**: {document any}
```

## Edge Cases

- **A consumer module's IIFE runs BEFORE the bus module loads** — `App.studio.eventBus` would be undefined and the `emit`/`on` call would throw. **Mitigation**: load order in `static/index.html` is the contract. Verify by reading the HTML after edits to confirm `studio-event-bus.js` precedes all consumers.
- **A third-party script (or future fan-out) wants to listen for one of these events but doesn't have `App.studio.eventBus` available** — they can still use `document.addEventListener('event-name', ...)` directly. The bus does NOT route through a private channel; it uses `document` as the underlying transport. Both interfaces produce/consume the same events. Document this in the bus module's docstring.
- **Event-name typo at an emit site** — `emit('connctor-agent-detached', ...)` silently fires a different event that no one listens for. The bus does NOT validate names — adding validation would mean keeping a registry, which is out of scope for this leg. Future leg can add `__DEBUG__`-gated validation.
- **A new listener site is added AFTER L6 lands** — it MUST use `App.studio.eventBus.on(...)` to satisfy the convention. The agents.md citation is the operator-facing reminder. A grep CI check could enforce, but L6 doesn't ship one (kept tight scope).
- **The bus is loaded but never used** — no-op; harmless. The IIFE just defines `App.studio.eventBus` and exits.
- **`emit` is called with `undefined` detail** — `new CustomEvent(name, {detail: undefined})` creates an event with `event.detail === undefined`. Existing consumers tolerate this (or didn't depend on detail). Not changing semantics.
- **Tests run in headless Chromium without `document`** — n/a; browser tests always have `document`.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/studio-event-bus.js` — NEW, ~25 LOC.
- `the_one/interfaces/web/static/index.html` — +1 line.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — 5 sites edited (~5-10 LOC net).
- `the_one/interfaces/web/static/js/areas/studio.js` — 1 site edited.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — 1 site edited.
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — 2 sites edited.
- `the_one/agents.md` — +1 paragraph (~10 LOC).
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — L6 entry.

Estimated total: ~50-60 LOC of meaningful change (the bus module + the convention paragraph) plus ~10 sites of mechanical conversion.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Grep confirms zero remaining inline CustomEvent / addEventListener calls in studio area
- [ ] Existing browser tests pass unchanged
- [ ] Update flight-log.md with L6 progress entry (template above)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

9 citations verified against current code at leg design time (post-L5):
- `connector-account-editor.js:1092` (always-listen-changed emit) — OK
- `connector-account-editor.js:1741` (pool-warmed emit) — OK
- `connector-account-editor.js:2956` (agent-detached emit, L5-introduced) — OK
- `connector-account-editor.js:3348-3349` (discoverable-refresh-requested emit) — OK
- `connector-account-editor.js:3379` (pool-warmed listener) — OK
- `studio.js:360` (agent-detached listener, L5-introduced) — OK
- `connectors-tab.js:73` (always-listen-changed listener) — OK
- `discoverable-dropdown.js:697` (pool-warmed listener) — OK
- `discoverable-dropdown.js:719-722` (discoverable-refresh-requested listener) — OK
