# Squawk 0242: agents.md lacks the sortie 05 conventions and the live push's single-process assumption

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
Sortie 05 (Live Chats list and connector chats) used several general patterns that `the_one/agents.md` documents only inside the feature sections, not as named Project Conventions. The next writer or push will not find them there. The live push also silently assumes one server process. Recommended in `sorties/05-live-chats/flight-debrief.md` (recommendation 5).

## Evidence
- `the_one/agents.md` "Live Chats list push" and "Live open connector chat" describe the mechanics but name no convention.
- The signal (`the_one/db/_session_changes.py`), the listener (`app.py::_SessionsPushListener`) and the socket registry (`the_one/sessions/_broadcast.py`) are all in-process. A second server process, or the CLI writing to the same database, produces no push. This is not stated anywhere.
- Stub DMs from different peers on the same (empty) `channel_id` resolve to one chat (`tests/browser/seeders.py::stub_inbound`, `channel_id=`). The only record of this is the flight log.

## Corrective Action
*(written at completion)*

## Verification
- `the_one/agents.md` "Project Conventions" gains named entries for:
  - notify-after-commit / broadcast-after-lock-release;
  - fingerprint-over-timestamp for cache freshness;
  - a push-only frame type (never reuse a reply frame; squawk 0085).
- "Live Chats list push" states the single-process assumption.
- The UI test apparatus or stub connector section notes the per-peer `channel_id` for stub DMs.
- Docs only; `ruff` and the doc-pin unit tests (if any reference these sections) still pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
