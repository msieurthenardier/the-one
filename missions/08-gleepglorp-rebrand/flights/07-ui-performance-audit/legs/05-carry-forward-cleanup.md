# Leg: carry-forward-cleanup

**Status**: completed
**Flight**: [UI Performance Audit](../flight.md)

## Objective

Close out the 4 small F6.5 debrief Action Items that didn't fit into L01-L04:

1. **F6.5 AI #1** — refactor OpenRouter's "skip `super().__init__()`" carve-out into a base-class `_init_provider_state()` hook so future state additions to `LLMProvider.__init__` don't silently break OpenRouter
2. **F6.5 AI #2** — explicit no-op `_resolve_max_context_tokens` override on `AnthropicProvider` with migration-template docstring
3. **F6.5 AI #3** — unit test for `_process_and_broadcast`'s live-read of `max_context_tokens` (pins the F6.5 L04 HAT-cycle bugfix against regression)
4. **F6.5 AI #6** — `agents.md` note about `make rebuild` Chromium wipe + how to recover via `make _ensure-playwright` (recurring operator footgun across F5/F6/F6.5/F7 HATs)

Pure cleanup — no architectural pivots, no new features. Each item is small (≤30 LOC); all four together land in a single leg.

## Context

- **F6.5 debrief AI #1**: `the_one/llm/openrouter_provider.py:63-65` "Override constructor entirely — do NOT call super().__init__()"; line 105 manually sets `self._max_context_tokens_resolved: bool = False`. Tripwire: any future state added to `LLMProvider.__init__` silently breaks OpenRouter at runtime.
- **F6.5 debrief AI #2**: `the_one/llm/anthropic_provider.py:15 — "max_context_tokens = 200_000"`; no resolver override exists. Latent staleness vector when Anthropic ships a non-200k Claude model.
- **F6.5 debrief AI #3**: `the_one/interfaces/web/app.py:752-756` has the F6.5 L04 HAT-cycle live-read fix (no capture; read `session.agent.llm.max_context_tokens` inline at usage emission). No test pins the contract; any future maintainer could resurrect the eager-capture pattern.
- **F6.5 debrief AI #6**: `make rebuild` wipes Playwright Chromium. Documented in F5/F6/F6.5/F7 flight logs but never promoted to `agents.md`. Operators hit this every flight.

## Inputs

- `the_one/llm/base.py` — `LLMProvider.__init__` from F6.5 L01 sets `_max_context_tokens_resolved = False`
- `the_one/llm/openrouter_provider.py:63-115` — `__init__` that skips super
- `the_one/llm/anthropic_provider.py:15` — class-level `max_context_tokens = 200_000`; no `_resolve_max_context_tokens` override
- `the_one/interfaces/web/app.py:~755-790` — `_process_and_broadcast` usage emission with live-read
- `the_one/agents.md` — operator-facing test/measurement docs

State that must be true:
- L01-L04 landed; broad pytest 1678p/4s/375d
- Branch `flight/07-ui-performance-audit` with all four prior legs' work uncommitted

## Outputs

Files modified:

**AI #1 (OpenRouter init hook)**:
- `the_one/llm/base.py` — add a new instance method `_init_provider_state(self)` to `LLMProvider` that initializes `self._max_context_tokens_resolved = False` (and any future state). `LLMProvider.__init__` calls it. Subclasses that skip `super().__init__()` (i.e., OpenRouter) must call `self._init_provider_state()` directly to inherit the state initialization.
- `the_one/llm/openrouter_provider.py` — replace the manual `self._max_context_tokens_resolved = False` line with `self._init_provider_state()`. Add a docstring note explaining the contract: any subclass that skips super MUST call `_init_provider_state()`.

**AI #2 (Anthropic explicit override)**:
- `the_one/llm/anthropic_provider.py` — add an explicit `async def _resolve_max_context_tokens(self) -> None:` method that's a documented no-op. Docstring: "Anthropic stays at the class-default 200_000 for all current Claude models (Claude 3.5 Sonnet, Haiku, Opus; Claude 4.x family all share the 200k window). If Anthropic ships a model with a different context window, this override should populate `self.max_context_tokens` via a model-name table (mirroring OpenAI's `OPENAI_MODEL_CONTEXT` pattern in `openai_provider.py`)."

**AI #3 (live-read unit test)**:
- `tests/test_process_and_broadcast_live_read.py` (NEW) — single test that:
  1. Constructs a mock `Agent` whose `.llm.max_context_tokens` is mutable
  2. Drives `_process_and_broadcast` to the usage-emission point (mock `agent.step` yielding an assistant Message with usage)
  3. BEFORE emission, mutate `agent.llm.max_context_tokens = 32000`
  4. Capture the broadcast `usage` event; assert `event["max_context_tokens"] == 32000` (NOT the value at function entry)

**AI #6 (agents.md make rebuild note)**:
- `the_one/agents.md` — add a new section `### `make rebuild` wipes Playwright Chromium` documenting the symptom (browser tests fail with 311+ errors immediately after rebuild) and the recovery (`make _ensure-playwright`). Section goes near the Performance Measurement section (Operator Notes).

State after:
- F6.5 AI #1, #2, #3, #6 all closed
- Broad pytest pass count grows by 1 (the new live-read test)
- Browser suite preserved at 316p/35s

## Acceptance Criteria

- [ ] **AI #1**: `LLMProvider._init_provider_state(self)` exists and initializes `_max_context_tokens_resolved = False`; `LLMProvider.__init__` calls it; `OpenRouterProvider.__init__` calls `self._init_provider_state()` instead of manually setting the sentinel; docstring on `_init_provider_state` documents the "subclasses that skip super MUST call this" contract
- [ ] **AI #2**: `AnthropicProvider._resolve_max_context_tokens(self) -> None` exists as a documented no-op with a migration-template docstring pointing to `openai_provider.py:OPENAI_MODEL_CONTEXT` as the future pattern
- [ ] **AI #3**: `tests/test_process_and_broadcast_live_read.py` exists; pins the live-read contract; test passes; calling the test under a regression scenario (manually re-introducing `max_context = session.agent.llm.max_context_tokens` capture at function entry) makes it FAIL
- [ ] **AI #6**: `the_one/agents.md` has a section documenting the `make rebuild` → Chromium-wipe → `make _ensure-playwright` recovery procedure
- [ ] Broad pytest exits 0 with 1679 passed (1678 baseline + 1 new test); 4 skipped, 375 deselected
- [ ] Browser suite preserved at 316 passing / 35 skipped (no regressions)
- [ ] All four items' diffs are self-contained: `git diff --stat` should show the listed files only

## Verification Steps

- **AI #1**: `grep -n "_init_provider_state" the_one/llm/*.py` returns the new method definition + the openrouter call site. `OpenRouterProvider()` construction (no args, no env keys) succeeds without raising AttributeError on `_max_context_tokens_resolved`.
- **AI #2**: `grep -n "_resolve_max_context_tokens" the_one/llm/anthropic_provider.py` returns the new override. Calling `await AnthropicProvider(...)._resolve_max_context_tokens()` returns None without raising.
- **AI #3**: `docker exec the-one pytest tests/test_process_and_broadcast_live_read.py -x --timeout 30 -v` — passes. Sanity-check: temporarily revert the live-read fix in `app.py` to verify the test fails (then restore the fix).
- **AI #6**: `grep -n "make rebuild" the_one/agents.md` returns the new section header.
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1679p/4s/375d.
- **Browser suite**: preserved at 316/35.

## Implementation Guidance

1. **`the_one/llm/base.py`** — add `_init_provider_state`:

   ```python
   class LLMProvider(ABC):
       # ... existing class attrs ...

       def __init__(self) -> None:
           self._init_provider_state()

       def _init_provider_state(self) -> None:
           """Initialize per-instance provider state.

           Called by ``LLMProvider.__init__``. Subclasses that override
           ``__init__`` AND skip ``super().__init__()`` (e.g.,
           ``OpenRouterProvider`` — see its docstring at lines 63-65)
           MUST call ``self._init_provider_state()`` directly to inherit
           this state. Adding new instance attributes here keeps the
           contract single-source-of-truth.

           M08 F7 L05 (F6.5 debrief AI #1): replaces the prior
           "manually mirror every state addition in OpenRouter" pattern.
           """
           self._max_context_tokens_resolved: bool = False
   ```

2. **`the_one/llm/openrouter_provider.py`** — replace the manual sentinel set with the hook call. Around line 105:

   ```python
   # BEFORE:
   # self._max_context_tokens_resolved: bool = False

   # AFTER:
   # M08 F7 L05 (F6.5 debrief AI #1): defuse the manual-state-mirror
   # tripwire. Future state added to LLMProvider._init_provider_state
   # is automatically inherited.
   self._init_provider_state()
   ```

3. **`the_one/llm/anthropic_provider.py`** — add the explicit no-op override:

   ```python
   class AnthropicProvider(LLMProvider):
       name = "anthropic"
       max_context_tokens = 200_000

       # ... existing __init__ ...

       async def _resolve_max_context_tokens(self) -> None:
           """No-op: all current Claude models share the 200k context window.

           Anthropic's Claude 3.5 (Sonnet/Haiku/Opus) and Claude 4.x family
           all have ``max_context_tokens = 200_000`` (matches the class-level
           default at line 15). When/if Anthropic ships a model with a
           different context window, populate ``self.max_context_tokens``
           here via a model-name table — mirror the pattern in
           ``openai_provider.py:OPENAI_MODEL_CONTEXT``.

           M08 F7 L05 (F6.5 debrief AI #2): explicit no-op replaces the
           prior implicit default-via-no-override pattern. Makes intent
           legible to future maintainers.
           """
           # Intentional no-op
   ```

4. **`tests/test_process_and_broadcast_live_read.py`** (NEW):

   ```python
   """F6.5 L04 HAT-cycle fix regression test (carried into F7 L05 per AI #3).

   `_process_and_broadcast` MUST read `session.agent.llm.max_context_tokens`
   LIVE at usage-event emission, NOT pre-capture it at function entry. The
   pre-capture pattern caused the F6.5 HAT-observed "first message shows
   128k, then jumps to resolved value" bug.

   This test pins the live-read contract by mutating the LLM's
   max_context_tokens BETWEEN function entry and usage emission, then
   asserting the broadcast event reflects the post-mutation value.
   """
   from __future__ import annotations

   import pytest
   from unittest.mock import AsyncMock, MagicMock

   from the_one.interfaces.web.app import _process_and_broadcast
   from the_one.llm.base import Message, Role, TokenUsage

   # ... build a minimal Session + Agent stub, drive _process_and_broadcast,
   #     mutate max_context_tokens before the usage event, assert broadcast
   #     event reflects the mutated value.
   ```

   The test infrastructure pattern: look at existing tests in `tests/test_app_websocket_pause_resume.py` for how to build `StubAgent` + capture `_send_to_session` calls. Use the same scaffolding.

5. **`the_one/agents.md`** — add the new section. Place it near the existing "Operator notes" / "Performance Measurement" sections. Suggested location: under a new `## Operator Reference` heading if no existing operator-notes section, OR as a sibling subsection.

   ```markdown
   ### `make rebuild` wipes Playwright Chromium

   **Symptom**: running `docker exec the-one pytest -m browser` immediately after `make rebuild` fails with hundreds of `Error: BrowserType.launch: Executable doesn't exist at /root/.cache/ms-playwright/...` errors in under 15 seconds (no real test work happened).

   **Cause**: `make rebuild` rebuilds the container image, wiping the cached Playwright Chromium binary from `/root/.cache/ms-playwright/`.

   **Recovery**: run `make _ensure-playwright` on the host. This reinstalls Chromium into the container's cache (~30-60s). Then re-run the browser suite — should pass cleanly.

   **Surfaced in**: F5, F6, F6.5, F7 HATs. Every flight that runs `make rebuild` during execution hits this. Promote to `make rebuild` idempotency in a future maintenance flight; for now, the recovery procedure is the documented workaround.
   ```

6. **Run tests**:
   ```bash
   docker exec the-one pytest tests/test_process_and_broadcast_live_read.py -x --timeout 30 -v
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

7. **Update flight log** + **DO NOT commit** — Flight Director batches commits after this leg (L05 is the last autonomous leg).

## Edge Cases

- **`_init_provider_state` calls**: Anthropic/OpenAI/Ollama all call `super().__init__()` from their `__init__`. After the refactor, that still triggers `_init_provider_state()`. OpenRouter calls `_init_provider_state()` directly (since it skips super). MockProvider / FakeLLM / test doubles don't call super and don't call `_init_provider_state()` — they inherit the unset sentinel state, which is fine since they don't use the resolver path. Verify all 4 real providers work via broad pytest.
- **The Anthropic no-op override**: doesn't change runtime behavior at all — the L01 lazy wrapper short-circuits on first call regardless. The override is documentation-as-code. Verify the AnthropicProvider's resolver flow still completes without error in `tests/test_llm_max_context.py`.
- **The live-read test should not pin too tightly to the test scaffolding**: focus on the contract (`event["max_context_tokens"] == agent.llm.max_context_tokens` at emission time, NOT at function-entry time). Don't pin specific token counts or wall-clock timings.
- **`agents.md` is large**: don't restructure it for the new section. Append-only to existing operator-notes section, or create one if none exists.

## Files Affected

- `the_one/llm/base.py` — add `_init_provider_state` method; refactor `__init__` to call it
- `the_one/llm/openrouter_provider.py` — replace manual sentinel set with `self._init_provider_state()`
- `the_one/llm/anthropic_provider.py` — add explicit no-op `_resolve_max_context_tokens` override
- `tests/test_process_and_broadcast_live_read.py` — NEW
- `the_one/agents.md` — new section on `make rebuild` Chromium wipe

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest 1679p/4s/375d; browser 316/35)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit — Flight Director batches commits after this leg

---

## Citation Audit

5 source-code citations verified against current code at leg design time:
- `the_one/llm/openrouter_provider.py:63-105` — OK
- `the_one/llm/anthropic_provider.py:15` — OK
- `the_one/interfaces/web/app.py` `_process_and_broadcast` usage-emission site (post-F6.5 live-read fix) — OK (live-read pattern confirmed at L04 design time)
- `the_one/llm/base.py` `LLMProvider.__init__` (F6.5 L01 addition) — OK
- `the_one/agents.md` — OK (the operator-docs root)
