# Squawk 0242: agents.md lacks the sortie 05 conventions and the live push's single-process assumption

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-11-03

## Report
Sortie 05 (Live Chats list and connector chats) used several general patterns that `the_one/agents.md` documents only inside the feature sections, not as named Project Conventions. The next writer or push will not find them there. The live push also silently assumes one server process. Recommended in `sorties/05-live-chats/flight-debrief.md` (recommendation 5).

## Evidence
- `the_one/agents.md` "Live Chats list push" and "Live open connector chat" describe the mechanics but name no convention.
- The signal (`the_one/db/_session_changes.py`), the listener (`app.py::_SessionsPushListener`) and the socket registry (`the_one/sessions/_broadcast.py`) are all in-process. A second server process, or the CLI writing to the same database, produces no push. This is not stated anywhere.
- Stub DMs from different peers on the same (empty) `channel_id` resolve to one chat (`tests/browser/seeders.py::stub_inbound`, `channel_id=`). The only record of this is the flight log.

## Corrective Action
Docs only. `the_one/agents.md` Project Conventions gained `notify-after-commit` / `broadcast-after-lock-release`, `fingerprint-over-timestamp` (`Session.db_fingerprint`) and `push-only-frame-type` (squawk 0085). "Live Chats list push" now states the single-process assumption (signal, listener and socket registry are in-process; a second server process or the CLI writing the same database produces no push). "UI test apparatus" gained the stub-DM per-peer `channel_id` note (`seeders.py::stub_inbound(channel_id=)`).

## Verification
Done: all three bullets met; `THE_ONE_TEST_NETNS=1 make test-unit`: 8724 passed, 15 skipped. No new tests.
- `the_one/agents.md` "Project Conventions" gains named entries for:
  - notify-after-commit / broadcast-after-lock-release;
  - fingerprint-over-timestamp for cache freshness;
  - a push-only frame type (never reuse a reply frame; squawk 0085).
- "Live Chats list push" states the single-process assumption.
- The UI test apparatus or stub connector section notes the per-peer `channel_id` for stub DMs.
- Docs only; `ruff` and the doc-pin unit tests (if any reference these sections) still pass.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
