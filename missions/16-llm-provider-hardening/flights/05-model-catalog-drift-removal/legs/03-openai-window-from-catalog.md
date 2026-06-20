# Leg: openai-window-from-catalog

**Status**: completed
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Repoint `OpenAIProvider`'s context-window resolver from the hand-maintained
`OPENAI_MODEL_CONTEXT` prefix table to the shared catalog lookup
(`context_window_for("openai", …)`), logging a WARN on a catalog miss (DD3) — so
the provider's runtime window is catalog-sourced.

> **Sequencing (FD note, see flight log):** this leg does **NOT** delete
> `OPENAI_MODEL_CONTEXT`. The table is still consumed by the Studio endpoint
> (`api.py:4216`) and two test files; deleting it now would red the tree until
> Leg 5. **Leg 5 owns the deletion** (after migrating both Studio branches) and
> the table-import test rewrites. Leg 3 is provider-resolver-only and keeps every
> test green.

## Context

- Catalog lookup (`context_window_for`) landed in Leg 1; cache+seed loading in
  Leg 2. This leg makes the OpenAI provider a *consumer*.
- The current resolver is a longest-prefix loop over `OPENAI_MODEL_CONTEXT`
  (`openai_provider.py:94-104`). The catalog's `context_window_for` already does
  exact-match-then-longest-prefix internally and the seed reproduces all twelve
  table windows — so swapping the resolver body is behavior-preserving for every
  currently-tabled model.
- **`OpenRouterProvider` subclasses `OpenAIProvider` but overrides
  `_resolve_max_context_tokens`** (`openrouter_provider.py:161`, uses
  `openrouter_api`) — it does NOT touch the OpenAI table or catalog. Changing the
  base resolver must not affect OpenRouter; keep that override intact and verify.
- DD3: a catalog miss logs a WARN before falling back to the class default (today
  the fallback is silent). The `_resolve_max_context_tokens_if_needed` wrapper
  (`base.py:281-301`) still owns exception-catching + the resolved-sentinel; this
  leg only changes what `_resolve_max_context_tokens` does on the happy path.
- **Test hermeticity**: `context_window_for` memoizes the catalog at module
  level. Leg-2 tests mutate that memo (`invalidate`/`_reset_for_tests`). Leg-3
  provider tests must reset the memo (autouse fixture or explicit
  `_reset_for_tests(None)`) so a prior test's injected/cached catalog can't leak
  in. Also: these tests must not depend on a real on-disk cache in
  `settings.data_dir` — reset to force a seed load, or inject a known catalog.

## Inputs
- Legs 1–2 landed: `the_one/llm/model_catalog.py` (`context_window_for`,
  `_reset_for_tests`, `invalidate`).
- `the_one/llm/openai_provider.py` current table-based resolver.
- `tests/test_llm_max_context.py` (existing OpenAI resolution tests).

## Outputs
- `the_one/llm/openai_provider.py` — resolver calls `context_window_for`; WARN on
  miss; `OPENAI_MODEL_CONTEXT` left in place (annotated as Leg-5-owned).
- `tests/test_llm_max_context.py` — existing parametrized resolution cases pass
  unchanged; new assertions that the resolver sources from the catalog and WARNs
  on miss; an autouse catalog-memo reset for hermeticity.

## Acceptance Criteria
- [x] `openai_provider.py` gains a module-level logger (`import logging` +
      `logger = logging.getLogger(__name__)`) — **required**: the file has none
      today, so without it the miss-path `logger.warning` would raise `NameError`,
      get swallowed by the `_resolve_..._if_needed` wrapper's `except`
      (`base.py:291-293`), and the WARN would never fire (the miss-WARN test would
      fail).
- [x] `OpenAIProvider._resolve_max_context_tokens` resolves `self.max_context_tokens`
      via `context_window_for("openai", self.model)`; on a non-`None` result it
      sets the window, on `None` it logs a **WARNING** naming the model and leaves
      the class default (128k).
- [x] The existing `TestOpenAIPrefixLookup.test_resolves_model_context`
      parametrized cases (`openai_provider`/`test_llm_max_context.py:75-103`,
      including the dated-variant and `gpt-4` 8k-trap cases) **pass unchanged** —
      the catalog reproduces every tabled window.
- [x] `test_unknown_model_falls_back_to_class_default`,
      `test_empty_model_string_falls_back`, and `test_idempotent_second_call_is_noop`
      still pass (the WARN on the miss cases is acceptable; idempotency via the
      sentinel is unchanged).
- [x] A new test proves the resolver reads the **catalog** (not the table): inject
      a catalog via `_reset_for_tests({...})` giving a known model a distinct
      window and assert the provider resolves to it.
- [x] A new test asserts the miss path logs a WARNING (via `caplog`) and keeps the
      default.
- [x] `OpenRouterProvider` is unaffected — its `_resolve_max_context_tokens`
      override still resolves via `openrouter_api` (existing OpenRouter
      context-window test still green).
- [x] `OPENAI_MODEL_CONTEXT` is still present in `openai_provider.py` (Leg 5
      deletes it); `api.py` and the table-import tests are untouched by this leg.
- [x] Catalog memo is reset between tests so suite-order can't contaminate
      resolution results.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_max_context.py tests/test_model_catalog.py tests/test_model_catalog_refresh.py tests/test_openrouter_wire_level.py -x --timeout 30` → green (the OpenRouter wire test confirms the base-resolver change didn't leak into the OpenRouter override).
- Grep confirms `OpenRouterProvider._resolve_max_context_tokens` override is intact and `OPENAI_MODEL_CONTEXT` still defined.
- `python -c "import asyncio; from the_one.llm.openai_provider import OpenAIProvider as P; p=P(model='gpt-4o-2024-05-13', api_key='x'); asyncio.run(p._resolve_max_context_tokens_if_needed()); print(p.max_context_tokens)"` → `128000`.

## Implementation Guidance

1. **Add the import + a module-level logger** in `openai_provider.py`:
   `from the_one.llm.model_catalog import context_window_for`, and (the file has
   neither today) `import logging` + `logger = logging.getLogger(__name__)`. The
   logger is mandatory — see the first acceptance criterion. (No import cycle:
   `model_catalog` imports `config`, not `openai_provider`.)

2. **Replace the resolver body** (`openai_provider.py:94-104`):
   ```python
   async def _resolve_max_context_tokens(self) -> None:
       # Catalog-sourced (M16 F05): replaces the OPENAI_MODEL_CONTEXT prefix
       # table. OpenRouterProvider overrides this method and is unaffected.
       window = context_window_for("openai", self.model)
       if window is not None:
           self.max_context_tokens = window
       else:
           logger.warning(
               "openai: no catalog context window for model %r; using default %d",
               self.model,
               self.max_context_tokens,
           )
   ```
   Confirm a module-level `logger` exists in `openai_provider.py` (add
   `logger = logging.getLogger(__name__)` if not).

3. **Annotate the table** — leave `OPENAI_MODEL_CONTEXT` defined but add a short
   comment: "Retained for the Studio model-list endpoint (`api.py`) + tests until
   Leg 5 migrates them and deletes this table. The provider resolver no longer
   reads it." Do not change its contents.

4. **Tests** (`tests/test_llm_max_context.py`):
   - Add a **function-scoped autouse fixture on the `TestOpenAIPrefixLookup` class**
     (not module-wide — keeps the reset isolated to the tests that need it) that
     `yield`s with `the_one.llm.model_catalog._reset_for_tests(None)` in **both**
     setup and teardown, so the memo is clean before each test and no injected
     catalog leaks out. (Verify the existing parametrized cases still pass.)
   - Add `test_resolver_reads_catalog_not_table`: `_reset_for_tests({"providers":
     {"openai": {"gpt-4o": 222_222}}})` (note the required `"providers"` wrapper —
     `context_window_for` reads `catalog.get("providers", {})`), construct
     `OpenAIProvider(model="gpt-4o")`, resolve, assert `222_222`.
   - Add `test_miss_logs_warning`: inject an empty/missing-model catalog, resolve a
     model not present, assert via
     `caplog.at_level(logging.WARNING, logger="the_one.llm.openai_provider")`
     (scoped to this logger, matching `test_model_catalog.py`'s pattern) that a
     WARNING fired and the window stayed 128k.
   - Add an explicit comment in the prefix-match test noting `gpt-4-turbo-preview`
     → `128000` exercises the longest-prefix sort-order (catches a regression of
     the length-desc scan).
   - Leave `test_table_contains_required_entries` (`:127-143`) as-is — it imports
     the table directly (memo-reset doesn't affect it) and guards the table that
     Leg 5 will remove.

## Edge Cases
- **OpenRouter regression**: the single most important non-obvious risk. Confirm
  `OpenRouterProvider` still resolves via its override — run its existing
  context-window test (search `tests/` for OpenRouter + context). Do not let the
  base change leak.
- **A real on-disk cache in `settings.data_dir`** could make a non-reset test read
  cache values instead of the seed. The autouse reset forces a fresh load each
  test; for the inject-catalog tests, `_reset_for_tests({...})` bypasses file
  loading entirely (memo is pre-populated), so they're independent of any cache.
- **WARN noise on legitimately-unknown models** (fine-tunes): acceptable per DD3 —
  the WARN is the intended drift signal. It's one line per provider-instance
  resolution (the sentinel prevents repeats).
- **Class default unchanged** (128k): the `max_context_tokens` class attribute on
  `OpenAIProvider` stays; only the resolved value changes source.

## Files Affected
- `the_one/llm/openai_provider.py` - resolver → catalog; table retained (annotated)
- `tests/test_llm_max_context.py` - catalog-source assertions + memo-reset fixture

---

## Post-Completion Checklist

**DEFERRED-COMMIT FLIGHT — do NOT commit, do NOT signal `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`test_llm_max_context.py`, `test_model_catalog*.py`, the
      OpenRouter context test)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Signal `[HANDOFF:review-needed]`
