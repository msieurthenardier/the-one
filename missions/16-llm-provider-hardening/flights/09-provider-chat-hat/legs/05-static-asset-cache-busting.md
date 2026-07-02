# Leg: static-asset-cache-busting

**Status**: completed
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

> **Completed (2026-07-02, ships in 0.2.14).** `index()` appends `?v={__version__}` to all
> 61 `/static` js/css refs and serves the HTML with `Cache-Control: no-store`. Verified via
> tests (4 new, 31 total) + manual curl (`no-store` header, all refs versioned, versioned
> URL → 200). Cross-upgrade cache-busting is automatic from 0.2.14 onward (the 0.2.13→0.2.14
> hop may still need one manual refresh since 0.2.13's HTML was cached without no-store).

## Objective
Cache-bust the front-end static assets per release so UI changes appear immediately after
an in-place upgrade, instead of the WebView serving the previous version's cached JS/CSS.

## Context
- HAT finding **F09-07**: 0.2.13 shipped the F09-06 UI change but the packaged app's WebView
  kept showing the old UI — stale cached `/static` assets. Root cause: `index.html` refs use
  stable URLs (no `?v=`) and the app sets no `Cache-Control` (`index()` at `app.py:1838-1839`;
  `/static` mount at `:330`). Different-origin dev (8485) looked fine only because its cache
  was empty.
- `index()` already uses `response_class=HTMLResponse` and returns
  `(STATIC_DIR / "index.html").read_text(...)`. index.html has **61** `/static/*.js|css` refs
  (`src="/static/..."` for JS, `href="/static/..."` for CSS).
- Version source: `the_one.__version__`.

## Inputs
- `the_one/interfaces/web/app.py` — `index()` route (`:1838-1839`), `STATIC_DIR`,
  `HTMLResponse` import; `/static` mount (`:330`).
- `the_one/interfaces/web/static/index.html` (asset refs — read only; rewrite happens
  server-side in `index()`).

## Outputs
- `GET /` returns `index.html` with every `/static/*.js` and `/static/*.css` reference
  suffixed `?v={__version__}`, and a `Cache-Control: no-store` (or `no-cache`) response header.
- Each release ⇒ new asset URLs ⇒ WebView fetches fresh JS/CSS; within a release, assets stay
  cacheable.

## Acceptance Criteria
- [ ] `GET /` response body has `?v={current __version__}` appended to all `/static/*.js` and
      `/static/*.css` URLs (all 61), and none are double-suffixed or broken.
- [ ] `GET /` sends `Cache-Control: no-store` (or `no-cache`) so the HTML is always revalidated
      /refetched and picks up new versioned URLs after an upgrade.
- [ ] The referenced versioned URLs resolve (e.g. `GET /static/js/areas/chat.js?v=X` → 200 and
      serves the file; the query string is ignored by the static mount).
- [ ] Non-`/static` URLs and any non-js/css refs are untouched; no change to the raw
      `index.html` on disk (rewrite is server-side only).
- [ ] Existing behavior preserved: `/` still returns valid HTML that boots the app.
- [ ] Test added asserting the `?v=` rewrite + the cache header; `ruff` clean; suite green.

## Implementation Guidance
1. In `index()`: read the HTML, then rewrite asset refs. Use a regex that appends
   `?v={version}` to `(src|href)="/static/…\.(js|css)"` occurrences (guard against an
   existing `?` — skip or use `&`). Prefer a precise regex over blind string replace so only
   `/static` js/css are touched. Pull `version` from `the_one.__version__`.
2. Return `HTMLResponse(content=rewritten, headers={"Cache-Control": "no-store"})` (keep the
   `response_class=HTMLResponse` route; setting the header on the response is what matters).
3. Leave the `/static` `StaticFiles` mount as-is (its etag/last-modified caching is fine now
   that URLs are version-scoped). Do NOT rewrite the file on disk.
4. Consider computing the rewrite once at import/startup (version is fixed per process) if a
   per-request regex feels heavy — optional; correctness first.

## Edge Cases
- **Refs with an existing query string** (none today): don't produce `?x?v=`; use `&v=` if a
  `?` is already present.
- **Dev vs frozen**: `STATIC_DIR` differs (repo vs PyInstaller bundle) but the rewrite is
  path-agnostic (operates on the HTML text) — works in both.
- **First upgrade to the fixed build**: a WebView that cached the OLD (pre-fix) `index.html`
  may still serve old URLs once; after it revalidates the HTML (or a one-time hard refresh)
  the no-store header makes all subsequent upgrades clean. Note this in the PR.
- **Transition note**: the very first launch on the fixed version may still need one manual
  refresh if the old HTML is cached; every release after is automatic.

## Files Affected
- `the_one/interfaces/web/app.py` — `index()` rewrite + cache header.
- `tests/` — new test for the rewrite + header (find where web/app routes are tested).

---

## Post-Completion Checklist
- [ ] Acceptance criteria verified (test + curl `GET /`)
- [ ] Update flight-log.md (F09-07 resolved)
- [ ] Set leg status `completed` (after build verify)
- [ ] Check off / add this leg in flight.md
- [ ] Commit (rolls into next build)
