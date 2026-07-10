# Leg: image-attachment-cap

**Status**: completed
**Flight**: [Input robustness](../flight.md)

## Objective
Add a lightweight size/count cap on chat image attachments — client-side (reject/skip in the composer) and server-side (validate before building the content list).

## Context
Maintenance report 2026-07-10 finding **S3** (known, F12 debrief): no cap anywhere. `chat.js` stages every `image/*` file with no per-file size check and no bound on `stagedImages.length`; `app.py` accepts `images` with no validation. Self-DoS / memory-pressure under the local posture. Defense-in-depth cap, not a hard security boundary.

## Inputs
- `the_one/interfaces/web/static/js/areas/chat.js` (the file-attach change handler + `stagedImages` staging + `performSend` payload, ~line 1523-1567 / staging array).
- `the_one/interfaces/web/app.py` (the `images = payload.get("images") or []` read + `_build_user_content`, ~line 2200).
- Depends on Leg 1 (the WS branch is now crash-guarded) — the server-side reject should surface a clean error, not rely on the crash guard.

## Outputs
- A per-image byte cap + max-attachment-count enforced on both client and server, with a clear user-visible/API error on rejection.

## Acceptance Criteria
- [x] A documented, discoverable pair of limits (named constants, not magic numbers): **per-image ≈ 10 MB, max count = 10** (pinned defaults — defense-in-depth, generous; the provider enforces its own stricter per-image limit). No separate total-payload cap — count × per-image (~100 MB) bounds the total; document that decision. **No existing constant to reuse** (design-review [3]: `_governor.py`/`execution.py` `*_cap_bytes` fields are LLM-context/transport budgets, a different subsystem — do NOT import their 256 KB/1 MB ceilings); follow the `*_cap_bytes` naming convention with a comment justifying the default. (`app.py` `IMAGE_ATTACHMENT_CAP_BYTES` / `IMAGE_ATTACHMENT_MAX_COUNT`; `chat.js` mirrors with the same names.)
- [x] **Client** (`chat.js`): reject/skip a file exceeding the per-image byte limit and cap `stagedImages.length`; give a user-visible notice on rejection. (Coordinate the notice with the Flight 3 a11y live-region — Flight 3 lands after this and will announce it; here, at minimum, surface it visibly.) Notice via `addMsg('system', ...)`.
- [x] **Server** (`app.py`): validate image count + per-image approximate byte size (base64 length → bytes) before building the content list; reject over-limit with a clear error event to the client (using the Leg-1 error-surfacing path), not by forwarding an oversized payload to the provider.
- [x] Tests: a server-side unit/integration test that an over-count / over-size `images` payload is rejected with the expected error (and the loop survives) — `tests/test_ws_message_branch_crash_guard.py::TestImageAttachmentCap`. A client-side test: the JS test harness (Playwright, `tests/browser/`) DOES support this, so real browser tests were added rather than falling back to a source-scan — `tests/browser/test_flow_chat_image_attach.py::test_chat_attach_over_count_caps_at_max_and_notices` / `::test_chat_attach_oversized_file_rejected_with_notice`.
- [x] Well-formed within-limit sends are unchanged.
- [x] `git diff` limited to `chat.js`, `app.py`, + test files (+ flight artifacts).

## Verification Steps
- Server test: over-limit payload → rejected + loop alive.
- Confirm the limit constant is discoverable (grep-able name) and documented.

## Implementation Guidance
1. Define the limits as named constants (server-side authoritative; client mirrors for UX). Base64 → bytes ≈ `len(b64) * 3/4`. Follow the `*_cap_bytes` naming convention (`_governor.py`/`execution.py`) but do NOT reuse their tiny ceilings.
2. **Server** (design-review suggestion): validate right after `images = payload.get("images") or []` (~line 2200), **before the auto-join block** (~2205-2216), so a rejected oversized payload doesn't spawn an unnecessary session. Reject via the Leg-1 `ws.send_json({"type":"system",...})` + `continue` path.
3. **Client**: check each file's size in the `fileInputEl` `change`/FileReader handler (~chat.js:1549); cap `stagedImages.length`; surface the notice via the established `addMsg('system', ...)` mechanism (design-review). **No `pendingQueuedMessages` interaction** — attach is already blocked while busy (`isCurrentBusy()` bail at chat.js:1534/1549); note this in the flight log.
4. Keep limits conservative and documented; defense-in-depth, not a strict security control.

## Edge Cases
- Multiple images summing large but each under the per-image cap — the count cap bounds this; note whether a total-payload cap is also warranted (optional; document the decision).
- A client that bypasses the JS cap → the server cap is the authoritative guard.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js`, `the_one/interfaces/web/app.py`, test files.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] **Final leg** — batch-reviewed (1 blocking: cap-check ran before the Leg-1 guard, crashing on malformed `images` shapes → fixed with explicit shape validation + 3 tests; re-verified), committed/PR
