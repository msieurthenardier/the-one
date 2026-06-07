# Leg: session-boxed

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Extend boxed mode to interactive PTY sessions: `shell_session_start` gains `host_access`,
and a boxed session gets a **persistent** scratch dir that survives across
`shell_session_send`s (install-then-use works) and is cleaned up when the session closes —
with cleanup owned by `PtySession.close()` (single locus) so every close path (explicit
close, idle reaper, shutdown drain, cancellation drain, test clear) and the
registration-failure path all clean up for free.

## Context

- **DD1**: `host_access: bool` (default false → boxed) on `shell_session_start`. A boxed
  session's scratch persists for the session lifetime (DD3), unlike one-shot's per-call
  ephemeral scratch (leg 3).
- **DD3 (cleanup, design-review)**: own scratch removal in `PtySession.close()` — NOT on the
  `_RegistryEntry`. `entry.session.close()` is invoked from **5** sites
  (`_session_registry.py` `close():140`, `_reap_once():241`, `shutdown_drain():198`,
  `_reap_loop` cancel-drain `:274`, `_clear_for_test():307`). Binding cleanup to `close()`
  covers all five. Plus: **close-on-registration-failure** — `ShellSessionStartTool.execute`
  creates+starts the session BEFORE `register()` (`sessions.py:142-149`); if `register`
  raises (or anything after `start()`), the session+scratch currently leak. Leg 4 closes the
  session on that failure.
- Current `ShellSessionStartTool.execute` (`sessions.py:105-154`): cap check → `_cwd_check`
  → `_build_tool_profile` → `create_pty_session(cwd, profile)` → `session.start()` →
  `register(...)`. `ShellSessionSendTool`/`CloseTool`/`ListTool` don't build profiles.
- `create_pty_session(cwd, shell, profile)` (`pty.py:193`) → `UnixPtySession`; teardown in
  `_close_blocking` (`pty.py:516`, idempotent via `self._closed`, runs in an executor).
- Leg 2 helpers: `_build_boxed_profile(scratch)`, `_boxed_cwd_check(cwd, scratch)`.

## Inputs

- Legs 1-3 landed (backend isolation, profile/cwd helpers, one-shot boxed).
- `_session_registry` (`tools/_session_registry.py`) with reaper + shutdown drain.

## Outputs

- `cleanup_dir: Path | None` param on `create_pty_session` + `UnixPtySession`; `close()`
  rmtrees it (single-locus cleanup).
- `host_access` on `shell_session_start` (schema + execute); boxed → persistent scratch +
  boxed profile + `cleanup_dir`.
- Close-on-registration-failure in the start tool.
- `@requires_bwrap` tests for boxed-session persistence, containment, and cleanup.

## Acceptance Criteria

- [x] `create_pty_session(...)` and `UnixPtySession.__init__` accept `cleanup_dir: Path | None
      = None`. `UnixPtySession._close_blocking` (or the async `close()`) removes
      `cleanup_dir` via `shutil.rmtree(cleanup_dir, ignore_errors=True)` **at the end of
      teardown**, idempotently (the existing `self._closed` guard ensures it runs once). When
      `cleanup_dir` is None (host sessions), behavior is unchanged.
- [x] `shell_session_start` accepts `host_access: bool = False` (schema + execute).
      **Boxed (default)**: create a **persistent** scratch dir under
      `settings.data_dir/"boxes"/<unique>` (`unique` = e.g. `f"{agent_name}-{sid}-{uuid4().hex}"`),
      build the profile via `_build_boxed_profile(scratch)`, validate cwd via
      `_boxed_cwd_check(cwd, scratch)`, and `create_pty_session(cwd=canonical_cwd,
      profile=profile, cleanup_dir=scratch)`. **Escalated (`host_access=true`)**: existing
      host path unchanged (`_cwd_check` + `_build_tool_profile`, `cleanup_dir=None`).
- [x] **Scratch persists across sends**: a boxed session that writes a file in send 1 can
      read it in send 2 (the scratch lives for the session, not per-send).
- [x] **Cleanup on close**: after `shell_session_close`, the boxed session's scratch dir is
      gone from the host fs. (Covers the reaper/drain paths too via the single `close()`
      locus — at least assert the explicit-close path; reaper path optional if cheap.)
- [x] **Close-on-registration-failure**: if `register()` raises after `session.start()`, the
      start tool `await session.close()` (removing the scratch) before returning the error —
      no process or scratch leak. (Test by forcing register to raise, e.g. cap exceeded is
      checked before start so use a monkeypatched `register` or the `_shutting_down` path.)
- [x] `@requires_bwrap`: a boxed session cannot read a planted host home-file; can write
      within its scratch; `host_access=true` session reads the host file (host mode intact).
- [x] Full default suite + ruff green; existing PTY `@requires_bwrap` tests
      (`test_pty_sandbox.py`) unaffected.

## Verification Steps

- `docker exec the-one python -m pytest -m requires_bwrap --timeout 120 -q` — green incl. new boxed-session tests.
- `docker exec the-one python -m pytest tests/test_pty_sandbox.py -m requires_bwrap --timeout 120 -q` — host-mode PTY tests pass.
- `docker exec the-one python -m pytest tests/test_sessions.py --timeout 60 -q` (or the session unit-test home) — registration-failure cleanup + host_access plumbing.
- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — no regressions.
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/tools/sessions.py the_one/platform/pty.py`.

## Implementation Guidance

1. **`cleanup_dir` on the PTY primitive**: add `cleanup_dir: Path | None = None` to
   `create_pty_session` (`pty.py:193`) and `UnixPtySession.__init__`; store `self._cleanup_dir`.
   In `_close_blocking` (`pty.py:516`), place the rmtree at the **very bottom**, AFTER
   `self._pid = None` / `self._master_fd = None` (so it runs on every path — bwrap fast-kill,
   passthrough SIGTERM, AND sessions with `pid=None`/`master_fd=None` that never fully
   started; design-review confirmed `_close_blocking` has no early return after
   `self._closed = True`):
   ```python
   if self._cleanup_dir is not None:
       shutil.rmtree(self._cleanup_dir, ignore_errors=True)
   ```
   The `self._closed` guard lives in the async `close()` (`pty.py:375`) BEFORE
   `run_in_executor(_close_blocking)`, so `_close_blocking` is never double-dispatched →
   rmtree runs exactly once. Add `import shutil` to `pty.py` (absent today). (Cleanup runs in
   the executor thread — fine; rmtree is blocking I/O.)
2. **`shell_session_start` boxed branch** (`sessions.py:105-154`): add `host_access: bool =
   False`. After the cap check:
   ```python
   if host_access:
       canonical_cwd = _cwd_check(cwd or Path.home(), fs_cfg)
       profile = _build_tool_profile(fs_cfg, exec_cfg)
       cleanup_dir = None
   else:
       from the_one.config import settings  # function-local (leg-3 precedent)
       scratch = settings.data_dir / "boxes" / f"{agent_name}-{sid}-{uuid4().hex}"
       scratch.mkdir(parents=True)
       canonical_cwd = _boxed_cwd_check(cwd, scratch)
       profile = _build_boxed_profile(scratch)
       cleanup_dir = scratch
   session = create_pty_session(cwd=canonical_cwd, profile=profile, cleanup_dir=cleanup_dir)
   ```
   Note: `sid` is currently allocated AFTER `register` in the existing code
   (`new_session_id()` at `:143`) — move `sid = _session_registry.new_session_id()` BEFORE
   the scratch naming so the scratch can include it (or just use `uuid4().hex` without the
   sid). Either is fine; keep it unique.
3. **Close-on-registration-failure**: add an **inner** `try/except` around just
   `session.start()` + `register(...)`, **nested inside the existing outer `try`** (which
   keeps the `ConstraintError` + `Exception` handlers at `sessions.py:151-154`). On failure
   after a successful `start()`: `await session.close()` (removes the scratch via
   `cleanup_dir`) then re-raise — the outer `except Exception` formats `[error] …`. Do NOT
   wrap the whole body in a new outer try (that would shadow the `ConstraintError` handler).
   `session.close()` is safe on a started-but-unregistered session (operates on the session's
   own state, no registry dependency — design-review confirmed).
4. **No PTY-HOME change needed (design-review).** `_build_boxed_profile` sets
   `home=str(scratch)` and bubblewrap overrides `$HOME` from `profile.home`
   (`bubblewrap.py:131`) — so a boxed bwrap session already has `$HOME=scratch` with no
   PTY-level change. (Passthrough == host mode, so its real HOME is correct there too.) Add a
   one-line comment in `_build_boxed_profile` noting `home=str(scratch)` is what sets `$HOME`
   in the box. Do NOT add an env mutation in `UnixPtySession.start` (the env is passed
   positionally into `prepare_spawn` — the stated mutation point doesn't exist, and it's a
   no-op for all live paths).
5. **Do NOT** generalize leg-3's `_ephemeral_box_scratch` (per-call) to sessions — sessions
   need a persistent dir owned by the session's `close()`, not a per-call CM.

## Edge Cases

- **`mkdir(parents=True)`**: the `boxes` parent may already exist (leg 3 creates it too) —
  use `parents=True` and let the unique leaf `mkdir()` (no `exist_ok` on the leaf so a UUID
  collision is loud, which won't happen).
- **Reaper/drain cleanup**: because cleanup is in `close()`, the idle reaper (`:241`) and
  shutdown drain (`:198`) remove the scratch for free. A reaper-path test is nice-to-have
  (set a tiny TTL) but the explicit-close test is the required one.
- **Orphan-on-crash**: a SIGKILL/OOM mid-session leaves a `boxes/<…>` orphan (close never
  runs) — same hazard as leg 3; **leg 7's startup-prune** sweeps both one-shot and session
  orphans. Don't build the prune here.
- **Registration-failure path is pre-existing**: today a register failure leaks the process
  too; leg 4's close-on-failure fixes both the process and the scratch leak. Keep the fix
  minimal and well-commented.

## Files Affected

- `the_one/platform/pty.py` — `cleanup_dir` param + `close()` rmtree.
- `the_one/tools/sessions.py` — `host_access` + boxed scratch + close-on-registration-failure.
- `tests/test_pty_sandbox.py` (or `tests/test_box_isolation.py`) + `tests/test_sessions.py`
  — boxed-session persistence/containment/cleanup + registration-failure cleanup.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to `landed`,
> signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified (persistence + cleanup on close + registration-failure)
- [x] Host-mode PTY tests unaffected; full suite + ruff green
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
