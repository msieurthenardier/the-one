# Leg: verify-integration

**Status**: completed
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Close the integration gaps the per-leg unit tests don't cover and prove the
flight's headline guarantees end-to-end: (1) **offline-restart survival** — with
no network and no cache, a freshly-constructed provider resolves the **catalog's**
window (1M for `claude-sonnet-4-6`, not the 200k default); (2) the catalog
**covers the models the app actually ships/uses**; (3) the **full suite** is green
at/above the F4 baseline with no new flakes. Test-only leg — no production code.

## Context

- Legs 1–5 each landed strong unit coverage: catalog lookup
  (`test_model_catalog.py`), refresh loop + offline fallback + seed-coverage guard
  (`test_model_catalog_refresh.py`), both provider resolvers
  (`test_llm_max_context.py`), the Studio endpoint per-model
  (`test_provider_api.py`).
- **The remaining gap is composition / restart-survival.** The operator's explicit
  requirement was: *reopening an old chat after a restart reports the correct
  window, offline.* The `/context-window` endpoint (`api.py:408-473`) calls
  `agent.llm._resolve_max_context_tokens_if_needed()` (`:472`) — but
  `test_api_context_window.py` mocks the agent wholesale, so the real
  resolver→catalog→seed chain is never exercised through a restart-like path.
- **"Offline" for OpenAI/Anthropic is inherent**: `context_window_for` reads the
  local catalog and makes **no** network call. The meaningful restart-survival
  proof is therefore: with `settings.data_dir` pointed at an **empty** dir (no
  cache — simulating a fresh/cleared install) and the memo reset, a **fresh**
  provider instance still resolves the correct window from the **bundled seed** —
  proving an old chat survives a restart with neither cache nor network.
- "Catalog-driven, not default": for Anthropic the class default is 200k, so
  asserting `claude-sonnet-4-6` → **1,000,000** proves the seed drove it.
- The F4 baseline (flight log): `3347 passed / 10 skipped / 594 deselected`, ~346s,
  no flakes. This flight adds ~hermetic catalog/refresh/provider/endpoint tests; the
  count rises and nothing should regress.

## Inputs
- Legs 1–5 landed (catalog single source of truth; table deleted).
- Existing suites: `test_model_catalog*.py`, `test_llm_max_context.py`,
  `test_provider_api.py`, `test_api_context_window.py`.

## Outputs
- `tests/test_model_catalog_integration.py` (or extend an existing file) — the
  offline-restart + shipped-model-coverage integration tests.
- Flight-log entry recording the **full-suite metrics** vs the F4 baseline.

## Acceptance Criteria
- [x] **Offline-restart survival (the headline test)**: with `settings.data_dir`
      monkeypatched to an **empty** `tmp_path` (no cache file) and the catalog memo
      reset, a freshly-constructed `AnthropicProvider(model="claude-sonnet-4-6")`
      resolves `max_context_tokens == 1_000_000` after
      `_resolve_max_context_tokens_if_needed()` — proving the value came from the
      **bundled seed** with no cache and no network, and is the **catalog** value
      (1M) not the **class default** (200k). Same test (or sibling) asserts a fresh
      `OpenAIProvider(model="gpt-4o")` → `128_000`.
- [x] **No network on the resolve path**: assert the OpenAI/Anthropic resolve makes
      no HTTP call — e.g. monkeypatch `httpx.AsyncClient`/`httpx.Client` to raise if
      invoked during the provider resolve, and confirm the resolve still succeeds
      from the seed. (Guards against a future regression that adds a live fetch to
      these providers.)
- [x] **Shipped-model coverage**: a conformance test asserts the catalog resolves a
      non-`None` window for the models the app ships/defaults to — at minimum the
      provider default models (`AnthropicProvider` default `claude-sonnet-4-6`;
      `OpenAIProvider` default `gpt-4o`) and a representative set of current
      families (e.g. `gpt-4o`, `o1`, `claude-sonnet-4-6`, and the Haiku-class id the
      seed carries — `claude-3-5-haiku-latest` → 200000). Drives the assertion
      through `context_window_for`.
- [x] **Catalog-driven-through-the-endpoint (composition)**: a test that the
      `/context-window` endpoint returns the catalog-driven value when backed by a
      real provider whose resolver runs against the catalog — either by patching
      `AgentFactory.create` to return an agent wrapping a **real**
      `AnthropicProvider(model="claude-sonnet-4-6")` (no API key needed — the
      resolver doesn't call the API) and asserting the endpoint yields
      `{"max_context_tokens": 1000000}`. (If wiring a real provider through the
      endpoint proves impractical, document why and rely on the provider-level
      offline test above as the restart-survival proof — but attempt the endpoint
      path first, since it's the actual restart code path.)
- [x] **Full suite green at/above baseline**: run the whole default suite; record
      `passed / skipped / deselected` + wall-clock in the flight log and compare to
      F4 (`3347 / 10 / 594`). Zero failures, no new flakes (re-run any suspicious
      test). The delta is explained (this flight's added hermetic tests).
- [x] Hermeticity: the new tests reset the catalog memo (autouse or explicit) so
      suite-order can't contaminate them.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_model_catalog_integration.py -x --timeout 30` → green.
- Full suite: **`make test-unit`** (the baseline-comparable selection — it applies
  the `-m 'not browser and not live and not pixel and not requires_bwrap and not
  discord_hat'` filter; a bare `run-tests.sh` without `-m` would pull in
  browser/live/pixel and isn't comparable) → record `passed/skipped/deselected` +
  wall-clock; compare to F4 `3347/10/594`. Zero failures.
- Spot-re-run the new integration test 2–3× to confirm no order-dependence/flake.

## Implementation Guidance

1. **Offline-restart test**: `monkeypatch.setattr(settings, "data_dir", tmp_path)`
   (empty dir → no cache), `model_catalog._reset_for_tests(None)` (force a fresh
   seed load). Construct `AnthropicProvider(model="claude-sonnet-4-6",
   api_key="x")`, `await provider._resolve_max_context_tokens_if_needed()`, assert
   `provider.max_context_tokens == 1_000_000`. Repeat for `OpenAIProvider(gpt-4o)`
   → `128_000`. Add a teardown reset.

2. **No-network assertion**: monkeypatch **`httpx.AsyncClient.send`** (and
   `httpx.Client.send` for completeness) to **raise** — **NOT `__init__`/
   instantiation**. `AnthropicProvider.__init__` builds an `anthropic.AsyncAnthropic`
   which instantiates an `httpx.AsyncClient` at construction (verified) — so
   patching `__init__` to raise breaks construction before the test reaches the
   resolve. Patching `.send` leaves construction intact and fails only if a real
   HTTP request is issued. Then run the provider resolve and assert it still
   returns the seed value with `.send` never invoked. (Only the Leg-2 refresh loop
   touches the network; it's not on the resolve path.)

3. **Shipped-model coverage**: a parametrized test over a representative id list
   asserting `context_window_for(provider, model) is not None` (and the known
   headline values: `claude-sonnet-4-6` → 1M, `gpt-4o` → 128k).

4. **Endpoint composition test** (**proven feasible** — design review live-verified
   the endpoint reads ONLY `agent.llm._resolve_max_context_tokens_if_needed()` and
   `agent.llm.max_context_tokens`, api.py:472-473, nothing else on `agent`): reuse
   `test_api_context_window.py`'s ASGI client pattern; patch `AgentFactory.create`
   to return `SimpleNamespace(llm=AnthropicProvider(model="claude-sonnet-4-6",
   api_key="x"))` (resolver reads the catalog, not the API — no key/network used).
   Assert the endpoint returns `{"max_context_tokens": 1000000}` — exercising the
   true restart code path (endpoint → resolver → catalog → seed). The fallback
   clause is retained only as defensive cover; the primary path is verified viable.

5. **Full-suite run + metrics**: run the default suite, capture the summary line,
   and write a flight-log note: baseline `3347/10/594` → new `X/Y/Z` (Δ explained:
   +N hermetic tests from F05 legs 1–6). Confirm 0 failures and no new flakes.

## Edge Cases
- **A real cache file in the dev `data_dir`** would shadow the seed — the test
  monkeypatches `data_dir` to an empty `tmp_path` precisely to exclude it, proving
  the **seed** path. Do not rely on the ambient data dir.
- **Memo contamination from earlier tests** (the refresh tests inject catalogs) —
  reset in setup AND teardown.
- **Endpoint test provider construction**: `AnthropicProvider.__init__` instantiates
  `anthropic.AsyncAnthropic`, which instantiates an `httpx.AsyncClient` — but **no
  HTTP request is issued** at construction. A dummy `api_key="x"` is fine; no
  network occurs. (This is exactly why the no-network test patches `.send`, not
  `__init__`.)
- **Don't assert exact full-suite counts as a hard gate** — assert **0 failures**
  and that passed ≥ baseline; record the exact numbers as an observation (run-to-run
  deselected/skipped can vary slightly, per the F4 debrief's own note).

## Files Affected
- `tests/test_model_catalog_integration.py` - new integration/restart/coverage tests
- flight-log.md - full-suite metrics vs baseline (recorded by this leg)

---

## Post-Completion Checklist

**DEFERRED-COMMIT FLIGHT — this is the LAST autonomous leg. After it lands, the
Flight Director runs the single flight-wide review + commit. Do NOT commit, do NOT
signal `[COMPLETE:leg]`.**

- [x] All acceptance criteria verified
- [x] Full suite run; metrics recorded in flight-log vs F4 baseline; 0 failures
- [x] Update flight-log.md with leg progress entry + the metrics
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Signal `[HANDOFF:review-needed]`
