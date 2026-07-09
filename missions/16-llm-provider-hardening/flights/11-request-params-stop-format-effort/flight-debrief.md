# Flight Debrief: Request-Param Capabilities — reasoning_effort, structured outputs, stop (A4)

**Date**: 2026-07-08
**Flight**: [Request-Param Capabilities (A4)](flight.md)
**Status**: landed
**Duration**: 2026-07-06 (planning) → 2026-07-08 (landed, incl. live HAT)
**Legs Completed**: 7 of 7 (L07 HAT Anthropic-only; OpenAI/Ollama live-verification deferred)

## Outcome Assessment

### Objectives Achieved

Delivered backlog **A4** — three request-side capabilities the official SDKs expose
but the-one did not wire through: **reasoning_effort**, **structured outputs / JSON
mode**, and **stop sequences** — through the provider **config surface**
(config → env → default), each mapped to every provider's native SDK shape and
exercised by an extended cross-provider conformance matrix plus a live HAT. The
`LLMProvider` ABC signature is unchanged (DD1), so nothing cascaded to the ~13
hand-rolled test doubles. All four request-capable providers (Anthropic, OpenAI,
OpenRouter, Ollama `/v1`+native) carry the params in their correct native shapes,
asserted config→wire.

### Mission Criteria Advanced

- **Criterion #3** (each prioritized capability gap implemented-or-deferred):
  **advanced** — A4 implemented; strict client-side structured-output validation
  explicitly deferred (DD2, recorded). Does not *close* #3: **A2** (vision/document
  `Message.content`) remains a following flight, and **A3/A5/B1–B4** get an explicit
  deferral sweep at mission close.
- Constraint (no agent framework; ABC + provider-shape-portability preserved):
  **held** — DD1's config surface kept the ABC stable.

## What Went Well

- **DD1 (config surface, not the ABC) was the flight's strongest decision** and the
  direct payoff of F10's lesson. Both debrief agents independently rated it the
  best call: zero test-double cascade (vs F10's 46-failure `enable_thinking`
  cascade). The resolver/coercer split (`_request_params.py`: coerce config in
  `__init__`, coerce env at call time) mirrors `resolve_extended_thinking` /
  `effective_num_ctx` exactly, applied consistently across all four providers with
  no drift.
- **The Leg-01 doc-gate (DD4) paid off measurably**: pinning wire formats against
  pinned-SDK stubs + first-party docs *before* any wiring produced **zero
  post-doc-gate mapping corrections** across L02–L04 — the precise failure mode
  (two mid-flight corrections) that motivated DD4 after F10. It also correctly
  classified Anthropic's `json_schema`-only structured-output surface as an
  "acceptable variation / no-op," not a divert.
- **The Phase-2d batch review caught a blocking bug no per-leg test could have**:
  the config-wipe on Studio provider save (a UI Save replaced `config` wholesale,
  silently wiping config/env-only `response_format`/`stop`). The *trigger* only
  existed because two legs' changes combined (L06 made openai/openai-compatible
  start sending `config`, exposing a latent replace-not-merge backend semantic).
  This is a concrete argument *for* the batch-review-before-commit model.
- **Per-leg design reviews surfaced real, specific pre-implementation issues**:
  DD5's OpenRouter config-reading trap (wired into L03, not assumed); L05's Ollama
  `/api/show` capture-pollution ([high] — would have false-passed); L02's
  temperature-retry-preserves-A4-kwargs edge case. Acceptance criteria were
  concrete and verifiable (specific counts, `git diff --stat` scoping, grep checks)
  — not vague.
- **Live HAT confirmed the wiring end-to-end on Anthropic (6/6)**, including the
  save-preserves-config fix (S3) — the one behavior with no automated coverage.

## What Could Be Improved

### Process
- **Under-resourced HAT left 2 of 3 providers live-unverified.** L07 ran
  Anthropic-only (no live OpenAI reasoning key / local Ollama this session). The
  two L04 Ollama HAT-confirm items (`/v1` effort→`think` translation granularity;
  `/v1` json_schema-wrapper acceptance) **remain open**. The "no wire-format
  surprises" result is proven for 2 of 3 target providers. Honest scope gap
  (recorded, not silently dropped) — but a live OpenAI+Ollama HAT should close it
  before the mission fully closes.
- **"Code merged" gate is still open** — PR #150 is up but draft/unmerged at
  debrief time. The flight is `landed`, not merged; treat merge as an outstanding
  gate before mission-close counts this flight fully done.

### Technical
- **No automated regression net for the save-preserves-config property.** The fix
  has only a *source-scan* guard (`test_admin_reasoning_effort_field.py::
  test_provider_editor_seeds_config_from_existing_provider_before_field_blocks`) —
  it checks the shape of the fix, not runtime behavior. The behavioral property was
  verified exactly once (L07 S3) then the config was reset. A future JS change
  could reintroduce the wipe and `make test-unit` would not catch it. **This is the
  flight's clearest behavior-test candidate** (see Recommendations).
- **DD2's deferral is real and now live-confirmed, not hypothetical.** The HAT's
  `additionalProperties:false` 400 is the DD2 trade-off manifesting: the-one
  forwards the caller's schema as-is; the provider's strict mode is the only guard.
  Correct per spec; carry an *opt-in* schema normalizer as a backlog convenience,
  not urgent debt.
- **Deliberate OpenAI-compat mapping duplication** (`openai_provider.py:
  _a4_request_kwargs` ≡ `ollama_provider.py:_v1_a4_kwargs`, ~17 lines) is
  well-managed debt: forward-note names the lift target
  (`_request_params.py::to_openai_compat_a4`) + trigger (3rd `/v1`-style provider),
  and L05's conformance matrix asserts the two emit byte-identical shapes (real
  drift net). Both agents agree: **do not refactor pre-emptively** — lift at
  rule-of-three.
- **The config-editor save bug class is structural.** UI-partial-config ×
  backend-replace-semantics (`model_copy(update=data)`) will re-trigger for *any*
  future provider-config field unless the seed-before-overlay pattern
  (`provider-editor.js:601-611`, `Object.assign({}, provider.config)` before field
  blocks) becomes a *checked convention*, not tribal knowledge re-derived per leg.

### Documentation
- The `_v1_a4_kwargs`/`_a4_request_kwargs` rule-of-three forward-note lives only in
  a code comment, not in `agents.md`'s A4 convention — a future 3rd-provider flight
  would have to find the comment rather than the canonical doc.
- The seed-before-overlay save pattern isn't a named convention in `agents.md`.

### Test Metrics
Fresh `make test` at HEAD (`6066830`): **3896 passed, 10 skipped, 655 deselected,
0 failed**, wall-clock **339.03s**. Corroborates the in-flight gates (L05 3891 →
Phase-2d 3895 → 3896; +1 within environment noise, no test files changed since
Phase-2d). Wall-clock sits inside the historical **296–346s** band (F02–F08) — no
timing regression despite Mission 17 + F11 both adding volume. **Caveat**: Mission
17 (UI redesign) landed between F10 and F11, so the raw F10→F11 jump (3675 → 3896,
+221) is *not* F11's; F11's own contribution is the ~117 A4-specific tests
(41 resolvers + 13 Anthropic + 25 OpenAI/OpenRouter + 25 Ollama + 8 conformance +
5 admin). The known aiosqlite-teardown `RuntimeError: Event loop is closed`
thread-warning (carried from F10, "isolation-clean") appeared twice as a
non-blocking `PytestUnhandledThreadExceptionWarning` — stable disposition, not a
failure. `deselected` grew 594–596 → 655 (Mission 17's browser/pixel growth, not
F11).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L07 HAT scoped down to Anthropic-only mid-session | No live OpenAI reasoning key / local Ollama available | No — record carry-forward items; run full HAT when creds available |
| Config-wipe fix added to the shared save path (all provider types) beyond L06's stated scope | Phase-2d review found a blocking data-loss bug L06's change triggered | Yes — the seed-before-overlay pattern should become a named convention |
| L05 grew from "add conformance rows" to a harness extension (config threading + per-provider capture + `/api/show` path-filter) | The existing harness didn't capture request bodies uniformly | No (one-off), but budget "harness archaeology" when reusing the conformance suite |

## Key Learnings

- **Front-loading wire-format risk works.** DD4's doc-gate converted F10's
  "correct-it-mid-flight" pattern into "zero corrections." Keep the doc-gate-first
  leg for any provider-wiring flight.
- **Cross-cutting invariants that span a UI leg and a backend semantic need an
  explicit batch-review checklist item** — per-leg "tests passing" gave false
  confidence on save-preserves-config until the batch stage caught it. The batch
  model earned its keep here.
- **The provider-config store has reached its scaling limit.** A4 added a *third*
  tuning knob (`reasoning_effort`, after `num_ctx`/`thinking_enabled`) to
  `LLMProviderConfig.config`, which models a *provider connection*, not a *usage
  policy*. The operator's HAT-time direction (move tuning to the **agent** level)
  is architecturally right and should gate future additions: the next provider-
  tuning field proposed before that migration warrants "is this a 4th field in the
  wrong home?" scrutiny.

## Recommendations

1. **Author a `/behavior-test` spec for save-preserves-config now** (highest-value,
   both agents concur). Steps: open Admin → set `response_format`+`stop` on a
   provider via API → edit `reasoning_effort` via the UI editor → Save → re-fetch →
   assert all keys survive. Converts L07's one-time S3 into a repeatable regression
   net for a property that already broke once this flight and has zero runtime-
   behavior coverage. Author it inline in the next planning conversation (per
   AUTHORING.md).
2. **Promote two patterns into `agents.md` conventions**: (a) the seed-existing-
   config-before-overlay save pattern (`provider-editor.js:601-611`) as a checked
   convention for any future provider-config editor field; (b) a one-line
   forward-note pointer in the A4 convention to the `_v1_a4_kwargs` rule-of-three
   lift target, so a future 3rd-provider flight finds it in the canonical doc.
3. **Run a full OpenAI + Ollama live HAT before mission close** to clear the two
   open Ollama HAT-confirm items and give the "no wire-format surprises" result all
   3 providers. Not blocking this flight; a mission-close prerequisite.
4. **Agent-level config surface = next-ish future mission** (operator: "works today
   but incomplete placement"). Flight-class work (new agent-level config store +
   agent-over-provider resolution order), not a side-effect of a future A-item
   flight. Tracked in mission Known Issues; scope it explicitly after Mission 16
   closes.
5. **No urgent action on**: DD2 schema validation (deliberate, live-confirmed —
   opt-in `additionalProperties:false` normalizer is a backlog convenience, bundle
   with A2 which also touches the structured-output surface); B4 per-route gating
   (cleanly deferred, `_read_a4_config`/`_a4_request_kwargs` are clean insertion
   points); the `_v1`/OpenAI duplication (lift at rule-of-three, not before).

## Action Items

- [ ] **Author `/behavior-test save-preserves-config` spec** — inline in the next
      planning conversation (Rec 1).
- [ ] **`agents.md`: add the seed-before-overlay save convention + the A4
      duplication forward-note pointer** (Rec 2). *(Doc-only; can ride the next
      flight touching this area.)*
- [ ] **Full OpenAI + Ollama live HAT** — mission-close prerequisite; clears the 2
      open Ollama HAT-confirm items (Rec 3).
- [ ] **Mark PR #150 ready / merge** — outstanding "Code merged" gate (operator
      decision).
- [ ] *(Mission-level, tracked in Known Issues)* Scope the **agent-level config
      surface** future mission — next-ish (Rec 4).
- [ ] *(Backlog, operator-assessed acceptable)* session-agent config
      live-propagation (config-change → session refresh) — recorded caveat, low
      priority; not scheduled.
