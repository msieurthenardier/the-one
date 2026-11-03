# Squawk 0085: static assets are cache-busted by app version, so dev edits serve stale

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-11-03

## Report

`static/index.html`'s asset references carry `?v={__version__}` — the **package
version**, not anything derived from the files themselves. So a browser that has
cached `knowledge-section.js?v=0.8.1` keeps serving it until the version string
changes, regardless of how many times the source was edited and the server
restarted.

For a release this is fine: a shipped build bumps the version. For **development
it is a footgun with no signal** — `make restart` reports success, the server
genuinely serves the new bytes, and the operator's browser silently runs the old
ones. Nothing on screen distinguishes "the fix didn't work" from "you are looking
at cached JavaScript".

**Observed during Mission 24 Flight 6's HAT**, which is exactly where it should
surface. Three landed UI changes appeared not to have shipped. The server was
verified to be serving the new code (`buildItemMenu` ×3, `refreshItemsListNow` ×2,
`kb-edit` ×7, fetched over HTTP); the browser was serving a cached
`?v=0.8.1`. A hard reload resolved it. Cost a round trip and briefly cast doubt on
a change that was correct.

## Evidence

- `the_one/interfaces/web/api.py` — the index template substitutes
  `"version": __version__`, and assets render as
  `knowledge-section.js?v=0.8.1`.
- `tests/test_index_asset_cache_busting.py` asserts every `/static` js/css ref
  carries the version parameter — so the mechanism is deliberate, and this squawk
  is about the **key**, not the presence of busting.

## Disposition

The fix shape is conventional but is a small design choice, so name it rather than
assume it: in dev mode (`THE_ONE_DEV_MODE=true`), key the parameter to each file's
**mtime** (or a short content hash) instead of the package version, leaving release
behaviour exactly as it is. That keeps production caching efficient — one stable
key per release — while making a dev restart always serve what is on disk.

Scoping it to dev mode avoids the obvious cost of per-file hashing on every
production page load, and matches how the project already gates other
developer-only behaviour.

`tests/test_index_asset_cache_busting.py` will need updating alongside — it
currently pins the total ref count and the version-keyed shape.

## Corrective Action

`the_one/interfaces/web/app.py`: `_cache_busted_index_html()` is now a plain function. With `settings.dev_mode` it renders `index.html` per request, keying each `/static` js/css ref by the first 10 hex of the sha1 of that file's bytes (`_asset_content_key`; a missing/unreadable file falls back to `__version__`). Otherwise it returns `_production_index_html()`, the unchanged `lru_cache`-memoized `__version__` rewrite. Content hash chosen over mtime: stable across checkouts/touches, so the key moves only when bytes do; cost is ~100 small file reads per dev index load. HTML shape unchanged. CLAUDE.md (two paragraphs) and `the_one/agents.md` updated. Root cause of the test surprise: the repo `.env` sets `THE_ONE_DEV_MODE=true`, so the existing tests now pin production mode with an autouse fixture.

## Verification

- `tests/test_index_asset_cache_busting.py`: 9 passed. New: `test_dev_mode_keys_assets_by_content_per_request` (content change changes `v`, same content same `v`, missing file falls back, falsified: yes, dev branch removed -> failed, restored) and `test_production_mode_stays_version_keyed_and_memoized` (falsified: no).
- `ruff check` / `ruff format --diff` clean on both Python files.
- `THE_ONE_TEST_NETNS=1 make test-unit`: see report.
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator approved implementing** a dev-mode content key (mtime or hash) for the `?v=` cache-bust parameter, with production keeping `__version__`. Mind `_cached_index_html`'s `lru_cache` and the shape `tests/test_index_asset_cache_busting.py` pins. Burn-down next turnaround.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
