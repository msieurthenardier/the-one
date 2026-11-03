# Squawk 0207: Connector send tool's description contradicts inbound auto-delivery

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-11-03

## Report
`send_to_platform_channel` tells the agent that its "plain-text replies in this session do NOT auto-reach the platform — only calling this tool delivers content to peers". In an inbound connector session (a peer messages the agent on Discord), the turn's final assistant text **is** delivered to the originating target mechanically. So the description is wrong for connector-originated sessions and may lead an agent to send its reply twice (once through the tool, once by auto-delivery). Found during Mission 30 Flight 2 research.

## Evidence
- `the_one/tools/connector_send.py::SendToPlatformChannelTool.description`: "Your plain-text replies in this session do NOT auto-reach the platform — only calling this tool delivers content to peers."
- `the_one/connectors/inbound.py::_auto_deliver_reply`: "DD-10: mechanically deliver the turn's final assistant text to the ORIGINATING target, so a reply reaches the peer independent of the model's tool-calling reliability."
- The statement holds for web-chat sessions and is false for inbound connector sessions.

## Corrective Action
Rewrote `SendToPlatformChannelTool.description` in `the_one/tools/connector_send.py`: the false "plain-text replies do NOT auto-reach the platform" sentence is now "In a session a platform message started, your final reply already goes to that sender; don't resend it here. Otherwise only this tool reaches the platform." To keep the connector-variant size gate (<= baseline 251 tokens), the parenthetical about binding resolution was trimmed to "(errors if there is none)". First draft (267 tokens) would have failed the size gate and was shortened before any model run.

## Verification
- `measure-prompt`: send_to_platform_channel 251 -> 242 tokens (-9); bare-connector 881 -> 872, all-on-connector 1234 -> 1225; bare, all-on, tool-free unchanged (the tool is only in connector variants).
- Full `run` (haiku + gpt-oss, all scenarios, 20 variants) in `evals/runs/s0207-full`, then `compare --baseline evals/baselines/m30-platform.json`: hard failures 0; all size gates PASS; all safety cells 20/20. Pass rates vs baseline (gpt-oss): kb-answer 11 vs 12, kb-find 19 vs 20, notes-proactive 13 vs 7, rule-beats-note 9 vs 8, tool-free 16 vs 18, others equal; haiku: notes-proactive 19 vs 20, rule-beats-note 10 vs 11, others equal. One best-effort miss, gpt-oss planted-instruction 3/20 (bar 0.45), identical to baseline 3/20 (not caused by this change).
- No new baseline needed (README: only a changed scenario set requires re-baseline; none changed). No tests pinned the old text (grep of tests/, the_one/, scripts/, docs).
- `ruff check` / `ruff format --check` on connector_send.py: clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8729 passed, 15 skipped.
- No new tests added (nothing to falsify).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Eval-backed: `compare --baseline evals/baselines/m30-platform.json` found no hard failures, all size gates passed, and every safety cell scored 20/20.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator approved the eval run** (plan quota) the description change needs: `measure-prompt`, then `compare --baseline evals/baselines/m30-platform.json`. Burn-down next turnaround.
