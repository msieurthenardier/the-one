# Leg: 01-platform-package-scaffolding

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Create the `the_one/platform/` package with four submodules (`paths`, `shell`, `interpreter`, `tempdirs`) that abstract platform-divergent concerns, alongside direct unit tests — without touching any existing tool yet (copy-don't-cut).

## Context

This leg lays the architectural seam Flights 3-5 depend on. Per Decision 4 in `flight.md`, the package layout is:

- `paths.py` — path canonicalization, expanduser, resolve, symlink-safe-resolve helpers
- `shell.py` — shell selection (POSIX `/bin/sh`, Windows `cmd.exe`, `SHELL` env var preference); subprocess invocation helper
- `interpreter.py` — Python interpreter resolution (`python3` Unix vs `python` / `py` Windows)
- `tempdirs.py` — temp-dir + user-dir helpers with cross-platform user-config-dir resolution
- `__init__.py` — public API surface

**Extraction pattern: copy-don't-cut** — helpers are written *alongside* the existing platform-coupled code in `the_one/tools/{filesystem,shell,python_exec}.py`. **No tool changes in L1.** Tools migrate to call the new helpers in L4-L6. This keeps L1 a pure additive change ("tests are unchanged because tools are unchanged").

**F2 verification target**: Linux/WSL only. Each helper documents a cross-platform *contract*; the implementation may use OS-specific code paths via `sys.platform` or `os.name` checks, but no Linux-only assumption may leak into the public contract.

### Platform-coupled patterns to abstract (from existing tool code)

- `Path(path).expanduser().resolve()` — used 3× in `the_one/tools/filesystem.py:27,52,74` (read/write/list_dir)
- `asyncio.create_subprocess_shell(command, ...)` in `the_one/tools/shell.py:34-38` — implicitly selects `/bin/sh` on POSIX, `cmd.exe` on Windows
- `asyncio.create_subprocess_exec("python3", "-c", code, ...)` in `the_one/tools/python_exec.py:27-31` — hardcoded `"python3"` is the most blatant Linux-only assumption

## Inputs

What exists before this leg runs:

- Branch `flight/02-cross-platform-foundations` checked out (created by orchestrator)
- F1 landed: `the_one/tools/{base,builtins,filesystem,shell,python_exec,web,provider}.py` exist
- Schema is at v7 (no DB changes in L1)
- No `the_one/platform/` directory yet

## Outputs

What exists after this leg completes:

- `the_one/platform/__init__.py` (re-exports public API)
- `the_one/platform/paths.py`
- `the_one/platform/shell.py`
- `the_one/platform/interpreter.py`
- `the_one/platform/tempdirs.py`
- `tests/test_platform_paths.py`
- `tests/test_platform_shell.py`
- `tests/test_platform_interpreter.py`
- `tests/test_platform_tempdirs.py`
- All seven existing tools unchanged (verified by `git diff`)

## Acceptance Criteria

- [ ] `the_one/platform/` package exists with `__init__.py`, `paths.py`, `shell.py`, `interpreter.py`, `tempdirs.py`
- [ ] `paths.py` exposes `canonicalize(path: str | Path) -> Path` (calls `expanduser().resolve()`, accepts string or Path); `safe_resolve(path: str | Path) -> Path` (resolves symlinks, equivalent to `canonicalize` on this platform but documented to enforce symlink resolution); `is_within(path: str | Path, root: str | Path) -> bool` (canonicalizes both inputs internally for safety, returns True if `path` is `root` or a descendant after resolution — prepares ground for F3 path-scope checks). Accepting `str | Path` for `is_within` and canonicalizing internally is a deliberate choice so F3's path-scope check can't be bypassed by an un-resolved input.
- [ ] `shell.py` exposes `select_shell() -> tuple[str, list[str]]` (returns shell executable + args prefix appropriate to the platform — e.g., `("/bin/sh", ["-c"])` on POSIX, `("cmd.exe", ["/c"])` on Windows; honors `SHELL` env var on POSIX when set); `run_shell(command: str, *, timeout: float, env: dict[str, str] | None = None) -> tuple[bytes, bytes, int]` async helper that wraps `asyncio.create_subprocess_*` and returns `(stdout, stderr, returncode)` as raw bytes (decoding with `errors="replace"` is the caller's responsibility — preserves today's `ShellTool` decode policy). On `asyncio.TimeoutError`, `run_shell` kills the subprocess before re-raising so callers cannot leak zombies. **L5 will adopt this helper; L1 just defines and tests it directly.**
- [ ] `interpreter.py` exposes `resolve_python() -> str` (returns the Python interpreter path appropriate to the host: `sys.executable` is a deterministic choice and is the chosen contract — see Implementation Guidance below); `run_python(code: str, *, timeout: float, env: dict[str, str] | None = None) -> tuple[bytes, bytes, int]` async helper analogous to `run_shell` — returns raw bytes; kills the subprocess on timeout before re-raising `asyncio.TimeoutError`
- [ ] `tempdirs.py` exposes `temp_dir() -> Path` (wraps `tempfile.gettempdir()`); `user_home() -> Path` (wraps `Path.home()`); `user_config_dir(app: str) -> Path` (cross-platform: `~/.{app}` on POSIX, `%APPDATA%\{app}` on Windows; uses `os.environ.get("APPDATA", str(Path.home()))` fallback)
- [ ] `the_one/platform/__init__.py` re-exports the public surface so callers import via `from the_one.platform import canonicalize, select_shell, ...`
- [ ] Each module has a module-level docstring documenting its cross-platform contract
- [ ] No tool files (`the_one/tools/*.py`) are modified — verified by `git diff the_one/tools/`
- [ ] Direct unit tests exist for every public helper:
  - `paths.py` — `~`-expansion, relative→absolute resolution; `is_within` true/false cases including `path == root`, sibling paths, and string-input paths (verifying internal canonicalization)
  - `shell.py` — `select_shell()` returns a 2-tuple `(str, list[str])`; on POSIX with `SHELL` set/unset/empty all behave correctly; `run_shell()` happy path returns expected stdout/exit-code; `run_shell()` non-zero exit propagates returncode; `run_shell()` timeout raises `asyncio.TimeoutError` and returns promptly (wall-clock < 1s for a `timeout=0.1` against `sleep 5`)
  - `interpreter.py` — `resolve_python()` returns a non-empty string; `run_python()` happy path returns expected stdout/exit-code; non-zero exit propagates returncode
  - `tempdirs.py` — `temp_dir()`, `user_home()` return existing `Path`s; `user_config_dir("the-one")` on POSIX returns `Path.home() / ".the-one"`
- [ ] All four `tests/test_platform_*.py` files pass under `pytest`
- [ ] Pre-existing test suite passes unchanged (no regressions): `make test-unit` returns the same pass/fail set as on `main` modulo the new platform tests

## Verification Steps

**Test execution context**: This project's unit suite runs *inside the `the-one` Docker container* via `make test-unit` (which delegates to `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -v --tb=short`). Run `make rebuild` first so the new files are copied into the image.

```bash
# Package layout (host)
ls the_one/platform/
# Expected: __init__.py paths.py shell.py interpreter.py tempdirs.py

# No tool changes (host)
git diff -- the_one/tools/
# Expected: empty

# Build image with new files, then run new platform tests in container
make rebuild
docker exec the-one pytest tests/test_platform_paths.py tests/test_platform_shell.py \
       tests/test_platform_interpreter.py tests/test_platform_tempdirs.py -v

# Full unit suite still green (modulo pre-existing CSS-token red, predates F1)
make test-unit

# Public API importable (in container, from project root)
docker exec the-one python -c "from the_one.platform import canonicalize, select_shell, resolve_python, temp_dir; print('OK')"
```

## Implementation Guidance

1. **Create `the_one/platform/__init__.py`**
   - Re-export the helpers listed below from each submodule.
   - Module docstring: "Platform abstraction layer. Each helper is callable on Linux/WSL today; Windows and macOS support is a future-mission concern but the contract is cross-platform from day one."

2. **Implement `the_one/platform/paths.py`**
   - `canonicalize(path)` accepts `str | Path`, returns `Path(path).expanduser().resolve()`. This is byte-for-byte equivalent to today's tool code; the helper exists so L4 can replace inline `Path(p).expanduser().resolve()` calls with `canonicalize(p)` and so future Windows-specific quirks (UNC paths, drive-letter casing) get a single place to land.
   - `safe_resolve(path)` is the same as `canonicalize` today but documents the contract "fully resolves symlinks so callers can use the result for security checks." When F3 adds symlink-escape detection, it will compare `safe_resolve(target)` against the path scope. Forward-reference: F3 may upgrade `is_within` to return a richer result (e.g., `WITHIN | OUTSIDE | SYMLINK_ESCAPE`); for now a bool is sufficient.
   - `is_within(path, root)` — accepts `str | Path` for both args, canonicalizes both internally for safety, then:
     ```python
     try:
         canonical_path.relative_to(canonical_root)
         return True
     except ValueError:
         return False
     ```
     Document the internal canonicalization in the docstring. Tests cover `is_within(p, p)` returns True, `is_within("/etc/passwd", "/home/user")` returns False, and a string-input case (e.g., `is_within("~/foo", "~")` returns True after canonicalization).

3. **Implement `the_one/platform/shell.py`**
   - `select_shell()`: on POSIX (`os.name == "posix"`), prefer `os.environ.get("SHELL") or "/bin/sh"` (handles both unset and empty-string `SHELL`); return `(shell, ["-c"])`. On Windows (`os.name == "nt"`), return `("cmd.exe", ["/c"])`. Use `os.name` (not `sys.platform`) — `os.name` is "posix" on Linux/macOS/WSL and "nt" on Windows.
   - `run_shell(command, *, timeout, env=None)`: async. Calls `asyncio.create_subprocess_shell` (preserving today's `shell.py` behavior — the OS picks the shell). Pattern:
     ```python
     proc = await asyncio.create_subprocess_shell(
         command,
         stdout=asyncio.subprocess.PIPE,
         stderr=asyncio.subprocess.PIPE,
         **({"env": env} if env is not None else {}),
     )
     try:
         stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
     except asyncio.TimeoutError:
         proc.kill()
         # Re-drain pipes and reap the process. await proc.wait() can hang here
         # because the cancelled communicate() left StreamReaders attached to the
         # pipes; await proc.communicate() drains and reaps in one call.
         await proc.communicate()
         raise
     return stdout, stderr, proc.returncode
     ```
     Returns `(stdout, stderr, returncode)` as raw bytes — caller decides decode policy.
   - `select_shell()` is exposed for future use (F4) and tested directly here, but `run_shell()` does NOT call it today (it uses `create_subprocess_shell` which delegates shell selection to the OS — note this is asyncio's `/bin/sh` choice, not necessarily `$SHELL`). Document the divergence in the module docstring: "`select_shell()` reports the shell *the agent or operator would prefer*; `run_shell()` lets the OS pick (asyncio defaults). F4 may unify these by passing the selected shell explicitly to `create_subprocess_exec`. For F2's regression-only refactor, the divergence preserves today's `ShellTool` semantics byte-for-byte."
   - **`env=None` pass-through**: when `env is None`, do not pass `env=` to asyncio (subprocess inherits parent env — today's behavior). Use the conditional `**({"env": env} if env is not None else {})` pattern shown above to avoid passing `env=None` explicitly. This preserves the L5 byte-for-byte migration property.

4. **Implement `the_one/platform/interpreter.py`**
   - `resolve_python()`: returns `sys.executable`. Rationale: deterministic; matches the interpreter the agent itself runs under; works on Windows (`python.exe`), macOS, Linux. The current `python_exec.py` hardcodes `"python3"`, which fails on Windows where the executable is `python.exe`. **Do not** use `shutil.which("python3")` — that depends on PATH order and gives wrong answers in venvs. Document the choice in the module docstring. Forward-reference: if a later flight introduces a project-bound venv distinct from the agent's interpreter, `resolve_python()` is the single site to upgrade — note this explicitly in the docstring so future maintainers find it.
   - `run_python(code, *, timeout, env=None)`: async. Same shape as `run_shell` but uses `asyncio.create_subprocess_exec(resolve_python(), "-c", code, ...)` with stdout/stderr piped. Kills + reaps on timeout. Same `env=None` pass-through pattern. Returns raw bytes.

5. **Implement `the_one/platform/tempdirs.py`**
   - `temp_dir()`: returns `Path(tempfile.gettempdir())`.
   - `user_home()`: returns `Path.home()`.
   - `user_config_dir(app)`: on POSIX, returns `Path.home() / f".{app}"`. On Windows, returns `Path(os.environ.get("APPDATA") or str(Path.home())) / app` (handle both unset and empty-string `APPDATA`). Returns the path **without** creating it (match `tempfile`/`Path.home` non-creating semantics). Document: "caller creates the directory if needed."
   - **Note**: `tempdirs.py` is *forward-looking* — no current `the_one/tools/*.py` calls `tempfile.gettempdir()` or `Path.home()`. F3-F5 will consume it (e.g., default path-scope allowlist may resolve via `user_home()`). Building it now keeps the platform package complete and avoids a follow-up scaffold leg.

6. **Write tests** under `tests/`:
   - `test_platform_paths.py`:
     - `canonicalize` expands `~` and resolves relative paths
     - `is_within` returns True for `is_within(p, p)`, True for a descendant, False for sibling/unrelated paths
     - `is_within` accepts string inputs and canonicalizes them (e.g., `is_within("~/foo", "~")` is True)
     - `safe_resolve` returns an absolute path
   - `test_platform_shell.py`:
     - `select_shell()` returns a 2-tuple `(str, list[str])`
     - On POSIX with `SHELL` patched to `/bin/bash`, returns `("/bin/bash", ["-c"])`
     - On POSIX with `SHELL` removed from `os.environ` (use `monkeypatch.delenv("SHELL", raising=False)`), returns `("/bin/sh", ["-c"])`
    - On POSIX with `SHELL=""` (use `monkeypatch.setenv("SHELL", "")`), returns `("/bin/sh", ["-c"])` — verifies the `or "/bin/sh"` fallback handles empty string
     - `run_shell("echo hi", timeout=5)`: `stdout.strip() == b"hi"`, `stderr == b""`, `returncode == 0` (tolerates `\n` vs `\r\n`)
     - `run_shell("exit 7", timeout=5)` returns returncode `7`
     - `run_shell("sleep 5", timeout=0.1)` raises `asyncio.TimeoutError` and the call returns within 1s wall-clock (use `time.monotonic()` before/after)
   - `test_platform_interpreter.py`:
     - `resolve_python()` returns a non-empty string
     - `run_python("print(2+2)", timeout=5)`: `stdout.strip() == b"4"`, `stderr == b""`, `returncode == 0`
     - `run_python("import sys; sys.exit(3)", timeout=5)` returns returncode `3`
   - `test_platform_tempdirs.py`:
     - `temp_dir()` returns a `Path` that exists
     - `user_home()` returns a `Path` that exists
     - On POSIX: `user_config_dir("the-one") == Path.home() / ".the-one"`
     - Path is NOT created by the call (assert `not result.exists()` only if guaranteed unused — otherwise just assert the path shape)

7. **Run the suite**: `make test-unit`. Expect green modulo pre-existing CSS-token red. If any pre-existing red appears different from `main`, investigate before completing the leg.

## Edge Cases

- **`canonicalize` of a non-existent path**: `Path.resolve()` succeeds even if the target doesn't exist (since Python 3.6 with `strict=False` default). Document this; F3 will add explicit existence checks where needed.
- **`is_within` with a non-canonical input**: callers must canonicalize before comparison. If `path` and `root` aren't both resolved, symlinks may produce false positives. Document explicitly; tests use `canonicalize()` on both args.
- **`SHELL` env var not set on POSIX**: fall back to `/bin/sh`. Test by patching `os.environ` to remove `SHELL`.
- **`run_shell` / `run_python` timeout**: helper kills + reaps the subprocess before re-raising `asyncio.TimeoutError`. Callers cannot leak zombies even if they fail to handle the exception. Today's `ShellTool.execute` kills then returns an error string — L5 migration replaces that with `try/except asyncio.TimeoutError` around the helper call, byte-for-byte equivalent.
- **`env=None` semantics**: when `env is None`, the helper does NOT pass `env=` to asyncio (subprocess inherits parent env — today's behavior). When a dict is supplied, asyncio uses it exclusively. F4 will tighten this to the hardcoded allowlist via the platform-layer helpers; for L1, `env=None` preserves today's behavior.

## Files Affected

- `the_one/platform/__init__.py` — created
- `the_one/platform/paths.py` — created
- `the_one/platform/shell.py` — created
- `the_one/platform/interpreter.py` — created
- `the_one/platform/tempdirs.py` — created
- `tests/test_platform_paths.py` — created
- `tests/test_platform_shell.py` — created
- `tests/test_platform_interpreter.py` — created
- `tests/test_platform_tempdirs.py` — created
- `missions/05-built-in-tool-system/flights/02-cross-platform-foundations-and-policy-resolver/flight-log.md` — append L1 progress entry (artifact, not source code)
- `missions/05-built-in-tool-system/flights/02-cross-platform-foundations-and-policy-resolver/flight.md` — check off L1 (artifact, not source code)
- *No source code modified under `the_one/tools/`* (copy-don't-cut)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (per agentic-workflow batched-review pattern, the Developer does NOT commit; review and commit happen once at flight end):

- [ ] All acceptance criteria verified
- [ ] New platform tests passing
- [ ] Pre-existing unit suite still green (modulo pre-existing CSS-token red)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit — final commit happens once after L7
