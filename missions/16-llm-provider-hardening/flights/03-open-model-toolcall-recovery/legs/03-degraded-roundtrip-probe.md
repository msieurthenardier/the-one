# Leg: degraded-roundtrip-probe

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

## Objective

Empirically resolve DD5 against **live gemma3:4b**: does a follow-up request whose message history
contains an assistant `tool_calls` block **and** a `role:"tool"` result message get accepted when
`tools` is omitted (the non-tool-capable degraded path)? Record the finding; **if** Ollama rejects
it, adapt both `_to_api_message` degraded branches to a plain-text round-trip and pin it with a
hermetic test.

## Context

- This is the flight's one deliberately-live, empirically-resolved leg (mirrors Flight 2's
  live-probe-resolves-open-question pattern). DD5 + the flight Open Questions pre-authorize the
  adaptation so no re-planning is needed regardless of outcome.
- After leg 02, a recovered text-form call **is dispatched** by the agent loop (DD6), producing an
  assistant message with `tool_calls` (synthesized ids) and a subsequent `ToolResult`. On the
  **next** turn the provider serializes that history via `_to_api_message`
  (`ollama_provider.py:280-302`): the `role:"tool"` branch at `:281-286` and the assistant-
  `tool_calls` branch at `:287-302`. *(DD5 in the flight spec cites the pre-leg-02 line numbers
  `:240-261` for these branches — stale by ~40 lines after leg 02; the live numbers are `:281-286`
  and `:287-302`.)* For a **non-tool-capable** model the request is sent with
  `tools=None` (the capability gate, `supports_tools()` → `False`). The spike only proved Ollama
  400s when tools are *offered*; whether it 400s on tool-call/tool-role *history* with `tools=None`
  is unverified — this leg verifies it.
- **Likely outcome** (flight's prior): round-trips cleanly, no code change. The leg must handle
  both branches deterministically either way.

## Inputs

- Live Ollama reachable with `gemma3:4b` (verified at flight start: capabilities `['completion','vision']`
  — no `tools`, so `supports_tools()` → `False`). The leg **self-documents a skip** if the model is
  absent at run time, but at flight start it is present.
- `the_one/llm/ollama_provider.py` `_to_api_message` (`:280-302`), `complete()` (post-leg-02).
- `the_one/llm/ollama_api.py` — `_capabilities_cache` (`:20-24`) + `get_model_capabilities` (`:199-225`),
  the warm `(base_url, model)` capability cache the gating signal reads.
- `the_one/agent/core.py:177` — the agent loop calls `await self.llm.supports_tools()` once per turn,
  **before** `stream()`, so the capability cache is already warm by the degraded follow-up turn.
- `the_one/llm/base.py` — `Message`, `ToolCall`, `ToolResult`, `Role`.

## Outputs

- A **flight-log finding** (Anomalies or Decisions) stating, with the raw observed status/body,
  whether the structured degraded round-trip is accepted or rejected by live gemma3:4b.
- **Conditional on rejection only**: `_to_api_message` degraded path adapted (both branches) +
  a gating signal + a hermetic test pinning the chosen serialization.
- **Conditional on clean round-trip**: a hermetic regression test that pins the *current*
  structured degraded serialization as the intended contract (so a future refactor can't silently
  break the round-trip we just validated), and NO production code change.
- The probe script itself lives in `/tmp` and is **NOT committed** (throwaway, like Flight 2's
  leg-03 and Flight 1's spike).

## Acceptance Criteria

- [x] **Probe executed against live gemma3:4b.** A throwaway script (`/tmp/the-one-degraded-probe/probe.py`,
      not committed) built the degraded history (USER, ASSISTANT carrying `ToolCall(id="get_weather_0")`,
      TOOL `ToolResult`) and called `OllamaProvider("gemma3:4b").complete(history)` with **no tools
      offered**. Captured the live HTTP outcome.
- [x] **Finding recorded in the flight log** verbatim (Decisions → "DD5 resolved LIVE" + Leg
      Progress): **ACCEPTED (2xx, model replied)** — the exact omitted-`tools` request shape and
      the coherent reply are recorded.
- [x] **Branch handled — ACCEPTED branch:** added the hermetic test (pure, no live model)
      `tests/test_ollama_degraded_roundtrip.py` asserting `_to_api_message` serializes the degraded
      history into the structured `role:"tool"` + assistant-`tool_calls` shape gemma accepted; NO
      change to `_to_api_message`. Test comment records "Structured degraded round-trip validated
      live against gemma3:4b on 2026-06-18 (flight 3 leg 03); this pins that contract."
- [x] **Re-probe after adaptation (rejection branch only):** N/A — clean accept, no adaptation.
- [x] `make test-unit` stays green — **3262 passed / 18 skipped** (new hermetic test included).
      No live test added to the default suite (probe is throwaway; leg 04 owns the `@pytest.mark.live` test).
- [x] `git status` shows no `/tmp` probe script staged; probe lives only in `/tmp`. Working tree
      has the new hermetic test + artifacts (no `the_one/` change this leg — clean branch).

## Verification Steps

- Run the `/tmp` probe; capture status/body (record the exact `curl`-equivalent or the
  `httpx` exception text).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ollama_degraded_roundtrip.py -x --timeout 30` (the new hermetic test) — green.
- `make test-unit` — full hermetic suite green.
- `grep -rn "tmp" --include=*.py the_one/ tests/` — no committed reference to the throwaway probe.

## Implementation Guidance

1. **Build the probe** (`/tmp/the-one-degraded-probe/probe.py`, throwaway):
   - Construct `history = [Message(role=USER, content="What's the weather in Paris?"),
     Message.assistant(content="", tool_calls=[ToolCall(id="get_weather_0", name="get_weather",
     arguments={"city": "Paris"})]), Message.tool(ToolResult(
     tool_call_id="get_weather_0", content="Sunny, 24°C"))]`. (`Message.tool(...)` is the blessed
     factory; the raw `Message(role=TOOL, tool_result=...)` form serializes identically through
     `:281-286`.)
   - `prov = OllamaProvider(model="gemma3:4b", base_url="http://localhost:11434/v1")`. Print
     `prov.base_url` (the `ensure_v1()` normalization is idempotent on a `/v1` URL).
   - `await prov.complete(history)` with NO `tools=` arg. **`complete()` is a deliberate proxy for
     the live `stream()` path** — the agent loop's degraded follow-up actually runs through
     `stream()` (`core.py:177` then `stream()`), but **both share `_to_api_message`**, so the wire
     `messages` shape and the omitted-`tools` condition are identical; `complete()` is the minimal
     probe. (With no `tools` arg the `if tools:` guard is falsy → the `tools` key is **omitted
     entirely** from the payload, which is exactly the non-tool-capable condition gemma needs.)
   - Wrap in try/except `httpx.HTTPStatusError`; capture `e.response.status_code` + `e.response.text`
     (the provider raises with the body on ≥400 at `ollama_provider.py:129-135`). Print the outcome.
   - Also print the serialized payload (`[prov._to_api_message(m) for m in history]`) so the flight
     log can show the exact wire shape that was accepted/rejected.

2. **Interpret:**
   - **2xx / model replies** → structured degraded round-trip is fine. Go to step 3 (clean branch).
   - **400 `does not support tools`** (or similar) on the *history* → adaptation needed (step 4).
   - **A third, unexpected shape** (neither clean accept nor the anticipated tool-history reject) →
     this hits the flight's **Divert criterion**; STOP and escalate to the Flight Director with the
     raw response rather than guessing a serialization.

3. **Clean branch** — add `tests/test_ollama_degraded_roundtrip.py`: a hermetic test that calls
   `OllamaProvider(...)._to_api_message(...)` on each of the three history messages and asserts the
   structured shapes (`{"role":"tool","tool_call_id":...}` and
   `{"role":"assistant","tool_calls":[...]}`). **Scope the pin to the degraded round-trip
   specifically** — the test exists to lock the *recovered-call follow-up history* serialization
   that the live probe validated, not the structured shape globally (a future tool-capable refactor
   should not be tripped by this test). Name it accordingly (e.g.
   `test_degraded_followup_history_serializes_structured`). Add a comment: "Structured degraded
   round-trip validated live against gemma3:4b on {date} (flight 3 leg 03); this pins that
   contract." No production code change. Done.

4. **Rejection branch** — adapt `_to_api_message` (DD5):
   - **Gating signal — pinned shape (option a, provider-capability gate).** `_to_api_message` is a
     synchronous per-message serializer; keep it sync and do **not** touch the cross-provider
     `Message` shape (mission constraint). The realistic implementation (the warm cache makes this
     easy):
     1. At the **top of `complete()` and `stream()`**, before the
        `[self._to_api_message(m) for m in messages]` list comprehension (`:113` / `:192`), resolve
        the capability **once** and stash it on the instance:
        `self._last_supports_tools = await self.supports_tools()`. This reads the warm module-level
        `_capabilities_cache` (`ollama_api.py:20-24`), already populated this turn by the agent
        loop's `core.py:177` call — no extra `/api/show` round-trip in practice. **Note:**
        `complete()`/`stream()` do **not** currently call `supports_tools()` themselves (only the
        loop does, to decide `tools=`), so this resolve-and-stash is a small **new** addition to
        both methods — not just "read a bool."
     2. In `_to_api_message`, read `self._last_supports_tools` (default it to `True` on the instance
        so any non-degraded caller keeps the structured shape).
   - The gate is **provider-capability level, not per-message**: in a degraded turn (gate False)
     **both** branches convert to prose uniformly. This is intentional — it also cleanly handles
     the partial-rejection edge case (gemma 400ing on only one branch): a uniformly-prose history
     beats a half-structured one. Do **not** reach for a per-`Message` flag (that would risk the
     `Message` shape).
   - Adapt both branches: assistant-`tool_calls` → inline text in `content` with no `tool_calls`
     key; `role:"tool"` → `role:"user"` (or `system`) prose. Tool-capable models (gate True) keep
     the structured shape unchanged.
   - **Hermetic test** (`tests/test_ollama_degraded_roundtrip.py`): seed the capability cache
     directly to avoid a live call — `ollama_api._capabilities_cache[(stripped_url, model)] =
     (frozenset(), <ts>)` forces gate-False; `(frozenset({"tools"}), <ts>)` forces gate-True (pass
     a timestamp via the test, not `time.time()` if the suite forbids it — a large constant is
     fine). Assert prose shape when gate False, structured shape when gate True.
   - Re-probe live (acceptance criterion 4).

## Edge Cases

- **Model absent at run time** → the probe self-skips with a recorded note; the leg cannot land
  without the live finding, so escalate to the Flight Director to confirm the model is reachable
  (it was at flight start).
- **Gemma accepts the assistant `tool_calls` but 400s only on the `role:"tool"` message** (partial
  rejection) → treat as the rejection branch; adapt both for consistency (a half-structured history
  is worse than uniform prose).
- **`supports_tools()` caching** (rejection branch, option a) → not a race in practice: the
  module-level `_capabilities_cache` (300s TTL) is already warm from the agent loop's per-turn
  `supports_tools()` call (`core.py:177`) before the follow-up `stream()`. The resolve-and-stash at
  the top of `complete()`/`stream()` just reads that warm cache; resolve once (not per-message).

## Files Affected

- `/tmp/the-one-degraded-probe/probe.py` — throwaway, NOT committed.
- `tests/test_ollama_degraded_roundtrip.py` — new hermetic test (both branches).
- `the_one/llm/ollama_provider.py` — **only if rejected**: `_to_api_message` degraded-path
  adaptation + the gating signal.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] Live probe run; finding recorded verbatim in the flight log (Decisions + Leg Progress) — ACCEPTED
- [x] Correct branch executed (clean: pin-test only — `tests/test_ollama_degraded_roundtrip.py`)
- [x] `make test-unit` green (3262/18); no `/tmp` probe committed
- [x] Update flight-log.md with the leg progress entry + the DD5 resolution
- [x] Set this leg's status to `landed` (deferred-review model — NOT committed)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight-landing steps; do NOT commit)
