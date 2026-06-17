# Flight: Recon & Root-Cause Spike

**Status**: landed
**Mission**: [LLM Provider Layer Hardening](../../mission.md)

## Contributing to Criteria

> This is a **read-only de-risking spike**. It *closes no success criterion by
> itself* — its job is to confirm (or correct) the root-cause hypotheses the
> mission rests on, so the criteria-closing flights (2–5) build on facts, not
> guesses. The criteria it de-risks:

- [ ] (de-risks) Anthropic extended-thinking + tool-use turn completes without error *(SC1 — confirms the actual trigger before Flight 2 builds the fix)*
- [ ] (de-risks) Gemma-via-Ollama reliably executes tool calls including loose-format *(SC3 — confirms the parser truly loses the call, and captures a real loose-format response to seed Flight 3's fixture)*
- [ ] (informs) `Message` carries thinking as a first-class field *(SC2 — the spike characterizes what Anthropic thinking blocks actually look like: signatures, redaction, ordering — feeding the representation design)*

---

## Pre-Flight

### Objective

Reproduce the two suspected provider-layer bugs against the **current** code —
the Anthropic extended-thinking + tool-use failure (hole #1) and the Gemma /
Ollama loose-format tool-call loss (hole #2) — to confirm or correct the
mission's root-cause hypotheses; evaluate whether `any-llm` solves holes #1/#2
for free; and emit a go/no-go recommendation for each downstream flight. No
production code changes — the deliverable is findings and decisions, plus one
captured raw Gemma response as evidence to seed Flight 3's fixture.

### Open Questions

> These mission-level open questions are the spike's **deliverables to resolve**,
> not blockers on the spike itself.

- [ ] **Anthropic trigger** — How is extended thinking enabled on a request today
      (provider config? per-model? not at all)? Grep found zero thinking handling
      and `_build_kwargs` (`anthropic_provider.py:90-100`) **never sets `thinking`
      and always sets `temperature`** (default 0.0). On extended-thinking-capable
      Opus/Sonnet 4.x models the Anthropic API **rejects `temperature` when
      thinking is on** — so a naive repro that just adds `thinking` hits a
      temperature-400, *not* the dropped-signature error, and the provider's
      existing temperature-strip retry (`:162-168`) would mask the real test.
      Resolve: in a throwaway script, set `thinking` **and remove `temperature`**,
      then reproduce and capture the real error.
- [ ] **Hole #1 is a two-turn failure** — Turn 1 (assistant emits thinking +
      `tool_use`) *succeeds*; the dropped-signature failure manifests on **turn 2**,
      when the tool_result is sent back and the replayed assistant turn is missing
      its `thinking` blocks/signatures. A single-turn repro will NOT reproduce
      hole #1. Resolve: drive the full two-turn exchange.
- [ ] **Capture point (replay) vs. live-display (UI)** — Two distinct questions
      the mission text blurred:
      (a) *Replay-capture* — does `stream.get_final_message()` already expose the
      signed `thinking`/`redacted_thinking` blocks, so capture-and-replay is a
      low-effort additive change? Static read says yes — `final.content` carries
      them, `anthropic_provider.py:188-192` merely filters them out — confirm
      against a live response.
      (b) *Live UI display* — streaming thinking *deltas* live is the separate,
      harder problem: `stream.text_stream` (`:178`) yields text only, so live
      thinking display would need raw-event iteration (the "too invasive" refactor
      the L04 comment flags). This does NOT gate replay. Resolve: state plainly
      which Flight 2 needs.
- [ ] **Gemma: is the bug even a parser gap?** Two candidate root causes to
      disambiguate: (a) `OllamaProvider.supports_tools()` (`:71-79`, base.py:341-343)
      reports **`False` for Gemma** (no `tools` capability) → the agent loop
      (`core.py:177-188`) sets `tool_schemas=[]` and **never offers tools at all**;
      or (b) tools are offered but the model emits the call as loose text and the
      parser only reads structured `tool_calls`. Also: the provider talks to the
      `/v1` OpenAI-compat endpoint, which **coerces tool calls server-side**, so
      the loose format is only observable via a raw `/api/chat` call. Resolve:
      probe the capability gate directly AND capture the raw loose-format response
      via `/api/chat`, bypassing the `/v1` shim.
- [ ] **harden vs. `any-llm`** — Does `any-llm`'s thinking + tool-call
      normalization solve holes #1/#2 for free? (Source-read evaluation only;
      default lean is hand-roll.)

### Design Decisions

**Live reproduction over static analysis**: Reproduce both bugs against real
models (operator has Anthropic-with-thinking and local Ollama+Gemma).
- Rationale: The static read was already done during mission review; a spike's
  value is confirming the *actual runtime trigger*, which static analysis cannot.
- Trade-off: Requires live credentials/models; mitigated because both are
  available and reproductions are cheap (short prompts, few calls).

**Reproduce hole #1 via a direct `provider.stream()` call, not the agent loop**:
The throwaway script calls `provider.stream(...)` directly (the
`test_input_tokens_cross_provider_live.py` style) — it exercises the exact same
`_stream_inner` capture code without the agent loop's confounds (`search_tools`/
`continue` virtual tools, `supports_tools()` gate, iteration/pause state).
- Rationale: The "streaming path" that matters for signed-thinking capture is
  `provider.stream()` → `_stream_inner`, not `Agent._run_iterations`. The agent
  loop adds friction with zero diagnostic benefit for this hole.
- Trade-off: Doesn't exercise the full operator code path; acceptable because the
  capture code is identical, and the agent-loop path is kept as an optional
  confirmation only if the direct repro somehow doesn't trigger.

**Capture-point (replay) is the key unknown; live-display is a separate question**:
The spike settles whether `get_final_message()` already carries the signed
thinking blocks (→ Flight 2 replay-capture is a low-effort additive change).
Live UI streaming of thinking deltas is explicitly scoped as a *separate* harder
question, not conflated with replay.
- Rationale: This split is what swings Flight 2's estimate. Replay-capture looks
  low-effort (blocks are in `final.content`); only live-display would need the
  "too invasive" raw-event refactor — and live-display isn't required to close
  the Anthropic bug.
- Trade-off: Spending spike time on streaming internals rather than just
  confirming the error — justified by the Flight 2 estimate swing.

**All thinking/temperature manipulation lives in the throwaway script**: Setting
`thinking` and removing `temperature` happens via a direct SDK call or an
in-script monkeypatch — **never** by editing `the_one/llm/anthropic_provider.py`.
- Rationale: Keeps the flight genuinely throwaway (clean `git status` for
  `the_one/`); the executor must not reflexively edit the provider "just to test."

**`any-llm` evaluated by source-reading, not install**: Read its thinking +
tool-call normalization and judge against holes #1/#2; no install/probe.
- Rationale: Matches the mission's default-lean (hand-roll, lowest dependency
  surface); a full install/probe is only warranted if the source read shows it
  plausibly solves both holes for free.
- Trade-off: Lower confidence than a live probe; acceptable because adopting it
  is the non-default path and would get its own validation in Flight 2 if chosen.

**Gemma fixture is captured raw here, formalized in Flight 3**: The spike stashes
the real loose-format response as evidence in the flight directory; Flight 3
promotes it into a proper test fixture.
- Rationale: Keeps this flight genuinely throwaway (no production/test files
  added) while still capturing the perishable real-model artifact now.
- Trade-off: The fixture isn't wired into a test until Flight 3 — fine, since
  Flight 3 owns the regression.

**Findings home = flight log + mission promotion**: Confirmed root causes get
promoted into the mission's Known Issues; resolved questions update the mission's
Open Questions. Per-leg findings accumulate in the flight log.
- Rationale: A read-only spike's output *is* documentation; the flight log is its
  natural home, and confirmed bugs belong at mission scope for the fixing flights.

### Prerequisites

- [ ] Anthropic API key set, with access to an **extended-thinking-capable**
      Claude model (Opus/Sonnet 4.x). The repro must **pin an explicit model**
      (e.g. via `LIVE_ANTHROPIC_MODEL`) — the live-test default `claude-haiku-4-5`
      does **not** support extended thinking and would not reproduce hole #1.
- [ ] Local **Ollama** running (default `:11434`) with a **tool-capable Gemma**
      model pulled and loadable.
- [ ] Python dev env: `pip -e ".[all-llms,dev]"` host install present.
- [ ] No port conflict introduced — the spike *uses* the existing Ollama on
      `:11434`, starts no new long-running service.

### Pre-Flight Checklist

- [ ] All open questions framed as deliverables (above)
- [ ] Design decisions documented
- [ ] Prerequisites verified (live creds + local Gemma reachable)
- [ ] Validation approach defined (below)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

Throwaway reproduction scripts (not committed) instantiate providers **directly**,
bypassing the agent loop to isolate provider behavior — following the diagnostic
style of `tests/test_input_tokens_cross_provider_live.py` (instantiate provider,
short prompt, inspect result). For hole #1, call `provider.stream(...)` directly
with extended thinking enabled **and `temperature` removed**, offering a tool,
across a **two-turn** exchange (turn 1 emits thinking+`tool_use`; turn 2 replays
with the tool_result and is where the dropped-signature failure surfaces) —
capturing turn 2's exact API error and inspecting `get_final_message()` block
types/signatures/ordering on turn 1. For hole #2, capture the raw Gemma response
via a **raw `/api/chat`** call (bypassing the `/v1` compat shim that coerces tool
calls server-side) to see the true loose format, AND check whether
`supports_tools()` even offers tools to Gemma through the agent path — to
disambiguate "parser gap" from "tools never offered." Findings are written to the
flight log as each leg completes; confirmed root causes are promoted to the
mission.

### Checkpoints

- [ ] Anthropic thinking+tools failure reproduced on the **two-turn** exchange
      (thinking set, temperature removed), turn-2 error captured, replay vs.
      live-display capture-point question answered
- [ ] Gemma root cause disambiguated (capability-gate "tools never offered" vs.
      parser gap), raw loose-format response captured via `/api/chat` as evidence
- [ ] `any-llm` evaluated against holes #1/#2 with a recorded decision
- [ ] Synthesis: root causes promoted to mission, go/no-go emitted per downstream
      flight

### Adaptation Criteria

**Divert if**:
- The Anthropic failure does **not** reproduce, or reproduces from a trigger
  unrelated to dropped thinking blocks → hole #1 is wrong; pause and re-plan
  Flight 2's premise with the operator before any fix work.
- The Gemma failure is **not** a parser-coverage gap — in particular if the root
  cause is the `supports_tools()` capability gate ("tools never offered to Gemma")
  rather than the parser dropping a loose call → hole #2's framing is wrong;
  re-plan Flight 3's approach (and possibly its objective) with the operator
  before any fix work.
- The capture-point investigation shows a streaming refactor is unavoidable *and*
  far larger than the mission assumed → surface to the operator as a Flight 2
  scope/risk change before proceeding.

**Acceptable variations**:
- Exact model names used for reproduction (any extended-thinking Claude / any
  tool-capable Gemma the operator has).
- Whether hole #1 is reproduced through the full agent loop or via a direct
  provider call, as long as the streaming path is exercised.
- Minor scope-down of the `any-llm` read if the first hole it clearly can't solve
  settles the hand-roll decision early.

### Legs

> **Note:** Tentative suggestions, not commitments. Legs are planned one at a time
> as the flight progresses.

- [x] `anthropic-thinking-repro` - **Landed; hole #1 CORRECTED.** Thinking-replay accepted by Sonnet 4.6; the-one never enables thinking. Real Anthropic bug found via issue #122 (tool `input_schema` top-level `oneOf/allOf/anyOf`), reproduced live.
- [x] `ollama-gemma-repro` - **Landed; hole #2 CONFIRMED (#105).** Capability gate is correct (Ollama 400s if tools offered); fix is text-form recovery. Captured the real ` ```tool ` fenced-block format as Flight 3 fixture seed.
- [x] `any-llm-evaluation` - **Landed; decision HAND-ROLL.** any-llm fixes neither #122 nor #105 (drops top-level combinators; no text-form recovery); stacks a second abstraction for no fix.
- [x] `root-cause-synthesis` - **Landed.** Confirmed root causes promoted to mission; open questions resolved; flight plan reshaped (new high-priority #122 flight; thinking → separate lower-priority flight); go/no-go recorded.

---

## Post-Flight

### Completion Checklist

- [x] Both root-cause hypotheses confirmed or corrected with captured evidence
      (hole #1 falsified → #122 reproduced; hole #2 #105 confirmed)
- [x] Capture-point question answered (`get_final_message()` carries signed thinking
      blocks → replay-capture low-effort; only matters for the optional thinking flight)
- [x] `any-llm` decision recorded (hand-roll)
- [x] Raw Gemma loose-format response captured for Flight 3 (` ```tool ` fenced block)
- [x] Confirmed root causes promoted to mission Known Issues; Open Questions updated
- [x] Go/no-go recorded per downstream flight
- [x] No production source files modified (clean `git status` for `the_one/`)

### Verification

How to confirm the flight achieved its objective:
- The flight log contains, for each hole, a captured artifact (API error text /
  raw model response) proving the failure reproduces against current code — not
  just an assertion that it does.
- The mission's Known Issues and Open Questions reflect the confirmed findings.
- A reader can see a clear go/no-go for each of Flights 2–5, with the capture-point
  estimate-swing resolved for Flight 2.
- `git status` shows no changes under `the_one/` (spike is throwaway; only
  artifacts and the captured evidence file changed).
