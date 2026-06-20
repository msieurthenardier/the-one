# Leg: unify-studio-model-list

**Status**: completed
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Migrate the Studio model-list endpoint's OpenAI and Anthropic branches
(`list_provider_models`, `api.py:4212-4260`) onto the shared
`context_window_for(...)` lookup, **delete** the now-orphaned `OPENAI_MODEL_CONTEXT`
table, and repoint the two remaining table-import tests onto the canonical
`_OPENAI_FLOOR` — leaving the catalog the single source of truth for context
windows across the provider layer and the UI.

## Context

- This is the last consumer migration. After Legs 3–4, the **providers** are
  catalog-sourced; the only remaining `OPENAI_MODEL_CONTEXT` consumers are the
  Studio endpoint (`api.py:4216,4224,4229`) and two tests
  (`test_llm_max_context.py:30,184`; `test_model_catalog.py:205,207`).
- **Endpoint**: `GET /api/providers/{provider_id}/models` → `list_provider_models`
  (`api.py:4116`).
  - **OpenAI branch** (`:4212-4237`): imports the table, builds `ordered_prefixes`,
    defines a local `_openai_ctx` longest-prefix fn, returns
    `context_length: _openai_ctx(m.id)`. → replace with
    `context_window_for("openai", m.id)`.
  - **Anthropic branch** (`:4238-4260`): returns a **flat**
    `AnthropicProvider.max_context_tokens` (200k) for **every** model, with a
    stale comment (`:4246-4249`) claiming all Claude models are 200k. → replace
    with per-model `context_window_for("anthropic", m.id)` and rewrite the comment.
    This is a real **behavior fix**: the Studio UI will now show 1M for
    `claude-sonnet-4*` instead of a wrong 200k.
- The deleted table's values already live on as **`_OPENAI_FLOOR`** in
  `the_one/llm/model_catalog.py` (moved there in Leg 2; 12 entries, importable) —
  the canonical no-regression floor. The two cross-check tests repoint onto it.
- **Existing endpoint tests don't assert `context_length`** (`test_provider_api.py`
  `test_openai_models:1371`, `test_anthropic_models:1398` check only `id`/`name`),
  so the migration won't break them — but this leg **adds** `context_length`
  assertions to lock the new per-model behavior (the Anthropic 1M fix especially).

## Inputs
- Legs 1–4 landed. `context_window_for` + `_OPENAI_FLOOR` in `model_catalog.py`.
- `api.py` `list_provider_models` with the two table/constant branches.
- `tests/test_llm_max_context.py`, `tests/test_model_catalog.py`,
  `tests/test_provider_api.py`.

## Outputs
- `the_one/interfaces/web/api.py` — both branches use `context_window_for`; stale
  Anthropic comment rewritten; no `OPENAI_MODEL_CONTEXT` import.
- `the_one/llm/openai_provider.py` — `OPENAI_MODEL_CONTEXT` deleted (+ the Leg-3
  annotation comment removed).
- `tests/test_llm_max_context.py` — table import removed; `test_table_contains_required_entries`
  repointed onto the catalog/`_OPENAI_FLOOR`.
- `tests/test_model_catalog.py` — cross-check imports `_OPENAI_FLOOR` instead of the table.
- `tests/test_provider_api.py` — `context_length` assertions added to the openai +
  anthropic model-list tests.
- `the_one/llm/model_catalog.py` — the `:74` comment's stale `openai_provider.py:46-59`
  file-ref updated (the table no longer lives there).

## Acceptance Criteria
- [x] `list_provider_models` OpenAI branch returns `context_length =
      context_window_for("openai", m.id)` (no local table/prefix logic, no
      `OPENAI_MODEL_CONTEXT` import).
- [x] `list_provider_models` Anthropic branch returns **per-model**
      `context_length = context_window_for("anthropic", m.id)` (not a flat
      constant); the stale `:4246-4249` comment is rewritten to describe
      catalog-sourcing.
- [x] `OPENAI_MODEL_CONTEXT` is **deleted** from `openai_provider.py`; a repo-wide
      grep shows zero remaining references in `the_one/` and `tests/` (comments/
      docstrings/JSON-`source` strings that merely name it historically are
      acceptable, but no code imports or indexes it).
- [x] `tests/test_model_catalog.py`'s seed-coverage cross-check imports
      `_OPENAI_FLOOR` from `model_catalog` (not the deleted table) and still
      asserts the seed covers every floor entry at ≥ its floor window.
- [x] `tests/test_llm_max_context.py` no longer imports `OPENAI_MODEL_CONTEXT`;
      `test_table_contains_required_entries` is repointed to assert each
      `_OPENAI_FLOOR` key resolves via `context_window_for("openai", key)` (a
      catalog-backed guard), or is removed if judged redundant with the
      model_catalog cross-check — keep at least one guard somewhere.
- [x] `test_provider_api.py` `test_openai_models` asserts `context_length` for a
      known model (e.g. `gpt-4o` → 128000), and `test_anthropic_models` asserts the
      **per-model** result — `claude-sonnet-4-20250514` → **1000000** (longest-prefix
      `claude-sonnet-4`), proving the flat-200k bug is fixed.
- [x] The full affected suite is green; no behavior regressions elsewhere.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py tests/test_llm_max_context.py tests/test_model_catalog.py tests/test_model_catalog_refresh.py tests/test_api_context_window.py -x --timeout 30` → green.
- `grep -rn "OPENAI_MODEL_CONTEXT" the_one/ tests/` → only historical comment/`source`-string mentions remain; **no imports, no dict definition, no indexing**.
- `python -c "from the_one.llm.openai_provider import OPENAI_MODEL_CONTEXT"` → `ImportError` (confirms deletion).
- Manually trace `list_provider_models` anthropic branch returns `context_window_for("anthropic", m.id)` per model.

## Implementation Guidance

1. **OpenAI branch** (`api.py:4212-4237`): delete the
   `from the_one.llm.openai_provider import OPENAI_MODEL_CONTEXT` import, the
   `ordered_prefixes` line, and the local `_openai_ctx` function. Add (lazy, in
   the branch, matching existing style)
   `from the_one.llm.model_catalog import context_window_for` and return
   `{"id": m.id, "name": m.id, "context_length": context_window_for("openai", m.id)}`.

2. **Anthropic branch** (`api.py:4238-4260`): delete the
   `AnthropicProvider.max_context_tokens` read and the stale `:4246-4249` comment.
   Use the same `context_window_for` import; return per model
   `{"id": m.id, "name": getattr(m, "display_name", m.id), "context_length":
   context_window_for("anthropic", m.id)}`. New comment: brief note that
   context_length is catalog-sourced per model (1M for current Claude, 200k
   Haiku-class), no longer a flat class constant. (The `from
   the_one.llm.anthropic_provider import AnthropicProvider` import is now unused in
   this branch — remove it if nothing else in the branch needs it.)

3. **Delete the table** (`openai_provider.py`): remove the `OPENAI_MODEL_CONTEXT`
   dict (the Leg-3 resolver no longer reads it) and the Leg-3 annotation comment
   that pointed at Leg 5. Leave the module otherwise intact.

4. **Repoint tests**:
   - `test_model_catalog.py` (~:205): `from the_one.llm.model_catalog import
     _OPENAI_FLOOR` and iterate `_OPENAI_FLOOR.items()` (same semantics — every
     floor model resolves in the catalog at ≥ its floor window).
   - `test_llm_max_context.py` (`:30`): **remove `OPENAI_MODEL_CONTEXT`** from the
     `openai_provider` import (keep `OpenAIProvider`), and **add** `_OPENAI_FLOOR`
     to the `model_catalog` import (the file already imports from `model_catalog`
     — extend it; `context_window_for` is also needed for the rewritten guard).
     Rename `test_table_contains_required_entries` (`~:184`) →
     `test_floor_covers_required_models` and assert each `_OPENAI_FLOOR` key
     resolves via `context_window_for("openai", key)` to a positive int. Reword the
     stale comment at `~:148` (drop "doesn't appear in OPENAI_MODEL_CONTEXT / not
     the table" — the table is gone; say the injected value proves catalog-sourcing).
   - `test_provider_api.py`: extend `test_openai_models` to assert
     `models[0]["context_length"] == 128000` for `gpt-4o`; extend
     `test_anthropic_models` to assert `models[0]["context_length"] == 1000000`
     for `claude-sonnet-4-20250514` (longest-prefix `claude-sonnet-4` → 1M) **and**
     `models[1]["context_length"] is None` for `claude-haiku-4-20250514` (locks the
     honest null-on-miss path; frontend renders no chip for null —
     `studio.js:1838-1841`).
     **Note**: these endpoint tests construct the provider and hit
     `context_window_for`, which memoizes the catalog — they don't reset it, but
     since they read the real seed (no inject) the values are stable; no
     hermeticity fixture needed (no test in that file injects a catalog — verified).

5. **Fix the stale file-ref** in `model_catalog.py:74`: the comment cites
   `openai_provider.py:46-59` as the floor's origin — after deletion that's stale.
   Reword to "mirrors the historical OPENAI_MODEL_CONTEXT table (now removed; this
   is the canonical floor)".

## Edge Cases
- **Anthropic models not in the seed** (e.g. `claude-haiku-4-20250514` has no
  `claude-haiku-4` prefix) → `context_window_for` returns `None` →
  `context_length: null` in the response. Acceptable (the UI renders no chip; the
  seed/refresh can add the family later). Don't fabricate a fallback here — `null`
  is the honest "unknown".
- **Memoization across the endpoint tests**: the catalog memo persists in-process;
  the endpoint reads the seed. If any earlier `test_provider_api.py` test injected
  a catalog it could leak — verify none does (grep `_reset_for_tests` in that
  file). If clean, no fixture needed.
- **`list_provider_models` other branches** (ollama/openrouter/openai-compatible/
  mock) are untouched — they source context via their own live paths or omit it.
  Only the openai + anthropic branches change.
- **Lazy imports**: keep the per-branch lazy-import style already used in this
  function (the file lazily imports `openai`/`anthropic` inside each branch).

## Files Affected
- `the_one/interfaces/web/api.py` - both Studio branches → `context_window_for`; stale comment fixed
- `the_one/llm/openai_provider.py` - `OPENAI_MODEL_CONTEXT` deleted
- `the_one/llm/model_catalog.py` - stale file-ref comment fixed
- `tests/test_model_catalog.py` - cross-check → `_OPENAI_FLOOR`
- `tests/test_llm_max_context.py` - table import removed; guard repointed
- `tests/test_provider_api.py` - `context_length` assertions added

---

## Post-Completion Checklist

**DEFERRED-COMMIT FLIGHT — do NOT commit, do NOT signal `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (the affected suite above)
- [x] `grep -rn "OPENAI_MODEL_CONTEXT" the_one/ tests/` shows no code references
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Signal `[HANDOFF:review-needed]`
