# Squawk 0176: The rules-and-notes tab's `App.time` listener accumulates per mount

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
Each mount of the notes section subscribes to `App.time.onChange`, and the listener only unsubscribes itself when it next fires with its list disconnected. Zone changes are rare, so a long-lived desktop session accumulates one closure (and its detached DOM) per tab open.

## Evidence
`static/js/areas/studio/rules-notes-tab.js` (notes `renderList` subscription, the `isConnected` self-unsubscribe). The fix: an owner-scoped `App.time.onChange(fn, ownerEl)` that prunes disconnected owners on every subscribe, or a teardown hook for Studio tabs. Found by the M28 F2 debrief Architect.

Logged from the Mission 28 flight debriefs.

## Corrective Action
`App.time.onChange(fn, ownerEl)` (static/js/time.js) gains an optional owner element. Listeners are stored as `{fn, owner}`; every subscribe and every zone change prunes entries whose owner is no longer connected, so detached notes lists are released the next time any tab mounts, not only when the zone changes. `onChange(fn)` without an owner behaves as before (returns an unsubscribe). The notes section in rules-notes-tab.js now passes `listWrap` as owner and drops its self-unsubscribe. Chosen over a Studio teardown hook because it is additive, local to the reported surface, and needs no change to the tab lifecycle. A test-only `App.time._listenerCount()` was added and documented in the_one/agents.md.

## Verification
- Static guards (test_ui_guards, test_token_definitions, test_design_tokens_a11y, test_time_getters_static): 271 passed.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 ... run-tests.sh -m browser tests/browser/test_ui_time_contract.py tests/browser/test_flow_chat_time_zone.py -x`: 24 passed (Chromium + WebKit; includes two new owner-pruning contract tests and the extended tab-switch flow test: repeated switches, one live re-render, bounded listener count, no errors).
- ruff check / format --check on tests/browser clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
