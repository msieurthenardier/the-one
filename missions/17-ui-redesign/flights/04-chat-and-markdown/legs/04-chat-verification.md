# Leg: chat-verification

**Status**: completed
**Flight**: [Chat Re-skin + Markdown Hardening](../flight.md)

## Objective

Flight-wide verification of the chat re-skin + markdown hardening: full suites, dual-theme visual pass (focus via CDP), author the `chat-roundtrip` behavior spec (mock provider), and record the sink/registry + browser-wall-clock ledger. (FD delegates the behavior-gate RUN afterward.)

## Scope

- `make test-unit` (record count + timing); `TEST_TIMEOUT=3600 make test-browser` FULL suite once. FLAKE DISPOSITION (pre-specified, F2/F3 rule): a failure that passes in isolation AND on one clean rerun of ITS MODULE is a flake (log it); only rerun the FULL suite if >2 modules flake. Record final counts + **browser wall-clock** (F3 debrief asked to measure — flag if a per-area lane is now due).
- Dual-theme visual pass on 8485 (THE_ONE_PORT=8485; hard-reload per doctrine — CSS not cache-busted on restart): chat empty/welcome state; a populated session (user tinted bubble + agent prose + a code block + an inline code + a tool-trace `<details>` + a thinking disclosure); the composer with the stop button visible (drive a mock stream) + send; both themes. Focus states via a CDP page (composer input, stop, send, copy button). printToPDF pixels; record+restore theme preference; close own tabs.
- **Author `tests/behavior/chat-roundtrip.md`** (do NOT run it — the FD delegates the run): mock-provider chat round-trip. Preconditions: instance under test (8485 default per M17) launched with `THE_ONE_DEV_MODE=true` (state a precondition-check + a relaunch note); seed a mock provider (`config.response` = a markdown reply e.g. `"Hello **world** and `code`"`, `stream_chunks` = a LIST of strings) + a mock agent (via `seed_mock_provider`/`seed_mock_agent` OR the UI). Steps (goldfinch apparatus, doctrine — printToPDF fallback, a11y-tree, CDP for focus): open chat → start a session with the mock agent → send a message → (streaming) the stop button appears while the assistant streams → on done the assistant reply renders with **bold** and inline-code as real markup (not literal) → reload → the session + rendered markdown survive. Both-theme variant. Reference the SC7 requirement.
- Sink/registry ledger in flight log; confirm the Leg-1 invariant guard + XSS suite + JS-dead-CSS-var tripwire all green; confirm sink baseline honest (92) after the chat churn.
- Regenerate pixel snapshots locally (NOT committed; verify untracked; not as root).

## Acceptance Criteria

- [x] Unit green; full browser suite 0 failures per the flake disposition; browser wall-clock recorded
- [x] `test_markdown.py` facade net green; invariant guard + XSS suite + tripwire green
- [x] Visual pass evidence recorded (both themes, enumerated chat surfaces + focus via CDP); no alien-console remnants (SC1 spot-check on the chat surface)
- [x] `chat-roundtrip.md` behavior spec authored (well-formed per ARTIFACTS.md; NOT run here)
- [x] Ledger in flight log; `git status` clean of snapshots; ruff clean

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry (suite counts, wall-clock, ledger, visual-pass record); leg `landed`; checked off in flight.md (behavior gate noted FD-pending)
