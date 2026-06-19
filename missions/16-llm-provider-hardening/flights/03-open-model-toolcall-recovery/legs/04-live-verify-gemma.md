# Leg: live-verify-gemma

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

## Objective

Add a committed `@pytest.mark.live` test that drives `OllamaProvider("gemma3:4b")` against a real
local Ollama with a tool-eliciting prompt and asserts the returned `Message` carries a **recovered**
`ToolCall` **and** that `Message.content` no longer contains a raw ` ```tool ` block — proving the
leg-01/02 recovery+strip works against genuine model output, not just the captured fixture. The test
**self-skips** when Ollama/gemma3:4b is absent so default `make test-unit` stays hermetic.

> **Run convention:** run this test **directly** — `pytest tests/test_ollama_recovery_live.py -m live`
> — NOT via `make test-live` (that target is hardcoded to `tests/test_aiat.py` only). This matches
> the canonical live cross-provider module (`test_llm_provider_cross_provider_history.py:592-593`).
> Broadening the `make test-live` target is out of this leg's scope.

## Context

- Implements the flight's `live-verify-gemma` leg and the "`@pytest.mark.live` test confirms
  recovery against real gemma3:4b" checkpoint. Distinct from leg 03's throwaway probe: this test is
  **committed** and re-runnable via `pytest tests/test_ollama_recovery_live.py -m live`.
- The recovery path is already wired (leg 02): `OllamaProvider.complete()`/`stream()` call
  `recover_and_strip` when no structured `tool_calls` arrive, mapping recovered calls to `ToolCall`s
  with synthesized ids and stripping the recognized block.
- **Live LLMs are non-deterministic** — the repo's standing convention (see
  `tests/test_llm_provider_cross_provider_history.py:599-603`) is that live tests are **confidence
  tests**, not exact-output pins. This test asserts the *mechanism* (recovery fired + strip
  happened) under a prompt engineered to reliably elicit the fenced form, and treats genuine model
  non-cooperation as **inconclusive (skip)**, never a hard red.
- gemma3:4b is **non-tool-capable** (`supports_tools()` → `False`), so tools are never offered; the
  model emits the call as loose text, which is exactly the recovery trigger.

## Inputs

- Live Ollama with **gemma3:4b** (verified reachable at flight start). On this host Ollama is at
  `http://localhost:11434`; the test honors `LIVE_OLLAMA_BASE_URL` (canonical resolver default is
  `http://host.docker.internal:11434/v1` for the container path).
- `the_one/llm/ollama_provider.py` (recovery wired, leg 02).
- The canonical Ollama self-skip resolver `_resolve_ollama` at
  `tests/test_llm_provider_cross_provider_history.py:545-585` (reuse its `/api/tags`-probe +
  `pytest.skip` + `LIVE_OLLAMA_BASE_URL`/`LIVE_OLLAMA_MODEL` pattern, but **require gemma3:4b
  specifically**).
- The `live` marker is registered (`pyproject.toml` markers; deselected by default `addopts`).

## Outputs

- `tests/test_ollama_recovery_live.py` — one (or two) `@pytest.mark.live` test(s), self-skipping,
  deselected from `make test-unit`, run under `make test-live`-style invocation.

## Acceptance Criteria

- [x] **Test is `@pytest.mark.live` and self-skips** when Ollama is unreachable OR no gemma3 model
      is loaded — via a local `/api/tags` probe + `pytest.skip` with a clear reason. Default
      `make test-unit` does NOT **collect** it (it is *deselected* by the `-m 'not live'` addopts —
      a different mechanism from `pytest.skip`, which only fires when the test is collected under
      `-m live`). Verify: absent from a `make test-unit` run; present under `-m live`.
      *(Confirmed: `--collect-only` under the default profile → 1 deselected, no tests collected.)*
- [x] **Drives real gemma3:4b** through `OllamaProvider(model="gemma3:4b", base_url=<resolved>)`
      with a prompt engineered to elicit a single fenced ` ```tool ` call (directive system/user
      prompt naming a `get_weather(city=...)`-style tool and instructing the model to respond ONLY
      with the fenced call). No `tools=` are offered (gemma is non-tool-capable).
- [x] **Asserts recovery fired**: the returned `Message.tool_calls` is non-empty — at least one
      `ToolCall` with a non-empty `name` and a `dict` `arguments`. (The id is a synthesized
      `f"{name}_{i}"` per DD4; assert the shape, not an exact model-chosen value.)
      *(Live: `ToolCall(id='get_weather_0', name='get_weather', arguments={'city': 'Paris'})`.)*
- [x] **Asserts the raw block was stripped** (DD4): the **call syntax is not rendered** —
      `"get_weather(" not in msg.content` (PRIMARY check, robust to whichever fence tag the model
      chose: ` ```tool `, ` ```python `, or untagged) — AND `"```tool" not in msg.content`.
      Surrounding prose, if any, may remain (the kernel preserves non-span text).
      *(Live: content stripped to `''` — the full span was the fenced block.)*
- [x] **Non-cooperation is inconclusive, not failure**: if after a bounded retry (≤2 attempts) the
      model returns neither a structured nor a recoverable call (e.g. it answered in plain prose),
      the test `pytest.skip`s with a message explaining the model didn't emit a recoverable form
      this run — it does NOT fail. (Confidence-test stance; documented in a comment.)
      *(Implemented as a 3-attempt bounded retry → `pytest.skip` with the last raw content.)*
- [x] **Runs green live**: with gemma3:4b present, `PYTHON=.venv/bin/python LIVE_OLLAMA_BASE_URL=http://localhost:11434/v1 .venv/bin/python -m pytest tests/test_ollama_recovery_live.py -m live -v`
      passes (recovery fired) — capture the result in the flight log.
      *(Live: 1 passed in 4.55s on attempt 1; recorded in flight log Leg Progress.)*
- [x] **`make test-unit` stays green and hermetic** (the live test is deselected) — still
      3262 passed / 18 skipped (+0; the live test adds to the live-marked, default-deselected set).
      *(Confirmed: 3262 passed / 18 skipped / 541 deselected — deselected +1 vs leg 03's 540.)*

## Verification Steps

- `PYTHON=.venv/bin/python LIVE_OLLAMA_BASE_URL=http://localhost:11434/v1 .venv/bin/python -m pytest tests/test_ollama_recovery_live.py -m live -v` — passes against local gemma3:4b (or skips with a clear reason if the model declines to emit a recoverable form / is absent).
- `make test-unit` — full hermetic suite green; the new live test is NOT collected.
- `grep -n "pytest.mark.live" tests/test_ollama_recovery_live.py` — the marker is present.

## Implementation Guidance

1. **Resolver** — write a small **local `_resolve_gemma()`** mirroring `_resolve_ollama`
   (`test_llm_provider_cross_provider_history.py:545-585`) rather than importing it — importing
   would inherit its "first available / qwen-preferred" order and skip whenever a non-gemma model
   sorts first. `_resolve_gemma()` probes `{base}/api/tags`, `pytest.skip`s if unreachable, then
   **matches gemma by substring**: skip unless `any("gemma3" in n for n in available_names)`; honor a
   `LIVE_OLLAMA_MODEL` exact override (so `gemma3:4b-instruct-q4`-style tags still run). Return
   `(base_url, model)`. Keep the `LIVE_OLLAMA_BASE_URL` env override so the test runs both
   in-container (`host.docker.internal`) and on this host (`localhost`).

2. **Eliciting prompt** — gemma3:4b follows directive instructions. Use a system (or user) prompt
   like: *"You can call a tool `get_weather(city)`. To call it, output exactly one fenced block:*
   ` ```tool ` *newline* `get_weather(city='<city>')` *newline* ` ``` ` *and nothing else."* Then a
   user turn: *"What's the weather in Paris?"*. This reliably elicits the captured fixture's form.

3. **Call + assert**:
   ```python
   prov = OllamaProvider(model=model, base_url=base_url)
   history = [Message(role=Role.SYSTEM, content=DIRECTIVE),
              Message(role=Role.USER, content="What's the weather in Paris?")]
   # bounded retry for non-determinism (temperature defaults to 0.0 in complete())
   last = ""
   for _ in range(3):
       msg = await prov.complete(history)
       last = msg.content
       if msg.tool_calls:
           break
   else:
       pytest.skip(f"gemma3 did not emit a recoverable tool-call form in 3 attempts "
                   f"(non-deterministic; last content: {last!r})")
   tc = msg.tool_calls[0]
   assert tc.name and isinstance(tc.arguments, dict)
   assert "get_weather(" not in msg.content   # primary strip check (fence-tag agnostic)
   assert "```tool" not in msg.content
   ```
   No explicit client cleanup is needed: `OllamaProvider.complete()` opens its `httpx.AsyncClient`
   in a per-call `async with` (`ollama_provider.py:124-128`) and there is no persistent client —
   base `aclose()` and `_aclose_provider_client` are no-ops for Ollama. Log each attempt's raw
   content so a chronic-skip is diagnosable from the flight log.

4. **Optional second assertion (acceptable variation)** — the flight allows asserting at the
   provider level, the `/api/chat` level, or both. This leg does the **provider level**; the
   `/api/chat` end-to-end is leg 05's behavior test. Do NOT duplicate the end-to-end here.

## Edge Cases

- **gemma3:4b absent but other models present** → skip (don't silently run against a tool-capable
  model, which wouldn't exercise recovery).
- **Model emits a structured `tool_calls`** (shouldn't happen — tools not offered, gemma
  non-capable) → if it somehow does, `tool_calls` is non-empty via the structured path and the
  strip assertion is vacuously satisfied; the test still passes (recovery-or-structured both yield a
  call). Acceptable; note it in a comment.
- **Model wraps the call in ` ```python ` instead of ` ```tool `** → still recovered (kernel accepts
  untagged/`python` single-call fences); assertion holds. Strip check should also cover a leftover
  ` ```python ` fence — assert the call syntax isn't rendered, or assert `get_weather(` not in
  content as a stronger strip check.
- **Network flake mid-call** → the bounded retry covers one transient; a hard `httpx` error
  propagates (legitimately fails — the service was supposed to be up).

## Files Affected

- `tests/test_ollama_recovery_live.py` — new committed `@pytest.mark.live` test (self-skipping).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Live run executed against local gemma3:4b; result captured in the flight log
- [x] `make test-unit` green and hermetic (live test deselected)
- [x] Update flight-log.md with the leg progress entry (include the live run outcome)
- [x] Set this leg's status to `landed` (deferred-review model — NOT committed)
- [x] Check off this leg in flight.md
- [x] (Not final leg — leg 05 behavior test remains; do NOT commit)
