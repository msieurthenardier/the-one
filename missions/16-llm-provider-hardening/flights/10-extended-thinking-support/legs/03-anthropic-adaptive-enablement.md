# Leg: anthropic-adaptive-enablement

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

> **★ NEW leg from the 2026-07-02 adaptive pivot** (flight-log → Decisions "PIVOT — adaptive-only
> enablement"). Revises Leg 02's enablement wire format + config surface. Leg 02's **capture**
> (both paths) and the **`enable_thinking` suppression contract** are correct and are NOT touched.

## Objective

Replace Leg 02's `budget_tokens` enablement — which **400s on Sonnet 4.6 and every current model**
— with **adaptive-only** enablement (`thinking: {"type": "adaptive"}`, for Sonnet 4.6+), flip the
per-provider config surface from an integer `thinking_budget` to a boolean `thinking_enabled`
(on/off, default off), and drop DD6's now-moot `temperature=1`-force + `max_tokens`-raise.

## Context

- **Pivot rationale (verified).** Anthropic's docs (platform.claude.com → Extended thinking)
  confirm `thinking: {"type": "enabled", "budget_tokens": N}` is **rejected (400)** on Opus 4.8 /
  4.7 / Sonnet 5 / Fable 5 / Mythos 5, and **deprecated (still functional)** on Sonnet 4.6 / Opus
  4.6 — while `thinking: {"type": "adaptive"}` is the correct on-mode for **all Sonnet 4.6+**.
  `budget_tokens` works cleanly only on Opus 4.5 / Haiku 4.5 / older Claude 4. the-one's default
  model is `claude-sonnet-4-6`. Operator decision: support thinking on **Sonnet 4.6+ only →
  adaptive-only** (correct there, and *required* on the hard-400 models); **on/off** control;
  **`effort` deferred to A4**.
- **What stays from Leg 02 (do NOT touch):** thinking/`redacted_thinking` **capture** in
  `complete()` (`anthropic_provider.py:271–300`) and `_stream_inner`
  (`:361–390`); the `enable_thinking` keyword-only param on `LLMProvider.complete`/`.stream` and
  every override + `base.stream` forwarding + the `_inference.py` classifier passing
  `enable_thinking=False` + the inference test doubles. Suppression is mode-independent.
- **What DD6 loses under adaptive:** adaptive has no token budget, so there is nothing to add
  `max_tokens` headroom above → **drop the `max_tokens` raise**. Adaptive does not require
  `temperature=1`, and current Claude models **reject the `temperature` parameter entirely** (the
  existing temperature-retry at `anthropic_provider.py:251–267`/`:326–341` already pops it and
  retries) → **drop the `temperature=1` force**; leave the existing `"temperature": temperature`
  and let the established retry handle rejection. *(Exact adaptive+temperature behavior is
  confirmed live at Leg 07's behavior test; dropping the force is strictly safer than the removed
  budget_tokens path.)*
- **Config precedent** stays the Ollama `num_ctx` shape, but the value is now a **bool** (a
  free-form JSON config value coerced leniently), not an int.

## Inputs

- Legs 01–02 landed. Current `anthropic_provider.py` (post-Leg-02) to be revised:
  - Module-level budget scaffolding to **remove**: `_THINKING_BUDGET_ENV`, `_MIN_THINKING_BUDGET`,
    `DEFAULT_THINKING_BUDGET`, `_ANSWER_HEADROOM_MIN`, `_coerce_thinking_budget`,
    `effective_thinking_budget` (added by Leg 02 near the top of the module).
  - `__init__` (`:137–153`) — reads `config["thinking_budget"]` into `self._configured_thinking_budget`.
  - `_build_kwargs` (`:179–235`) — enablement block at `:223–234`
    (`budget = effective_thinking_budget(...)`; `if budget > 0 and enable_thinking is not False:`
    sets `kwargs["thinking"]={"type":"enabled","budget_tokens":budget}`, `temperature=1`, raised
    `max_tokens`). The message loop is at `:189–193`.
- `tests/test_anthropic_provider.py` — Leg 02's budget-resolver + enablement + suppression +
  max_tokens-raised tests (to be migrated to the boolean/adaptive shape).
- **Grep to confirm blast radius:** `grep -rn "thinking_budget\|budget_tokens\|effective_thinking_budget\|_coerce_thinking_budget\|DEFAULT_THINKING_BUDGET\|_ANSWER_HEADROOM_MIN" the_one/ tests/`
  — current hits are in `anthropic_provider.py`, `test_anthropic_provider.py`, **and
  `test_anthropic_live.py:217`** (the Leg 02 premise probe `test_real_anthropic_streaming_thinking_premise`
  sets `config={"thinking_budget": 1024}`). Only `test_anthropic_provider.py:29–33` *imports* the
  removed symbols (so removal is collection-safe elsewhere); the live probe uses the config key as
  a plain dict key and must be migrated (below). No `the_one/` module outside `anthropic_provider.py`
  references them — confirm with the grep before removing.

## Outputs

- `the_one/llm/anthropic_provider.py`:
  - budget scaffolding removed; a **boolean** resolver added: `_EXTENDED_THINKING_ENV`,
    `_coerce_bool`, `resolve_extended_thinking(configured)`.
  - `__init__` reads `config["thinking_enabled"]` → `self._thinking_enabled_config: bool | None`.
  - `_build_kwargs` computes `thinking_active` **before** the message loop (hoisted — sets up
    Leg 04 replay) and, when active, sets `kwargs["thinking"] = {"type": "adaptive"}`; no
    `temperature`/`max_tokens` manipulation.
- `tests/test_anthropic_provider.py` — boolean-resolver + adaptive-enablement + suppression tests
  replacing the removed budget tests; any test that *activated* thinking via `thinking_budget`
  migrated to `thinking_enabled=True`.

## Acceptance Criteria

- [x] All `budget_tokens` enablement is gone: `grep -n "budget_tokens\|thinking_budget\|effective_thinking_budget\|_coerce_thinking_budget\|DEFAULT_THINKING_BUDGET\|_ANSWER_HEADROOM_MIN" the_one/llm/anthropic_provider.py`
      returns nothing.
- [x] `_coerce_bool(value)` coerces a free-form config/env value to `bool | None`: real bools pass
      through; `"true"/"1"/"yes"/"on"` → True; `"false"/"0"/"no"/"off"/""` → False; unrecognized /
      other types → None (unset). `resolve_extended_thinking(configured)` applies precedence
      config → env `THE_ONE_ANTHROPIC_EXTENDED_THINKING` (read at call time) → default **False**.
- [x] `AnthropicProvider.__init__` reads `config["thinking_enabled"]` via `_coerce_bool` into
      `self._thinking_enabled_config` (absent/non-dict config → None).
- [x] When thinking is active (`resolve_extended_thinking(self._thinking_enabled_config)` True and
      `enable_thinking is not False`), `_build_kwargs` sets `kwargs["thinking"] == {"type":
      "adaptive"}` and sets **no** `budget_tokens`. `temperature` and `max_tokens` are left at the
      caller's values (no forcing) — asserted via `_CreateRecorder` call kwargs.
- [x] When thinking is disabled (no config / `thinking_enabled` False), `_build_kwargs` sets **no**
      `thinking` key — byte-identical to a non-thinking request.
- [x] `enable_thinking=False` suppresses thinking even when `thinking_enabled` is True (no
      `thinking` key) — the `_inference.py` classifier path stays thinking-free.
- [x] `thinking_active` is computed **once, before** the message loop in `_build_kwargs` (so
      Leg 04 can thread it into `_to_api_message`). Its value is
      `resolve_extended_thinking(self._thinking_enabled_config) and enable_thinking is not False`.
- [x] Leg 02's **capture** behavior is unchanged: thinking/`redacted_thinking` blocks are still
      captured into `Message.thinking` on both `complete()` and streaming (capture tests still
      pass, migrated only where they set enablement config).
- [x] Config key contract: `config["thinking_enabled"]` (bool). **Leg 06's admin toggle writes
      this exact key.**
- [x] Full unit suite green minus the known aiosqlite teardown flake; `test_anthropic_provider.py`
      green; no other module referenced the removed budget symbols.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py -x --timeout 30`
  — new resolver/adaptive-enablement/suppression tests pass; capture tests still pass; old
  budget-resolver/max_tokens-raise tests removed (not left failing).
- `grep -rn "thinking_budget\|budget_tokens\|effective_thinking_budget" the_one/ tests/` — only
  historical references in artifacts/flight-log; none in `the_one/` source.
- `make test-unit` once at leg end — green minus the known teardown flake.
- Adaptive + temperature behavior confirmed live at Leg 07 (behavior test).

## Implementation Guidance

1. **Remove the budget scaffolding** near the top of `anthropic_provider.py` (the Leg 02 block:
   `_THINKING_BUDGET_ENV`, `_MIN_THINKING_BUDGET`, `DEFAULT_THINKING_BUDGET`, `_ANSWER_HEADROOM_MIN`,
   `_coerce_thinking_budget`, `effective_thinking_budget`).

2. **Add the boolean resolver** in its place:

   ```python
   _EXTENDED_THINKING_ENV = "THE_ONE_ANTHROPIC_EXTENDED_THINKING"

   def _coerce_bool(value: Any) -> bool | None:
       """Coerce a free-form config/env value to bool, or None when unset/unrecognized.
       Handles real bools, ints, and the common string encodings a JSON config
       round-trip or an env var produces. None (unset) lets the resolver fall through."""
       if isinstance(value, bool):
           return value
       if isinstance(value, int):  # bool already handled above
           return value != 0
       if isinstance(value, str):
           s = value.strip().lower()
           if s in ("1", "true", "yes", "on"):
               return True
           if s in ("0", "false", "no", "off", ""):
               return False
           return None
       return None

   def resolve_extended_thinking(configured: bool | None) -> bool:
       """Precedence: per-provider config → env THE_ONE_ANTHROPIC_EXTENDED_THINKING → default False."""
       if configured is not None:
           return configured
       env = _coerce_bool(os.environ.get(_EXTENDED_THINKING_ENV))
       return env if env is not None else False
   ```

3. **`__init__`** (`:143–153`): replace the `thinking_budget` read with

   ```python
   config = kwargs.get("config")
   self._thinking_enabled_config: bool | None = (
       _coerce_bool(config.get("thinking_enabled")) if isinstance(config, dict) else None
   )
   ```

4. **`_build_kwargs`** (`:179–235`): compute `thinking_active` **before** the message loop, and
   replace the enablement block:

   ```python
   thinking_active = (
       resolve_extended_thinking(self._thinking_enabled_config) and enable_thinking is not False
   )
   system_prompt = ""
   api_messages = []
   for m in messages:
       if m.role == Role.SYSTEM:
           system_prompt = m.content
       else:
           api_messages.append(self._to_api_message(m))  # Leg 04 adds thinking_active here
   ...
   # (replaces the Leg 02 budget block at :223-234)
   if thinking_active:
       # Adaptive-only (M16 F10 pivot): Sonnet 4.6+ reject budget_tokens; adaptive is the
       # on-mode. No temperature/max_tokens forcing — adaptive has no budget, and newer models
       # reject `temperature` anyway (the existing temperature-retry handles that).
       kwargs["thinking"] = {"type": "adaptive"}
   ```

   Do NOT thread `thinking_active` into `_to_api_message` here — that is Leg 04's replay concern
   (this leg only hoists the flag and uses it for enablement).

5. **Migrate the tests** in `tests/test_anthropic_provider.py`:
   - **Update the module import first** (`test_anthropic_provider.py:29–33`): it currently imports
     `_coerce_thinking_budget` / `effective_thinking_budget` from `anthropic_provider`. Replace with
     `_coerce_bool` / `resolve_extended_thinking`. **If you remove the symbols but leave this
     import, the ENTIRE module fails at collection** and masks every other result — do this in the
     same edit as the removal.
   - Replace the budget-resolver matrix with a `_coerce_bool` / `resolve_extended_thinking` matrix
     (True/False/"true"/"1"/"0"/""/None/junk; config>env precedence via `monkeypatch.setenv`;
     default off). **Include the explicit-`False`-short-circuit case:** `config` False does NOT
     fall through to a truthy env var (the boolean analog of the old
     `test_effective_thinking_budget_zero_disables_and_does_not_fall_through`).
   - Replace the enablement test: `config={"thinking_enabled": True}` → recorded
     `kwargs["thinking"] == {"type": "adaptive"}`, no `budget_tokens`, AND — as the load-bearing
     proof DD6's forcing is gone — assert `sent["temperature"] == 0.0` (caller's) and
     `sent["max_tokens"] == <caller value>` (unchanged).
   - Keep disabled-passthrough + suppression tests, migrated to the boolean config.
   - **Remove** the now-obsolete tests (budget-resolver `0/blank/500→1024`, `max_tokens` raised,
     `budget_tokens` shape) — do not leave them failing.
   - Migrate every test that set `config={"thinking_budget": ...}` to `config={"thinking_enabled":
     True}` — including the error-path tests `test_non_thinking_model_error_reraised_unchanged`
     (`:792`) and `..._stream` (`:807`) which set a budget config (they won't break — plain dict
     key — but go stale). Capture tests set no enablement config and need no change (grep to
     confirm).
   - **Migrate the live probe** `test_real_anthropic_streaming_thinking_premise`
     (`tests/test_anthropic_live.py:217`): change `config={"thinking_budget": 1024}` →
     `config={"thinking_enabled": True}` and target a **Sonnet 4.6+** model. The probe's premise
     (does `text_stream` yield the answer + `get_final_message()` carry signed thinking) is
     mode-agnostic, so it stays valuable under adaptive; it remains `@pytest.mark.live` (deselected,
     not run autonomously). Do NOT retire it — Leg 07's behavior test is the acceptance gate, but
     this probe is the cheap isolated premise check.

## Edge Cases

- **`thinking_enabled` unset vs. explicit False.** `_coerce_bool(None)`/missing key → None → falls
  through to env → default False. An explicit `False` in config short-circuits (config wins over
  env). Both yield "off"; the distinction only matters for env-override behavior.
- **Model support is the operator's responsibility.** Adaptive is for Sonnet 4.6+; if the operator
  points a thinking-enabled provider at a pre-4.6 model (e.g. Opus 4.5), Anthropic may reject
  `adaptive` — surfaces as a `BadRequestError` (error bubble, session survives), same non-fatal
  path Leg 02 established. Document in Leg 07.
- **Temperature under adaptive.** Left to the existing retry. If the behavior test (Leg 07) shows
  adaptive needs an explicit temperature handling, add it then and record a deviation — not
  guessed here.
- **`enable_thinking=True` (explicit).** `enable_thinking is not False` is True for both `None` and
  `True`, so an explicit `True` honors the configured enable state (does not force-enable when the
  config is off). This matches Leg 02's semantics.
- **Config-key rename is a silent change for any persisted `thinking_budget`.** After this leg,
  `__init__` reads only `config["thinking_enabled"]`; a persisted provider config still carrying
  `thinking_budget` becomes a no-op (thinking stays off). Given the mid-flight pivot supersedes
  Leg 05's budget UI before it shipped, no persisted `thinking_budget` configs are expected — but
  note it: there is no migration, and an operator who somehow set a budget config must re-enable
  via the Leg 06 toggle.

## Files Affected

- `the_one/llm/anthropic_provider.py` — remove budget scaffolding; add `_coerce_bool` /
  `resolve_extended_thinking` / `_EXTENDED_THINKING_ENV`; `__init__` reads `thinking_enabled`;
  `_build_kwargs` adaptive enablement + hoisted `thinking_active`.
- `tests/test_anthropic_provider.py` — module import swap (`:29–33`); resolver + adaptive-enablement
  + suppression tests replacing the removed budget tests; error-path tests migrated off the budget
  config.
- `tests/test_anthropic_live.py` — migrate the premise probe (`:217`) from `thinking_budget` →
  `thinking_enabled=True` on a Sonnet 4.6+ model (stays `@pytest.mark.live`, deselected).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (new resolver/enablement tests + capture tests + full unit suite green minus
      known teardown flake)
- [x] Update flight-log.md with the Leg 03 progress entry
- [x] Set this leg's status to `landed` (NOT `completed` — commit deferred to Phase 2d)
- [x] Do NOT commit; do NOT check off in flight.md; do NOT touch mission.md
- [x] Signal `[HANDOFF:review-needed]`
