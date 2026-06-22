# Leg: degraded-passive-recovery

**Status**: planning *(CONTINGENT — design in full and run ONLY if 08A is abandoned)*
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **Gated trial, approach B of three (08A → 08B → 08C).** Do **not** start this leg unless
> [08A](08a-degraded-blind-start-search.md) was tried and **abandoned** (over-routing fixed but the 4B model
> couldn't reliably complete the blind→search→call discovery hop). If 08A was accepted, this leg never runs.
> This spec is intentionally lighter than 08A — flesh it out at the point it's actually picked up, using
> 08A's findings.

## Objective

Stop *inducing* tool use on the degraded path entirely — drop the injected tool catalog/protocol and give
non-tool-capable models a **tool-free conversational** system prompt — while keeping the recovery kernel wired
as a **passive safety net**: if the model spontaneously emits a well-formed `tool_code`/Hermes/JSON call, it
is still recovered and dispatched. Essentially reverts to the pre-Leg-08 posture (legs 01–07: recover what
the model emits; don't tell it the catalog).

## Context

- **Why this kills over-routing.** The over-routing driver (08A's root cause) is the *injected* catalog +
  format framing. If the degraded prompt advertises no tools and no call format, a 4B model has nothing to
  over-reach for and defaults to conversation. The recovery kernel in `ollama_provider`
  (`_recover_into_tool_calls`) is **provider-stateless** (Flight 3 DD2 deliberately did NOT gate it on
  `supports_tools`), so it keeps working as a net for a model that *spontaneously* produces a valid call.
- **The trade-off, stated honestly.** This **partially gives up** the Flight 3 mission criterion: tool use
  becomes *best-effort* (fires only when the model volunteers a valid call), not *reliable*. That is strictly
  weaker than 08A's "preserved via discovery." Acceptable only if 08A's hop proved unreliable — i.e. reliable
  degraded tool use isn't achievable on this model anyway, so an honest best-effort + clean conversation beats
  a broken always-on path.
- **Prompt drift hazard (debrief Rec 3).** `DEGRADED_BASE_PROMPT` (`agent/config.py:DEGRADED_BASE_PROMPT`) is
  a ~90% verbatim copy of `BASE_PROMPT` and still carries tool-use nudges ("prefer the right tool…"). 08B
  needs a genuinely **tool-free** chat prompt (strip the "Tool use" guidance, keep identity + turn semantics +
  persona-append). This is a good moment to also address Rec 3 (derive the degraded prompt from `BASE_PROMPT`
  by section-removal rather than maintaining a third verbatim copy) — but keep that refactor a separate diff
  hunk.

## Inputs

- 08A abandoned, with its findings recorded in the flight log.
- `the_one/agent/core.py:_build_degraded_messages` (currently injects the addendum), `agent/degraded_tools.py`,
  `agent/config.py` (`DEGRADED_BASE_PROMPT`), `the_one/llm/ollama_provider.py:_recover_into_tool_calls`.

## Outputs

- `the_one/agent/core.py` — degraded path no longer injects a tool catalog/protocol; it sends a tool-free
  chat system prompt with `tools=None`.
- `the_one/agent/config.py` — a tool-free degraded/chat prompt (strip tool-use guidance; ideally derive from
  `BASE_PROMPT` per Rec 3).
- `the_one/llm/ollama_provider.py` — recovery kernel **kept on** as the passive net (no change, or a clarifying
  comment that it is now the sole tool path for degraded models).
- Tests: degraded prompt is tool-free (no catalog, no format spec); a spontaneously-emitted valid `tool_code`
  call still recovers + dispatches; over-routing control (greeting/knowledge question) dispatches nothing.
- Behavior-test spec adjusted to the best-effort reality (the reliable-execution checkpoints become
  best-effort/INCONCLUSIVE-on-no-attempt rather than hard FAIL); new run log.
- Accept/abandon decision recorded.

## Acceptance Criteria (sketch — finalize at pickup)

- [ ] **Degraded prompt is tool-free:** no tool catalog, no `tool_code` format spec, no "prefer the right
      tool" nudge. Unit-tested (assert the degraded system message contains neither a catalog nor the format
      block).
- [ ] **Over-routing gone (LIVE, full-catalog agent):** greeting + "what is a haiku?" → direct answers, zero
      tool dispatches.
- [ ] **Passive net still works:** a model turn whose content *is* a well-formed
      ` ```tool_code\nshell(command="echo hi")\n``` ` (scripted via mock provider) still recovers → dispatches
      → executes. Unit-tested.
- [ ] **Capable path unchanged** (byte-identical). Unit-tested.
- [ ] **Behavior test adjusted to best-effort + green:** the no-false-positive checkpoint (full-catalog)
      passes; the reliable-tool-execution checkpoints are reframed as best-effort (INCONCLUSIVE when the model
      doesn't volunteer a call) rather than hard failures. `/behavior-test gemma-tool-use-recovery` → PASS.
- [ ] **`make test-unit` green.**
- [ ] **Accept/abandon decision recorded.**

## Accept / Abandon Decision Gate

- **ACCEPT** — over-routing gone, conversation clean, and best-effort recovery is judged a good-enough tool
  story for non-tool models. Land it; reframe the mission criterion from "reliably executes tool calls" to
  "executes spontaneously-emitted tool calls (best-effort); does not over-route" and update the mission docs.
  Skip 08C.
- **ABANDON** — the residual best-effort tool behavior is still judged unacceptable (e.g. the passive net
  fires on intentional-but-non-tool output, or the half-supported tool story is more confusing than no
  support). Record the finding and proceed to **08C** (chat-only, recovery off).

## Files Affected (anticipated)

- `the_one/agent/core.py`, `the_one/agent/config.py`, `the_one/agent/degraded_tools.py` (likely retired/no
  longer injected on this path), `the_one/llm/ollama_provider.py` (comment only), `tests/…`,
  `tests/behavior/gemma-tool-use-recovery.md`, flight log, mission docs.

## Citation Audit

Citations carried from 08A (same symbols); re-verify against current code at pickup, since 08A's accepted/
abandoned changes may have shifted them.
