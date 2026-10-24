# Squawk 0251: 21 unit tests fail on CPython 3.11.14 and pass on 3.12

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: 2026-10-24

## Report
> **Count note (at completion):** the title's "21" is the original observation, which included OpenRouter failures from an unlocked resolve. Reproduced against the locked closure, 15 tests fail on 3.11 (11 in `test_mcp_signin_detection.py`, 4 in `test_mcp_test_connection_negotiation.py`); see Investigation.

In Mission 32 Flight 1 (leg `linux-pyinstaller-build`, 2026-10-23), `make test-unit` in a uv-managed CPython 3.11.14 venv failed 21 tests that pass in the same worktree on CPython 3.12. The failing files:
- `tests/test_mcp_signin_detection.py`
- `tests/test_mcp_test_connection_negotiation.py`
- `tests/test_mcp_wire_shapes.py`
- `tests/test_credential_gate.py`

The common error is `CancelledError` raised in `MCPClient._cleanup_after_failed_connect`. The leg judged them environmental, with no app code changed, and moved the worktree venv to 3.12, where the gate passed (6783 passed, 12 skipped).

Why it matters:
- `pyproject.toml` declares `requires-python = ">=3.11"`.
- CI's unit tier (`ci/tasks/test.yml`) runs `ghcr.io/astral-sh/uv:0.9.30-python3.11-bookworm`.
- Mission 32 chose PyInstaller and freezes the shipped Linux and macOS bundles with Python 3.11 (Flight 1 decision). If this is real 3.11 behaviour (for example, asyncio cancellation semantics differing between 3.11 and 3.12), the installers would carry it.

Reproduce:
1. Make a 3.11 venv: `uv venv --python 3.11 /tmp/v311` (or use CI's image).
2. Install the locked closure: `uv pip install --python /tmp/v311/bin/python -r <(uv export --no-dev --no-emit-project --extra all-llms --extra dev --format requirements-txt) --no-deps`, then `pip install -e . --no-deps`.
3. Run `python -m pytest tests/test_mcp_signin_detection.py tests/test_mcp_test_connection_negotiation.py tests/test_mcp_wire_shapes.py tests/test_credential_gate.py -x --timeout 30`.

## Evidence
- Mission 32 Flight 1, flight log `### linux-pyinstaller-build`, the unit-gate notes, and the evidence files `$HOME/the-one-m32-evidence/unit-gate.log` and `unit-gate2.log` (local to the operator's host).
- `the_one/mcp/client.py::MCPClient._cleanup_after_failed_connect`: the site the `CancelledError` came from.
- First step: run the four files under CI's exact image (Debian's `python3.11`) to tell "uv-managed 3.11.14 only" from "3.11 generally". If CI's image passes, record why the two differ. If it fails, CI's unit lane should already be red, so check its recent builds.

### Investigation (2026-10-24)
- Reproduced in both environments, same patch version: uv-managed CPython 3.11.14 (Clang build) and CI's image `ghcr.io/astral-sh/uv:0.9.30-python3.11-bookworm` (Debian CPython 3.11.14, GCC). Both fail the same **15** tests (not 21) in the four files: 11 in `test_mcp_signin_detection.py`, 4 in `test_mcp_test_connection_negotiation.py`; `test_mcp_wire_shapes.py` and `test_credential_gate.py` pass here. So it is real 3.11 behaviour, not a uv-build quirk, and CI's unit lane on main should be red (not checked: `fly -t the-one` is not logged in).
- Traceback: `CancelledError: Cancelled via cancel scope ... by <Task ... _cleanup_after_failed_connect()>` raised out of `await waiter` in `asyncio.tasks.wait`, from `_safe_cleanup`'s `asyncio.wait_for(...)`.
- Root cause: on 3.11 `asyncio.wait_for` runs the awaitable in a **child task** (3.12 inlined it onto `asyncio.timeout`, same task). The SDK's anyio task group was entered by the connecting task, so the cleanup task exiting it cancels the connecting task's scope: the bare `CancelledError` lands on the caller, past the `except` that was written to absorb it.

## Corrective Action
Replaced `asyncio.wait_for(self._cleanup_after_failed_connect(), timeout=3.0)` with `async with asyncio.timeout(3.0): await self._cleanup_after_failed_connect()` in `MCPClient.connect`'s `_safe_cleanup` (`the_one/mcp/client.py`). Same 3 s bound and same exception handling, but the cleanup runs in the caller's task on 3.11 and 3.12 alike. No interface change; the supported floor is unchanged.

## Verification
- Four files: 160 passed on uv CPython 3.11.14, on CI's image (3.11.14), and (as part of the suite) on 3.12.3. Before: 15 failed on both 3.11 environments.
- `make test-unit` on 3.12.3: 6783 passed, 12 skipped.
- Full unit tier in CI's image (no bwrap, unprivileged container): 6802 passed, 20 failed, all in bwrap sandbox files (`test_box_isolation`, `test_builtin_tool_sandbox`, `test_cli_sandbox_parity`, `test_mcp_sandbox_integration`, `test_pty_sandbox`); none touch the MCP client, and they need namespaces the container lacks (CI runs privileged).
- `ruff check` and `ruff format --check` clean on `the_one/mcp/client.py`.

Criteria (original):
- The four files pass on CI's `python3.11` image and on 3.12, or the supported floor is deliberately moved to 3.12 (`requires-python`, the CI image, Mission 32's freeze interpreter) with the operator's approval.
- `make test-unit` passes on both versions.

## Sign-Off
**Reviewer**: independent Reviewer agent (Haiku tier; MCP connect-failure cleanup, not a credential or sandbox surface), scoped to the diff
**Verdict**: confirmed. The same 3 s bound, the cleanup in the caller's task, the `except` tuple still catching `TimeoutError`, `asyncio.timeout` available on the 3.11 floor; the four files pass on 3.11.14 and 3.12.3; ruff clean
**Commit**: see the squawk branch commit (`squawk/0251-unit-failures-on-cpython-311`)

## Disposition

**Escalate if** the fix needs a design change to MCP connection-failure cleanup, or a change to the supported Python floor. Either is a design decision, not a squawk.
