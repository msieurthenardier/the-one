# Leg: rename-sandbox-abstraction

**Status**: completed
**Flight**: [Sandbox Seam + Built-in Tool Retrofit](../flight.md)

## Objective

Rename the sandbox abstraction's two public symbols — `MCPSandbox` → `ToolSandbox`
and `MCPSandboxError` → `SandboxError` — across every importer, docstring, and test,
**keeping `SandboxError`'s canonical home in `the_one/mcp/errors.py` and its
`MCPClientError` parentage** so the `client.py` teardown catch still propagates
sandbox errors through MCP teardown. Pure symbol rename — no behavior change.

## Context

- **DD8 (flight):** rename the abstraction *in place*, not a relocation. The
  abstraction is now platform-wide (it will sandbox built-in tools, not just MCP),
  so the `MCP` prefix is misleading. But the error class's *home* and *hierarchy*
  must stay put: `the_one/mcp/client.py` deliberately relies on `SandboxError`
  being an `MCPClientError` subclass to let sandbox-setup failures propagate
  through MCP teardown (the `except MCPClientError` catch). Relocating the error
  out of `mcp/` would silently break that catch or re-introduce a `platform→mcp`
  dependency. Relocation is deferred to a future mission.
- **Why its own leg:** blast radius is real — ~18 files, ~106 `MCPSandboxError`
  refs + ~16 `MCPSandbox` refs (verified at design time). Landing the rename first
  means the factory/passthrough work (legs 2–4) is authored against the final names.
- This is the **first** leg; no prior leg outcomes to inherit.

## Inputs

What exists before this leg runs:
- `the_one/mcp/errors.py` defines `MCPSandboxError(MCPClientError)`
  (`errors.py:37`).
- `the_one/platform/sandbox/base.py` defines the `MCPSandbox` Protocol
  (`base.py:209 — "class MCPSandbox(Protocol)"`).
- `the_one/platform/sandbox/__init__.py` re-exports both
  (imports at `__init__.py:15-16`; `__all__` at `__init__.py:19-25`; line 17 is the
  `BubblewrapSandbox` import, which is unaffected).
- `the_one/mcp/client.py:511 — "except MCPClientError as e"` is the teardown
  catch that must keep catching sandbox errors via the `MCPClientError` parentage.
- Working tree is clean on branch `flight/01-sandbox-seam-builtin-retrofit`.

## Outputs

What exists after this leg completes:
- `the_one/mcp/errors.py` defines `SandboxError(MCPClientError)` — **same file,
  same parent class**, only the class name changed.
- `the_one/platform/sandbox/base.py` defines the `ToolSandbox` Protocol.
- Every importer, type annotation, `isinstance`/`except` clause, `__all__` entry,
  and test reference uses the new names.
- Docstrings and comments that name the symbols-as-code use the new names.
- The `MCPClientError` hierarchy is unchanged; `client.py`'s teardown catch still
  catches `SandboxError`.
- Full default test suite green; `ruff check` + `ruff format --check` green.

## Acceptance Criteria

- [x] `grep -rn 'MCPSandbox' --include='*.py'` returns **zero** matches for the
      symbols `MCPSandbox` and `MCPSandboxError` in source and tests (no symbol
      reference, type annotation, import, or `__all__` entry remains). *(See Edge
      Cases for the message-string carve-out.)*
- [x] `grep -rn 'MCPSandbox' the_one/agents.md the_one/mcp/README.md` returns
      **zero** symbol matches — the two canonical doc files have their backtick
      symbol references and import-path examples renamed too (prose mentions of
      "MCP sandbox" as a concept may remain; see Edge Cases).
- [x] No test asserts the **old class name as a rendered string**. Both
      `tests/test_mcp_tool_provider.py` (`assert "MCPSandboxError" in result`) and
      `tests/test_mcp_stdio_test_connect.py` (`assert "MCPSandboxError" in body[...]`)
      are updated to `"SandboxError"` — these assert `type(e).__name__` output, not
      message-string literals, so they change with the rename (see Edge Cases).
- [x] `SandboxError` is defined in `the_one/mcp/errors.py` and is a subclass of
      `MCPClientError` (`issubclass(SandboxError, MCPClientError)` is `True`).
- [x] `ToolSandbox` is defined in `the_one/platform/sandbox/base.py` as the
      `@runtime_checkable` Protocol, and re-exported from
      `the_one/platform/sandbox/__init__.py` (`__all__` lists `ToolSandbox` and
      `SandboxError`, not the old names).
- [x] `the_one/mcp/client.py`'s teardown catch (`except MCPClientError`) is
      unchanged and still catches `SandboxError` (verified by the existing
      sandbox-teardown test, or a direct `issubclass` assertion if none exists).
- [x] The canonical import path `from the_one.mcp.errors import SandboxError`
      works; `from the_one.platform.sandbox import ToolSandbox, SandboxError` works.
- [x] Full default suite passes (`docker exec the-one pytest -x --timeout 30`),
      and `ruff check .` + `ruff format --check .` pass.

## Verification Steps

- `docker exec the-one grep -rn 'MCPSandbox' /app --include='*.py'` (or run from
  repo root) — expect no symbol matches; only message-string literals like
  `"MCP sandbox setup failed"` may remain (see Edge Cases).
- `docker exec the-one python -c "from the_one.mcp.errors import SandboxError; from the_one.mcp.errors import MCPClientError; assert issubclass(SandboxError, MCPClientError)"`
- `docker exec the-one python -c "from the_one.platform.sandbox import ToolSandbox, SandboxError"`
- `docker exec the-one pytest -x --timeout 30` — full suite green (the
  `@requires_bwrap`-marked tests stay deselected by default addopts).
- `ruff check . && ruff format --check .`

## Implementation Guidance

1. **Rename the error class in its canonical home.**
   - In `the_one/mcp/errors.py`, rename `class MCPSandboxError(MCPClientError)`
     → `class SandboxError(MCPClientError)` (`errors.py:37`). Keep it in this
     file, keep the `MCPClientError` parent, keep the docstring (update any
     in-docstring mention of the class name).
   - Note the `# noqa: N818` convention used on other non-`Error`-suffixed
     classes does not apply here — `SandboxError` ends in `Error`, so it needs
     no noqa.

2. **Rename the Protocol.**
   - In `the_one/platform/sandbox/base.py`, rename `class MCPSandbox(Protocol)`
     → `class ToolSandbox(Protocol)` (`base.py:209`). Update the module docstring's
     references to `MCPSandbox`/`MCPSandboxError` (the "Error class" section at
     `base.py:73-79` and the Protocol references in the header prose) to the new
     names.

3. **Update the package re-export.**
   - In `the_one/platform/sandbox/__init__.py`, update the imports
     (`__init__.py:15-16`), the `__all__` list (`__init__.py:19-25`), and the
     module docstring's public-API listing (`__init__.py:1-11`) to the new names.

4. **Sweep all remaining importers and references** across source and tests.
   The known files (verified at design time):
   - Source: `the_one/interfaces/web/api.py`, `the_one/mcp/_tool.py`,
     `the_one/mcp/_tool_provider.py`, `the_one/mcp/client.py`,
     `the_one/mcp/transports/stdio.py`, `the_one/platform/sandbox/bubblewrap.py`.
   - Tests: `tests/test_mcp_client.py`, `tests/test_mcp_pool.py`,
     `tests/test_mcp_sandbox_integration.py`,
     `tests/test_mcp_stdio_error_translation.py`,
     `tests/test_mcp_stdio_sandbox.py`, `tests/test_mcp_stdio_test_connect.py`,
     `tests/test_mcp_tool_provider.py`, `tests/test_sandbox_bubblewrap.py`,
     `tests/test_sandbox_contract.py`.
   - Use the grep in Verification Steps as the completion check — drive it to zero
     symbol matches.

5. **Decide each occurrence by kind:**
   - **Symbol references** (imports, type hints, `except`/`isinstance`, `__all__`,
     class instantiation, `prepare_spawn` Protocol typing): rename.
   - **Docstring/comment mentions of the class as a named code symbol**: rename
     (DD8 says "incl. docstrings").
   - **User-facing message-string literals** (e.g. `"MCP sandbox setup failed: …"`
     inside `_translate_bwrap_stderr`, `stdio.py:173/183/190`): **leave as-is** —
     these are prose describing MCP-server sandboxing, not symbol references, and
     rewording them is out of scope for a symbol rename (a later leg revisits
     built-in-tool messaging). See Edge Cases.

6. **Run the suite and lint**, fix any fallout, confirm green.

## Edge Cases

- **Message-string literals vs symbols.** `the_one/mcp/transports/stdio.py`
  constructs error messages like `"MCP sandbox setup failed: …"`
  (`stdio.py:173`, `:183`, `:190`). These are *not* the renamed symbol — they are
  human-readable text specific to the MCP path. Do **not** rename them in this leg.
  The acceptance grep targets the `MCPSandbox`/`MCPSandboxError` *symbols*; a
  remaining `"MCP sandbox"` substring inside a quoted message is acceptable and
  expected. (If a grep for `MCPSandbox` with a word boundary still flags these,
  confirm by eye they are inside string literals.)
- **Class-name-as-rendered-string assertions ARE in scope (the subtle one).**
  Two tests assert the *class name as it appears in formatted output*, not a
  message literal:
  - `tests/test_mcp_tool_provider.py` — `assert "MCPSandboxError" in result`
    (production formats `f"... {type(e).__name__}: {e}"` at
    `the_one/mcp/_tool.py:165 — "type(e).__name__"`).
  - `tests/test_mcp_stdio_test_connect.py` — `assert "MCPSandboxError" in body["error"]`
    (production formats `f"{type(e).__name__}: {e}"` at
    `the_one/interfaces/web/api.py:1591`).
  After the rename, `type(e).__name__` becomes `"SandboxError"`, so these
  assertions **must** be updated to `"SandboxError"` or the tests fail. These
  look like string literals but are really assertions about the renamed symbol —
  rename them. (Also update the nearby test docstrings/descriptions that name the
  old class, per the docstring rule in Step 5.)
- **Doc files carry symbol references too.** `the_one/agents.md` and
  `the_one/mcp/README.md` reference `MCPSandbox`/`MCPSandboxError` as backtick
  code symbols and in import-path examples. The `.py`-only acceptance grep won't
  catch these, so they are called out as a separate acceptance criterion and in
  Files Affected. Rename the symbol references; leave plain-prose "MCP sandbox"
  concept mentions (same carve-out as the message strings).
- **`MCPClientError` must not be renamed.** Only `MCPSandboxError` →
  `SandboxError`. The base class `MCPClientError` and every *other* `MCP*`-prefixed
  error (`MCPConnectionError`, `MCPVersionMismatch`, etc.) stay exactly as they
  are — they remain MCP-specific. A careless `s/MCP//` would corrupt them.
- **No relocation.** Do not move `SandboxError` to `platform/sandbox/`. Its home
  stays `mcp/errors.py` (DD8). Moving it breaks `client.py`'s catch or re-creates
  a `platform→mcp` import cycle.
- **`isinstance`/`except` ordering.** If any site catches `MCPSandboxError`
  *before* a broader `MCPClientError`, the rename preserves ordering — just the
  name changes. Verify no `except` clause was relying on the literal name in a way
  a rename would reorder (it won't, but confirm the teardown catch at
  `client.py:511` is untouched in structure).
- **Stale F-number references in docstrings** (e.g. "F4 leg 02", "F3 §6") are
  historical provenance, not symbols — leave them; only the class names change.

## Files Affected

- `the_one/mcp/errors.py` — rename class `MCPSandboxError` → `SandboxError`.
- `the_one/platform/sandbox/base.py` — rename Protocol `MCPSandbox` → `ToolSandbox`;
  update module docstring.
- `the_one/platform/sandbox/__init__.py` — update imports, `__all__`, docstring.
- `the_one/platform/sandbox/bubblewrap.py` — update symbol references/docstrings.
- `the_one/mcp/client.py` — update symbol references (multiple docstring/comment
  mentions at `client.py:270`, `:378`, `:499` in addition to imports); **leave the
  teardown catch structure at `client.py:511` intact**.
- `the_one/mcp/transports/stdio.py` — update symbol references; **leave message
  strings**.
- `the_one/mcp/_tool.py`, `the_one/mcp/_tool_provider.py`,
  `the_one/interfaces/web/api.py` — update symbol references.
- All nine `tests/test_*.py` files listed above — update symbol references,
  **including the two class-name-as-rendered-string assertions** (see Edge Cases).
- `the_one/agents.md`, `the_one/mcp/README.md` — update backtick symbol references
  and import-path examples; leave plain-prose "MCP sandbox" concept mentions.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (N/A — leg 1 of 5)
- [x] Commit all changes together (code + artifacts)

> **Note (batched flight):** This flight runs via `/agentic-workflow` with batched
> review/commit. The Developer implementing this leg does **not** commit and does
> **not** signal `[COMPLETE:leg]` — it sets the leg to `landed`, updates the flight
> log, and signals `[HANDOFF:review-needed]`. Status moves to `completed` and the
> commit happens in the flight-level review/commit phase (2d).
