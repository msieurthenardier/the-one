# Flight Log: Sandbox Seam + Built-in Tool Retrofit

**Flight**: [Sandbox Seam + Built-in Tool Retrofit](flight.md)

## Summary
Flight landed. All 5 legs completed and reviewed; full suite + 7 `requires_bwrap`
containment tests green; ruff gate clean. Executed via `/agentic-workflow` (batched:
per-leg design reviews, implementation across all autonomous legs, single Reviewer
pass + flight-level commit). Final gate: `pytest --timeout 60` → 3007 passed, 4
skipped, 552 deselected; `pytest -m requires_bwrap --timeout 120` → 7 passed.

---

### Flight Director Notes
- **Phase file loaded**: `.flightops/agent-crews/leg-execution.md` — validated (Crew,
  Interaction Protocol, Prompts present). Developer=Sonnet, Reviewer=Haiku.
- **Branch**: `flight/01-sandbox-seam-builtin-retrofit` created from
  `plan/mission-14-sandbox` HEAD (carries the M14 planning artifacts not yet on main).
- **Flight status**: `ready` → `in-flight`.
- **Execution model**: 5 autonomous legs, no HAT/interactive legs. Per-leg design
  review; implementation batched (no per-leg commit); single Reviewer pass + commit
  at flight end (Phase 2d).
- **Flight-level code review passed** (Reviewer: Sonnet). One non-blocking finding
  was flagged: a potential unused `BubblewrapSandbox` import in `platform/shell.py`
  and `platform/interpreter.py`. Verified via `ruff check` — no unused import
  exists in the working tree (the function-level `from the_one.platform.sandbox
  import BubblewrapSandbox, get_sandbox_backend` import is live; the finding was
  pre-empted during Leg 4 implementation). No blocking findings; ruff gate clean;
  flight cleared for commit.
- **Leg 1 design review** (1 cycle): Developer returned *approve with changes* —
  two high-severity gaps: (a) two tests assert the old class name via
  `type(e).__name__` rendered output (`test_mcp_tool_provider.py`,
  `test_mcp_stdio_test_connect.py`) and would break; (b) `agents.md` +
  `mcp/README.md` carry symbol refs the `.py`-only acceptance grep misses. Both
  incorporated into the leg (new acceptance criteria + edge cases + Files Affected);
  minor `__init__.py` line-range fix applied. **Decision:** skipped a second
  design-review cycle — the changes were the reviewer's own findings, each backed by
  file/line facts it had already grep-verified against the code, so a re-review would
  only re-confirm. Leg → `ready`. `[HANDOFF:review-needed]`.

---

## Leg Progress

### Leg 1: rename-sandbox-abstraction — landed

- **Status**: `ready` → `in-flight` → `landed`
- **What changed**: Pure symbol rename — `MCPSandbox` → `ToolSandbox` and
  `MCPSandboxError` → `SandboxError` — across the entire codebase.
- **File count**: 22 files modified (10 source files, 9 test files, 2 doc files,
  1 leg artifact).
  - Source: `the_one/mcp/errors.py`, `the_one/platform/sandbox/base.py`,
    `the_one/platform/sandbox/__init__.py`, `the_one/platform/sandbox/bubblewrap.py`,
    `the_one/mcp/client.py`, `the_one/mcp/transports/stdio.py`,
    `the_one/mcp/_tool.py`, `the_one/mcp/_tool_provider.py`,
    `the_one/interfaces/web/api.py`.
  - Tests: `tests/test_sandbox_contract.py`, `tests/test_sandbox_bubblewrap.py`,
    `tests/test_mcp_stdio_sandbox.py`, `tests/test_mcp_stdio_error_translation.py`,
    `tests/test_mcp_pool.py`, `tests/test_mcp_client.py`,
    `tests/test_mcp_tool_provider.py`, `tests/test_mcp_stdio_test_connect.py`,
    `tests/test_mcp_sandbox_integration.py`.
  - Docs: `the_one/agents.md`, `the_one/mcp/README.md`.
- **Edge cases handled**:
  - `MCPClientError` hierarchy and `client.py:511` teardown catch preserved intact.
  - Message-string literals in `stdio.py` (`"MCP sandbox setup failed: …"`) left as-is
    (prose, not symbol references).
  - Two class-name-as-rendered-string assertions updated to `"SandboxError"` in
    `test_mcp_tool_provider.py` and `test_mcp_stdio_test_connect.py`.
  - `SandboxError` stays in `the_one/mcp/errors.py` — no relocation.
  - Import sort fix applied in `_tool.py` (ruff I001).
- **Test results**: 2990 passed, 4 skipped, 548 deselected (live/browser). One
  pre-existing failure in `test_connectors_e2e.py::test_e2e_full_lifecycle`
  (pool reaping assertion, no sandbox involvement — confirmed failing on clean tree).
- **Ruff results**: `ruff check .` — all checks passed; `ruff format --check .` —
  435 files already formatted.
- **Anomaly**: None.

---

### Leg 2: sandbox-backend-factory — landed

- **Status**: `ready` → `in-flight` → `landed`
- **What changed**: Built the seam machinery without wiring any spawn site.
  - `the_one/platform/sandbox/passthrough.py` (new) — `PassthroughSandbox` no-op backend;
    structurally satisfies `ToolSandbox`; `name == "passthrough"`; `prepare_spawn` returns
    `SpawnSpec(command, args, env, cwd)` with defensive copies; all profile fields silently ignored.
  - `the_one/platform/sandbox/factory.py` (new) — `get_sandbox_backend()` selection factory;
    module-level `_LOGGED: set[str]` log-once guard; `_reset_selection_log_state()` reset hook for
    tests; `_sandbox_disabled_for_tests()` predicate mirroring the MCP stdio copy (leg 3 reconciles).
    Imports `sys` and `shutil` at module level so tests can monkeypatch via object form.
  - `the_one/platform/sandbox/base.py` — `SandboxProfile` gains `readonly_overlay_paths: list[str]`
    (defaults `[]`, parsed by `from_dict` with same coercion/None-rejection as `writable_paths`) and
    `home: str | None = None` (programmatic-only; `from_dict` intentionally omits it, with a docstring
    note explaining the §13 "operators cannot set HOME" contract). `known` set updated accordingly.
  - `the_one/platform/sandbox/bubblewrap.py` — `--ro-bind PATH PATH` overlay loop added AFTER the
    writable `--bind` loop and before `--proc`/`--dev`; HOME set from `profile.home if profile.home
    is not None else "/tmp"`; class/method docstrings corrected.
  - `the_one/platform/sandbox/__init__.py` — `PassthroughSandbox` and `get_sandbox_backend` added to
    imports and `__all__`; module docstring updated.
  - `the_one/agents.md` — HOME-policy description updated: "HOME defaults to `/tmp`; callers with a
    real workspace pass `profile.home` to override — operators still cannot override HOME via the
    kv-table."
  - `tests/test_sandbox_factory.py` (new) — 12 tests: selection matrix (4 branches), single-flag
    no-bypass, passthrough-never-raises, log-once (4 tests covering all branches), backend.name.
  - `tests/test_sandbox_bubblewrap.py` — stale `..._home_override_unconditional` docstring clarified
    ("with the default profile (`home=None`), HOME is still forced to `/tmp`"); 3 new tests:
    overlay argv ordering (--ro-bind after --bind, before --proc), profile-driven HOME, default-profile
    HOME-still-tmp regression.
  - `tests/test_sandbox_contract.py` — `PassthroughSandbox` added to Protocol-conformance check.
- **DD3 refinement (accepted, recorded per leg spec)**: the one-time unsandboxed WARNING lives in
  `get_sandbox_backend()` in `factory.py`, NOT inside `PassthroughSandbox.prepare_spawn` as DD3
  literally phrases it. The factory is the single selection locus and knows the *reason*
  (non-Linux vs bwrap-missing vs test-bypass) which determines WARNING vs INFO level. This avoids
  per-instance global state on the backend class. Observably equivalent to DD3 (one-time WARNING when
  unsandboxed on Linux without bwrap).
- **Verification smoke checks**:
  - `PassthroughSandbox isinstance ToolSandbox`: PASS
  - `get_sandbox_backend()` returns `BubblewrapSandbox` in container (Linux + bwrap present): PASS
- **Test results**: Targeted (47 tests) — all passed. Full default suite — 3007 passed, 4 skipped,
  547 deselected. One pre-existing failure (`test_connectors_e2e.py::test_e2e_full_lifecycle`,
  pool reaping assertion) — absent from this run, consistent with earlier observations.
- **Ruff results**: `ruff check .` — all checks passed; `ruff format --check .` — 333 files
  formatted (factory.py needed one reformat after initial write).
- **Anomaly**: None.

---

## Decisions

### Leg 2 design review (1 cycle) — DD3 WARNING locus refined
**Context**: DD3 phrases the one-time unsandboxed WARNING as living inside
`PassthroughSandbox`. **Decision**: place it in `get_sandbox_backend()` instead —
the factory is the single selection locus, knows the *reason* (which sets WARNING vs
INFO level), and this avoids per-instance global state on the backend. Observably
equivalent (one-time WARNING when unsandboxed). **Impact**: cleaner; DD3 noted as
refined, not violated. The implementing Developer records this in the leg's flight-log
entry.

Leg 2 design review returned *approve with changes*: medium issues — (a) monkeypatch
guidance (use object form `monkeypatch.setattr(factory_module.sys, "platform", …)`,
matching existing test pattern), (b) `agents.md` HOME description goes stale once
`profile.home` exists → added `agents.md` to Files Affected. Plus low/suggestion
fixes: clarify stale `..._home_override_unconditional` test docstring, document why
`from_dict` omits `home`, promote `PassthroughSandbox` contract-test coverage to
required, note `which()` per-call cost is acceptable. All incorporated. **Decision**:
skipped a second design-review cycle — same rationale as leg 1 (all changes were the
reviewer's own code-verified findings). Leg → `ready`. `[HANDOFF:review-needed]`.

### Leg 3: mcp-via-factory — landed

- **Status**: `ready` → `in-flight` → `landed`
- **What changed**: Retrofitted the MCP stdio spawn site to obtain its sandbox backend
  from `get_sandbox_backend()` instead of constructing `BubblewrapSandbox()` directly.
  - `the_one/mcp/transports/stdio.py` — removed `_sandbox_disabled_for_tests()` (24 lines);
    removed `import os` (no longer needed); added `get_sandbox_backend`, `ToolSandbox` to
    the `from the_one.platform.sandbox import ...` line (split for line-length);
    rewrote `_build_stdio_params` to call `get_sandbox_backend()`, always run
    `SandboxProfile.from_dict`, and return `(params, backend)`; updated `connect_stdio` and
    `_open_stdio_transport_stack` to unpack `params, backend = _build_stdio_params(source)`
    and derive `sandboxed = isinstance(backend, BubblewrapSandbox)`; updated all related
    docstrings and comments (module docstring, function docstring, inline comments).
  - `the_one/platform/sandbox/factory.py` — tightened `get_sandbox_backend()` return
    annotation from `object` to `"ToolSandbox"` (imported under `TYPE_CHECKING` to avoid
    circular-import risk; pure readability/honesty win, no CI gate).
  - `tests/test_mcp_stdio_sandbox.py` — rewrote module docstring (new factory-based
    contract); reworked 7 of 9 tests per the per-test contract:
    - §1, §4, §5: inject via `patch.object(stdio_module, "get_sandbox_backend",
      lambda: BubblewrapSandbox())`; assert `params.command == "bwrap"`. Dropped
      `sandbox_cls = MagicMock()` + `assert_called_once_with()` (unachievable post-retrofit).
    - §2: replaced with a `_RecordingBackend` wrapper that captures the profile arg.
    - §3: let real factory run under both flags; dropped vacuous
      `patch.object(stdio_module, "BubblewrapSandbox", ...)`; assert `params.command == "/bin/echo"`.
    - §6: **inverted** — renamed `test_connect_stdio_routes_to_passthrough_when_bwrap_missing`;
      patches `factory_module.shutil.which → None`; asserts NO `SandboxError` raised and
      `params.command == "/bin/echo"`. The construction-time raise remains unit-tested in
      `test_sandbox_bubblewrap.py`.
    - §7: added `monkeypatch.setattr(factory_module.shutil, "which", ...)` alongside the
      existing `bwrap_module.shutil.which` patch so the factory reliably selects bubblewrap
      regardless of host; preserved `HOME == "/tmp"` assertion.
    - §8 (real subprocess), §9 (validation error): no change needed.
  - `tests/conftest.py` — repointed line-29 docstring from
    `the_one.mcp.transports.stdio._sandbox_disabled_for_tests` to
    `the_one.platform.sandbox.factory._sandbox_disabled_for_tests`.
- **`sandboxed` semantics shift**: Previously `sandboxed == not bypassed`. Now
  `sandboxed == isinstance(backend, BubblewrapSandbox)`. They agree on Linux+bwrap
  (both True) and under bypass (both False). They diverge only in the new reachable
  state — bwrap-missing/non-Linux — where the old code couldn't reach this point
  (it raised at `BubblewrapSandbox()`) and the new code correctly treats passthrough
  as not-bwrap-wrapped (False), taking the SDK-default-errlog branch. This is the
  intended behavior.
- **Test results**: Targeted (28 tests) — all passed. `@requires_bwrap` MCP integration
  + pool tests — 2 passed, 36 deselected. Full default suite — 3007 passed, 4 skipped,
  547 deselected. Pre-existing failure (`test_connectors_e2e.py::test_e2e_full_lifecycle`)
  absent from this run (consistent pattern).
- **Ruff results**: `ruff check .` — all checks passed; `ruff format --check .` — 333 files
  already formatted.
- **Anomaly**: None. Initial ruff run caught three fixable issues (I001 import order,
  F401 unused `PassthroughSandbox` import, E501 line-too-long) — all fixed before the
  final suite run.

---

### Leg 3 design review (1 cycle) — test-injection reframed around the factory's lazy import
**Context**: The reviewer found that `get_sandbox_backend()` imports `BubblewrapSandbox`
*lazily inside the function* (`factory.py:77`), so the existing MCP tests' pattern of
`patch.object(stdio_module, "BubblewrapSandbox", ...)` + `assert_called_once_with()`
no longer intercepts selection — those assertions become unachievable post-retrofit.
**Decision**: canonical test injection for this leg is `patch.object(stdio_module,
"get_sandbox_backend", lambda: <backend>)`, asserting on the resulting wrapped params
(`command == "bwrap"`), not on mock construction. Also: `sdk_default_env_preserved`
test must additionally patch `factory_module.shutil.which` (selection now reads it,
not `bwrap_module.shutil.which`); the bwrap-missing test inverts to assert
passthrough/no-raise (construction-raise still unit-covered in
`test_sandbox_bubblewrap.py`); `get_sandbox_backend` return annotation tightened
`object`→`ToolSandbox` in this leg; `from_dict` now runs on the bypass path (validation
strictly-better, no test feeds malformed config under bypass — confirmed). All
incorporated. **Decision**: skipped a second design-review cycle (reviewer findings
were code-verified; same rationale as legs 1–2). Leg → `ready`. `[HANDOFF:review-needed]`.

### Leg 4 — Flight-spec contradiction resolved: denylist overlay is write-protection only
**Context**: The flight spec contradicts itself on the denylist overlay's effect.
DD4 specifies `--ro-bind` and names the field `readonly_overlay_paths` → **read-only**
(writes denied, path still *readable*), purpose "prevent **accidental** leakage". But
DD5's parenthetical ("the overlay *does* block reads") and the flight's Verification (b)
("a denylisted secret path … is neither writable nor readable") claim the overlay blocks
**reads**. A read-only bind **cannot** block reads (and everything is readable anyway
under DD5's `--ro-bind / /`). **Decision (Flight Director)**: honor **DD4** — overlay =
write-protection only; reads of denylisted paths remain possible this flight (consistent
with DD5's explicit read-scoping deferral). The `@requires_bwrap` acceptance test asserts
a denylisted secret is **not writable**, NOT unreadable. DD5's "blocks reads" parenthetical
and Verification (b)'s "nor readable" are treated as drafting errors. **Impact**: leg 5 /
Post-Flight verification must use the write-only wording; read-blocking lands with the
deferred read-scoping flight.

### Leg 4 — bubblewrap overlay `--ro-bind` → `--ro-bind-try`
**Context**: `DEFAULT_PATH_DENYLIST` lists many optional secret locations (`~/.aws`,
`~/.kube`, `~/.mozilla`, …) that frequently don't exist; `--ro-bind src dst` fails the
whole spawn if `src` is missing. **Decision**: the overlay loop emits `--ro-bind-try`
(bind-if-present-else-skip); the base `--ro-bind / /` mount is unchanged. Refines leg-2's
landed code (uncommitted) + its overlay test. The MCP path is unaffected (it sets no
overlay).

### Leg 4 — open questions resolved
- **cwd injection**: not needed — `_cwd_check` constrains cwd to the allowlist and the
  whole allowlist is `writable_paths`, so cwd ⊆ writable by construction.
- **kill under bwrap**: keep `start_new_session=True` + the existing killpg→proc.kill
  path for **both** passthrough and bubblewrap (bwrap is the group leader; killpg reaps
  the wrapped tree; `--die-with-parent` is the backstop). Validated by the
  `@requires_bwrap` timeout-kill test (criterion e); only add a bwrap-pid SIGKILL branch
  if that test proves an orphan survives.
- **seam opt-in**: `run_shell`/`run_python` gain an OPTIONAL `profile` param; `None` →
  byte-for-byte legacy spawn (keeps `test_platform_shell`/`_interpreter` untouched);
  non-None → seam (`select_shell()`+exec for shell, per DD7). Tools always pass a profile.

Leg 4 design review returned *approve with changes* (reviewer ran bwrap to verify
behavior): network-test rationale corrected (isolated net namespace → ECONNREFUSED, not
"loopback down"/ENETUNREACH); overlay-test update made token-precise (only the overlay
search token changes; base `--ro-bind / /` assertions stay); noted `--proc`/`--dev` must
stay after the overlay loop (denylist includes `/proc`,`/dev`); HOME-persistence test
simplified to `setenv("HOME", …)`; orphan-check robustness softened; `pyproject.toml`
marker count added to Files Affected. The reviewer independently endorsed the DD4/DD5
resolution and the kill strategy. **Decision**: skipped a second design-review cycle (same
rationale as legs 1–3). Leg → `ready`. `[HANDOFF:review-needed]`.

### Leg 4: builtin-tool-seam — landed

- **Status**: `ready` → `in-flight` → `landed`
- **What changed**: Routed `ShellTool` and `PythonExecTool` through the sandbox seam.
  - `the_one/tools/execution.py` — added `sandbox_network_allowed: Annotated[bool, Narrow] = False`
    to `ExecutionConfig` (DD6; inherited by `PythonExecConfig`; migration-free via `extra=ignore`);
    added `_build_tool_profile(fs_cfg, exec_cfg) → SandboxProfile` (DD10) returning
    `writable_paths` from `fs_cfg._canonical_allowlist`, `readonly_overlay_paths` from
    `fs_cfg._canonical_denylist`, `network_allowed = exec_cfg.sandbox_network_allowed`,
    `home = str(Path.home())`; added `TYPE_CHECKING` import of `SandboxProfile` for the
    return type annotation.
  - `the_one/platform/shell.py` — rewrote with optional `profile: SandboxProfile | None = None`
    kwarg; legacy path (`profile is None`) is byte-for-byte unchanged; sandboxed path calls
    `get_sandbox_backend().prepare_spawn()` with `select_shell()+exec` (DD7) and spawns via
    `create_subprocess_exec`; `start_new_session=True` + killpg kill strategy on both paths;
    function-level import of `get_sandbox_backend`/`BubblewrapSandbox` to avoid circular import.
  - `the_one/platform/interpreter.py` — identical pattern; sandboxed path uses `resolve_python()`
    + `["-c", code]` as the command/args pair.
  - `the_one/tools/shell.py` — imported `_build_tool_profile`; added
    `profile = _build_tool_profile(fs_cfg, exec_cfg)` + `profile=profile` kwarg in the call;
    no other behavior changed.
  - `the_one/tools/python_exec.py` — same wiring.
  - `the_one/platform/sandbox/bubblewrap.py` — overlay loop changed from `--ro-bind` to
    `--ro-bind-try` (F14 L4 refinement of leg-2 code); base `--ro-bind / /` unchanged;
    class/method docstrings updated.
  - `tests/test_execution_tools.py` — added autouse `_force_passthrough` fixture setting
    `THE_ONE_SANDBOX_DISABLED=1` + `THE_ONE_TEST_MODE=1`; all 35 existing tests now run under
    passthrough deterministically.
  - `tests/test_sandbox_bubblewrap.py` — updated overlay test
    (`test_prepare_spawn_readonly_overlay_after_writable_bind_before_proc`) to search for
    `--ro-bind-try` token (not `--ro-bind`); base-mount assertion `"--ro-bind" in a` unchanged.
  - `tests/test_builtin_tool_sandbox.py` (new) — 5 `@requires_bwrap` containment tests (a–e):
    write-outside-allowlist denied; denylist-secret write denied (write-only; sibling write
    succeeds); network isolated by default / reachable when allowed (via PythonExecTool);
    real-HOME persistence; timeout kills promptly with no orphan.
  - `pyproject.toml` — updated `requires_bwrap=2` comment to `requires_bwrap=7`.
- **Kill strategy**: kept `start_new_session=True` + existing killpg→proc.kill path on BOTH
  the legacy and sandboxed paths. With bwrap as the process group leader, `killpg` reaps the
  wrapped tree (bwrap + shell + any grandchildren). The `@requires_bwrap` timeout test (criterion e)
  confirmed: prompt return in <5s with no orphan `sleep 30` processes surviving. No bwrap-pid
  SIGKILL branch was needed — `--die-with-parent` + killpg was sufficient.
- **`--ro-bind-try` change**: the overlay loop in `bubblewrap.py` now emits `--ro-bind-try`
  instead of `--ro-bind`. This prevents a spawn failure when optional denylist paths (e.g.
  `~/.aws`, `~/.kube`, `~/.mozilla`) don't exist on the host. The base `--ro-bind / /` mount
  is unaffected. The `--proc` and `--dev` mounts remain AFTER the overlay loop — correct
  because denylist paths include `/proc`/`/dev`, so the overlay emits `--ro-bind-try /proc /proc`
  etc., and the subsequent `--proc /proc` / `--dev /dev` replace those binds (last-wins), giving
  proper procfs/devfs.
- **Test results**:
  - Targeted (`test_execution_tools`, `test_platform_shell`, `test_platform_interpreter`,
    `test_sandbox_bubblewrap`): 61 passed.
  - `@requires_bwrap` set (`test_builtin_tool_sandbox` + `test_sandbox_bubblewrap` +
    `test_mcp_pool`): 7 passed, 43 deselected.
  - Full default suite: 3007 passed, 4 skipped, 552 deselected, 3 warnings. Pre-existing
    aiosqlite/event-loop-closed warning (documented in conftest.py). `test_connectors_e2e.py::
    test_e2e_full_lifecycle` not present as a failure (consistent with prior runs).
- **Ruff results**: `ruff check .` — all checks passed; `ruff format --check .` — 439 files
  already formatted. (Initial run caught F401 unused imports, F821 undefined name in string
  annotation — resolved via `TYPE_CHECKING` import; I001 import order in test file — resolved
  via `ruff check --fix`.)
- **Anomaly**: None.

### Leg 5 design review (1 cycle) — scope expanded to full doc-sync; production posture clarified
**Context**: The reviewer found several doc claims that became **false** after this
flight, which a verify/doc-sync leg must correct rather than leave standing:
- `agents.md` point 4 ("bwrap-missing → `SandboxError`; NO unsandboxed fallback in
  production") — now false (factory returns passthrough). **Decision**: corrected per
  the mission criterion — bwrap-missing routes through `PassthroughSandbox` with a
  one-time WARNING (observable, not silent); passthrough-on-bwrap-missing IS the
  intended posture (the mission explicitly wants "no error at construction … absence of
  enforcement is observable/logged"). Construction-time `SandboxError` is gone from the
  spawn sites; the runtime bwrap-stderr→`SandboxError` translation on the MCP path
  remains.
- `agents.md` "Subprocess environment invariant" + `SECURITY-MODEL.md` name stale env
  call sites (`_build_subprocess_env` now called from `tools/shell.py` +
  `tools/python_exec.py`, not the platform layer).
- `agents.md` "Constraint surface" table omits `sandbox_network_allowed`.
- `mcp/README.md` attributes bwrap-missing/bypass handling to the old direct
  `BubblewrapSandbox()` construction (now the factory).
- `README.md` MCP-sandboxed/built-in-silent asymmetry.
- `pyproject.toml` marker-count comment stale.
Also fixed: ruff invocation scoped to `the_one/ tests/` (canonical CI scope, not `.`);
checklist `completed`→`landed`; `-x`-omission trade-off documented (record full failure
surface; re-run with `-x` if wedged). All incorporated — leg 5 now owns full doc-sync.
flight.md checkbox/landing updates remain deferred to the flight-level commit phase.
**Decision**: skipped a second design-review cycle (reviewer findings code-verified;
same rationale as legs 1–4). Leg → `ready`. `[HANDOFF:review-needed]`.

### Leg 5: verify-integration — landed

- **Status**: `ready` → `in-flight` → `landed`
- **Container**: `the-one` confirmed running and healthy (`docker ps | grep the-one`).

#### Verification Matrix

| Check | Result |
|-------|--------|
| Full default suite (`--timeout 60`) | **3007 passed, 4 skipped, 552 deselected** — no regression. Pre-existing aiosqlite event-loop-closed warning on one migration test; `test_connectors_e2e::test_e2e_full_lifecycle` not present as a failure (consistent with prior legs). |
| `requires_bwrap` suite (`--timeout 120`) | **7 passed, 3556 deselected** — all 7 containment tests pass (5 `test_builtin_tool_sandbox.py` + 2 `test_mcp_pool.py`). |
| Ruff (`the_one/ tests/`) | `ruff check` — all checks passed; `ruff format --check` — 333 files already formatted. |
| Passthrough no-error (simulated bwrap-missing) | Confirmed via `test_execution_tools.py` (29 tests, all green, autouse passthrough fixture — built-in tools execute through `PassthroughSandbox` without error) + `test_sandbox_factory.py` (factory passthrough/bwrap-missing/non-Linux unit tests). No gap; no additional smoke needed. |
| Pre-existing failure | `test_connectors_e2e::test_e2e_full_lifecycle` — NOT present as a failure in this run (absent from the failure list). No regression from this flight. |

#### Doc-sync surfaces corrected

1. **`the_one/agents.md`** — replaced the "MCP F3 Sandbox" heading with "Sandbox seam — platform-wide (M14 F1)" and added a new intro block describing: the three wired spawn paths (shell, python_exec, MCP stdio); `get_sandbox_backend()` factory; `PassthroughSandbox` fallback (bwrap-missing → passthrough + WARNING, no construction error); the host-workspace profile (`_build_tool_profile`, writable allowlist, `--ro-bind-try` denylist overlay, real `$HOME`, network deny-by-default). Kept all still-accurate MCP-specific points. Corrected point 4 (bwrap-missing no longer raises `SandboxError` at construction time; factory routes to passthrough; runtime bwrap-stderr translation remains). Updated HOME-policy note (6) to mention built-in tools use host-workspace profile. Corrected "Subprocess environment invariant" call sites (`_build_subprocess_env()` now called from `tools/shell.py` + `tools/python_exec.py`, not the platform layer). Added `sandbox_network_allowed` row to "Constraint surface" table.
2. **`the_one/mcp/README.md`** — updated §7 to note M14 F1: `connect_stdio` now calls `get_sandbox_backend()` (factory); bwrap-missing routes to `PassthroughSandbox` (not raise); double-flag bypass and runtime bwrap-stderr→SandboxError translation unchanged. Updated HOME-policy note to distinguish MCP (`/tmp`) from built-in tool host-workspace profile.
3. **`SECURITY-MODEL.md`** — corrected stale call site names (`shell.py::run_shell`, `interpreter.py::run_python`) to the actual tool-layer call sites (`tools/shell.py`, `tools/python_exec.py`) with correct description of the seam flow. Added a new bullet noting the OS-level execution fence for built-in tools (host-workspace profile, `--ro-bind-try` write-only protection, `sandbox_network_allowed` deny-by-default, `PassthroughSandbox` fallback). Write-only wording preserved (read-scoping deferred, per DD4/DD5).
4. **`README.md`** — appended one sentence to the MCP paragraph noting that `shell` and `python_exec` route through the same bubblewrap seam via a host-workspace profile (M14). Asymmetry corrected.
5. **`CLAUDE.md`** — added a paragraph after the `test_mcp_pool.py` note describing `tests/test_builtin_tool_sandbox.py` (5 tests) and the full `pytest -m requires_bwrap` invocation (7 total).
6. **`pyproject.toml`** — refreshed the `# Per-marker deselect math` comment from the stale `(last verified L0): live=10, browser=288, pixel=12, requires_bwrap=7, total=317` to actual verified counts `(last verified L5): live=15, browser=513, pixel=12, requires_bwrap=7, discord_hat=5, total=552`.

#### No deviations; no regressions; no code changes

All 6 acceptance criteria for doc corrections are satisfied. No source/behavior changes
were made (this is a verify+docs leg). The one known pre-existing failure
(`test_connectors_e2e::test_e2e_full_lifecycle`) was absent from the failure list.

#### Doc debt flagged for later (not a standing falsehood)

- `the_one/mcp/README.md` §7 still references "see CLAUDE.md F3 contracts §7" for the
  HOME policy — that section reference may need updating in a future maintenance cycle
  if CLAUDE.md's F3-contracts section is reorganized, but the content itself is not false.

---

_Runtime decisions not in the original plan will be recorded here._

---

## Deviations
_Departures from the planned approach will be recorded here._

---

## Anomalies
_Unexpected issues will be recorded here._

---

## Session Notes
- Flight spec created from Mission 14 (Unified Tool-Execution Sandbox), Flight 1.
- Architect design review (Phase 5b): **approve with changes** — all incorporated.
- Key decisions (final): built-in tools default to a **host-workspace** profile
  (capable assistant, not a cage) = writable from `FilesystemConfig` allowlist,
  denylist OS-enforced via a new `readonly_overlay_paths` field, **real `$HOME`**,
  network deny-by-default (opt-in via `ExecutionConfig.sandbox_network_allowed`).
  Read-scoping deferred. Rename **in place** (`ToolSandbox`/`SandboxError`,
  keeping the `MCPClientError` hierarchy + `client.py:511` catch) as its own first
  leg. Existing `test_execution_tools.py` pinned to passthrough; containment via
  `@requires_bwrap` integration tests. Profile derivation built as one clean
  `_build_tool_profile()` function = the hook for Flight 4 (agent-selectable boxed
  mode), which was added to the mission as a separate flight.
- Architectural framing confirmed with operator: bwrap ≠ Docker — the seam is a
  per-execution *policy dial*, not an outer cage; the native trajectory (M15)
  makes the app the capable assistant on the host with the sandbox as the opt-in box.
