# Mission: LLM Provider Layer Hardening & Capability Completeness

**Status**: active
**Depends on**: none (touches `the_one/llm/` + `the_one/agent/`; independent of M15's packaging work)

> **Origin (2026-06-17).** Scoped out of a research conversation that asked
> "should we drop the hand-rolled agent loop for a framework?" The investigation
> (deep-research pass + reading the source of two TS agent tools the operator
> admires — `earendil-works/pi` and `openclaw/openclaw`) reached a clear answer:
> **no framework, and stay in Python.** Both reference tools independently chose
> the *exact* architecture this project already has — a thin per-provider adapter
> over the **official vendor SDKs**, not a framework (LangChain), not a
> reimplemented wire layer (LiteLLM), which they relegate to "one optional
> OpenAI-compatible endpoint you can point at." `the_one/llm/` is already that
> shape. The operator's pain is therefore not architectural; it is **three
> specific holes** in the provider layer. This mission fixes those holes and
> records the strategic decisions so they don't get re-litigated.

> **★ Spike correction (Flight 1, 2026-06-17).** The recon spike **falsified hole
> #1**: the operator's actual Anthropic bug is **not** extended-thinking replay —
> it is **issue #122**, a tool-`input_schema` rejection (Anthropic 400s on
> top-level `oneOf/allOf/anyOf`, and requires a top-level `type`), reproduced live.
> Extended-thinking replay was *forced on* and **succeeded** — and the code never
> even enables thinking. **Hole #2 (#105)** is confirmed: gemma3:4b can't be
> offered tools (Ollama rejects them), so the gate is correct and the fix is
> text-form tool-call recovery. **any-llm** was evaluated and rejected (fixes
> neither bug) → **hand-roll**. Full evidence:
> `flights/01-recon-root-cause-spike/flight-log.md`.
>
> **★ Scope broadened (operator, 2026-06-17).** Beyond fixing #122 + #105, this
> mission is now **preemptive capability-completeness**: bring each provider
> adapter to full coverage of the useful capabilities its **official SDK** exposes
> — extended thinking (first-class, *not* a demoted optional), plus prompt
> caching, structured outputs / JSON mode, vision/multimodal, reasoning-effort
> controls, document inputs, and whatever else each SDK surfaces. To keep this
> bounded and evidence-driven, an early **provider capability-audit flight**
> enumerates, per SDK (Anthropic / OpenAI / Ollama / OpenRouter), what's exposed
> vs. what the-one wires through; the gap list becomes the capability-flight
> backlog (prioritized by the operator). The two confirmed bugs are the immediate
> work; the capability coverage is the broader goal.
>
> **★ Agent-layer scope expansion (operator-authorized, Flight 3 Leg 08, 2026-06-19).**
> Flight 3 Leg 08 deliberately expands into `the_one/agent/` (new
> `agent/degraded_tools.py`, a `DEGRADED_BASE_PROMPT` in `agent/config.py`, and a
> degraded-branch change in `agent/core.py`) to inject a **direct tool protocol**
> for non-tool-capable models (`supports_tools=False`, e.g. gemma3:4b) — two
> behavior-test runs proved recognizer-only recovery is best-effort, not reliable,
> so the durable fix is telling the model the catalog + one parseable call format
> upstream. Narrowly scoped to tool exposure / prompt for non-tool models; does NOT
> touch the iteration/auth-pause logic or the `LLMProvider` contract. See the
> Flight 3 leg-08 spec + flight-log Decisions.

> **★ Agent-loop iteration-logic expansion (operator-authorized, Flight 3 Leg 09, 2026-06-19).**
> Flight 3 Leg 09 expands further — into the agent loop's **iteration/dispatch
> logic** in `agent/core.py` `_run_iterations` (which the prior legs deliberately
> left untouched) — to add a degraded-path **redundant-tool-call backstop**: detect
> when a non-tool-capable model re-emits a call whose result it already holds and
> terminates with an empty message, suppress the re-dispatch, and synthesize a
> non-empty closing answer. Scoped to the `not supports_tools` branch; does NOT
> alter the auth-pause/`_deferred_tool_calls` flow or the `LLMProvider` contract.

> **★ Outcome framing corrected (operator, 2026-06-19).** The original Outcome /
> Constraints wording — "the agent loop … is untouched; changes confined to
> `the_one/llm/` … nothing else" — was **incorrect**. The mission's real expected
> outcome is to **leverage the full set of tools and abilities each LLM exposes**,
> which *inherently* impacts the agent loop (tool exposure, dispatch, iteration) —
> not just the provider layer. The **"hand-rolled, no framework"** decision still
> stands (the loop is *extended*, not replaced; auth-pause + sandbox safety
> invariants preserved), but the **"agent-loop-untouched / `the_one/llm/`-only"**
> boundary does **not**. Outcome + Constraints updated below. The Flight 3
> leg-08/09 banners above are therefore the *first instances* of expected
> capability-driven loop work — not out-of-scope exceptions.

## Outcome

A conversation that uses **extended thinking** on Anthropic models *and* calls
tools in the same turn completes reliably instead of erroring — because thinking
blocks are now captured in the message protocol and replayed correctly. A
conversation driven by an **open/local model (e.g. Gemma via Ollama)** reliably
executes tool calls, including the cases where the model emits a tool call as
loose text instead of a structured `tool_calls` array. And the provider layer
stops carrying **hand-maintained model tables that silently drift** out of date.
Delivering this is **not** confined to the provider layer: fully leveraging what
each LLM can do — extended thinking, structured outputs, vision, and reliable
tool use for tool-capable *and* non-tool-capable models — **inherently reaches
into the agent loop** (tool exposure, dispatch, iteration), the `Message`
protocol, and the persistence codec, alongside the `the_one/llm/` adapters. What
stays fixed is the **architecture**: the loop remains **hand-rolled** (no agent
framework) and the provider layer keeps wrapping the official vendor SDKs. The
loop is *extended* where a capability requires it — it is not replaced, and its
safety invariants (auth-pause semantics, the sandbox) are preserved.

## Context

`the_one/llm/` is a hand-rolled provider abstraction that is already
well-architected and maps almost 1:1 onto how `pi-ai` is built:

- **Base contract** — `the_one/llm/base.py` (~370 lines): the `LLMProvider` ABC
  (`complete()`, `stream()`, `supports_tools()`, `tool_schema()`, `aclose()`),
  plus the canonical message protocol (`Message`, `ToolCall`, `ToolResult`,
  `TokenUsage`). `tool_schema()` defaults to OpenAI function-calling format;
  providers override `_to_api_message()` for their wire format.
- **Concrete providers** — Anthropic (`anthropic_provider.py`, official
  `anthropic` SDK), OpenAI (`openai_provider.py`, official `openai` SDK),
  OpenRouter (`openrouter_provider.py`, thin `OpenAIProvider` subclass),
  Ollama (`ollama_provider.py`, **raw `httpx`** against the OpenAI-compatible
  `/v1/chat/completions`), and Mock (`mock.py`, dev-mode only).
- **Shared streaming** — `_streaming.py` (`_StreamAccumulator`, index-keyed
  tool-call delta concatenation + interim usage emission).
- **Agent loop** — `the_one/agent/core.py` `Agent._run_iterations()` is the
  while-loop that calls `llm.stream(...)`, dispatches tool calls, and continues.

**The three holes the investigation found:**

1. **No extended-thinking / reasoning handling anywhere.** Grep found zero
   thinking-block capture or replay. Anthropic's extended-thinking + tool-calling
   protocol *requires* the assistant turn's `thinking` blocks (with their
   signatures) to be preserved and replayed in the next request alongside the
   `tool_use` blocks, or the API rejects the turn. Because there is no code for
   thinking blocks, they are dropped — the **leading hypothesis for the
   Anthropic tool-use bug the operator already hit**. (Confirmed-as-a-real-class
   problem by LiteLLM's own docs: "Anthropic extended thinking with tool calling
   is not fully compatible with OpenAI-compatible API clients.")

2. **Open-model tool-use lives in the one hand-rolled HTTP path.** Gemma runs
   through `ollama_provider.py` — the only provider parsed by hand over raw
   `httpx`. Open/local models are loose about tool-call formatting and frequently
   emit a call as JSON/text in `content` rather than as a structured
   `tool_calls` array (the failure mode the Hermes `<tool_call>` format exists to
   tame). The current parser only reads structured `tool_calls`, so those calls
   are silently lost — the **leading hypothesis for the Gemma tool-use bug.**

3. **Hand-maintained model tables drift.** `openai_provider.py` resolves context
   windows from a hand-curated model-name prefix table; Anthropic's window is a
   hard-coded class default. This is exactly the "keeping up is untenable" tax.
   (OpenRouter and Ollama already source this live — `/models` and `/api/show` —
   so the *don't-hand-maintain* pattern already exists in-repo. Note the live-
   fetch shape does **not** transfer to OpenAI directly: OpenAI's `/models` API
   exposes no `context_length` (see `openai_provider.py:37-38`), so OpenAI's
   limits have to come from a generated/cached catalog rather than a live call.)

**Strategic decisions already settled (do not re-litigate; recorded as
constraints):** stay in Python; keep the **hand-rolled** architecture (do **not**
adopt an agent framework); keep wrapping the **official vendor SDKs** rather than
reimplementing wire protocols. **"Hand-rolled" means *not a framework* — it does
not mean the agent loop is frozen.** Leveraging the LLMs' full capabilities
inherently extends the loop (tool exposure, dispatch, iteration), as Flight 3
demonstrated; that work is in scope. The build-vs-adopt question ("harden vs.
`any-llm`") was resolved provider-layer-local, but capability work legitimately
spans the agent layer too.

## Success Criteria

- [x] A tool whose `input_schema` uses top-level `oneOf/allOf/anyOf` (or omits a
      top-level `type`) no longer fails the whole Anthropic turn — the schema is
      sanitized before send, and if a schema genuinely can't be sent the failure
      names the offending tool rather than a bare index. *(#122; behavior- or
      fixture-test-backed against the real Anthropic constraint)*
- [x] **Per-SDK capability audit exists** enumerating, for Anthropic / OpenAI /
      Ollama / OpenRouter, the capabilities the official SDK exposes vs. what the
      `LLMProvider` layer currently wires through — yielding a prioritized gap
      backlog. *(the bound on "implement whatever the SDKs expose")*
- [ ] **Each prioritized capability gap is either implemented behind the
      `LLMProvider` contract or explicitly deferred** with a recorded reason — so
      the provider layer's coverage of its SDKs is intentional, not accidental.
      *(capability-completeness; scope set by the audit + operator priority)*
- [ ] With extended thinking enabled on an Anthropic model, a single turn that
      both emits thinking **and** calls a tool completes without an API error,
      and the follow-up turn (carrying the tool result) also succeeds — i.e.
      thinking blocks + signatures are preserved and replayed.
      *(behavior-test-backed against a real Anthropic model)*
- [ ] The `Message` protocol carries reasoning/thinking content as a
      first-class field (a `ThinkingPart`-equivalent) instead of discarding it;
      it round-trips through persistence and is available to the web UI.
      *(unit-test-backed)*
- [~] ~~A tool-using conversation with **Gemma via Ollama** reliably executes tool
      calls, **including** when the model emits the call as text/JSON in
      `content` rather than a structured `tool_calls` array.~~ **NOT MET /
      RESCOPED (operator, 2026-06-19, M16 F03 L08C).** gemma3:4b (a 4B model) can
      decide to invoke a tool but cannot reliably complete the multi-step discovery
      hop (search → select → call); always-on catalog injection caused over-routing
      that made the agent unusable for chat; chat-only was chosen for UX (a reliable
      chat agent beats an unreliable tool agent that frequently no-responds). Models
      that DO advertise the `tools` capability continue to use the structured path
      unaffected. This is an explicit, operator-authorized scope decision — not a
      bug. Carry to `/mission-debrief`. See flight-log leg-08C.
- [x] A **cross-provider tool-use conformance test** exists and passes for
      Anthropic, OpenAI, Ollama, and Mock — asserting that a request→tool_call→
      tool_result→final-answer round-trip works uniformly through the
      `LLMProvider` contract. *(this is the regression net that stops future
      provider-quirk drift)*
- [ ] Model context-window limits for OpenAI and Anthropic are sourced without a
      hand-maintained per-model table that silently drifts. (The sourcing
      mechanism — live fetch with caching vs. a generated/cached catalog — is
      deliberately left to the open question; OpenAI in particular cannot be
      live-fetched the way Ollama/OpenRouter are, since its API exposes no
      context-window field.) *(test-backed)*
- [ ] No agent framework is added and the provider layer still wraps official
      SDKs; the `LLMProvider` contract and the provider-shape-portability
      convention (`Message.content` is always `str`; `ToolResult` normalization)
      are preserved. *(records the strategic decision as a verifiable boundary)*

## Stakeholders

- **Operator / maintainer** — wants cross-provider tool use that just works and a
  provider layer that doesn't demand constant manual catch-up, without taking on
  a framework dependency or a rewrite.
- **End users** — anyone running the agent against Anthropic-with-thinking or a
  local Gemma/Ollama model and hitting silent tool-call failures today.
- **Future provider additions** — a conformance suite + live model catalogs make
  the next provider cheaper and safer to add.

## Constraints

- **No agent framework (but the loop is not frozen).** The architecture stays
  **hand-rolled** — do not adopt LangChain/LiteLLM/etc. or replace the loop. But
  the mission changes whatever leveraging an LLM capability requires: the
  `the_one/llm/` adapters, the `Message` protocol, the persistence codec, **and
  the agent loop / tool exposure / dispatch** (e.g. Flight 3's degraded tool
  protocol + redundant-call backstop). Extending the hand-rolled loop is in
  scope; adopting a framework is not.
- **Stay in Python.** The language decision is settled (the TS-ness of the
  reference tools is about CLI distribution/frontend ergonomics, not this
  project's exec-heavy/sandboxed/packaged shape — and not the cause of any bug
  here).
- **Wrap official SDKs; do not reimplement wire protocols.** Anthropic/OpenAI/
  OpenRouter keep their official SDKs. Ollama may stay raw `httpx` (it is a
  genuinely OpenAI-compatible server) **or** adopt the official `ollama` SDK —
  see Open Questions — but either way the fix is *parsing robustness*, not a
  reimplementation.
- **Preserve the `LLMProvider` contract and provider-shape-portability
  convention** (`Message.content` always `str`; `ToolResult.__post_init__`
  JSON-normalizes non-str content). Adding a thinking field must not break
  consumers that read `content` as `str`.
- **Do not regress streaming usage accounting** (`_StreamAccumulator` interim
  usage emission, per-provider bytes-per-token).
- **Preserve dev-mode mock behavior** and the encrypted-credential store
  contract (including the `__MASKED__` API-key sentinel in the provider edit
  form).
- **Out of scope**: adopting a full agent framework; a TypeScript rewrite;
  adding new providers; **regressing** the agent loop's
  auth-pause/`_deferred_tool_calls` semantics or the sandbox (the loop *may* be
  extended for capability work — see the Outcome — but these safety invariants
  must be preserved); changing the web UI beyond surfacing thinking content.

## Environment Requirements

- **Development**: existing Python 3.11+ `pip -e ".[all-llms,dev]"` host install.
- **For the Anthropic thinking criterion**: an Anthropic API key and access to an
  extended-thinking-capable model.
- **For the Gemma/Ollama criterion**: a local Ollama install with a
  tool-capable Gemma model — plus a **recorded/fixtured** loose-format response
  so the regression test is deterministic and does not require a live model.
- **For the OpenAI criterion**: an OpenAI API key (or a recorded fixture).
- Live-model checks belong behind the existing `@pytest.mark.live` /
  fixtured-response patterns so default `make test` stays hermetic.

## Open Questions

- [x] ~~**Confirm root cause before building.**~~ **Resolved by Flight 1.** Hole #1
      falsified → real bug is #122 (tool-schema); hole #2 (#105) confirmed. See
      flight log.
- [x] ~~**Harden vs. adopt `any-llm`.**~~ **Resolved: hand-roll.** any-llm was
      source-evaluated against the real bugs (#122, #105) and fixes neither (its
      Anthropic adapter would silently drop top-level combinators; its Ollama
      adapter has no text-form recovery). Keep the hand-rolled `LLMProvider`.
- [ ] **Thinking representation** *(now scoped to the optional lower-priority
      thinking flight, not the critical path).* How to model thinking in `Message`
      (typed field vs. structured parts), persistence, and whether the UI displays
      or only stores it. Spike de-risked the capture side: `get_final_message()`
      carries signed thinking blocks, so replay-capture is low-effort; live UI
      streaming of thinking deltas is the harder, optional part. Anthropic
      specifics still apply: signatures, redacted thinking, interleaved ordering.
- [ ] **Ollama: official SDK vs. raw `httpx`.** Does adopting the `ollama` SDK
      meaningfully improve tool-call robustness, or is hardening the existing
      `httpx` parser (recover tool calls from `content`) sufficient and lower-
      dependency?
- [ ] **Model-catalog sourcing.** Live fetch + cache vs. build-time generated
      artifact (pi's `models.generated`). Where does the cache live, and how
      does it degrade when offline?
- [ ] **Reasoning beyond Anthropic.** Scope of OpenAI reasoning-model
      (`o*`-series) and `<think>`-tag-emitting open models in this mission, vs.
      Anthropic-only for the first pass.
- [ ] **Header-gated 1M context (deferred from Flight 5).** Flight 5 reports the
      correct per-model context window from the catalog but sends no `context-1m`
      beta header — current Claude models (incl. the default `claude-sonnet-4-6`)
      are natively 1M, so none is needed. If a model is later targeted that still
      requires the dated `context-1m-*` header to unlock 1M, evaluate sending it
      (via `extra_headers` on the Anthropic SDK call) as part of the planned
      extended-thinking/capability flight, where request-path capability work
      already lives. *(Recorded during Flight 5 planning, 2026-06-19.)*
- [ ] **/mission-debrief carry-forward (08C scope decision).** The "Gemma reliably
      executes tool calls" criterion was reversed (see Known Issues above). The
      debrief should record: (a) the trajectory L08→L08A→L08C and what was learned
      about 4B multi-step composition; (b) the Leg-09 backstop in `core.py` is now
      harmless dead code on the chat-only path (a candidate cleanup); (c) the
      CP5 false-pass in the behavior test (single-`shell` agent masked full-catalog
      over-routing) as a test-validity lesson.
- [ ] **Non-tool-capable models: chat-only (08C design decision).** Models with
      `supports_tools()=False` (e.g. gemma3:4b) are conversational agents only.
      This is by design (08C). If a future Ollama model advertises `tools` it will
      automatically take the structured path. No further action needed unless
      the operator wants tool use on sub-tool-capable models.

## Known Issues

Confirmed by the Flight 1 spike (2026-06-17):

- [x] ~~**#122 — Anthropic rejects tool `input_schema` with top-level
      `oneOf/allOf/anyOf` (and requires top-level `type`).**~~ **RESOLVED by Flight 2**
      (2026-06-18): pure schema sanitizer shipped + wired into the Anthropic adapter
      (drop-and-proceed + `BadRequestError → tool-name`); live-verified against
      first-party Anthropic. Also wired (gated) onto the OpenRouter→Anthropic path after a
      live probe showed it 400s identically. See
      `flights/02-anthropic-tool-input-schema/flight-debrief.md`.
- [~] ~~**#105 — open models (gemma3:4b) emit tool calls as text that is never
      recovered.**~~ **RESCOPED (M16 F03 L08C, 2026-06-19).** The recovery
      kernel works (Flight 3 legs 01–07 landed). The longer question — should
      non-tool models attempt tool use via protocol injection — was trialled
      (leg 08A), found unreliable for 4B models, and resolved as: **non-tool-
      capable models are conversational-only by design (08C)**. Recovery is
      gated OFF for `supports_tools()=False` models; their content passes through
      verbatim. Reliable tool use requires a model that advertises the `tools`
      capability. Carry to `/mission-debrief`.

Discovered during Flight 2 (2026-06-18):

- [ ] **OpenRouter→Anthropic #122 path lacks DD5/DD6 parity** — discovered in Flight 2,
      affects the `OpenRouterProvider` `anthropic/*` route. Flight 2 sanitizes the common
      `anyOf`/`oneOf` case on this path, but (operator-scoped minimal) does **not** add
      drop-and-proceed or the `BadRequestError → tool-name` net. Consequence: a
      *genuinely-unsanitizable* tool schema forwards unmodified and 400s the whole turn on
      OpenRouter (WARN-logged), whereas Anthropic-direct drops it and the turn proceeds.
      Same underlying constraint, divergent reliability guarantee. **Owned by Flight 4**
      (cross-provider conformance): decide DD5/DD6 parity vs. formalizing "forward-with-WARN"
      as the OpenRouter contract.
- [x] ~~Hole #1: extended-thinking replay errors on tool use~~ — **falsified by the
      spike** (replay succeeded; thinking never enabled). Retired *as a bug* — but
      extended thinking is now a **planned capability** (see Scope-broadened banner),
      not a problem to fix.

Discovered during Flight 5 HAT (2026-06-20):

- [x] ~~**Telemetry overlay used-token state doesn't persist on chat reopen**~~ —
      discovered in the F5 HAT, affected the web chat telemetry overlay. Usage events
      were projection-only (never `add_event`'d to history) and `renderHistory`
      didn't replay them, so reopening an old chat showed `0 / max` instead of the
      accumulated `used / max`. **RESOLVED by Flight 6** (2026-06-20, PR #134): the
      last completed turn's `{input_tokens, output_tokens, context_tokens}` is now
      persisted to `session_metadata["last_usage"]` at both turn-settle points and
      restored on `session_joined` (with a max-only `/context-window` seed so it isn't
      re-zeroed). HAT-confirmed across a genuine server restart. See
      `flights/06-telemetry-overlay-usage-persistence/`.

Discovered during Flight 6 (2026-06-20):

- [ ] **`if last_input:` usage-persist guard drops real turns that report
      `input_tokens=0`** — surfaced by the F6 L03 design review. The per-turn
      `last_usage` write is guarded on `last_input` (the last assistant step's
      `input_tokens`); a real provider that reports `input_tokens=0` — notably Ollama,
      whose adapter uses `u.get("prompt_tokens", 0)` and can omit `prompt_tokens` (or
      the whole usage block) — settles with `last_input == 0` and has its snapshot
      suppressed, so reopening shows `0 / max` for that provider. Not fixed in F6 (the
      fullness bar is unrestorable for such a turn regardless, since `context_tokens`
      *is* the missing input count, and a fix reopens landed L01 + its guard tests).
      Candidate follow-up: guard on "saw any usage event" or `last_input or
      total_output` so the in/out counts still restore. Carry to `/mission-debrief`.
- [x] ~~**Model-catalog runtime refresh parsed the wrong models.dev shape**~~ —
      discovered + **fixed in the F5 HAT** (commit `9f152b9`): `project_raw` was
      built blind (models.dev unreachable in Leg 1) and extracted zero models, so the
      cache was never written. Parser corrected to the real `raw[provider]["models"]`
      shape; seed regenerated from authoritative models.dev (also fixed over-reported
      1M windows for `sonnet-4-5`/`opus-4-5`). Verified live.

Discovered during Flight 7 (2026-06-21):

- [ ] **`web_search` (DuckDuckGo HTML scrape) returns "No results found" for every
      query on the installed instance** — surfaced in the F7 live repro of the Sonos
      chat-loop hang. `web_search` uses `https://html.duckduckgo.com/html/`
      (`tools/_search_backends.py` `DDGSearchBackend`, no API key); DDG appears to
      throttle/block the scrape, so the agent gets nothing and resorts to *guessing*
      URLs via `fetch_url`/`http_request` — which is how it reached a live audio
      stream and hung. **Out of scope for F7** (which fixes the hang/cancel/queue);
      split here per the F7 verify-leg adaptation criteria. Candidate follow-up: a
      more robust/keyed search backend, or detect the empty-DDG response and surface
      it honestly. Carry to `/mission-debrief`. **NOTE: being addressed by Flight 8**
      (DD3 — configurable backend + honest-empty).

Deferred (own-mission candidate, 2026-06-23):

- [ ] **Context compaction (eviction / summarization of old conversation turns)** —
      Flight 8 adds per-result governance + conversation-level *accounting + warn* (the
      telemetry overlay turns orange/red as the window fills) but deliberately does NOT
      recover a turn already near the limit. Compaction — evicting old tool-result
      content (constrained by tool_use↔tool_result pairing) or LLM-summarizing earlier
      turns (added cost/latency/quality risk, persistence-codec impact) — is a subsystem
      in its own right. Operator judgement (2026-06-23): "almost feels like its own
      mission." Seeded here as a future-mission candidate, not an M16 flight.
      **Confirmed still-deferred after F8 (2026-06-25):** the F8 verify behavior-test
      (`tests/behavior/agent-governance-and-search`, 9/9 pass) witnessed the governor bound
      + the overlay *warn* signal live — i.e. F8 *informs* the operator at fullness but does
      not *recover* a turn near the limit. Compaction remains the open gap.

## Flights

> **Note:** Tentative suggestions, not commitments. Flights are planned and
> created one at a time as work progresses; this list will evolve.

> **Reshaped by the Flight 1 spike + scope-broadening (2026-06-17).** Two tracks:
> **(A) bug fixes** (#122, #105 — immediate) and **(B) capability completeness**
> (audit-driven; extended thinking + other SDK capabilities). Capability flights
> after F2A are planned from the audit's gap list, prioritized by the operator —
> the list below names the ones already known to be wanted.

- [x] Flight 1: **Recon & root-cause spike** — **LANDED.** Falsified hole #1
      (extended-thinking replay; real Anthropic bug is #122, reproduced live);
      confirmed hole #2 (#105) and captured the gemma text-form fixture; settled
      build-vs-adopt → **hand-roll** (any-llm rejected). Output: confirmed root
      causes + go/no-go below. See `flights/01-recon-root-cause-spike/`.
- [x] Flight 1B: **Provider capability audit** — **LANDED (audit complete; backlog A1–A5/B1–B4 ratified).** Enumerate, per official SDK
      (Anthropic / OpenAI / Ollama / OpenRouter), the capabilities the SDK exposes
      vs. what `the_one/llm/` wires through (extended thinking, prompt caching,
      structured outputs / JSON mode, vision/multimodal, reasoning effort, document
      inputs, parallel tool calls, stop sequences, streaming events, token
      counting, …). Output: a prioritized capability-gap backlog that drives the
      capability flights below. *(read-only recon, like F1; bounds the "implement
      whatever the SDKs expose" scope.)*
- [x] Flight 2 **(HIGH — the real Anthropic bug): Anthropic tool `input_schema`
      compatibility (#122)** — sanitize tool `input_schema` before sending to
      Anthropic: wrap/flatten top-level `oneOf/allOf/anyOf` and ensure a top-level
      `type`; isolate and **name the offending tool** instead of failing the whole
      turn. (Optionally folds in #122's bundled UI enhancement — a copy-button on
      chat error bubbles — or split that out.) Closes the bug the operator hit.
- [x] Flight 3: **Open-model tool-use robustness (Ollama/Gemma) (#105)** — add a
      **text-form tool-call recovery parser** that runs when `supports_tools()` is
      `False`: detect the ` ```tool ` fenced Python-call block (captured from
      gemma3:4b) plus Hermes-tag / bare-JSON variants, normalized into structured
      `ToolCall`s. **Do not** try to offer tools to non-tool-capable models —
      Ollama rejects them. Fixtured regression from the captured response.
- [x] Flight 4: **Cross-provider tool-use conformance suite** — a shared,
      provider-parametrized test asserting the request→tool_call→tool_result→
      final round-trip works uniformly across Anthropic/OpenAI/Ollama/Mock. Now
      also the regression net guarding the #122 and #105 fixes.
- [x] Flight 5: **Model-catalog drift removal** — **LANDED (2026-06-20).** Replaced
      the hand-maintained OpenAI prefix table (+ its Studio-endpoint duplicate) and
      Anthropic's hard-coded window with a **built-in catalog refreshed on a daily
      cadence** at runtime (bundled seed + on-disk cache from models.dev), resolved
      locally cache→seed→default — installs stay current without a redeploy and an
      old chat's window survives an offline restart. Reports the catalog's per-model
      window (1M for current Claude; no `context-1m` header — deferred to the
      capability flight). HAT caught + fixed a critical refresh-parser bug (built
      blind against an assumed models.dev shape) and an over-reporting seed. Full
      suite `3422/10/594`, 0 failures. See `flights/05-model-catalog-drift-removal/`.
- [x] Flight 6: **Telemetry overlay usage persistence** — **LANDED (2026-06-20,
      PR #134, stacked on F5 #133).** Persists the per-session token-usage snapshot in
      `session_metadata["last_usage"]` (via the existing `set_session_metadata_key`
      primitive — no migration) and restores it on `session_joined` so reopening an old
      chat (incl. after a server restart) shows the last turn's `used / max` fullness,
      not `0 / max`. Writes at both turn-settle points (normal + auth-resume); frontend
      `/context-window` seed made max-only to avoid re-zeroing the restore. Added a
      backward-compatible `config["input_tokens"]` test seam to `MockProvider` (+ fixed
      a pre-existing dev-mode `__init__` bug). Full suite `3443/10/595`, 0 failures;
      Playwright browser flow + HAT (genuine restart) PASS. Surfaced one carried-forward
      Known Issue (the `if last_input:` guard vs. Ollama `input_tokens=0`). See
      `flights/06-telemetry-overlay-usage-persistence/`.
- [x] Flight 7: **Chat-loop robustness & control** — **LANDED (2026-06-21, PR #137).**
      HAT verified live (no-hang + cancel + lock-release). Sourced from a live repro:
      the chat loop hung indefinitely when a turn fetched a continuous-stream URL via
      the web tools (provider-agnostic — sonnet-4.6 + ministral). Fixes: web tools
      (`http_request`/`fetch_url`) stream + in-loop byte cap + total deadline + media
      content-type short-circuit (no more infinite-stream hang); a per-tool-call
      timeout at `_execute_tool` (`THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`, default 120);
      interrupt/cancel (WS `cancel` action + task cancellation, partial output kept);
      one queued send-while-thinking. Full suite `3489/10/595`, 0 failures. See
      `flights/07-chat-loop-robustness/`.
- [x] Flight 8: **Agent-loop resource governance & context-budget management** —
      **LANDED (2026-06-25).** 6 legs (governor; search-backend registry + honest-empty;
      encrypted tool-config secret persistence; search-config admin UI; config-driven
      overlay thresholds + non-color a11y; verify). Mid-flight the search work expanded
      (operator) into a configurable engine registry (DDG default + SearXNG + Google PSE +
      Brave + Tavily) with masked keys in the tools-admin form. Verified live by the
      `agent-governance-and-search` behavior test (9/9 PASS). Code + a11y review confirmed.
      Compaction (evict/summarize) explicitly deferred (see Known Issues). Sourced from the
      F07 debrief Rec 1: the three
      chat-loop defects are one theme (no governance over what tools pull into the LLM
      context). A central context-budget governor at the `_execute_tool` dispatch
      boundary bounds EVERY tool result (derived from the active model's context
      window), retiring the inconsistent per-tool LLM-facing caps (keeping the
      transport/file-size safety caps); conversation-level accounting surfaced in the
      telemetry overlay (orange/red, warn-only, no eviction); and a configurable
      `web_search` backend with honest empty/blocked surfacing (the upstream fix for the
      URL-guessing that drives the scrape-large-page failure). Compaction
      (evict/summarize) is explicitly deferred (see Known Issues). See
      `flights/08-agent-loop-resource-governance/`.
- [ ] Flight *(capability, planned)*: **Extended-thinking / reasoning support** —
      add a thinking field to `Message`; capture signed thinking blocks in
      `anthropic_provider.py` and replay in `_to_api_message()`; persist and surface
      in the UI. A wanted capability (not the operator's bug). Spike de-risked
      capture (`get_final_message()` carries signed blocks → low-effort); live UI
      streaming of thinking deltas is the harder part (may need raw-event iteration
      the L04 comment flags as "too invasive"). Scope OpenAI `o*`-reasoning and
      `<think>`-tag open models per the audit.
- [ ] Flights *(capability, audit-driven)*: **other SDK capabilities** — e.g.
      prompt caching, structured outputs / JSON mode, vision/multimodal, document
      inputs, reasoning-effort controls — each planned and prioritized from the
      Flight 1B gap backlog, implemented behind the `LLMProvider` contract.
- [ ] Flight N *(optional)*: **Alignment** — hands-on session exercising real
      models and tuning judgment-call behavior that benefits from human feedback.
