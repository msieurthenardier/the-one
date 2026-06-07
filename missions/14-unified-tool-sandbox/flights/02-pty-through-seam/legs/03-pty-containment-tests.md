# Leg: pty-containment-tests

**Status**: completed
**Flight**: [PTY Through the Seam](../flight.md)

## Objective

Extend `tests/test_pty_sandbox.py` with the remaining `@requires_bwrap` containment
tests — write-outside-allowlist denied, denylisted-secret not writable (sibling
allowed), network deny-by-default + opt-in, and real-`$HOME` persistence — each
driven through a real bwrap-wrapped `UnixPtySession` via `session.send`, mirroring
`tests/test_builtin_tool_sandbox.py` but for the interactive PTY path.

## Context

- **Design decisions** (from `flight.md`): DD6 (verify both ways — these are the
  hermetic `@requires_bwrap` arm; the live behavior test is Leg 4), DD5 (orphan-
  survival already landed in Leg 1).
- **Depends on Legs 1-2 (landed):** `create_pty_session(cwd=…, profile=…)` wraps the
  session in bwrap when a profile is supplied on a bwrap host; `session.send(...)`
  returns the session's raw output `bytes`.
- **Mirror, don't reinvent:** `tests/test_builtin_tool_sandbox.py` already proves these
  exact properties for the one-shot shell/python tools. This leg reproduces them for
  the PTY session. Where a property leaves a **host-filesystem** artifact, assert on
  the host (robust); only the network test, which has no host artifact, reads the
  session output sentinel.
- **Architect medium issue (carried):** the denylist test must **create the
  denylisted dir explicitly** — `--ro-bind-try` silently skips absent paths, so a
  missing denylist dir would false-pass the write. Mirror
  `test_builtin_tool_sandbox.py:99-148`.

## Inputs

What exists before this leg runs:
- `tests/test_pty_sandbox.py` — created in Leg 1 with `_sleep_pids()` + the
  orphan-survival test; the module docstring already documents the bwrap constraints
  (workspace under `$HOME`, `THE_ONE_SANDBOX_DISABLED` UNSET, `--unshare-pid` host
  /proc visibility). Construct sessions with `create_pty_session(cwd=…,
  profile=SandboxProfile(...))` and read output via `(await session.send(...))`.
- `tests/test_builtin_tool_sandbox.py` — the four reference tests to mirror:
  `test_write_outside_allowlist_denied` (`:56-96`),
  `test_denylist_secret_write_denied_sibling_allowed` (`:99-148`),
  `test_network_denied_by_default_allowed_when_enabled` (`:150-241`, incl. the
  host-loopback server + isolated-netns rationale),
  `test_real_home_persistence` (`:243-283`, uses `monkeypatch.setenv("HOME", …)`).
- `SandboxProfile` (`the_one/platform/sandbox/base.py`) — `writable_paths`,
  `readonly_overlay_paths`, `network_allowed`, `home`.

## Outputs

What exists after this leg completes:
- `tests/test_pty_sandbox.py` contains four new `@requires_bwrap` tests (plus the
  Leg-1 orphan-survival test), all green under `-m requires_bwrap`.

## Acceptance Criteria
- [x] **write-outside-allowlist denied:** a PTY session with `writable_paths=[workspace]`
      runs (via `send`) a write to a path in a *sibling* dir outside the allowlist; the
      target file does **not** exist on the host afterward. The sibling dir is created
      **explicitly** on the host first (`sibling.mkdir(exist_ok=True)`) — bwrap's
      `--ro-bind / /` only mounts paths that exist, so an absent sibling would make the
      write fail for the wrong reason. (Mirror `test_builtin_tool_sandbox.py:56-96,75-76`.)
- [x] **denylist-secret not writable, sibling allowed:** create a `secret/` dir under
      the workspace **explicitly** with known content; profile has
      `writable_paths=[workspace]`, `readonly_overlay_paths=[secret_dir]`. A `send`
      that overwrites the secret leaves the host file content **unchanged**; a `send`
      that writes an allowlisted sibling file **does** create it on the host. (Mirror
      `:99-148`; the explicit dir creation is the architect-flagged requirement.)
- [x] **network deny-by-default + opt-in:** with a host loopback TCP server running,
      a session whose profile has `network_allowed=False` cannot connect (assert
      `"connected" not in out` — more robust than matching `failed`, which a stray
      `TimeoutError` could also satisfy); a session whose profile has
      `network_allowed=True` **can** connect (assert `"connected" in out`). The connect
      logic is a **single-line `python3 -c '…'`** sent in one `send` (NOT a
      heredoc-then-exec across two sends — `send` returns on the idle-mark after the
      heredoc, so the exec's output would never be seen). Run it under a
      **non-interactive `/bin/sh`** session (`create_pty_session(shell="/bin/sh", …)`)
      so no `.bashrc`/RC hook can perturb the loopback or add prompt noise. (Mirror
      `:150-241`, including the isolated-loopback rationale — the host server is on the
      host's 127.0.0.1, unreachable from the sandbox's separate netns.)
- [x] **real-`$HOME` persistence:** `monkeypatch.setenv("HOME", str(workspace))`;
      profile `home=str(workspace)`, `writable_paths=[workspace]`. A `send` writing a
      `~`-relative file results in that file existing on the host **under the
      workspace** (proving the session's HOME is the real, writable home, not the MCP
      `/tmp`). (Mirror `:243-283`.)
- [x] Every test: `monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)`;
      workspace(s) under `$HOME`; `try/finally` closes the session and `shutil.rmtree`s
      the workspace(s). Sessions are closed even on assertion failure.
- [x] `docker exec the-one pytest tests/test_pty_sandbox.py -m requires_bwrap -x
      --timeout 90` — all 5 tests green. `ruff check` + `ruff format --check` clean.

## Verification Steps
- `docker exec the-one pytest tests/test_pty_sandbox.py -m requires_bwrap -x --timeout 90`
  — 5 passed (orphan + the four new).
- `docker exec the-one ruff check tests/test_pty_sandbox.py` and
  `docker exec the-one ruff format --check tests/test_pty_sandbox.py` — clean.
- Sanity: `docker exec the-one pytest tests/test_pty_sandbox.py --collect-only` shows
  all 5 tests carry the `requires_bwrap` marker (they are deselected by the default
  suite per `pyproject.toml` addopts).

## Implementation Guidance

General PTY-driving pattern (all four tests):
```python
home_dir = Path.home()                       # real home — used ONLY for mkdir/rmtree
workspace = home_dir / ".the-one-test-…"      # disposable workspace under $HOME
workspace.mkdir(exist_ok=True)
# NOTE the profile `home=` is the SANDBOX home (usually str(workspace) for the
# HOME test, str(home_dir) otherwise) — NOT a single reused variable. Pass it
# explicitly per test; do not write `home=str(home)` ambiguously.
prof = SandboxProfile(writable_paths=[str(workspace)], network_allowed=False, home=str(home_dir))
session = create_pty_session(cwd=workspace, profile=prof)   # bind `session` BEFORE the try
await session.start()
try:
    out = (await session.send("…command…\n")).decode(errors="replace")
    # assert on HOST filesystem state (preferred) and/or `out` (network only)
finally:
    try:
        await session.close()
    except Exception:
        pass
    shutil.rmtree(workspace, ignore_errors=True)
```
- **Prefer host-filesystem assertions.** For write-denied / denylist / real-HOME,
  assert on `Path(...).exists()` / `.read_text()` on the host rather than parsing the
  PTY output (interactive output carries echoed input + prompt noise; host state is
  unambiguous). The network test is the exception — read the `out` sentinel.
- **No settle needed.** bwrap uses `--bind` (not a networked FS), so the host-FS write
  is kernel-synchronous by the time the shell goes idle and `send` returns — the
  host assertion is already consistent. Do **not** add a `time.sleep` or follow-up
  `send` for the host-FS tests (add a one-line comment saying so, to stop a future
  reader from inserting an unnecessary sleep).
- **Bind `session` before the `try`** (mirror the Leg-1 orphan test) so the `finally`
  never references an unbound name; guard `close()` with `try/except` in `finally`.

1. **write-outside-allowlist denied** — workspace + sibling under `$HOME`, both created
   **explicitly** on the host (`workspace.mkdir(exist_ok=True)`,
   `sibling.mkdir(exist_ok=True)` — bwrap's `--ro-bind / /` only mounts existing paths,
   so an absent sibling would fail the write for the wrong reason). Profile
   `writable_paths=[str(workspace)]`, `home=str(home_dir)`;
   `send(f"echo forbidden > {sibling}/should-not-exist.txt\n")`; assert the target file
   does **not** exist on the host. `rmtree` both dirs.

2. **denylist-secret not writable, sibling allowed** — workspace under `$HOME`;
   **explicitly** `secret_dir = workspace/"secret"; secret_dir.mkdir();
   (secret_dir/"key").write_text("original-content")`. Profile
   `writable_paths=[str(workspace)]`, `readonly_overlay_paths=[str(secret_dir)]`,
   `home=str(home_dir)`. `send` overwriting `secret/key` → assert host file still
   `"original-content"`. `send` writing `workspace/ok.txt` → assert it exists on host.

3. **network deny-by-default + opt-in** — stand up the host loopback server exactly as
   `test_builtin_tool_sandbox.py:160-186` (thread + `SO_REUSEADDR` + `stop_event`).
   Drive the connect with a **single-line** `python3 -c '...'` that prints `connected`
   on success and a non-"connected" sentinel on failure. **Mandatory single `send`** —
   do NOT use a heredoc-then-exec across two sends (the idle-mark returns after the
   heredoc; the exec output is lost). Use a **non-interactive `/bin/sh`** session
   (`create_pty_session(shell="/bin/sh", cwd=workspace, profile=prof)`) so no RC hook
   perturbs loopback or adds prompt noise. Pass an explicit `timeout=15.0` to `send`
   (headroom if the server thread is slow to start; the 30 s default would hang that
   long on a wedge).
   - **Deny** session: `SandboxProfile(network_allowed=False, writable_paths=[str(workspace)],
     home=str(home_dir))` → assert `"connected" not in out` (more robust than matching
     `failed`). Close.
   - **Allow** session: `SandboxProfile(network_allowed=True, …)` → assert
     `"connected" in out`. Close.
   - `finally`: `stop_event.set()`, close server sock, join thread, rmtree.

4. **real-`$HOME` persistence** — workspace under `$HOME`;
   `monkeypatch.setenv("HOME", str(workspace))`; profile `home=str(workspace)`,
   `writable_paths=[str(workspace)]`. `send("echo pty-home-canary > ~/canary.txt\n")`;
   assert `(workspace/"canary.txt")` exists on the host and contains `pty-home-canary`.
   (`~` resolves to the profile HOME inside the sandbox = the workspace.)

## Edge Cases
- **PTY output noise:** never assert exact-equality on `send` output; the shell echoes
  the command and may emit prompt bytes. Host-FS assertions sidestep this entirely; the
  network test uses substring on `"connected"` (`not in` for deny, `in` for allow) and
  a non-interactive `/bin/sh` to minimize noise.
- **Session start cost:** each test starts a real bwrap session (~up to 2 s readiness
  cap). Five tests + the network test's two sessions ≈ 6-7 starts — keep `--timeout 90`.
- **Isolated loopback (network test):** the sandbox's `127.0.0.1` is a *different* lo
  from the host's, so the host server is unreachable under deny (sentinel `failed`),
  reachable under allow (`connected`) — same rationale as the builtin test; copy its
  docstring note.
- **HOME pollution:** the real-HOME test must `monkeypatch.setenv("HOME", workspace)`
  so `~`-writes land in the disposable workspace, NOT the developer's real home.
- **No tool-layer or platform changes:** this leg is tests-only. Do not touch
  `the_one/`.

## Files Affected
- `tests/test_pty_sandbox.py` — four new `@requires_bwrap` containment tests appended.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (`-m requires_bwrap` → 5 passed)
- [x] Update flight-log.md with a leg progress entry (append)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off the leg in flight.md, do NOT land the flight
- [x] **Do NOT commit** — batched workflow: review + commit after the last leg.
      Signal `[HANDOFF:review-needed]`.
