# Leg: mcp-via-factory

**Status**: completed
**Flight**: [Sandbox Seam + Built-in Tool Retrofit](../flight.md)

## Objective

Retrofit the MCP stdio spawn site (`the_one/mcp/transports/stdio.py`) to obtain its
sandbox backend from `get_sandbox_backend()` instead of constructing
`BubblewrapSandbox()` directly — folding the test-bypass into the factory, removing
the now-redundant stdio-local `_sandbox_disabled_for_tests`, and making the
bwrap-stderr-capture path key off the *actual selected backend* rather than the
bypass flag. Net effect: MCP still launches sandboxed on Linux+bwrap (HOME=/tmp
preserved), the test-bypass still skips wrapping, and **off-Linux / bwrap-missing
now routes through passthrough without erroring at construction** (the mission's core
fix for the MCP path).

## Context

- **DD2 (flight):** retrofit `stdio.py:_build_stdio_params` to use the factory; fold
  the bypass in. Today `BubblewrapSandbox()` is constructed directly at the build
  site and raises off-Linux; the factory centralizes that guard.
- **Mission criterion:** "On a platform with no sandbox backend, the app runs
  through the shared seam via a passthrough and does not error at construction."
  This leg delivers that for the MCP path.
- **Constraint (mission):** do not regress existing MCP sandboxing — MCP must still
  be bwrap-wrapped on Linux, still get `HOME=/tmp` (profile-driven HOME with
  `profile.home=None` for MCP yields `/tmp` — leg 2).
- **Prior legs:** Leg 1 renamed symbols (`ToolSandbox`/`SandboxError`); Leg 2 added
  `PassthroughSandbox`, `get_sandbox_backend()` (with its own copy of the
  double-flag predicate and the one-time selection log), the overlay field, and
  profile-driven HOME. This leg consumes all of that.
- **State-machine reachability (critical):** today the bwrap-missing path raises
  `SandboxError` at `BubblewrapSandbox()` construction *inside the MCP build*. After
  this leg, the factory returns `PassthroughSandbox` for bwrap-missing, so that
  construction-time raise is **unreachable from the MCP path**. The existing test
  that asserts it raises must be **inverted** (it now asserts no-raise +
  passthrough), per the leg-design state-machine audit. The construction-time raise
  itself is still unit-tested at the `BubblewrapSandbox` level
  (`test_sandbox_bubblewrap.py::...bwrap_missing`), so the guard is not lost — only
  the MCP path stops triggering it.

## Inputs

What exists before this leg runs (post-leg-2, landed):
- `the_one/mcp/transports/stdio.py`:
  - imports `from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile`
    (`stdio.py:75`).
  - `_sandbox_disabled_for_tests()` (`stdio.py:359`) — the double-flag predicate.
  - `_build_stdio_params(source) -> StdioServerParameters` (`stdio.py:383`):
    currently `if _sandbox_disabled_for_tests(): return StdioServerParameters(...unwrapped...)`
    then `profile = SandboxProfile.from_dict(...)`, `sandbox = BubblewrapSandbox()`,
    `spec = sandbox.prepare_spawn(...)`, returns wrapped params
    (`stdio.py:408-419`).
  - `connect_stdio` computes `sandboxed = not _sandbox_disabled_for_tests()`
    (`stdio.py:451`) and branches: sandboxed → capture bwrap stderr via
    `errlog=errbuf` + `_translate_bwrap_stderr`; else → SDK default errlog passthrough.
  - `_open_stdio_transport_stack` computes the same `sandboxed = not
    _sandbox_disabled_for_tests()` (`stdio.py:569`) and the same branch.
- `the_one/platform/sandbox/factory.py` — `get_sandbox_backend()` (leg 2): returns
  `BubblewrapSandbox` on Linux+bwrap (bypass off), else `PassthroughSandbox`. Has
  its own `_sandbox_disabled_for_tests()`.
- `the_one/platform/sandbox/__init__.py` — re-exports `get_sandbox_backend`,
  `PassthroughSandbox`, `BubblewrapSandbox`, `SandboxProfile`, `ToolSandbox`.
- `tests/conftest.py:29` — a docstring/comment referencing
  `the_one.mcp.transports.stdio._sandbox_disabled_for_tests`.
- `tests/test_mcp_stdio_sandbox.py` — the F3 L4 integration tests. Several patch
  `stdio_module.BubblewrapSandbox` directly and will break under the retrofit (see
  Edge Cases / Implementation Guidance for the per-test rework contract).
- `tests/test_mcp_sandbox_integration.py` — `@requires_bwrap` real-bwrap MCP tests
  (must still pass: MCP still wrapped when bwrap present).
- `_build_stdio_params` has **no direct test callers** (verified) — only the two
  in-module callers; its signature can change freely.

## Outputs

What exists after this leg completes:
- `_build_stdio_params(source) -> tuple[StdioServerParameters, ToolSandbox]` —
  builds the profile, calls `get_sandbox_backend()`, runs `prepare_spawn`, and
  returns `(params, backend)`. The bypass-branch early-return is gone (passthrough
  produces the same unwrapped params).
- `connect_stdio` and `_open_stdio_transport_stack` do
  `params, backend = _build_stdio_params(source)` and
  `sandboxed = isinstance(backend, BubblewrapSandbox)` — the bwrap-stderr-capture
  path now keys off "is the spawn actually bwrap-wrapped", not the bypass flag.
- `stdio.py:_sandbox_disabled_for_tests` removed (centralized in the factory);
  imports updated (`get_sandbox_backend` added).
- `tests/conftest.py` docstring reference repointed to the factory's predicate.
- `tests/test_mcp_stdio_sandbox.py` reworked: backend-selection tests inject via the
  factory; the bwrap-missing test inverted to assert passthrough/no-raise.
- MCP still bwrap-wrapped + `HOME=/tmp` on Linux+bwrap; `@requires_bwrap` MCP
  integration tests green; full default suite + ruff green.

## Acceptance Criteria

- [x] `_build_stdio_params` calls `get_sandbox_backend()` (no direct
      `BubblewrapSandbox()` construction) and returns `(params, backend)`. It always
      builds `SandboxProfile.from_dict(source.config.get("sandbox") or {})` and runs
      `backend.prepare_spawn(...)` — the result for `PassthroughSandbox` is the
      unwrapped command (matching the old bypass branch), and for `BubblewrapSandbox`
      is the bwrap-wrapped command.
- [x] `connect_stdio` and `_open_stdio_transport_stack` derive
      `sandboxed = isinstance(backend, BubblewrapSandbox)` from the returned backend
      (not from `_sandbox_disabled_for_tests()`). The bwrap-stderr-capture branch
      runs only when the backend is `BubblewrapSandbox`; passthrough takes the SDK
      default-errlog branch (incl. its `FileNotFoundError` inner-spawn translation).
- [x] `stdio.py` no longer defines `_sandbox_disabled_for_tests`; the symbol is gone
      from the module and no in-module reference remains (`grep -n
      '_sandbox_disabled_for_tests' the_one/mcp/transports/stdio.py` → empty).
- [x] On Linux with `bwrap` present and bypass off, MCP spawns are bwrap-wrapped
      (`params.command == "bwrap"`) and `HOME` is forced to `/tmp` (profile.home is
      None for MCP) — **no regression**. Proven by the `@requires_bwrap` MCP
      integration tests and the HOME-preservation test, still green.
- [x] With the double-flag bypass set, MCP spawns are **not** wrapped
      (`params.command` is the operator command; env not bwrap-mangled) — the factory
      returns passthrough.
- [x] With `bwrap` simulated-absent and bypass off, `connect_stdio` does **not**
      raise `SandboxError` at build/connect time — it routes through passthrough and
      runs unwrapped. (Inverted from the prior "raises when bwrap missing" test.)
- [x] `tests/conftest.py`'s reference to the bypass predicate points at the factory,
      not the removed stdio symbol.
- [x] Full default suite passes (`docker exec the-one pytest -x --timeout 30`);
      `@requires_bwrap` MCP tests pass (`docker exec the-one pytest -m requires_bwrap
      tests/test_mcp_sandbox_integration.py --timeout 60`); `ruff check .` +
      `ruff format --check .` pass.

## Verification Steps

- `docker exec the-one pytest tests/test_mcp_stdio_sandbox.py tests/test_mcp_stdio_error_translation.py tests/test_mcp_stdio_test_connect.py -x --timeout 30`
- `docker exec the-one pytest -m requires_bwrap tests/test_mcp_sandbox_integration.py tests/test_mcp_pool.py --timeout 60` — real-bwrap MCP path still green.
- `docker exec the-one grep -n '_sandbox_disabled_for_tests' /app/the_one/mcp/transports/stdio.py` — expect empty.
- `docker exec the-one pytest -x --timeout 30` (full default suite).
- `ruff check . && ruff format --check .`.

## Implementation Guidance

1. **Imports** (`stdio.py:75`): add `get_sandbox_backend` to the
   `from the_one.platform.sandbox import ...` line; keep `BubblewrapSandbox` (needed
   for the `isinstance` check) and `SandboxProfile`. `ToolSandbox` is needed only for
   the return-type annotation — import it too (it's a re-exported Protocol).
   - **Use `isinstance(backend, BubblewrapSandbox)` — the concrete class, NOT
     `isinstance(backend, ToolSandbox)`.** The Protocol check would be `True` for
     both backends (passthrough satisfies it too) and so would not discriminate.

1b. **Tighten the factory return annotation** (`the_one/platform/sandbox/factory.py:65`):
   `get_sandbox_backend()` currently returns `-> object` (leg 2). This is the natural
   moment to change it to `-> ToolSandbox` (import `ToolSandbox` from `.base` in the
   factory, under `TYPE_CHECKING` or directly — it's a lightweight Protocol). Small,
   in-scope, and makes the `(params, backend: ToolSandbox)` tuple type honest. No
   static gate runs today, so this is for readers, not CI.

2. **Rewrite `_build_stdio_params`** (`stdio.py:383-419`):
   - New signature: `def _build_stdio_params(source: MCPSource) -> tuple[StdioServerParameters, ToolSandbox]:`.
   - Remove the `if _sandbox_disabled_for_tests(): return ...unwrapped...` early
     return.
   - Keep building `command`/`args`/`cwd`/`env` exactly as today.
   - `profile = SandboxProfile.from_dict(source.config.get("sandbox") or {})`
     (unchanged — see Edge Cases on always-validating).
   - `backend = get_sandbox_backend()`.
   - `spec = backend.prepare_spawn(profile, command, args, env, cwd)`.
   - `return (StdioServerParameters(command=spec.command, args=spec.args,
     env=spec.env, cwd=spec.cwd), backend)`.
   - Update the docstring: it now obtains the backend from the factory; off-Linux /
     bwrap-missing yields passthrough (unwrapped) instead of raising; the bypass is
     handled inside the factory. Keep the note that `from_dict` may raise `ValueError`
     on a type-mismatched `config["sandbox"]`.

3. **Update `connect_stdio`** (`stdio.py:450-451`):
   - `params, backend = _build_stdio_params(source)`.
   - `sandboxed = isinstance(backend, BubblewrapSandbox)`.
   - Everything downstream (the `if sandboxed:` errbuf-capture branch and the `else:`
     SDK-default branch) is unchanged in body. Update the inline comment that
     explains `sandboxed` so it reads "True iff the factory selected the bubblewrap
     backend (the only backend that wraps in `bwrap` and writes bwrap stderr)".

4. **Update `_open_stdio_transport_stack`** (`stdio.py:568-569`): identical change —
   `params, backend = _build_stdio_params(source)` then
   `sandboxed = isinstance(backend, BubblewrapSandbox)`.

5. **Remove `stdio.py:_sandbox_disabled_for_tests`** (`stdio.py:359-380`). First
   `grep -rn '_sandbox_disabled_for_tests' tests/ the_one/` to confirm nothing
   imports the stdio copy (expected: only `tests/conftest.py` docstring + the
   factory's own copy). Then delete the stdio function. Also drop the now-unused
   `import os` if nothing else in the module uses it (check first — other code may).

6. **Repoint `tests/conftest.py:29`** docstring/comment from
   `the_one.mcp.transports.stdio._sandbox_disabled_for_tests` to
   `the_one.platform.sandbox.factory._sandbox_disabled_for_tests` (or describe it as
   "the factory's double-flag bypass"). This is a comment-only change; do not alter
   conftest behavior.

7. **Rework `tests/test_mcp_stdio_sandbox.py`.**

   **Critical injection fact:** `get_sandbox_backend()` imports `BubblewrapSandbox`
   **lazily inside the function** (`factory.py:77 — "from the_one.platform.sandbox.bubblewrap
   import BubblewrapSandbox"`). So patching `stdio_module.BubblewrapSandbox` (what
   the current tests do) **no longer intercepts backend selection** — the factory
   never reads that name. Every test that relied on `patch.object(stdio_module,
   "BubblewrapSandbox", sandbox_cls)` + `sandbox_cls.assert_called_once_with()` is
   now broken and the assertion is unachievable.

   **Canonical injection for this leg:** patch the factory at the stdio call site —
   `patch.object(stdio_module, "get_sandbox_backend", lambda: <backend>)` — returning
   a real `BubblewrapSandbox()` (or `PassthroughSandbox()`) as the test needs. This
   is hermetic (no container/env dependence, no lazy-import trap) and is the
   preferred pattern for all selection tests below. Assert on the **resulting
   wrapped params** (`captured["params"].command == "bwrap"` vs the operator command),
   not on mock-construction calls. Drop the now-dead `sandbox_cls = MagicMock(...)`
   setups and `assert_called_once_with()` / `assert_not_called()` assertions entirely.
   (Driving the real factory via env + `monkeypatch.setattr(factory_module.shutil,
   "which", ...)` is an acceptable alternative for the bwrap-missing inversion, where
   simulating absence is the point.)

   Per-test rework contract:
   - `test_connect_stdio_invokes_bubblewrap_when_flag_off`: patch
     `stdio_module.get_sandbox_backend` → `BubblewrapSandbox()`; assert `captured`
     params have `command == "bwrap"`. Remove the `sandbox_cls`/`assert_called_once_with`.
   - `test_connect_stdio_passes_config_sandbox_to_profile`: patch
     `stdio_module.get_sandbox_backend` to return a backend whose `prepare_spawn`
     records its `profile` arg (a small recording wrapper or a `MagicMock` backend
     with a side-effecting `prepare_spawn`); assert the recorded profile matches the
     config (e.g. `writable_paths`).
   - `test_connect_stdio_double_flag_bypass_skips_sandbox`: with both flags set,
     assert the spawn is **not** wrapped (`captured.command` == operator command,
     not `"bwrap"`). **Drop** the now-vacuous `patch.object(stdio_module,
     "BubblewrapSandbox", ...)` + `assert_not_called()` (they intercept nothing
     post-retrofit). The real factory returns passthrough under the double flag;
     either let it (set both env flags, no get_sandbox_backend patch) or patch
     `get_sandbox_backend` → `PassthroughSandbox()`. Update the docstring: mechanism
     is "factory returns passthrough", not "BubblewrapSandbox never instantiated".
   - `test_connect_stdio_only_sandbox_disabled_flag_does_not_bypass` and
     `test_connect_stdio_only_test_mode_flag_does_not_bypass`: **remove** the
     `sandbox_cls = MagicMock(...)` setup and the `assert_called_once_with()`
     assertion (unachievable now). With a single flag the bypass is NOT active →
     factory selects bubblewrap; assert the spawn **is** wrapped
     (`captured["params"].command == "bwrap"`), injecting via
     `patch.object(stdio_module, "get_sandbox_backend", lambda: BubblewrapSandbox())`.
   - `test_connect_stdio_propagates_mcpsandbox_error_when_bwrap_missing` →
     **invert and rename** (e.g. `test_connect_stdio_routes_to_passthrough_when_bwrap_missing`):
     with `bwrap` simulated absent (patch `factory_module.shutil.which` → None) and
     bypass off, assert `connect_stdio` does **not** raise `SandboxError`, runs
     unwrapped (`captured.command` == operator command), and yields a session. Keep
     the inverted test's docstring explaining the mission shift (bwrap-missing no
     longer errors — it degrades to passthrough). Note the construction-time raise is
     still covered at the unit level in `test_sandbox_bubblewrap.py`.
   - `test_connect_stdio_sdk_default_env_preserved_through_setenv`: **needs an
     explicit fix.** It patches `bwrap_module.shutil.which → "/usr/bin/bwrap"` to
     stop `BubblewrapSandbox.__init__` raising — but after the retrofit, *selection*
     is decided by `factory_module.shutil.which`, which this patch does not touch. On
     a bwrap-less host the factory returns passthrough, `HOME` isn't forced to
     `/tmp`, and the assertion fails. Fix: also patch
     `factory_module.shutil.which → "/usr/bin/bwrap"` (or simply patch
     `stdio_module.get_sandbox_backend` → `BubblewrapSandbox()`), so the factory
     reliably selects bubblewrap regardless of host. Preserve the `HOME == "/tmp"`
     assertion.
   - `test_connect_stdio_propagates_sandbox_profile_validation_error` (§9):
     **unaffected — no change needed.** `_build_stdio_params` builds the profile via
     `from_dict` *before* calling `get_sandbox_backend()`, so a malformed
     `config["sandbox"]` still raises `ValueError` before the factory is consulted.
     (Listed here so the implementer confirms it rather than wondering.)
   - The `@requires_bwrap` real-subprocess test(s): use a real `BubblewrapSandbox`;
     pass unchanged **if** they don't patch the class away from selection. If one
     patches `stdio_module.BubblewrapSandbox`, switch it to patch
     `stdio_module.get_sandbox_backend` → `BubblewrapSandbox()` (or let the real
     factory pick it; bwrap is present under `@requires_bwrap`).
   - **Log-once guard hygiene:** the factory's `_LOGGED` selection-log guard is
     process-global. It causes no failures here (it only suppresses repeat log
     emission), but if any test in this file later uses `caplog` to assert on the
     selection log, it must call `factory_module._reset_selection_log_state()` first.
     Optionally add an autouse fixture calling it, mirroring `test_sandbox_factory.py`,
     to keep this file self-contained. Not required for the current rework.
   - Update the module docstring header (lines ~1-25) which describes the old
     "BubblewrapSandbox unless bypass" / "SandboxError propagates when bwrap missing"
     contract to the new factory-based contract.

8. **Run** the targeted MCP test files, then `-m requires_bwrap` for the MCP
   integration + pool tests, then the full default suite, then ruff. Fix fallout.

## Edge Cases

- **`from_dict` now runs on the bypass path too.** The old code skipped
  `SandboxProfile.from_dict` when bypassed; the new code always builds the profile
  (passthrough ignores it). A *malformed* `config["sandbox"]` would now raise
  `ValueError` even under bypass. This is acceptable (validation is strictly better,
  and well-formed/empty configs are unaffected) — but confirm no existing test feeds
  a malformed sandbox config under the bypass and expects success. If one does,
  that's a deliberate behavior change to surface in review, not to paper over.
- **`sandboxed` semantics shift.** Previously `sandboxed == not bypassed`. Now
  `sandboxed == isinstance(backend, BubblewrapSandbox)`. The two agree on Linux+bwrap
  (both True) and under bypass (both False). They **diverge** only in the new
  reachable state — real deployment, bwrap-missing/non-Linux — where the old code
  couldn't reach this point (it raised) and the new code correctly treats passthrough
  as not-bwrap-wrapped (False), taking the SDK-default-errlog branch. This is the
  intended behavior; call it out in the flight-log entry.
- **`HOME=/tmp` must survive.** MCP builds its profile via `from_dict`, which does
  not set `home` (leg 2), so `profile.home is None` → bubblewrap forces `/tmp`. Do
  not pass a `home` for MCP. The existing HOME-preservation test guards this.
- **Don't touch built-in tools here.** `tools/shell.py`, `tools/python_exec.py`,
  `tools/execution.py`, `platform/shell.py`, `platform/interpreter.py` are leg 4.
  This leg is MCP-only.
- **`import os` removal.** Only drop `import os` from stdio.py if no other code in
  the module uses it — grep first; leaving it is harmless if uncertain (but ruff
  will flag a truly-unused import, so confirm).
- **Pre-existing failure.** `tests/test_connectors_e2e.py::test_e2e_full_lifecycle`
  is a known pre-existing failure unrelated to this flight; if it is the *only*
  failure, it is not a regression.

## Files Affected

- `the_one/mcp/transports/stdio.py` — `_build_stdio_params` uses the factory + returns
  `(params, backend)`; `connect_stdio` / `_open_stdio_transport_stack` derive
  `sandboxed = isinstance(backend, BubblewrapSandbox)`; remove
  `_sandbox_disabled_for_tests`; update imports and docstrings.
- `the_one/platform/sandbox/factory.py` — tighten `get_sandbox_backend()` return
  annotation `object` → `ToolSandbox`.
- `tests/test_mcp_stdio_sandbox.py` — rework backend-selection tests; invert the
  bwrap-missing test; update module docstring.
- `tests/conftest.py` — repoint the bypass-predicate docstring reference to the
  factory.
- (Verify, likely no change) `tests/test_mcp_sandbox_integration.py`,
  `tests/test_mcp_pool.py` — `@requires_bwrap` MCP tests should still pass; touch only
  if a patch target moved.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (incl. `-m requires_bwrap` MCP integration)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (N/A — leg 3 of 5)
- [x] Commit all changes together (code + artifacts)

> **Note (batched flight):** Implementing Developer does **not** commit and does
> **not** signal `[COMPLETE:leg]` — set the leg to `landed`, update the flight log,
> signal `[HANDOFF:review-needed]`. Status → `completed` and the commit happen in the
> flight-level review/commit phase (2d).
