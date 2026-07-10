# Leg: ws-crash-proofing

**Status**: completed
**Flight**: [Input robustness](../flight.md)

## Objective
Make the chat WebSocket receive loop survive a malformed `images` payload — convert the `ImageContent` bare `assert` to `raise`, and guard the message-processing branch with a generic `except` mirroring the sibling branches.

## Context
Maintenance report 2026-07-10 findings **S1** (new) + **S2** (known, M16 debrief):
- `interfaces/web/app.py` — the `websocket_endpoint` `while True` loop calls `_build_user_content(user_input, images)` → `ImageContent(**img)` inside a block guarded only by `except WebSocketDisconnect`, unlike the sibling `join`/`new_session` branches which catch broadly. A client image dict with an unexpected key (`TypeError`) or missing both `data`/`url` (`AssertionError`) kills the connection loop.
- `llm/base.py` — `ImageContent.__post_init__` uses a bare `assert self.data is not None or self.url is not None`, stripped under `python -O`, diverging from the sibling `Message.__post_init__` `raise` (documented convention, `agents.md` `message-*`).

## Inputs
- `the_one/llm/base.py` (`ImageContent.__post_init__`, ~line 76-79), `the_one/interfaces/web/app.py` (the WS message branch + `_build_user_content`, ~line 2200-2234, and the sibling join/new_session except blocks ~2101-2152).

## Outputs
- `ImageContent` guard raises (not `assert`); the WS message branch catches broadly and surfaces an error to the client instead of dropping the connection.

## Acceptance Criteria
- [x] `ImageContent.__post_init__` uses `raise AssertionError(...)` (or a more specific `ValueError`) instead of a bare `assert`, matching the sibling `Message.__post_init__` pattern. A test asserts a `data`-and-`url`-both-absent `ImageContent` raises even under `-O` semantics (i.e. not an `assert`). (`tests/test_llm_base.py::TestContentBlockConstruction::test_image_content_requires_data_or_url`, docstring pins the explicit-raise rationale; `tests/test_ws_build_user_content.py::TestMalformedImagePayloadRaises`.)
- [x] The WS message-processing branch in `app.py` is wrapped in a generic `except Exception` that mirrors the sibling `join`/`new_session` branches: log the error, surface an error event/message to the client, and keep the receive loop alive (do NOT let a malformed `images` payload break out of `while True`).
- [x] A test (integration/unit against the WS handler or `_build_user_content`) proves a malformed `images` payload (unexpected key → `TypeError`; both-absent → the guard) degrades to a surfaced error and the loop survives — not a dropped connection. (`tests/test_ws_message_branch_crash_guard.py::TestMalformedImagesPayloadSurvivesLoop`, drives the real `websocket_endpoint` against a fake WebSocket; also asserts a mid-loop disconnect still exits cleanly.)
- [x] Text-only and well-formed image sends are byte-identical (no behavior change on the happy path). (`tests/test_ws_message_branch_crash_guard.py::TestHappyPathUnaffected`.)
- [x] `git diff` limited to `llm/base.py`, `app.py`, + test files (+ flight artifacts). (Leg 2 also touches `app.py`/`chat.js` — both legs landed together in this pass; see flight-log for the combined diff.)

## Verification Steps
- Scoped tests green (`PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x --timeout 30`).
- Confirm the exact error-surfacing shape matches how the sibling branches report errors to the client (consistency).

## Implementation Guidance
1. `llm/base.py`: replace the bare `assert` in `ImageContent.__post_init__` with an explicit `raise` (match `Message.__post_init__`'s exception type/message style).
2. `app.py`: **scope the new `try/except Exception` TIGHTLY around the content-build line** (`content = _build_user_content(user_input, images)`, ~line 2232) — do NOT wrap `await ws.receive_text()` (~line 2053) or the whole loop body. The **outer** `try` (~line 2253) already handles `WebSocketDisconnect` (which IS an `Exception` subclass) — a broad second wrapper would swallow disconnects. (design-review [1])
3. **Error-surfacing shape** (design-review [2]): mirror the narrower sibling *in this same branch* (~line 2205-2210) — `logger.exception(...)` + `await ws.send_json({"type": "system", "content": f"..."})` + `continue` (`session` is already bound here). Do NOT use `_send_to_session` (that broadcasts to all subscribers — wrong call site).
4. `asyncio.CancelledError` needs no special handling — it's a `BaseException`, not caught by `except Exception` (the codebase documents this convention ~`app.py:1680-1709`).
5. Add tests for the guard AND loop-survival, including a test that a disconnect mid-loop still exits cleanly (not just code review).

## Edge Cases
- The new inner `except Exception` must be NARROW (content-build only). A genuine `WebSocketDisconnect` is raised by `receive_text()` *outside* the guard and handled by the outer try — verify a mid-loop disconnect still ends the loop.
- Only malformed-payload errors are caught-and-continue; the happy path is untouched.

## Files Affected
- `the_one/llm/base.py`, `the_one/interfaces/web/app.py`, test files.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Changes stay uncommitted — batch commit after review
