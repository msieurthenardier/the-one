# Squawk 0251: 21 unit tests fail on CPython 3.11.14 and pass on 3.12

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: —

## Report
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

## Corrective Action
*(written at completion)*

## Verification
- The four files pass on CI's `python3.11` image and on 3.12, or the supported floor is deliberately moved to 3.12 (`requires-python`, the CI image, Mission 32's freeze interpreter) with the operator's approval.
- `make test-unit` passes on both versions.

## Sign-Off
*(written at completion)*

## Disposition

**Escalate if** the fix needs a design change to MCP connection-failure cleanup, or a change to the supported Python floor. Either is a design decision, not a squawk.
