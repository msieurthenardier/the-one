# Flight: Request-Param Capabilities — reasoning_effort, structured outputs, stop (A4)

**Status**: in-flight
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria

- [ ] **Each prioritized capability gap is either implemented behind the
      `LLMProvider` contract or explicitly deferred** with a recorded reason.
      *(This flight implements backlog **A4** — reasoning_effort, structured
      outputs / JSON mode, stop sequences — and records an explicit deferral of
      strict client-side schema validation. It advances but does not by itself
      close #3: A2 remains a following flight; A3/A5/B1–B4 are deferred at mission
      close.)*
- [ ] No agent framework is added; the provider layer still wraps official SDKs;
      the `LLMProvider` contract and provider-shape-portability convention are
      preserved. *(A4 via the config surface keeps the ABC signature stable — see
      DD1.)*

---

## Pre-Flight

### Objective

Bring the provider layer to coverage of three request-side capabilities the
official SDKs expose but the-one does not yet wire through — **reasoning effort**,
**structured outputs / JSON mode**, and **stop sequences** (backlog item **A4**
from the Flight 1B capability audit). Each is resolved from the **provider config
surface** (config dict → env → default), mapped to each provider's native SDK
shape, and exercised by the cross-provider conformance suite plus a live HAT.
The `LLMProvider` ABC signature stays unchanged; structured outputs ship as
provider-native pass-through (strict client-side schema validation explicitly
deferred).

### Open Questions

- [x] **Combined A2+A4, or split?** → **Split; A4 first** (operator, 2026-07-06).
      A2 (structured `Message.content` for vision/documents) is a flight-class
      protocol migration with no in-scope ingestion surface to drive live; A4 is
      request-side, live-verifiable, and continues the A1 thinking work. A2 is the
      following flight. → Design Decision context.
- [x] **Where do the A4 params live — ABC signature or config surface?** →
      **Config surface** (operator, 2026-07-06). See DD1.
- [x] **How deep does structured outputs go?** → **Provider-native pass-through**;
      defer strict client-side schema-validation/repair (operator, 2026-07-06).
      See DD2 + Deferred.
- [ ] **[wire-format gate — resolve in Leg 01, before any provider wiring]** For
      each param, what is the *accepted request format* and the *per-model default*
      on the current target lineup, per **first-party docs**? Specifically:
      Anthropic `output_config.effort` values + `output_config.format` (native
      `json_schema` — confirmed present on the pinned anthropic 0.97.0, so this is a
      per-model-*acceptance* check, not a "does the surface exist" check); OpenAI
      `reasoning_effort` accepted values + `response_format` `json_schema` vs
      `json_object` + which models accept which; Ollama `/v1` `reasoning_effort` /
      `response_format` vs native `think` / `format` (schema), and which the-one's
      two Ollama paths should carry. *(This is the F10-Rec-1 gate; both of F10's
      corrections came from skipping it. Recorded as a flight premise in the log.)*
- [ ] **[Leg 01 doc-gate] Anthropic `output_config.effort` × adaptive-thinking
      composition.** `_build_kwargs` already sets `thinking={type:adaptive,
      display:summarized}` when thinking is active (`anthropic_provider.py:232`);
      `output_config.effort` also governs reasoning. Resolve, per the target lineup,
      whether the two coexist, whether effort supersedes the thinking block, or
      whether the combination 400s — the exact wire-format-interaction class F10
      Rec 1 exists to catch. *(Raised by the F11 design review.)*
- [ ] **Ollama `/v1` vs native surface for each param** — apply on both paths where
      honored, no-op/document where the surface doesn't support it. Resolve with the
      Leg 01 doc-gate.

### Design Decisions

**DD1 — A4 params live in the config surface, not the `LLMProvider` ABC.**
- Choice: `reasoning_effort`, `response_format`, and `stop` are resolved from
  `LLMProviderConfig.config` (config → env → default) via `resolve_*` helpers that
  mirror the established `resolve_extended_thinking` (`anthropic_provider.py:92`)
  and `effective_num_ctx` (`ollama_provider.py:85`) precedents. Each provider reads
  the resolved value in `__init__` into an instance attr and applies it when
  building request kwargs.
- Rationale: keeps the abstract `complete()` / `stream()` signatures stable, so the
  change **does not cascade to the ~13 hand-rolled `LLMProvider` test doubles**
  (none use `**kwargs`) that broke when F10 added `enable_thinking` (46-failure
  cascade; F10 Rec 6 + Rec 7). Reuses an in-repo pattern the operator already
  ratified for `num_ctx` and the thinking toggle.
- Trade-off: config-surface defaults are provider/session-scoped, not per-call.
  For `reasoning_effort` this is the natural home (like `thinking_enabled`). For
  `response_format` a provider-wide default is niche (usually per-call), so this
  flight delivers the *capability* (the layer can be configured to request JSON and
  the wire path is proven) rather than a per-call caller — per-call plumbing is a
  clean future extension when a consumer needs it. Recorded as the intended shape,
  not a limitation to fix here.

**DD2 — Structured outputs ship as provider-native pass-through.**
- Choice: a canonical `response_format` value is mapped to each provider's native
  surface (OpenAI `response_format` `json_schema`/`json_object`; Anthropic's
  structured-output surface per the Leg 01 doc-gate; Ollama `/v1 response_format`
  or native `format`). No client-side validation of the returned JSON this flight.
- Rationale: the mission's capability-completeness bar is "the provider layer wires
  through what the SDK exposes," which native pass-through meets. Strict
  validate-and-repair is a materially larger, separable concern.
- Trade-off: a model that returns malformed/off-schema JSON is not caught or
  re-prompted by the-one this flight (the provider's own strict mode, where it
  exists, is the only guard). Deferral recorded.

**DD3 — Canonical → per-provider mapping (finalized against Leg 01 doc-gate).**
- `stop` → Anthropic `stop_sequences`, OpenAI / Ollama-`/v1` `stop`, Ollama-native
  `options.stop`.
- `reasoning_effort` → Anthropic effort surface (the carved A4 hook at
  `anthropic_provider.py:66,219`), OpenAI `reasoning_effort`, Ollama per doc-gate.
- `response_format` → OpenAI native `response_format`, Anthropic + Ollama per
  doc-gate.
- Exact SDK shapes and per-model acceptance are pinned in Leg 01, not assumed.

**DD4 — Wire-format + per-model-default verification gate (F10 Rec 1).**
- Before any provider request wiring, Leg 01 verifies each param's accepted format
  AND per-model defaults for the current target lineup against first-party docs, and
  records it as a flight premise in the flight log. No param is wired on an assumed
  format. This is the single gate that would have caught both of F10's corrections.

**DD5 — OpenRouter inherits OpenAI's *request methods* free, but not its config
reading; per-route gating deferred to B4.**
- `OpenRouterProvider` overrides neither `complete` nor `stream`
  (`openrouter_provider.py`), so once OpenAI's request-kwargs assembly forwards the
  A4 params they are inherited for free. **But config→attr reading is NOT
  inherited**: `OpenAIProvider.__init__` reads no `config` today (zero hits), and
  `OpenRouterProvider.__init__` (`openrouter_provider.py:85`) deliberately skips
  `super().__init__()` and currently ignores its `config` param (`:90`
  "accepted for factory uniformity; unused"). So A4 must wire the three config-key
  reads into **both** `__init__`s — OpenAI's (new) and OpenRouter's (its own,
  separately) — landing them in Leg 03 alongside the OpenAI request wiring.
- The existing OpenRouter attribute-parity test
  (`tests/test_openrouter_provider.py:271-286`, `vars(parent) − vars(sub)`) forces
  the A4 attrs to *exist* on the subclass (catches an AttributeError-at-request),
  but does **not** assert OpenRouter *reads them from config* — so Leg 03/05 add a
  config→wire assertion for OpenRouter, not attribute-existence alone.
- Per-route capability gating (consulting OpenRouter `supported_parameters` before
  sending `response_format`/reasoning/`stop`) is backlog **B4** (Low) and is **not**
  done here; OpenRouter forwards the params best-effort. Recorded so the boundary
  is intentional.

**DD6 — Admin exposure is minimal and scoped to provider config, not chat UI.**
- To make the primary knob operator-settable for the HAT, a single
  `reasoning_effort` field is added to the Administration provider-config editor
  (the `num_ctx` / thinking-toggle precedent — provider config, not the chat
  surface the mission constraints fence off). `response_format` and `stop` stay
  config/env-settable only this flight (they are less naturally a provider-wide UI
  default). Adjustable at review if the operator wants all three surfaced.

### Prerequisites

- [ ] **Leg 01 doc-gate complete** — accepted request formats + per-model defaults
      recorded as a flight premise before provider wiring begins (DD4).
- [ ] Hermetic tests run against the existing `tests/fixtures/scripted_transport.py`
      canned-transport harness (no live calls in `make test`).
- [ ] **For the HAT leg only**: live Anthropic API key (current Sonnet/Opus), live
      OpenAI API key (a reasoning-capable model), and a local Ollama with a
      reasoning/`think`-capable model. Backend built from the current tree
      (F10 HAT lesson — confirm the running backend's commit before driving).

### Pre-Flight Checklist
- [x] All open questions resolved *(the two remaining are the Leg 01 doc-gate
      deliverable **by design** — DD4; they close in-flight, not pre-flight)*
- [x] Design decisions documented
- [x] Prerequisites verified *(live-key/backend-currency prereqs apply to L07 HAT)*
- [x] Validation approach defined (conformance extension + live HAT)
- [x] Legs defined
- [x] Design-reviewed (Phase 5b: approve-with-changes; changes incorporated)
- [x] Operator sign-off (2026-07-06)

---

## In-Flight

### Technical Approach

Follow the in-repo config-resolver pattern end to end. Leg 01 de-risks the whole
flight: it pins the wire formats against first-party docs and lands the canonical
`resolve_reasoning_effort` / `resolve_response_format` / `resolve_stop` helpers
(precedence config → env → default) with unit tests, touching **no** provider
request path yet. Legs 02–04 then wire each provider's request-kwargs assembly to
the resolved values, at the sites the blast-radius map identified:

- **Anthropic** — the one extracted `_build_kwargs` (`anthropic_provider.py:163`),
  which already carries the deferred-to-A4 effort hook.
- **OpenAI (+OpenRouter free)** — the two inline kwargs sites in `complete`
  (`openai_provider.py:99-106`) and `stream` (`:151-160`); OpenRouter inherits.
- **Ollama** — the `/v1` inline sites (`complete` `:248-256`, `stream` `:338-346`)
  plus the native `_native_body`/`_native_options` path.

- Because config→attr reading is not inherited across the OpenAI→OpenRouter
  subclass, Leg 03 wires the A4 config-key reads into **both** `__init__`s (OpenAI's
  new one and OpenRouter's bespoke one — DD5).

Because the params ride the config surface, the abstract `complete()`/`stream()`
signatures are untouched — no test-double cascade. Leg 05 extends the Flight 4
cross-provider conformance suite (response_format/stop/effort rows + OpenRouter in
the A4 matrix, asserting config→wire); Leg 06 adds the minimal admin field; Leg 07
drives it all against live models.

### Checkpoints
- [ ] Wire-format premise recorded (incl. effort×thinking composition); canonical
      resolvers landed + unit-tested (L01)
- [ ] Each provider forwards all three params in its native shape, fixtured; both
      OpenAI and OpenRouter `__init__` read the A4 config keys (L02–04)
- [ ] Conformance suite green across Anthropic/OpenAI/Ollama/Mock (+OpenRouter A4
      matrix, config→wire asserted) (L05)
- [ ] Admin `reasoning_effort` field round-trips through provider config (L06)
- [ ] Live HAT: effort visibly changes model behavior; JSON mode returns
      well-formed structured output; a stop sequence truncates as expected (L07)

### Adaptation Criteria

**Divert if**:
- The Leg 01 doc-gate reveals a param's surface diverges enough per provider that a
  single canonical shape can't map cleanly (e.g. Anthropic structured output is
  tool-based, not a `response_format` analog) — re-scope that param (carry it or
  narrow to the providers where it maps) rather than force a leaky abstraction.
- Wiring any param requires an ABC signature change after all (contradicting DD1) —
  stop and re-confirm scope with the operator before triggering the test-double
  cascade.

**Acceptable variations**:
- Per-provider no-ops where a surface genuinely doesn't support a param (documented,
  not forced) — e.g. Ollama `/v1` lacking a knob the native path has.
- Reordering L02–04 (providers are independent).

### Legs

> **Note:** Tentative; planned and created one at a time as the flight progresses.

- [x] `wire-format-premise-and-resolvers` — L01: first-party-doc wire-format gate
      (recorded premise) + canonical `resolve_*` helpers (config→env→default) with
      unit tests. No provider request wiring.
- [x] `anthropic-request-params` — L02: wire effort / response_format / stop into
      Anthropic `_build_kwargs`; fixtured conformance via scripted transport.
- [x] `openai-openrouter-request-params` — L03: wire the three params at both OpenAI
      inline sites; confirm OpenRouter inherits (+ a smoke); fixtured tests.
- [x] `ollama-request-params` — L04: wire the three params across the `/v1` and
      native Ollama paths; document un-honorable combos; fixtured tests.
- [x] `conformance-matrix-extension` — L05: extend the F4 cross-provider conformance
      suite (response_format/stop/effort rows; add OpenRouter to the A4 matrix,
      asserting config→wire, not attribute-existence alone). Test-only, hermetic.
- [x] `admin-reasoning-effort-field` — L06: add the minimal Administration
      provider-config `reasoning_effort` field (num_ctx / thinking-toggle precedent)
      with a config round-trip. Split from L05 (UI surface, different verification);
      droppable to config/env-only if the operator prefers (DD6).
- [ ] `hat-and-alignment` *(optional)* — L07: guided HAT driving effort + structured
      outputs + stop against live Anthropic/OpenAI/Ollama; fix wire-format/default
      surprises inline (F10 pattern); refresh/author a behavior-test spec if warranted.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (full suite + extended conformance matrix)
- [ ] `the_one/agents.md` updated with the A4 config-key conventions
      (`reasoning_effort` / `response_format` / `stop` resolution + precedence)
- [ ] Mission criterion #3 checkbox advanced (A4 implemented; strict-validation
      deferral recorded)

### Verification

- **Hermetic**: the extended cross-provider conformance suite
  (`tests/test_llm_provider_cross_provider_conformance.py`) asserts each param
  reaches each provider's request in the correct native shape via the scripted
  transport; per-provider fixtured tests cover the mapping and the config→env→default
  precedence.
- **Live (HAT, L06)**: with `reasoning_effort` set high vs low on a reasoning model,
  observe the behavioral/latency/usage difference; with a JSON `response_format` set,
  observe well-formed structured output; with a `stop` sequence set, observe
  generation truncates at it. Backend confirmed built from the current tree first
  (F10 lesson).

### Out of Scope (this flight)
- **A2** — structured `Message.content` for vision/documents (following flight).
- **Strict client-side structured-output validation / repair** (DD2 deferral).
- **OpenRouter per-route `supported_parameters` gating** (backlog B4).
- **Per-call (vs config-default) plumbing** of response_format/stop through the agent
  loop — future extension when a consumer needs it.
- The two F10 "before mission close" cleanups (live thinking-broadcast `visibility`
  at `app.py:1581`; empty-thinking-text tests) — thinking-layer, not A4; close them
  at mission-debrief or a dedicated cleanup, not here.
