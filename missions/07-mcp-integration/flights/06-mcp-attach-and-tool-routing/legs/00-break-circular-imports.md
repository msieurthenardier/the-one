# Leg: 00-break-circular-imports

**Status**: completed
**Flight**: [Per-agent MCP attach + tool-routing in agent loop](../flight.md)

## Objective

Move `MCPAuthRequired` from `the_one/mcp/oauth/errors.py` to the canonical `the_one/mcp/errors.py` so the agent layer can import it without dragging in the `mcp.oauth.__init__ → storage → db.repositories → agent.config → agent` chain — retiring F5's lazy-import workarounds and adding `MCPRegistrationError` for L2's prefix-collision surface.

## Context

**Why this leg**: F5 had to lazy-import `MCPAuthRequired` inside `Agent._execute_tool` and `MCPClient.call_tool` because importing it from `the_one.mcp.oauth.errors` triggers `the_one.mcp.oauth.__init__` evaluation (Python loads the package's `__init__.py` when resolving any submodule). That `__init__.py` eagerly imports `storage` (which imports `db.repositories` which imports `agent.config`) — a transitive cycle into the agent layer. F5 papered over with `from the_one.mcp.oauth.errors import MCPAuthRequired` inside function bodies; F6 needs the symbol in module scope (per §6 of the flight) and refuses to inherit the workaround.

**Why move, not refactor**: `MCPAuthRequired` is an MCP-level control-flow signal (the agent loop catches it; it's not OAuth-internal). Per the project's `canonical-import + convenience-re-export` convention (`agents.md::Project Conventions`), it belongs in the canonical MCP errors module alongside `MCPConnectionError`, `MCPToolNotFoundError`, etc. `the_one/mcp/oauth/errors.py` retains a re-export so any existing `from the_one.mcp.oauth.errors import MCPAuthRequired` still works. The chain still exists for callers who explicitly import oauth surfaces (e.g. `provider_factory`); F6 just keeps `MCPAuthRequired` consumers off it.

**Why add `MCPRegistrationError` here**: L2 needs it for the source-name prefix collision (§2 / §8 class #4) and the 64-char tool-name ceiling (§8 sub-case). The error is MCP-registration-level; canonical home is `the_one/mcp/errors.py`. Adding it in L0 (a small leaf-module touch) means L2 can import it without an extra round-trip.

**Prior leg outcomes (flight log)**: empty — F6 started with this leg.

**Stake**: this is the smallest leg in the flight by design. ~70 LOC delta. Verifiable via a single new import-graph regression test plus the 4 existing OAuth-error tests continuing to pass through the re-export shim.

## Inputs

What exists before this leg runs:

- `the_one/mcp/errors.py` — leaf module with `MCPClientError` base + 7 subclasses (`MCPVersionMismatch`, `MCPCapabilityMissing`, `MCPConnectionError`, `MCPSandboxError`, `MCPToolNotFoundError`, `MCPArgumentError`, `MCPCallError`). NO imports from `the_one.*`. Verified leaf at design time.
- `the_one/mcp/oauth/errors.py` — has `MCPAuthRequired` definition; subclasses `MCPClientError` (imported from `the_one.mcp.errors:9`).
- `the_one/agent/core.py` lines 8-13 — F5 lazy-import comment block; `_execute_tool` body uses `from the_one.mcp.oauth.errors import MCPAuthRequired` at line 251.
- `the_one/mcp/client.py` lines 41-45 — F5 lazy-import comment block; `call_tool` body uses `from the_one.mcp.oauth.errors import MCPAuthRequired` at line 436.
- `the_one/mcp/oauth/__init__.py:27` — `from the_one.mcp.oauth.errors import MCPAuthRequired` re-export; `:34` — `__all__` lists `"MCPAuthRequired"`.
- `the_one/mcp/__init__.py:45-53` — re-exports 8 of the 8 `the_one.mcp.errors` symbols but does NOT yet re-export `MCPAuthRequired` (it's still in `oauth.errors`).
- `tests/test_mcp_oauth_errors.py` lines 9, 35, 39, 42, 52, 53 — locks the `MCPAuthRequired` shape (carries `source_id`, `resource_metadata_url`, `consent_url`; subclasses `MCPClientError`, NOT `MCPOAuthError`); imports via `from the_one.mcp.oauth.errors import MCPAuthRequired`.
- `tests/test_mcp_oauth_integration.py:30` and 8 use-sites — imports `MCPAuthRequired` via `from the_one.mcp.oauth.errors import MCPAuthRequired`; 4 `pytest.raises(MCPAuthRequired)` call sites.
- `tests/test_oauth_provider_factory.py:50` — docstring mention only (no import).
- `tests/test_imports.py` — does NOT exist (verified at design time).

## Outputs

What exists after this leg completes:

- `the_one/mcp/errors.py` — gains `MCPAuthRequired` definition (moved verbatim from `mcp.oauth.errors`) AND `MCPRegistrationError` class (new, per L2 consumer).
- `the_one/mcp/oauth/errors.py` — `MCPAuthRequired` definition replaced with `from the_one.mcp.errors import MCPAuthRequired` re-export. `MCPOAuthError` + 3 OAuth subclasses unchanged.
- `the_one/mcp/__init__.py` — `__all__` and the re-export block extend with `MCPAuthRequired` and `MCPRegistrationError`.
- `the_one/agent/core.py` — lines 8-13 lazy-import comment block dropped. Line 251 `from the_one.mcp.oauth.errors import MCPAuthRequired` retired. Module-top `from the_one.mcp.errors import MCPAuthRequired` added at the existing import block.
- `the_one/mcp/client.py` — lines 41-45 lazy-import comment block dropped. Line 436 `from the_one.mcp.oauth.errors import MCPAuthRequired` retired. Module-top `from the_one.mcp.errors import MCPAuthRequired` added (alongside the existing `from the_one.mcp.errors import (...)` block at line 30-38).
- `tests/test_imports.py` (NEW) — locks the chain break: `import the_one.agent.core` does NOT load `the_one.mcp.oauth`. Asserts via `sys.modules` snapshot diff (subprocess-isolated to avoid contamination from prior test imports).
- `tests/test_agent.py` — module-top `from the_one.mcp.errors import MCPAuthRequired` added; lazy import at line 657 retired (single test function `test_execute_tool_translates_mcp_auth_required_to_metadata`). Test assertions unchanged.
- `tests/test_mcp_oauth_errors.py` — assertions unchanged. Imports unchanged (still uses `from the_one.mcp.oauth.errors import MCPAuthRequired` — the re-export means the name resolves to the canonical class; `issubclass(MCPAuthRequired, MCPClientError)` still True).
- `tests/test_mcp_oauth_integration.py` — assertions unchanged. Imports unchanged (re-export resolves identically).

## Acceptance Criteria

- [ ] `MCPAuthRequired` is defined in `the_one/mcp/errors.py` (verified via `grep -n "^class MCPAuthRequired" the_one/mcp/errors.py` returns 1 hit; same grep on `the_one/mcp/oauth/errors.py` returns 0 hits).
- [ ] `MCPRegistrationError` is defined in `the_one/mcp/errors.py` (verified via `grep -n "^class MCPRegistrationError" the_one/mcp/errors.py` returns 1 hit).
- [ ] `the_one/mcp/oauth/errors.py` imports `MCPAuthRequired` from `the_one.mcp.errors` and exports it as a module-level name (verified via `grep -n "from the_one.mcp.errors import MCPAuthRequired" the_one/mcp/oauth/errors.py` returns 1 hit; `python -c "from the_one.mcp.oauth.errors import MCPAuthRequired"` exits 0).
- [ ] `the_one/agent/core.py` lazy-import retired: lines 8-13 comment block GONE, the `_execute_tool` lazy-import statement GONE, replaced by a module-top `from the_one.mcp.errors import MCPAuthRequired`.
- [ ] `the_one/mcp/client.py` lazy-import retired: lines 41-45 comment block GONE, the `call_tool` lazy-import statement GONE, replaced by a module-top `from the_one.mcp.errors import MCPAuthRequired`.
- [ ] `the_one/mcp/__init__.py` re-exports `MCPAuthRequired` and `MCPRegistrationError` (both in the import block AND in `__all__`).
- [ ] `tests/test_imports.py` exists and asserts: importing `the_one.agent.core` in a fresh interpreter does NOT load any `the_one.mcp.oauth.*` module into `sys.modules`. Test runs subprocess-isolated.
- [ ] `MCPAuthRequired` continues to subclass `MCPClientError` directly (NOT `MCPOAuthError`) — locked by existing `tests/test_mcp_oauth_errors.py` which must continue to pass unmodified.
- [ ] `pytest tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_oauth_provider_factory.py tests/test_imports.py -v` is green.
- [ ] `tests/test_agent.py:657` lazy import is GONE; module-top `from the_one.mcp.errors import MCPAuthRequired` added to `tests/test_agent.py`'s import block (verified by `grep "from the_one.mcp.oauth.errors" tests/test_agent.py` returning 0 hits AND `grep "from the_one.mcp.errors import MCPAuthRequired" tests/test_agent.py` returning 1 hit).
- [ ] `pytest tests/test_agent.py tests/test_mcp_client.py -v` is green (regression — module-top import doesn't break agent/client construction).
- [ ] Full suite `pytest --tb=no -q` is green (no regressions across F1-F5).
- [ ] `ruff check the_one/ tests/` is clean.
- [ ] No `the_one.mcp.oauth` import is loaded transitively by `the_one.agent.core` (verified by the new `test_imports.py`).

## Verification Steps

How to confirm each criterion is met:

```bash
# Symbol relocation
grep -n "^class MCPAuthRequired" the_one/mcp/errors.py        # → 1 hit
grep -n "^class MCPAuthRequired" the_one/mcp/oauth/errors.py  # → 0 hits
grep -n "^class MCPRegistrationError" the_one/mcp/errors.py   # → 1 hit

# Re-export integrity
python -c "from the_one.mcp.errors import MCPAuthRequired, MCPRegistrationError, MCPClientError; assert issubclass(MCPAuthRequired, MCPClientError); assert issubclass(MCPRegistrationError, MCPClientError)"
python -c "from the_one.mcp.oauth.errors import MCPAuthRequired as A; from the_one.mcp.errors import MCPAuthRequired as B; assert A is B"
python -c "from the_one.mcp import MCPAuthRequired, MCPRegistrationError"

# Lazy-import retirement
grep -n "from the_one.mcp.oauth.errors import MCPAuthRequired" the_one/agent/core.py the_one/mcp/client.py  # → 0 hits each
grep -n "imported lazily" the_one/agent/core.py the_one/mcp/client.py  # → 0 hits each (comment blocks dropped)

# Import-graph regression
pytest tests/test_imports.py -v

# Existing test regression — locked by re-export
pytest tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py -v

# Agent + client regression — locked by module-top import working
pytest tests/test_agent.py tests/test_mcp_client.py -v

# Full suite + lint
pytest --tb=no -q
ruff check the_one/ tests/
```

## Implementation Guidance

The order matters — do these in sequence so the test suite stays green at each step.

1. **Move `MCPAuthRequired` definition into the canonical errors module.**
   - Open `the_one/mcp/errors.py`. Append the `MCPAuthRequired` class verbatim from `the_one/mcp/oauth/errors.py:52-80` AFTER `MCPCallError`. Preserve the docstring, the `# noqa: N818` comment, the `__init__` signature (`source_id: str, *, resource_metadata_url: str | None = None, consent_url: str | None = None`), and the body.
   - Critical: the docstring's "Inherits from MCPClientError (NOT MCPOAuthError)" sentence is still accurate at the new home. Keep it — the assertion in `tests/test_mcp_oauth_errors.py:53` (`assert issubclass(MCPAuthRequired, MCPClientError)`) locks the inheritance.
   - Update `the_one/mcp/errors.py`'s module docstring (lines 1-6) if needed — the current "Single base class with narrow subclasses" framing already accommodates the new class. Don't expand the docstring unnecessarily.

2. **Add `MCPRegistrationError` to the canonical errors module.**
   - In `the_one/mcp/errors.py`, append after `MCPAuthRequired`:
     ```python
     class MCPRegistrationError(MCPClientError):
         """Raised when an MCP source's tools cannot register cleanly into the agent's tool registry.

         Two failure modes:
           - Source-name prefix collision (two sources normalize to the same `mcp__{name}__` prefix)
           - Tool-name length exceeds the LLM provider tool-name ceiling (64 chars per OpenAI/Anthropic spec)

         L2's MCPToolProvider catches this per-tool (or per-source for collisions),
         logs WARNING, and skips the offending tool/source rather than failing
         the entire agent build (graceful-degrade, F6 §8).
         """
     ```
   - No `__init__` needed — call sites pass a single string message via `MCPRegistrationError(f"...")`.

3. **Replace the `MCPAuthRequired` definition in `the_one/mcp/oauth/errors.py` with a re-export.**
   - Open `the_one/mcp/oauth/errors.py`. Delete lines 52-80 (the entire `MCPAuthRequired` class definition).
   - Replace with a single re-export line. The cleanest placement is INSIDE the existing `from the_one.mcp.errors import MCPClientError` import at line 9 — extend it:
     ```python
     from the_one.mcp.errors import MCPAuthRequired, MCPClientError
     ```
   - Add `MCPAuthRequired` to a new `__all__` list at module scope so the re-export is explicit (the `oauth/errors.py` module currently has no `__all__`):
     ```python
     __all__ = [
         "MCPAuthRequired",
         "MCPOAuthError",
         "MCPOAuthDiscoveryError",
         "MCPOAuthRegistrationError",
         "MCPOAuthRefreshFailed",
     ]
     ```
   - The module docstring at lines 1-7 currently says "Mirrors the_one/mcp/errors.py's pattern" — keep that. Add a sentence at the end of the docstring: "MCPAuthRequired is canonical at the_one.mcp.errors as of F6 L0; re-exported here for back-compat with F5 callers."

4. **Retire the lazy import in `the_one/agent/core.py`.**
   - Open `the_one/agent/core.py`. Delete lines 8-13 (the entire F5-L4-comment block). The blank-line pattern at line 14 (the gap between the comment block and `# The agent can call this...`) should remain — keep one blank line as separator.
   - Find the existing module-top import block (lines 1-6 currently). Add `from the_one.mcp.errors import MCPAuthRequired` to that block.
   - Find `Agent._execute_tool` (around line 249-279). Delete the body's lazy import (line 251 — `from the_one.mcp.oauth.errors import MCPAuthRequired`) AND the immediately preceding comment line 250 (`# Lazy import — see module docstring at the top of this file.`). The function body's `try` block at line 253 stays exactly as-is.
   - Verify: `grep "MCPAuthRequired" the_one/agent/core.py` should show only the module-top import line and the line 257 `except MCPAuthRequired as e:` clause.

5. **Retire the lazy import in `the_one/mcp/client.py`.**
   - Open `the_one/mcp/client.py`. Delete lines 41-45 (the F5-L4-comment block). Keep one blank line as separator before the `if TYPE_CHECKING:` block at line 47.
   - Find the existing `from the_one.mcp.errors import (...)` block (lines 30-38). Add `MCPAuthRequired` to the imported names — preserve the alphabetical-sort convention used by the existing block (insert between `MCPArgumentError` and `MCPCallError` — alphabetical: `MCPArgumentError` < `MCPAuthRequired` < `MCPCallError`).
   - Find `MCPClient.call_tool` (around line 409-535). Delete the body's lazy import (line 436 — `from the_one.mcp.oauth.errors import MCPAuthRequired`) AND the immediately preceding comment line 435 (`# Lazy import — see module docstring near the import block.`). The cache-population logic at lines 438-441 stays exactly as-is.
   - Verify: `grep "MCPAuthRequired" the_one/mcp/client.py` should show only the module-top import (within the multi-line tuple), the line ~486 `raise MCPAuthRequired(...)` call, the line ~496 comment that mentions the name in the SDK-translation explanation, the line ~512 `raise MCPAuthRequired(...)` call, and the line ~526 `except MCPAuthRequired:` clause.

6. **Re-export from `the_one/mcp/__init__.py`.**
   - Open `the_one/mcp/__init__.py`. Find the import block at lines 45-53 (`from the_one.mcp.errors import (...)`). The block is alphabetically sorted: `MCPArgumentError, MCPCallError, MCPCapabilityMissing, MCPClientError, MCPConnectionError, MCPToolNotFoundError, MCPVersionMismatch`. Note: `MCPSandboxError` is NOT in this block today.
   - Insert `MCPAuthRequired` between `MCPArgumentError` and `MCPCallError` (alphabetical: 'r' in `MCPArgumentError` < 'u' in `MCPAuthRequired` < 'a' in `MCPCallError`).
   - Insert `MCPRegistrationError` between `MCPConnectionError` and `MCPToolNotFoundError` (alphabetical: 'C-o' < 'R' < 'T').
   - Find `__all__` at line 59. Add `"MCPAuthRequired"` and `"MCPRegistrationError"` preserving the existing block's order — match positional grouping with the import block (i.e. `MCPAuthRequired` near `MCPArgumentError`/`MCPCallError`; `MCPRegistrationError` near `MCPConnectionError`/`MCPToolNotFoundError`).

7. **Hoist the `tests/test_agent.py:657` lazy `MCPAuthRequired` import to module-top.**
   - Open `tests/test_agent.py`. Find the existing module-top import block at the top of the file. Add `from the_one.mcp.errors import MCPAuthRequired` to the imports (the canonical home is now `mcp.errors`, NOT `mcp.oauth.errors`).
   - Find `test_execute_tool_translates_mcp_auth_required_to_metadata` (around line 648). Delete the body's lazy import at line 657 (`from the_one.mcp.oauth.errors import MCPAuthRequired`). The `raise MCPAuthRequired(...)` at line 670 stays exactly as-is — the name now resolves through the module-top import.
   - Rationale: this is one of the F5 lazy-import sites that the leg's "retire F5 workarounds" framing covers. Hoisting to module-top demonstrates the canonical path works for test consumers and removes a stale F5-era pattern. 1-line addition + 1-line deletion.

8. **Create `tests/test_imports.py` with the chain-break regression test.**
   - The test must run in subprocess isolation because pytest's own import machinery contaminates `sys.modules` across tests (any prior test that imported `the_one.mcp.oauth.*` would pollute the snapshot).
   - Use `subprocess.run([sys.executable, "-c", ...])` with a small inline script that imports `the_one.agent.core` and asserts the absence of `the_one.mcp.oauth.*` keys in `sys.modules`. Capture stdout/stderr; fail the test on non-zero exit.
   - Keep the test minimal — one positive case (`import the_one.agent.core` does NOT load `the_one.mcp.oauth`) and one negative case (`import the_one.mcp.oauth` DOES load `the_one.mcp.oauth.storage` etc., to lock the contract that the chain still exists for explicit oauth-surface imports). Two tests, ~40 LOC.
   - Suggested skeleton:
     ```python
     """Import-graph regression tests.

     Locks the F6 L0 chain-break: importing the_one.agent.core does NOT
     transitively load the_one.mcp.oauth. The oauth surface is still
     reachable for callers who explicitly import it.

     Subprocess-isolated because pytest's own import machinery contaminates
     sys.modules; assertions on sys.modules under the same interpreter
     would see pollution from earlier-running tests.
     """
     import subprocess
     import sys


     def _run_in_subprocess(script: str) -> tuple[int, str, str]:
         result = subprocess.run(
             [sys.executable, "-c", script],
             capture_output=True,
             text=True,
             timeout=30,
         )
         return result.returncode, result.stdout, result.stderr


     def test_import_agent_core_does_not_load_mcp_oauth() -> None:
         """F6 L0: chain break — agent.core lazy-import retirement does NOT
         drag in mcp.oauth via the canonical-MCPAuthRequired-at-mcp.errors
         path.
         """
         script = (
             "import sys; "
             "import the_one.agent.core; "
             "leaked = sorted(k for k in sys.modules if k.startswith('the_one.mcp.oauth')); "
             "assert leaked == [], f'mcp.oauth leaked: {leaked}'; "
             "print('OK')"
         )
         rc, out, err = _run_in_subprocess(script)
         assert rc == 0, f"subprocess failed:\nstdout={out}\nstderr={err}"
         assert "OK" in out


     def test_import_mcp_oauth_still_loads_storage() -> None:
         """Negative: explicit oauth import still loads the storage chain.
         Locks that the chain exists for callers who legitimately need oauth
         surfaces (e.g. provider_factory).
         """
         script = (
             "import sys; "
             "import the_one.mcp.oauth; "
             "assert 'the_one.mcp.oauth.storage' in sys.modules; "
             "assert 'the_one.db.repositories' in sys.modules; "
             "print('OK')"
         )
         rc, out, err = _run_in_subprocess(script)
         assert rc == 0, f"subprocess failed:\nstdout={out}\nstderr={err}"
         assert "OK" in out
     ```

9. **Update flight log.**
   - Append a Leg Progress entry to `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` per the ARTIFACTS.md template (Started/Completed timestamps, Changes Made, Notes).
   - Note any deviations from this leg artifact in the Deviations section.

10. **Run lint + targeted test gate before signaling handoff.**
   - `ruff check the_one/ tests/`
   - `pytest tests/test_imports.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_client.py -v`
   - Then full suite: `pytest --tb=no -q` (timeout 5 min — fail fast on any hang).

## Edge Cases

- **Existing `from the_one.mcp.oauth.errors import MCPAuthRequired` callers (in tests, in `oauth/__init__.py:27`)**: the re-export at `oauth/errors.py` makes them resolve to the same class object as the canonical `the_one.mcp.errors.MCPAuthRequired`. `python -c "from the_one.mcp.oauth.errors import MCPAuthRequired as A; from the_one.mcp.errors import MCPAuthRequired as B; assert A is B"` confirms identity. Tests `tests/test_mcp_oauth_errors.py` and `tests/test_mcp_oauth_integration.py` pass without modification.
- **`isinstance` and `except` clauses**: Python's `isinstance(x, MCPAuthRequired)` and `except MCPAuthRequired:` use class identity, NOT class name. The re-export preserves identity → existing isinstance/except sites work unchanged.
- **Pickling / serialization across the move**: not exercised by any test today (the class is a control-flow signal, never pickled). Safe to move.
- **`__module__` attribute**: post-move, `MCPAuthRequired.__module__ == "the_one.mcp.errors"`. If any test asserts on `__module__` (none found at design time — `grep -rn '__module__' tests/` returned no relevant hits), update inline. If a future test asserts on `oauth.errors`, the canonical home is the right answer; update the test, not the home.
- **Type-checker / IDE imports**: Pyright/Pylance may flag unused-import warnings on the `oauth/errors.py` re-export until consumers are fixed up. The new `__all__` declaration suppresses the warning under most configurations, but **add `# noqa: F401` to the re-export line unconditionally** — some Pyright configurations don't honor `__all__` for unused-import suppression, and the noqa is one character of insurance against environment-dependent CI failures.
- **`MCPRegistrationError` subclassing `MCPClientError`**: the L2 consumer expects to catch `MCPRegistrationError` specifically (NOT `MCPClientError`) inside the per-tool wrap loop. Subclassing `MCPClientError` gives the right hierarchy — code that catches the broader `MCPClientError` (none today) would also catch `MCPRegistrationError`, which is the intended back-compat semantic.
- **Python ordering in `the_one/mcp/__init__.py`**: the file at lines 40-57 has `noqa: E402` markers on the imports because constants are declared first (per the F2 contract — `_PINNED_PROTOCOL_VERSION`, etc., come before imports). When extending the import tuple at lines 45-53, preserve the `noqa: E402` semantic — don't reorder the constants vs imports.

## Files Affected

- `the_one/mcp/errors.py` — `MCPAuthRequired` definition added (~30 LOC verbatim from `oauth/errors.py:52-80`); `MCPRegistrationError` added (~12 LOC).
- `the_one/mcp/oauth/errors.py` — `MCPAuthRequired` definition removed (~30 LOC); re-export added (~1 line); `__all__` added (~7 LOC); module docstring sentence added (~1 LOC).
- `the_one/agent/core.py` — comment block lines 8-13 dropped (~6 LOC); module-top import added (~1 LOC); lazy-import statement at line 251 dropped (~1 LOC); preceding comment at line 250 dropped (~1 LOC).
- `the_one/mcp/client.py` — comment block lines 41-45 dropped (~5 LOC); module-top import extended (~1 LOC inside existing tuple); lazy-import statement at line 436 dropped (~1 LOC); preceding comment at line 435 dropped (~1 LOC).
- `the_one/mcp/__init__.py` — import block at lines 45-53 extended with 2 names (~2 LOC inside tuple); `__all__` extended with 2 strings (~2 LOC).
- `tests/test_agent.py` — module-top import added (~1 LOC); lazy import at line 657 retired (~1 LOC).
- `tests/test_imports.py` (NEW) — ~40 LOC; 2 subprocess-isolated tests.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry appended (~15 LOC).

Net delta: ~+85 LOC production+tests; ~-15 LOC (comment-block + lazy-import-statement retirements) ≈ **~+70 LOC total**, matching the flight artifact's L0 estimate.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (each grep / pytest / ruff command produces the expected result)
- [ ] Tests passing (`pytest --tb=no -q` green; targeted suite per Verification Steps green)
- [ ] Lint clean (`ruff check the_one/ tests/`)
- [ ] Update `flight-log.md` with leg progress entry (Started/Completed timestamps, Changes Made, Notes)
- [ ] Set this leg's status to `landed` (in this file's header) — Flight Director (NOT the implementer) will flip to `completed` at flight commit time per the agentic-workflow protocol
- [ ] Do NOT check off this leg in flight.md yet — that happens at flight commit
- [ ] Do NOT commit — defer to flight-end commit per agentic-workflow protocol
- [ ] Signal `[HANDOFF:review-needed]` once all checklist items above are done

---

## Citation Audit

9 citations verified against current code at leg design time. All `OK`:

| Citation | Classification | Evidence |
|----------|----------------|----------|
| `the_one/mcp/errors.py:9` — `class MCPClientError(Exception)` | OK | Read directly; matches |
| `the_one/mcp/oauth/errors.py:52-80` — `class MCPAuthRequired(MCPClientError)` | OK | Read directly; lines 52-80 contain the verbatim class |
| `the_one/agent/core.py:8-13` — F5 lazy-import comment block | OK | Read directly; comment block spans lines 8-13 |
| `the_one/agent/core.py:251` — lazy `from the_one.mcp.oauth.errors import MCPAuthRequired` | OK | grep confirmed |
| `the_one/mcp/client.py:41-45` — F5 lazy-import comment block | OK | Read directly; comment block spans lines 41-45 |
| `the_one/mcp/client.py:436` — lazy `from the_one.mcp.oauth.errors import MCPAuthRequired` | OK | grep confirmed |
| `the_one/mcp/oauth/__init__.py:27, :34` — re-export + `__all__` entry | OK | Read directly; matches |
| `the_one/mcp/__init__.py:45-53` — error re-export block (alphabetically sorted; excludes `MCPAuthRequired` AND `MCPSandboxError` today) | OK | Read directly; matches; F6 L0 extends this block with `MCPAuthRequired` and `MCPRegistrationError` only |
| `tests/test_agent.py:657` — lazy `from the_one.mcp.oauth.errors import MCPAuthRequired` inside `test_execute_tool_translates_mcp_auth_required_to_metadata` | OK | grep confirmed; in-scope for this leg per cycle-1 review (hoist to module-top per step 7) |
