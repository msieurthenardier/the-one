# Squawk 0213: Behavior specs still use `/tmp` scratch data directories and `make down` teardown

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-11-03

## Report
After squawk 0212, CLAUDE.md's behavior-test convention puts the scratch data directory under `$HOME` (not `/tmp`) and stops the instance by its recorded PID. Several behavior specs still name `/tmp/...` scratch data directories and tell the operator to stop with `make down`, which conflicts with the new convention. Found by the squawk 0208–0212 batch Reviewer.

## Evidence
- `/tmp` scratch data directories remain in `tests/behavior/jump-to-palette.md`, `list-and-detail.md`, `start-a-chat.md`, `workbench-navigation.md`, `stub-connector-round-trip.md` and the `kb-*` specs.
- "`make down` against the same env" stop instructions remain, for example in `kb-folder-watch-round-trip.md` step 8.

## Corrective Action
Re-grepped `tests/behavior/*.md` for `/tmp` and `make down`. Instance data directories, credential paths and stop instructions only were changed, nothing a spec tests:
- Data dir moved to `$HOME/the-one-behavior-test-scratch/<name>/data`: `agent-history-auto-purge`, `directory-lookup-send`, `list-and-detail` (both mentions), `start-a-chat`, `workbench-navigation` (both mentions), `discord-live-round-trip` (the credential path now `.../data/api-credential`, matching its boot block), `kb-folder-index-round-trip`, `kb-folder-watch-round-trip`, `kb-agent-query-round-trip` (`<scratch>` is now stated as under `$HOME`). `mcp-sensitive-headers-round-trip` already used `$HOME`; it gained example `$HOME` paths (0282 pass).
- `make down` replaced by "kill the recorded PID" in `kb-folder-index-round-trip` step 9 and `kb-folder-watch-round-trip` step 8; the `make up` / `make down` observable wording in both and `make up`'s "verify step fails without a credential" text in all three kb specs now says a fresh data directory has no `api-credential` (`serve` does not create it) and to run `the-one rotate-api-credential` before the first start. `kb-folder-index-round-trip`'s live-kill variant now names `<scratch>/cwd/serve.pid` instead of the Makefile PID file. `start-a-chat`, `list-and-detail`, `agent-history-auto-purge`, `directory-lookup-send` also gained the rotate-api-credential line (as `workbench-navigation` and `list-and-detail` already had).
- Left as `/tmp` on purpose: (a) the `kb-*` fixture folders (`/tmp/kb-query-fixture`, `/tmp/kb-round-trip/fixture`, `/tmp/kb-watch-fixture`): they are the knowledge folder under test and must sit on a native filesystem outside `<scratch>`, not the instance's data dir or cwd (each now says so); (b) `pty-session-containment` step 2's ephemeral-`/tmp` text, which describes the sandbox's tmpfs under test; (c) `/tmp/behavior-tests/...` evidence paths in run logs (methodology). Ports (several specs still say 8485) are out of this squawk's scope and unchanged.

## Verification

**Partial progress, Mission 31 Flight 6 leg 09b (2026-10-27; the squawk stays open):** five specs were deliberately re-authored before the mission-close sweep: `chat-roundtrip`, `studio-agent-crud`, `agent-step-limit-notice`, `stub-connector-round-trip` and `jump-to-palette` now name "a dedicated port of 8490 or higher (not 8485)" and a scratch data and working directory under `$HOME` (no `/tmp`, no 8485/8488). These five are cleared. `list-and-detail`, `start-a-chat`, `workbench-navigation` and the `kb-*` specs, and the `make down` stop instructions, remain open here. In the B5 fix pass `system-provider-config.md`'s mentions of `App.confirmDelete` (the retired alias) were re-authored to `App.ui.confirm` (descriptive wording only, no Expected Result change).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
