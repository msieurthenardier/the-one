# Leg: containment-behavior-suite

**Status**: completed
**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](../flight.md)

## Objective

Consolidate the duplicated `@requires_bwrap` setup shared by
`test_builtin_tool_sandbox.py` and `test_pty_sandbox.py` into a single importable
`tests/_sandbox_fixtures.py` module, and confirm the already-authored unified
behavior spec `tests/behavior/tool-sandbox-containment.md` is present and coherent —
all bwrap tests staying green after the refactor.

## Context

- **DD3** (flight): one unified agent-driven containment behavior test
  (`tool-sandbox-containment`) authored around agent-safe observables. **That spec
  already exists** — it was written inline during planning and is committed
  (`tests/behavior/tool-sandbox-containment.md`, status `draft`). This leg does **not**
  re-author it; it verifies coherence and leaves it `draft` (it flips to `active` when
  it first passes live, in `verify-integration`).
- **DD3 / architect correction**: consolidate the shared `@requires_bwrap` setup into
  `tests/_sandbox_fixtures.py` scoped to **`test_builtin_tool_sandbox.py` +
  `test_pty_sandbox.py`** only. `test_mcp_sandbox_integration.py` is structurally
  different (uses `/var/tmp` to dodge `--tmpfs /tmp`, its own `writable_scratch_dir`
  fixture, drives `MCPClient`, probes external DNS rather than a loopback server) — pull
  in a shared helper **only if one genuinely applies**; do **not** force the `$HOME`
  shape onto it.
- This is a **test-only / no-enforcement-code** leg. No production `.py` changes.

### Duplicated patterns to extract (verified against current code)

| Pattern | builtin test | pty test | Notes |
|---|---|---|---|
| `_sleep_pids()` — `pgrep -f "sleep 30"` → set of PIDs | `:307-317` (**inner function** inside `test_timeout_kills_promptly_no_orphan`, indented) | `:41-51` (**module-level**) | Semantically identical. Extract as a module-level function **matching the PTY copy's form**; in the builtin test, delete the inner-function def and replace with the import. |
| Loopback TCP server (socket + `SO_REUSEADDR` + daemon thread + `stop_event`) | setup `:167-186`; teardown `stop_event.set()/server_sock.close()/t.join()` at `:236-238` | setup `:285-304`; teardown at `:365-367` | **Identical setup.** Extract only the **server** (socket+thread lifetime) into the CM's enter/exit. The probe differs (builtin = inline python `connect_code`; pty = single-line `connect_cmd` with `"con"+"nected"` echo trick) — do NOT extract it. **Note**: the `shutil.rmtree(workspace)` at `:239` / `:368` sits in the *same* `finally` block but belongs to the workspace CM, **not** the loopback CM — keep the two cleanups separate. |
| Workspace under `$HOME` (`home / ".the-one-test-…"`, `mkdir(exist_ok=True)`, `finally: shutil.rmtree(…, ignore_errors=True)`) | every test | every test | Extract as a context manager that yields the path and rmtrees on exit. **Two-dir tests**: `test_write_outside_allowlist_denied` (builtin `:73-76`) and `test_pty_write_outside_allowlist_denied` (pty `:172-175`) each create a `workspace` AND a `sibling` — nest two `home_workspace(...)` CMs (or keep the sibling inline). Either is fine; just ensure both get cleaned up. |
| Denylist secret fixture (`secret_dir.mkdir`; `secret_file = secret_dir/"key"`; `write_text("original-content")`) | `:115-118` | `:222-225` | Extract a helper that materializes the secret and returns `(secret_dir, secret_file)`. **Footgun — put the canonical warning in THIS helper's docstring**: `--ro-bind-try` silently skips absent paths, so the denylist dir MUST exist before the run (this is the helper whose contract depends on it). `home_workspace` may cross-reference it; the canonical note lives on `make_denylist_secret`. (Full doc treatment is in `debt-and-docs`.) |
| `monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)` | every test | every test | One-liner; may stay inline OR become a tiny helper — implementer's call. Do not over-abstract. |

## Inputs

- `tests/test_builtin_tool_sandbox.py` (5 `@requires_bwrap` tests) and
  `tests/test_pty_sandbox.py` (5 `@requires_bwrap` tests), current on the branch.
- `tests/behavior/tool-sandbox-containment.md` already authored (`draft`).
- `bwrap` present on host.

## Outputs

- New `tests/_sandbox_fixtures.py` — shared helpers (leading underscore so pytest does
  not collect it as a test module).
- `tests/test_builtin_tool_sandbox.py` and `tests/test_pty_sandbox.py` refactored to
  import the shared helpers; duplicated copies removed.
- `tests/test_mcp_sandbox_integration.py` — assessed; changed only if a genuinely
  shared helper applies (expected: no change).
- The behavior spec verified coherent (no content change expected).

## Acceptance Criteria

- [x] `tests/_sandbox_fixtures.py` exists and provides at minimum: a `sleep_pids()`
      helper, a loopback-TCP-server helper (context manager or factory returning the
      bound port + a teardown), a workspace-under-`$HOME` context manager, and a
      denylist-secret materializer. Each carries a docstring.
- [x] `test_builtin_tool_sandbox.py` and `test_pty_sandbox.py` import these helpers;
      the inline `_sleep_pids`, inline loopback-server blocks, and per-test
      workspace-mkdir/rmtree boilerplate are **removed** (no remaining duplicate copy
      of an extracted pattern across the two files).
- [x] All `@requires_bwrap` tests in **both** files still pass under real bwrap (same
      count green as before: 5 + 5 = 10).
- [x] The non-bwrap default run of both files is unaffected (tests deselect cleanly).
- [x] `test_mcp_sandbox_integration.py` is assessed; the flight log entry records the
      decision (expected: left as-is — different `/var/tmp` + `MCPClient` shape; loopback
      helper N/A since it probes external DNS). If any shared helper *is* pulled in, it
      must not impose the `$HOME` shape on the MCP test.
- [x] `tests/behavior/tool-sandbox-containment.md` exists, is well-formed (Steps table
      present, agent-safe observables, Out of Scope references
      `tests/test_cli_sandbox_parity.py` which now exists), and remains `draft`.
- [x] No production source files (`the_one/**`) modified. `ruff check` + `ruff format
      --check` pass on all touched test files.

## Verification Steps

- `docker exec the-one python -m pytest tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py -m requires_bwrap --timeout 120` — 10 passed.
- `docker exec the-one python -m pytest tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py -m "not requires_bwrap" --timeout 60` — clean deselect / no errors at import.
- `docker exec the-one python -m pytest tests/test_mcp_sandbox_integration.py -m requires_bwrap --timeout 120` — still green if touched (run regardless to confirm no collateral).
- `grep -n "_sleep_pids\|SO_REUSEADDR\|workspace.mkdir\|shutil.rmtree" tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py` — confirm the extracted boilerplate no longer appears inline (only the import + call sites remain). Note: the `".the-one-test-…"` suffix strings legitimately persist as `home_workspace(...)` arguments, so do NOT grep for them.
- `docker exec the-one ruff check tests/ && docker exec the-one ruff format --check tests/_sandbox_fixtures.py tests/test_builtin_tool_sandbox.py tests/test_pty_sandbox.py`.

## Implementation Guidance

1. **Author `tests/_sandbox_fixtures.py`.** Prefer **context-manager helpers** over
   pytest fixtures — the existing tests use explicit `try/finally`, context managers map
   onto that with minimal churn, and a plain importable module avoids conftest
   fixture-registration. Suggested surface (names illustrative):
   - `def sleep_pids() -> set[str]:` — verbatim copy of the existing helper.
   - `@contextmanager def home_workspace(suffix: str) -> Iterator[Path]:` — creates
     `Path.home() / f".the-one-test-{suffix}"`, `mkdir(exist_ok=True)`, yields it,
     `shutil.rmtree(..., ignore_errors=True)` on exit. (Optionally support extra
     sibling dirs, or let callers nest a second `home_workspace`.)
   - `@contextmanager def loopback_server() -> Iterator[int]:` — binds
     `127.0.0.1:0`, starts the daemon accept-thread (`sendall(b"hello")`), yields the
     port, sets the stop event + closes + joins on exit.
   - `def make_denylist_secret(workspace: Path) -> tuple[Path, Path]:` — creates
     `workspace/"secret"/"key"` with `"original-content"`, returns `(secret_dir, secret_file)`.
   - Keep `monkeypatch.delenv(...)` at the call sites (it needs the test's
     `monkeypatch`); do not try to wrap monkeypatch in this module.

2. **Refactor both test files** to import and use the helpers. **Preserve every test's
   semantics exactly** — same workspace names (or equivalent unique suffixes), same
   assertions, same probe code/cmd (the probe is NOT shared). Do not change the
   `"con"+"nected"` echo trick in the PTY network test (it dodges the PTY-echo footgun).
   The two-dir allowlist tests use a `workspace` + `sibling` (see table) — nest two
   `home_workspace(...)` CMs or keep the sibling inline. Switching to CM-based cleanup
   may incidentally make teardown more robust (e.g. the PTY allowlist test currently
   doesn't guard `sibling` cleanup if `session.start()` throws) — that's an acceptable
   improvement **as long as no assertion changes**; do not treat semantics-preservation
   as forbidding more-reliable cleanup.

3. **Assess the MCP test.** Read `test_mcp_sandbox_integration.py`. Confirm it uses
   `/var/tmp` + `writable_scratch_dir` + `MCPClient` + external DNS (not a loopback
   server). Conclusion expected: **no shared helper applies** — leave it unchanged.
   Record the assessment in the flight log. If you find a genuinely shared, identical
   helper (e.g. a loopback server it secretly also uses), pull only that, without the
   `$HOME` workspace shape.

4. **Verify the behavior spec** (`tests/behavior/tool-sandbox-containment.md`) is
   coherent: Steps table present, all assertions agent-safe (no "perform the exploit
   and read the error"), Out of Scope references the now-existing
   `tests/test_cli_sandbox_parity.py`. Leave status `draft`. Do not re-author.

## Edge Cases

- **`_sandbox_fixtures.py` collected as tests**: the leading underscore keeps pytest
  from collecting it, but double-check there are no `test_`-prefixed functions in it.
- **Context manager vs fixture**: if the implementer prefers pytest fixtures, they must
  be registered (conftest `pytest_plugins = ["tests._sandbox_fixtures"]` or moved into a
  conftest). Context managers avoid this entirely — recommended.
- **Loopback server lifetime**: the accept-thread must be a daemon and joined on exit so
  a refactor doesn't leak threads across tests.
- **Semantic drift**: the refactor must not weaken any assertion. If a test's behavior
  changes (e.g. a workspace path collision under a shared suffix), that's a regression —
  keep suffixes unique per test.
- **Do not pre-touch `debt-and-docs` files**: the `--ro-bind-try` footgun doc lives in
  `debt-and-docs`; here, only mention it in the helper docstring.

## Files Affected

- `tests/_sandbox_fixtures.py` — **new**; shared `@requires_bwrap` helpers.
- `tests/test_builtin_tool_sandbox.py` — refactor to import shared helpers.
- `tests/test_pty_sandbox.py` — refactor to import shared helpers.
- `tests/test_mcp_sandbox_integration.py` — assess-only (expected: no change).
- `tests/behavior/tool-sandbox-containment.md` — verify only (no change expected).

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to
> `landed`, signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified
- [x] 10 `@requires_bwrap` tests green after refactor; ruff clean
- [x] MCP-test assessment recorded in the flight log
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
