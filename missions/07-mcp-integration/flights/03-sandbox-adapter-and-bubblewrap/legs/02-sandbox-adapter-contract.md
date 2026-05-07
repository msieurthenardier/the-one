# Leg: 02-sandbox-adapter-contract

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Land the OS-agnostic `MCPSandbox` Protocol contract under `the_one/platform/sandbox/`: define `SandboxProfile` and `SpawnSpec` frozen dataclasses, declare the `MCPSandbox` runtime-checkable Protocol, paper-exercise the contract against documented capabilities of bubblewrap / sandbox-exec / AppContainer with citations in the module docstring, and add the `MCPSandboxError(MCPClientError)` subclass to `the_one/mcp/errors.py`. Stub `BubblewrapSandbox` raises `NotImplementedError` from `prepare_spawn` (L3 implements). Contract tests prove Protocol shape, frozen-dataclass invariants, and `SandboxProfile.from_dict` handling of missing/extra/type-mismatched keys.

## Context

- **Contract-only leg.** No real subprocess, no bwrap argv compilation, no integration with `connect_stdio` — just types, docstrings, and one new exception class. L3 implements `BubblewrapSandbox.prepare_spawn`; L4 wires it into `connect_stdio`. The Protocol shape and dataclass field names locked here become the F4-and-beyond contract surface, so getting them right matters more than getting them comprehensive.
- **Why before L3.** L3 needs the Protocol shape and dataclasses to import; the contract tests in this leg prove the shape is well-formed before L3 stakes implementation effort on it. The capability matrix's paper-exercise also forces the question "does the contract actually work for sandbox-exec / AppContainer?" before bwrap-shaped assumptions leak into the dataclass field set.
- **F3 contracts already published in CLAUDE.md / agents.md** (L1b). L2 implements the symbols those docs forward-reference. Contract drift risk: if L2 lands a slightly different shape than CLAUDE.md describes (e.g., field rename, parameter reorder), the docs become stale immediately. Mitigation: this leg's acceptance criteria require docs prose to match the implemented shape; if drift is found, fix the docs in this leg (NOT a follow-up).
- **Module placement (flight §8)**: `the_one/platform/sandbox/` is a peer of `the_one/platform/env.py`, `the_one/platform/pty.py`, `the_one/platform/paths.py`. The package directory contains:
  - `__init__.py` — re-exports `MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `BubblewrapSandbox`, and (for convenience) `MCPSandboxError`. Populates `__all__`.
  - `base.py` — Protocol + dataclasses + capability-matrix module docstring with citations.
  - `bubblewrap.py` — stub `BubblewrapSandbox` whose `prepare_spawn` raises `NotImplementedError("L3 implements")` for now; full implementation lands in L3.
- **`MCPSandboxError` canonical home (flight §6 + §8)**: `the_one/mcp/errors.py`, between `MCPConnectionError` and `MCPToolNotFoundError` (or at the end — placement is non-strict; `MCPClientError` subclasses are not strictly ordered). `the_one/platform/sandbox/__init__.py` re-exports for convenience but the canonical import path is `from the_one.mcp.errors import MCPSandboxError`. The error message catalog (flight §6) lives in the docstring as a reference but is consumed by L3 (which raises with those exact strings) — L2 only declares the class, no instances raised yet.
- **Capability matrix in `base.py` module docstring (flight §7)**: a 4×3 matrix (env-allowlist / FS scope / network policy / process supervision × bubblewrap / sandbox-exec / AppContainer) with one-line documented capability descriptions per cell, citations to bwrap(1), Apple Developer "App Sandbox Design Guide" / SBPL reference, Microsoft Learn "AppContainer Isolation" / "Job Objects" reference. The matrix is verbatim-portable from the flight log's Phase 1b Part C — no new research required, just copy-paste-and-format.
- **`agents.md` cross-reference**: a 1-line addition near `### the_one/platform/` (or wherever the platform sub-packages get their entry) pointing to `the_one/platform/sandbox/base.py` for the capability matrix. The actual content lives in `base.py`'s docstring; agents.md just gets a "sandbox capability matrix lives here" pointer so the doc index is searchable. **Decision for this leg**: only add the pointer if `agents.md` already has a `### the_one/platform/` section; otherwise defer the pointer-add to routine maintenance. Reading the file at design time will resolve the decision.
- **Per-leg lint gate**: `ruff check the_one/ tests/` clean before `[HANDOFF:review-needed]`.
- **Citation style**: per flight §Legs convention — anchor by symbol-name (`the_one/platform/sandbox/base.py::SandboxProfile.from_dict`), not by file:LINE.

## Inputs

What exists before this leg runs:

- L1a `completed` (dev container has `bwrap 0.11.0` + §10 privilege grants).
- L1b `completed` (`_validate_mcp_source_config` extended with `config.sandbox` sub-block; F3 contracts in CLAUDE.md + agents.md forward-referencing this leg's symbols).
- `the_one/platform/` package exists with `env.py`, `interpreter.py`, `paths.py`, `pty.py`, `shell.py`, `tempdirs.py`. `__init__.py` re-exports concrete names and populates `__all__`. Coding style: `from __future__ import annotations` at top; module docstring with `Public API:` section; design-decision citations (e.g., "F4 Decision 10").
- `the_one/mcp/errors.py` exists with `MCPClientError(Exception)` base + 6 subclasses. New subclasses follow the same pattern: small docstring; `__init__` with structured message-formatting if any state is captured.
- `the_one/agent/store.py::AgentConfigStore` is the canonical example of a `runtime_checkable` Protocol in this codebase — `@runtime_checkable` decorator above the class, `class AgentConfigStore(Protocol):` declaration, methods declared with `...` body.
- Frozen dataclass examples exist in `the_one/mcp/types.py` (`MCPTool`, `MCPToolResult`), `the_one/tools/_search_backends.py`, `the_one/tools/execution.py`, etc. — `@dataclass(frozen=True)` decorator pattern is in use. (`the_one/mcp/types.py` is the closest thematic reference — same package family.)
- Flight log Phase 1b Part C contains the citation-backed capability matrix (bubblewrap / sandbox-exec / AppContainer × env-allowlist / FS scope / network policy / process supervision) — verbatim source for L2's `base.py` module docstring.
- CLAUDE.md F3 section (added by L1b) names the symbols this leg lands; the docs prose reads "L2 lands the actual code; this entry documents the contract."

## Outputs

What exists after this leg completes:

- **`the_one/platform/sandbox/__init__.py`** — new file. Module docstring summarises the package. Re-exports `MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `BubblewrapSandbox`, `MCPSandboxError`. `__all__` lists all five.
- **`the_one/platform/sandbox/base.py`** — new file. Module docstring contains:
  - One-paragraph summary of the package's role (sandbox-spawn machinery for MCP stdio servers; cross-platform-ready; Linux-verified).
  - The 4×3 capability matrix table with citations. Use a simple ASCII / markdown-ish table inside a triple-quoted docstring; readers parse it visually, no programmatic consumption.
  - Forward-reference paragraph: "`MCPSandboxError` canonical home is `the_one/mcp/errors.py`; this package re-exports for convenience."
  - Note on the Linux-only-shipping caveat (per flight Adaptation Criteria): macOS sandbox-exec and Windows AppContainer backends are explicit follow-on work; the contract is shaped to accept them without rewrite (Windows-only fields `creation_flags`, `attribute_list` on `SpawnSpec`).

  Code:
  - `@dataclass(frozen=True)` `SandboxProfile` with fields per flight §12:
    ```python
    writable_paths: list[str] = field(default_factory=list)
    network_allowed: bool = False
    pid_unshare: bool = True
    ipc_unshare: bool = True
    uts_unshare: bool = True
    ```
    plus a `@classmethod from_dict(cls, data: dict[str, Any]) -> SandboxProfile` factory implementing the §12 contract:
    - Unknown keys ignored (debug-log via `logging.getLogger(__name__).debug(...)`)
    - Missing keys → dataclass field defaults
    - Type mismatch on a known field → `ValueError` at construction time with a small-model-friendly message naming the offending field and expected type
    - `writable_paths` list contents coerced to `str` via `str(...)`; non-string-coercible entries (e.g., `None`) raise `ValueError` (note: `str(None)` returns `"None"` which is technically coercible — the §12 spec says "non-string-coercible entries (e.g., `None`) raise `ValueError`"; honour the spec literally by treating `None` as non-coercible despite Python's permissive `str(None)`. Implementation: explicit `if entry is None: raise ValueError(...)` before the `str(...)` coerce).
  - `@dataclass(frozen=True)` `SpawnSpec` with fields per flight §11:
    ```python
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: str | None = None
    creation_flags: int = 0
    attribute_list: dict[str, Any] | None = None
    ```
  - `@runtime_checkable` `MCPSandbox` Protocol per flight §11:
    ```python
    @runtime_checkable
    class MCPSandbox(Protocol):
        @property
        def name(self) -> str: ...

        def prepare_spawn(
            self,
            profile: SandboxProfile,
            command: str,
            args: list[str],
            env: dict[str, str],
            cwd: str | None = None,
        ) -> SpawnSpec: ...
    ```

- **`the_one/platform/sandbox/bubblewrap.py`** — new file. Stub class:
  - Module docstring: "Bubblewrap-backed Linux sandbox. L2 stub; L3 implements `prepare_spawn`."
  - `from __future__ import annotations`.
  - `class BubblewrapSandbox:` (NOT `(MCPSandbox)` — Protocol satisfaction is structural; subclassing a `runtime_checkable` Protocol is unusual and unidiomatic. The class structurally satisfies the Protocol; tests verify via `isinstance(bw, MCPSandbox)`.)
  - `name: str = "bubblewrap"` class attribute (or `@property`); the simpler class-attribute form is fine since names don't change per-instance.
  - `def prepare_spawn(self, profile, command, args, env, cwd=None) -> SpawnSpec:` — body: `raise NotImplementedError("L3 implements BubblewrapSandbox.prepare_spawn")`. Type annotations on parameters and return type per Protocol shape.
  - Constructor: `def __init__(self) -> None:` with no body (`pass`) — L3 may add `shutil.which("bwrap")` validation here.

- **`the_one/mcp/errors.py`** extended:
  - New class `MCPSandboxError(MCPClientError)` placed after `MCPConnectionError` (or at the end of the file — non-strict ordering).
  - Docstring: "Local MCP sandbox setup failed (bwrap missing, writable_paths nonexistent, EPERM on unshare, container lacks privileges)."
  - No custom `__init__` — accepts a single message string per the existing pattern for non-state-bearing classes (e.g., `MCPConnectionError`). L3 raises with the §6 error catalog messages directly.

- **`tests/test_sandbox_contract.py`** — new test file. ~14 contract tests:
  1. `test_sandbox_profile_defaults` — `SandboxProfile()` produces strict-floor defaults: empty `writable_paths`, `network_allowed=False`, all three `*_unshare` flags True.
  2. `test_sandbox_profile_is_frozen` — attempting to mutate a field raises `dataclasses.FrozenInstanceError`.
  3. `test_sandbox_profile_from_dict_unknown_keys_ignored` — `from_dict({"writable_paths": [], "extra_key": "ignored"})` succeeds and produces defaults; debug log captured optionally.
  4. `test_sandbox_profile_from_dict_missing_keys_use_defaults` — `from_dict({})` produces strict-floor profile.
  5. `test_sandbox_profile_from_dict_type_mismatch_raises` — `from_dict({"network_allowed": "yes"})` raises `ValueError` with "network_allowed" + "bool" in the message; same for `writable_paths` not-a-list.
  5b. `test_sandbox_profile_from_dict_rejects_int_for_bool` — `from_dict({"network_allowed": 1})` raises `ValueError` (not implicitly coerced; locks the `isinstance(value, bool)` strictness invariant alignment with L1b's API validator).
  6. `test_sandbox_profile_from_dict_writable_paths_coerce_str` — `from_dict({"writable_paths": ["/data", 42]})` coerces `42` → `"42"` (the API validator already rejects non-string entries; `from_dict`'s coercion exists for direct programmatic construction).
  7. `test_sandbox_profile_from_dict_writable_paths_none_raises` — `from_dict({"writable_paths": [None]})` raises `ValueError` per §12's "non-string-coercible entries (e.g., `None`)" clause.
  8. `test_spawn_spec_is_frozen` — attempting to mutate a field raises `dataclasses.FrozenInstanceError`.
  9. `test_spawn_spec_default_windows_fields` — `SpawnSpec(command="/bin/echo", args=["hello"], env={})` produces `creation_flags=0`, `attribute_list=None`, `cwd=None`.
  10. `test_mcpsandbox_protocol_runtime_check_bubblewrap` — `isinstance(BubblewrapSandbox(), MCPSandbox)` is True (structural-satisfaction check).
  11. `test_mcpsandbox_protocol_runtime_check_negative_missing_prepare_spawn` — a class missing `prepare_spawn` (but having `name`) is NOT recognised as `MCPSandbox`.
  11b. `test_mcpsandbox_protocol_runtime_check_negative_missing_name` — a class missing `name` (but having `prepare_spawn`) is NOT recognised as `MCPSandbox`. Two-direction negative coverage proves both attributes are checked structurally.
  12. `test_bubblewrap_sandbox_prepare_spawn_not_implemented` — calling `BubblewrapSandbox().prepare_spawn(SandboxProfile(), "/bin/echo", [], {})` raises `NotImplementedError` with "L3 implements" in the message.
  13. `test_mcpsandbox_error_subclass_of_mcpclient_error` — `issubclass(MCPSandboxError, MCPClientError)` is True; canonical import works (`from the_one.mcp.errors import MCPSandboxError`); convenience re-export works (`from the_one.platform.sandbox import MCPSandboxError`).
  
  ~14 tests total — covers Protocol shape (positive + 2-direction negative), frozen invariants, `from_dict` factory exhaustively (including bool-vs-int strictness), NotImplementedError stub, error class hierarchy + import paths.

- **`the_one/platform/sandbox/` registered as a sub-package** so it's importable. No `agents.md` edit unless the file already has a `### the_one/platform/` section (resolve at implementation time per Decision in Context).

- **Flight artifacts**:
  - `flights/03-.../flight-log.md` gets `### L2 Sandbox Adapter Contract` under `## Leg Progress`.
  - `flights/03-.../flight.md` checkbox ticked under `### Legs`.
  - `legs/02-sandbox-adapter-contract.md` Status flipped to `completed`.

## Acceptance Criteria

- [ ] **Package created**: `the_one/platform/sandbox/__init__.py`, `base.py`, `bubblewrap.py` exist; `from the_one.platform.sandbox import MCPSandbox, SandboxProfile, SpawnSpec, BubblewrapSandbox, MCPSandboxError` succeeds in a Python REPL.
- [ ] **`SandboxProfile` matches §12 spec**: 5 fields with correct types and defaults; frozen dataclass; `from_dict` classmethod implements unknown-keys-ignored / missing-keys-defaults / type-mismatch-ValueError / `writable_paths` coercion semantics.
- [ ] **`SpawnSpec` matches §11 spec**: 6 fields with correct types and defaults; frozen dataclass.
- [ ] **`MCPSandbox` Protocol matches §11 spec**: `@runtime_checkable`; `name` property + `prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec` method.
- [ ] **`BubblewrapSandbox` stub satisfies Protocol**: `isinstance(BubblewrapSandbox(), MCPSandbox)` returns True; `prepare_spawn(...)` raises `NotImplementedError("L3 implements BubblewrapSandbox.prepare_spawn")`.
- [ ] **`MCPSandboxError(MCPClientError)` added to `the_one/mcp/errors.py`**: `issubclass(MCPSandboxError, MCPClientError)` is True; both `from the_one.mcp.errors import MCPSandboxError` AND `from the_one.platform.sandbox import MCPSandboxError` succeed (convenience re-export).
- [ ] **Capability matrix in `base.py` module docstring**: 4×3 matrix (env-allowlist / FS scope / network policy / process supervision × bubblewrap / sandbox-exec / AppContainer) with one-line capability descriptions per cell + citations to `bwrap(1)`, `@anthropic-ai/sandbox-runtime`, Apple Developer "App Sandbox Design Guide" + SBPL reference, Microsoft Learn "AppContainer Isolation" + "Job Objects". Verbatim-portable from flight log Phase 1b Part C. Column headers MUST use the binary names (`bubblewrap`, `sandbox-exec`, `AppContainer`) so the verification grep can match. Verifiable by `python -c 'from the_one.platform.sandbox import base; print(base.__doc__)' | grep -E 'bubblewrap|sandbox-exec|AppContainer'` returning at least 3 matches AND `... | grep -E 'bwrap\(1\)|sandbox-runtime|Apple Developer|Microsoft Learn'` returning at least 4 matches.
- [ ] **CLAUDE.md F3 contracts UNCHANGED unless drift is found**: if the implemented Protocol shape exactly matches the L1b CLAUDE.md description, no doc edit; if a field name / type / default differs, edit the CLAUDE.md F3 section (and `agents.md` F3 bullets) inline in this leg to keep them in sync.
- [ ] **agents.md sandbox-package pointer (conditional)**: if `the_one/agents.md` has a `### the_one/platform/` section, add a 1-line pointer "`the_one/platform/sandbox/` — sandbox-spawn machinery for MCP stdio servers (capability matrix in `base.py` module docstring; F3 contract in CLAUDE.md)." If no such section exists, defer to routine maintenance and document the deferral in the flight log.
- [ ] **`tests/test_sandbox_contract.py` green**: ~14 tests listed in Outputs, all passing. Total wall-clock <1s (no subprocess in any test).
- [ ] **No regression in F2/F1 tests**: `pytest tests/test_db_api.py::TestMCPSourceAPI tests/test_mcp_*.py -v` still green; the new `MCPSandboxError` import doesn't break any F2 import path.
- [ ] **Lint clean**: `ruff check the_one/ tests/` exits 0.
- [ ] **No source-code changes outside the contract surface**: `git status --porcelain` shows only `the_one/mcp/errors.py`, `the_one/platform/sandbox/__init__.py`, `the_one/platform/sandbox/base.py`, `the_one/platform/sandbox/bubblewrap.py`, `tests/test_sandbox_contract.py`, optionally `the_one/agents.md` (conditional pointer), optionally `CLAUDE.md` (drift-fix only), plus flight artifacts.
- [ ] **No `connect_stdio` integration in this leg**: `the_one/mcp/transports/stdio.py` is NOT modified — that's L4's surface. Verifiable by `git diff the_one/mcp/transports/stdio.py` returning empty.
- [ ] **Flight log updated**: `flight-log.md` gains `### L2 Sandbox Adapter Contract` under `## Leg Progress` per L1a/L1b format.
- [ ] **Leg status flipped to `completed`**; flight.md checkbox ticked.

## Verification Steps

```bash
cd /home/cprch/projects/the-one

# --- 1. Diff scope ---
git status --porcelain
# Expect: only the contract-surface paths (errors.py, platform/sandbox/*, test_sandbox_contract.py),
# optionally agents.md / CLAUDE.md if drift was fixed, plus the flight artifacts.

# --- 2. Imports work ---
docker compose exec -T the-one python -c "
from the_one.platform.sandbox import MCPSandbox, SandboxProfile, SpawnSpec, BubblewrapSandbox, MCPSandboxError
from the_one.mcp.errors import MCPSandboxError as canonical
assert MCPSandboxError is canonical, 'Convenience re-export must alias the canonical class'
print('imports ok')
"
# Expect: prints 'imports ok'.

# --- 3. Contract tests ---
docker compose exec -T the-one python -m pytest tests/test_sandbox_contract.py -v
# Expect: ~13 passed; <1s wall clock.

# --- 4. F2 stdio tests still pass (no MCPSandboxError import-path break) ---
docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py tests/test_db_api.py::TestMCPSourceAPI -v
# Expect: all green; no errors loading test modules.

# --- 5. Lint ---
docker compose exec -T the-one ruff check the_one/ tests/
# Expect: All checks passed.

# --- 6. Capability matrix presence ---
docker compose exec -T the-one python -c "
from the_one.platform.sandbox import base
doc = base.__doc__ or ''
for backend in ('bubblewrap', 'sandbox-exec', 'AppContainer'):
    assert backend in doc, f'Capability matrix missing {backend}'
for citation in ('bwrap(1)', 'Apple Developer', 'Microsoft Learn'):
    assert citation in doc, f'Citation missing: {citation}'
print('capability matrix ok')
"
# Expect: prints 'capability matrix ok'.

# --- 7. Protocol structural check (BubblewrapSandbox satisfies MCPSandbox) ---
docker compose exec -T the-one python -c "
from the_one.platform.sandbox import MCPSandbox, BubblewrapSandbox
assert isinstance(BubblewrapSandbox(), MCPSandbox), 'BubblewrapSandbox must satisfy MCPSandbox Protocol'
print('protocol ok')
"
# Expect: prints 'protocol ok'.

# --- 8. Stub raises NotImplementedError ---
docker compose exec -T the-one python -c "
from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile
try:
    BubblewrapSandbox().prepare_spawn(SandboxProfile(), '/bin/echo', [], {})
    print('FAIL: expected NotImplementedError')
except NotImplementedError as e:
    assert 'L3 implements' in str(e), f'Unexpected message: {e}'
    print('stub ok')
"
# Expect: prints 'stub ok'.

# --- 9. F3 docs forward-references in CLAUDE.md still resolve to existing symbols ---
grep -E 'MCPSandbox|SandboxProfile|SpawnSpec|MCPSandboxError' CLAUDE.md | head -3
docker compose exec -T the-one python -c "
from the_one.platform.sandbox import MCPSandbox, SandboxProfile, SpawnSpec, MCPSandboxError
print('all four symbols importable')
"
# Expect: 4 symbols importable; CLAUDE.md prose names remain accurate (no rename drift).
```

If any assertion fails:
1. Do NOT signal `[COMPLETE:leg]`.
2. Capture failing output.
3. Diagnose: most likely (a) missing `@runtime_checkable` on the Protocol → `isinstance` check fails, (b) `BubblewrapSandbox.name` is missing → structural check fails, (c) `from_dict` raises on empty input due to over-strict isinstance check, (d) `writable_paths` coercion accepts `None` (spec says reject), (e) ruff flags an unused import in the new files.

## Implementation Guidance

1. **Create `the_one/platform/sandbox/` directory** with three files. Use `from __future__ import annotations` at the top of each. Module docstrings follow the `the_one/platform/env.py` style — `"""<one-line summary>.\n\n<context paragraph(s)>.\n"""`.

2. **`base.py` — capability matrix in module docstring**. Verbatim-portable from flight log Phase 1b Part C. Format as a markdown-like table inside a triple-quoted docstring. Rows: env-allowlist, FS scope, network policy, process supervision. Column headers MUST be the binary names: `bubblewrap` (Linux), `sandbox-exec` (macOS), `AppContainer` (Windows) — those literal strings, so the AC's grep verification matches. Each cell: one-sentence description of the documented capability. Below the matrix, three citation footnotes (each citation must be present in literal form for the AC's second grep to match):
   - bubblewrap: `bwrap(1)` man page; `@anthropic-ai/sandbox-runtime` reference
   - sandbox-exec: Apple Developer documentation "App Sandbox Design Guide"; `sandbox-exec(1)` man page; SBPL (Sandbox Profile Language) reference
   - AppContainer: Microsoft Learn "AppContainer Isolation"; Microsoft Learn "Job Objects" reference

3. **`base.py` — code**:

   ```python
   from __future__ import annotations

   import logging
   from dataclasses import dataclass, field
   from typing import Any, Protocol, runtime_checkable

   _logger = logging.getLogger(__name__)


   @dataclass(frozen=True)
   class SandboxProfile:
       """Sandbox policy for a local MCP server. F3 §12."""
       writable_paths: list[str] = field(default_factory=list)
       network_allowed: bool = False
       pid_unshare: bool = True
       ipc_unshare: bool = True
       uts_unshare: bool = True

       @classmethod
       def from_dict(cls, data: dict[str, Any]) -> SandboxProfile:
           """Construct from a plain dict (e.g., MCPSource.config['sandbox']).

           Per §12: unknown keys ignored (debug-logged); missing keys
           default to dataclass defaults; type mismatch on a known field
           raises ValueError; writable_paths entries coerced to str.
           Non-string-coercible entries (e.g., None) raise ValueError.
           """
           known = {"writable_paths", "network_allowed", "pid_unshare", "ipc_unshare", "uts_unshare"}
           extra = set(data) - known
           if extra:
               _logger.debug("SandboxProfile.from_dict ignoring unknown keys: %s", sorted(extra))

           writable_paths_raw = data.get("writable_paths")
           if writable_paths_raw is None:
               writable_paths: list[str] = []
           elif isinstance(writable_paths_raw, list):
               writable_paths = []
               for entry in writable_paths_raw:
                   if entry is None:
                       raise ValueError(
                           "SandboxProfile.writable_paths: None is not a valid path entry."
                       )
                   writable_paths.append(str(entry))
           else:
               raise ValueError(
                   f"SandboxProfile.writable_paths must be a list, got {type(writable_paths_raw).__name__}."
               )

           network_allowed = data.get("network_allowed", False)
           if not isinstance(network_allowed, bool):
               raise ValueError(
                   f"SandboxProfile.network_allowed must be a bool, got {type(network_allowed).__name__}."
               )

           pid_unshare = data.get("pid_unshare", True)
           if not isinstance(pid_unshare, bool):
               raise ValueError(
                   f"SandboxProfile.pid_unshare must be a bool, got {type(pid_unshare).__name__}."
               )

           ipc_unshare = data.get("ipc_unshare", True)
           if not isinstance(ipc_unshare, bool):
               raise ValueError(
                   f"SandboxProfile.ipc_unshare must be a bool, got {type(ipc_unshare).__name__}."
               )

           uts_unshare = data.get("uts_unshare", True)
           if not isinstance(uts_unshare, bool):
               raise ValueError(
                   f"SandboxProfile.uts_unshare must be a bool, got {type(uts_unshare).__name__}."
               )

           return cls(
               writable_paths=writable_paths,
               network_allowed=network_allowed,
               pid_unshare=pid_unshare,
               ipc_unshare=ipc_unshare,
               uts_unshare=uts_unshare,
           )


   @dataclass(frozen=True)
   class SpawnSpec:
       """Process-creation parameters spanning Linux/macOS/Windows backends. F3 §11."""
       command: str
       args: list[str]
       env: dict[str, str]
       cwd: str | None = None
       creation_flags: int = 0  # Windows AppContainer; ignored on Linux/macOS.
       attribute_list: dict[str, Any] | None = None  # Windows AppContainer; ignored on Linux/macOS.


   @runtime_checkable
   class MCPSandbox(Protocol):
       """OS-agnostic adapter contract for sandboxing MCP server subprocesses. F3 §11."""

       @property
       def name(self) -> str: ...

       def prepare_spawn(
           self,
           profile: SandboxProfile,
           command: str,
           args: list[str],
           env: dict[str, str],
           cwd: str | None = None,
       ) -> SpawnSpec: ...
   ```

4. **`bubblewrap.py` — stub**:

   ```python
   """Bubblewrap-backed Linux sandbox. L2 stub; L3 implements prepare_spawn."""

   from __future__ import annotations

   from the_one.platform.sandbox.base import SandboxProfile, SpawnSpec


   class BubblewrapSandbox:
       """Linux sandbox backend using bubblewrap (bwrap). F3 §8 + §11."""

       name: str = "bubblewrap"

       def __init__(self) -> None:
           """L2 stub. L3 may add `shutil.which('bwrap')` validation here."""

       def prepare_spawn(
           self,
           profile: SandboxProfile,
           command: str,
           args: list[str],
           env: dict[str, str],
           cwd: str | None = None,
       ) -> SpawnSpec:
           raise NotImplementedError("L3 implements BubblewrapSandbox.prepare_spawn")
   ```

5. **`__init__.py` — re-exports**:

   ```python
   """OS-level sandbox layer for MCP server subprocesses (F3).

   Public API:
       MCPSandbox: Protocol contract (runtime_checkable)
       SandboxProfile: frozen dataclass (sandbox policy per source)
       SpawnSpec: frozen dataclass (process-creation parameters)
       BubblewrapSandbox: Linux backend (L2 stub, L3 implements)
       MCPSandboxError: exception (canonical home: the_one/mcp/errors.py)

   See base.py module docstring for the cross-platform capability matrix.
   """

   from __future__ import annotations

   from the_one.mcp.errors import MCPSandboxError
   from the_one.platform.sandbox.base import MCPSandbox, SandboxProfile, SpawnSpec
   from the_one.platform.sandbox.bubblewrap import BubblewrapSandbox

   __all__ = [
       "BubblewrapSandbox",
       "MCPSandbox",
       "MCPSandboxError",
       "SandboxProfile",
       "SpawnSpec",
   ]
   ```

6. **`the_one/mcp/errors.py` — append `MCPSandboxError`**. Place after `MCPConnectionError` for thematic grouping (both are setup/transport-tier errors). Pattern: bare class with docstring, no `__init__`, accepts a single string message.

   ```python
   class MCPSandboxError(MCPClientError):
       """Local MCP sandbox setup failed: bwrap missing, writable_paths nonexistent,
       EPERM on unshare, container lacks privileges, or other pre-spawn failure
       (F3 §6).
       """
   ```

7. **`tests/test_sandbox_contract.py`** — write the ~13 contract tests listed in Outputs. Style: pytest function tests (NOT class-based — there's no shared fixture). Synchronous (no async needed; no real subprocess). Use `pytest.raises(ValueError)` / `pytest.raises(NotImplementedError)` / `pytest.raises(dataclasses.FrozenInstanceError)`. Keep each test focused on one assertion.

8. **`agents.md` cross-reference**: read the file at implementation time. If a `### the_one/platform/` (or `### the_one/platform` without trailing slash) section exists, add a 1-line pointer entry. If not, document the deferral in the flight log entry instead.

9. **CLAUDE.md drift check**: re-read the CLAUDE.md F3 section (added in L1b) and confirm the implemented shape matches. Field names: `writable_paths`, `network_allowed`, `pid_unshare`, `ipc_unshare`, `uts_unshare`, `creation_flags`, `attribute_list`. Method name: `prepare_spawn`. Type annotations match. Defaults match. If any drift is found, fix CLAUDE.md (and `agents.md` F3 bullets) inline. If no drift, no edit.

10. **Run all Verification Steps** before signalling `[HANDOFF:review-needed]`. Lint must be clean.

## Edge Cases

- **`bool` is a subclass of `int`**: `isinstance(True, int)` is True. The `from_dict` factory uses `isinstance(value, bool)` (NOT `int`) for `network_allowed` / `pid_unshare` / `ipc_unshare` / `uts_unshare`. A JSON `1` would fail with ValueError. Matches L1b's API-validator strictness.
- **`SandboxProfile.from_dict({})`**: returns a strict-floor profile (empty writable_paths, all-default flags). Empty dict is valid input — both fields are individually optional.
- **`writable_paths` list with mixed types**: `from_dict({"writable_paths": ["/data", 42, 3.14]})` coerces `42` → `"42"` and `3.14` → `"3.14"`. The API validator (L1b) rejects non-string entries with 422 BEFORE `from_dict` ever sees them in the production flow; `from_dict`'s coercion is a safety net for direct programmatic construction (e.g., from a YAML config that round-trips ints).
- **`writable_paths` list with `None`**: explicitly rejected per §12 ("non-string-coercible entries (e.g., `None`) raise ValueError"). Implementation raises BEFORE coercing — `if entry is None: raise ValueError(...)`. Despite Python's `str(None) == "None"`, `None`-as-a-path is meaningless and likely a bug; reject it.
- **`SpawnSpec` mutability**: `frozen=True` makes attribute assignment raise `FrozenInstanceError`. List/dict fields (`args`, `env`, `attribute_list`) are still mutable internally — `spec.args.append("X")` succeeds. This is a Python `dataclasses(frozen=True)` quirk; not L2's bug. If a future leg needs deep immutability, switch to `tuple` / `frozendict`. Out of scope here.
- **Protocol structural check on a class with `prepare_spawn` but wrong signature**: `runtime_checkable` Protocols only check method NAMES, not signatures. `isinstance(BadSandbox(), MCPSandbox)` returns True even if `BadSandbox.prepare_spawn` takes wrong args. This is a Python typing limitation; mypy / pyright catch the mismatch statically. Tests assert structural-yes for `BubblewrapSandbox` and structural-no for a class missing `prepare_spawn` entirely. Out-of-band signature checking is L3's surface (its real implementation will fail-fast on wrong arg shapes).
- **Capability matrix drift**: future spec revisions (bwrap upgrades, sandbox-exec deprecation, AppContainer evolution) may invalidate the matrix entries. The matrix is a snapshot at L2-design-time; not a runtime contract. If a future routine-maintenance pass finds drift, the fix is to edit `base.py`'s docstring — no code changes needed.
- **No `agents.md` `### the_one/platform/` section**: don't fabricate one. The pointer entry is conditional. Document the deferral in the flight log: "agents.md `### the_one/platform/` section absent at L2 implementation time; sandbox-package pointer deferred to routine maintenance."

## Files Affected

- `the_one/platform/sandbox/__init__.py` — NEW
- `the_one/platform/sandbox/base.py` — NEW (Protocol + dataclasses + capability matrix)
- `the_one/platform/sandbox/bubblewrap.py` — NEW (stub class)
- `the_one/mcp/errors.py` — APPEND `MCPSandboxError(MCPClientError)`
- `tests/test_sandbox_contract.py` — NEW (~13 contract tests)
- `the_one/agents.md` — CONDITIONAL (pointer to sandbox package, only if `### the_one/platform/` section exists)
- `CLAUDE.md` — CONDITIONAL (drift-fix only, if implemented shape diverges from L1b's prose)
- `missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight-log.md` — APPEND `### L2 Sandbox Adapter Contract`
- `missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight.md` — tick L2 checkbox
- `missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/legs/02-sandbox-adapter-contract.md` — flip Status

**Explicitly NOT modified by this leg**: `the_one/mcp/transports/stdio.py` (L4's surface), `the_one/interfaces/web/api.py` (L1b's surface, already done), `tests/conftest.py` (L4 adds `mcp_fixture_sandbox_profile`), `tests/fixtures/mcp/hello_server.py` (L5a), JS, Dockerfile, docker-compose.yml, Makefile, pyproject.toml.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `the_one/platform/sandbox/` package created with `__init__.py`, `base.py`, `bubblewrap.py`
- [ ] `MCPSandboxError` added to `the_one/mcp/errors.py`; convenience re-export in sandbox `__init__.py` works
- [ ] Capability matrix in `base.py` module docstring with citations
- [ ] `tests/test_sandbox_contract.py` ~14 tests all pass
- [ ] F2/F1 tests still green (no import-path break)
- [ ] `ruff check the_one/ tests/` exit 0
- [ ] CLAUDE.md F3 contracts: drift checked, fixed inline if needed (else unchanged)
- [ ] agents.md sandbox-package pointer added if `### the_one/platform/` section exists; deferred otherwise (with note in flight log)
- [ ] `git status --porcelain` shows only the contract surface paths + flight artifacts; no `connect_stdio` change, no API change, no JS change
- [ ] Update flight-log.md with `### L2 Sandbox Adapter Contract` under `## Leg Progress`
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end
