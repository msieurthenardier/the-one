# Flight Log: Open-Model Tool-Use Robustness — Text-Form Tool-Call Recovery (#105)

**Flight**: [Open-Model Tool-Use Robustness (#105)](flight.md)

## Summary

Planning. Spec authored from issue #105 + the Flight 1 spike (`leg 02`, which confirmed the
capability gate is correct and captured the real loose format — a ` ```tool ` fenced
Python-call block — from live gemma3:4b). Direction ratified with the operator: a pure
text-form tool-call recovery kernel wired into the Ollama adapter (all three formats —
gemma fenced Python-call first-class, Hermes tags, bare-JSON), recovering into structured
`ToolCall`s that the existing agent loop dispatches unchanged. Verification: fixtured units +
a live gemma marker test + a behavior test. Optional HAT included.

---

## Reconnaissance Report

Upstream source: GitHub issue **#105**, which cites specific code locations. Verified against
current code at planning (2026-06-18):

| Item (from #105) | Classification | Evidence | Note |
|---|---|---|---|
| Capability gate drops tools for Gemma — `ollama_provider.py:71-79` | `confirmed-live` | `supports_tools()` at `:71-79`, Gemma-style models → `False` | Gate is CORRECT (spike: Ollama 400s if tools offered). Keep. |
| Loop drops all schemas + single-shot when no tools — `agent/core.py:167-188` | `confirmed-live` (refined) | Logic at `:177-238`; `supports_tools` gates only the wire `tools=` array (`:185-188`) | **Key refinement:** dispatch `if not response.tool_calls: return` / `_dispatch_tool_calls(...)` at `:225-235` is **unconditional** of `supports_tools` → recovering into `tool_calls` is dispatched even in degraded mode. No loop change needed (DD6). |
| `complete()` parses only structured `tool_calls` — `ollama_provider.py:117-129` | `confirmed-live` | `:117-129` reads `msg.get("tool_calls")` only | The recovery wire point (DD2). |
| `stream()` parses only structured `tool_calls` — `ollama_provider.py:197-228` | `confirmed-live` | `:197-228` accumulates `delta.tool_calls` only | The streamed recovery wire point. |
| "no tools" degradation documented — `the_one/agents.md:798` | `drifted` | `agents.md:798` is now the subprocess-env-invariant section | The degradation note moved; re-locate when updating docs in the Post-Flight doc step. |

Decision: all items proceed as live work (the gate item proceeds as "keep as-is, do not
offer tools"). No retirements. The `agents.md` citation drift is a doc-update detail, not a
scope change.

---

## Flight Director Notes

- 2026-06-18 — `/flight` planning started for Flight 3 (#105). Pulled in #105 as the primary
  issue; excluded the UI copy-button / #117 / #122-enhancement items (UI surface, out of
  mission scope). Reused the Flight 1 spike's captured gemma fixture.
- **Central design question resolved at planning (DD6):** provider-side recovery is
  sufficient — the agent loop dispatches `response.tool_calls` unconditionally (`core.py:225-235`).
  Flight stays within the mission's "agent loop untouched" boundary (`the_one/llm/` only).
- **Operator design decisions (interview):** (1) cover all three text-form formats, gemma
  first-class; (2) verification = fixtured units + live gemma marker test + behavior test;
  (3) include the optional HAT/alignment leg.
- **One question deliberately left live:** DD5 degraded round-trip serialization (does gemma
  400 on tool-call/tool-role history with `tools=None`?) — deferred into `leg 03` with a
  pre-authorized `_to_api_message` plain-text adaptation, mirroring Flight 2's live-probe-
  resolves-open-question pattern.

---

## Decisions

_None yet._

---

## Deviations

_None yet._

---

## Anomalies

### Doc drift: "single-shot / single iteration" wording is stale for the recovery path
**Observed** (architect design review, 2026-06-18): `the_one/agent/core.py:172-173` comments
"run as a single-shot chat" and `agents.md` says the degraded path "runs a single LLM
iteration as plain chat." This is **false once tool calls are recovered**: the only degraded-
mode early-exit is `if not response.tool_calls: return` (`:225-226`), so a recovered call is
dispatched and the loop **re-iterates** (the follow-up turn carries the tool result). The code
is correct; the *documentation* is stale and would mislead a reviewer of the recovery wiring.
**Severity**: cosmetic (no code impact). **Resolution**: fix both the `core.py` comment and the
`agents.md` sentence in the Post-Flight documentation step (Completion Checklist), alongside
the degradation-note update.

---

## Session Notes

- 2026-06-18 — Spec authored (planning). Behavior-test spec drafted
  (`tests/behavior/gemma-tool-use-recovery.md`, status `draft`).
- 2026-06-18 — Architect design review (Phase 5b): **approve with changes**. DD6 boundary
  claim verified correct (loop dispatches recovered `tool_calls` unconditionally, re-iterates;
  no agent-loop change). Incorporated (additive — skipped 2nd cycle):
  - [high→cosmetic] recorded the "single-shot" doc-drift anomaly + scheduled the `core.py:172`
    + `agents.md` fix in the Post-Flight doc step.
  - [med] DD5 now names **both** `_to_api_message` branches the plain-text adaptation must
    change (assistant `tool_calls` → inline text; `role:"tool"` → `role:"user"` prose) + the
    gating signal; `leg 03` updated.
  - [med] `leg 02` now states the **explicit** recovery insertion points (esp. stream(): after
    `acc.finalize_tool_calls()` `:225-228`, before the final `Message` `:230` — not inside the
    loop) + pins the `ToolCall.id → ToolResult.tool_call_id` invariant.
  - [low] DD3 pins positional-arg handling (`arguments["__positional_args__"]` + WARN, never
    dropped); added DD5a (no per-turn recovery cap; multi-call ordered list).
  - [low] behavior test gained a step 0 (confirm/create the gemma+shell agent), a shell-tool
    guard in step 1, and a one-shot directive re-prompt before INCONCLUSIVE.
  - `leg 04` now also asserts the raw block is stripped from `Message.content`.
- 2026-06-18 — Flight status → **ready** (operator-confirmed). Pre-flight checklist satisfied;
  DD5 degraded-round-trip question deliberately deferred into `leg 03`. Planning artifacts are
  currently untracked on the `flight/02` branch (will not enter PR #127); at execution start
  they branch from `main` as `flight/03-open-model-toolcall-recovery` and are committed there.
  Next: run `/agentic-workflow flight 3, mission 16, the-one` to execute.
- 2026-06-18 — `/agentic-workflow` execution started. Flight Director (Mission Control)
  orchestrating. Branched `flight/03-open-model-toolcall-recovery` from `main` (flight/02 is
  unmerged but independent — Anthropic schema vs Ollama recovery — per the planning note).
  **Flight-start prerequisites verified:** local Ollama reachable with `gemma3:4b` pulled
  (capabilities `['completion','vision']` — no `tools`, confirming the `supports_tools()=False`
  degraded path this flight targets); the-one app responding at `:8484` (HTTP 200). Flight
  status → **in-flight**. Loaded crew from `.flightops/agent-crews/leg-execution.md` (Developer
  Sonnet / Reviewer Haiku). Per the deferred-review model, leg design is reviewed per leg, but
  code review + commit are batched after the last autonomous leg. Execution plan: legs 01–02
  (kernel + adapter wiring) are standard autonomous; leg 03 (degraded-roundtrip-probe) and leg
  04 (live-verify-gemma) need the live model already verified present; leg 05 runs via the
  `/behavior-test` skill directly (not a spawned Developer); leg 06 (HAT) is operator-driven and
  optional. Committed planning artifacts as the branch foundation.
