# Mission Debrief: LLM Provider Layer Hardening & Capability Completeness

**Date**: 2026-07-10
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](mission.md)
**Status**: completed
**Duration**: 2026-06-17 (recon spike) → 2026-07-10 (close)
**Flights Completed**: 13 (F01 recon, F1B audit, F02–F12) — all landed/completed, none aborted

## Outcome Assessment

### Success Criteria Results

| # | Criterion | Status | Notes |
|---|-----------|--------|-------|
| 1 | Anthropic tool `input_schema` with top-level `oneOf/allOf/anyOf` (or no top-level `type`) no longer fails the whole turn; unsanitizable schemas name the offending tool | **Met** | F02; pure sanitizer + `BadRequestError → tool-name`, live-verified vs first-party Anthropic. *Residual*: the OpenRouter→Anthropic route sanitizes the common case but lacks drop-and-proceed parity (recorded Known Issue). |
| 2 | Per-SDK capability audit exists → prioritized gap backlog | **Met** | F1B; backlog A1–A5 / B1–B4 operator-ratified. |
| 3 | Each prioritized capability gap implemented **or** explicitly deferred with a recorded reason | **Met** | A1 (F10), A2 (F12), A4 (F11) implemented. A3/A5/B1–B4 explicitly deferred with recorded rationale — see **Deferred Capabilities** below. |
| 4 | Thinking + tool call in one Anthropic turn completes; follow-up turn also succeeds | **Met** | F10; live behavior test 6/6 on Sonnet 5, incl. multi-turn replay stability. |
| 5 | `Message` carries reasoning as a first-class field, round-trips through persistence, available to UI | **Met** | F10; `Message.thinking` (`list[ThinkingBlock]`) + codec round-trip + collapsed web-UI disclosure surviving reopen. |
| 6 | Gemma via Ollama reliably executes tool calls, incl. text-form calls | **Rescoped — not met by design** | F03 L08C, operator-ratified. gemma3:4b (4B) can't reliably complete multi-step tool discovery; always-on catalog injection over-routed and broke chat. Non-tool-capable models are **conversational-only**; models advertising `tools` still use the structured path. Operator confirms satisfied with the rescope. |
| 7 | Cross-provider tool-use conformance test exists and passes | **Met** | F04; later extended by F11 (A4 config→wire matrix) and F12 (A2 image-projection matrix with an explicit OpenAI ≡ OpenRouter ≡ Ollama-`/v1` parity assertion). |
| 8 | Context-window limits for OpenAI + Anthropic sourced without a hand-maintained drifting table | **Met** | F05; `context_window_for()` resolves cache→seed→default off a bundled models.dev seed + daily refresh. OpenAI prefix table deleted (`ImportError`-confirmed); Anthropic `200_000` constant replaced. *Footnotes*: a residual `_OPENAI_FLOOR` no-regression floor (acknowledged, not primary truth); a shipped **Windows-packaging** bug — the seed JSON isn't collected into the frozen build → silent fallback to class defaults (recorded Known Issue). |
| 9 | No agent framework added; `LLMProvider` contract + provider-shape-portability convention preserved | **Met** | Held across all three contract-touching capability flights. ABC grew exactly one keyword-only param (`enable_thinking`); F11 routed all of A4 through the **config surface** (no ABC change → no test-double cascade); the `str`-identical `Message.content` fast path is preserved (list content only when an image is actually attached). |

**Score**: 8 of 9 criteria met; #6 deliberately rescoped with operator ratification (an explicit scope decision, not a failure).

### Overall Outcome

**The mission achieved its outcome, and the outcome was still the right goal at the end.** It began as a two-bug fix (#122 Anthropic tool-schema, #105 Gemma tool-use) and was broadened on day one into *capability completeness* bounded by an evidence-driven per-SDK audit. Both original bugs were resolved (#122 fixed and live-verified; #105's recovery kernel shipped, then the harder "should non-tool models attempt tools" question was trialled, found unreliable for 4B models, and resolved as a deliberate chat-only scope). The audit's operator-prioritized capabilities — **extended thinking (A1), request params (A4), vision (A2)** — all landed behind the `LLMProvider` contract; the remaining lower-tier items are explicitly deferred with recorded reasons.

The strategic bet the mission was built to defend — **stay hand-rolled over the official SDKs, no framework** — was stress-tested three separate times by contract-touching capability flights and held every time. The architecture came out *more* disciplined than it went in (the config-surface-not-ABC choice in F11, the `raise`-not-`assert` and `isinstance`-not-`type`-string conventions in F12 were each a direct correction of the prior flight's lesson).

The operator's own framing of the value delivered: *"a lot of learning during the mission; completeness of the chat interface is a good outcome."* The mission also absorbed a run of field-driven robustness flights (F05–F09) that weren't in the original two-bug plan but emerged from real use — catalog drift removal, telemetry persistence, chat-loop hang/cancel/queue, resource governance, and a hands-on provider chat sweep. That broadening was healthy: the mission fixed the class of problem, not just the two reported instances.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F01 — Recon & root-cause spike | landed | Falsified hole #1 (extended-thinking replay); confirmed #122 (live repro) + #105; settled build-vs-adopt → **hand-roll** (any-llm rejected). |
| F1B — Provider capability audit | landed | Per-SDK exposed-vs-wired matrix → ratified backlog A1–A5 / B1–B4. |
| F02 — Anthropic tool `input_schema` (#122) | completed | Pure schema sanitizer + name-the-offending-tool; live-verified; gated onto OpenRouter→Anthropic. |
| F03 — Open-model tool-use (#105) | completed | Text-form recovery kernel (fenced/​Hermes/​bare-JSON); L08C rescope → non-tool models chat-only. |
| F04 — Cross-provider conformance | completed | Provider-parametrized request→tool_call→result→final round-trip; the standing regression net. |
| F05 — Model-catalog drift removal | completed | Runtime models.dev catalog (seed + daily cache); killed the OpenAI prefix table + Anthropic constant. **Satisfies criterion #8.** |
| F06 — Telemetry usage persistence | completed | `session_metadata["last_usage"]` restore on rejoin; survives server restart. |
| F07 — Chat-loop robustness & control | completed | Streamed web tools + byte cap + deadline; per-tool timeout; cancel; one queued send. Fixed a live infinite-stream hang. |
| F08 — Agent-loop resource governance | completed | Central context-budget governor at `_execute_tool`; configurable search-backend registry + honest-empty; a11y overlay. |
| F09 — Provider chat HAT | completed | 8 field findings across 6 legs (0.2.10→0.2.15); tool-search truncation, queue UX, editable Ollama `num_ctx`, cache-busting, MCP-disable bug. |
| F10 — Extended thinking (A1) | completed | `Message.thinking` + adaptive Anthropic enable/​capture/​replay + UI disclosure; live behavior test 6/6. |
| F11 — Request params (A4) | completed | `reasoning_effort` / structured-output / stop via the config surface (no ABC change); extended conformance matrix; live HAT. |
| F12 — Multimodal `Message.content` (A2) | completed | `str \| list[ContentBlock]` with `TextContent`/`ImageContent`; per-provider image mapping; live Anthropic vision HAT; two latent WS/title bugs fixed. |

## What Went Well

- **The core strategic bet held under repeated stress.** Three capability flights (F10/F11/F12) reached into the `LLMProvider` contract and the `Message` protocol without breaking the "hand-rolled over official SDKs" architecture. The ABC still has its original five methods plus one keyword-only param. This is the mission's headline validation: the operator's pain was correctly diagnosed as *specific holes*, not an architectural problem, and hardening (not adopting a framework) was the right prescription.
- **Each flight learned from the last, mechanically.** F10's 46-failure `enable_thinking` test-double cascade → F11 deliberately chose the config surface over an ABC change (zero cascade). F11's wire-format corrections → F11/F12 both front-loaded a Leg-01 doc-gate (pinning wire shapes from SDK stubs + docs) that produced *zero* mid-flight mapping corrections. F12's own `Message` role-guard fix → the same flight used `raise` not bare `assert` and `isinstance` not `type`-string dispatch. The debrief loop demonstrably fed forward.
- **The batch-review-before-commit model earned its keep.** F11's Phase-2d batch review caught a blocking config-wipe data-loss bug that *no per-leg test could have surfaced* — the trigger only existed once two legs' changes combined. Concrete evidence for the single-review-after-last-leg orchestration.
- **Behavior tests / live HATs proved the things hermetic tests structurally cannot.** F10's thinking round-trip (6/6 on live Sonnet 5), F08's governance sweep (9/9), and F12's live vision HAT each verified real-environment behavior — and each HAT "found a little something" (the operator's expectation of them), from wire-format surprises to the attach-UX iteration to a live `FileList`-collapse bug.
- **The mission broadened well under field pressure.** F05–F09 weren't in the original two-bug plan; they came from real use and were absorbed as first-class flights rather than scope-creep afterthoughts. The result is a provider layer that's robust in practice, not just correct on the two reported bugs.

## What Could Be Improved

### Process
- **Live HAT coverage was Anthropic-only for the request-side capabilities.** A4 (F11) and A2 (F12) HATs both ran Anthropic-only — no live OpenAI-reasoning key or local Ollama this cycle. F11 named a full OpenAI + Ollama HAT a "mission-close prerequisite" (two Ollama `/v1` items — effort→`think` translation granularity, json_schema-wrapper acceptance — remain live-unconfirmed). **Operator decision at close: accept the gap and close the mission** — hermetic conformance covers the wire *shapes* cross-provider; the gap is live per-model *acceptance* on OpenAI/Ollama, to be cleared when those creds/environment are available. Recorded as an accepted carry-forward, not a silent drop.
- **"Capability-then-producer-later" (F12) left two latent bugs dormant in `main` ~36h** (a `json.dumps` WS crash + a session-title corruption, live the instant `content` could legally be a list). Correctly tracked as an L02 expiry and fixed when L08 built the producer; the operator assessed the pattern acceptable. The cheap net (recorded, optional): a producer-independent smoke that pushes a synthetic list-content `Message` through the read path at capability-land time.

### Technical
- **Debt inventory carried into `main`** (priority-ordered; all recorded as action items):
  1. `ImageContent.__post_init__` uses a bare `assert` (`llm/base.py`) — the exact `-O`-strippable pattern the *same flight* fixed on `Message`'s role guard three lines away. Two-line fix, unshipped.
  2. Live thinking-broadcast omits `visibility` (`interfaces/web/app.py`) while the replay projection includes it — an F10 "(before mission close)" action item that was never done. One-line fix + test.
  3. The Leg-09 redundant-tool-call backstop (`agent/core.py`) is now **verified dead code** on the chat-only degraded path (post-08C, `tool_schemas` is always `[]` and recovery is gated off, so `response.tool_calls` is never populated there). A real cleanup-leg candidate — moderate size, since it's intertwined with the shared loop body.
  4. **Provider-config store overload** — `num_ctx`, `thinking_enabled`, `reasoning_effort` all live on `LLMProviderConfig.config`, which models a *provider connection*, not a *usage policy*. Correct per the ratified precedent, structurally in the wrong home. This is the mission's clearest forward signal (see Action Items → next-mission seed).
  5. **aiosqlite `Event loop is closed` teardown flake** — the mission's oldest carried item (since F05). F09 escalated it from "cosmetic warning" to "an actual intermittent test failure… fix at `/mission-debrief`, don't defer a fifth time." **Disposition at close: recorded for explicit fix-or-accept in routine maintenance** rather than a sixth silent carry-forward.
- **OpenAI-compat mapping duplication now exists in two places** (F11 request-kwargs + F12 content-blocks; openai ≡ ollama-`/v1`), each guarded by a conformance parity test and a rule-of-three code comment. Well-managed, but a genuine 3rd `/v1` provider would now trigger *two* simultaneous lifts, and the "don't refactor pre-emptively" judgment has been re-derived twice in comments rather than promoted once to `agents.md`.

### Documentation
- Two `/behavior-test` specs were recommended by flight debriefs and not yet authored: `save-preserves-config` (F11 — a property that already broke once and has zero runtime regression coverage) and `vision-round-trip` (F12 — the only proof of image-grounding is one-off HAT prose). Author each inline in the next planning conversation that touches those surfaces.
- The rule-of-three forward-note and the seed-before-overlay save pattern (F11) live only in code comments, not in `agents.md` conventions.

## Deferred Capabilities (criterion #3 — recorded reasons)

The Flight 1B backlog items not implemented this mission, each deferred with rationale (source: `flights/01b-provider-capability-audit/`, operator-ratified 2026-06-17). None is a currently-live bug; each is single-provider, a control-knob (not a modality), cosmetic-precision, or sequencing-blocked by an already-deferred prerequisite.

- **A3 — Prompt caching + `TokenUsage` cache-read/creation fields.** *Deferred*: additive cost-accounting/latency optimization; nothing is blocked or broken without it. Naturally bundled with its own small flight (A3 + the cache-token codec fields, A-item's companion) when caching becomes a priority.
- **A5 — Parallel-tool-call toggle (`tool_choice`/disable-parallel).** *Deferred*: a control knob, not a new capability; parse already works for Anthropic/OpenAI/Ollama; not honorable on Ollama `/v1` at all. Defer until a concrete need to suppress parallel calls arises.
- **B1 — Anthropic streaming usage fidelity (raw-event iteration vs. byte heuristic).** *Deferred*: cosmetic accounting precision; F06/F08 built real telemetry features on the existing heuristic without needing exactness. Stream-loop rewrite is disproportionate to the display-precision gain.
- **B2 — Ollama streaming lifecycle / typed-event fidelity.** *Deferred*: text/tool/usage deltas already work; the missing thinking-delta parse is only useful once Ollama populates `Message.thinking` (itself deferred) — a sequencing dependency puts it below its own prerequisite.
- **B3 — Anthropic pre-flight token counting (`messages.count_tokens`).** *Deferred*: single-provider-only (OpenAI's counter is Responses-API-only/unused; Ollama has none), so it can't generalize into a cross-provider contract feature. A nice-to-have budgeting convenience.
- **B4 — OpenRouter `supported_parameters` per-route request-param gating.** *Deferred*: the discovery mechanism already exists (consulted for the `tools` gate); extending it to gate `response_format`/`reasoning`/`stop` is newly-ripe now that A4 landed, but it's a single-provider adapter refinement with no user-visible bug behind it (worst case: a downstream model's own API errors surface). The most "ready to pick up next" of the six.

## Lessons Learned

- **"Hand-rolled, no framework" ≠ "frozen loop."** The mission's most important framing correction (operator, 2026-06-19): leveraging an LLM's full capabilities *inherently* reaches into the agent loop, the `Message` protocol, and the codec — not just the adapters. The architecture that stays fixed is *no framework* and *wrap the official SDKs*; the loop is extended where a capability requires it (Flight 3's degraded protocol, F12's content widening), with the auth-pause/sandbox invariants preserved. Keep this boundary explicit for the next capability mission.
- **Front-load wire-format risk with a doc-gate leg.** Pinning per-provider wire shapes from SDK stubs + first-party docs *before* any wiring converted F10's "correct-it-mid-flight" into F11/F12's "zero corrections." Adopt the Leg-01 doc-gate for any provider-wiring flight.
- **Contract widenings create consumer-side bugs the instant they land, before any producer exists.** F12's two latent bugs were legal-but-untriggered from the moment `content` could be a list. Capability-only flights should smoke the full *read* path with a synthetic value, not wait for a producer.
- **Boundary-projections (`content_to_text`) are good tactical fixes with a fork point.** Fine while the frontend only *displays* what was sent; a dead-end the moment the UI must *reconstruct/re-edit* content — at which point the codec's structured encoder should feed the event instead. Decide this before scoping the thumbnail follow-up.
- **A config store models one thing; watch the third knob.** The provider-config surface quietly became a usage-policy store (`num_ctx`, `thinking_enabled`, `reasoning_effort`). The third field is the signal that the surface is wrong, not that the field is wrong. The next tuning field before the agent-config migration warrants "is this a 4th field in the wrong home?" scrutiny.

## Methodology Feedback

- **The debrief→next-flight feedback loop worked as designed** — and visibly. Each capability flight's debrief recommendation shaped the next flight's design decision (F10→F11 config-surface; F11→F12 doc-gate + convention corrections). This is the clearest cross-flight evidence in the mission that the debrief step is load-bearing, not ceremonial.
- **Batch review before commit paid off on a cross-cutting bug** (F11 config-wipe) that per-leg "tests passing" gave false confidence on. Keep the single-review-after-last-autonomous-leg model for flights whose legs share a UI×backend seam.
- **Guided HATs consistently found real issues** ("we almost always find a little something") — wire-format surprises, UX gaps, and a live `FileList` bug that no hermetic test would have caught. The optional-HAT leg is worth including on any flight with a live-environment surface.
- **Orchestration friction**: no operator notes. The recurring internal pattern (implementer subagents backgrounding `make test-unit` and pausing, the Flight Director finalizing artifacts) was absorbed by the FD without operator-visible cost.
- **Carry-forward hygiene held**: every rescope (Gemma), deferral (compaction ×3, A3/A5/B1–B4), and accepted gap (OpenAI/Ollama HAT) was recorded rather than silently dropped — which is what made this close auditable.

## Action Items

- [ ] **Next-mission seed — agent-level config surface** *(operator: "near-future mission option")*. Introduce an agent/usage-policy config store and migrate `num_ctx`/`thinking_enabled`/`reasoning_effort` off the provider-connection config, with agent-over-provider resolution order. Flight-class work; the mission's clearest architectural forward signal.
- [ ] **Routine-maintenance disposition for carried debt** — fix-or-formally-accept: the aiosqlite teardown flake (oldest item, F09 escalated), the `ImageContent` bare `assert`, and the F10 live-thinking `visibility` omission are all quick wins that could ride a single maintenance/health leg. The Leg-09 dead-code removal is a moderate cleanup-leg candidate.
- [ ] **Author the two outstanding `/behavior-test` specs** inline when next touching those surfaces: `save-preserves-config` (F11) and `vision-round-trip` (F12).
- [ ] **Promote patterns to `agents.md`**: the OpenAI-compat mapping-duplication rule-of-three (cite both the A4 request-kwargs and A2 content-block pairs) and the seed-before-overlay provider-config save pattern (F11).
- [ ] **Record the Windows-packaging seed-collection bug** (F05 catalog seed not bundled into the frozen build → silent default fallback) for a fix — carried to mission Known Issues.
- [ ] **Deferred, recorded (not scheduled)**: context compaction (three-time deferral, F09 field evidence — strongest independent next-mission candidate); documents/PDF inputs (own flight, distinct wire shape); own-image thumbnail + full replay rendering (one coupled unit); `web_search` DDG-scrape reliability; the OpenAI + Ollama live HAT (accepted gap this close); A3/A5/B1–B4 per the deferral rationale above.
