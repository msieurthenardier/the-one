# Flight Log: Input robustness

**Flight**: [Input robustness](flight.md)

## Summary
Both legs implemented and landed in one execution pass.

---

## Leg Progress

### Leg 1 — ws-crash-proofing (landed)
- `the_one/llm/base.py`: `ImageContent.__post_init__` now raises
  `AssertionError` explicitly (`if self.data is None and self.url is None:
  raise AssertionError(...)`) instead of a bare `assert`, matching
  `Message.__post_init__`'s convention — survives `python -O`.
- `the_one/interfaces/web/app.py`: the `content = _build_user_content(user_input,
  images)` call (websocket_endpoint message branch) is now wrapped in a
  narrow `try/except Exception` — scoped to that one line only, not
  `receive_text()` and not the whole loop body. On failure: `logger.exception(...)`
  + `await ws.send_json({"type": "system", "content": f"Cannot process
  message: {exc}"})` + `continue`, mirroring the sibling auto-create/new_session
  except blocks in the same function. The outer `try` (already present) still
  owns `WebSocketDisconnect` handling — verified a mid-loop disconnect still
  exits the loop cleanly (not swallowed by the new inner guard).
- Tests: `tests/test_llm_base.py::TestContentBlockConstruction::test_image_content_requires_data_or_url`
  (docstring updated to state the -O rationale), `tests/test_ws_build_user_content.py::TestMalformedImagePayloadRaises`
  (unit-pins `_build_user_content` raising `TypeError`/`AssertionError` on
  malformed image dicts), and the new `tests/test_ws_message_branch_crash_guard.py`
  (drives the real `websocket_endpoint` against a fake WebSocket — proves the
  malformed-payload turn surfaces a `system` error AND the loop survives to
  process the next message, proves happy-path text/image sends are
  unaffected, and proves a genuine mid-loop disconnect still exits cleanly).

### Leg 2 — image-attachment-cap (landed)
- New named constants in `the_one/interfaces/web/app.py`: `IMAGE_ATTACHMENT_CAP_BYTES
  = 10 * 1024 * 1024` (~10 MB per image, decoded size) and
  `IMAGE_ATTACHMENT_MAX_COUNT = 10` (max attachments per turn), each commented
  with the defense-in-depth rationale and the "no separate total-payload cap"
  decision (count × per-image ≈ 100 MB worst case already bounds the total).
  Follows the codebase's `*_cap_bytes` naming convention; confirmed no
  existing constant was reusable (`_governor.py`/`execution.py` `*_cap_bytes`
  fields are a different subsystem's transport/context budgets).
- Server validation (`app.py`, `websocket_endpoint`): added right after
  `images = payload.get("images") or []`, BEFORE the auto-join block — an
  over-limit payload is rejected without spinning up an unnecessary session.
  Count and per-image size (via `_approx_image_bytes`, `len(data) * 3 // 4`
  base64→bytes approximation) are checked; violations reject via the Leg-1
  error-surfacing shape (`ws.send_json({"type": "system", ...})` + `continue`).
  A well-formed follow-up message after a rejection still auto-joins and
  spawns normally (verified in tests — the rejection doesn't wedge the loop).
- Client (`the_one/interfaces/web/static/js/areas/chat.js`): mirrored
  constants near `stagedImages`, plus a per-file size check and a
  batch-aware count cap (`plannedCount`, tracking staged-or-scheduled images
  across one multi-select batch — FileReader is async, so a naive
  `stagedImages.length` check alone would under-count mid-batch) in the
  `fileInputEl` `change` handler. Rejections surface via the established
  `addMsg('system', ...)` mechanism. No `pendingQueuedMessages` interaction
  needed — attach is already blocked while the session is busy
  (`isCurrentBusy()` bail).
- Tests: server-side in `tests/test_ws_message_branch_crash_guard.py::TestImageAttachmentCap`
  (over-count and over-size rejection, loop survival, within-limit
  unaffected). Client-side: the Playwright browser harness (`tests/browser/`)
  DOES support driving this flow (it's how the existing image-attach tests
  work), so real browser tests were added rather than a source-scan fallback —
  `tests/browser/test_flow_chat_image_attach.py::test_chat_attach_over_count_caps_at_max_and_notices`
  and `::test_chat_attach_oversized_file_rejected_with_notice`.
- **Review fix (post-landing):** the Leg-2 cap-check block ran BEFORE the
  Leg-1 `try/except` guard and was itself unguarded against a malformed
  `images` *shape* (as opposed to a malformed per-image dict, which Leg 1
  already covers) — `images` as a non-list (e.g. an int) crashed
  `len(images)` with `TypeError`; `images` as a string handed
  `_approx_image_bytes` individual characters, crashing with
  `AttributeError`; `images` as a list of non-dicts crashed `img.get(...)`
  the same way. None were caught, so all three reintroduced the exact
  connection-killing crash class Leg 1 was written to fix. Fixed by adding
  an explicit `isinstance(images, list)` + per-item `isinstance(img, dict)`
  check at the top of the `if images:` block, rejecting via the same
  system-event + `continue` shape ("Malformed images payload; expected a
  list of image objects.") before the count/size logic runs. Added a
  defensive `isinstance(img, dict)` backstop inside `_approx_image_bytes`
  itself (returns 0 for a non-dict `img`) so the helper stays safe even if
  called directly. New tests in
  `tests/test_ws_message_branch_crash_guard.py::TestMalformedImagesShapeSurvivesLoop`
  cover all three malformed shapes (`images: 123`, `images: "hello"`,
  `images: ["not-a-dict", "also-not"]`), each asserting a system error
  surfaces and the loop survives to process the next message.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
