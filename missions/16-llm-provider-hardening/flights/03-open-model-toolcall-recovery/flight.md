# Flight: Open-Model Tool-Use Robustness — Text-Form Tool-Call Recovery (#105)

**Status**: completed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
- [ ] A tool-using conversation with **Gemma via Ollama** reliably executes tool calls,
      **including** when the model emits the call as text/JSON in `content` rather than a
      structured `tool_calls` array. *(#105; test-backed with a recorded/fixtured Gemma
      response for the loose-format case)*
- [ ] No agent framework is added and the provider layer still wraps official SDKs / the
      OpenAI-compatible endpoint; the `LLMProvider` contract and the provider-shape-
      portability convention are preserved. *(trivially preserved — change is confined to
      the Ollama adapter + one new pure helper module under `the_one/llm/`)*

---

## Pre-Flight

### Objective

Make an open/local model that emits tool calls as **loose text** (rather than the
structured `tool_calls` array) actually execute those tools. The reproduced trigger
(Flight 1 spike, live gemma3:4b) is a ` ```tool ` fenced block carrying **Python-call
syntax** — `get_weather(city='Paris')` — with `tool_calls: null`. Today
`OllamaProvider` parses only the structured `tool_calls` field
(`ollama_provider.py:117-129` for `complete`, `:197-228` for `stream`), so the call flows
through as visible `content` and no tool runs (#105).

The fix is a **pure, deterministic text-form tool-call recovery parser** wired into the
Ollama adapter: when the structured `tool_calls` field is empty **and** the content carries
a recognizable tool-call form, recover the call(s) into structured `ToolCall`s, strip the
recognized block from the rendered content, and let the **existing** agent loop dispatch
them. The change is confined to `the_one/llm/` (the Ollama adapter + one new pure helper);
the `Message`/`LLMProvider` contract, the other adapters, the MCP layer, **and the agent
loop** are untouched.

### Background (why this is the right shape, and where the boundary is)

Issue #105 combines two mechanisms (root-cause analysis confirmed against current code):

1. **The capability gate is CORRECT and stays.** `OllamaProvider.supports_tools()` returns
   `False` when Ollama's `/api/show` capabilities don't advertise `"tools"` (Gemma variants)
   — `ollama_provider.py:71-79`. The Flight 1 spike confirmed live that **Ollama 400s if
   tools are offered** to gemma3:4b (`does not support tools`). So the fix is **not** to
   offer tools to non-tool-capable models — it is to **recover** the text-form call the
   model emits anyway.

2. **The agent loop already dispatches recovered calls — no loop change needed.**
   `Agent._run_iterations` (`the_one/agent/core.py:177-238`) resolves `supports_tools` once
   and uses it **only** to decide whether schemas go on the wire (`:185-188`). The tool
   dispatch — `if not response.tool_calls: return` then
   `_dispatch_tool_calls(response.tool_calls)` (`:225-235`) — runs **unconditionally** of
   `supports_tools`. **Therefore a provider that populates `response.tool_calls` from
   recovered text is dispatched even in degraded mode.** This is the key finding that keeps
   the flight inside the mission's "agent loop untouched" boundary. *(Verified at planning;
   see Design Decision DD6.)*

The remaining real risk is the **degraded follow-up round-trip** (DD5): after a recovered
call is dispatched and a `ToolResult` is appended, the next turn serializes the assistant
message's `tool_calls` + a `role:"tool"` result (`ollama_provider.py:240-261`) and sends
them to gemma3:4b **with `tools=None`**. It is unverified whether Ollama 400s on tool-call /
tool-role *history* for a non-tool-capable model (the spike only proved it 400s when tools
are *offered*). This is resolved empirically in `leg 03` with a pre-authorized adaptation.

### Open Questions
- [ ] **Degraded round-trip serialization (DD5).** Does Ollama/gemma3:4b reject a follow-up
      request whose message history contains an assistant `tool_calls` block and a
      `role:"tool"` message when `tools` is omitted (the non-tool-capable path)? Resolve
      empirically in `leg 03` against live gemma3:4b. **Likely outcome unknown** — pre-
      authorize the adaptation: if it rejects, serialize the degraded round-trip as plain
      text (assistant `content` describing the call; tool result fed as a `user`/`system`
      message) in `_to_api_message`'s degraded path, instead of the structured
      `tool_calls`/`tool` shape. A divert criterion covers an unexpected third shape.
- [x] **Recovery trigger** → provider-stateless, high-precision (see DD2).
- [x] **Format coverage** → all three (gemma fenced Python-call + Hermes + bare-JSON), gemma
      first-class (see DD3). *(operator-ratified)*
- [x] **Agent-loop change needed?** → **No** — loop dispatches `response.tool_calls`
      unconditionally (DD6, verified `core.py:225-235`).
- [x] **Verification depth** → fixtured units (mandatory) + live gemma marker test +
      behavior test (see Verification). *(operator-ratified)*

### Design Decisions

**DD1 — Recovery is a pure, leaf kernel** (mirrors Flight 2's `_schema_sanitize.py` and the
`_streaming.py` convention): add `the_one/llm/_toolcall_recovery.py` as a pure, **stdlib-only**
(`ast`, `json`, `re`) module. Signature `recover_tool_calls(content: str) -> list[dict]`
returning recovered calls as plain dicts `{"name": str, "arguments": dict}` (no `the_one.llm`
import → the provider maps them to `ToolCall`, synthesizing ids per DD4). Returns `[]` on no
match.
- Rationale: testability/isolation (exhaustive unit tests without a provider or network);
  consistency with the Flight 2 precedent; the format zoo (gemma/Hermes/JSON) is parsing
  logic that deserves isolation from adapter I/O. Other OpenAI-compatible local backends
  (LM Studio, vLLM, llama.cpp via `OllamaProvider`) can emit the same loose forms, so the
  kernel is reusable across them even though only Ollama wires it today.
- Trade-off: one new module vs. an inline adapter method. Isolation/testability win, same as F2.

**DD2 — Recovery trigger is provider-stateless and high-precision**: the adapter calls the
kernel **only when** the structured `tool_calls` field is empty/absent. The kernel itself
only returns a call when a **high-precision marker** is present (a ` ```tool `/` ```json `
fenced block, a Hermes `<tool_call>…</tool_call>` tag, or a content that *is* a tool-call-
shaped JSON object) — never from free prose. Recovery is **not** gated on
`supports_tools()` (the provider's `complete()`/`stream()` don't resolve it, and a tool-
capable model that *occasionally* drops to text-form should also be recovered).
- Rationale: the high-precision markers bound false positives without needing capability
  state; keeping the kernel stateless preserves its purity (DD1).
- Trade-off: a model that prints a tool-call-shaped block as *intentional* output (rare;
  e.g. a code example) would be misrecovered. Mitigated by marker precision + the
  agent-loop's graceful handling of an unknown tool name (the registry returns an error
  `ToolResult`, not a crash). The bare-JSON recognizer is the riskiest and is gated tightest
  (whole-content, exact `{"name","arguments"}`/`{"tool"/"function"}` shape).

**DD3 — Three formats, gemma first-class**:
| Form | Recognizer | Arg parsing |
|---|---|---|
| ` ```tool ` fenced **Python-call** (gemma3:4b — the reproduced primary fixture) | fenced block tagged `tool` (also accept untagged/` ```python ` containing a single call) | `ast.parse(mode="eval")` → `Call`; func = `Name.id` (or dotted `Attribute`); **keyword args** via `ast.literal_eval` (first-class). **Positional args** (rare; built-ins/MCP expect named args and the provider has no schema to name them) are **carried under `arguments["__positional_args__"] = [...]`** — never silently dropped — and a WARN is logged; this is a recorded known limitation. NEVER `eval` — `ast` only (parse + `literal_eval` execute no code). |
| Hermes `<tool_call>{json}</tool_call>` tag(s) | regex tag extraction | `json.loads` the inner object `{"name","arguments"}` |
| Bare-JSON tool-call object | content that *is* a JSON object of tool-call shape | `json.loads`; accept `{"name","arguments"}` and `{"type":"function","function":{…}}`/`{"tool",…}` shapes |
- Multiple recovered calls in one message are supported (a list).
- Rationale: gemma is the actual reproduced bug (exhaustively fixtured from the spike
  capture); Hermes + bare-JSON cover the common local-model idioms the mission backlog names,
  for the same parsing cost in one cohesive kernel.

**DD4 — On recovery, strip the recognized block from content + synthesize stable ids**: when a
call is recovered, remove the recognized block from the `content` the adapter returns, so the
raw call syntax is **not** also rendered to the user (addresses #105's "suppress raw text"
direction). Synthesize a deterministic id (`f"{name}_{index}"` or a short hash) so the
dispatched `ToolResult.tool_call_id` has a stable match. If stripping leaves only whitespace,
content becomes `""`.
- Rationale: a recovered call rendered AND executed would double-surface; the model's
  surrounding prose (if any) is preserved, only the call block is removed.

**DD5 — Degraded round-trip serialization, empirically pinned (`leg 03`)**: see Open
Questions. The provider must produce a follow-up request that a non-tool-capable model
accepts. `leg 03` probes live; if the structured `tool_calls`/`tool`-role history is
rejected, `_to_api_message`'s degraded path is adapted to a plain-text round-trip. This is
**provider-local** (`ollama_provider.py`), so it stays in mission scope.
- **Both `_to_api_message` branches change in the plain-text adaptation** (architect note):
  (1) the **assistant message with `tool_calls`** (`:246-261`) → emit the call as inline
  text in `content` (e.g. `\n[called {name}({args})]`) with **no** structured `tool_calls`
  key; and (2) the **`role:"tool"` result message** (`:240-245`) → re-serialize as
  `role:"user"` (or `system`) carrying the result in prose (e.g. `[tool result for {name}:
  {content}]`), since a non-tool-capable turn has no `tool_call_id` to anchor a `tool` role.
  The exact prose shape is an acceptable variation; `leg 03` picks one and pins it with a
  hermetic test. The synthesized id (DD4) is irrelevant in this fallback (no `tool_call_id`
  on the wire); it still matters for the in-process `ToolCall.id → ToolResult.tool_call_id`
  linkage the agent loop uses.
- **Gate the adaptation on the degraded path only** (`supports_tools`-False turns). Tool-
  capable Ollama models keep the structured round-trip unchanged. Since `_to_api_message`
  is stateless about capability, `leg 03` decides the gating signal (e.g. presence of the
  recovered-call marker on the prior assistant message, or a per-call flag) — pin it there.
- Trade-off: a text round-trip loses the structured tool-call linkage on the wire, but the
  model is non-tool-capable anyway — it only needs to *see* the result to continue.

**DD5a — No artificial cap on recoveries per turn** (architect Q): recovery may fire on each
iteration that lacks structured `tool_calls` but carries a marker (e.g. the model emits a
second text-form call after seeing the first result). This is intended — the natural loop
iteration handles it, bounded by `_remaining_iterations`. A multi-call *single* response is
returned as an ordered list by the kernel (DD3) and dispatched in order by
`_dispatch_tool_calls`. No per-`step()` recovery cap.

**DD6 — Agent loop is NOT modified**: verified that `_run_iterations` dispatches
`response.tool_calls` unconditionally (`core.py:225-235`); `supports_tools` gates only the
wire `tools=` array. Recovering into `tool_calls` is sufficient. Recorded as a verifiable
boundary (the mission forbids agent-loop iteration changes).

**DD7 — Verification apparatus** (behavior test, both axes): the end-to-end behavior test
drives the **running the-one agent** via `POST /api/chat` (apparatus: shell/http, per the
existing `tests/test_aiat.py` live harness) against a gemma3:4b-backed Ollama agent, and
**observes** via the `/api/chat` response body + session message history that (a) the tool
actually executed (the result is reflected) and (b) the raw ` ```tool ` block is **not** the
final assistant text. Both the act path (`/api/chat`) and the read path (chat response /
session history) are existing HTTP surfaces — no test-only seam needed. The provider-level
live marker test drives `OllamaProvider` directly against local gemma3:4b.

### Prerequisites
- [ ] Local Ollama reachable with **gemma3:4b** pulled (the spike's environment; the live
      marker test + behavior test self-skip when absent). Verify reachability at flight start.
- [ ] The captured Flight 1 fixture (` ```tool\nget_weather(city='Paris')\n``` ` with
      `tool_calls: null`) transcribed verbatim into the parser's test fixtures (source:
      `flights/01-recon-root-cause-spike/legs/02-ollama-gemma-repro.md` + flight log).
- [ ] For the behavior test: a runnable the-one instance (`/api/chat` at the configured URL,
      default `:8484`) with an agent configured for the Ollama gemma3:4b provider. Probe the
      apparatus before the behavior leg runs.
- [ ] `make test` stays hermetic: live + behavior verification behind `@pytest.mark.live` /
      the `/behavior-test` skill, deselected by default.

### Pre-Flight Checklist
- [x] All open questions resolved — except DD5's degraded-round-trip question, deliberately
      deferred into `leg 03` to resolve empirically (a divert criterion covers the surprise case)
- [x] Design decisions documented (DD1–DD7, DD5a)
- [x] Prerequisites identified; the captured fixture is available; live Ollama+gemma3:4b
      reachability + a runnable app are verified at **flight start** (live/behavior tests
      self-skip when absent, so default `make test` stays hermetic)
- [x] Validation approach defined (hermetic units + `@pytest.mark.live` + a behavior test)
- [x] Legs defined (5 + optional HAT)

---

## In-Flight

### Technical Approach

A pure recovery kernel (`_toolcall_recovery.py`, DD1–DD3) is built and exhaustively unit-
tested first, in isolation. It is then wired into `OllamaProvider.complete()` and `stream()`
(DD2/DD4): when no structured `tool_calls` are present, run the kernel on the accumulated
content, map any recovered calls to `ToolCall`s (synthesized ids), strip the recognized
block from the returned content, and return them on the `Message` — which the existing agent
loop dispatches (DD6). The degraded follow-up round-trip is then probed live and, if
necessary, the `_to_api_message` degraded path is adapted (`leg 03`, DD5). Finally a
`@pytest.mark.live` test confirms recovery against **real** gemma3:4b output, and a behavior
test confirms the full agent loop executes the tool end-to-end with no raw call text shown.

### Checkpoints
- [ ] Recovery kernel + unit suite green (gemma fenced Python-call fixture, Hermes, bare-JSON,
      multi-call, no-false-positive-on-prose, positional best-effort)
- [ ] Ollama adapter recovers in `complete()` + `stream()`; content-strip; synthesized ids
- [x] Degraded round-trip question resolved (round-trips cleanly — gemma3:4b accepts the
      structured tool-history with `tools` omitted; no `_to_api_message` change, contract pinned)
- [ ] `@pytest.mark.live` test confirms recovery against real gemma3:4b
- [ ] Behavior test passes: real gemma turn executes the tool; no raw ` ```tool ` block shown

### Adaptation Criteria

**Divert if**:
- The degraded round-trip needs a serialization shape neither structured-tool-history nor the
  pre-authorized plain-text fallback handles (re-scope DD5).
- Live gemma3:4b emits a text-form shape materially different from the captured fenced
  Python-call (e.g. a new wrapper) — extend DD3's recognizers and re-fixture.

**Acceptable variations**:
- Exact module/function names; the regexes/markers for each recognizer.
- Whether positional-arg recovery is supported or recorded as a known limitation.
- Whether the live marker test asserts at the provider level, the `/api/chat` level, or both.

### Legs

- [x] `toolcall-recovery-kernel` — new pure, stdlib-only `the_one/llm/_toolcall_recovery.py`
      (DD1–DD3): `recover_tool_calls(content) -> list[dict]` handling the gemma ` ```tool `
      fenced Python-call (ast-based, kwargs first-class), Hermes `<tool_call>` tags, and bare-
      JSON tool-call objects; high-precision (no recovery from prose); multi-call; `[]` on no
      match. Exhaustive unit tests incl. the captured gemma fixture, each format, multi-call,
      positional best-effort, and no-false-positive cases.
- [x] `wire-into-ollama-adapter` — call the kernel when structured `tool_calls` is empty; map
      recovered dicts → `ToolCall` with synthesized ids (DD4); strip the recognized block from
      returned `content`. **Insertion points (explicit):** in `complete()` after the structured
      parse at `:117-129` and before the `Message.assistant(...)` at `:139`; in `stream()`
      **after `acc.finalize_tool_calls()` (`:225-228`) and before the final `Message.assistant`
      (`:230`)** — NOT inside the streaming loop (content is still accumulating there). Tests use
      the `httpx.MockTransport` pattern from `tests/test_ollama_provider_auth.py` (the
      `/api/show` resolver fires first) for both `complete` and the streamed path; assert
      recovered `tool_calls`, stripped content, a clean structured response is unaffected, and
      **pin the `ToolCall.id` synthesized here so it round-trips to `ToolResult.tool_call_id`**
      (the loop preserves it via `core.py:331-336`).
- [x] `degraded-roundtrip-probe` — empirically resolved DD5 against live gemma3:4b: a follow-up
      with assistant-`tool_calls` + `role:"tool"` history and `tools` omitted is **ACCEPTED (2xx,
      model replied)** — round-trips cleanly, **no production code change**. No adaptation needed;
      the structured `_to_api_message` serialization is pinned by a hermetic test
      (`tests/test_ollama_degraded_roundtrip.py`). Probe was throwaway in `/tmp` (not committed);
      finding recorded in the flight log (Decisions "DD5 resolved LIVE" + Leg Progress).
- [x] `live-verify-gemma` — `@pytest.mark.live` test (deselected by `make test`): drive
      `OllamaProvider("gemma3:4b")` against local Ollama with a tool-eliciting prompt and assert
      the returned `Message` carries a **recovered** `ToolCall` **and** that `Message.content`
      no longer contains a raw ` ```tool ` block (recovery fired AND the strip happened, DD4).
      Proves the kernel handles real model output, not just the captured fixture. Self-skips
      when Ollama/gemma3:4b is absent.
- [x] `behavior-test-gemma-tool-use` — author (if not already) and **run** the behavior test
      `tests/behavior/gemma-tool-use-recovery.md` via `/behavior-test gemma-tool-use-recovery`:
      end-to-end through the running agent (`/api/chat`), a gemma turn that should call a
      built-in tool **executes** it and the final answer reflects the tool output, with **no**
      raw ` ```tool ` block rendered. Run log committed; a failing test blocks the leg.
- [x] `docker-removal-host-native` *(added mid-flight — operator-directed DIVERSION, 2026-06-18)* —
      rip out all stale **deployment**-Docker scaffolding (`Dockerfile`, `docker-compose.yml`,
      `.dockerignore`, the Makefile container-lifecycle targets, the crew `docker exec` prompt line,
      and Docker-as-deployment prose in `CLAUDE.md` / `SECURITY-MODEL.md` / `tests/HAT.md` / two
      `scripts/`) and replace each with its host-native equivalent (`the-one serve`, host data-dir
      reset, host log tail, etc.). Docker was retired for the Windows installer a prior mission but
      the scaffold lingered and misled execution. **Preserve** tool-sandbox-Docker references and
      historical artifacts. See flight-log Deviations + leg 06. Executes **before** the behavior test.
- [x] `gemma-toolcode-positional-fix` *(added after leg-05 behavior test failed; operator: "fix both")* —
      add `tool_code` to the recovery kernel's recognized fences + schema-aware positional→named arg
      binding (`Tool.bind_positional_args`) applied via a one-line `_execute_tool` change. Code landed;
      the behavior-test re-run still failed (gemma format variability) → led to leg 08.
- [x] `degraded-model-direct-tool-protocol` *(DURABLE FIX — operator-directed MISSION-scope expansion
      into `the_one/agent/`, 2026-06-19)* — for `supports_tools()=False` models, inject a direct tool
      protocol (tool catalog + pinned ` ```tool_code\nname(arg="val")\n``` ` format) into the agent
      loop's degraded branch so the model emits a deterministically-parseable call the kernel recovers.
      Recognizer-based recovery alone proved best-effort, not reliable (two behavior-test runs). See
      flight-log Decisions + leg 08. Re-runs the behavior test (must pass before landing).
- [ ] `uat-and-alignment` *(optional)* — guided hands-on session tuning recovery behavior
      against real gemma output (false-positive feel, multi-call ordering, stripping aesthetics).

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (`make test` hermetic; live + behavior green when run against local gemma3:4b)
- [ ] Documentation updated — (a) refresh the Ollama/degraded-tools note in `the_one/agents.md`
      (the "no tools" degradation section — note the citation has **drifted** from the old
      `:798`; re-locate it) to record that text-form tool calls are now recovered for
      non-tool-capable models, and which formats are recognized; (b) **fix the stale
      "single-shot"/"single LLM iteration" wording** in `the_one/agent/core.py:172-173` and the
      matching `agents.md` sentence — the loop **multi-iterates** in degraded mode when
      `tool_calls` are recovered (architect finding; see flight-log Anomalies).

### Verification
- **Unit (hermetic, primary):** the recovery-kernel suite covers all three formats, the real
  gemma fixture, multi-call, positional best-effort, and no-false-positive-on-prose; the
  adapter suite (mocked transport) proves recover-on-empty-structured, content-strip, and
  no-regression on clean structured responses.
- **Live (gated):** `@pytest.mark.live` confirms recovery against real gemma3:4b output; the
  degraded-round-trip probe pins DD5 against the live model.
- **Behavior test:** `/behavior-test gemma-tool-use-recovery` — the running agent executes the
  tool end-to-end with no raw call text shown (Witnessed pattern; Executor + Validator).
- **Regression net:** Flight 4's cross-provider conformance suite will later guard the
  request→tool_call→tool_result→final round-trip across providers, including this recovery path
  for Ollama (out of scope here; this flight ships its own tests).
