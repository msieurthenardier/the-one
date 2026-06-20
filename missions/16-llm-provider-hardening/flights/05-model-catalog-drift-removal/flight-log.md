# Flight Log: Model-Catalog Drift Removal

**Flight**: [Model-Catalog Drift Removal](flight.md)

## Summary

Flight created (planning). Replaces the hand-maintained OpenAI prefix table (and
its Studio-endpoint duplicate) and Anthropic's hard-coded 200k constant with a
checked-in, regenerable model catalog resolved locally; enables Anthropic's 1M
context for real. No execution yet.

---

## Reconnaissance Report

Source artifact: mission `16-llm-provider-hardening` (hole #3 + the OpenAI/
Anthropic context-window success criterion). The mission cites specific code
locations; each was walked against current code during planning.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| OpenAI hand-curated prefix table | `confirmed-live` | `the_one/llm/openai_provider.py:46-59` (`OPENAI_MODEL_CONTEXT`, 12 entries) + resolver `:94-104` | Replace with catalog lookup (L02); delete table |
| OpenAI table **duplicated** in Studio model-list | `confirmed-live` (extra item, not named in mission) | `the_one/interfaces/web/api.py:4216-4233` (`_openai_ctx`, re-implements longest-prefix over the same import) | Unify onto shared lookup (L04) |
| Anthropic hard-coded window | `confirmed-live` | `the_one/llm/anthropic_provider.py:77` (`max_context_tokens = 200_000`) + explicit no-op resolver `:86-104`; Studio branch reads the class constant at `api.py:4250` | Replace with catalog lookup (L03); also the "all Claude = 200k" premise is now false (1M models exist) |
| OpenAI `/models` exposes no `context_length` | `confirmed-live` (premise behind "generated catalog, not live fetch") | `openai_provider.py:37-38` comment; `api.py` OpenAI branch derives ctx from the table, not the API response | Validates DD1 — bundled catalog, not live fetch |
| Live-fetch reference pattern (for the providers that *do* expose it) | `confirmed-live` | `openrouter_api.py:165-192` (`get_model_context_length`, typed + cached + fail-open); `ollama_api`/`ollama_provider.py:83-92` (`/api/show`) | Mirror its fail-open/typed shape in the new catalog loader; OpenRouter/Ollama unchanged |

No `already-satisfied` / `partially-satisfied` items — all cited drift sites are
live. No `needs-human-recheck` items beyond the two impl-detail confirmations
deferred into legs (models.dev shape → L01; current `context-1m` header id +
supported models → L03). No retirements to confirm with the operator.

**Adjacent observability check** (apparatus premise for the test-backed
criterion): `max_context_tokens` is read through two existing surfaces — the
`/agents/{name}/context-window` endpoint (`api.py:472`) and the usage WS event
(`app.py:1355`, `:1391`). Both are confirmed read paths, so the flight needs no
new measurement seam to assert the reported window. This is why the criterion is
satisfied with unit + offline-restart + live tests rather than a behavior test.

**Carry-forward from prior debriefs**: F4 test baseline `3347 passed / 10 skipped
/ 594 deselected`, ~346s, no flakes (F2 was 313s / F3 inflated by the marker bug,
since fixed). No context-window/catalog flakes recorded in F2–F4 debriefs (the F3
"catalog" references are about *tool* catalogs, unrelated). Existing regression
surfaces to keep green: `tests/test_api_context_window.py` (5 tests),
`tests/test_llm_max_context.py` (26 tests).

---

## Flight Director Notes

- **2026-06-19** — `/agentic-workflow` started. Phase file loaded:
  `.flightops/agent-crews/leg-execution.md` (valid — Crew/Protocol/Prompts
  present). Crew: Developer = Sonnet (design-review, implement, fix, commit);
  Reviewer = Haiku (code review); Accessibility Reviewer = Sonnet (optional, UI
  only). Tests run host-native: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  <files> -x --timeout 30` or `make test-unit`. Branch
  `flight/05-model-catalog-drift-removal` created off `main` (carried the planning
  artifacts + the mission.md edit). Flight flipped `ready → in-flight`. 6
  autonomous legs + 1 optional HAT; deferred-commit model (single flight-wide
  review + commit after leg 06). Starting at Leg 1 (`catalog-module-and-seed`).

- **2026-06-20 — Flight LANDED.** All 6 autonomous legs + the HAT completed. The
  HAT (run against a live 0.2.3 dev instance on :8485) verified all 6 steps and
  caught a **critical defect the automated pipeline missed**: the runtime refresh
  parser was built blind (models.dev unreachable in Leg 1) and parsed the wrong
  `api.json` shape → 0 models extracted → cache never written (DD1's stay-current
  goal silently dead). Fixed inline (commit `9f152b9`): parser traverses the real
  `raw[provider]["models"]` shape; seed regenerated from authoritative models.dev
  (also corrected over-reported 1M windows for `sonnet-4-5`/`opus-4-5`). Re-verified
  live: refresh writes the cache on startup; Studio endpoint returns correct
  per-model windows against the real Anthropic API. The HAT also surfaced an
  **out-of-scope** gap — the telemetry overlay's *used-token* state resets on chat
  reopen (the *max* persists) — routed by operator decision to **new Flight 6**
  (distinct session/DB persistence subsystem; kept out of F5 to avoid bundling).
  Commits: `03f3a61` (6 legs) + `9f152b9` (HAT fix). Full suite `3422/10/594`, 0
  failures. PR opened. `/flight-debrief` next.

- **2026-06-19 — Leg 3/5 sequencing refinement (FD decision).** The flight spec's
  Leg 3 line said "delete the dead table." Recon during Leg 3 design found
  `OPENAI_MODEL_CONTEXT` is still consumed by the Studio endpoint
  (`api.py:4216`, Leg 5's migration target) **and** two test files
  (`test_llm_max_context.py:26,143`; `test_model_catalog.py:204-207`). Deleting it
  in Leg 3 would red the tree until Leg 5 — violating the deferred-commit
  invariant that every leg-end leaves the suite green. **Refinement: Leg 3
  repoints only the OpenAI *provider* resolver to the catalog (keeps the table in
  place, WARN-on-miss); Leg 5 owns the table deletion** after migrating both
  Studio branches, plus the two test-file rewrites. Provider-resolution tests stay
  green through Leg 3 because the seed reproduces the table windows. Net scope and
  end-state are unchanged; only the deletion's leg-home moved 3→5.

---

## Decisions

### Flight-wide review on Sonnet, not the crew's Haiku (deferred-commit)
**Context**: This deferred-commit flight concentrates the whole correctness check
into one review of a large multi-file diff (~1826 insertions; 6 production files +
6 test files). The crew file specifies Reviewer = Haiku.
**Decision**: Used **Sonnet** for the single flight-wide Reviewer (non-Opus per the
hard rule), mirroring the F4 debrief's standardized deviation for deferred-commit
flights with large concentrated diffs.
**Impact**: Reviewer returned `[HANDOFF:confirmed]` — all DDs honored
(cache→seed→default fail-open; seed-coverage guard correct for both providers; no
`context-1m` header; OpenRouter untouched; no new runtime deps). One non-blocking
finding (vacuous tmp-filename assertions in `test_model_catalog_refresh.py:187,198`)
fixed at commit.

### Catalog mechanism pivoted to runtime refresh (mid-planning)
**Context**: Initial DD1 was a build-time-only checked-in artifact regenerated by
`make`. Operator clarified they want installs to stay current **without a
redeploy**.
**Decision**: DD1 reframed to a **built-in catalog refreshed on a daily cadence at
runtime** — bundled seed (offline fallback) + on-disk cache at
`settings.data_dir / "model_catalog.json"`, refreshed by a background loop
mirroring `_chat_history_purge_loop` (`app.py:646-680`). `make refresh-model-catalog`
demoted to a dev convenience that regenerates the committed seed.
**Impact**: Adds a `runtime-refresh-loop` leg; satisfies both "stay current
without deploy" and "survive restarts offline" (cache persists + seed always
present). All three moving parts have in-repo precedent (purge loop;
`settings.data_dir` at `config.py:68`; `openrouter_api.py` cached fetch).

---

## Leg Progress

### Session Note — 2026-06-19 (flight-wide review + commit)

Flight-wide review passed (Sonnet reviewer, `[HANDOFF:confirmed]`); one
non-blocking finding: vacuous tmp-filename assertions in
`tests/test_model_catalog_refresh.py` at lines 187 and 198 asserted
`model_catalog.json.tmp` but the production code generates `model_catalog.tmp`
(via `cache_path.with_suffix(".tmp")`). Both assertions fixed to the real temp
filename; 22/22 tests in `test_model_catalog_refresh.py` remain green. All 6
autonomous legs committed in a single flight-wide commit; flight remains
`in-flight` pending the optional HAT (leg 07 `uat-and-alignment`).

---

### L06 — verify-integration (landed 2026-06-19)

**New file**: `tests/test_model_catalog_integration.py` — 9 hermetic integration
tests covering all four acceptance criteria:

1. **Offline-restart survival** (2 tests): `monkeypatch.setattr(settings,
   "data_dir", tmp_path)` (empty dir → no cache) + `_reset_for_tests(None)`.
   Fresh `AnthropicProvider(model="claude-sonnet-4-6", api_key="x")` →
   `max_context_tokens == 1_000_000` after resolve (proves the seed drove it,
   not the class default of 200_000). Fresh `OpenAIProvider(model="gpt-4o",
   api_key="x")` → `128_000`.

2. **No-network on the resolve path** (2 tests): `httpx.AsyncClient.send` and
   `httpx.Client.send` monkeypatched to raise (not `__init__` — provider
   construction instantiates the httpx client before `send` is ever called).
   With `.send` raising, both providers resolve successfully from the seed with
   zero HTTP calls recorded.

3. **Shipped-model coverage** (4 parametrized tests): `context_window_for`
   returns the expected non-None window for `gpt-4o` → 128_000, `o1` →
   200_000, `claude-sonnet-4-6` → 1_000_000, `claude-3-5-haiku-latest` →
   200_000.

4. **Endpoint composition** (1 test): ASGI client around the api router (same
   pattern as `test_api_context_window.py`); `AgentFactory.create` patched to
   return `SimpleNamespace(llm=AnthropicProvider(model="claude-sonnet-4-6",
   api_key="x"))`; `data_dir` set to empty `tmp_path` + memo reset so the seed
   drives the resolve. `GET /api/agents/myagent/context-window` → `{"max_context_tokens":
   1000000}` — the true restart code path (endpoint → resolver → catalog → seed).

**Hermeticity**: autouse fixture resets the catalog memo before and after every
test via `_reset_for_tests(None)`.

**Flake check**: run 3 times in isolation — 9 passed, 9 passed, 9 passed.

**Full-suite metrics (make test-unit, F4 baseline comparison)**:

| Run | Passed | Skipped | Deselected | Wall-clock |
|-----|--------|---------|------------|------------|
| F4 baseline | 3347 | 10 | 594 | ~346s |
| F5 L06 (this run) | **3422** | 10 | 594 | ~296s |
| Delta | **+75** | 0 | 0 | −50s |

The +75 tests are the hermetic catalog/refresh/provider/endpoint tests added
across F05 Legs 1–6:
- L01 (`test_model_catalog.py`): +22
- L02 (`test_model_catalog_refresh.py`): +22
- L03/L04 (`test_llm_max_context.py`): net additions after rewrites
- L04 (`test_anthropic_provider.py`): ripple-fix (count-neutral)
- L05 (`test_provider_api.py`): assertion extensions (count-neutral)
- L06 (`test_model_catalog_integration.py`): +9

**0 failures. No new flakes.**

**Files changed**: `tests/test_model_catalog_integration.py` (new).

---

### L05 — unify-studio-model-list (landed 2026-06-19)

**Endpoint migration**: replaced both branches in `list_provider_models`
(`api.py:4212-4260`) with `context_window_for` from `model_catalog`:

- **OpenAI branch**: deleted the `from the_one.llm.openai_provider import
  OPENAI_MODEL_CONTEXT` import, the `ordered_prefixes` sort, and the local
  `_openai_ctx` helper function. Added a lazy
  `from the_one.llm.model_catalog import context_window_for` import (in-branch,
  matching the existing lazy-import style). Returns
  `{"id": m.id, "name": m.id, "context_length": context_window_for("openai", m.id)}`.

- **Anthropic branch**: deleted the
  `from the_one.llm.anthropic_provider import AnthropicProvider` import, the
  `anthropic_ctx = AnthropicProvider.max_context_tokens` read, and the stale comment
  (lines ~4246-4249) claiming "all current Claude models share the 200k window" — now
  false. Added the same `context_window_for` import; returns per-model
  `context_length`. New comment notes catalog-sourcing with 1M for current Claude,
  200k for Haiku-class, null if unknown.

**Table deletion**: `OPENAI_MODEL_CONTEXT` dict and its surrounding annotation
comment (pointing at Leg 5) deleted from `openai_provider.py`. `grep -rn
"OPENAI_MODEL_CONTEXT" the_one/ tests/` now shows only three historical comment /
JSON-source-string mentions — no imports, no dict definition, no indexing.
`python -c "from the_one.llm.openai_provider import OPENAI_MODEL_CONTEXT"` →
`ImportError` confirmed.

**Stale file-ref fixed**: `model_catalog.py:74` comment updated from citing
`openai_provider.py:46-59` as the floor origin to: "mirrors the historical
OPENAI_MODEL_CONTEXT table (now removed; this is the canonical floor)".

**Test changes**:
- `tests/test_model_catalog.py`: repointed `test_seed_covers_all_openai_model_context_entries`
  to import `_OPENAI_FLOOR` from `model_catalog` (not the deleted table) and iterate
  `_OPENAI_FLOOR.items()` — identical semantics.
- `tests/test_llm_max_context.py`: removed `OPENAI_MODEL_CONTEXT` from the
  `openai_provider` import (kept `OpenAIProvider`); added `_OPENAI_FLOOR` and
  `context_window_for` to the `model_catalog` import. Renamed
  `test_table_contains_required_entries` → `test_floor_covers_required_models`, now
  asserts each `_OPENAI_FLOOR` key resolves via `context_window_for("openai", key)` to
  a positive int. Rewrote stale comment at `test_resolver_reads_catalog_not_table`
  (dropped "doesn't appear in OPENAI_MODEL_CONTEXT / not the table" — says "injected
  value proves catalog-sourcing" instead).
- `tests/test_provider_api.py`: extended `test_openai_models` to assert
  `models[0]["context_length"] == 128000` (gpt-4o); extended `test_anthropic_models`
  to assert `models[0]["context_length"] == 1000000` (claude-sonnet-4-20250514 →
  longest-prefix `claude-sonnet-4`) and `models[1]["context_length"] is None`
  (claude-haiku-4-20250514 — honest null, no matching prefix in seed).

**Verification**: 219 tests across `test_provider_api.py`, `test_llm_max_context.py`,
`test_model_catalog.py`, `test_model_catalog_refresh.py`, `test_api_context_window.py`
— all green in 36s.

**Files changed**: `the_one/interfaces/web/api.py`, `the_one/llm/openai_provider.py`,
`the_one/llm/model_catalog.py`, `tests/test_model_catalog.py`,
`tests/test_llm_max_context.py`, `tests/test_provider_api.py`.

---

### L04 — anthropic-window-from-catalog (landed 2026-06-19)

**Resolver swap**: replaced the explicit no-op `_resolve_max_context_tokens` body
in `anthropic_provider.py` (lines 86-104, which documented "all current Claude models
share the 200k context window" — now false) with a catalog lookup via
`context_window_for("anthropic", self.model)`. On a non-`None` result, sets
`self.max_context_tokens`; on `None`, logs a WARNING naming the model and leaving
the class default (200k). The class default `max_context_tokens = 200_000` (line 77)
is retained as the conservative miss-fallback. No `context-1m` beta header is sent
(DD4 — catalog-only).

**Import added**: `from the_one.llm.model_catalog import context_window_for` added
to `anthropic_provider.py`. The file already had a module-level `logger` (line 24),
so no logging import was needed.

**Test changes** (`tests/test_llm_max_context.py`):
- Module docstring updated — removed the stale "survives the no-op default resolver"
  claim; describes catalog-sourcing instead.
- Added a function-scoped autouse fixture on `TestAnthropicDefault` that calls
  `_reset_for_tests(None)` in both setup and teardown (same pattern as
  `TestOpenAIPrefixLookup`).
- Rewrote `test_class_default_preserved_after_resolver` → `test_resolves_native_1m_from_catalog`:
  pre-resolution class default is 200k; after `_resolve_max_context_tokens_if_needed()`,
  `claude-sonnet-4-6` resolves to 1_000_000 (from the seed).
- Kept `test_resolver_is_idempotent` (updated comment: first resolve now sets 1M,
  then mutate to sentinel, second call no-ops).
- Added `test_resolver_reads_catalog`: injects `{"providers": {"anthropic": {"claude-x":
  333_333}}}`, resolves, asserts 333_333 (proves resolver sources from catalog, not hardcoded table).
- Added `test_miss_logs_warning`: injects an empty Anthropic provider section, resolves
  `unknown-claude`, asserts via `caplog.at_level(logging.WARNING, logger=
  "the_one.llm.anthropic_provider")` that a WARNING fires and the window stays 200k.

**test_anthropic_provider.py ripple-fix**: `test_drop_warning_names_tool_and_reason`
assumed `records[0]` was the tool-drop warning. With the catalog-miss WARN firing first
(for `claude-test`, not in the seed), the tool-drop is now `records[1]`. Updated the
assertion to search all records for the "press_key" message rather than checking
position — intent-preserving, more robust.

**Verification**:
- `python -c "... asyncio.run(p._resolve_max_context_tokens_if_needed()); print(p.max_context_tokens)"` → `1000000`.
- `grep -n "max_context_tokens = 200_000" anthropic_provider.py` → line 78 (class default intact).
- `grep -n "no-op default\|survives the no-op" test_llm_max_context.py` → no matches.
- `api.py` untouched (confirmed via `git diff --name-only`).
- 107 tests across `test_llm_max_context.py`, `test_model_catalog.py`,
  `test_model_catalog_refresh.py`, `test_anthropic_provider.py` — all green in 1.56s.

**Files changed**: `the_one/llm/anthropic_provider.py`, `tests/test_llm_max_context.py`,
`tests/test_anthropic_provider.py`.

---

### L03 — openai-window-from-catalog (landed 2026-06-19)

**Resolver swap**: replaced the `OPENAI_MODEL_CONTEXT` longest-prefix loop in
`_resolve_max_context_tokens` (`openai_provider.py:94-104`) with a single call to
`context_window_for("openai", self.model)`. On a non-`None` result, sets
`self.max_context_tokens`; on `None`, logs a WARNING naming the model and leaving
the class default (128k). The base wrapper (`_resolve_max_context_tokens_if_needed`,
`base.py:281-301`) owns exception-catching and the resolved-sentinel — unchanged.

**Logging added**: `import logging` and `logger = logging.getLogger(__name__)` added
to `openai_provider.py` (the file had neither); required so the miss-path
`logger.warning` doesn't raise `NameError` (which the base wrapper's `except` would
swallow silently, hiding the WARN and failing the test).

**Table retained**: `OPENAI_MODEL_CONTEXT` kept in place with an annotation comment
noting it's consumed by `api.py` + tests until Leg 5 migrates them and deletes it;
the provider resolver no longer reads it.

**OpenRouter unaffected**: confirmed `OpenRouterProvider._resolve_max_context_tokens`
override (line 161 of `openrouter_provider.py`) is untouched; it still delegates to
`openrouter_api.get_model_context_length`. The OpenRouter wire-level test passed
green, confirming no leak from the base-class change.

**Test changes** (`tests/test_llm_max_context.py`):
- Added `import logging` + `import the_one.llm.model_catalog as _model_catalog` +
  `from the_one.llm.model_catalog import _reset_for_tests`.
- Added a function-scoped autouse fixture on `TestOpenAIPrefixLookup` that calls
  `_reset_for_tests(None)` in both setup and teardown, keeping the catalog memo
  clean between tests.
- Added a comment on the parametrize marking `gpt-4-turbo-preview` → 128000 as the
  case that exercises longest-prefix sort-order.
- All 17 existing parametrized `test_resolves_model_context` cases pass unchanged —
  the seed reproduces every window.
- Added `test_resolver_reads_catalog_not_table`: injects `{"providers": {"openai":
  {"gpt-4o": 222_222}}}`, resolves, asserts 222_222 (proves the resolver reads the
  catalog, not `OPENAI_MODEL_CONTEXT`).
- Added `test_miss_logs_warning`: injects an empty provider section, resolves an
  unknown model, asserts via `caplog.at_level(logging.WARNING, logger=
  "the_one.llm.openai_provider")` that a WARNING fires and the window stays 128k.
- `test_table_contains_required_entries` left as-is.

**Test run**: 92 tests across `test_llm_max_context.py`, `test_model_catalog.py`,
`test_model_catalog_refresh.py`, `test_openrouter_wire_level.py` — all green in
1.55s.

**Files changed**: `the_one/llm/openai_provider.py`, `tests/test_llm_max_context.py`.

---

### L02 — runtime-refresh-loop (landed 2026-06-19)

**Fetch method**: mocked (httpx.AsyncClient.get patched via unittest.mock.AsyncMock
in all tests; no live network calls made during implementation). The seed-coverage
guard was verified via a canned list-shape payload matching the bundled seed's
(provider, model) pairs.

**Implementation notes**:
- `the_one/llm/model_catalog.py` — extended with: shared projection helpers
  (`project_raw`, `apply_floor`, `_OPENAI_FLOOR`, `_strip_provider_prefix`,
  `_extract_context_window`) promoted from the script to module level;
  `_load_catalog()` now prefers `settings.data_dir / "model_catalog.json"` (cache)
  before falling back to the bundled seed — corrupt cache logs WARN and falls
  through cleanly; `refresh_catalog_cache()` async fetch → `project_raw` →
  `apply_floor` → seed-coverage write guard (every seed (provider, model) pair must
  be present in the projected catalog, else no write) → atomic write (`os.replace`)
  with `fetched_at` + `source` + `providers` → `invalidate()`; `_refresh_due()`
  reads `fetched_at` from cache (absent / missing / stale / unparseable → True);
  `invalidate()` public symbol that sets `_catalog = None`.
- `scripts/refresh_model_catalog.py` — refactored to import `project_raw`,
  `apply_floor`, `_OPENAI_FLOOR`, `_MODELS_DEV_URL`, `_FETCH_TIMEOUT` from
  `the_one.llm.model_catalog`; its `fetch_and_project` is now a thin sync wrapper
  (httpx.Client GET → `project_raw(resp.json())`); `main` applies the floor and
  writes the seed with `generated_at` unchanged. `make refresh-model-catalog`
  verified to import cleanly (`.venv/bin/python scripts/refresh_model_catalog.py
  --help` → OK).
- `the_one/interfaces/web/app.py` — added `_catalog_refresh_task` module global,
  `_get_catalog_refresh_check_interval()` (env `THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS`,
  default 3600, floor 60), `_model_catalog_refresh_loop()` (startup catch-up +
  `while True: sleep + _maybe_refresh`), `_model_catalog_refresh_shutdown_drain()`;
  started via `asyncio.create_task` in lifespan right after the purge-loop start;
  drained in lifespan shutdown right after the purge drain. All wrapped in
  try/except-log matching the purge-loop pattern exactly.
- `tests/test_model_catalog_refresh.py` — 22 tests covering all acceptance
  criteria: cache preferred over seed; corrupt cache fallback + WARN; atomic write
  + `fetched_at`; `_refresh_due` (fresh/stale/absent/corrupt); offline returns False
  + existing cache intact + WARN; seed-coverage guard (empty payload, partial
  payload, garbage payload, full coverage allowed, pre-existing cache intact after
  rejection); post-refresh invalidation reflects new cache values; `invalidate()`
  clears memo. All 22 new + 22 existing catalog + 42 llm_max_context = 86 total green.

---

### L01 — catalog-module-and-seed (landed 2026-06-19)

**Seed authoring method**: hand-authored. models.dev was unreachable from the
execution environment; the seed was authored directly per the leg's Edge Cases
guidance. All twelve `OPENAI_MODEL_CONTEXT` entries are present at their
existing windows (no regression). Anthropic entries cover `claude-sonnet-4-6`
→ 1 000 000, `claude-3-5-haiku-latest` → 200 000, plus other current Claude
families (`claude-3-haiku`, `claude-3-opus`, `claude-3-sonnet`, `claude-sonnet-4`,
`claude-opus-4`). The `source` field in the seed records the hand-authoring
reason.

**Implementation notes**:
- `the_one/llm/model_catalog.py` — typed, fail-open `context_window_for(provider, model) → int | None`. Exact-match then longest-prefix-wins. Memoized at module level with a bare `_reset_for_tests(catalog=None)` seam. Fail-open error boundary lives in `_get_catalog()` (not `_load_catalog()`) so monkeypatching `_load_catalog` in tests exercises the same WARNING boundary.
- `the_one/llm/data/model_catalog.json` — committed seed with `generated_at` + `source` fields.
- `scripts/refresh_model_catalog.py` — complete, runnable generator mirroring `derive_brand_assets.py` structure. Handles both models.dev list and dict top-level shapes; strips `provider/` prefixes; applies no-regression floor from `OPENAI_MODEL_CONTEXT`.
- `Makefile` — `.PHONY refresh-model-catalog` target with `##` help line added after `brand-assets`.
- `pyproject.toml` — extended to `the_one = ["interfaces/web/static/**/*", "llm/data/*.json"]`.
- `tests/test_model_catalog.py` — 22 tests covering all required cases; all green. `test_llm_max_context.py` (42 tests) unchanged and green. `OPENAI_MODEL_CONTEXT` confirmed present and untouched in `openai_provider.py`.

---

## Deviations

_(none yet)_

---

## Anomalies

### HAT-surfaced parser bug + seed over-reporting (2026-06-19, Leg 7 inline fix)

**Severity**: BLOCKING (defeated DD1's stay-current goal + mis-reported some context windows).

**Bug 1 — `project_raw` parsed 0 models from real models.dev shape.**
`project_raw` was built blind against an assumed models.dev shape. The real
`https://models.dev/api.json` shape is:
```
{ "<provider>": { "id": "...", "name": "...", ..., "models": { "<model_id>": { "limit": { "context": N }, ... } } } }
```
The dict branch in `project_raw` iterated `raw[provider]` as if it were the
models map — so it was iterating keys `id`, `env`, `npm`, `name`, `doc`,
`models` as if they were model ids. Result: `_extract_context_window` received
provider-level metadata strings (not model entry dicts), extracted nothing, and
the projected catalog was always empty. `refresh_catalog_cache` → seed-coverage
guard blocked every write → cache was never written → the runtime refresh loop
silently appeared to work but never updated the on-disk cache.

**Fix**: rewrote the dict branch to read `raw[provider]["models"]` (the nested
dict keyed by model_id → entry). Kept a defensive flat-shape fallback (skips
non-dict values) for forward-compatibility. `_extract_context_window` and
`_strip_provider_prefix` were correct and unchanged.

**Bug 2 — seed over-reported some Anthropic context windows.**
The hand-authored seed (written when models.dev was unreachable) used
`claude-sonnet-4 → 1M` and `claude-opus-4 → 1M` as prefix entries. The real
models.dev data shows: `claude-sonnet-4-5` → 200k, `claude-opus-4-5` → 200k,
`claude-opus-4-0` → 200k; only `claude-sonnet-4-6`, `claude-opus-4-6`,
`claude-opus-4-7`, `claude-opus-4-8` are actually 1M. The broad prefixes were
incorrect.

**Resolution**:
1. `project_raw` fixed to the real nested shape (`raw[provider]["models"]`).
2. Seed regenerated from live models.dev via `make refresh-model-catalog`:
   - 2 providers, 77 models (anthropic: 25, openai: 52).
   - `source` now "models.dev" (not "hand-authored … unreachable").
   - Key corrections: `claude-sonnet-4-5` → 200k, `claude-opus-4-5` → 200k,
     `claude-opus-4-8` → 1M, `claude-sonnet-4-6` → 1M (confirmed).
   - All `_OPENAI_FLOOR` keys present (floor applied in script).
3. `tests/test_model_catalog_refresh.py` mock payloads updated from list-shape
   to the real nested shape (`{provider: {models: {id: {limit: {context: N}}}}}`)
   so they exercise the fixed parser path.
4. `tests/test_provider_api.py::TestModelDiscovery::test_anthropic_models`
   assertion corrected: `claude-sonnet-4-20250514` → 200k (not 1M — the old
   1M came from the incorrect hand-authored `claude-sonnet-4` prefix entry).
5. Full unit suite: **3422 passed, 10 skipped, 594 deselected, 0 failures**.
6. Live cache write confirmed: `refresh_catalog_cache()` → `True`, 25 anthropic
   models written to `settings.data_dir / "model_catalog.json"` with `fetched_at`.

---

## Session Notes

- **2026-06-19** — Flight planned. Initial operator interview resolved: catalog
  mechanism = checked-in generated JSON; source = models.dev (operator deferred to
  "best practice"); freshness = refresh target + loud unknown-model WARN +
  `generated_at` stamp; Anthropic 1M = enable the beta header, then report 1M;
  unify the duplicated Studio table.

- **2026-06-19** — **Design review (Architect, Opus) → approve with changes.** All
  cited line numbers verified accurate against live code. One **HIGH** finding
  corrected a planning premise: current Claude models (incl. the default
  `claude-sonnet-4-6`, `anthropic_provider.py:79`) have a **native 1M window — no
  `context-1m` beta header, no above-200k premium**; the dated header is the older
  Sonnet-4.x mechanism. The interview's "we don't send the header so 1M isn't
  real" premise was wrong. **DD4 reframed**: report the catalog's per-model window,
  send no header; header-enable demoted to a deferred capability follow-up.
  Pending operator re-confirm (reverses their earlier explicit pick, which rested
  on the bad premise). MEDIUM: if a header *were* kept, the SDK call sites
  (`anthropic_provider.py:169,251`) take `extra_headers`, not a typed `betas=` arg
  (that lives on `client.beta.messages.*`). LOW: the web→llm import for DD5 is not
  new (`api.py:4216,4242`) — a shared leaf catalog module is an improvement, no
  cycle. Suggestions folded in: package-data for the seed (DD6); offline test must
  assert the catalog *drove* the value (1M reads 1M, not default); deleting
  `OPENAI_MODEL_CONTEXT` **rewrites** the table-importing cases in
  `test_llm_max_context.py` (not just "extends"); whole-catalog parse failure
  should WARN (louder than the blanket `except` at `base.py:293`) — added to DD3.

- **2026-06-19** — Operator mid-planning directive: catalog should be built-in and
  refresh on a regular cadence rather than requiring a build (see Decisions).

- **2026-06-19** — **1M scope resolved (operator): catalog-only now, revisit
  later.** DD4 locked to report-the-catalog-window, no header. Header-gated 1M
  recorded as a mission Open Question, folded into the planned extended-thinking/
  capability flight (which already touches the request path). Conditional
  "if header scope kept" caveats removed from the prereqs, adaptation criteria,
  and leg 04.
