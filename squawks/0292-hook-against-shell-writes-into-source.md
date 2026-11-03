# Squawk 0292: A PreToolUse hook should refuse shell writes into source

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-03

## Report
Squawk 0286 put "edit source and test files only through the edit tool" into both Developer prompts, yet three of seven Developers in Mission 33 Flight 4 wrote into source or tests through the shell (`sed -i`, heredoc appends). Each self-reported and a reviewer verified the diff, but a written rule did not hold. The operator chose a mechanical guard at the Flight 4 debrief.

## Evidence
- `missions/33-routines/flights/04-hat-and-alignment/flight-debrief.md`, Methodology Observation 2 and Recommendation 2.
- The flight log's fix pass 1, leg 05 and fix pass 3 entries.
- No project `.claude/settings.json` exists yet (only `settings.local.json`).

## Corrective Action
Added `.claude/settings.json` (a `PreToolUse` hook, matcher `Bash`, command `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/block_shell_writes.py"`) and the stdlib-only script `.claude/hooks/block_shell_writes.py`. `.claude/settings.local.json` was not touched; `.gitignore` ignores only `settings.local.json` and `scheduled_tasks.lock`, so the two new files are committable (`git check-ignore` reports nothing). A one-paragraph pointer was added next to the squawk 0286 rule in `.flightops/agent-crews/leg-execution.md`. The hook does not take effect in already-running sessions; the unit test is the verification.

Contract: the hook JSON arrives on stdin (`tool_name`, `tool_input.command`, `cwd`); exit 2 blocks and feeds stderr to the model; the message is one line naming the Edit/Write tools and squawk 0286. **Fails open** (exit 0) on unparseable stdin, a non-Bash tool, a missing or non-string command, or any internal exception.

**Protected tree**: `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/`, `evals/`, as a relative path (resolved against the hook's `cwd`, with `cd X &&` tracked) or absolute under the repo root (`$CLAUDE_PROJECT_DIR`, `$HOME` and `~` are expanded; any other `$VAR` cannot be resolved and is let through).

**Denied** (target in the protected tree):
- output redirects `>`, `>>`, `>|`, `&>`, `2>` to such a path
- `sed -i` / `-Ei` / `-ni` / `--in-place`, `perl -i` / `-pi` (any flag cluster containing `i`), `tee`, `truncate`, `dd of=`
- `cp`, `install`, `rsync` whose destination (last operand, or `-t DIR`) is such a path; `mv` with any operand there (moving a source file out edits the tree too)
- inline interpreter scripts (`python*`, `perl`, `ruby`, `node`: `-c`, `-e` or a heredoc) that mention such a path and contain a file-write call (`open(..., 'w'/'a'/'x')`, `write_text`, `write_bytes`, `shutil.*`, `os.rename/remove/...`, `writeFile*`, perl `open(F, ">...")`)
- the same inside `bash -c "..."`, `sh -c`, `eval "..."`, a shell fed a heredoc, `xargs CMD` and `find ... -exec CMD`
- heredoc-into-file (`cat > tests/x <<EOF`) is the redirect rule

**Allowed**: redirects to `/dev/null`, `2>&1`; writes to `/tmp`, the scratchpad, `squawks/`, `$HOME/...` and other paths outside the six directories; `git`, `make`, `pytest`, `scripts/run-tests.sh`, `ruff check`, `ruff format --check/--diff`, `gh`, `grep`, `cat`, `head`, `diff`, `find` and `sed` without `-i` (reads of protected paths are fine, including `cp`/`install` FROM them); inline python that only reads a protected path; `python3 scripts/x.py`.

**Quoting**: a small tokenizer (shlex cannot tell a quoted `>` from an operator) honours single quotes, double quotes, backslashes and `#` comments, so `grep '>' tests/x.py`, `echo "a > b"` and `echo 'a > tests/x.py'` are plain words and pass. `$(...)` inside double quotes is not parsed.

**Known gaps** (not a sandbox; the test is the verification): a script FILE that writes (`python helper.py`), `git apply`/`patch`, `rm`/`touch`, paths built at run time or from unknown `$VARS`, and the interpreter check is deliberately coarse (path mention plus a write call anywhere in the command).

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_shell_write_hook.py --timeout 120 -q`: 100 passed (45 blocked and 50 allowed commands over JSON on stdin via subprocess, cwd resolution, fail-open on bad input, non-Bash tool, settings wiring).
- Falsified: yes. Disabling the redirect rule and the `sed` rule by editing made 26 of the tests fail (blocked-table cases, cwd test); both restored by editing and the file re-passes 100/100.
- `ruff check` and `ruff format --check` on `.claude/` and the test: clean. Found and fixed during development: the `perl` branch shadowed the inline-script check, and the tokenizer dropped quotes the script scan needed (now scans the raw text).

A project `.claude/settings.json` `PreToolUse` hook on `Bash` (a script under `.claude/hooks/`) refuses, with a one-line message naming the Edit/Write tools, a command whose `sed -i`/`perl -i`/`tee`/output redirect/heredoc write/`python` file write/`cp`/`mv`/`install` targets `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/` or `evals/`, while redirects to `/dev/null` and the scratchpad, `git`, `make`, `pytest`, `ruff` and `gh` pass. A unit test feeds the script sample commands (blocked and allowed) and checks the exit codes.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Live evidence: the hook blocked heredoc writes into tests/ from four crew during this batch, and each change was redone with Edit. It also blocked one inline script of the Flight Director's that wrote only to squawks/: a false positive from the coarse inline-interpreter check, which is a documented gap.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator approved adding the project PreToolUse hook** (`.claude/settings.json`). It refuses `sed -i`, heredoc and redirect writes into `the_one/` and `tests/` and will limit autonomous crew's shell use. Write the allow/deny list down in the squawk at completion. Burn-down next turnaround.
