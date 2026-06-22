# Flight Debrief: Cross-Provider Tool-Use Conformance Suite

**Date**: 2026-06-19
**Flight**: [Cross-Provider Tool-Use Conformance Suite](flight.md)
**Status**: landed
**Duration**: 2026-06-19 (single execution session)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The flight delivered the cross-provider tool-use conformance suite in full and held a
strictly test/infra-only footprint:

- A provider-parametrized `request → tool_call → tool_result → final-answer`
  conformance suite drives `provider.complete()`/`stream()` directly across
  **Anthropic, OpenAI, Ollama, and Mock** at the `LLMProvider` contract — structural
  (not wire-byte) assertions, hermetic, credential-free by default. **No cross-provider
  divergence surfaced** — the canonical shape was uniform on first run across all four,
  which is itself substantive evidence the contract is well-formed.
- All three Flight-2 #122 coverage gaps closed (cross-provider same-schema assertion;
  OpenRouter `anthropic/*` `complete()`/`stream()` smoke with on-wire sanitize proof;
  `stream()` temperature-retry→`tools.N` sub-path) + the DD6 `_TOOLS_INDEX_RE`
  format pin.
- The deferred OpenRouter→Anthropic parity question resolved as **forward-with-WARN**,
  formalized by a pin test + a module-docstring note — **zero production logic change**;
  the kernel stays a leaf.
- The #105 loose-format recovery joined the matrix as a fixtured row (contract-level,
  kwargs-form `GEMMA_FIXTURE`).
- The shared test-fixtures extraction landed (`tests/fixtures/tool_schemas.py`).
- The `make test-unit` marker-selection bug fixed (additive `-m`; `requires_bwrap` +
  `discord_hat` now correctly deselected).
- A light, key-gated, self-skipping live tool round-trip added (anti-duplication
  verified vs the existing swap test).

### Mission Criteria Advanced

- **MET** — "A cross-provider tool-use conformance test exists and passes for
  Anthropic, OpenAI, Ollama, and Mock." Checked off in `mission.md`.
- **Reaffirmed** — "No agent framework is added and the provider layer still wraps
  official SDKs; the `LLMProvider` contract and provider-shape-portability convention
  are preserved." Trivially held (test/infra-only).

**Production footprint**: 2 files — `the_one/llm/openrouter_provider.py` (docstring
note, +10) and `Makefile` (one recipe). 19 files total, +3495/−92.

## What Went Well

- **Test/infra-only scope genuinely held.** A flight that also resolved a deferred
  policy decision (DD3) touched zero production logic — unusually clean. The scope
  guard was verified at the flight-wide review (`git diff the_one/` = docstring-only).
- **Design review caught empirical-premise errors before implementation, three times**:
  `requires_bwrap` is ~44 tests not the stale `pyproject.toml:85` "12"; the DD6 caller
  lists were wrong (`PRESS_KEY` not in the anthropic file; `_mk_bad_request` not shared
  across three); Ollama's `/api/show` serves the **context-resolver**, not
  `supports_tools()`. All three would have forced mid-implementation pivots or rework.
- **The scripted-transport harness is a sound, reusable abstraction.** `CannedTurn` +
  `ScriptedProvider` are provider-neutral; a new provider needs only a `make_<provider>`
  constructor. Tight design touches: the `call_count()` guard against stateless-handler
  regressions, the selective `request_bodies` capture (proves sanitize ran through
  `complete()`/`stream()`, not just `tool_schema()`), and the `make_openrouter`
  context-resolver defuse via the provider's own `_max_context_tokens_resolved` sentinel
  (no new test seam).
- **A latent correctness improvement fell out of DD6**: converging `test_streaming.py`'s
  `_make_bad_request` (a `MagicMock` body) onto the real-`httpx.Response` builder means
  the streaming error-handling tests now exercise a structurally faithful error object,
  not just a style cleanup.
- **Per-leg design-review + deferred-commit cadence** kept quality high while avoiding
  per-leg review/commit overhead; every design review came back approve / approve-with-
  changes and all high/medium findings were incorporated before implementation.

## What Could Be Improved

### Process
- The leg-05 spec inherited a stale count (`requires_bwrap`≈12) from `pyproject.toml:85`;
  design review corrected it to ~44. The spec did flag the source as stale and told the
  implementer to reproduce from the run — the right mitigation — but the lesson is to
  treat any cited numeric count as design-review-verifiable, not authoritative.
- `make_openrouter` was framed as a leg-02 harness deliverable but actually landed in
  leg 03 (the leg whose test first needs it). Harness constructors belong in the leg
  that introduces their consumer, not the foundational harness leg — worth encoding in
  future leg-dependency planning.

### Technical
- **`GEMMA_FIXTURE` now has two definitional copies** (`test_toolcall_recovery.py` and
  the conformance module), re-declared verbatim with a source comment for drift
  detection. Defensible (avoids test-to-test import coupling) but it is the exact drift
  pattern leg-01 extraction fought. If a third consumer appears, move it to
  `tests/fixtures/`.
- **`make_mock`'s `call_count()` counts configuration events, not HTTP hits** — a
  different semantic from the transport-backed providers. Correct and documented in the
  method docstring, but the harness *module* docstring should state it so a reader of
  the harness contract doesn't miss it.
- **Minor coverage gap**: the unsanitizable-schema asymmetry is pinned at the method
  level (`tool_schema()` / `_build_kwargs()`), not driven through `complete()`/`stream()`
  end-to-end. Low priority — the production logic on that path is thin and the common
  combinator case is covered end-to-end.

### Documentation
Three flag-don't-fix items were identified and correctly deferred (out of this flight's
allowed-edit scope):
- `pyproject.toml:85` per-marker comment is stale (`requires_bwrap=12`, actual ~44).
- `Makefile` `make test` docstring ("unit + browser") contradicts addopts, which
  deselects `browser`.
- `the_one/agents.md` provider-shape-portability "Pinned by" list should gain a
  one-line pointer to the conformance suite.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Flight-wide Reviewer used Sonnet, not the crew's Haiku | Deferred-commit model concentrates the whole flight's correctness into one review of a large multi-file diff; non-Opus per the hard rule | Yes — for deferred-commit flights with large concentrated diffs, a stronger-than-Haiku (non-Opus) reviewer is the right default; record the deviation |
| `make_openrouter` landed in leg 03, not the leg-02 harness | The OpenRouter `anthropic/*` smoke (leg 03) is its first consumer | Yes — harness constructors belong with the leg that introduces their consumer |
| Leg 02 unblocked from leg 01 mid-design | Round-trip needs only a tool def + script; the shared fixtures are a leg-03 consumer | Yes — derive leg dependency graphs from actual import/consumer relationships, not "uses the module ⇒ depends on its leg" |
| `requires_bwrap` re-baselined 12 → ~44 | The `pyproject.toml:85` source comment was stale | Yes — design review verifies cited numeric counts against live code |

## Key Learnings

- **Test metrics (this run): `3347 passed / 10 skipped / 594 deselected`, ~346s** —
  reproduces leg-05's recorded `3347/10/594` (~327s) within run-to-run variance, 0
  failures, no flakes. F3→F4: **passed +45, skipped −8, deselected +53**. Dominant
  terms: the marker fix moves ~44 `requires_bwrap` from passed→deselected (and +49
  total deselected with `discord_hat`), offset by ~32 new hermetic flight-04 tests in
  passed. Wall-clock **dropped 385s → 346s** — F3's figure was inflated because the
  buggy recipe was running 44 `requires_bwrap` pty tests with non-trivial setup; the new
  figure is structurally correct.
- **"Design review verifies empirical premises" is a load-bearing pattern**, not
  advisory. Three numeric/structural premises were wrong in specs and all three were
  caught in design review, not implementation. This is the strongest argument for
  keeping the deferred-commit model's per-leg design-review phase non-optional.
- **Re-declared empirical fixtures with a source comment** (the `GEMMA_FIXTURE` pattern)
  turn an invisible copy into a traceable relationship — a good standard for any
  recorded live-model output reused in hermetic tests.
- **The Ollama streaming recovery path carries a documented behavioral asymmetry**:
  interim stream chunks carry raw un-stripped content; only the final chunk carries the
  stripped content + recovered `ToolCall`. Not a bug, but a footgun if the agent loop
  ever consumes interim chunks for early decisions. The test correctly asserts the final
  chunk only.
- **Skill effectiveness**: mission/flight/leg artifacts and the agentic-workflow cadence
  worked well end-to-end. The flight skill's apparatus/premise-audit guidance paid off
  (the design reviews caught feasibility *and* observability premises). No skill changes
  recommended from this flight.

## Recommendations

1. **Schedule a short maintenance leg/flight for the three flag-don't-fix doc items**
   (`pyproject.toml:85` marker comment 12→44; `Makefile` `make test` docstring;
   `the_one/agents.md` conformance-suite pointer). Low effort, no logic risk; they
   currently mislead a new contributor or an AI agent reading the files.
2. **Document `make_mock`'s `call_count()` semantics in the `scripted_transport.py`
   module docstring** (config-events vs HTTP-hits), and treat `CannedTurn`/
   `ScriptedProvider` shape as a stable contract — changing them breaks all consumers.
3. **Revisit the deferred OpenRouter forward-with-WARN vs Anthropic-direct
   drop-and-proceed asymmetry** when the next flight touches the sanitize kernel or adds
   OpenAI strict structured-output — it is now documented but unresolved, and is the
   largest deferred item in the provider layer.
4. **If a third `GEMMA_FIXTURE` consumer appears, promote it to `tests/fixtures/`** (and
   consider an end-to-end OpenRouter unsanitizable-schema round-trip test if a future
   flight is already in `openrouter_provider.py`).
5. **Mission-level**: the F3 `DEGRADED_BASE_PROMPT`-derive refactor and the
   non-tool-model subsystem design note remain open — `/mission-debrief` should recheck
   their status before declaring mission 16 complete.

## Action Items

- [ ] Maintenance leg: correct `pyproject.toml:85` marker comment (12→44), the `Makefile`
      `make test` docstring, and add the `the_one/agents.md` conformance-suite pointer.
- [ ] Add the `make_mock` `call_count()` semantics note to `scripted_transport.py`'s
      module docstring.
- [ ] (Forward) Re-evaluate OpenRouter parity / kernel promotion when the sanitize-kernel
      or OpenAI-strict structured-output flight lands.
- [ ] (Mission) Recheck F3 `DEGRADED_BASE_PROMPT` refactor + non-tool-model design-note
      status before mission-16 completion.
