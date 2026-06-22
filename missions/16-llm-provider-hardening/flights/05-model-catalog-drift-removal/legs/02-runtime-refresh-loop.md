# Leg: runtime-refresh-loop

**Status**: completed
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Add the runtime side of DD1: a daily background loop that fetches models.dev into
an on-disk cache at `settings.data_dir / "model_catalog.json"`, and extend the
catalog loader to prefer that cache over the bundled seed — so installs stay
current without a redeploy and reopening an old chat resolves from local files
(cache → seed → default) with no network call.

## Context

- Builds directly on Leg 1's `the_one/llm/model_catalog.py`. Leg 1 left two seams:
  `_load_catalog()` (single load path, to be extended to prefer the cache) and the
  module-level memoization (`_get_catalog`/`_reset_for_tests`).
- **Precedent to mirror exactly**: the chat-history purge loop in
  `the_one/interfaces/web/app.py` — `_get_purge_check_interval()` (env-overridable,
  default 3600s, floored 60s, `:597-610`), `_purge_due()` (`:613-616`),
  `_chat_history_purge_loop()` (startup catch-up `_maybe_*` then
  `while True: sleep(interval); _maybe_*`, `:646-660`),
  `_chat_history_purge_shutdown_drain()` (cancel + suppress CancelledError,
  `:663-670`), startup `asyncio.create_task` (`:124-125`), shutdown drain
  (`:251-256`). The catalog loop is the same shape.
- **Difference from the purge loop**: "due" is keyed off the **cache file's
  `fetched_at` stamp** (no DB row) — if the cache is absent or its `fetched_at` is
  older than the refresh interval (24h), a refresh is due.
- **Cache location**: `settings.data_dir / "model_catalog.json"` (`config.py:68`;
  the dir is `mkdir`-ensured at startup, `config.py:98`). Same writable per-user
  dir as `the-one.db`. Atomic write (temp file + `os.replace`) so a crash mid-write
  can't corrupt the cache.
- **Fetch idiom**: async `httpx.AsyncClient(timeout=...)` mirroring
  `openrouter_api.list_models` (`openrouter_api.py:129-140`). Reuse Leg 1's
  models.dev projection logic — see Implementation Guidance §1 (factor it into a
  pure function both the runtime loop and the Leg-1 script call, eliminating
  duplication).
- **Nothing is committed yet** (deferred-commit flight), so refactoring Leg 1's
  `scripts/refresh_model_catalog.py` to share the projection function is clean.
- **DD3 (cache parse failure)**: a corrupt **cache** must not break lookups — the
  loader falls back to the seed (WARN), and only a seed failure trips the
  fail-open-to-empty boundary in `_get_catalog`.

## Inputs
- Leg 1 landed: `the_one/llm/model_catalog.py` (with `_load_catalog()` seam),
  `the_one/llm/data/model_catalog.json` seed, `scripts/refresh_model_catalog.py`.
- `the_one/interfaces/web/app.py` purge-loop precedent + lifespan startup/shutdown.
- `the_one/config.py` `settings.data_dir`.

## Outputs
- `the_one/llm/model_catalog.py` — extended: cache-preferring `_load_catalog()`;
  the moved-in pure `project_raw(raw)` projector + `apply_floor` + `_OPENAI_FLOOR`
  + id helpers; an async `refresh_catalog_cache() -> bool` (fetch → project →
  floor → seed-coverage guard → atomic write w/ `fetched_at` → invalidate memo); a
  `_refresh_due()` helper; a public `invalidate()` reset.
- `the_one/interfaces/web/app.py` — `_model_catalog_refresh_loop()` +
  `_get_catalog_refresh_check_interval()` + shutdown drain + lifespan wiring.
- `scripts/refresh_model_catalog.py` — refactored to call the shared projector.
- `tests/test_model_catalog_refresh.py` — new tests.

## Acceptance Criteria
- [x] `_load_catalog()` prefers `settings.data_dir / "model_catalog.json"` when it
      exists and parses; otherwise loads the bundled seed. A **corrupt cache**
      logs a WARN and falls back to the seed (lookups still work from the seed),
      rather than tripping the empty-catalog fail-open.
- [x] `refresh_catalog_cache()` fetches models.dev, projects to the flat shape
      (reusing the shared projector), and **atomically** writes the cache file with
      a `fetched_at` stamp + `source`; on success the in-memory memo is invalidated
      so the next `context_window_for()` reflects the fresh cache.
- [x] `refresh_catalog_cache()` never raises on fetch/network failure — it logs and
      returns `False`, leaving any existing cache/seed intact (offline-safe).
- [x] **Seed-coverage write guard**: `refresh_catalog_cache()` writes the cache
      only when the newly-projected catalog covers every `(provider, model)` pair
      the bundled seed covers; an empty/garbage fetch (which `apply_floor` would
      otherwise paper over with the 12 OpenAI floor keys) is rejected — no write,
      returns `False`, prior cache/seed intact.
- [x] `_refresh_due()` returns `True` when the cache is absent or its `fetched_at`
      is older than the 24h refresh interval, `False` when fresh.
- [x] A background loop `_model_catalog_refresh_loop()` mirrors
      `_chat_history_purge_loop` (startup catch-up, due-gated, sleep+recheck via an
      env-overridable check interval defaulting to 3600s/floored 60s), is started
      via `asyncio.create_task` in the web lifespan **after** the purge-loop start,
      and is drained on shutdown (cancel + suppress `CancelledError`). A failing
      refresh pass is caught and the loop continues.
- [x] `scripts/refresh_model_catalog.py` is refactored to call the shared
      `project_models_dev` projector (no duplicated projection logic) and still
      writes the committed **seed** (not the cache) — `make refresh-model-catalog`
      still works.
- [x] `tests/test_model_catalog_refresh.py` covers: cache-preferred-over-seed;
      corrupt-cache-falls-back-to-seed (+WARN); atomic write produces a valid cache
      with `fetched_at`; `_refresh_due` fresh/stale/absent; offline refresh returns
      `False` and leaves cache intact; post-refresh invalidation reflects new
      values. All green. Existing `tests/test_model_catalog.py` still green.
- [x] No provider/endpoint behavior changes (still leg 3–5 territory);
      `OPENAI_MODEL_CONTEXT` still present.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_model_catalog_refresh.py tests/test_model_catalog.py -x --timeout 30` → green.
- Inject a cache with a higher window than the seed for a model (via `settings.data_dir` monkeypatched to `tmp_path`) → `context_window_for` returns the cache value; corrupt that cache → returns the seed value + a WARN logged.
- `make refresh-model-catalog` (offline) still produces/validates the seed via the shared projector (or hand-path per Leg 1 if unreachable).
- Grep `app.py` for `_model_catalog_refresh_loop` started in lifespan and drained in shutdown.

## Implementation Guidance

> **Note on the Leg-1 script**: it is already factored into
> `fetch_and_project(url)` (sync fetch **+** projection, `scripts/refresh_model_catalog.py:111-178`),
> `apply_floor(providers, floor, provider)` (`:181-199`), `write_catalog(...)`
> (`:202-214`), `_OPENAI_FLOOR` (`:60-73`), plus `_strip_provider_prefix` /
> `_extract_context_window`. The runtime loop needs an **async** fetch, so the
> shareable piece is the **pure projection** (the body of `fetch_and_project`
> after the HTTP call), not `fetch_and_project` itself.

1. **Move the shared transform into `model_catalog.py`**: extract the pure
   projection (the raw-payload → `{provider: {model: window}}` logic at
   `refresh_model_catalog.py:127-178`) into a module-level
   `project_raw(raw) -> dict[str, dict[str, int]]`, and move `apply_floor`,
   `_OPENAI_FLOOR`, `_strip_provider_prefix`, `_extract_context_window` alongside
   it. Refactor `scripts/refresh_model_catalog.py` to **import** these from
   `the_one.llm.model_catalog` (its `fetch_and_project` becomes: sync `httpx.Client`
   GET → `project_raw(resp.json())`; `main` still calls `apply_floor` + writes the
   **seed** with `generated_at`). `make refresh-model-catalog` must still work.

2. **Extend `_load_catalog()`** to prefer the cache. Import `settings` at module
   top — **confirmed no cycle** (`config.py` imports nothing from `the_one.llm.*`).
   - Cache exists and parses to a dict → return it.
   - Cache exists but fails to parse → `logger.warning(...)` and fall through to
     the seed (do NOT raise; the seed is the safety net).
   - Cache absent → seed (Leg-1 behavior, unchanged).

3. **`async def refresh_catalog_cache() -> bool`**: `httpx.AsyncClient(timeout=...,
   follow_redirects=True)` GET models.dev (default `https://models.dev/api.json`),
   `apply_floor(project_raw(resp.json()), _OPENAI_FLOOR, "openai")`, then the
   **seed-coverage write guard** (critical — see below), and on pass an **atomic
   write** (write `<cache>.tmp` in the same dir, `os.replace`) of
   `{fetched_at, source, providers}`, then `invalidate()`. Catch all exceptions →
   log + return `False` (offline-safe). Return `True` only on a successful write.

   > **Seed-coverage write guard (do NOT use OpenAI-floor coverage).**
   > `apply_floor` *unconditionally* injects all 12 OpenAI floor keys, so an
   > empty/garbage fetch would still yield a "covered" OpenAI section and clobber
   > the cache — losing the seed's Anthropic entries and newer OpenAI models. The
   > guard must instead require the **newly-projected catalog to cover every
   > `(provider, model)` pair the bundled seed covers** (load the seed, diff keys).
   > If the projection misses any seed pair, skip the write and return `False`
   > (keep the existing cache/seed). This subsumes the Anthropic case too.

4. **`_refresh_due() -> bool`** and **`invalidate()`**: `invalidate()` sets the
   memo `_catalog = None` and is the public symbol; leave `_reset_for_tests`
   unchanged (it already handles both None and dict injection — `invalidate()` is
   effectively `_reset_for_tests(None)` under a runtime-meaningful name).
   `_refresh_due()` reads the **cache file's `fetched_at`** (the cache uses
   `fetched_at`; the seed uses `generated_at`). Absent cache, a cache with no
   `fetched_at` (e.g. a script-written seed copy), unparseable, or `fetched_at`
   older than 24h → `True`. So first run is always due (startup catch-up) — intended.

5. **`app.py` loop** mirroring the purge loop. The lifespan function is
   `lifespan()` (`app.py:87`). Add `_get_catalog_refresh_check_interval()` reading
   `THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS` (default 3600, floor 60,
   mirroring `_get_purge_check_interval` `:597-608`); a `_model_catalog_refresh_loop()`
   whose inner **`async def _maybe_refresh()`** (async — it awaits
   `refresh_catalog_cache()`) is guarded try/except-log and calls
   `refresh_catalog_cache()` only when `_refresh_due()`; the startup `create_task`
   right after the purge-loop start (`:124-125`) with a module-global task ref;
   and `_model_catalog_refresh_shutdown_drain()` invoked beside the purge drain
   (`:253-256`, cancel + suppress `CancelledError`). Place the new loop section
   directly after the purge-loop section (`app.py:594-670`).

6. **Tests** (`tests/test_model_catalog_refresh.py`): `monkeypatch.setattr(settings,
   "data_dir", tmp_path)` (pattern from existing tests; `tmp_path` already exists —
   no mkdir needed). Mock the fetch with `unittest.mock.AsyncMock` on
   `httpx.AsyncClient.get` (return a canned models.dev payload; raise for the
   offline case). Cover the acceptance-criteria behaviors, including the
   **seed-coverage guard** (a payload missing a seed pair → no write, returns
   `False`, prior cache/seed intact). Use `caplog` for the corrupt-cache WARN.

## Edge Cases
- **`settings.data_dir` not yet created in a test**: create it in the fixture
  (`tmp_path` exists; write the cache under it). In production it's `mkdir`-ensured
  at startup (`config.py:98`).
- **Concurrent first-lookup vs. refresh writing the cache**: the atomic
  `os.replace` means a reader sees either the old or the new file whole, never a
  partial. The memo invalidation after write is a plain assignment (GIL-atomic).
  No lock needed for this single-writer/occasional-reader pattern.
- **`fetched_at` in a future timezone / clock skew**: treat unparseable or
  future-dated as "due" is acceptable (worst case an extra refresh). Don't crash.
- **models.dev reachable but shape changed / empty**: handled by the
  **seed-coverage write guard** in Implementation Guidance §3 — the cache is only
  written when the new projection covers every seed `(provider, model)` pair.
  Because `apply_floor` always re-adds the 12 OpenAI floor keys, an
  OpenAI-coverage check would be defeated by an empty fetch; the seed-coverage
  check is the correct guard and covers Anthropic too.
- **dev-mode / tests must not spawn the loop unexpectedly**: the loop only starts
  in the web lifespan; unit tests target the `model_catalog` functions directly
  and never start the app, so no background task leaks into the test process.

## Files Affected
- `the_one/llm/model_catalog.py` - cache-preferring load, projector, refresh, due, invalidate
- `the_one/interfaces/web/app.py` - refresh loop + interval + drain + lifespan wiring
- `scripts/refresh_model_catalog.py` - use shared projector
- `tests/test_model_catalog_refresh.py` - new tests

---

## Post-Completion Checklist

**Complete ALL steps before signaling — DEFERRED-COMMIT FLIGHT (do NOT commit, do
NOT signal `[COMPLETE:leg]`):**

- [x] All acceptance criteria verified
- [x] Tests passing (`test_model_catalog_refresh.py` + `test_model_catalog.py`)
- [x] Update flight-log.md with leg progress entry (note live-vs-mocked fetch)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Signal `[HANDOFF:review-needed]`
