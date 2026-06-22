# Leg: degraded-chat-only

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **CHOSEN RESOLUTION (operator, 2026-06-19).** The gated trial ran 08A (blind-start discovery) and the
> operator verified hands-on that gemma3:4b, even when search surfaces the right tools, will not call them and
> stalls — the multi-step hop is a 4B floor. 08A is **aborted**; 08B (passive recovery) is **skipped**. The
> operator chose **08C: block tools for models that don't advertise the `tools` capability** — the cleaner UX
> (a reliable chat agent beats an unreliable tool agent that frequently no-responds). The search tokenize+cap
> from the 08A trial is **kept** (leg `08d-search-query-tokenization`). This leg **reverses** the mission's
> "Gemma reliably executes tool calls" criterion — an explicit, operator-authorized scope decision.

## Objective

Treat any model whose `supports_tools()` is `False` (e.g. gemma3:4b via Ollama) as a **conversational-only**
agent: inject no tool catalog/protocol, give it a tool-free chat system prompt, and **gate the recovery kernel
OFF** so a spontaneously-emitted `tool_code`/Hermes/JSON block can never be dispatched. The agent converses; it
never runs a tool. The UI already shows a red "no tools" capability chip for these models, so the operator is
informed.

## Context

- **Current state on the branch.** 08A put a blind-start discovery protocol on the degraded path
  (`agent/degraded_tools.py` reframed addendum + `agent/core.py:_build_degraded_messages` rendering a
  discovery-only catalog). 08C **supersedes** that: the degraded path stops injecting any tool protocol. The
  `degraded_tools.py` direct-tool-protocol module becomes dead code and is retired.
- **Why recovery must be gated off (the non-obvious requirement).** Recovery lives in `OllamaProvider`
  (`the_one/llm/ollama_provider.py`): both `complete()` and `stream()` run
  `if not tool_calls: content, recovered = _recover_into_tool_calls(content); tool_calls = recovered`.
  Flight 3 DD2 deliberately made this **provider-stateless** (recover regardless of capability). So removing
  the catalog injection (above) is **not enough** — a chat-only gemma that emits a `tool_code` fence (training
  priors) would still get parsed, **content-stripped (DD4)**, and dispatched. Because the *strip* and the
  *parse* are the same step, the gate must sit **in the provider, at the recovery call site** (so a non-tool
  model's content passes through verbatim and nothing dispatches), not at the agent layer.
- **Capable-but-loose models still recover.** Gating recovery on `supports_tools()` being **True** preserves
  DD2's real intent: a *tool-capable* model that occasionally drops to text-form is still recovered; only
  *non-tool* models are chat-only. (Tool-capable Ollama models are offered tools on the wire and normally use
  structured `tool_calls`; the recovery remains their text-form fallback.)
- **This reverses a mission criterion.** Mission success criterion *"A tool-using conversation with Gemma via
  Ollama reliably executes tool calls, including loose text/JSON format"* and the Flight 3 "Contributing to
  Criteria" line become **explicitly not-met / rescoped**: non-tool models are conversational by design.
  Record as an operator scope decision (mission Known Issues + criterion state + a `/mission-debrief` note),
  not buried in a leg.
- **Breadth note.** The degraded mechanism served any OpenAI-compatible local model without the `tools`
  capability. 08C makes all of them chat-only. That breadth was weighed and accepted: an unreliable hop on a
  4B is worse UX than a clean chat agent, and a better future model that *does* advertise `tools` takes the
  normal structured path unaffected.

## Inputs

- Branch `flight/03-degraded-over-routing` with 08A's blind-start changes in place and the 08d search
  tokenize+cap landed.
- `the_one/agent/core.py` (`_build_degraded_messages`, the `supports_tools` degraded branch in
  `_run_iterations`), `the_one/agent/config.py` (`BASE_PROMPT`, `DEGRADED_BASE_PROMPT`),
  `the_one/agent/degraded_tools.py` (to be retired), `the_one/llm/ollama_provider.py`
  (`_recover_into_tool_calls` + the two call sites in `complete()`/`stream()`, `supports_tools()`).

## Outputs

- `the_one/llm/ollama_provider.py` — recovery gated on `supports_tools()` (memoized resolve); a
  `supports_tools=False` model never recovers/strips/dispatches a text-form call.
- `the_one/agent/core.py` — `_build_degraded_messages` produces a **tool-free chat** system prompt (no
  addendum, no catalog); the blind-start/discovery rendering from 08A is removed.
- `the_one/agent/config.py` — a tool-free chat prompt for non-tool models (derive cleanly; resolve the
  debrief Rec 3 `DEGRADED_BASE_PROMPT`-verbatim-copy hazard while here if low-risk).
- `the_one/agent/degraded_tools.py` — **retired** (deleted) along with `tests/test_degraded_tool_prompt.py`,
  since no path injects a tool protocol anymore. (If deletion is noisier than expected, leave the module
  unimported with a deprecation note — but prefer deletion.)
- Tests: a `supports_tools=False` turn whose model content is a `tool_code` block dispatches **nothing**
  (the inverse of the Flight 3 recovery-dispatch tests — invert/rename them, don't leave them contradicting
  the design); recovery STILL fires for a `supports_tools=True` model that drops to text; conversation works.
- `tests/behavior/gemma-tool-use-recovery.md` — **retired/disabled** (its premise "degraded recovery executes
  a tool" is reversed). Replace with a short note or a chat-only assertion; the new property (no tool ever
  runs for a non-tool model) is cheaply covered by unit tests + a quick live check, not a full behavior test.
- `mission.md` — the "reliably executes tool calls" criterion marked not-met/rescoped with reason + Known
  Issues entry; carry to `/mission-debrief`.

## Acceptance Criteria

- [ ] **No tool dispatch for non-tool models (unit + LIVE):** a `supports_tools()=False` agent dispatches no
      tool. A turn whose model content is a well-formed ` ```tool_code\nshell(command="echo hi")\n``` ` results
      in **zero** dispatches; the block is NOT stripped/parsed — it passes through as assistant text (so the
      user isn't left with an empty message). Unit-tested with a mock provider; LIVE-confirmed against
      gemma3:4b on the full-catalog `Test Agemt` (the input that produced `shell(command=...)` now yields a
      normal text reply, no `tool_call`/`tool_result` events).
- [ ] **Recovery preserved for tool-capable models:** a `supports_tools()=True` Ollama model that returns a
      text-form call (no structured `tool_calls`) STILL recovers + dispatches (DD2's real intent). Unit-tested
      (mock provider with `supports_tools` True vs False).
- [ ] **Over-routing gone (LIVE, full-catalog agent):** "Hello there!" and "What is a haiku?" → direct
      natural-language answers, zero tool dispatches (already true under 08A's prompt; must remain true with
      the tool-free chat prompt).
- [ ] **Tool-free chat prompt:** the degraded system prompt contains no tool catalog, no `tool_code` format
      spec, and no "prefer the right tool"/`continue`-tool guidance. Unit-tested.
- [ ] **Contradicting tests inverted/retired:** every test asserting "degraded recovery dispatches a tool"
      (e.g. in `tests/test_agent_degraded_injection.py`, and any in `tests/test_ollama_provider*.py`) is
      inverted/renamed to the new reality (git-documented intent shift), not left contradicting. The
      `degraded_tools.py` renderer tests are removed with the module.
- [ ] **Behavior test disposition:** `tests/behavior/gemma-tool-use-recovery.md` is retired or rewritten to
      chat-only; the flight log records which and why.
- [ ] **Mission docs updated:** the "reliably executes tool calls" criterion is marked not-met/rescoped with
      a recorded reason; mission Known Issues notes non-tool models are chat-only by design (08C);
      `/mission-debrief` carry-forward noted.
- [ ] **`make test-unit` green** (record the new count).
- [ ] **08d search tokenize+cap retained** (untouched by 08C; confirm `tests/test_search_tools.py` stays
      green).

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ollama_provider_recovery.py
  tests/test_ollama_degraded_roundtrip.py tests/test_llm_provider_cross_provider_conformance.py
  tests/test_agent_degraded_injection.py tests/test_toolcall_recovery.py tests/test_search_tools.py
  -x --timeout 30` — green (these are the actual file names; invert the recovery-dispatch ones per the
  layer-specific guidance above).
- `make test-unit` — full hermetic suite green.
- `git diff` — recovery gate confined to the provider's two recovery call sites; `_build_degraded_messages`
  produces a tool-free prompt; `degraded_tools.py` + its tests deleted; no change to the auth-pause /
  `_deferred_tool_calls` flow, the Leg-09 backstop, or the capable-path wire `tools=` array.
- **Restart** the dev instance (kill the running `the_one.main serve` and relaunch with `THE_ONE_PORT=8485`),
  then LIVE-check against `Test Agemt`: "Hello there!" → text reply, no tool; "Run `echo hi` and show the
  output" → the model may *describe* it or emit a `tool_code` block, but **no tool runs** and the user gets a
  text response (not an empty/stalled turn).

## Implementation Guidance

1. **Gate recovery in the provider** (`the_one/llm/ollama_provider.py`). At both recovery call sites
   (`complete()` ~`if not tool_calls:` before `Message.assistant`, and `stream()` ~ after
   `acc.finalize_tool_calls()`), only run `_recover_into_tool_calls` when the model is tool-capable:
   `if not tool_calls and await self.supports_tools(): content, recovered = ...`.
   - **Do NOT add a new `_tools_capable()` memoization layer (design-review correction).** `supports_tools()`
     already delegates to `get_model_capabilities()`, which has a module-level 300s TTL cache in `ollama_api`;
     and the agent layer calls `supports_tools()` only once per `_run_iterations` entry. So calling
     `await self.supports_tools()` directly at the two sites adds no per-request `/api/show` round-trip in
     practice. A second per-instance memoization would duplicate the cache and risk a stale latch across
     reconfigurations. (If a per-instance latch is ever wanted, mirror the `bool | None` sentinel pattern of
     `_resolve_max_context_tokens_if_needed` — but it is not needed here.)
   - Document that this updates Flight 3 DD2: recovery is now gated on capability (tool-capable models that
     drop to text are still recovered; non-tool models are chat-only). The fail-open behavior of
     `supports_tools()` (returns `True` on an indeterminate `/api/show`) means recovery stays on under
     uncertainty — acceptable (fail toward prior behavior).
2. **Tool-free chat prompt** (`the_one/agent/config.py` + `core.py:_build_degraded_messages`). Replace 08A's
   blind-start rendering: `_build_degraded_messages` returns `[Message.system(chat_system), *self.messages[1:]]`
   where `chat_system` is a tool-free chat prompt (identity + "respond directly, concisely" + persona-append),
   with NO tool-discovery, NO "Tool use", NO `continue`-tool, NO catalog. **Replace `DEGRADED_BASE_PROMPT`
   with a clearly-named tool-free constant `CHAT_ONLY_PROMPT`** (its current docstring describes the now-dead
   08A direct-tool-protocol reasoning — delete/replace it). Derive `CHAT_ONLY_PROMPT` cleanly from
   `BASE_PROMPT` (strip all tool sections) rather than maintaining a verbatim copy (debrief Rec 3); keep the
   persona compose path intact. No call to `build_degraded_tool_prompt`. The existing strip-and-swap logic in
   `_build_degraded_messages` can be reused almost verbatim — the only diff is the absence of the addendum.
3. **Retire `degraded_tools.py`** and `tests/test_degraded_tool_prompt.py` (nothing injects a protocol now).
   Remove the import in `core.py`. Grep confirms `build_degraded_tool_prompt` / `_PROTOCOL_HEADER` are
   referenced only by `core.py` + those tests.
4. **Invert/retire recovery-dispatch tests — at the RIGHT layer (design-review correction; the layers behave
   differently):**
   - **Provider layer = the real gate.** The new property — `supports_tools()=False` + content is a raw
     `tool_code` block → **zero** recovered calls, content passes through verbatim (NOT stripped) — must be
     tested in **`tests/test_ollama_provider_recovery.py`** (it exercises the *real* `OllamaProvider` +
     recovery kernel, where the gate lives). Add: a `supports_tools()=False` provider does not recover; a
     `supports_tools()=True` provider still recovers (DD2's real intent preserved). This is the load-bearing
     new test.
   - **Agent-layer mock tests don't hit the gate.** `tests/test_agent_degraded_injection.py:test_degraded_loop_dispatches_recovered_tool_code`
     uses a mock LLM that returns *pre-formed structured* `tool_calls` (it bypasses the provider recovery
     kernel), so the provider gate doesn't change it. Re-author it to the new product reality: the degraded
     system prompt is tool-free (no catalog/format), and assert the chat-only behavior — do NOT just rename it
     while leaving a mock that still injects structured tool_calls (that would be green-but-vacuous).
   - **Conformance suite (`tests/test_llm_provider_cross_provider_conformance.py` §6 recovery rows):**
     `test_ollama_recovery_roundtrip_complete`/`_stream` feed `GEMMA_FIXTURE` to a real `OllamaProvider` whose
     `make_ollama` fixture "never calls `supports_tools()`." After gating, recovery now consults
     `supports_tools()`; with no live Ollama it returns `True` (fail-open) so they'd pass *by accident*.
     **Explicitly stub `supports_tools()` to return `True`** in those fixtures so the recovery rows test the
     intended path, not the network-error fail-open. Add a clarifying comment.
   - **08A search-dispatch tests are now moot — remove them:**
     `tests/test_agent_degraded_injection.py:test_search_tools_dispatch_mutates_loaded_schemas_and_next_turn_rerenders`
     and `test_backstop_does_not_misfire_on_search_then_different_concrete_tool` exercise the 08A
     degraded-discovery hop, which 08C deletes. Remove them.
   - **`tests/test_agent_redundant_backstop.py` is UNAFFECTED** — it uses degraded mocks that emit *structured*
     tool_calls directly (bypassing recovery), so it still validates the Leg-09 backstop loop logic. Leave as
     is (see the dead-code note below).
5. **Behavior test.** Retire `tests/behavior/gemma-tool-use-recovery.md` (premise reversed) — set its status
   to a terminal/obsolete state with a note pointing here, or rewrite to assert chat-only. Record the choice
   in the flight log. Do not leave an `active` spec whose premise the code now contradicts.
6. **Mission docs** (`missions/16-…/mission.md`): mark the "reliably executes tool calls" criterion as
   not-met/rescoped with the reason (4B can decide+invoke but not reliably complete the discovery hop;
   over-routing made always-on injection unusable; chat-only chosen for UX); add a Known Issues line
   (non-tool models are conversational-only by design, 08C); note the `/mission-debrief` carry-forward.
   Annotate, don't rewrite the original framing.

## Edge Cases

- **Non-tool model emits a `tool_code` block anyway** → with recovery gated off it is NOT parsed/stripped; it
  surfaces as assistant text. Prefer showing it as text over an empty message. Confirm the content isn't
  silently dropped.
- **Tool-capable model with `tools=None` on a given call** → still `supports_tools()=True`, so recovery stays
  available (unchanged from today).
- **`supports_tools()` indeterminate (network blip)** → it returns `True` on uncertainty
  (`ollama_provider.py:supports_tools` docstring), so recovery stays on in the ambiguous case — acceptable
  (fail toward the prior behavior, not toward silently swallowing a tool call).
- **Capable path** → byte-identical (wire `tools=` array unchanged; the gate only affects the recovery branch).
- **Leg-09 redundant-call backstop becomes unreachable on the chat-only path** → with recovery gated off, a
  non-tool model's `response.tool_calls` is always empty, so the degraded partition (`new` vs redundant) and
  the backstop closing never fire. This is **harmless dead code** — leave the backstop + its tests
  (`test_agent_redundant_backstop.py`) in place (they still validate the loop logic given structured
  tool_calls); do NOT remove the backstop in 08C (out of scope). Record it in the flight log as a now-dead
  path and a candidate cleanup for the debrief.

## Files Affected

- `the_one/llm/ollama_provider.py` — memoized `_tools_capable()` gate on the two recovery call sites.
- `the_one/agent/core.py` — `_build_degraded_messages` → tool-free chat prompt; drop `degraded_tools` import.
- `the_one/agent/config.py` — tool-free chat prompt (derive from `BASE_PROMPT`).
- `the_one/agent/degraded_tools.py` — deleted; `tests/test_degraded_tool_prompt.py` — deleted.
- `tests/test_agent_degraded_injection.py`, `tests/test_ollama_provider*.py` — invert/retire recovery-dispatch
  assertions; add the capability-gated-recovery tests.
- `tests/behavior/gemma-tool-use-recovery.md` — retired/rewritten.
- `missions/16-…/mission.md` — criterion reversal + Known Issues.
- `missions/16-…/flights/03-…/flight-log.md` — leg-08C entry + behavior-test disposition.

## Citation Audit

Citations verified at design time (2026-06-19, branch `flight/03-degraded-over-routing`):
- `the_one/llm/ollama_provider.py` — recovery call sites in `complete()` and `stream()` (`if not tool_calls:
  … _recover_into_tool_calls`); `supports_tools()` present (returns True on indeterminate). OK.
- `the_one/agent/core.py:_build_degraded_messages` — currently renders 08A's discovery-only catalog (to be
  replaced). OK.
- `the_one/agent/config.py` — `BASE_PROMPT`, `DEGRADED_BASE_PROMPT` present. OK.
- `the_one/agent/degraded_tools.py` — present (to be retired). OK.
- DD2 reference — Flight 3 `flight.md` DD2 ("recovery NOT gated on supports_tools"); 08C updates it. OK.
