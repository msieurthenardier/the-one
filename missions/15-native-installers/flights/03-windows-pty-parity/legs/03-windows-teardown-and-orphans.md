# Leg: windows-teardown-and-orphans

**Status**: completed
**Flight**: [Windows PTY Parity (ConPTY)](../flight.md)

## Objective

Guarantee that closing a `WindowsPtySession` — or the parent process dying —
reaps the whole cmd.exe process tree (including backgrounded grandchildren), by
assigning the spawned process to a Win32 **Job Object** with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and verify it on the `windows-2022` lane.

## Context

- **DD-OQ resolved by requirement, not guesswork.** DD4 requires "no orphan
  after `close()` AND after parent-death." `proc.close(force=True)` (Leg 2) only
  runs when `close()` is explicitly called and only reliably kills the *direct*
  child — a backgrounded grandchild (`start /b …`) detaches and survives, and a
  parent *crash* never calls `close()` at all. **Only a Job Object with
  `KILL_ON_JOB_CLOSE` satisfies both:** the OS auto-closes the job handle when
  the holding (Python) process dies, firing the kill on the whole tree. This is
  the Windows analogue of bwrap's PID-namespace `--die-with-parent` reap that
  the Unix backend relies on (`test_pty_sandbox.py::test_pty_close_reaps_
  namespace_grandchild` / `test_pty_app_crash_reaps_grandchild`).
- **Empirical edges remain (CI-verified, F1 "verify the premise" lesson):**
  whether pywinpty/ConPTY already places the process in a job (so our
  `AssignProcessToJobObject` must handle the nested-job case), and whether the
  close-reap and parent-death-reap both fire on `windows-2022`. The CI tests are
  the authoritative answer; the operator's Windows box is a supplementary check
  (offered for this leg) but not required to land.
- **Windows = passthrough/unsandboxed (DD9).** The Job Object is a *lifecycle*
  reaper, NOT a security boundary — it does not contain the child, only
  guarantees teardown. SECURITY-MODEL.md already documents Windows as unsandboxed;
  this leg adds only the teardown guarantee, no containment claim.
- **No fork on Windows** → the `pty_unix` "parent-loads/child-execs" fork-safety
  convention does not apply; ctypes `kernel32` calls are made normally in
  `pty_windows`.

## Inputs

- `the_one/platform/pty_windows.py` — `WindowsPtySession` from Leg 2; `start()`
  spawns `winpty.PtyProcess` and has `proc.pid`; `close()` calls
  `proc.close(force=True)`. **VERIFIED WORKING on windows-2022** (Leg 2 CI:
  test_pty_windows 7/7).
- `tests/test_pty_windows.py` — Leg 2's nt-gated round-trip tests.
- `tests/test_pty_sandbox.py` — Unix grandchild/app-crash reap tests (the
  behavioral pattern to mirror; they are `@requires_bwrap` and stay Unix-only).

## Outputs

- `the_one/platform/pty_windows.py` — a Job Object created in `start()` with
  `KILL_ON_JOB_CLOSE`, the spawned process assigned to it, the job handle held
  on the session and `CloseHandle`'d in `close()` (after `proc.close`). The
  ctypes `kernel32` plumbing (struct + calls) lives here (or a small
  `the_one/platform/_winjob.py` helper if cleaner).
- `tests/test_pty_windows.py` (or a new `tests/test_pty_windows_orphans.py`,
  nt-gated) — close-reaps-grandchild and (best-effort) parent-death-reaps-
  grandchild tests.
- SECURITY-MODEL.md / docs note: Windows session teardown reaps the tree via a
  Job Object (lifecycle, not containment). *(Full docs are Leg 5; a one-line
  note here if the implementer touches the file is fine — otherwise defer.)*

## Acceptance Criteria

- [ ] `WindowsPtySession.start()` creates a Job Object with
      `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assigns the spawned process to it
      (via `OpenProcess(proc.pid)` + `AssignProcessToJobObject`), and stores the
      job handle on the session. Assignment is done immediately after spawn so
      grandchildren spawned by later `send()`s inherit the job.
- [ ] `WindowsPtySession.close()` closes the job handle (after `proc.close`),
      firing the kill on any still-running tree members; remains idempotent.
- [ ] The nested-job case is handled: if `AssignProcessToJobObject` fails
      because the process is already in a job (pywinpty/ConPTY may pre-assign),
      the code detects it and either nests (Win8+ default) or logs+degrades
      gracefully (documented) rather than crashing `start()`.
- [ ] `tests/test_pty_windows*.py` (nt-gated) proves a backgrounded grandchild
      (`start /b` a detectable process, e.g. `timeout /t 30` or a python sleep)
      is **gone after `close()`** — mirroring the Unix reap test's shape.
- [ ] Best-effort: a parent-death reap test (a subprocess creates a session +
      grandchild, then is hard-killed; the grandchild is gone afterward).
      If the in-CI mechanism proves unreliable, mark `xfail`/`skip` with a
      written reason and record it for the operator's hands-on check — do NOT
      silently drop it.
- [ ] Linux suite / bwrap / browser remain green; lint clean. The new ctypes
      code is nt-gated and never imported on Linux (it lives in `pty_windows`,
      imported only via the `nt` dispatch branch).

## Verification Steps

POSIX-side (implementing agent, locally — cannot run Windows/ctypes-kernel32):
- `.venv/bin/python -c "import the_one.platform.pty"` — no error (pty_windows not
  imported on Linux; the kernel32 ctypes never load here).
- Full default suite `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green,
  no regression (the new code is nt-gated).
- `ruff check`/`format --check` on the changed files — clean (use a per-file
  noqa if ruff flags `ctypes.windll`, which only exists on Windows).

Windows-side (Flight Director, post-push, `windows-2022` lane):
- The orphan-reap test(s) pass: grandchild gone after `close()`.
- test_pty_windows round-trip still 7/7 (no teardown regression).
- Capture the orphan-reap result + the nested-job finding into the flight log
  (this is the DD-OQ empirical answer).

## Implementation Guidance

1. **Job Object plumbing** (ctypes `kernel32`; lives in `pty_windows.py`, or a
   small `the_one/platform/_winjob.py` helper if the struct defs make the file
   unwieldy — implementer's call by line count). **Use `ctypes.wintypes`** for
   `DWORD`/`HANDLE`/`BOOL` (import inside `pty_windows`, which is nt-only) — it
   self-documents and gets the widths right. **Spell the structs out EXACTLY —
   the field types are the #1 blind-port trap** (design review): `DWORD` is
   always 4 bytes (`wintypes.DWORD` / `c_uint32`, **NOT `c_ulong`** — `c_ulong`
   is 8 bytes on 64-bit Linux but 4 on Windows, so a Linux size-check lies);
   `LARGE_INTEGER` → `c_int64`; `SIZE_T`/`ULONG_PTR` (the working-set fields,
   `Affinity`, and all the memory-limit fields) → `c_size_t` (pointer-width).
   ctypes inserts the correct x64 padding automatically (the DWORD `LimitFlags`
   before the first `SIZE_T` gets 4 bytes of padding):

   ```python
   import ctypes
   from ctypes import wintypes

   ULONG_PTR = ctypes.c_size_t

   class IO_COUNTERS(ctypes.Structure):
       _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                   ("WriteOperationCount", ctypes.c_uint64),
                   ("OtherOperationCount", ctypes.c_uint64),
                   ("ReadTransferCount", ctypes.c_uint64),
                   ("WriteTransferCount", ctypes.c_uint64),
                   ("OtherTransferCount", ctypes.c_uint64)]

   class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
       _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),  # LARGE_INTEGER
                   ("PerJobUserTimeLimit", ctypes.c_int64),       # LARGE_INTEGER
                   ("LimitFlags", wintypes.DWORD),
                   ("MinimumWorkingSetSize", ctypes.c_size_t),    # SIZE_T
                   ("MaximumWorkingSetSize", ctypes.c_size_t),
                   ("ActiveProcessLimit", wintypes.DWORD),
                   ("Affinity", ULONG_PTR),                       # ULONG_PTR, NOT DWORD
                   ("PriorityClass", wintypes.DWORD),
                   ("SchedulingClass", wintypes.DWORD)]

   class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
       _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                   ("IoInfo", IO_COUNTERS),
                   ("ProcessMemoryLimit", ctypes.c_size_t),
                   ("JobMemoryLimit", ctypes.c_size_t),
                   ("PeakProcessMemoryUsed", ctypes.c_size_t),
                   ("PeakJobMemoryUsed", ctypes.c_size_t)]
   ```

   - **HANDLE truncation trap (design review):** set `argtypes`/`restype` on
     every call, and `HANDLE` MUST be `wintypes.HANDLE` (== `c_void_p`,
     pointer-width) — `c_int` silently truncates 64-bit handles, causing a
     non-obvious `ERROR_INVALID_HANDLE` at `AssignProcessToJobObject`. e.g.
     `CreateJobObjectW.restype = wintypes.HANDLE`;
     `AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]`;
     `OpenProcess.restype = wintypes.HANDLE`;
     `SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
     ctypes.c_void_p, wintypes.DWORD]`.
   - `CreateJobObjectW(None, None)` → job handle (0/NULL → `GetLastError`).
   - Fill `JOBOBJECT_EXTENDED_LIMIT_INFORMATION`, set
     `BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
     (0x00002000)`, then `SetInformationJobObject(job,
     JobObjectExtendedLimitInformation==9, byref(info), sizeof(info))`.
   - `OpenProcess(PROCESS_SET_QUOTA(0x0100)|PROCESS_TERMINATE(0x0001), False,
     proc.pid)` → process handle. (Add `PROCESS_SET_INFORMATION(0x0200)` if a CI
     iteration shows access-denied — but the two above are the documented
     minimum for `AssignProcessToJobObject`.)
   - `AssignProcessToJobObject(job, hproc)`. On Win8+/windows-2022 this
     **succeeds even if the process is already in a job** (nested jobs are
     supported). So `ERROR_ACCESS_DENIED` here is a **genuine permissions /
     protected-process failure — log it and raise**, NOT a "silently degrade,
     already-jobbed" case (that path essentially never triggers on
     windows-2022). Close `hproc` after assignment (keep only the job handle).
   - Optional flight-log data: `IsProcessInJob(proc.pid-handle, NULL, &out)`
     after spawn to learn whether pywinpty/ConPTY pre-jobs the process.
   - On any hard failure in `start()`, raise a clear `RuntimeError` — fail loudly
     (a ConPTY-works-but-JobObject-fails environment failing all PTY sessions is
     the intended safety trade-off; better than silently leaking trees). Use
     `ctypes.windll.kernel32`.

2. **`start()`** — after `PtyProcess.spawn(...)` and storing `self._proc`, create
   the job and assign `self._proc.pid` BEFORE the banner drain (so anything
   cmd.exe spawns is already in the job). Store `self._job = job_handle`.

3. **`close()`** — in the idempotent `_close_blocking`: call
   `proc.close(force=True)` (existing, already in a `try/except IOError`) then
   **place `CloseHandle(self._job)` AFTER that try/except block, in its own
   `try/finally` that nulls `self._job` unconditionally** (design review — so a
   non-`IOError` from `proc.close` can't skip the job teardown and break the
   idempotent-teardown contract). `CloseHandle` fires KILL_ON_JOB_CLOSE on any
   survivors. Then remove `cleanup_dir` (unchanged order: proc closed → job
   closed → rmtree). Guard against double-close (the `_closed` flag + null
   `_job`).

4. **Parent-death is automatic** — because the Python process holds the only
   job handle, when it dies the OS closes the handle → KILL_ON_JOB_CLOSE reaps
   the tree. No explicit signal handler needed (this is the whole point of the
   Job Object over `proc.close`).

5. **Tests** (nt-gated, `skipif(os.name != "nt")`):
   - close-reap: start session → `send` a command that backgrounds a grandchild
     which **writes its own PID to a temp file** (robust in shared CI — design
     review; `tasklist` before/after diff false-passes when another
     `python.exe`/`timeout.exe` runs concurrently). e.g. `start /b "" python -c
     "import os,time;open(r'<tmpfile>','w').write(str(os.getpid()));time.sleep(30)"`.
     Read the PID from the file → `close()` → assert gone via
     `tasklist /FI "PID eq <pid>"` (or ctypes `OpenProcess`/`WaitForSingleObject`).
   - parent-death-reap (best-effort): a `subprocess` child script creates a
     session + grandchild and prints the grandchild PID, then the test
     `TerminateProcess`es the child script → assert the grandchild is gone.
     If flaky/unworkable in CI, `xfail(reason=...)` + flag for operator
     hands-on (DD-OQ secondary check).
   - Pin passthrough via `monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED","1")`
     (matches the Leg-2 tests; on Windows passthrough is selected anyway).

6. **Do NOT** claim containment/security from the Job Object — it's lifecycle
   only (DD9; Windows stays unsandboxed).

## Notes for the Flight Director (post-implementation)

- Push to verify on `windows-2022`. The orphan-reap result IS the DD-OQ answer —
  record it (and the nested-job finding) in the flight log. Budget 1-2 CI
  iterations (the ctypes Job Object is written blind; the nested-job case is the
  likeliest first-iteration surprise). The operator's Windows box can
  cross-check the parent-death reap if the CI mechanism proves unreliable.
