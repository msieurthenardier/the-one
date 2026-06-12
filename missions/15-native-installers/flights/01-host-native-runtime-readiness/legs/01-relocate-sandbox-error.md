# Leg: relocate-sandbox-error

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

Move the `SandboxError` definition out of `the_one/mcp/errors.py` into a sandbox-owned
module so M15's per-OS backends import their error from the sandbox domain, not the MCP
module — without creating an import cycle.

## Context

- **Flight DD** — "`SandboxError` relocates to the sandbox package — definition moves,
  no back-edge re-export." The M14 debrief flagged the `mcp/errors.py` home as an
  "import-cycle inversion" that "blocks clean M15 backend errors."
- **Reconnaissance correction** — there is *no literal runtime cycle today* (imports
  are one-way: `platform/sandbox/* → mcp.errors`, and `mcp/errors.py` is a verified
  zero-import leaf). The fix addresses the **layering** inversion: a sandbox-domain
  error living in the MCP module. The sandbox-domain import path already exists
  (`platform/sandbox/__init__.py:17` re-exports `SandboxError`).
- **Design-review HIGH (resolved)** — a back-compat re-export *back* from
  `mcp/errors.py` would *manufacture* an order-dependent circular import (the factory
  documents this exact deferral at `platform/sandbox/factory.py:62-64`). So: definition
  moves, base imported one-way, **no re-export back-edge**; importers are repointed.
- Lands early for a clean backend error base, but is **not** a hard predecessor of
  Legs 2/3/7 (they don't touch `SandboxError`).

## Inputs

- `the_one/mcp/errors.py` defines `SandboxError(MCPClientError)` at line 37; the module
  is a pure leaf (no imports).
- `the_one/platform/sandbox/__init__.py:17` already re-exports `SandboxError` from
  `the_one.mcp.errors`.
- `the_one/platform/sandbox/base.py:76-79` documents the canonical home.
- The complete set of importers that source `SandboxError` from `the_one.mcp.errors`
  (from design review — see Files Affected).

## Outputs

- New module `the_one/platform/sandbox/errors.py` defining `SandboxError(MCPClientError)`,
  importing `MCPClientError` one-way from `the_one.mcp.errors`.
- `SandboxError` removed from `the_one/mcp/errors.py` (no re-export back).
- Every importer repointed to source `SandboxError` from the sandbox package
  (`the_one.platform.sandbox` for external consumers; `the_one.platform.sandbox.errors`
  for in-`mcp`-package importers, to avoid pulling the whole package).
- The stale duplicated-predicate note at `factory.py:62-64` removed.
- Full suite + `ruff` green.

## Acceptance Criteria

- [x] `the_one/platform/sandbox/errors.py` exists and defines
      `SandboxError(MCPClientError)` with a one-way import of `MCPClientError` from
      `the_one.mcp.errors`.
- [x] `the_one/mcp/errors.py` no longer defines or re-exports `SandboxError`, and
      remains import-free (still a leaf).
- [x] `the_one.platform.sandbox.SandboxError` and
      `the_one.platform.sandbox.errors.SandboxError` are the **same object**, and
      `issubclass(SandboxError, MCPClientError)` holds.
- [x] Every importer in Files Affected sources `SandboxError` from the sandbox package
      (none still `from the_one.mcp.errors import ... SandboxError`).
- [x] No new import cycle: importing `the_one.platform.sandbox.errors` first (cold) and
      `the_one.mcp.errors` first (cold) both succeed.
- [x] The stale note at `factory.py:62-64` is removed.
- [x] `tests/test_sandbox_contract.py` passes with `CanonicalSandboxError` repointed to
      `the_one.platform.sandbox.errors`; `issubclass` + identity assertions still hold.
- [x] Canonical-home docs updated: `agents.md:40` and `base.py:76-79` name
      `the_one/platform/sandbox/errors.py` as canonical (no stale `mcp.errors` guidance).
- [x] Full test suite passes and `ruff check`/`ruff format` are clean.

## Verification Steps

- `grep -rn "from the_one.mcp.errors import" the_one tests | grep SandboxError` → no hits.
- `docker exec the-one python -c "from the_one.platform.sandbox.errors import SandboxError as A; from the_one.platform.sandbox import SandboxError as B; from the_one.mcp.errors import MCPClientError; assert A is B and issubclass(A, MCPClientError); print('identity+subclass OK')"`
- `docker exec the-one python -c "import the_one.platform.sandbox.errors"` (cold) and
  `docker exec the-one python -c "import the_one.mcp.errors"` (cold) → both exit 0.
- `docker exec the-one pytest -x --timeout 30 tests/test_sandbox_contract.py tests/test_sandbox_bubblewrap.py tests/test_mcp_stdio_error_translation.py` → green; then full suite once at leg-end.
- `docker exec the-one ruff check . && docker exec the-one ruff format --check .`

## Implementation Guidance

1. **Create `the_one/platform/sandbox/errors.py`**
   - `from the_one.mcp.errors import MCPClientError`
   - Move the `SandboxError` class body verbatim from `mcp/errors.py:37` (keep the
     docstring; keep `MCPClientError` as the base).

2. **Remove `SandboxError` from `the_one/mcp/errors.py`**
   - Delete the class. Do **not** add any import or re-export of it back — keep the
     module a zero-import leaf.

3. **Repoint the sandbox package canonical re-export**
   - `the_one/platform/sandbox/__init__.py:17` (and the docstring at line 10): import
     `SandboxError` from `.errors` instead of from `the_one.mcp.errors`. This keeps
     `the_one.platform.sandbox.SandboxError` working as the public domain path.

4. **Repoint the remaining source importers** (source from the sandbox package):
   - `the_one/platform/sandbox/bubblewrap.py:35` (used at the `__init__` raise, line 84)
   - `the_one/mcp/transports/stdio.py:74` — this file **already** imports
     `from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile, ToolSandbox`
     (lines 76-79); add `SandboxError` to that existing block rather than a second
     import (cleaner; no extra package-load cost since the package is already pulled).
   - `the_one/mcp/_tool_provider.py:57` (multi-line block from line 52) — use
     `the_one.platform.sandbox.errors` directly (this file doesn't otherwise import the
     sandbox package, so the `.errors` module avoids pulling the whole package).
   - `the_one/mcp/_tool.py:35` (multi-line block from line 31) — same: use
     `the_one.platform.sandbox.errors` directly.
   - `the_one/interfaces/web/api.py:1542` (function-local import block — repoint in
     place, keep it function-local).

5. **Update the canonical-home documentation** (these encode the OLD import path as
   normative and become factually inverted after the move):
   - `the_one/agents.md:40` — the `canonical-import + convenience-re-export` example
     names `from the_one.mcp.errors import SandboxError` as canonical. Rewrite so the
     canonical path is `from the_one.platform.sandbox.errors import SandboxError` and
     the convenience re-export is `the_one.platform.sandbox`.
   - `the_one/platform/sandbox/base.py:76-79` — docstring stating the canonical home is
     `the_one/mcp/errors.py`. Rewrite to point at `the_one/platform/sandbox/errors.py`.

6. **Repoint the test importers**
   - `tests/test_sandbox_contract.py:32` — repoint `CanonicalSandboxError` to
     `the_one.platform.sandbox.errors` (this is the canonical-home assertion).
   - `tests/test_sandbox_bubblewrap.py:15`, `tests/test_mcp_sandbox_integration.py:76`,
     `tests/test_mcp_stdio_sandbox.py:54`, `tests/test_mcp_stdio_error_translation.py:20`,
     `tests/test_mcp_pool.py:33`, `tests/test_mcp_stdio_test_connect.py:281`
     (function-local — repoint **in place**, keep it local), `tests/test_mcp_tool_provider.py:50`.

7. **Remove the stale note at `factory.py:62-64`** documenting the deferred
   import-cycle inversion (the duplicated predicate it explains may stay or be
   simplified at the developer's discretion, but the now-false note must go).

8. **Run `ruff` + the suite**; fix any import-ordering lint.

## Edge Cases

- **Cold-import order** — because the base is imported one-way and there is no
  back-edge, neither import order can cycle. The two cold-import checks in Verification
  guard this explicitly.
- **`isinstance`/`except` tuples across modules** — consumers catch `SandboxError` by
  reference (e.g. `api.py`, `stdio.py` translation); identity is preserved by sourcing
  the same class object through the package re-export, so these keep working.
- **Missed importer** — any leftover `from the_one.mcp.errors import ... SandboxError`
  fails at import; the grep in Verification must return zero hits before leg-end.

## Files Affected

- `the_one/platform/sandbox/errors.py` — **new**: `SandboxError` definition.
- `the_one/mcp/errors.py` — remove `SandboxError` (stays a leaf).
- `the_one/platform/sandbox/__init__.py` — re-export from `.errors` (line 17 + docstring 10).
- `the_one/platform/sandbox/bubblewrap.py` — import repoint (line 35).
- `the_one/platform/sandbox/factory.py` — remove stale note (lines 62-64).
- `the_one/agents.md` — rewrite the canonical-import example (line 40).
- `the_one/platform/sandbox/base.py` — rewrite the canonical-home docstring (lines 76-79).
- `the_one/mcp/transports/stdio.py` — import repoint (line 74).
- `the_one/mcp/_tool_provider.py` — import repoint (line 57).
- `the_one/mcp/_tool.py` — import repoint (line 35).
- `the_one/interfaces/web/api.py` — import repoint (line 1542).
- `tests/test_sandbox_contract.py` — repoint `CanonicalSandboxError` (line 32).
- `tests/test_sandbox_bubblewrap.py`, `tests/test_mcp_sandbox_integration.py`,
  `tests/test_mcp_stdio_sandbox.py`, `tests/test_mcp_stdio_error_translation.py`,
  `tests/test_mcp_pool.py`, `tests/test_mcp_stdio_test_connect.py`,
  `tests/test_mcp_tool_provider.py` — import repoints.

---
