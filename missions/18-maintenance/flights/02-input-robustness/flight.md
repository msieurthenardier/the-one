# Flight: Input robustness

**Status**: landed
**Mission**: [Post-Mission-16 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] A malformed `images` payload no longer crashes the WS loop; `ImageContent` guard is `raise` (S1 + S2)
- [ ] Image attachments have a size/count cap (S3)

---

## Pre-Flight

### Objective
Make the Mission-16 image-ingestion path crash-resistant against malformed or
oversized client payloads — the input-robustness cluster.

### Open Questions
N/A.

### Design Decisions
N/A (maintenance).

### Prerequisites
- [x] Mission-16 image path landed (`_build_user_content`, `ImageContent`)

### Pre-Flight Checklist
- [x] Open questions — N/A
- [x] Design decisions — N/A
- [x] Prerequisites verified
- [x] Validation approach defined (unit tests for both guards + the cap)
- [ ] Legs defined (during `/agentic-workflow`)

---

## In-Flight

### Technical Approach

**Leg 1 — Crash-proof the WS message branch (S1 + S2, fixed together).**
Evidence: `app.py:2234` calls `_build_user_content(user_input, images)` →
`ImageContent(**img)` (`app.py:485`) inside the `websocket_endpoint` `while True`
loop, which is guarded only by `except WebSocketDisconnect` — unlike the sibling
`join`/`new_session` branches which catch broadly (`app.py:2101-2112`,
`2142-2152`). A client-supplied image dict with an unexpected key raises
`TypeError`; one missing both `data` and `url` raises `AssertionError`
(`llm/base.py:76-79`, a bare `assert` — stripped under `python -O`). Either kills
the connection's receive loop.
Two coupled fixes:
1. `llm/base.py:76-79` — convert the `ImageContent.__post_init__` bare `assert
   self.data is not None or self.url is not None` to `raise AssertionError(...)`,
   matching the sibling `Message.__post_init__` and the convention `agents.md:198`
   documents. (S2)
2. `app.py` message branch — wrap the message-processing path in a generic
   `except Exception` that mirrors the sibling branches (log + surface an error to
   the client, keep the loop alive), so a malformed `images` payload degrades to an
   error response instead of a dropped connection. (S1)
Tests: a malformed-`images` unit/integration test asserting the loop survives and
an error is surfaced; a `-O`-mode-equivalent test (or explicit `raise`) for the
`ImageContent` guard.

**Leg 2 — Image size/count cap (S3).**
Evidence: no cap anywhere — `chat.js:1537-1567` stages every `image/*` file with no
per-file size check and no bound on `stagedImages.length`; `app.py:2200`
(`images = payload.get("images") or []`) accepts the array with no validation.
Under the local posture this is self-DoS/memory-pressure, not multi-tenant, so a
lightweight defense-in-depth cap suffices:
- Client (`chat.js`): reject/skip a file over a per-image byte threshold and cap
  the number of staged images, with a user-visible notice (coordinate with the
  Flight 3 a11y live-region so the rejection is announced).
- Server (`app.py`): validate image count + per-image approximate byte size before
  building the content list; reject over-limit with a clear error rather than
  forwarding an oversized payload to the provider.
Pick conservative limits (document them); make the constant discoverable, not
magic-buried.

### Checkpoints
- [x] Malformed `images` payload → error surfaced, connection stays up (test)
- [x] `ImageContent` guard raises under `-O` semantics (test)
- [x] Over-size / over-count attachment rejected client + server (test)

### Adaptation Criteria
**Divert if**: crash-proofing the message branch reveals other unguarded raise
sites in the same loop worth catching — note them; fix in-scope only if trivial.
**Acceptable variations**: exact byte/count thresholds.

### Legs
> Planned one at a time during `/agentic-workflow`.
- [x] `ws-crash-proofing` — `ImageContent` raise + generic except on the message branch (S1/S2)
- [x] `image-attachment-cap` — client + server size/count limits (S3)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged (PR opened; merge on land)
- [x] Tests passing (3986 passed / 0 failed; crash-guard 11/11 incl. malformed shapes; browser 7/7)
- [x] Documentation updated (cap constants documented inline)

### Verification
Malformed and oversized payloads are handled gracefully (tests); the connection no
longer drops on a bad `images` dict; suite green.
