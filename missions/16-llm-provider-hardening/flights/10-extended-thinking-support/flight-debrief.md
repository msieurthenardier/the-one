# Flight Debrief: Extended-Thinking / Reasoning Support (A1)

**Date**: 2026-07-03
**Flight**: [Extended-Thinking / Reasoning Support (A1)](flight.md)
**Status**: landed
**Duration**: 2026-07-02 – 2026-07-03
**Legs Completed**: 7 of 7 (01–06 autonomous + 07 guided HAT)

## Outcome Assessment

### Objectives Achieved

Delivered backlog item **A1** complete: the `Message` protocol carries a first-class structured
`thinking` field (`ThinkingBlock` list), and extended thinking is wired end-to-end on Anthropic —
adaptive enablement → capture signed blocks → replay them (signatures intact, before `tool_use`,
gated on the request's thinking state) → persist through the codec → surface in the web chat as a
collapsed disclosure. Verified live on `claude-sonnet-5` by the `extended-thinking-tool-turn`
behavior test (**PASS 6/6**, incl. multi-turn replay stability), plus a hermetic unit + browser
suite. Enablement, capture, and replay are Anthropic-only this flight; the protocol/codec/UI are
provider-agnostic (DD5).

### Mission Criteria Advanced

- **✓ Criterion #1** (thinking+tool turn + follow-up complete, no API error; signatures preserved
  + replayed) — MET, live-confirmed on Sonnet 5.
- **✓ Criterion #2** (`Message` carries reasoning as a first-class field; round-trips persistence;
  available to the web UI) — MET (codec round-trip unit-tested + disclosure renders/survives reload
  with text matching persistence).
- **(advances)** the capability-completeness criterion — A1 implemented; OpenAI/Ollama reasoning +
  live thinking-delta streaming + the `effort` knob (A4) explicitly deferred.

## What Went Well

- **The per-leg design-review gate caught the flight-breaking wire-format issue before build-out.**
  Leg 03's design review independently verified against Anthropic's docs that `budget_tokens`
  400s on Sonnet 4.6+ — while Leg 02's budget enablement was still uncommitted. The flight would
  otherwise have shipped enablement that 400s on the project's own default model.
- **The batch-commit workflow made the pivot cheap.** Because all six autonomous legs commit in a
  single Phase 2d batch, the `budget_tokens → adaptive` pivot cost ~one extra leg of rework with
  **zero history churn and zero dead code** (Leg 02's budget scaffolding was never committed; the
  final tree has no commented-out budget logic).
- **The live HAT earned its place — it found two defects fixtured tests structurally cannot.** A
  stale dev backend (new static JS, 14h-old Python) and Sonnet 5's `display:"omitted"` default
  (signed-but-empty thinking → empty disclosure). Both were fixed inline; the "turn completes = no
  400" witness held throughout.
- **The Witnessed behavior-test pattern was trustworthy.** Every browser-frame PASS paired a DOM
  witness with a server-log grep for 400/signature/exception (closing the swallowed-400 silent
  failure), and cited a rendered-state a11y snapshot. Step 6 matched the reloaded disclosure text
  against the persisted DB block byte-for-byte.
- **DD1, DD2, DD8 held exactly** (structured thinking list + truthy codec guard with the tripwire
  green unchanged; capture-from-final-message reveal-after; strip-when-off replay gating). The
  `enable_thinking` contract extension is clean (necessary for the generic-provider classifier
  suppression; not a leak).
- **Metrics clean**: 3675 passed / 10 skipped / **1 known pre-existing flake** (aiosqlite teardown,
  isolation-clean), +66 net passing — second-highest single-flight gain in M16. Skips stable at 10;
  no new flakes.

## What Could Be Improved

### Process

- **Wire-format was validated at the SDK type-shape level, not the live model-support level.** The
  F1B recon + Phase-5b review correctly validated the SDK *response* shape (`ThinkingBlock`) for
  DD1, but never validated the *request* wire format (the `thinking` param value) against the model
  support matrix. Both the `budget_tokens` 400 and the `display:"omitted"` empty-text default share
  this one root cause: request-parameter formats/defaults were assumed, not read from first-party
  docs. (Architect + Developer converged on this independently; FD concurs.)
- **The stale-backend HAT trap** nearly produced a false "it works" reading — the reachable app is
  not necessarily the current backend. The behavior-test/HAT preconditions check reachability but
  not backend currency.
- **Base-contract change blast-radius under-scoped.** Adding `enable_thinking` + forwarding it
  through `base.stream`'s default cascaded a `TypeError` to **9** default-stream test doubles across
  **6** files; Leg 02 (via its design review) named only **4** in one file → a 46-failure cascade
  during implementation.
- **A key verification deliverable was a review catch, not a plan output.** Leg 05's MockProvider
  thinking seam + Playwright disclosure test (the thing that would have caught the frontend if the
  disclosure had been code-broken) was added by the design reviewer as a [high] finding, not
  specced up front.

### Technical

- **DD3 "above the answer" ≠ implementation.** Thinking renders *after* assistant content in stream
  order (both live and replay) — so on turns with both answer text and thinking, the disclosure
  sits below the answer, and on empty-content thinking+tool turns it "floats" above the tool trace.
  Reconciled by review as HAT-tunable and operator-accepted, but the DD3 wording now conflicts with
  what shipped.
- **Live thinking broadcast omits `visibility`** (`app.py:1581`) while the replay projection spreads
  it. For an operator-only assistant turn, the live disclosure isn't visibility-gated (the replayed
  one is). Small (one-line) but technically incorrect — worth fixing before the mission closes.
- **The `display:"omitted"` / empty-thinking-text path is not hermetically tested.** Capture tests
  always stub non-empty `thinking` text, so no unit test exercises `thinking=""` round-trip or
  asserts "no disclosure event fires when thinking text is empty" — the exact case the HAT found
  live. The **MockProvider seam always produces non-empty text**, which is what masked the
  `display:omitted` case (the browser test passed because its fixture had text).
- **`thinking_display_text` filters on `type == "thinking"` — a latent A2 risk.** A future Ollama
  adapter using its native `type="think"` (or OpenAI `type="reasoning"`) would get empty display
  text from this helper even with real reasoning present. This will surface the moment a second
  provider populates `Message.thinking`.
- **Minor DRY**: `_thinking_block_to_dict` (codec) and `_thinking_block_to_api` (Anthropic) produce
  the same shape from the same `ThinkingBlock` in two places (kept separate by concern for now; may
  converge as more providers adopt thinking).

### Documentation

- The `message-thinking-field` convention was added to `the_one/agents.md` (thinking field +
  adaptive enablement + `display:"summarized"` + DD8 gating). Good.
- **DD3's spec text should be updated** to "after the answer, in stream order" to match what
  shipped (or a follow-on UX leg files the move-thinking-above work).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `budget_tokens` → **adaptive-only** enablement (DD4/DD6 superseded; 6→7 legs) | Anthropic 400s `budget_tokens` on Sonnet 4.6+/current models; verified vs docs at Leg 03 review | **Yes** — add a pre-flight "verify request wire format + per-model defaults vs the model matrix" gate |
| `{"type":"adaptive"}` → `{"type":"adaptive","display":"summarized"}` (HAT inline fix) | `display` defaults to `"omitted"` on Sonnet 5/Opus 4.8 (signed-but-empty thinking) → empty disclosure; found live | **Yes** — same wire-format gate covers per-parameter defaults, not just the top-level format |
| Leg 02 `enable_thinking` blast radius: 9 test doubles / 6 files (leg named 4/1) | `base.stream` default forwards the new kwarg to `self.complete()`; every default-stream double must accept it | **Yes** — grep ALL `class .*\(LLMProvider\)` (prod + tests) before a base-contract signature change |
| Leg 06 checkbox-blind dirty machinery (`getFormSnapshot`/revert `.value`-only) | The `num_ctx` template is a number input; a checkbox needs `.checked`-aware snapshot/revert | Note — flag value-vs-checked divergence when adapting an input-field template to a checkbox |
| Stale `:8485` dev backend (new JS, old Python) served during HAT | Long-lived dev process + no `--reload`; static assets reload on browser refresh and mask stale Python | **Yes** — HAT precondition: confirm the backend is built from the current tree |

## Key Learnings

1. **The recurring theme is "SDK type-shape ≠ live API wire-format/behavior."** Validating the
   response data-model (which the F1B audit did well) is necessary but not sufficient; the request
   parameter format and per-model defaults are a separate surface that must be read from first-party
   docs against the actual target-model lineup. This one gap produced both of the flight's biggest
   corrections.
2. **A live HAT is not redundant with a green hermetic suite for provider-capability work** — it is
   the only thing that catches (a) environment staleness and (b) real-model behavioral defaults that
   the test author didn't know to fixture. Fixtured/mock tests can only cover behaviors the author
   already knows about; the HAT surfaces the unknowns.
3. **The per-leg design-review + batch-commit combination is what made a mid-flight pivot survivable
   cheaply.** Catching the wire-format issue at review (before commit) and holding all autonomous
   commits to one Phase-2d batch meant the pivot was working-tree rework, not history surgery.
4. **Test-metric health**: the flight added +66 passing tests with no new flakes; the lone aiosqlite
   teardown flake remains stable and isolation-clean — carry it forward as the known M16 flake, still
   a candidate for a dedicated fix.

## Recommendations

1. **[Critical] Add a "request wire-format + per-model-defaults verification" gate to capability-flight
   pre-flight planning.** For any leg touching a provider-specific API request parameter (thinking,
   cache_control, response_format, effort…), require a first-party-doc citation confirming the
   accepted format AND the per-model defaults for the *target model lineup*, recorded as a flight
   premise. This single gate would have caught both this flight's corrections at planning.
2. **[Important] Standardize a HAT/behavior-test precondition: "the running backend is built from the
   current working tree,"** not just "reachable." For the-one specifically, add a **startup log line
   printing the git commit / build id** (cheap, works regardless of launch method) so the check is
   one line; `--reload` in dev is the heavier alternative. *(Methodology-level; benefits every
   project's HAT.)*
3. **[Important, small — do before mission close] Fix the live thinking-broadcast `visibility` gap**
   at `app.py:1581` (spread `visibility` like the codec/other events do) so operator-only thinking
   disclosures are gated live, not only on replay. Add a test covering the live path.
4. **[Important] Close the empty-thinking-text test gap.** Add hermetic tests: (a) `test_db_codec.py`
   — `ThinkingBlock(type="thinking", thinking="")` encode/decode round-trip; (b)
   `test_anthropic_provider.py` — a `block.thinking=""` capture stub; (c) assert `thinking_display_text`
   returns `""` and **no** `thinking` WS event fires for it. **Author a `thinking-empty-display`
   behavior-test spec** (runnable hermetically via a `thinking:""` MockProvider fixture) asserting the
   disclosure does NOT render — complements the happy-path spec and pins the exact HAT-found case.
5. **[Important — carry into A2] `thinking_display_text` type-filter will break for a second
   provider.** Before the OpenAI/Ollama-reasoning flight (A2) populates `Message.thinking`, decide:
   canonicalize `ThinkingBlock.type` at capture time, or broaden `thinking_display_text` to recognize
   provider-neutral reasoning types. Flag it in the A2 spec.
6. **[Design — for A4] Put `effort` (and `display`) in the provider config surface, not the
   `LLMProvider` ABC.** Keep the ABC signature stable at `enable_thinking: bool | None = None` (the
   suppression *signal*); resolve tuning parameters (`effort`, `display`) via the config dict +
   `resolve_extended_thinking` (returning a small config object). Prevents ABC signature accretion of
   Anthropic-specific concerns.
7. **[Standing checklist] Enumerate ALL `LLMProvider` subclasses (prod + test doubles) before any
   base-contract signature change** — `grep -rn "class .*\(LLMProvider\)\|def complete\|def stream"
   the_one/ tests/`. One grep at design time prevents a mid-flight cascade.
8. **[Minor] DD3 discrepancy**: update the flight/DD3 wording to "thinking renders after the answer in
   stream order" (document reality), or scope a small follow-on UX leg to move the disclosure above
   the answer. Note vision/`Message.content` widening is a **flight-class** protocol migration (relaxes
   the `__post_init__` str-assert; touches every provider + the codec) — plan it as a dedicated leg,
   not a capability addendum.

## Action Items

- [ ] **(before mission close)** Fix the live thinking-broadcast `visibility` omission (`app.py:1581`)
      + add a live-path visibility test. *(Rec 3 — small.)*
- [ ] **(before mission close)** Add the empty-thinking-text hermetic tests (codec round-trip +
      capture stub + "no event fires"). *(Rec 4.)*
- [ ] Author a `thinking-empty-display` behavior-test spec (hermetic, MockProvider `thinking:""`
      fixture → asserts no `.thinking-disclosure`). *(Rec 4.)*
- [ ] Reconcile DD3 wording vs the interleaved/after-answer implementation (doc update, or a follow-on
      UX leg). *(Rec 8.)*
- [ ] **Carry to `/mission-debrief`:** (a) adopt the "request wire-format + per-model-defaults"
      pre-flight gate for the remaining A-series capability flights (Rec 1); (b) the HAT
      backend-currency precondition + startup version-log (Rec 2); (c) the `enable_thinking`-on-ABC
      pattern + the A4 "config-not-ABC" guidance (Rec 6); (d) the `thinking_display_text` type-filter
      A2 risk (Rec 5); (e) the still-open aiosqlite teardown flake.
- [ ] Consider deduping `_thinking_block_to_dict` / `_thinking_block_to_api` if/when a second provider
      adopts thinking. *(Rec — low priority.)*
