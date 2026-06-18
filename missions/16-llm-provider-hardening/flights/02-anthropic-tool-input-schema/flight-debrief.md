# Flight Debrief: Anthropic Tool `input_schema` Compatibility (#122)

**Date**: 2026-06-18
**Flight**: [Anthropic Tool `input_schema` Compatibility (#122)](flight.md)
**Status**: landed
**Duration**: 2026-06-18 (single execution session; spec authored 2026-06-17/18)
**Legs Completed**: 4 of 4 autonomous (optional `uat-and-alignment` skipped per operator — leg 04's live first-party verification covered the core criterion)

## Outcome Assessment

### Objectives Achieved

Fully achieved. One non-conforming MCP tool schema can no longer kill an Anthropic
turn. Shipped:

- **`the_one/llm/_schema_sanitize.py`** — a pure, stdlib-only (`copy`-only) kernel that
  normalizes a tool `input_schema` to a single top-level object schema (union-merge
  `anyOf`/`oneOf` with required-intersection, union-merge `allOf` with required-union,
  collapse array `type` to the scalar `"object"`), raising `UnsanitizableToolSchema(reason)`
  for genuinely-unrepresentable shapes. DD2 non-mutation (deep-copy) verified by `is`-identity.
- **`anthropic_provider.py`** — sanitize-before-send in `_to_anthropic_tool`; DD5
  drop-and-proceed in `_build_kwargs` (omit `tools` when all dropped; named, `reason`-carrying
  warning); DD6 `BadRequestError → tool-name` net composed with the existing temperature-retry
  in both `complete()` and `stream()`, covering the retry's second call.
- **`openrouter_provider.py`** — a live probe proved OpenRouter forwards schemas to the
  Anthropic backend unmodified (identical #122 400), so a `tool_schema` override sanitizes
  `anthropic/*` routes (minimal scope; unsanitizable → forward-with-WARN, no DD5/DD6 parity).

### Mission Criteria Advanced

- ✅ **"A tool whose `input_schema` uses top-level `oneOf/allOf/anyOf` … no longer fails the
  whole Anthropic turn … names the offending tool rather than a bare index."** — fully met,
  fixture- **and** live-test-backed against the real Anthropic constraint. (Checked off in the
  mission.)
- ✅ **"No agent framework is added; the `LLMProvider` contract and provider-shape-portability
  convention are preserved."** — change is confined to `the_one/llm/`; `base.py`, the other
  adapters, the MCP layer, the agent loop, and the web UI are untouched.

### Checkpoints

All five flight checkpoints met: sanitizer module + unit suite green; adapter sanitizes
before send (one bad tool no longer kills the turn); `BadRequestError` surfaces the tool
**name**; the OpenRouter→Anthropic question resolved (wired, gated); the live-gated test
confirms real Anthropic accepts the sanitized output and still 400s on the raw one.

## What Went Well

- **Kernel-first, wire-second, verify-live sequencing.** Building and exhaustively testing
  the pure kernel (leg 01) before any adapter touch (leg 02) let the adapter tests use the
  *real* kernel rather than a mock — a stronger integration signal. Clean 4-leg hierarchy.
- **The live-probe-resolves-open-question mechanism.** The OpenRouter open question was not
  decided at design time; it was assigned to a dedicated leg, resolved by a live probe whose
  output was recorded as flight-log evidence, with the adaptation trigger ("wire only if it
  demonstrably rejects AND a clean adaptation exists") pre-authorized in the spec. When the
  probe **falsified** the spec's "likely outcome," the mechanism handled it without a divert —
  operator confirmation for the scope decision only. Worth standardizing.
- **Pre-flight "known SDK quirks" in the leg spec.** Leg 02 documented the
  `anthropic.BadRequestError` construction gotcha (required keyword-only `response`/`body` on
  0.97.0) and the streaming async-CM mock shape *before* implementation — the implementer
  avoided rediscovering a `TypeError` the hard way.
- **DD4's one empirically-undecidable rule was honestly deferred and then pinned.** The array-
  `type` collapse was marked provisional and confirmed load-bearing by leg 04: first-party
  Anthropic *rejects* `type:["object","null"]` (`Input should be 'object'`) and accepts the
  collapsed scalar. Not merely conservative — necessary.
- **Independent final review.** The whole-flight Reviewer (Haiku, no knowledge of the build)
  confirmed scope-clean, ruff-clean, no regressions, no leaked secrets/paths — zero fix cycles.

## What Could Be Improved

### Process

- **The "likely outcome" framing slightly under-planned leg 03's most-probable path.** The
  Open Question's prose leaned 70/30 toward "document and scope out," while the Adaptation
  Criteria simultaneously pre-authorized the wire. The spec could have stated explicitly that
  "if the conditions are met, leg 03 becomes a code-change leg with its own design review" as
  an expected branch rather than an exception. Outcome was good; the framing could be crisper.
- **Per-leg design reviews used the implementer role (Developer/Sonnet), not the independent
  Reviewer.** For this clean, additive-change flight that was fine (all reviews were
  approve-with-additive-changes, no second cycle). For future flights with tighter or novel
  design constraints, route at least the high-complexity leg design reviews through the
  independent Reviewer so design and implementation are independently validated.

### Technical

- **OpenRouter↔Anthropic-direct behavioral asymmetry (the flight's biggest architectural
  consequence).** For a *genuinely-unsanitizable* tool: Anthropic-direct **drops** it and the
  turn proceeds (DD5); OpenRouter→Anthropic **forwards** it and the backend 400s the whole turn
  (WARN only, minimal scope). This is intentional and "no worse than today," but it means the
  same unsanitizable schema behaves differently depending on the route. Sound, but a **latent
  inconsistency to resolve in Flight 4** — decide whether OpenRouter gains DD5/DD6 parity or
  "forward-with-WARN" becomes its formal contract. (Note: the common `anyOf`/`oneOf` case — the
  real-world trigger — *is* fixed on both paths; only the rare unsanitizable case diverges.)
- **DD6's `tools\.(\d+)\.` regex is Anthropic-error-format-specific.** It matches the confirmed
  first-party wording today and falls back to re-raising unchanged if the format drifts (correct
  fail-safe), but the name-mapping would silently stop working. Add a single
  `test_tools_index_re_matches_known_format` assertion pinning the known string so a format
  change surfaces as a red test rather than silent degradation.
- **Test-metrics run:** `.venv/bin/pytest -q` (host-native; Docker unavailable) →
  **3232 passed / 10 skipped / 592 deselected / 0 failed / 0 flakes**, wall-clock **313.6 s**.
  Vs the M15 F9 debrief baseline (~3219 passed, ~341 s): **+13 net passing**, no regressions, no
  new flakes; wall-clock within the historical 312–392 s band. The +13 are this flight's hermetic
  additions (32 sanitizer + 17 adapter + 5 new OpenRouter; the prior 18 OpenRouter tests were
  already counted). The 3 live tests are among the 592 deselected, as designed. (Minor: prior
  debriefs reported 18 skipped vs 10 now — a skip-vs-deselect categorization difference across
  runs, not a regression.)
- **Small coverage gaps (non-blocking):** no test exercises `complete()` with `tools=None/[]`
  end-to-end through the new path (the `if tools:` guard); the OpenRouter unsanitizable-fallback
  is exercised through only the bare-`$ref` shape (the kernel's other unsanitizable shapes are
  exhaustively covered in `test_schema_sanitize.py`, so this is thin, not absent); no end-to-end
  smoke through `OpenRouterProvider.complete()/stream()` with an `anthropic/*` slug (only
  `tool_schema()` is called directly — the single-chokepoint argument is sound, but a smoke test
  would close it). All three are natural **Flight 4** conformance-suite targets.

### Documentation

- **`the_one/agents.md` correctly left unchanged** — internal adapter fix, no new agent-facing
  contract. If the project has a provider-compatibility/troubleshooting doc, a one-line note
  ("Anthropic rejects top-level `oneOf`/`allOf`/`anyOf` in tool schemas; the adapter sanitizes
  automatically") would aid future diagnosis. Optional.
- **The OpenRouter forward-with-WARN asymmetry lives only in code comments + flight artifacts.**
  A short note in `openrouter_provider.py`'s module docstring would help future maintainers
  understand why the two paths diverge.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 03 became a **code-change** leg (planned as probe/documentation) | Live probe **falsified** the spec's "likely outcome": OpenRouter forwards schemas to the Anthropic backend, which 400s on #122 identically. Adaptation Criteria (reject + clean adaptation) were met. | **Yes** — standardize the *live-probe-resolves-open-question* pattern for open questions about external system behavior. |
| Tests run **host-native** (`.venv/bin/pytest`) instead of `docker exec the-one pytest` | Docker daemon unavailable in the execution environment. Suite has no container-only deps; CLAUDE.md documents the host-native path. | **No** — environment-specific. But the crew "Implement" prompt's hard-coded `docker exec` should tolerate a documented host-native fallback. |
| OpenRouter wired **without DD5/DD6 parity** | Operator-scoped minimal: fix the common `anyOf`/`oneOf` case now; defer drop-and-proceed/named-error to a later flight. | **No** (it's a scoping choice) — but **track** the parity gap as a Flight 4 decision. |

## Key Learnings

- **A "second caller" is not automatically a "promote-the-interface" trigger.** DD1 deferred a
  uniform `LLMProvider.sanitize_tool_schema()` until a second real caller; one arrived this
  flight (OpenRouter), seeming to fire the trigger. But the two callers are **asymmetric**:
  Anthropic calls the kernel inside its private `_to_anthropic_tool` (it overrides the whole
  build path and does *not* use `tool_schema()`), while OpenRouter calls it inside the base-class
  `tool_schema()` seam — and their unsanitizable-tool behavior differs (drop vs forward). A
  uniform base method would have to reconcile behaviors that *can't* share a default. **Refined
  trigger:** promote only when a caller appears in the *`tool_schema()` seam with symmetric
  behavior* — i.e. when the OpenAI-strict structured-output capability flight needs the same
  kernel there, or when Flight 4 grants OpenRouter DD5 parity. The promotion stays mechanical
  (logic stays in `_schema_sanitize.py`; only call sites move).
- **Provider-neutral pure kernels compose across structurally different callers.** The same
  237-line kernel dropped onto two different tool shapes (Anthropic-native `input_schema` dict
  vs OpenAI `function.parameters` dict) with no signature change — vindicating the leaf-module
  (`_streaming.py`-style) choice.
- **Live verification can convert a "provisional" design rule into a "load-bearing" one.** The
  array-`type` collapse would have remained an unverified guess without leg 04.

## Recommendations

1. **Flight 4 owns the OpenRouter parity decision.** Explicitly decide whether the
   OpenRouter→Anthropic path gains DD5 drop-and-proceed + DD6 tool-name parity, or whether
   "forward-with-WARN" becomes its documented contract. Don't leave it as an incidental asymmetry.
2. **Track the uniform-interface promotion as a deferred item, not a fired trigger.** Promote the
   kernel to a `LLMProvider.sanitize_tool_schema()` base no-op only when a symmetric
   `tool_schema()`-seam caller appears (OpenAI-strict capability flight, or Flight-4 OpenRouter
   parity). Record the adoption nuance: Anthropic's adoption point is `_to_anthropic_tool`, not
   the base `tool_schema()`.
3. **Add a DD6 format-monitoring test** (`test_tools_index_re_matches_known_format`) pinning the
   confirmed first-party `tools.0.custom.input_schema: …` string so an Anthropic error-format
   change surfaces as a red test instead of silent name-mapping loss.
4. **Fold the small coverage gaps into Flight 4's cross-provider conformance suite:**
   cross-provider same-schema assertion (sanitized for Anthropic & `anthropic/*`-OpenRouter,
   verbatim for OpenAI); an `OpenRouterProvider.complete()/stream()` end-to-end smoke with an
   `anthropic/*` slug; and a decision on the `stream()` temperature-retry→`tools.N` sub-path.
5. **Carry methodology wins forward:** (a) standardize the live-probe-resolves-open-question
   pattern in flight-design guidance; (b) keep the pre-flight "known SDK quirks" leg-spec section
   for any SDK-touching leg; (c) for Flight 3 (#105), extract the `_mk_bad_request` / mocked-client
   harness and the inlined `PRESS_KEY` fixture into shared test helpers if a second consumer
   appears (currently inlined in 3 test files — a fourth justifies a `tests/fixtures/` module).

## Action Items

- [ ] Flight 4: decide + implement the OpenRouter DD5/DD6 parity question (or formalize
      forward-with-WARN as the contract). *(carries the flight's one tracked debt item)*
- [ ] Add `test_tools_index_re_matches_known_format` to `tests/test_anthropic_provider.py`
      (cheap; prevents silent DD6 regression).
- [ ] Flight 4: cross-provider conformance suite to close the three coverage gaps above and
      become the regression net for this fix.
- [ ] When the OpenAI-strict (or Flight-4 OpenRouter-parity) caller lands, promote the kernel to
      a uniform `LLMProvider.sanitize_tool_schema()` base no-op (mechanical refactor).
- [ ] (Optional) One-line provider-compatibility note (Anthropic top-level-combinator rejection +
      auto-sanitize) wherever the project documents provider quirks; module-docstring note on the
      OpenRouter forward-with-WARN asymmetry.
- [ ] (Methodology, mission-control) Tolerate a documented host-native `pytest` fallback in the
      leg-execution "Implement" crew prompt when Docker is unavailable.
