# Leg: anthropic-thinking-replay

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

> **★ Renumbered 03→04 by the 2026-07-02 adaptive pivot.** The **replay logic + DD8 strip-when-off
> approach below were design-reviewed and APPROVED** (mode-agnostic — correct for both adaptive and
> the old budget_tokens mode). Two references are superseded by the new **Leg 03
> `anthropic-adaptive-enablement`** and will be refreshed when this leg executes against post-Leg-03
> code: (1) the `_build_kwargs` **hoist of `thinking_active` is done in Leg 03** (which rewrites
> enablement), so this leg's `_build_kwargs` change reduces to *threading the already-hoisted
> `thinking_active` into `_to_api_message(m, thinking_active)`*; (2) `thinking_active` derives from
> `thinking_enabled` (bool), NOT `budget > 0`, and the end-to-end test asserts
> `kwargs["thinking"] == {"type": "adaptive"}` with activation via `config["thinking_enabled"]=True`.
> The `_to_api_message` replay projection (the substance of this leg) is unchanged; line refs will be
> re-verified at execution.

## Objective

Replay stored thinking blocks (signatures intact, **before** `text`/`tool_use`) in the assistant
turn projected by `_to_api_message` — **gated on the outgoing request's thinking state (DD8:
replay-when-on, strip-when-off)** — so a thinking+tool turn's follow-up request (carrying the
tool result) is accepted by Anthropic instead of 400-ing. This is the leg that makes mission
criterion #1's *second* turn pass.

## Context

- Builds on Legs 01–02: `Message.thinking` carries captured signed blocks
  (`ThinkingBlock{type, thinking, signature, data}`) that round-trip through the codec, and
  `_build_kwargs` already resolves whether thinking is enabled on the request. Leg
  02 left the breadcrumb at `anthropic_provider.py:271–273` ("Leg 03 replay preserves that
  ordering").
- **The criterion.** Anthropic *rejects* the follow-up turn (the one carrying `tool_result`
  back) unless the prior assistant turn's `thinking` blocks are replayed **with their
  signatures**, ordered **before** the `tool_use` block. Today `_to_api_message`
  (`anthropic_provider.py:399–436`) builds the assistant turn as `[text?, tool_use…]` — no
  thinking slot — so the follow-up 400s. This leg adds the slot.
- **DD8 — gated on the OUTGOING request's thinking state.** Replay thinking blocks **only when
  thinking is enabled on the current request**; when thinking is disabled, **strip** stored
  thinking from the projected history. An operator can disable the budget mid-session (or run
  the budget-0 variant in a chat that already accumulated thinking turns), producing a
  thinking-OFF request over a history full of signed blocks — replaying signed blocks onto a
  thinking-off request risks a signature-validation 400. Stripping-when-off is deterministic and
  safe; within a single thinking-ON tool loop the follow-up request still has thinking ON, so
  criterion #1's blocks *are* replayed. The `thinking_active` flag defaults to `False`, so any
  non-thinking request (and every legacy call site) projects byte-identically to today.
- **Live verification (deferred, like Leg 02's probe).** Whether Anthropic *400s* or *silently
  ignores* stored thinking on a thinking-off request is confirmed live in the behavior test's
  mixed-session variant (Leg 07) / by the operator — but strip-when-off is safe regardless, so
  the autonomous implementation is correct before that confirmation. Autonomous acceptance =
  fixtured projection tests (on + off).
- **DD5 — Anthropic-only.** Replay lives entirely in `anthropic_provider.py`.

## Inputs

- Legs 01–03 landed on this branch (post-adaptive-pivot). Current adapter state:
  - `_build_kwargs` (`anthropic_provider.py:163–224`) — **`thinking_active` is already HOISTED**
    above the message loop by Leg 03 (`:175–178`:
    `resolve_extended_thinking(self._thinking_enabled_config) and enable_thinking is not False`);
    the message loop calls `self._to_api_message(m)` (single-arg) at `:185`; adaptive enablement
    (`if thinking_active: kwargs["thinking"] = {"type": "adaptive"}`) at `:222–223`.
  - `_to_api_message` (`:399`) — TOOL branch, **ASSISTANT-with-tool_calls branch** (`:418`, builds
    `[text?, tool_use…]`), generic string branch (last `return`). `_to_anthropic_tool` at `:388`
    (place `_thinking_block_to_api` adjacent).
  - Leg 03 replaced the budget resolver with the boolean `resolve_extended_thinking` /
    `self._thinking_enabled_config` — **`thinking_active` derives from `thinking_enabled`, not a
    budget.** Enablement is `{"type": "adaptive"}` (no `budget_tokens`).
  - `ThinkingBlock` imported (Leg 02).
- `tests/test_anthropic_provider.py` — fixture scaffolding (`_CreateRecorder` records
  `kwargs["messages"]`; provider built via a config-bearing constructor per Leg 02's tests);
  `_to_api_message` is directly unit-testable (a plain method).

## Outputs

- `the_one/llm/anthropic_provider.py`:
  - `_build_kwargs` — `thinking_active` is ALREADY hoisted (Leg 03, `:175`); this leg only
    **threads it into the loop call**: `self._to_api_message(m, thinking_active)` at `:185`. No
    other `_build_kwargs` change.
  - `_to_api_message(self, msg, thinking_active: bool = False)` prepends stored thinking blocks
    (signatures intact) before `text`/`tool_use` in the assistant projection, gated on
    `thinking_active`.
  - a small `_thinking_block_to_api(tb)` helper building the API block dict.
- `tests/test_anthropic_provider.py` — replay-on / strip-off / redacted / ordering /
  thinking-only-turn / back-compat projection tests.
- `tests/test_anthropic_live.py` — an optional deselected `@pytest.mark.live` mixed-session
  conformance probe (authored; run at Leg 07/HAT).

## Acceptance Criteria

- [x] `_to_api_message` accepts `thinking_active: bool = False`. When `thinking_active` is True
      and the assistant message has `thinking`, the projected assistant `content` list begins
      with the thinking blocks (in stored order), then `text` (if any), then `tool_use` blocks —
      i.e. thinking strictly **precedes** `tool_use`.
- [x] Each replayed thinking block is byte-faithful to the stored `ThinkingBlock`:
      `type="thinking"` → `{"type": "thinking", "thinking": <text>, "signature": <sig>}` with the
      signature intact; `type="redacted_thinking"` → `{"type": "redacted_thinking", "data": <data>}`.
      Only set sub-fields are emitted (a redacted block carries no `thinking`/`signature`).
- [x] **DD8 strip-when-off:** when `thinking_active` is False, `_to_api_message` emits **no**
      thinking blocks — the assistant projection is byte-identical to the pre-Leg-03 output
      (`[text?, tool_use…]` or the plain-string branch). Verified against a stored-thinking
      message projected with `thinking_active=False`.
- [x] An assistant turn that has `thinking` but **no** `tool_calls`, projected with
      `thinking_active=True`, builds a content list `[*thinking, text?]` (widened branch);
      the same turn with `thinking_active=False` (or empty thinking) falls through to the
      plain-string branch unchanged.
- [x] `_build_kwargs` threads the **already-hoisted** `thinking_active` (Leg 03, `:175`) into the
      `_to_api_message(m, thinking_active)` loop call (`:185`). No other `_build_kwargs` change —
      the adaptive enablement block (`:222`) is untouched.
- [x] End-to-end projection: given a message list `[user, assistant(thinking+tool_calls),
      tool_result]` and a **thinking-enabled** provider (`config={"thinking_enabled": True}`), the
      `messages` kwarg recorded by `_CreateRecorder` shows the assistant entry with
      thinking-before-tool_use, AND `kwargs["thinking"] == {"type": "adaptive"}` — the shape
      Anthropic requires for the follow-up turn to be accepted.
- [x] **Hermetic DD8 strip-off end-to-end:** the same `[user, assistant(thinking+tool_calls),
      tool_result]` list with thinking **disabled** (no `thinking_enabled` config, or
      `enable_thinking=False`) records an assistant entry with **no** thinking block AND `kwargs`
      with **no** `"thinking"` key — proving the multi-turn strip contract hermetically, without
      waiting for the Leg 07 live probe.
- [x] **Ordering with two stored blocks:** an assistant turn carrying two `ThinkingBlock`s
      projects them at `content[0]`/`content[1]` in stored order (locks order preservation, not
      just presence).
- [x] No regression: existing `_to_api_message` / `_build_kwargs` tests (tool projection,
      sanitize, temperature-retry, tools.N) still pass; single-arg `_to_api_message(msg)` callers
      (if any in tests) still work via the `thinking_active=False` default.
- [x] A `@pytest.mark.live` mixed-session conformance probe is authored in
      `test_anthropic_live.py` (deselected; not run this leg).
- [x] Full unit suite green minus the known aiosqlite teardown flake.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py -x --timeout 30`
  — replay/strip/redacted/ordering tests pass; existing projection tests unaffected.
- Direct projection assertions (preferred): call
  `prov._to_api_message(Message.assistant("ans", tool_calls=[...], thinking=[ThinkingBlock(...)]), thinking_active=True)`
  and assert the `content` list order; repeat with `thinking_active=False` for the strip case.
- `grep -n "_to_api_message" the_one/llm/anthropic_provider.py` — confirm the only call site
  (`_build_kwargs`) passes `thinking_active`.
- `make test-unit` once at leg end — green minus the known teardown flake.
- Live mixed-session tolerance (operator, later): behavior-test mixed-session variant at Leg 07.

## Implementation Guidance

1. **Add a block-to-API helper** near `_to_anthropic_tool` (`anthropic_provider.py:388`):

   ```python
   def _thinking_block_to_api(self, tb: ThinkingBlock) -> dict[str, Any]:
       # Emit the stored block in Anthropic's content-block shape, signatures
       # intact. Only set sub-fields are included (a redacted block has no
       # thinking/signature). The stored ThinkingBlock is already API-shaped
       # (Leg 01), so this is a faithful projection, not a re-mapping.
       d: dict[str, Any] = {"type": tb.type}
       if tb.thinking is not None:
           d["thinking"] = tb.thinking
       if tb.signature is not None:
           d["signature"] = tb.signature
       if tb.data is not None:
           d["data"] = tb.data
       return d
   ```

2. **Widen the assistant branch in `_to_api_message`** (`:399`; assistant branch at `:418`).
   Change the signature to `def _to_api_message(self, msg: Message, thinking_active: bool = False)`
   and the assistant branch to build the thinking-first content list:

   ```python
   if msg.role == Role.ASSISTANT and (msg.tool_calls or (thinking_active and msg.thinking)):
       content: list[dict[str, Any]] = []
       # DD8: replay thinking (signatures intact) ONLY when thinking is active on
       # THIS request; thinking must precede text/tool_use or Anthropic 400s the
       # follow-up turn. When thinking is off, this loop is skipped → stored
       # thinking is stripped, byte-identical to the pre-L03 projection.
       if thinking_active:
           for tb in msg.thinking:
               content.append(self._thinking_block_to_api(tb))
       if msg.content:
           content.append({"type": "text", "text": msg.content})
       for tc in msg.tool_calls:
           content.append(
               {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
           )
       return {"role": "assistant", "content": content}
   ```

   The widened guard `(msg.tool_calls or (thinking_active and msg.thinking))` means: a
   thinking-only assistant turn enters this branch **only** when thinking is active; otherwise it
   falls through to the plain-string branch (DD8 strip, byte-identical legacy). A tool-calling
   turn enters as before regardless of `thinking_active` (and simply skips the thinking loop when
   off).

3. **Thread `thinking_active` into the loop call** in `_build_kwargs`. Leg 03 **already computes**
   `thinking_active` before the message loop (`anthropic_provider.py:175–178`) and already sets the
   adaptive enablement block (`:222–223`). This leg's ONLY `_build_kwargs` change is the loop call
   at `:185`:

   ```python
   #   before:  api_messages.append(self._to_api_message(m))
   #   after:   api_messages.append(self._to_api_message(m, thinking_active))
   ```

   Do NOT touch the `thinking_active` computation or the adaptive enablement block — they are
   Leg 03's and are correct (adaptive-only; no `temperature`/`max_tokens` forcing after the pivot).

4. **Tests** (`tests/test_anthropic_provider.py`) — prefer direct `_to_api_message` unit tests
   plus one end-to-end `_build_kwargs`/`_CreateRecorder` shape check:
   - **replay-on ordering:** `_to_api_message(Message.assistant("ans", tool_calls=[ToolCall(...)],
     thinking=[ThinkingBlock(type="thinking", thinking="reasoned", signature="sig123")]),
     thinking_active=True)` → `content[0] == {"type":"thinking","thinking":"reasoned","signature":"sig123"}`,
     a `text` block, then the `tool_use` block; assert thinking index < tool_use index.
   - **strip-off (DD8):** same message with `thinking_active=False` → content is `[text, tool_use]`,
     no thinking block; byte-identical to a message with empty thinking.
   - **redacted replay:** a `type="redacted_thinking"` block → `{"type":"redacted_thinking","data":...}`,
     no `thinking`/`signature` keys.
   - **thinking-only turn:** `Message.assistant("ans", thinking=[ThinkingBlock(...)])` (no
     tool_calls) with `thinking_active=True` → `[thinking, text]`; with `thinking_active=False`
     → plain-string branch (`{"role":"assistant","content":"ans"}`).
   - **empty thinking no-op:** `Message.assistant("ans", tool_calls=[...])` (empty thinking) with
     `thinking_active=True` → `[text, tool_use]` (no empty/None thinking noise).
   - **end-to-end (replay-on):** build `[user, assistant(thinking+tool), tool_result]`, a
     thinking-enabled provider (`config={"thinking_enabled": True}`), drive `complete()`/`stream()`
     through a recorder, and assert the recorded `messages` assistant entry has thinking before
     tool_use AND `kwargs["thinking"] == {"type": "adaptive"}`.
   - **end-to-end (strip-off, DD8):** the same list with thinking disabled (no config, or
     `enable_thinking=False`) → recorded assistant entry has no thinking block AND `kwargs` has no
     `"thinking"` key.
   - Author the deselected `@pytest.mark.live` mixed-session probe in `test_anthropic_live.py`
     (thinking-on tool round-trip, then disable thinking / `enable_thinking=False` and continue —
     asserts no 400; not run autonomously).

## Edge Cases

- **Interleaving.** We store thinking, text, and tool_calls separately (order within each list
  preserved). Anthropic requires thinking **before** `tool_use`; emitting `[*thinking, text,
  *tool_use]` satisfies that. If a future model interleaves multiple thinking/tool segments in
  one turn, this flat ordering still validates (all thinking precedes all tool_use) — record any
  live surprise as a flight-log deviation per the flight's Adaptation Criteria.
- **Assistant turn with thinking but no tool_use, thinking OFF.** Falls to the plain-string
  branch — stored thinking silently dropped from the projection (DD8). Correct.
- **Empty `msg.thinking`.** The `thinking_active` loop is a no-op; the widened guard's
  `(thinking_active and msg.thinking)` is falsy, so a thinking-empty, tool-empty assistant turn
  still takes the plain-string branch (unchanged).
- **Signature must be verbatim.** `_thinking_block_to_api` copies `signature`/`data` unmodified
  — never truncate, re-encode, or re-order. The codec already preserved them (Leg 01).
- **`thinking_active` default `False`.** Any caller of `_to_api_message` that doesn't pass the
  flag (legacy/test) strips thinking — the safe default. Only `_build_kwargs` passes `True`
  (when thinking is enabled on the request).
- **Degenerate thinking-only turn with empty content.** With `thinking_active=True` and an
  assistant message that has thinking but empty `content` and no `tool_calls`, the branch emits a
  bare `[*thinking]` — a thinking-only assistant turn Anthropic may reject. This is a rare
  capture state (model returned *only* thinking) outside criterion #1's thinking+tool path. Add a
  test documenting the current behavior; if it proves problematic live (Leg 07), fall back to the
  plain-string branch when `content`/`tool_calls` are both empty. Not a blocker for the criterion.

## Files Affected

- `the_one/llm/anthropic_provider.py` — `_thinking_block_to_api` helper; `_to_api_message`
  signature + thinking-first assistant projection; `_build_kwargs` hoist + thread.
- `tests/test_anthropic_provider.py` — replay/strip/redacted/ordering/thinking-only/end-to-end
  projection tests.
- `tests/test_anthropic_live.py` — deselected `@pytest.mark.live` mixed-session probe.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (new replay tests + full unit suite green minus known teardown flake)
- [x] Update flight-log.md with the Leg 04 progress entry
- [x] Set this leg's status to `landed` (NOT `completed` — commit deferred to Phase 2d)
- [x] Do NOT commit; do NOT check off the leg in flight.md; do NOT touch mission.md
- [x] Signal `[HANDOFF:review-needed]`
