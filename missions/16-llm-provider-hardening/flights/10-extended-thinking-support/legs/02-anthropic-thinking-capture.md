# Leg: anthropic-thinking-capture

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

## Objective

Enable extended thinking on Anthropic requests (resolved budget → `kwargs["thinking"]`, with
DD6's `temperature=1` / raised `max_tokens` enforcement) and **capture** the signed
`thinking` / `redacted_thinking` blocks the model returns into `Message.thinking`, on both the
`complete()` and streaming (`get_final_message()`) paths — while suppressing thinking on the
connector inference classifier (DD4).

## Context

- Builds directly on Leg 01: `Message.thinking` (list of `ThinkingBlock`) and
  `Message.assistant(..., thinking=...)` already exist and round-trip through the codec. This
  leg is the **first producer** of thinking blocks.
- **DD4 — enablement via resolved budget.** Precedence: per-provider `config["thinking_budget"]`
  → env `THE_ONE_ANTHROPIC_THINKING_BUDGET` → default. Config reaches the adapter via
  `factory.py:272–277` (`"config": provider_config.config` → `AnthropicProvider.__init__`
  `**kwargs`). Mirrors the F09-05 `num_ctx` resolver (`ollama_provider.py:_coerce_num_ctx` /
  `effective_num_ctx`) exactly.
- **DECISION (this leg) — thinking is OFF by default.** The flight DD4 text carries an
  ambiguity ("default (0 = disabled)" vs. "default 4096"). Resolved here: the resolver's
  terminal default is **`0` = disabled**; `4096` is the *suggested enabled magnitude*
  (`DEFAULT_THINKING_BUDGET` constant) that Leg 05's admin field pre-fills and writes when the
  operator turns thinking on. Off-by-default is the only reading consistent with (a) the
  "`0`/blank = disabled" sentinel, (b) the behavior-test "Budget = 0 (disabled)" gating
  variant, and (c) not silently forcing `temperature=1` + raised `max_tokens` + thinking-token
  billing onto every existing Anthropic user. The flight lists "choosing the exact default
  budget value" as an acceptable variation, granting this latitude. **Recorded as a flight-log
  Decision.**
- **DD6 — request constraints are enforced, not surprises.** When thinking is enabled the
  adapter forces `temperature = 1` (API rejects any other value with thinking on), ensures
  `budget_tokens ≥ 1024` (Anthropic floor), and **raises** `max_tokens` (never shrinks the
  operator's budget) so the answer has headroom above the thinking budget. Single enforcement
  site: `_build_kwargs`. The existing temperature-retry (`anthropic_provider.py:175–187`,
  `:233–243`) is **benign** under thinking (popping `temperature` falls back to Anthropic's
  thinking default of 1) — do NOT "fix" it.
- **DD4 — connector inference fast path must suppress thinking.** `_inference.py:325–330` calls
  `provider.complete(..., temperature=0.0, max_tokens=10)` as a cheap yes/no classifier. A
  configured budget (≥1024) would force thinking onto that call (`max_tokens=10 ≪ budget`,
  wasteful + DD6-tripping). The call is on a **generic** provider, so the "no thinking" signal
  is a back-compatible keyword-only param `enable_thinking: bool | None = None` added to the
  `LLMProvider` contract — only Anthropic acts on it; the others accept-and-ignore. The
  classifier passes `enable_thinking=False`.
- **DD5 — Anthropic-only this flight.** Only `anthropic_provider.py` populates thinking; the
  `enable_thinking` param is provider-neutral so other adapters can honor it later.
- **Live premise (flight prerequisite).** The empirical premise (with thinking enabled,
  `text_stream` yields answer deltas and `get_final_message()` carries signed thinking blocks)
  is judged well-founded by design review, not a real risk. Autonomous acceptance is via
  **fixtured** tests. The **live** confirmation is authored here as a `@pytest.mark.live` probe
  but the operator should **run it before Leg 03 (replay)**, not Leg 06 — the flight's
  Adaptation Criteria frame the probe as a fail-fast gate "before building capture," and the
  divert (raw-event iteration) would otherwise land after Legs 03–05 already built on the
  premise. Author-and-defer for autonomous execution; recommended live-run point = pre-Leg-03
  (operator action, needs an Anthropic key). The behavior test (Leg 06) remains the final live
  acceptance gate.

## Inputs

- Leg 01 landed: `ThinkingBlock`, `Message.thinking`, `Message.assistant(thinking=...)`, codec
  round-trip all present.
- `the_one/llm/anthropic_provider.py` — `__init__` (`:84–89`, swallows `**kwargs`);
  `_build_kwargs` (`:115–157`, `kwargs` assembled `:130–135`, `temperature` at `:134`,
  `max_tokens` at `:133`); `complete` block loop (`:191–195`), `Message.assistant` return
  (`:204`); `_stream_inner` block loop (`:263–267`), `Message.assistant` return (`:276`);
  temperature-retry (`:175–187`, `:233–243`); base import (`:13–21`).
- `the_one/llm/ollama_provider.py` — the resolver template: `_coerce_num_ctx` (`:62–82`),
  `effective_num_ctx` (`:85–108`), `_env_int` (`:44`), env/default constants (`:40–41`),
  `__init__` config read (`:176–179`).
- `the_one/connectors/_inference.py` — the classifier call (`:325–330`).
- `tests/test_anthropic_provider.py` — fixture scaffolding: `_StubContentBlock(type_, **kwargs)`
  (`:40–46`), `_StubResponse` (`:49–54`), `_CreateRecorder` (`:57–80`, records call kwargs),
  `_provider_with_create` (`:83–88`), `_StreamCM` / `_StreamRecorder` / `_provider_with_stream`
  (`:365–419`), `_tool` / `_user_msg` (`:91–96`), `make_bad_request` (used `:447`).
- `tests/test_anthropic_live.py` — the `@pytest.mark.live` home.

## Outputs

- `the_one/llm/anthropic_provider.py` — budget resolver (`_coerce_thinking_budget`,
  `effective_thinking_budget`, env/default/min constants); `__init__` reads
  `config["thinking_budget"]`; `_build_kwargs` enables thinking + enforces DD6 + honors
  `enable_thinking`; capture on both `complete()` and `_stream_inner`; `ThinkingBlock` imported.
- `the_one/llm/base.py` — `enable_thinking: bool | None = None` keyword-only param on
  `LLMProvider.complete` / `.stream` (abstractmethods).
- `the_one/llm/openai_provider.py`, `openrouter_provider.py`, `ollama_provider.py`, `mock.py` —
  each `complete`/`stream` override accepts `enable_thinking` (ignored). (OpenRouter may inherit
  from OpenAI — verify by grep.)
- `the_one/connectors/_inference.py` — classifier passes `enable_thinking=False`.
- `tests/test_anthropic_provider.py` — new capture + enablement + enforcement + suppression +
  budget-resolution + non-thinking-model-error tests.
- `tests/test_anthropic_live.py` — a `@pytest.mark.live` premise-probe test (authored; run at
  Leg 06/HAT).

## Acceptance Criteria

- [x] Budget resolver: `_coerce_thinking_budget(value)` coerces a free-form config value to
      `int | None`, **preserving `0` as a meaningful explicit-disable** (distinct from `None` =
      unset), rejecting `bool`, treating blank string / non-parsable / negative as `None`.
      `effective_thinking_budget(configured)` applies precedence config → env
      (`THE_ONE_ANTHROPIC_THINKING_BUDGET`, read at call time) → default `0`; returns `0`
      (disabled) or a value clamped up to `≥ 1024` (Anthropic floor). Unit-tested across the
      matrix (config wins over env; `0` disables; blank→env→default; `500`→`1024`; junk→off).
- [x] `AnthropicProvider.__init__` reads `config["thinking_budget"]` via
      `_coerce_thinking_budget` into `self._configured_thinking_budget` (mirrors Ollama's
      `_configured_num_ctx` at `ollama_provider.py:176–179`); absent/non-dict config → `None`.
- [x] When the resolved budget `> 0` and thinking is not suppressed, `_build_kwargs` sets
      `kwargs["thinking"] = {"type": "enabled", "budget_tokens": <budget>}`, forces
      `kwargs["temperature"] = 1`, and **raises** `max_tokens` so it exceeds the budget with
      answer headroom (never lowers a caller's `max_tokens`). Asserted via `_CreateRecorder`
      call-kwargs.
- [x] When the resolved budget is `0` (disabled), `_build_kwargs` sets **no** `thinking` key and
      leaves `temperature` / `max_tokens` at the caller's values — byte-identical to today's
      request (regression-guarded).
- [x] `enable_thinking: bool | None = None` (keyword-only) is added to `LLMProvider.complete`
      and `.stream` and to every concrete provider override. `enable_thinking=False` forces
      thinking OFF on the Anthropic path regardless of configured budget; `None` uses the
      configured budget. Non-Anthropic providers accept it without error and behave unchanged.
- [x] `LLMProvider.stream`'s **concrete default body** (`base.py:355–374`, which calls
      `self.complete(...)`) **forwards** `enable_thinking` to that `complete()` call — so a
      provider relying on the default `stream` (e.g. a complete-only provider) doesn't silently
      drop the signal. (Latent DD5 correctness: a future adapter honoring `enable_thinking`
      through the default stream path works without a follow-up "bug fix".)
- [x] The four `LLMProvider` test doubles in `tests/test_connectors_inference.py`
      (`_RaisingProvider` `:555`, and the three `_CapturingProvider`s `:676`/`:718`/`:759`)
      accept `enable_thinking` (add `enable_thinking: bool | None = None` or `**kwargs` to their
      `complete` signatures) — otherwise the new `enable_thinking=False` classifier call
      `TypeError`s them and this leg's own inference-suite verification breaks.
- [x] `complete()` captures `thinking` / `redacted_thinking` blocks from `response.content`
      into `Message.thinking` (a `type="thinking"` block → `ThinkingBlock(type="thinking",
      thinking=..., signature=...)`; a `type="redacted_thinking"` block →
      `ThinkingBlock(type="redacted_thinking", data=...)`), threaded via
      `Message.assistant(..., thinking=blocks)`. `text` / `tool_use` handling is unchanged.
- [x] `_stream_inner` captures the same blocks from `get_final_message()` into the synthesized
      assistant `Message` (the `is_final` chunk's `.message.thinking`); the answer still streams
      via `text_stream` and no thinking text leaks into the streamed `content` deltas.
- [x] `_inference.py`'s classifier call passes `enable_thinking=False` — a fixtured test with an
      Anthropic provider that has a configured budget asserts the classifier's `complete()` is
      issued with **no** `thinking` kwarg.
- [x] Non-thinking-model error is non-fatal: a fixtured `BadRequestError` mentioning an
      unsupported-thinking/model condition (not `temperature`, not `tools.N`) propagates cleanly
      out of `complete()`/`stream()` (falls through to the plain re-raise; not swallowed, not
      mis-caught by the temperature/tools branches) — so the agent loop surfaces it as an error
      bubble without wedging the session.
- [x] A `@pytest.mark.live` premise-probe test exists in `test_anthropic_live.py` (real key +
      thinking-capable model → `text_stream` yields answer text AND `get_final_message()`
      carries a `thinking` block with a non-empty `signature`). It is **deselected by default**
      (`live` marker) and is NOT required to run in this leg; noted for Leg 06/HAT.
- [x] Full unit suite green (minus the known aiosqlite teardown flake); no existing Anthropic
      test regresses.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py -x --timeout 30`
  — new capture/enablement/suppression/budget tests pass; existing sanitize + temperature-retry
  + tools.N tests still pass.
- `grep -n "def complete\|def stream" the_one/llm/*.py` — confirm every override carries
  `enable_thinking`.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connectors_inference.py -x --timeout 30`
  (or the inference test module) — the classifier path still returns yes/no and now sends no
  thinking kwarg.
- `make test-unit` once at leg end — green minus the known teardown flake.
- Live probe (operator, later): `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_anthropic_live.py -m live -k thinking` with a real key — deferred to Leg 06/HAT.

## Implementation Guidance

1. **Add the budget resolver** near the top of `anthropic_provider.py` (module level, mirroring
   `ollama_provider.py:40–108`):

   ```python
   _THINKING_BUDGET_ENV = "THE_ONE_ANTHROPIC_THINKING_BUDGET"
   _MIN_THINKING_BUDGET = 1024          # Anthropic hard floor for budget_tokens
   DEFAULT_THINKING_BUDGET = 4096       # suggested magnitude when enabled (Leg 05 UI pre-fill)
   _ANSWER_HEADROOM_MIN = 4096          # DD6: answer needs room ABOVE the thinking budget

   def _coerce_thinking_budget(value: Any) -> int | None:
       """Coerce a free-form config value to int | None. 0 is MEANINGFUL
       (explicit disable); None means unset (fall through to env/default).
       bool rejected; blank/negative/non-parsable → None."""
       if isinstance(value, bool):
           return None
       if isinstance(value, int):
           return value if value >= 0 else None
       if isinstance(value, str):
           s = value.strip()
           if not s:
               return None
           try:
               parsed = int(s)
           except ValueError:
               return None
           return parsed if parsed >= 0 else None
       return None

   def effective_thinking_budget(configured: int | None) -> int:
       """Resolve the request budget. Precedence: config → env → default(0=off).
       Returns 0 (disabled) or a value clamped up to _MIN_THINKING_BUDGET."""
       if configured is None:
           configured = _coerce_thinking_budget(os.environ.get(_THINKING_BUDGET_ENV))
       if configured is None or configured <= 0:
           return 0
       return max(configured, _MIN_THINKING_BUDGET)
   ```

   Note: `os` is already imported (`anthropic_provider.py:4`). If you prefer, reuse an
   `_env_int`-style helper, but reading the env inside `effective_thinking_budget` (call time)
   matches the Ollama resolver's semantics.

2. **Read config in `__init__`** (`anthropic_provider.py:84–89`), mirroring Ollama
   (`:176–179`):

   ```python
   config = kwargs.get("config")
   self._configured_thinking_budget: int | None = (
       _coerce_thinking_budget(config.get("thinking_budget")) if isinstance(config, dict) else None
   )
   ```

   **Config key contract:** `config["thinking_budget"]`. Leg 05's admin field MUST write this
   exact key.

3. **Import `ThinkingBlock`** — extend the base import (`anthropic_provider.py:13–21`).

4. **Thread `enable_thinking` + enable/enforce in `_build_kwargs`** (`:115–157`). Add
   `enable_thinking: bool | None = None` to its signature and, after the `kwargs` dict is built
   (`:130–135`), before the `system`/`tools` blocks or at the end:

   ```python
   budget = effective_thinking_budget(self._configured_thinking_budget)
   if budget > 0 and enable_thinking is not False:
       kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
       kwargs["temperature"] = 1  # DD6: API rejects any other temperature with thinking on
       # DD6: raise (never shrink) max_tokens so the answer has headroom above the budget.
       kwargs["max_tokens"] = max(kwargs["max_tokens"], budget + _ANSWER_HEADROOM_MIN)
   ```

   (`enable_thinking is not False` → `None`/`True` use the configured budget; `False`
   suppresses.)

5. **Thread `enable_thinking` through `complete` and `stream`** (`:159–165`, `:206–212`): add
   `*, enable_thinking: bool | None = None` to each signature and pass it into `_build_kwargs`
   (both the initial call and — harmless — the temperature-retry rebuild, since the retry reuses
   the same `kwargs`; you only need to pass it on the initial `_build_kwargs` call because the
   retry mutates the existing `kwargs`).

6. **Capture in `complete()`** (`:189–204`) — extend the block loop and the return:

   ```python
   thinking_blocks: list[ThinkingBlock] = []
   for block in response.content:
       if block.type == "text":
           content += block.text
       elif block.type == "tool_use":
           tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
       elif block.type == "thinking":
           thinking_blocks.append(
               ThinkingBlock(type="thinking", thinking=block.thinking, signature=block.signature)
           )
       elif block.type == "redacted_thinking":
           thinking_blocks.append(ThinkingBlock(type="redacted_thinking", data=block.data))
   ...
   return Message.assistant(
       content=content, tool_calls=tool_calls, usage=usage, thinking=thinking_blocks
   )
   ```

7. **Capture in `_stream_inner`** (`:261–276`) — the identical block-loop extension over
   `final.content`, threading `thinking=thinking_blocks` into the `Message.assistant(...)` at
   `:276`. Leave the `text_stream` loop (`:253–258`) untouched (the answer streams; thinking is
   read whole from the final message — DD2).

8. **Add `enable_thinking` to the base contract + other providers.** In `the_one/llm/base.py`,
   add `*, enable_thinking: bool | None = None` to the abstract `LLMProvider.complete` and to
   `LLMProvider.stream`. `stream` is a **concrete default** (`base.py:355–374`) that calls
   `self.complete(...)` positionally — **forward the param**: pass `enable_thinking=enable_thinking`
   into that `complete()` call so it isn't dropped for default-stream providers. Then
   `grep -n "def complete\|def stream" the_one/llm/*.py` and add the same keyword-only param to
   each real override (ignored in the body). **Confirmed by design review:** only
   `anthropic_provider.py`, `openai_provider.py`, `ollama_provider.py`, `mock.py` override —
   **OpenRouter inherits from `OpenAIProvider` and needs no edit** (verify with the grep).

9. **Suppress on the classifier** (`_inference.py:325–330`): add `enable_thinking=False` to the
   `provider.complete(...)` call.

9b. **Update the inference test doubles.** `tests/test_connectors_inference.py` defines four
   `LLMProvider` doubles whose `complete` signature lacks `enable_thinking`/`**kwargs`:
   `_RaisingProvider` (`:555`) and three `_CapturingProvider`s (`:676`, `:718`, `:759`). Step 9's
   new kwarg would `TypeError` them (silently swallowed by the inference try/except → the
   `_CapturingProvider` tests fail on an unset `captured["prompt"]`). Add
   `enable_thinking: bool | None = None` (or `**kwargs`) to all four `complete` signatures.

10. **Tests** (`tests/test_anthropic_provider.py`) — using the existing scaffolding:
    - **capture (complete):** a `_StubResponse` whose `content` mixes `text`, `thinking`
      (`_StubContentBlock("thinking", thinking="...", signature="sig")`), and `tool_use` →
      `complete()` returns a `Message` with `.thinking` carrying the block (signature intact) AND
      the tool call AND the text.
    - **capture (redacted):** a `redacted_thinking` block → `ThinkingBlock(type="redacted_thinking",
      data=...)`, no text/signature.
    - **capture (stream):** a `_StreamCM` whose `final` carries a thinking block → the `is_final`
      chunk's `.message.thinking` has it; the streamed `content` deltas contain only the answer
      text.
    - **enablement:** build the provider with `config={"thinking_budget": 4096}`; a `complete()`
      records `kwargs["thinking"] == {"type": "enabled", "budget_tokens": 4096}`,
      `kwargs["temperature"] == 1`, `kwargs["max_tokens"] > 4096`. **Note:** the existing
      `_provider_with_create` helper (`:83–88`) hardcodes `AnthropicProvider(model="claude-test")`
      with **no `config`** — either extend it to forward `**kwargs` to the constructor, or have
      the budget-bearing tests construct the provider directly (setting `ANTHROPIC_API_KEY` +
      monkeypatching `client.messages.create`) as the helper does.
    - **max_tokens raised, not shrunk:** with `config={"thinking_budget": 20000}` and the default
      `max_tokens=16384`, the recorded `max_tokens` is `> 20000` (raised), never `16384`.
    - **disabled passthrough:** no budget (or `0`) → no `thinking` key, `temperature`/`max_tokens`
      unchanged.
    - **suppression:** `config={"thinking_budget": 4096}` + `complete(..., enable_thinking=False)`
      → no `thinking` kwarg, `temperature` unchanged.
    - **budget resolver matrix:** direct unit tests of `_coerce_thinking_budget` /
      `effective_thinking_budget` (config>env precedence via `monkeypatch.setenv`; `0` disables;
      blank→env; `500`→`1024`; `bool`/junk→off).
    - **non-thinking-model error:** a `_CreateRecorder` side-effect raising a `BadRequestError`
      whose message names an unsupported-thinking/model condition (no "temperature", no "tools.")
      → `complete()` re-raises it unchanged (`ei.value is err`).
    - **inference suppression:** an Anthropic provider with a budget, driven through the
      classifier path (or a direct `complete(enable_thinking=False)`), records no thinking kwarg.
    Author the `@pytest.mark.live` premise probe in `tests/test_anthropic_live.py` (guarded by
    the `live` marker; not run autonomously).

## Edge Cases

- **`0` vs `None` in the config.** `0` is explicit-disable and must NOT fall through to env.
  `_coerce_thinking_budget(0)` returns `0` (not `None`); `effective_thinking_budget(0)` returns
  `0`. Blank string / missing key → `None` → env/default. This is the one place the resolver
  differs from `_coerce_num_ctx` (which treats `0` as `None`); call it out in a comment.
- **Budget below the floor.** A configured `1..1023` clamps up to `1024` (DD6), not disabled.
- **`max_tokens` already above budget.** The default `16384` exceeds a `4096` budget → no raise;
  the raise only bites for large budgets or the tiny inference path (which is anyway suppressed).
- **Temperature-retry under thinking.** If a `temperature` 400 fires with thinking on, the retry
  pops `temperature` (falls back to Anthropic's thinking default of 1) — benign. Do NOT change
  this branch.
- **Redacted block has no `thinking`/`signature`.** Capture only `data`; the other fields stay
  `None`.
- **Thinking + tool_use ordering on capture.** Capture order follows `response.content` order
  (Anthropic emits thinking before tool_use). Leg 03 (replay) is responsible for re-emitting
  thinking BEFORE tool_use on the next request — not this leg. Preserve list order as received.
- **Non-thinking-capable model under a budget.** Surfaces as a `BadRequestError`; must propagate
  (error bubble), not wedge. Covered by the non-fatal-error test.

## Files Affected

- `the_one/llm/anthropic_provider.py` — resolver + constants; `__init__` config read;
  `_build_kwargs` enablement/enforcement + `enable_thinking`; capture in `complete` +
  `_stream_inner`; `ThinkingBlock` import.
- `the_one/llm/base.py` — `enable_thinking` on `LLMProvider.complete`/`.stream`.
- `the_one/llm/openai_provider.py`, `openrouter_provider.py`, `ollama_provider.py`, `mock.py` —
  accept `enable_thinking` (ignored; verify which actually override).
- `the_one/connectors/_inference.py` — `enable_thinking=False` on the classifier call.
- `tests/test_connectors_inference.py` — add `enable_thinking` (or `**kwargs`) to the four
  `LLMProvider` doubles (`_RaisingProvider`, three `_CapturingProvider`s) so the new kwarg
  doesn't `TypeError` them.
- `tests/test_anthropic_provider.py` — capture/enablement/enforcement/suppression/resolver/error
  tests.
- `tests/test_anthropic_live.py` — `@pytest.mark.live` premise probe (authored, not run here).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (new Anthropic tests + full unit suite green minus known teardown flake)
- [x] Update flight-log.md with the Leg 02 progress entry (incl. the off-by-default budget
      Decision and the live-probe-deferred note)
- [x] Set this leg's status to `landed` (NOT `completed` — commit deferred to Phase 2d)
- [x] Do NOT commit; do NOT check off the leg in flight.md; do NOT touch mission.md
- [x] Signal `[HANDOFF:review-needed]`
