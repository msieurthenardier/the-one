# Squawk 0239: The knowledge inspect panels do not announce when their content arrives

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-11-03

## Report
"View chunks" and "View source" move focus to the panel's `h3` heading, which announces the file path. The "Loading…" line is `live: 'off'`, and nothing is announced when the chunks or source finish loading. A screen-reader user has no cue that the content is ready. It is acceptable because focus is already on the panel, but a polite "{n} chunks" or "Source loaded" status would close the gap. Found in the Mission 31 Flight 3 accessibility review.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/knowledge-inspect.js`: the loading status (about line 53) and the content render paths.
- Flight 3 flight log, the flight review entry.

## Corrective Action
`knowledge-inspect.js`: each panel now holds a persistent visually hidden `role=status` / `aria-live=polite` region (`kb-panel-announce`), built with the panel so it exists before its text changes. It is cleared on open and on hide, and set after a successful render: "{n} chunks" / "1 chunk" / "No chunks yet" for chunks, "Source loaded" for source. Errors were already announced by the existing alert status line.

## Verification
`test_chunks_open_in_seq_order_and_source_not_prefetched` (knowledge lane) now asserts the region's role, `aria-live` and text for the chunks panel ("No chunks yet") and the source panel ("Source loaded", `/source` stubbed). Falsified: yes (announce assignment removed, test failed; restored). Lane results in the completion report.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
