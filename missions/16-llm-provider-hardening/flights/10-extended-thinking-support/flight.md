# Flight: Extended-Thinking / Reasoning Support (A1)

**Status**: in-flight
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria

- [ ] With extended thinking enabled on an Anthropic model, a single turn that both
      emits thinking **and** calls a tool completes without an API error, and the
      follow-up turn (carrying the tool result) also succeeds — i.e. thinking blocks
      + signatures are preserved and replayed.
- [ ] The `Message` protocol carries reasoning/thinking content as a first-class field
      (a `ThinkingPart`-equivalent) instead of discarding it; it round-trips through
      persistence and is available to the web UI.
- [ ] *(advances)* Each prioritized capability gap is either implemented behind the
      `LLMProvider` contract or explicitly deferred — this flight implements **A1**
      (the first ratified capability, per the F1B backlog) and explicitly defers the
      OpenAI/Ollama partial-reasoning surfaces + live thinking-delta streaming.

---

## Pre-Flight

### Objective

Give the `Message` protocol a first-class, structured thinking/reasoning representation
and wire it end-to-end on **Anthropic**: enable extended thinking on the request,
**capture** the signed thinking blocks the model returns, **replay** them (signatures
intact, correctly ordered before `tool_use`) so a thinking+tool turn *and* its follow-up
turn both complete without an API error, **persist** them through the codec, and
**surface** them in the web chat as a collapsed-by-default disclosure that survives a
chat reopen. The thinking field and codec are built **provider-agnostic** so Ollama/OpenAI
can populate them in a later flight; only the Anthropic adapter is wired here.

### Open Questions

- [x] **Thinking representation** — typed field vs. structured parts? → **Design Decision
      DD1** (structured list of thinking blocks; a bare `str` cannot carry the signature
      that replay requires). Resolved from the F1B OQ4 disposition + this flight's recon.
- [x] **Live streaming vs. store-and-reveal** → **DD2** (reveal-after; defer live deltas).
- [x] **UI display shape** → **DD3** (collapsible `<details>` disclosure).
- [x] **Enablement/config surface** → **DD4** (Studio admin budget field, num_ctx precedent).
- [x] **Scope beyond Anthropic** → **DD5** (Anthropic-first; protocol provider-agnostic;
      OpenAI/Ollama partial-reasoning + `reasoning_effort` knob are out of scope — the
      latter is backlog **A4**, a separate flight).
- [x] **Mixed thinking-on/off session replay** — replaying stored signed thinking onto a
      thinking-disabled request → **DD8** (strip-when-off, replay-when-on; verify the exact
      Anthropic tolerance live in Leg 03).
- [~] **Empirical premise (confirm live in Leg 02, before building capture):** with
      `thinking` enabled, does `stream.text_stream` still deliver the *answer* deltas, and
      does `stream.get_final_message()` carry the signed `ThinkingBlock`(s) whole? Design
      review judges this **well-founded, not a real risk** (the SDK's `text_stream` yields
      only text-block deltas; `get_final_message()` returns full content incl. signed
      blocks) — the probe is a cheap confirmation with a defined divert (below), not an open
      unknown.

### Design Decisions

**DD1 — Structured thinking representation on `Message` (not a bare `str`).**
- Choice: add a structured, ordered `thinking` carrier to `Message` — a list of blocks,
  each either `{type: "thinking", thinking: str, signature: str}` or
  `{type: "redacted_thinking", data: str}` (opaque; no text). Round-tripped through the
  codec exactly like `tool_calls` already is (`list` of dicts, emit-when-non-empty).
- Rationale: **Criterion #1 requires the follow-up turn to succeed**, and Anthropic
  *rejects* that turn unless the prior assistant turn's thinking blocks are replayed
  **with their signatures**. A `thinking: str` discards the signature and the
  `redacted_thinking` `data`, so it would fail the named criterion — it is not a valid
  lite option here. Display text is derivable from the structured blocks; the reverse is
  not. *(Design-review-confirmed against the installed `anthropic` SDK 0.79.0:
  `ThinkingBlock = {signature, thinking, type}`, `RedactedThinkingBlock = {data, type}` —
  DD1's shape matches exactly.)*
- **Modeled on `tool_calls`, NOT on the `emit-when-non-none` convention.** `thinking` is a
  `list` with a `field(default_factory=list)` default — a structural sibling of
  `tool_calls` (`base.py:68`, `codec.py:74`). The codec emits it with the **truthy guard**
  `if msg.thinking:` (like `tool_calls`), so it sits **outside** the
  `message-additive-back-compat-via-emit-when-non-none` convention (`agents.md:414–436`,
  which mandates `is not None` and would emit an always-non-`None` empty list
  unconditionally, breaking the byte-identity tripwire). No `n=N` citation bump in
  `agents.md`; state this explicitly in Leg 01.
- Trade-off: heavier codec than a scalar field (nested list), and a second structured
  list on `Message` alongside `tool_calls`. Accepted — it is the minimum shape that meets
  the criterion. Preserves the `Message.content`-is-always-`str` convention (this is a
  *new* field, not a widening of `content` — contrast A2; the `__post_init__` `str`-assert
  at `base.py:135–137` is untouched).

**DD2 — Capture-whole and reveal-after; defer live thinking-delta streaming.**
- Choice: v1 keeps `_stream_inner`'s `text_stream` + `get_final_message()` loop
  (`anthropic_provider.py:245–276`). The *answer* streams as today; the thinking blocks are
  read **whole** from `get_final_message()` at turn end and revealed then. No stream-loop
  rewrite.
- Rationale: `get_final_message()` already carries the signed blocks, so store + replay +
  display all work without touching the `_StreamAccumulator` usage heuristic. The F1B audit
  and the L04 code comment both flag live-delta streaming (raw `RawMessageStreamEvent`
  iteration) as the "harder, optional part." *(Design-review note: the SDK's `text_stream`
  yields only text-block deltas, so thinking cannot leak into the answer stream, and
  `get_final_message()` returns full content including signed `ThinkingBlock`s — the premise
  is well-founded; the Leg-02 live probe is belt-and-suspenders, not a real risk.)*
- **Thinking does NOT ride on `StreamChunk`.** Because capture is from the final message,
  thinking lands on the synthesized assistant `Message` (`anthropic_provider.py:276`), which
  the web layer already holds at both emit sites (`app.py:1392`, `:1558`) via
  `final_chunk.message` (`core.py:414–416`). No intermediate chunk carries thinking → **do
  not add a `StreamChunk.thinking` field** (it would be dead surface). Read
  `final_chunk.message.thinking`.
- Trade-off: the user sees thinking appear as a block after the answer, not token-by-token.
  Acceptable for v1; live streaming is a clean follow-on (capture/replay/codec are identical
  either way). **Recorded as an explicit deferral** (see Out of Scope).

**DD3 — Collapsible `<details>` disclosure per assistant turn.**
- Choice: render thinking as a collapsed-by-default `<details>` block above the answer,
  reusing the existing trace-shell disclosure idiom (`chat.css:149–208`) rather than the
  always-visible `.msg.thinking` bubble or a routing-audit-style modal overlay.
- Rationale: reasoning can be long and is secondary to the answer; the same disclosure
  idiom already renders tool traces, so it is consistent and low-novelty. Works identically
  live (revealed on `done`) and on history replay.
- Trade-off: one extra click to read reasoning. Accepted (that is the point — keep the
  transcript clean).

> **★ PIVOT (operator, 2026-07-02) — DD4 + DD6 enablement SUPERSEDED.** Design review + Anthropic's
> authoritative docs confirmed the `budget_tokens` wire format below **400s on Sonnet 4.6 and all
> current models** (works only on pre-4.6). Operator decision: support thinking on **Sonnet 4.6+
> only → adaptive-only enablement** (`thinking: {"type": "adaptive"}`); **drop `budget_tokens`**;
> **on/off** control (no token budget); **`effort` deferred to A4**. This evaporates DD6's
> `temperature=1`-force + `max_tokens`-raise, and flips the config surface to
> `config["thinking_enabled"]` (bool). New **Leg 03 `anthropic-adaptive-enablement`** implements
> the revised enablement; the DD4/DD6 bodies below are retained as the pre-pivot design record.
> See flight-log → Decisions "PIVOT — adaptive-only enablement" + Anomalies. DD1/DD2/DD3/DD5/DD7/DD8
> are unaffected.

**DD4 — Enablement via a Studio admin "Extended thinking budget" field (num_ctx precedent).**
- Choice: an editable budget field on the Anthropic provider config, precedence
  **per-provider `config` value → `THE_ONE_ANTHROPIC_THINKING_BUDGET` env → default
  (`0` = disabled; default budget when enabled: `4096`)**, where `0`/blank = disabled.
  Config already reaches the adapter (`factory.py:276` passes `provider_config.config`;
  today swallowed by `**kwargs`). Mirrors the F09-05 `num_ctx` field end-to-end (backend
  effective-value resolver in Leg 02; the admin UI field in Leg 05).
- Rationale: consistent with the most recent provider-config work the operator already
  vetted (F09-05); keeps enablement operator-controllable without a code change; the split
  (backend resolver first, UI field second) keeps Leg 02 independently testable via env.
- Trade-off: per-**provider**, not per-**model** (a provider serves many models; only some
  support thinking). Same shape-limitation the F09-05 `num_ctx` field carries; per-model
  config is already a recorded compaction-mission surface. Operator's responsibility to
  point a thinking-budget provider at a thinking-capable model; a non-supporting model
  surfaces as an API error named to the provider — **Leg 02 verifies that error path is
  non-fatal** (renders an error bubble, session survives, does not wedge the turn).
- **Consequence — the connector inference-decision fast path must suppress thinking.**
  `_inference.py:322–330` calls `complete(..., temperature=0.0, max_tokens=10)` as a cheap
  "should I engage?" classifier. A per-provider budget (≥1024) would force thinking onto
  *that* call, where `max_tokens=10 ≪ budget` — wasteful and DD6-tripping. Leg 02 suppresses
  thinking on this path (an explicit "no thinking" signal on that `complete()` call), so the
  budget governs only real chat turns.

**DD5 — Anthropic-first; protocol provider-agnostic; OpenAI/Ollama deferred.**
- Choice: the `Message` thinking field, codec, agent-loop threading, and web UI are
  provider-neutral; only `anthropic_provider.py` populates/replays them this flight.
- Rationale: A1 is "Anthropic full"; OpenAI Chat surfaces only a `reasoning_tokens` count
  (no replayable block) and Ollama's native `think`/`message.thinking` is off the `/v1`
  path the-one uses — both are *partial* and out of A1's named-criterion scope. Building the
  contract neutrally means those adapters can populate it later with no protocol change.
- Trade-off: Ollama/OpenAI users see no thinking this flight. Accepted and recorded.

**DD6 — Anthropic request constraints are enforced, not surprises.**
- When thinking is enabled the adapter **forces `temperature = 1`** (the API rejects any
  other value with thinking on) and ensures `budget_tokens ≥ 1024`.
- **`max_tokens` is raised, not clamped:** the answer needs headroom *above* the thinking
  budget, so when `max_tokens ≤ budget` the adapter raises `max_tokens` to
  `budget + answer-headroom` rather than shrinking the operator's budget. (Neither
  `core.py` nor `_inference.py` passes `max_tokens` explicitly — the turn defaults to
  `16384` at `base.py:318`; raising is only needed for large budgets or the tiny
  inference-path `max_tokens`, which is anyway thinking-suppressed per DD4.)
- **Single enforcement site:** the agent loop does **not** pass temperature
  (`core.py` calls `stream(messages=, tools=)` → provider default `0.0`); `_inference.py`
  passes `0.0` explicitly. So forcing `temperature=1` inside `_build_kwargs` is the *only*
  reconciliation site — no loop-level change. Note in Leg 02 that the existing
  temperature-retry (`anthropic_provider.py:175–187`, `:233–243`) is **benign** under
  thinking (popping temperature falls back to Anthropic's thinking default of 1) so a future
  reader doesn't "fix" it.
- All encoded in Leg 02 with unit coverage, not left to runtime discovery.

**DD8 — Thinking replay is gated on the OUTGOING request's thinking state.**
- Choice: `_to_api_message` replays stored thinking blocks (signatures intact, before
  `tool_use`) **only when thinking is enabled on the current outgoing request**; when
  thinking is disabled, stored thinking blocks are **stripped** from the replayed history.
- Rationale: an operator can disable the budget mid-session (or run the budget-0 variant in a
  chat that already accumulated thinking turns), producing a request with thinking OFF but a
  history full of signed thinking blocks. Signed blocks are only meaningful/validated while
  thinking is active; replaying them onto a thinking-off request risks a signature-validation
  400. Stripping-when-off is deterministic and safe. Within a single thinking-ON tool loop,
  the follow-up request still has thinking ON, so criterion #1's blocks *are* replayed —
  unaffected.
- **Verify live in Leg 03:** confirm Anthropic's actual tolerance (does an off-request 400 on
  stored thinking, or silently ignore?) and encode the real contract. The behavior test gains
  a mixed-session variant (accumulate thinking turns → set budget 0 → continue → no error).
- Trade-off: a small conditional in the replay projection keyed on the request's thinking
  state. Accepted — it is the correct multi-turn contract.

**DD7 — Behavior-test apparatus (both axes audited).**
- **Act path:** the installed/dev web chat driven over the WebSocket (via chrome-devtools
  MCP: navigate → select a thinking-budget Anthropic agent → send a prompt that induces a
  tool call). This is exactly how a real operator exercises it.
- **Observe path (all assertions read existing surfaces — no test-only seam):**
  (a) *no API error across the tool round-trip* → the turn settles with an answer bubble and
  a `done` event, no error bubble (DOM + WS `done`); the tool round-trip **is** the
  follow-up turn, so its success is the direct witness that signed thinking was replayed;
  (b) *thinking visible* → the `<details>` disclosure with reasoning text in the DOM;
  (c) *persistence* → after a chat reopen/reload, the disclosure is still present (history
  replay via `messages_to_ui_events`), and the block is durable in `session` history.
- Both premises are static/verifiable now; no reactive seam expected.

### Prerequisites

- [ ] **Anthropic API key** present in the credential store and an **extended-thinking-capable
      model** selectable (e.g. a current Claude Sonnet/Opus). Verified before the behavior
      test / HAT leg.
- [ ] **Empirical premise probe (Leg 02, gating capture):** confirm live that with thinking
      enabled, `text_stream` yields answer deltas and `get_final_message()` carries signed
      thinking block(s). If falsified, Leg 02 diverts to raw-event capture (see Adaptation).
- [ ] **Dev instance / installed app** reachable for HAT (dev-instance on `:8485` per the
      F09 loop; installed app on `:8484`).
- [ ] Full test suite green at flight start (F09 landed at `3609` passing / `10` skips;
      **note the carried aiosqlite teardown flake** — if it fires on a flight run, it is the
      known cross-test event-loop teardown issue, not an A1 regression).

### Pre-Flight Checklist

- [x] All open questions resolved (one empirical premise confirmed live in Leg 02 by design,
      with an adaptation branch)
- [x] Design decisions documented (DD1–DD8)
- [x] Prerequisites verified (satisfiable — Anthropic key + thinking-capable model
      configurable today; live probes scheduled in Leg 02/behavior-test)
- [x] Validation approach defined (fixtured unit tests + live behavior test + optional HAT)
- [x] Legs defined (6, tentative; authored one at a time at execution)
- [x] Design review passed (Architect: approve with changes; all applied — see flight log)

---

## In-Flight

### Technical Approach

Build the capability bottom-up so each leg is independently testable:

1. **Protocol + codec foundation (Leg 01).** Add the structured `thinking` list field to
   `Message` (`base.py:65–119`), modeled on `tool_calls` (`field(default_factory=list)`,
   **truthy emit guard**) — **not** a `StreamChunk` field (DD2: capture is from the final
   message, so no chunk carries thinking). Emit/read it in the codec
   (`message_to_dict:71–102` / `message_from_dict:105–141`) with `if msg.thinking:` on emit
   and `d.get("thinking", [])` on read (template: `tool_calls` at `codec.py:74`, NOT the
   `metadata` `is not None` guard). The byte-identity tripwire (`test_db_codec.py:655–676`)
   **stays green unchanged** — an empty list isn't emitted; *verify* it, don't edit it. Add a
   `thinking` round-trip + back-compat test (mirror `TestMessagePeerNameCodec:479–534`).
   Provider-agnostic; nothing enables thinking yet.

2. **Anthropic capture + enablement (Leg 02).** Add budget resolution (config → env →
   default `4096`; `0`/blank off) and set `kwargs["thinking"]` in `_build_kwargs:115–157`,
   forcing `temperature=1` and **raising** `max_tokens` to clear the budget (DD6). Capture
   `thinking` / `redacted_thinking` blocks in both `complete()` (`191–195`, the Discord path
   too) and the streaming `get_final_message()` path (`263–276`) into `Message.thinking`.
   **Suppress thinking on the `_inference.py:322–330` decision fast path** (DD4). Confirm the
   empirical premise live first; **verify a non-thinking-model error is non-fatal**. Fixtured
   tests from a recorded thinking response.

3. **Anthropic replay (Leg 03).** In `_to_api_message:296–323`, emit stored thinking blocks
   **before** the `text`/`tool_use` blocks in the assistant turn, signatures intact, so the
   follow-up (tool-result-carrying) request is accepted — **gated on the outgoing request's
   thinking state (DD8: strip-when-off)**. This is the leg that makes criterion #1's second
   turn pass. Verify Anthropic's mixed-session tolerance live. Fixtured/conformance
   projection test (both thinking-on replay and thinking-off strip).

4. **Web UI disclosure (Leg 04).** Add a thinking event/envelope on the WS turn + project it
   in `messages_to_ui_events` (history) (`app.py:53,979`); render the collapsible `<details>`
   in `chat.js` (live finalize near `finalizeStreamingBubble` def at `:586`; history branch
   in `renderHistory:358–424`); style in `chat.css`. **Use distinct identifiers** — the
   existing `.msg.thinking` / `createThinking` / `removeThinking` (`chat.css:444`,
   `chat.js:602/608`) are the ACTIVE ephemeral "thinking…" loading indicator, not free names.
   Respect the F09-07 cache-busting invariant (versioned static refs + `no-store`).

5. **Config admin field (Leg 05).** The "Extended thinking budget" field on the Anthropic
   provider editor — `api.py` + `admin/provider-editor.js` + `admin.js` — mirroring the
   F09-05 `num_ctx` field (label, ⓘ tooltip, `0`/blank = off, default shown). Config-touching
   → run the browser provider-editor suite.

6. **Verify + behavior test + HAT (Leg 06).** Author (drafted below) and run the
   `extended-thinking-tool-turn` behavior test on live Anthropic; run the optional guided HAT;
   full suite; doc updates (thinking field convention in `agents.md`; the cache-busting
   invariant carry from F09 if not already documented).

### Checkpoints

- [ ] `Message.thinking` round-trips the codec; legacy rows decode unchanged (tripwire green)
- [ ] Empirical premise reconfirmed live (or adaptation taken) — Leg 02
- [ ] A thinking+tool turn on live Anthropic completes **and** its follow-up turn completes
      (no API error) — the core criterion
- [ ] Thinking renders as a collapsed `<details>` and survives a chat reopen
- [ ] "Extended thinking budget" editable in Studio; `0`/blank disables
- [ ] `extended-thinking-tool-turn` behavior test PASS; full suite green

### Adaptation Criteria

**Divert if**:
- The Leg 02 premise probe shows `get_final_message()` does **not** carry signed thinking on
  the streaming path with thinking enabled → capture must move to raw-event iteration
  (`RawMessageStreamEvent`), pulling the deferred DD2 stream-refactor forward into scope.
  Log the divert + rationale; re-estimate. *(Low-probability per design review — the SDK
  contract makes this well-founded; the probe is confirmation, not a coin-flip.)*
- Anthropic's thinking+tool replay contract differs from the documented "thinking before
  tool_use, signatures intact" (e.g. an unanticipated ordering/interleave rule surfaces
  live) → re-scope Leg 03 and record the real contract in the flight log.

**Acceptable variations**:
- Folding the Leg 05 admin field into Leg 02 if the UI turns out trivial (keep the browser
  suite run either way).
- Adjusting the `<details>` styling / collapsed-default per HAT feedback (DD3 UX is
  operator-tunable in Leg 06).
- Choosing the exact default budget value during Leg 02/05.

### Legs

> **Note:** Tentative; planned and created one at a time as the flight progresses.
> **Reshaped by the 2026-07-02 adaptive pivot (see the DD4/DD6 banner + flight-log):** 6→7 legs.
> Legs 01–02 landed (Leg 02's *capture* + `enable_thinking` contract retained; its *budget*
> enablement superseded by the new Leg 03). Original 5-leg list annotated inline below.

- [x] `thinking-message-protocol` (**Leg 01, landed**) — structured `thinking` **list** field on
      `Message` (modeled on `tool_calls`, truthy emit guard — **no `StreamChunk` field**); codec
      round-trip; tripwire stays green; round-trip + back-compat tests. Provider-agnostic. *(S–M)*
- [x] `anthropic-thinking-capture` (**Leg 02, landed**) — capture signed
      `thinking`/`redacted_thinking` from `complete()` + `get_final_message()`; **suppress on the
      `_inference` fast path** (`enable_thinking` contract); fixtured tests. *(M)* **Note:** its
      `budget_tokens` enablement + `thinking_budget` config are **superseded by Leg 03** (adaptive
      pivot); capture + the contract are correct and retained.
- [x] `anthropic-adaptive-enablement` (**Leg 03, NEW — pivot**) — replace the `budget_tokens`
      enablement with **adaptive-only** (`thinking: {"type": "adaptive"}`, Sonnet 4.6+); rip out
      the budget resolver → a `thinking_enabled` **boolean** resolver
      (`config["thinking_enabled"]` → env `THE_ONE_ANTHROPIC_EXTENDED_THINKING` → default off);
      drop DD6's `temperature=1`-force + `max_tokens`-raise; keep `enable_thinking` suppression;
      update Leg 02's enablement tests. *(S–M)*
- [x] `anthropic-thinking-replay` (**Leg 04**) — `_to_api_message` emits thinking blocks before
      `text`/`tool_use`, signatures intact, **gated on outgoing thinking state (DD8:
      strip-when-off)**; follow-up turn accepted; projection tests (on + off). Design-approved;
      hoist derives `thinking_active` from the Leg-03 `thinking_enabled` resolver. *(M)*
- [x] `web-ui-thinking-disclosure` (**Leg 05**) — WS thinking envelope + `messages_to_ui_events`
      history projection + `chat.js` collapsible `<details>` (live + replay, **distinct
      identifiers**, not the `.msg.thinking` loading indicator) + `chat.css`; cache-bust invariant
      respected. Unaffected by the pivot. *(M)*
- [x] `thinking-enable-admin-field` (**Leg 06** — was `thinking-budget-admin-field`) — Studio
      Anthropic provider-editor **on/off "Extended thinking"** toggle (writes
      `config["thinking_enabled"]`), default off — NOT a budget number (pivot); api.py +
      provider-editor.js + admin.js; browser provider-editor suite. *(S–M)*
- [ ] `verify-and-hat` (**Leg 07**) *(optional guided HAT included)* — run the
      `extended-thinking-tool-turn` behavior test on live Anthropic (adaptive mode); guided HAT
      session (tune disclosure/enable UX, fix inline); full suite; doc updates. *(M)*

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (fixtured unit + browser provider-editor + behavior test)
- [ ] Documentation updated (thinking-field convention in `the_one/agents.md`; behavior-test
      spec active)
- [ ] Mission success criteria #1 (thinking+tool turn) and the `ThinkingPart` criterion
      checked off; A1 marked implemented in the F1B backlog

### Verification

- **Unit (hermetic):** codec round-trip + back-compat tripwire (`test_db_codec.py`);
  Anthropic capture + enablement (fixtured thinking response); replay projection ordering.
- **Browser:** provider-editor flow with the new budget field (`test_flow_provider_editor.py`
  or equivalent).
- **Behavior test (live):** `/behavior-test extended-thinking-tool-turn` — a thinking+tool
  round-trip on a real Anthropic model completes with no API error, the thinking disclosure
  renders, and it survives a chat reopen. Spec: [`tests/behavior/extended-thinking-tool-turn.md`](../../../../tests/behavior/extended-thinking-tool-turn.md).
- **HAT (optional, Leg 06):** guided live session tuning the disclosure/budget UX.
