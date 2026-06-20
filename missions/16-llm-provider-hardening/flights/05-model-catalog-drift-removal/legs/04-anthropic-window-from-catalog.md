# Leg: anthropic-window-from-catalog

**Status**: completed
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Replace `AnthropicProvider`'s no-op context-window resolver (and the now-false
"all current Claude models share 200k" premise it documents) with the shared
catalog lookup (`context_window_for("anthropic", …)`), so Anthropic windows are
catalog-sourced — correctly reporting **1M for current Claude models** (e.g. the
default `claude-sonnet-4-6`) and the right value for older/Haiku-class models —
with a WARN on a catalog miss (DD3) and the conservative 200k class default as
fallback. No `context-1m` beta header is sent (DD4 — catalog-only).

## Context

- The current resolver is an explicit **no-op** (`anthropic_provider.py:86-104`)
  whose docstring asserts "all current Claude models share the 200k context
  window" — **now false**: the seed has `claude-sonnet-4-6` → 1,000,000. The class
  default `max_context_tokens = 200_000` (`:77`) stays as the conservative fallback
  for a catalog miss.
- `anthropic_provider.py` **already has a module-level logger** (`:24`) — unlike
  the OpenAI file in Leg 3, no logger needs adding.
- This mirrors Leg 3's provider-resolver swap. `OpenRouterProvider` is a subclass
  of `OpenAIProvider`, not `AnthropicProvider`, so it is irrelevant here.
- **Studio endpoint untouched**: `api.py:4250` (the Anthropic Studio branch) reads
  `AnthropicProvider.max_context_tokens` (the class constant) — that migration is
  **Leg 5's** job. Leg 4 does not touch `api.py`.
- DD4 (catalog-only): report the catalog window; do **not** send `context-1m`.
  Current Claude models are natively 1M, so the catalog value is truthful with no
  request-path change.
- **Test impact**: `TestAnthropicDefault` (`test_llm_max_context.py:349-366`)
  asserts `claude-sonnet-4-6` stays 200k after resolution — that is exactly the
  stale premise this leg corrects, so it **must be rewritten** to assert 1M. The
  module docstring (`:11`) also states the old behavior and needs updating.
- **Hermeticity**: same as Leg 3 — `context_window_for` memoizes; the Anthropic
  test class needs the autouse memo-reset so suite-order can't contaminate it.

## Inputs
- Legs 1–3 landed: catalog module + OpenAI provider already catalog-sourced.
- `the_one/llm/anthropic_provider.py` no-op resolver + 200k class default.
- `tests/test_llm_max_context.py` `TestAnthropicDefault`.

## Outputs
- `the_one/llm/anthropic_provider.py` — resolver calls `context_window_for`; WARN
  on miss; class default 200k retained as fallback; stale docstring replaced.
- `tests/test_llm_max_context.py` — `TestAnthropicDefault` rewritten (sonnet-4-6 →
  1M); catalog-source + miss-WARN tests added; autouse memo-reset on the class;
  module docstring corrected.

## Acceptance Criteria
- [x] `AnthropicProvider._resolve_max_context_tokens` resolves
      `self.max_context_tokens` via `context_window_for("anthropic", self.model)`;
      non-`None` → set it; `None` → log a **WARNING** naming the model and leave the
      200k class default. (No `context-1m` header; no request-path change.)
- [x] The no-op docstring (`:86-104`) is replaced with text describing the
      catalog-sourced behavior (no "all Claude = 200k" claim; note 200k is the
      conservative miss-fallback, and the catalog carries the real per-model
      window incl. 1M).
- [x] `claude-sonnet-4-6` resolves to **1,000,000** (from the seed) after
      `_resolve_max_context_tokens_if_needed()` — the rewritten `TestAnthropicDefault`
      asserts this (was: asserted 200k).
- [x] The idempotency test still holds (second resolve no-ops via the sentinel).
- [x] A new test proves the resolver reads the **catalog**: inject via
      `_reset_for_tests({"providers": {"anthropic": {"claude-x": 333_333}}})` and
      assert the provider resolves to it.
- [x] A new test asserts the miss path logs a WARNING (via
      `caplog.at_level(logging.WARNING, logger="the_one.llm.anthropic_provider")`)
      and keeps the 200k default.
- [x] `max_context_tokens = 200_000` class default is retained (`:77`).
- [x] `api.py` is untouched (Leg 5 owns the Studio Anthropic branch). The module
      docstring (`:11`) is updated to reflect catalog-sourcing.
- [x] Autouse catalog-memo reset on the Anthropic test class for hermeticity.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_max_context.py tests/test_model_catalog.py tests/test_model_catalog_refresh.py tests/test_anthropic_provider.py -x --timeout 30` → green.
- `python -c "import asyncio; from the_one.llm.anthropic_provider import AnthropicProvider as P; p=P(model='claude-sonnet-4-6', api_key='x'); asyncio.run(p._resolve_max_context_tokens_if_needed()); print(p.max_context_tokens)"` → `1000000`.
- Grep confirms `max_context_tokens = 200_000` class default still present and `api.py` unchanged.
- `grep -n "no-op default\|survives the no-op" tests/test_llm_max_context.py` → no matches (confirms the stale module docstring was updated).

## Implementation Guidance

1. **Add the import** in `anthropic_provider.py`:
   `from the_one.llm.model_catalog import context_window_for`. (Logger already
   exists at `:24`. No cycle.)

2. **Replace the no-op resolver body** (`:86-104`):
   ```python
   async def _resolve_max_context_tokens(self) -> None:
       # Catalog-sourced (M16 F05): replaces the prior no-op that assumed all
       # Claude models share 200k — false now that current models are natively
       # 1M. 200k stays the conservative fallback on a catalog miss. No
       # `context-1m` beta header is sent (DD4 — catalog reports the real window;
       # current Claude models are natively 1M).
       window = context_window_for("anthropic", self.model)
       if window is not None:
           self.max_context_tokens = window
       else:
           logger.warning(
               "anthropic: no catalog context window for model %r; using default %d",
               self.model,
               self.max_context_tokens,
           )
   ```

3. **Keep** `max_context_tokens = 200_000` (`:77`) as the class default/fallback.

4. **Tests** (`tests/test_llm_max_context.py`):
   - Add a function-scoped **autouse fixture on `TestAnthropicDefault`** (yield +
     `_reset_for_tests(None)` in setup and teardown) — same pattern as the Leg-3
     `TestOpenAIPrefixLookup` fixture.
   - Rewrite `test_class_default_preserved_after_resolver` → e.g.
     `test_resolves_native_1m_from_catalog`: assert pre-resolution class default is
     200k, then after `_resolve_max_context_tokens_if_needed()` it is
     **1_000_000** for `claude-sonnet-4-6`.
   - Keep `test_resolver_is_idempotent` (still valid).
   - Add `test_resolver_reads_catalog` (inject `{"providers": {"anthropic":
     {"claude-x": 333_333}}}`, model `claude-x`, assert 333_333).
   - Add `test_miss_logs_warning`: inject `_reset_for_tests({"providers":
     {"anthropic": {}}})` with `model="unknown-claude"`; assert WARNING via
     `caplog.at_level(logging.WARNING, logger="the_one.llm.anthropic_provider")`
     + 200k retained.
   - Update the **module docstring** (`:11`) line that claims the class-default
     200k survives the no-op → describe catalog-sourcing.

## Edge Cases
- **Miss → 200k under-reports a new 1M model** until the catalog refreshes: this is
  the safe direction (never over-reports), and the Leg-2 daily refresh closes the
  gap. Acceptable per DD3/DD4.
- **Conformance/streaming tests** construct `AnthropicProvider` with
  `model="claude-test"` (not in the catalog) and don't assert `max_context_tokens`
  — so the resolver change doesn't ripple. **Expected**: those suites now emit a
  benign catalog-miss WARNING for `claude-test` on each `complete()`/`stream()`
  (swallowed; no test asserts WARN-absence). Run `test_anthropic_provider.py` to
  confirm.
- **Leg 5 carry**: `api.py:4246-4249` has a stale comment ("Anthropic stays at
  class-default — all current Claude models share the 200k window") that becomes
  materially false after this leg. Leave it for **Leg 5** (which migrates that
  Studio branch to the catalog and will rewrite the comment). Noted here so it
  isn't lost.
- **Memo contamination**: the autouse reset handles it; the inject tests bypass
  file loading entirely.
- **No `context-1m` header**: explicitly do not add one — DD4 keeps this a
  data-only change.

## Files Affected
- `the_one/llm/anthropic_provider.py` - resolver → catalog; docstring replaced; 200k default kept
- `tests/test_llm_max_context.py` - `TestAnthropicDefault` rewritten + new tests + memo-reset + module-docstring fix

---

## Post-Completion Checklist

**DEFERRED-COMMIT FLIGHT — do NOT commit, do NOT signal `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`test_llm_max_context.py`, `test_model_catalog*.py`, `test_anthropic_provider.py`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Signal `[HANDOFF:review-needed]`
