# Squawk 0433: the mid-turn join test fails under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report

`tests/browser/test_flow_chat_live_updates.py::test_a_message_sent_during_a_mid_turn_join_is_held_then_delivered` fails at load 18 to 25: `_join_mid_turn` (line 255) reloads the chat for 20 s and each try waits 2.5 s for the "working" indicator, so a slow boot or a short stub turn means it never joins mid-turn ("never joined while the connector turn was running"). It failed in the `chats` lane and again in isolation, at load 18. Sortie 20 recorded the same test failing on a pristine `main` (squawk 0428 evidence), so it is not from Mission 37 Flight 2. Flight 2 had no quiet host and did not observe it passing.

## Evidence
- Flight 2 Leg 4 fallback gate: `chats` lane, 1 failed; isolation re-run at load 17.9 failed too.
- The other half of the "different class" pair in 0428, `test_overlay_custom_warn_threshold_moves_transition`, was an `httpx` 5 s read timeout; Leg 4 raised that to 30 s and it passes.

## Corrective Action
*(written at completion)* Suggested: have the stub turn hold until the join is seen, instead of racing a retry loop against its length.

## Verification
*(written at completion)* None yet. Leg 4's only isolation run, at load 17.9, failed. No passing run exists on record.

## Sign-Off
*(written at completion)*
