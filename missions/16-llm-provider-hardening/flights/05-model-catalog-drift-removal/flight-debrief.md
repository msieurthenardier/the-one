# Flight Debrief: Model-Catalog Drift Removal

**Date**: 2026-06-20
**Flight**: [Model-Catalog Drift Removal](flight.md)
**Status**: landed
**Duration**: 2026-06-19 (planned + 6 autonomous legs) – 2026-06-20 (HAT + land)
**Legs Completed**: 6 of 6 autonomous + HAT (leg 07)

## Outcome Assessment

### Objectives Achieved
The two hand-maintained, silently-drifting context-window sources are gone. The
OpenAI `OPENAI_MODEL_CONTEXT` longest-prefix table (and its verbatim duplicate in
the Studio model-list endpoint) and Anthropic's flat `200_000` constant are both
replaced by a single shared `context_window_for(provider, model)` lookup against a
built-in catalog (bundled seed + daily models.dev refresh into an on-disk cache),
resolved locally cache→seed→default. `OPENAI_MODEL_CONTEXT` is deleted
(`ImportError` confirmed). Current Claude models now report their native 1M window;
Haiku-class report 200k. Offline restart of an old chat resolves the correct window
with no network call (asserted in the integration suite). No framework added; the
`LLMProvider` contract and SDK-wrapping shape are preserved.

### Mission Criteria Advanced
- **MET** — "Model context-window limits for OpenAI and Anthropic are sourced
  without a hand-maintained per-model table that silently drifts." Built-in catalog,
  refreshed daily, fail-open local resolution.
- **MET (verified-as-boundary)** — "No agent framework added; provider layer still
  wraps official SDKs; `LLMProvider` contract preserved." This flight added a leaf
  data module + a background refresh loop only.

### Test Metrics (debrief run, `make test-unit`, host-native `.venv`)
Run on `main` @ `d51e179` (post-F05 + F06 + PR #135), single run, exit 0:

| Metric | This run | F05 at landing | F4 baseline |
|--------|----------|----------------|-------------|
| Passed | 3448 | 3422 | 3347 |
| Failed | 0 | 0 | 0 |
| Skipped | 10 | 10 | 10 |
| Deselected | 595 | 594 | 594 |
| Wall-clock | 324.5s | ~296s | ~346s |

F05 landed **+75 passing** over F4 (hermetic catalog/refresh/provider/endpoint
tests: L01 +22, L02 +22, L06 +9, plus net L03/L04 rewrites). Skip count stable at
**10** since F3 fixed the `requires_bwrap` marker bug; deselected ticked to 595 at
F6. This run's +5 over F6 is PR #135's `doctor` probe tests — **no F05 test lost**.
Wall-clock sits inside the historical 296–346s band. **No flakes**; the 4
`Event loop is closed` lines are the pre-existing aiosqlite async-teardown warnings
already flagged in the F06 debrief (not flakes, not F05-introduced).

## What Went Well
- **DD5 (unify the two consumers) delivered exactly as designed, zero revision.**
  The duplicate `_openai_ctx` table and the Anthropic class-constant read in the
  Studio endpoint are both gone; one drift surface remains, not three.
- **DD3 (freshness made loud) closes the named "silently drifts" defect.** Per-model
  miss → WARN, whole-catalog parse failure → WARN, `fetched_at`/`generated_at`
  stamps, `make refresh-model-catalog`.
- **Strong, reusable patterns emerged:** (a) the fail-open boundary placed in
  `_get_catalog()` (not `_load_catalog()`) as a deliberate test seam; (b) the
  **seed-coverage write guard** — never overwrite a known-good local artifact with a
  fetch that doesn't cover the bundled floor; (c) shared `project_raw`/`apply_floor`
  helpers used by both the runtime loop and the regenerate script (no parser drift).
- **Convention fidelity:** the refresh loop is a faithful clone of
  `_chat_history_purge_loop` (startup catch-up, due-based recheck, shutdown drain);
  providers slot into the existing `_resolve_max_context_tokens_if_needed` hook with
  no contract change.
- **Architecturally clean:** `model_catalog.py` is a true leaf (imports only
  `settings` + stdlib/httpx); both providers and the web layer depend on it, it on
  neither — no cycle, and an improvement over the web layer reaching into a provider
  class constant.
- **The HAT (leg 07) earned its keep** — it was the only leg that caught both
  blocking defects (see Lessons).

## What Could Be Improved

### Process
- **Live-source-shape confirmation was treated as a deferred open question when it
  should have been a hard, blocking prerequisite.** models.dev was unreachable in
  the execution env, so the seed was hand-authored and `project_raw` was built
  *blind* against a guessed shape — then unit-tested against self-authored fixtures
  *matching that same guess*. The suite went green while the real refresh pipeline
  parsed 0 models and never wrote the cache (DD1's "stay current without redeploy"
  was non-functional through Leg 6). A blind parser with passing tests is more
  dangerous than no parser. This is the second time in the mission (after F2/F3) a
  green-but-wrong pipeline came from building against an unverified external contract.
- **The "optional" HAT was not optional.** It caught both the dead refresh pipeline
  and the seed's over-reported windows (`claude-sonnet-4-5`/`opus-4-5` seeded at 1M;
  actually 200k). The flight's call that "no behavior test needed — data-sourcing
  logic read through existing surfaces" was wrong: the failure *was* that the data
  and its sourcing were wrong, which only a live/real-shape check surfaces.

### Technical
- **LIVE BUG — the bundled seed is not collected into the frozen Windows build.**
  `_load_seed()` uses `importlib.resources.files("the_one.llm")` (correct, PyInstaller-safe),
  but `packaging/windows/the-one.spec` only collects `interfaces/web/static/**`;
  nothing collects `llm/data/*.json`. PR #135 added `collect_submodules("the_one.llm")`
  — that ships *modules*, not *data files*. Net effect in a frozen install: `_load_seed()`
  fails → fail-open → empty catalog → **every model reports the class default (200k
  for all Claude, including the 1M default `claude-sonnet-4-6`; 128k for OpenAI)** —
  silently, exactly the drift DD6 was written to prevent. DD6's `pyproject.toml`
  package-data fix covers wheels/sdist but **not** the PyInstaller path. The
  `doctor llm providers` probe does **not** catch this (it imports modules; the seed
  is read lazily inside a swallowing try/except, so the probe stays green).
- **`_OPENAI_FLOOR` resurrects a small hand-maintained table** inside the catalog
  module as a no-regression floor. Justified, but it is residual hand-maintenance
  that DD3's loudness does not cover.
- **Longest-prefix matching over authored keys is a foot-gun** for per-version
  window differences (it produced the over-reporting bug). Correct while the seed
  carries exact dated ids; a future regeneration that drops a dated id silently
  re-exposes the broad-prefix hazard.
- **DD3 made *drift* loud but not a *silently-failing refresh*.** A non-writing
  refresh (`refresh_catalog_cache() → False`) logs WARN and the loop keeps serving
  from seed — the system looks healthy. That gap is what let the blind-parser bug
  survive automated testing.

### Documentation
- `THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS`, `make refresh-model-catalog`,
  the cache location (`settings.data_dir / model_catalog.json`), and the
  cache→seed→default resolution order are only documented in-code/Makefile-help. A
  dev/operator-facing note was explicitly punted to this debrief (Post-Flight `[~]`).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD4 reframed mid-planning: report catalog window, send no beta header (was: enable `context-1m` header) | Design review found current Claude models are natively 1M — no header, no premium; planning premise was false | Yes — the design-review-corrects-a-false-premise loop is the value |
| Leg 3→5 deletion resequencing: keep `OPENAI_MODEL_CONTEXT` alive through Leg 3, delete in Leg 5 after both consumers migrate | Deleting in Leg 3 would red the tree until Leg 5, violating the deferred-commit "every leg-end is green" invariant | Yes — sequence destructive deletes after all consumers migrate |
| Flight-wide review on Sonnet (not crew's Haiku) | Single concentrated ~1826-insertion / 12-file diff under deferred-commit | Yes — already standardized in F4 debrief for large deferred-commit diffs |
| Seed hand-authored + parser built blind (models.dev unreachable) | External source offline in exec env | **No** — this *caused* the two HAT-caught defects; the fix is to block, not improvise (see Recommendations) |

## Key Learnings
- **Packaging-survival is a mission-level failure class, not a per-flight concern.**
  Three instances of "works in the editable dev tree, silently dropped from the
  packaged build" now exist in `the_one/llm/`: DD6 (seed absent from wheels —
  caught proactively), PR #135 (provider modules tree-shaken from the freeze —
  string `__import__` invisible to PyInstaller), and the newly-found frozen-seed gap
  (this debrief). The flight was actively *thinking* about packaging survival (DD6
  proves it) and still missed the sibling instance sitting in the same package. Per-
  flight vigilance is necessarily piecemeal; this class needs a mission-level guard.
- **Self-authored fixtures matching an assumed external shape produce false-green
  suites.** The unit tests validated the parser against the same wrong assumption
  the parser was built on. Tests are only as truthful as the contract they encode.
- **For data-sourcing flights, a live/real-shape check is load-bearing, not
  optional polish.** "Read through existing surfaces, so no behavior test needed"
  under-weights that the *correctness of the data itself* is the thing under test.

## Recommendations
1. **Fix the frozen-seed gap now (live correctness bug in the shipped Windows
   build).** Add `*collect_data_files("the_one", includes=["llm/data/*.json"])` to
   the spec's `datas` — a one-line packaging fix in the same family as PR #135.
2. **Add a frozen-build *resolution* gate, not just an import gate.** Extend the
   `doctor` smoke (or add a sibling probe) to actually call
   `context_window_for("anthropic", "claude-sonnet-4-6")` and FAIL when frozen if it
   returns the default instead of the seed's 1M — so the CI packaged-smoke catches a
   missing/empty seed. Frame as a behavior test / frozen-resolution smoke (real-
   environment behavior the unit suite cannot observe).
3. **Make "external API shape unconfirmed" a hard leg gate.** Any leg parsing a
   third-party payload must live-probe (or capture a real-shape fixture once) before
   the parser is written; an unsatisfiable prereq blocks or de-scopes the leg rather
   than deferring to a guess.
4. **Carry a mission-level "what must survive packaging?" checklist to the mission
   debrief** — enumerate everything resolved by a mechanism static analysis can't
   see (string/dynamic imports, `importlib.resources` data files, `platformdirs`
   paths, lazy in-function imports) so any flight touching `the_one/llm/` checks it.

## Action Items
- [ ] **(High, live bug)** Add `collect_data_files("the_one", includes=["llm/data/*.json"])` to `packaging/windows/the-one.spec` `datas`; rebuild + confirm the frozen `doctor` resolves a 1M Claude window.
- [ ] **(High)** Extend `the_one/diagnostics.py` `doctor` with a catalog-resolution assertion (instantiate a provider in the frozen build, assert a non-default catalog-driven window). Author as a frozen-resolution smoke.
- [ ] **(Medium)** Pin the write-guard invariant: a test asserting the Anthropic seed section is non-empty and is what gatekeeps the refresh write (closes the `apply_floor`-masks-OpenAI-coverage weakness before someone trims the seed).
- [ ] **(Medium)** Add operator/dev docs for `THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS`, `make refresh-model-catalog`, the cache location, and the cache→seed→default resolution order.
- [ ] **(Mission-level)** Record the "packaging-survival checklist + single frozen-build resolution smoke" practice for the Mission 16 debrief — DD6 vs PR #135 vs the frozen-seed gap are three instances of one class.
