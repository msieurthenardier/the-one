# Leg: hat-and-alignment

**Status**: completed
**Flight**: [Honest MCP sign-in in the desktop app](../flight.md)

## Objective
Walk the charter's four criteria with the operator on the real Windows desktop app (WebView2) and in a normal browser, against the OAuth fixture, fixing anything that fails.

## Context
- Flight DD8. Leg 01 is committed (`d4059be`, PR #288). This is the only check in the real WebView2 engine (squawk 0138).
- Interactive: the Flight Director guides one step at a time; the operator acts and reports. Fixes follow the agentic-workflow fix-vs-feature gate; a code fix gets a Developer, a re-verify, and a commit.
- Accessibility nits carried from the flight review, observed here: the editor's first status text may not be announced; "Copied" may be announced twice; focus falls to `body` when the block clears on a successful sign-in.
- Open question carried from the flight: does a `window.open` from a WebSocket handler (chat auto-open) reach the system browser in WebView2?

## Inputs
- A Windows test copy of `d4059be` (`scripts/windows_test_copy.py setup`, non-frozen `launch --port 8490 --data-dir <root>\data-hat`), bracketed by `snapshot --out` / `--compare`.
- An OAuth fixture runner on the dev box (scratchpad script, not committed): stub A (`OAuthASStub`, sign-in server), stub B (`OAuthASStub(bare_401=True)`, key server), and a control endpoint to change A's accepted token and refresh status and B's accepted token.
- A real model provider in the scratch instance (dev mode is off in the test copy, so no mock provider) and an agent with both MCP sources attached.

## Acceptance Criteria
- [x] H1 (charter 2). Desktop app, MCP editor: Test connection on stub A opens the consent page in the system browser (or the "Open sign-in page" link does), and the editor lists the `echo` tool by itself, with no manual re-test; no "Popup blocked".
- [x] H2 (charter 1). Desktop app, chat: with A's token rejected and refresh refused, a tool call shows the sign-in link; finishing consent in the system browser resumes the tool call; no "Popup blocked"; a reconnect (reload) keeps the link and does not open another browser tab.
- [x] H3 (charter 3). Desktop app: stub B with a wrong key: Test connection shows "The server rejected the configured credentials." (path (a) with cached `no_auth`, and path (c) after Reset connection); a chat tool call returns the rejected-credentials error with no "Log in" button.
- [x] H4 (charter 4). Normal browser (via a handoff link to the test copy): sign-in from the MCP editor opens a popup as before, and the link block is shown.
- [x] H5. Observations recorded: chat auto-open in WebView2 (reached the browser or not); the three accessibility nits (keep or fix, operator's call).
- [x] H6. `snapshot --compare` clean; the test copy and the fixture runner stopped by recorded PID.

## Verification Steps
Operator observation per step, recorded in the flight log with the step's result; fixes recorded with their commit.

## Implementation Guidance
1. Snapshot, setup, launch the test copy; start the fixture runner; confirm Windows reaches the runner's ports.
2. Operator: add a model provider and an agent in the test copy; add MCP sources A (no headers) and B (`Authorization: Bearer good`).
3. H1, then H2, then H3, then H4 (mint the handoff link from the test copy's `api-credential`), then H5.
4. Stop everything, compare the snapshot.

## Edge Cases
- **Mirrored networking**: if Windows cannot reach the runner on 127.0.0.1, bind the runner differently or run it on Windows with `C:\Python311\python.exe`.
- **Refresh races**: A's refresh must be refused for H2, or the client silently refreshes and no sign-in is needed.

## Files Affected
- None planned. Fixes, if any, are recorded per step.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
