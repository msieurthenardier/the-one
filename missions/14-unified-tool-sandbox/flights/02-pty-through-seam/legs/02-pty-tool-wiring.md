# Leg: pty-tool-wiring

**Status**: completed
**Flight**: [PTY Through the Seam](../flight.md)

## Objective

Thread the host-workspace `SandboxProfile` from the tool layer into the PTY session:
`ShellSessionStartTool.execute` builds the profile via `_build_tool_profile(fs_cfg,
exec_cfg)` (the same policy source as the one-shot tools) and passes it to
`create_pty_session(...)`, so a tool-launched session is actually bwrap-wrapped on
Linux — and fix the mock-lambda signatures the new `profile=` kwarg would otherwise
break.

## Context

- **Design decisions** (from `flight.md`): DD3 (reuse `_build_tool_profile` — one
  policy source, real `$HOME`), DD2 (single-path seam — the profile is what makes the
  Linux session enforced rather than a strict empty cage).
- **Depends on Leg 1** (`pty-platform-seam`, landed): `create_pty_session` /
  `UnixPtySession` now accept `profile: … | None`; with no profile on a bwrap host
  the session is a strict cage (no writable paths). This leg supplies the real
  profile so tool-launched sessions are capable-within-workspace.
- **Leg 1 deviation to reconcile** (from flight log): Leg 1 pinned
  `tests/test_session_tools.py::test_end_to_end_real_pty_round_trip` to passthrough
  because single-path + no-profile made the strict cage block its `/tmp` workspace.
  **The pin must stay** (see Edge Cases — bwrap lays a fresh tmpfs at `/tmp`, so a
  `tmp_path` workspace is invisible under real bwrap regardless of profile; this is a
  tool-layer round-trip test, not a containment test). This leg corrects that pin's
  *rationale comment* — it is not removed.

## Inputs

What exists before this leg runs:
- `the_one/tools/sessions.py` — `ShellSessionStartTool.execute` imports from
  `the_one.tools.execution` (`sessions.py:54-60`), validates cwd via `_cwd_check`
  (`sessions.py:135`), and calls `create_pty_session(cwd=canonical_cwd)`
  (`sessions.py:139`) with `exec_cfg`/`fs_cfg` already in scope
  (`sessions.py:109,112`).
- `the_one/tools/execution.py:424` — `_build_tool_profile(fs_cfg, exec_cfg) ->
  SandboxProfile` (the shared host-workspace profile builder; real `$HOME`, writable
  allowlist, denylist overlay, network from `ExecutionConfig.sandbox_network_allowed`).
- `tests/test_session_tools.py` — four `create_pty_session` monkeypatch lambdas with
  signature `lambda cwd=None, shell=None: MockPtySession()` (`:67,93,113,134`), and
  the `test_end_to_end_real_pty_round_trip` passthrough pin from Leg 1 (`:314-320`).

## Outputs

What exists after this leg completes:
- `ShellSessionStartTool.execute` builds `_build_tool_profile(fs_cfg, exec_cfg)` and
  passes `profile=` to `create_pty_session`.
- The four mock lambdas accept `profile=None` (no `TypeError` from the new kwarg).
- A plain unit test for `_build_tool_profile(FilesystemConfig(), ExecutionConfig())`
  (default-allowlist production path) exists (debrief action item).

## Acceptance Criteria
- [x] `the_one/tools/execution` import in `sessions.py` includes `_build_tool_profile`.
- [x] In `ShellSessionStartTool.execute`, after `canonical_cwd = _cwd_check(...)`,
      a profile is built: `profile = _build_tool_profile(fs_cfg, exec_cfg)` and passed
      to `create_pty_session(cwd=canonical_cwd, profile=profile)` (`sessions.py:139`).
      No other behavior in `execute` changes (cap check, registry register, error
      envelope all unchanged).
- [x] The four `create_pty_session` monkeypatch lambdas in `tests/test_session_tools.py`
      (`:67,93,113,134`) accept the new kwarg: `lambda cwd=None, shell=None,
      profile=None: MockPtySession()`. (The mock never reaches the factory — this is a
      signature fix, NOT passthrough-pinning.)
- [x] `test_end_to_end_real_pty_round_trip` keeps its passthrough pin; its comment is
      corrected to the accurate rationale (the `/tmp` tmpfs shadows a `tmp_path`
      workspace under real bwrap; this is a tool-layer round-trip test, real-bwrap
      containment is covered by `test_pty_sandbox.py` + the behavior test).
- [x] A unit test asserts `_build_tool_profile(FilesystemConfig(), ExecutionConfig())`
      produces the expected default-allowlist production profile: `writable_paths` =
      the canonical default allowlist (real `~`), `readonly_overlay_paths` = the
      canonical default denylist, `network_allowed` is `False`, `home` =
      `str(Path.home())`. Placed in `tests/test_execution_tools.py` (passthrough-pinned
      execution unit tests) or the nearest existing `_build_tool_profile` unit home.
- [x] `tests/test_session_tools.py` and `tests/test_session_tools.py` green;
      `ruff check` + `ruff format --check` clean on touched files.

## Verification Steps
- `docker exec the-one pytest tests/test_session_tools.py tests/test_session_lifecycle.py -x --timeout 30`
  — green (mock lambdas accept `profile=`; round-trip still pinned).
- `docker exec the-one pytest tests/test_execution_tools.py -x --timeout 30` — green
  (incl. the new `_build_tool_profile` default-allowlist unit test).
- `docker exec the-one pytest tests/test_pty_session.py -x --timeout 30` — still green
  (Leg 1 regression check; untouched here).
- `docker exec the-one ruff check the_one/tools/sessions.py tests/test_session_tools.py tests/test_execution_tools.py`
  and `ruff format --check` — clean.

## Implementation Guidance

1. **Wire the profile into the start tool.**
   - In `sessions.py`, add `_build_tool_profile` to the existing
     `from the_one.tools.execution import (…)` block (`sessions.py:54-60`).
   - In `ShellSessionStartTool.execute`, after `canonical_cwd = _cwd_check(target_cwd,
     fs_cfg)` (`sessions.py:135`), add `profile = _build_tool_profile(fs_cfg,
     exec_cfg)` and change the call (`sessions.py:139`) to
     `create_pty_session(cwd=canonical_cwd, profile=profile)`.
   - Leave the comment above the call (about `Path | None`) intact / adjust minimally.

2. **Fix the mock lambdas (the high issue from flight design review).**
   - Update each of the four lambdas (`:67,93,113,134`) to
     `lambda cwd=None, shell=None, profile=None: MockPtySession()`. Without this they
     raise `TypeError` the moment `execute` passes `profile=`.

3. **Correct the round-trip pin rationale (do not remove the pin).**
   - Update the docstring/comment at `test_session_tools.py:314-320` so it no longer
     says "until Leg 2 wires the profile." State the real reason: under real bwrap the
     fresh tmpfs at `/tmp` shadows a `tmp_path` workspace, so this tool-layer
     round-trip test runs under passthrough by design; real-bwrap containment lives in
     `tests/test_pty_sandbox.py` and `/behavior-test pty-session-containment`.

4. **Add the `_build_tool_profile` default-allowlist unit test (debrief action item).**
   - In `tests/test_execution_tools.py`, **add `_build_tool_profile` to the existing
     `from the_one.tools.execution import (…)` statement** (`test_execution_tools.py:34`,
     currently `import ExecutionConfig, PythonExecConfig`).
   - Add a test calling `_build_tool_profile(FilesystemConfig(), ExecutionConfig())`
     and asserting the profile fields:
     - `writable_paths == [str(Path.home())]` (the canonical default allowlist —
       `FilesystemConfig()._canonical_allowlist == [Path.home()]`).
     - `readonly_overlay_paths == [str(p) for p in FilesystemConfig()._canonical_denylist]`
       — compare against the **canonical** (resolved absolute) denylist, NOT
       `path_denylist` (the `~/.ssh` tilde form); `_build_tool_profile` emits
       `str(p)` over `_canonical_denylist`.
     - `network_allowed is False`; `home == str(Path.home())`.
   - This pins the production default path that until now was only exercised
     indirectly by `@requires_bwrap` tests. (The file's passthrough-pin autouse
     fixture is irrelevant here — `_build_tool_profile` never calls the factory.)

## Edge Cases
- **`tmp_path` workspace under real bwrap:** bwrap mounts a fresh tmpfs at `/tmp`, so
  any workspace under `/tmp` is invisible inside the sandbox (see
  `test_builtin_tool_sandbox.py:1-12`). The round-trip test therefore stays on
  passthrough — supplying a profile does NOT make it runnable under bwrap. Do not try
  to "un-pin" it by adding the tmp path to the allowlist.
- **`exec_cfg`/`fs_cfg` availability:** both are already resolved at the top of
  `execute` (`sessions.py:109,112`) — no new config plumbing needed.
- **No change to `ShellSessionSendTool`/close/list:** only the *start* path constructs
  the session, so only it needs the profile (send/close operate on an
  already-wrapped session).
- **Behavior unchanged off-Linux / bwrap-missing:** `_build_tool_profile` always
  produces a profile, but passthrough ignores it — so non-Linux tool sessions behave
  exactly as today (no enforcement, no error).

## Files Affected
- `the_one/tools/sessions.py` — import + build/pass the profile in the start tool.
- `tests/test_session_tools.py` — mock-lambda `profile=None`; round-trip pin comment.
- `tests/test_execution_tools.py` — new `_build_tool_profile` default-allowlist unit test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`test_session_tools.py`, `test_session_lifecycle.py`,
      `test_execution_tools.py`, and Leg-1 `test_pty_session.py` regression)
- [x] Update flight-log.md with a leg progress entry (append)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off the leg in flight.md, do NOT land the flight
- [x] **Do NOT commit** — batched workflow: review + commit after the last leg.
      Signal `[HANDOFF:review-needed]`.
