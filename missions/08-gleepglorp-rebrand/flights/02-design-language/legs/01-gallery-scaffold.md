# Leg: 01-gallery-scaffold

**Status**: landed
**Flight**: [Design Language — Glass + Control Panel](../flight.md)

## Objective

Land the design-language gallery page substrate: a new `GET /api/config` server endpoint that exposes `{dev_mode, version}`, a boot-blocking client fetch that populates `window.App.config` before any area initializes, a conditional `Design Language` category in the Admin sidebar gated on `App.config.dev_mode`, and an empty gallery page scaffold ready for Leg 02 to populate. Nothing aesthetic ships in this leg — pure scaffolding.

## Context

- Leg 1 of 6. Flight is `in-flight` on branch `flight/02-design-language` from base commit `17c63e3`.
- Flight design resolves: boot-blocking client fetch (not render-time gate), per-section subdirectory at `static/js/areas/admin/design-language/`, the validIds-rejects-then-syncUrlFromState-corrects mechanism for the dev-mode-off fallback.
- The MCP `clientInfo.name` preservation contract (Flight 1) — `/api/config` exposes `the_one.__version__` (dynamic interpolation, not hardcoded) so version bumps stay free.
- M07 OAuth pause-snapshot path (`api.py:1436, 1821`) is unrelated to this leg.

## Inputs

- `/api/config` does NOT exist yet — net new route
- `/api/info` at `app.py:919-921` already exists and returns `{"version": "0.1.0", "base_prompt": BASE_PROMPT}` with a HARDCODED, STALE version literal (actual `__version__` is `0.2.0`). This leg opportunistically fixes the stale version in `/api/info` per the Flight 1 debrief "encouraged at design-review caught moments" pattern. `/api/info` remains a parallel legacy endpoint (carries `base_prompt`, used by selftest and other internal callers) — not deprecated in this leg.
- `window.App.config` does NOT exist on the client — net new namespace
- `app.js:225-230` `DOMContentLoaded` handler currently synchronous; needs to wrap in fetch-then-switch
- `admin.js:108-117` `categories` array lives in `init()` (the area's first-activation closure)
- `admin.js:84` `validIds` array lives in `hydrateState` (sibling method); these are TWO separate closures, not one
- `docker-compose.yml:55` sets `THE_ONE_DEV_MODE=true` for the dev container — dev_mode ON is the development DEFAULT; verifying the OFF behavior requires temporarily overriding this env var
- `static/js/areas/admin/` directory exists with 7 sub-modules (`provider-editor.js`, `tools-editor.js`, etc.); no `design-language/` subdirectory yet (Leg 02 creates it when adding the first section module — this leg does NOT create the empty subdirectory)
- `index.html:54-60` lists admin sub-modules; `admin.js` at `:60` loads last so namespaces are populated before `App.registerArea({id: 'admin', ...})` runs
- `Makefile:80-93` `verify-serving` target enumerates admin sub-modules in a shell `for f in ...` loop — must be updated to include the new `design-language-page.js`

## Outputs

- `the_one/interfaces/web/api.py` — new `@router.get("/config")` handler + `from the_one import __version__` import
- `the_one/interfaces/web/app.py` — `/api/info` at line 921 rewritten to use `__version__` instead of hardcoded `"0.1.0"`; `from the_one import __version__` added to the imports
- `the_one/interfaces/web/static/js/app.js` — `DOMContentLoaded` handler rewritten to boot-block on `/api/config`; `window.App.config` populated before first `switchTo(...)`
- `the_one/interfaces/web/static/js/areas/admin.js` — `categories` push of `{id: 'design-language', label: 'Design Language'}` conditional on `window.App.config.dev_mode`; `validIds` push of `'design-language'` under same condition; `renderContent()` dispatches to `App.admin.renderDesignLanguagePage(contentEl)` for the new category
- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` — new container module exporting `App.admin.renderDesignLanguagePage(container)`; renders page header + empty section-scroll container body. The per-section subdirectory at `admin/design-language/` is NOT created in this leg — Leg 02 creates it when it adds the first section module
- `the_one/interfaces/web/static/index.html` — new `<script src="/static/js/areas/admin/design-language-page.js">` line inserted before the `admin.js` script tag
- `Makefile` — `verify-serving` target's admin-sub-module shell-loop updated to include `admin/design-language-page.js`

## Acceptance Criteria

- [ ] `GET /api/config` returns `200` with JSON body `{"dev_mode": <bool>, "version": "<__version__ value>"}`; verified by `curl -s http://localhost:8484/api/config` returning a JSON object containing exactly those two keys
- [ ] The version field reads from `the_one.__version__` (imported at module top) — NOT hardcoded; verified by `grep -nE '"0\.[0-9]+\.[0-9]+"' the_one/interfaces/web/api.py the_one/interfaces/web/app.py` showing no version-literal matches added by this leg (and confirming `/api/info`'s prior hardcoded `"0.1.0"` is gone)
- [ ] `GET /api/info` returns `version` matching `the_one.__version__` (e.g., `"0.2.0"`) — verified by `curl -s http://localhost:8484/api/info` showing the dynamic value, not `"0.1.0"`
- [ ] In the dev container (default state: `THE_ONE_DEV_MODE=true` per `docker-compose.yml:55`), `GET /api/config` returns `dev_mode: true`. To verify the `false` case, temporarily edit `docker-compose.yml:55` to `THE_ONE_DEV_MODE=false`, `make restart`, then revert
- [ ] `window.App.config` is populated with the fetched `{dev_mode, version}` object before any `area.init()` call runs — verified by setting a `console.assert` or `if (!window.App.config) throw new Error(...)` early in `admin.init` and confirming no error fires on cold load
- [ ] Failed `/api/config` fetch defaults `window.App.config` to `{dev_mode: false, version: 'unknown'}` and boot continues — verified by adding a temporary network block in DevTools and confirming the app still loads (then removed)
- [ ] In dev mode (default), the Admin sidebar shows 4 categories: General, LLM Providers, Built-in Tools, Design Language (in that order) — verified by visiting `#admin` and inspecting the sidebar `.section-nav-item` elements
- [ ] With dev mode temporarily off (per the env override above), the Admin sidebar shows exactly the 3 existing categories — verified the same way
- [ ] In dev mode, clicking the Design Language category renders the empty gallery page with title "Design Language" and an empty scroll container — verified visually
- [ ] In dev mode, direct-loading `#admin/design-language` resolves to the gallery (not a fallback) — verified by entering the URL directly and confirming the page renders
- [ ] With dev mode off, direct-loading `#admin/design-language` falls back to the default `system` category AND `history.replaceState` rewrites the URL hash to `#admin/system` — verified by entering the URL and inspecting `location.hash` post-load
- [ ] `App.admin.renderDesignLanguagePage` is registered on `window.App.admin` namespace via the existing pattern (IIFE wrapping, `window.App.admin = window.App.admin || {};` bootstrap, single-function export)
- [ ] `Makefile` `verify-serving` admin-sub-module loop includes `admin/design-language-page.js` and the loop passes after `make rebuild`
- [ ] `window.App.config` defensively defaults to safe values if `/api/config` returns `null` or a non-object body, OR if the fetch fails — verified by inspection of the `app.js` `.then`/`.catch` chain
- [ ] All existing tests still pass on the narrow test gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10`
- [ ] Flight log updated with leg progress entry; leg status set to `landed`

## Verification Steps

1. **Server endpoint shape**:
   ```bash
   docker exec the-one curl -s http://localhost:8484/api/config | python -m json.tool
   ```
   Expect JSON object with `dev_mode` (bool) and `version` (string) keys.

2. **Version dynamic interpolation**:
   ```bash
   grep -n 'from the_one import __version__\|the_one.__version__' the_one/interfaces/web/api.py
   ```
   Expect at least one match in the diff added by this leg.

3. **Dev mode on**:
   ```bash
   # Stop the running container, restart with THE_ONE_DEV_MODE=true
   # (the existing make rebuild flow does not set this; manual override via
   # docker-compose env injection or by editing the running container env)
   # Then load the app and confirm 4 sidebar categories
   ```

4. **Dev mode off (default state)**:
   - Load the app at `http://localhost:8484/` after `make rebuild`
   - Admin sidebar shows 3 categories (no Design Language)
   - Visit `http://localhost:8484/#admin/design-language` — expect the page to land on the General category and URL to become `#admin/system`

5. **Empty gallery page (dev mode)**:
   - With dev mode on, navigate to `#admin/design-language` — expect a page with `<h1 class="page-title">Design Language</h1>` and an empty scroll-container `<div>` below

6. **Boot-block resilience**:
   - Open DevTools → Network → block `/api/config`
   - Hard-refresh the page
   - Expect the app to still load (Chat area visible by default); confirm `window.App.config` equals `{dev_mode: false, version: 'unknown'}` in console

7. **Narrow test gate**:
   ```bash
   docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10
   ```
   Expect all 56 to pass (matching Flight 1 baseline).

## Implementation Guidance

1. **Server endpoint — `the_one/interfaces/web/api.py`**

   Add the import at the top with the other `the_one` imports:
   ```python
   from the_one import __version__
   ```

   Add the route handler. Place it near the top of the route registrations (after the helper functions, before the entity routes) so it's logically grouped as a metadata endpoint. A reasonable location is right after the `_provider_repo` helpers, before `@router.get("/tools")` at line 128:
   ```python
   @router.get("/config")
   async def get_config() -> dict[str, Any]:
       """Client-visible configuration — dev mode flag + version.

       Fetched once at boot by the JS client (app.js DOMContentLoaded
       handler) and cached on window.App.config. The dev_mode flag gates
       the dev-mode-only Design Language Admin category (Mission 08 F2).
       """
       return {"dev_mode": settings.dev_mode, "version": __version__}
   ```

2. **Server `/api/info` opportunistic fix — `the_one/interfaces/web/app.py`**

   Add at the top with the other `the_one` imports:
   ```python
   from the_one import __version__
   ```

   Rewrite line 919-921:
   ```python
   @app.get("/api/info")
   async def info() -> dict[str, Any]:
       return {"version": __version__, "base_prompt": BASE_PROMPT}
   ```

   This closes the stale `"0.1.0"` hardcoded version that Flight 1 missed (its brand-text sweep didn't cover `/api/info`).

3. **Client boot — `the_one/interfaces/web/static/js/app.js`**

   Rewrite the `DOMContentLoaded` handler (currently lines 225-230):
   ```js
   document.addEventListener('DOMContentLoaded', function () {
     renderTopBar();
     // Boot-block on /api/config so window.App.config is populated before
     // any area.init() runs. Areas read App.config.dev_mode in their init
     // closures (e.g. admin's sidebar categories list).
     fetch('/api/config')
       .then(function (r) { return r.json(); })
       .then(function (config) {
         // Defensive default: a malformed 200 (null body, truncated JSON
         // that parses to a non-object) won't crash downstream readers.
         window.App.config = (config && typeof config === 'object')
           ? config
           : { dev_mode: false, version: 'unknown' };
       })
       .catch(function () {
         // Failed fetch must not break boot. Defaults to non-dev,
         // unknown-version so dev-mode-gated features stay off.
         window.App.config = { dev_mode: false, version: 'unknown' };
       })
       .then(function () {
         var parsed = parseHash(location.hash);
         var area = (parsed.area && areas[parsed.area]) ? parsed.area : 'chat';
         switchTo(area, parsed.sub);
       });
   });
   ```

   Note: `.catch` returns a fulfilled promise (returns `undefined`), so the subsequent `.then` runs in both success and failure paths — the `switchTo` always fires.

4. **Admin area integration — `the_one/interfaces/web/static/js/areas/admin.js`**

   In `init()` (around line 107), modify the `categories` array initialization to push the conditional 4th entry:
   ```js
   var categories = [
     { id: 'system', label: 'General' },
     { id: 'providers', label: 'LLM Providers' },
     { id: 'tools', label: 'Built-in Tools' }
   ];
   // Mission 08 F2 L1: dev-mode-only Design Language gallery category.
   // Boot-blocking fetch in app.js populates window.App.config before init.
   if (window.App && window.App.config && window.App.config.dev_mode) {
     categories.push({ id: 'design-language', label: 'Design Language' });
   }
   ```

   In `hydrateState` (around line 84), modify the `validIds` array similarly:
   ```js
   var validIds = ['system', 'providers', 'tools'];
   if (window.App && window.App.config && window.App.config.dev_mode) {
     validIds.push('design-language');
   }
   if (validIds.indexOf(sub) === -1) return;
   ```

   In `renderContent()` (around line 243), add the dispatch branch:
   ```js
   } else if (currentCategory === 'design-language') {
     App.admin.renderDesignLanguagePage(contentEl);
   }
   ```

5. **Gallery container module — `static/js/areas/admin/design-language-page.js`**

   Match the existing sub-module pattern (see `system-page.js:1-5`):
   ```js
   (function () {
     'use strict';
     window.App = window.App || {};
     window.App.admin = window.App.admin || {};

     function renderDesignLanguagePage(container) {
       container.innerHTML =
         '<div class="page-header">' +
           '<h1 class="page-title">Design Language</h1>' +
         '</div>' +
         '<div class="admin-content-body design-language-sections" id="design-language-sections">' +
         '</div>';
       // Leg 02 will populate #design-language-sections with per-section
       // render() invocations. This scaffold lands the container only.
     }

     window.App.admin.renderDesignLanguagePage = renderDesignLanguagePage;
   })();
   ```

6. **Script load order — `static/index.html`**

   Insert the new `<script>` tag for `design-language-page.js` BEFORE the `admin.js` script tag, grouped with the other admin sub-modules. Concretely, after `provider-models.js` (line 59) and before `admin.js` (line 60):
   ```html
   <script src="/static/js/areas/admin/provider-models.js"></script>
   <script src="/static/js/areas/admin/design-language-page.js"></script>
   <script src="/static/js/areas/admin.js"></script>
   ```

   Note: the empty per-section subdirectory `static/js/areas/admin/design-language/` is NOT created in this leg. Leg 02 creates it organically when adding the first section module — avoids checking in an empty directory (the project does not use `.gitkeep` conventions; `find . -name .gitkeep` returns zero hits).

7. **`Makefile` `verify-serving` update**

   The target at `Makefile:80-93` enumerates admin sub-modules in a shell `for f in ...` loop and curls each from the running container to confirm it's served. Add `admin/design-language-page.js` to that loop:
   ```make
   @for f in admin.js admin/system-page.js admin/providers-grid.js admin/provider-editor.js admin/provider-models.js admin/tools-form-helpers.js admin/tools-grid.js admin/tools-editor.js admin/design-language-page.js layout/section-nav.js; do \
   ```

8. **Verification flow**

   Run the narrow gate first to confirm no regression. Then `make rebuild` to bake the new files into the container (this also fires the updated `verify-serving` and will fail loud if the new file isn't being served). Then run the verification steps above (server endpoint, sidebar with dev mode on/off, boot-block resilience).

## Edge Cases

- **Dev mode toggled mid-session**: User toggles `THE_ONE_DEV_MODE` and restarts the server but keeps the existing tab open. The cached `App.config` is stale. **Accepted**: hard-refresh is required (documented). Tab reload re-fetches.
- **`/api/config` returns malformed JSON**: The `.json()` parser throws; `.catch` catches and defaults `App.config`. Boot completes.
- **`__version__` import fails or is missing**: The endpoint module-import-time fails, route never registers. Unlikely (Flight 1 already established the dynamic-version convention with `cli.py`); if it happens, fix the underlying import error.
- **Race between admin.init and `App.config` write**: Cannot happen — boot-block ensures `App.config` is set before `switchTo` (which invokes `init`) is called.
- **Direct-load `#admin/design-language` BEFORE the boot-block fetch resolves**: Cannot happen — `switchTo` is inside the boot-block's `.then`. The hash is parsed only after `App.config` is set.
- **Hashchange / in-app navigation to `#admin/design-language` post-boot**: The `hashchange` listener at `app.js:219-223` calls `switchTo` directly with no `App.config` re-check. By that time `App.config` is already populated from boot, so this is fine. Documented here so the reasoning is captured.
- **`/api/info` callers expecting `version: "0.1.0"` literal**: Grep `the_one/ tests/ docs/` for the literal `"0.1.0"` — no consumer-side hits expected (Flight 1 debrief did not surface any), and the project's actual version has been 0.2.0+ for a while. The risk is bounded.
- **`validIds` rejection but URL not corrected**: `syncUrlFromState` (app.js:123-130) runs unconditionally after `hydrateState` and rewrites the hash from `serializeState()`. If `currentCategory` stays at `'system'` (the constructor default), `serializeState` returns `'system'`, and the hash becomes `#admin/system`. Verified by reading `app.js:213-220` (cross-area path) and `:140-146` (same-area path).

## Files Affected

- `the_one/interfaces/web/api.py` — add `from the_one import __version__` import + `GET /api/config` route handler
- `the_one/interfaces/web/app.py` — add `from the_one import __version__` import; rewrite `/api/info` (line 921) to use `__version__` instead of hardcoded `"0.1.0"`
- `the_one/interfaces/web/static/js/app.js` — rewrite `DOMContentLoaded` handler (lines 225-230) to boot-block on `/api/config`; defensive defaulting on malformed success path
- `the_one/interfaces/web/static/js/areas/admin.js` — conditional push to `categories` (in `init()`, around line 117) and `validIds` (in `hydrateState`, around line 84) gated on `App.config.dev_mode`; `renderContent()` dispatch branch for `design-language` (around line 243)
- `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` — NEW file, container module exporting `App.admin.renderDesignLanguagePage`
- `the_one/interfaces/web/static/index.html` — NEW `<script src="/static/js/areas/admin/design-language-page.js">` line before `admin.js`
- `Makefile` — `verify-serving` admin-sub-module shell-loop updated to include `admin/design-language-page.js`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Narrow test gate passing
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in `flight.md` (the Legs list under In-Flight, AND the corresponding Checkpoint under In-Flight → Checkpoints)
- [ ] Do NOT commit yet — orchestrator commits all autonomous legs together in Phase 2d
- [ ] Signal `[HANDOFF:review-needed]` (handled by Flight Director, not Developer)

## Citation Audit

12 citations verified against current code at leg design time:
- `app.js:225-230` `DOMContentLoaded` handler — confirmed at lines 225-230 (`document.addEventListener('DOMContentLoaded', function () { renderTopBar(); ... switchTo(area, parsed.sub); });`)
- `admin.js:108-117` `categories` array — confirmed at lines 108-117 (3-entry hardcoded array)
- `admin.js:84` `validIds` array — confirmed at line 84 (`var validIds = ['system', 'providers', 'tools'];`)
- `admin.js:243-250` `renderContent` dispatch — confirmed (`if (currentCategory === 'system') ... else if (currentCategory === 'providers') ... else if (currentCategory === 'tools') ...`)
- `app.js:123-130` `syncUrlFromState` — confirmed (uses `history.replaceState(null, '', '#' + areaId + '/' + serialized);`)
- `api.py:36` `router = APIRouter(prefix="/api")` — confirmed at line 36
- `api.py:128` first route `@router.get("/tools")` — confirmed at line 128
- `system-page.js:1-5` namespace bootstrap pattern — confirmed (`window.App = window.App || {}; window.App.admin = window.App.admin || {};`)
- `index.html:54-60` admin sub-module script tag block — confirmed (insertion point between line 59 `provider-models.js` and line 60 `admin.js`)
- `app.py:919-921` `/api/info` endpoint with stale hardcoded `"version": "0.1.0"` — confirmed (rewrite in scope of this leg per Flight 1 debrief opportunistic-fix pattern)
- `docker-compose.yml:55` `THE_ONE_DEV_MODE=true` — confirmed (dev container default is dev-mode ON; OFF case requires temporary env override to verify)
- `Makefile:80-93` `verify-serving` target with admin-sub-module shell-loop — confirmed (loop will be updated to include `design-language-page.js`)
- No `.gitkeep` convention in the project (`find . -name .gitkeep -not -path "./.git/*"` returns zero) — switched approach: empty subdirectory deferred to Leg 02
