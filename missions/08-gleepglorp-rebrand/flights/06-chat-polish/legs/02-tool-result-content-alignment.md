# Leg: tool-result-content-alignment

**Status**: completed
**Flight**: [Chat Polish](../flight.md)

## Objective

Collapse the three-way `tool_result.content` truncation divergence (live 2000-char vs HTTP-API 4000-char vs replay untruncated) into a single shared `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` constant + `truncate_for_event(content)` helper, applied at all four projection sites so live broadcast, HTTP API, and replay all emit identical truncated content for identical inputs. DB persistence stays full-fidelity.

## Context

- **Design Decision (flight.md)**: "Tool-result truncation: single shared constant + projection-time truncation only." Constant value `4000` (matches the existing HTTP-API consumer's value, minimizing the chance of regressing a downstream caller that relied on the higher cap). Truncation is a PROJECTION concern, not a STORAGE concern.
- **Module placement (flight.md, cycle-1 review fix)**: place the constant + helper in `the_one/db/codec.py`. The codec IS the canonical `Message → event dict` projector via `messages_to_ui_events`; `app.py` already imports from `the_one.db.codec` at `app.py:39` (`from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events`), so the import direction (interfaces → db) is correct. The originally-proposed `the_one/interfaces/web/event_shapes.py` location would have forced a backwards db → interfaces import — rejected at cycle-1.
- **Recon (flight-log.md row #2)**: confirmed-live at design time —
  - `the_one/interfaces/web/app.py:720` (`_broadcast_one`): `[:2000]`
  - `the_one/interfaces/web/app.py:853` (`_process_and_broadcast` WS branch): `[:2000]`
  - `the_one/interfaces/web/app.py:863` (`_process_and_broadcast` HTTP API `result_messages.append`): `[:4000]`
  - `the_one/db/codec.py:144` (`messages_to_ui_events` replay): no truncation
- **Verification anchor (flight.md "Verification" §2)**: send a tool that emits a 5000-char result; WS broadcast event, `session.history` rejoin event, AND HTTP API `result_messages` consumer all show the SAME truncated content (capped at 4000).
- **Checkpoint anchor (flight.md "Checkpoints" §L02, cycle-1 reviewer suggestion)**: add an integration test that sends a tool whose `ToolResult.content` exceeds the cap and asserts the truncated content is identical across all three projection consumers. Single best regression-net against future per-site truncation drift.
- **F5 carry-forward**: F5 L02 added `parent_message_id` + `tool_call_id` discriminators to all four sites. This leg ONLY touches the `content` field — the discriminator contract is untouched.

## Inputs

Files that exist before this leg runs:
- `the_one/db/codec.py` — defines `messages_to_ui_events` (line 85) and projects `msg.tool_result.content` at line 144 with NO truncation
- `the_one/interfaces/web/app.py` — three truncation sites at lines 720, 853, 863
- `tests/test_db_codec.py` — F5 codec round-trip tests including `test_tool_result_metadata_round_trip` (line 224) and event-shape coverage; currently does NOT assert truncation behavior
- `tests/test_app_websocket_pause_resume.py` — broadcast integration test fixture infrastructure (`Session`-shaped scaffolding, `_send_to_session` capture); the closest existing test file to a "broadcast site emits the right shape" assertion

State that must be true:
- L01 (`settings-lazy-refactor`) landed — broad pytest exits 0, browser suite 315/35 (verified via L01 report)
- Container `the-one` running; `make rebuild` available
- F5's discriminator contract intact (`parent_message_id` + `tool_call_id` on all `tool_call` and `tool_result` events)

## Outputs

Files modified:
- `the_one/db/codec.py` — adds `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` module-level constant + `truncate_for_event(content: str) -> str` helper; applies the helper at line 144 (`messages_to_ui_events` tool_result projection)
- `the_one/interfaces/web/app.py` — imports the new helper from `the_one.db.codec`; replaces the three bare slice expressions at lines 720, 853, 863 with `truncate_for_event(msg.tool_result.content)`
- `tests/test_db_codec.py` — adds a `messages_to_ui_events` truncation test (input > 4000 chars → output exactly 4000 chars; input ≤ 4000 → output unchanged)
- `tests/test_app_websocket_pause_resume.py` OR a new `tests/test_tool_result_truncation_alignment.py` — adds the cross-projection-site integration assertion (cycle-1 reviewer's checkpoint suggestion)

State after:
- All four projection sites use the same constant; the three-way divergence is gone
- A single tool that emits a 5000-char result produces identical truncated `content` strings on: live WS broadcast, replay-on-rejoin via `session.history` hydration, and HTTP API `result_messages` consumer
- DB persistence (`encode_messages` / `decode_messages` round-trip via `_tool_result_to_dict` / `message_from_dict`) is unchanged — full content preserved in storage
- Test suite asserts the truncation invariant at both unit (codec) and integration (cross-site) levels

## Acceptance Criteria

- [ ] `the_one/db/codec.py` exports `MAX_TOOL_RESULT_INLINE_CONTENT: int = 4000` at module scope
- [ ] `the_one/db/codec.py` exports a function `truncate_for_event(content: str) -> str` that returns `content[:MAX_TOOL_RESULT_INLINE_CONTENT]` (one-liner; behavior identical to slicing with the constant)
- [ ] `the_one/db/codec.py:144` — the `messages_to_ui_events` `tool_result` projection uses `truncate_for_event(msg.tool_result.content)` (not raw `msg.tool_result.content`)
- [ ] `the_one/db/codec.py`'s `_tool_result_to_dict`, `message_to_dict`, `message_from_dict`, `encode_messages`, `decode_messages` are UNCHANGED — DB persistence stays full-fidelity
- [ ] `the_one/interfaces/web/app.py:720` — `_broadcast_one`'s `tr_event["content"]` uses `truncate_for_event(msg.tool_result.content)` (was `[:2000]`)
- [ ] `the_one/interfaces/web/app.py:853` — `_process_and_broadcast`'s WS `tr_event["content"]` uses `truncate_for_event(msg.tool_result.content)` (was `[:2000]`)
- [ ] `the_one/interfaces/web/app.py:863` — `_process_and_broadcast`'s HTTP API `result_messages.append({"role": "tool", "content": ...})` uses `truncate_for_event(msg.tool_result.content)` (was `[:4000]`)
- [ ] `the_one/interfaces/web/app.py` imports `truncate_for_event` (and optionally `MAX_TOOL_RESULT_INLINE_CONTENT` if any test or assertion in `app.py` itself needs the value — none currently does, so the helper import alone suffices) from `the_one.db.codec`
- [ ] No NEW occurrences of bare `[:2000]` or `[:4000]` slicing remain on `tool_result.content` anywhere in `the_one/` source — `grep -rn "tool_result\.content\[:" the_one/` (scoped to `the_one/`, NOT repo root — the leg artifact itself contains literal `tool_result.content[:` strings in its Implementation Guidance and Citation Audit) returns empty
- [ ] `tests/test_db_codec.py` includes a new test asserting `messages_to_ui_events` truncates `tool_result.content` at 4000 chars (input of `"x" * 5000` → projected `content` of length 4000; input of `"x" * 4000` → length 4000 unchanged; input of `"x" * 100` → length 100 unchanged)
- [ ] A new integration test (location: either added to `tests/test_app_websocket_pause_resume.py` OR a new `tests/test_tool_result_truncation_alignment.py` — choose based on the existing fixture's reusability) exercises the FULL `_process_and_broadcast` path (not isolated projector calls) and asserts that for a single `ToolResult.content` value > 4000 chars, the truncated `content` string is IDENTICAL across: (a) the WS-broadcast `tool_result` event captured from `_send_to_session` (which routes through `_process_and_broadcast`'s line-853 site), (b) the `_process_and_broadcast` HTTP API `result_messages` `content` field (line-863 site), AND (c) the `messages_to_ui_events` replay projection of the equivalent `Message` (codec.py:144 site). Per cycle-1 reviewer confirmation: the `tests/test_app_websocket_pause_resume.py` `StubAgent` + `monkeypatch.setattr(web_app, "_send_to_session", capture)` pattern supports this in ~30 lines; the unit-style fallback is NOT acceptable
- [ ] Broad pytest (`docker exec the-one pytest -x --timeout 30`) exits code 0; pass count is the L01-landed baseline (1622 passed, 4 skipped, 370 deselected per L01 report) PLUS the new codec truncation test PLUS the new cross-projection-site integration test (expect 1624 passed, 4 skipped, 370 deselected; no NEW failures or new skips)
- [ ] Browser suite preserved at 315 passing / 35 skipped (F5/L01 baseline)

## Verification Steps

- **Constant + helper exposed**: `docker exec the-one python -c "from the_one.db.codec import MAX_TOOL_RESULT_INLINE_CONTENT, truncate_for_event; assert MAX_TOOL_RESULT_INLINE_CONTENT == 4000; assert truncate_for_event('x' * 5000) == 'x' * 4000; assert truncate_for_event('short') == 'short'"` exits cleanly.
- **No bare slices remain**: `grep -rn "tool_result\.content\[:" the_one/` returns empty (excluding the leg artifact itself; if run from repo root, restrict to `the_one/`).
- **DB persistence unchanged**: `docker exec the-one pytest tests/test_db_codec.py::test_tool_result_metadata_round_trip -x --timeout 30 -v` passes; a manual smoke `python -c "from the_one.db.codec import encode_messages, decode_messages; from the_one.llm.base import Message, Role, ToolResult; m = Message(role=Role.TOOL, tool_result=ToolResult(tool_call_id='x', content='y'*8000)); rt = decode_messages(encode_messages([m])); assert len(rt[0].tool_result.content) == 8000"` confirms storage is full-fidelity.
- **New codec truncation test**: `docker exec the-one pytest tests/test_db_codec.py -x --timeout 30 -v` includes the new test and it passes.
- **Cross-projection-site assertion**: `docker exec the-one pytest tests/test_tool_result_truncation_alignment.py -x --timeout 30 -v` (or the chosen file) passes; the test asserts all three projections produce equal-string content for a >4000-char input.
- **Broad pytest exits 0**: `docker exec the-one pytest -x --timeout 30` exits code 0 with pass count ≥ L01 baseline + 2.
- **Browser suite preserved**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` exits with 315/35 split unchanged.

## Implementation Guidance

1. **Edit `the_one/db/codec.py`** — add constant + helper at module scope (after imports, before the first `_tool_call_to_dict`):

   ```python
   # M08 F6 L02: shared projection-time truncation for tool_result.content.
   # Applied at every consumer that surfaces tool content to a client (live
   # WS broadcast in app._broadcast_one + app._process_and_broadcast, HTTP API
   # result_messages, replay via messages_to_ui_events). DB persistence stays
   # full-fidelity — encode_messages / decode_messages do NOT truncate.
   MAX_TOOL_RESULT_INLINE_CONTENT = 4000


   def truncate_for_event(content: str) -> str:
       """Cap tool_result.content for projection to clients.

       Single source of truth for the projection-time truncation contract.
       DB persistence is unaffected — truncation is a "what we hand to
       clients" concern, not a "what we keep" concern.
       """
       return content[:MAX_TOOL_RESULT_INLINE_CONTENT]
   ```

   Then update line 144 (inside `messages_to_ui_events`'s `tool_result` projection branch):

   ```python
   # BEFORE
   "content": msg.tool_result.content,
   # AFTER
   "content": truncate_for_event(msg.tool_result.content),
   ```

2. **Edit `the_one/interfaces/web/app.py`** — extend the existing codec import at line 39 to include the helper:

   ```python
   from the_one.db.codec import (
       decode_messages,
       encode_messages,
       messages_to_ui_events,
       truncate_for_event,
   )
   ```

   Apply the helper at all three sites:

   - Line 720 (`_broadcast_one`): `"content": msg.tool_result.content[:2000]` → `"content": truncate_for_event(msg.tool_result.content)`
   - Line 853 (`_process_and_broadcast` WS): `"content": msg.tool_result.content[:2000]` → `"content": truncate_for_event(msg.tool_result.content)`
   - Line 863 (`_process_and_broadcast` HTTP API `result_messages`): `"content": msg.tool_result.content[:4000]` → `"content": truncate_for_event(msg.tool_result.content)`

3. **Add codec-level test to `tests/test_db_codec.py`** — extend the existing `messages_to_ui_events`-shape test class. Pattern (adapt to existing class style):

   ```python
   def test_tool_result_content_truncated_to_max(self) -> None:
       """messages_to_ui_events caps tool_result.content at the shared constant."""
       from the_one.db.codec import (
           MAX_TOOL_RESULT_INLINE_CONTENT,
           messages_to_ui_events,
       )
       from the_one.llm.base import Message, Role, ToolResult

       # Input > cap → output exactly cap-long
       msg_over = Message(
           role=Role.TOOL,
           tool_result=ToolResult(
               tool_call_id="tc-1",
               content="x" * (MAX_TOOL_RESULT_INLINE_CONTENT + 1000),
           ),
       )
       events = messages_to_ui_events([msg_over])
       assert len(events[0]["content"]) == MAX_TOOL_RESULT_INLINE_CONTENT

       # Input == cap → unchanged
       msg_at = Message(
           role=Role.TOOL,
           tool_result=ToolResult(
               tool_call_id="tc-2",
               content="y" * MAX_TOOL_RESULT_INLINE_CONTENT,
           ),
       )
       assert len(messages_to_ui_events([msg_at])[0]["content"]) == MAX_TOOL_RESULT_INLINE_CONTENT

       # Input < cap → unchanged
       msg_under = Message(
           role=Role.TOOL,
           tool_result=ToolResult(tool_call_id="tc-3", content="hi"),
       )
       assert messages_to_ui_events([msg_under])[0]["content"] == "hi"
   ```

4. **Add cross-projection-site integration test** — new file `tests/test_tool_result_truncation_alignment.py`. The test MUST exercise the full `_process_and_broadcast` path (not just call each projector in isolation).

   Pattern: reuse the `StubAgent(step_messages=[...])` + `monkeypatch.setattr(web_app, "_send_to_session", capture)` fixture pattern from `tests/test_app_websocket_pause_resume.py`. Construct a single `ToolResult(content="x" * 5000)`-bearing `Message`, drive `_process_and_broadcast`, capture (a) the WS-broadcast `tool_result` event from the `_send_to_session` capture sink (this exercises the line-853 site) and (b) the `result_messages` returned by `_process_and_broadcast` (this exercises the line-863 site). Then call `messages_to_ui_events([the_tool_message])` (this exercises the codec.py:144 site). Assert all three `content` strings:

   - are byte-equal (`assert ws_content == api_content == replay_content`)
   - have length exactly `MAX_TOOL_RESULT_INLINE_CONTENT` (4000)

   Cycle-1 reviewer confirmed this is ~30 lines using existing fixtures. The unit-style fallback (calling each projector in isolation) is NOT acceptable per cycle-1 review — it would silently hide a regression where `_process_and_broadcast` rewires its own truncation path bypassing the helper.

5. **Run targeted tests first**, then broad suite:

   ```bash
   docker exec the-one pytest tests/test_db_codec.py tests/test_tool_result_truncation_alignment.py -x --timeout 30 -v
   docker exec the-one pytest tests/test_app_websocket_pause_resume.py -x --timeout 30 -v
   docker exec the-one pytest -x --timeout 30
   ```

6. **Run browser suite**:

   ```bash
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

7. **Update flight log** — append a "Leg Progress > tool-result-content-alignment" entry summarizing the four sites changed, the new tests added, and broad/browser pass counts.

8. **Do NOT commit yet** — Flight Director batches commits after L05.

## Edge Cases

- **The `_auth_required_event_from_metadata(meta)` path (app.py:714)**: this path broadcasts an `auth_required` event INSTEAD of a `tool_result`. It does NOT project `msg.tool_result.content`, so it is NOT affected by this leg. Confirm during impl — don't accidentally inject `truncate_for_event` into the `auth_required` path.
- **Anthropic / OpenAI / Ollama provider tool_result projection** (`the_one/llm/anthropic_provider.py:161`, `the_one/llm/openai_provider.py:166`, `the_one/llm/ollama_provider.py:208`): these are PROVIDER-API projections (Message → provider request body), NOT client-projection sites. They MUST stay untruncated — providers receive the full content for context-aware tool follow-up. These are OUT of scope for this leg. Verify by inspection — the leg does NOT modify them.
- **CLI tool result rendering** (`the_one/interfaces/cli.py:83 — "output = msg.tool_result.content"`): the CLI is a separate consumer that receives the full content directly (Rich-rendered to a terminal). The CLI is NOT bound by the projection-time truncation contract — leave untruncated. The mission's scope is the WEB UI consistency; CLI behavior is out of scope.
- **Unicode boundary edge case**: `content[:4000]` in Python slices by code-point (str), not by byte. A 4000-grapheme content with multi-codepoint sequences (emoji ZWJ joiners, combining marks) may slice mid-sequence and emit a partial grapheme. This matches the EXISTING behavior at all three sites — the leg does NOT introduce new edge cases; it merely aligns them. Document this in the helper docstring if not already present, but do NOT attempt grapheme-aware truncation (out of scope).
- **Empty content**: `truncate_for_event("")` returns `""` — no special case needed, slicing of empty string is empty string.
- **None content**: `Message.tool_result.content` is typed `str` (not `str | None`) in `the_one/llm/base.py` — verified at design time via the existing `_tool_result_to_dict` accessing `tr.content` directly. No None-handling needed.

## Files Affected

- `the_one/db/codec.py` — add constant, add helper, apply helper at line 144
- `the_one/interfaces/web/app.py` — extend codec import (line 39), apply helper at lines 720, 853, 863
- `tests/test_db_codec.py` — add codec truncation test (one new test method)
- `tests/test_tool_result_truncation_alignment.py` (new file) OR extension to `tests/test_app_websocket_pause_resume.py` — cross-projection-site assertion

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0; browser suite 315/35 preserved)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md yet — that happens during the post-L05 commit batch
- [ ] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

8 source-code citations verified against current code at leg design time:
- `the_one/db/codec.py:144 — "msg.tool_result.content"` — OK (`messages_to_ui_events` tool_result branch)
- `the_one/db/codec.py:85` (start of `messages_to_ui_events`) — OK
- `the_one/interfaces/web/app.py:39 — "from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events"` — OK
- `the_one/interfaces/web/app.py:720 — "msg.tool_result.content[:2000]"` — OK (`_broadcast_one`)
- `the_one/interfaces/web/app.py:853 — "msg.tool_result.content[:2000]"` — OK (`_process_and_broadcast` WS)
- `the_one/interfaces/web/app.py:863 — "msg.tool_result.content[:4000]"` — OK (`_process_and_broadcast` HTTP API `result_messages`)
- `the_one/llm/base.py:Message.tool_result.content` (type is `str`) — verified during edge-case audit
- `tests/test_db_codec.py:224 — "test_tool_result_metadata_round_trip"` — OK (target reference for round-trip non-regression)
