# Leg: cli-parity

**Status**: completed
**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](../flight.md)

## Objective

Lock CLI/web sandbox parity with a `@requires_bwrap` test that builds a built-in
tool the way `AgentFactory` (and therefore the CLI) builds it, and proves (a) a
write outside the allowlist is denied under real bwrap and (b) the factory path
wires a real, non-empty `FilesystemConfig` rather than silently defaulting to an
empty one.

## Context

- **DD2** (flight): CLI parity is verified by building the tool the CLI's way, not
  by driving the interactive CLI REPL (brittle: stdin/PTY + LLM loop). The CLI
  (`interfaces/cli.py:38` — `factory = AgentFactory(store=store)`) and web
  (`interfaces/web/app.py:97`) both construct tools via the **same**
  `AgentFactory(store=store)` path. Parity is a property of that shared path.
- **Architect correction** (DD2): asserting "CLI profile *equals* web profile" is
  tautological — both interfaces call the identical `AgentFactory(store=store)` →
  `ToolConfigRepository(conn).list()` → tool construction with identical inputs;
  there is no interface-specific tool-config customization. So the test does **not**
  assert profile-equality. It asserts the real invariant: the shared construction
  path produces a *genuinely sandboxed* tool sourcing a *real* policy.
- The actual tool-construction call the factory makes is
  `BuiltinToolProvider().get_tools(tool_configs_by_name, agent_overrides, agent_name=…)`
  at `the_one/agent/factory.py:380-387` (the `isinstance(provider, BuiltinToolProvider)`
  branch under the `for provider in self.tool_providers:` loop). Testing through
  `BuiltinToolProvider.get_tools` is the faithful, hermetic stand-in for the factory
  path (no DB-configured provider required) — it is the same call site, exercised with
  operator tool-configs.
- **Cross-config keying (design-review finding — load-bearing).** `ShellTool.Config`
  is `ExecutionConfig`, **not** `FilesystemConfig` (`tools/shell.py:55-56` —
  `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`). The shell tool reads
  its filesystem policy from the **shared cross-config**:
  `fs_cfg = self._cross_configs[FilesystemConfig]` (`tools/shell.py:66`). In
  `get_tools`, the cross-config `FilesystemConfig` is resolved **once**, from the
  **first** tool in `_TOOL_CLASSES` declaration order whose `Config` is
  `FilesystemConfig` — which is `read_file` (`tools/builtins.py:150-155`), since `shell`
  is first but its `Config` is `ExecutionConfig`. Therefore the test must key the
  `FilesystemConfig` fields under **`"read_file"`** (not `"shell"`). Keying under
  `"shell"` silently routes those keys into `ExecutionConfig` (dropped by
  `extra="ignore"`) and leaves the cross-config `FilesystemConfig` at its default
  `["~"]` allowlist — a **vacuous pass** for assertion (b).
- The `SandboxProfile` is assembled at **execution time** by
  `_build_tool_profile(fs_cfg, exec_cfg)` (`tools/execution.py:424-458`), which maps
  `FilesystemConfig._canonical_allowlist` → `writable_paths`,
  `._canonical_denylist` → `readonly_overlay_paths`,
  `ExecutionConfig.sandbox_network_allowed` → `network_allowed`, `Path.home()` →
  `home`. So "the factory wired a real FilesystemConfig" is observable on the
  constructed tool *before* execution, and "containment holds" is observable by
  running `execute()` under bwrap.

## Inputs

- All four spawn paths route through the seam (Flights 1-2, merged to `main`).
- `bwrap` present on host (0.9.0) + Docker grants userns caps.
- Existing per-path proof: `tests/test_builtin_tool_sandbox.py` already asserts
  write-outside-allowlist denial for a directly-instantiated `ShellTool`. This leg's
  new value is proving the **construction path** (`get_tools` with operator configs)
  does not drop the policy.

## Outputs

- New `tests/test_cli_sandbox_parity.py` with a `@requires_bwrap` test (or small
  test class) covering assertions (a) and (b) below.
- No production code changes — this is a verification leg (read `interfaces/cli.py`
  and `the_one/agent/factory.py` only to confirm the shared path).

## Acceptance Criteria

- [x] `tests/test_cli_sandbox_parity.py` exists and builds a built-in tool via the
      factory's tool-construction call — `BuiltinToolProvider().get_tools(...)` with a
      `tool_configs_by_name` carrying a **`read_file`**-keyed `FilesystemConfig` whose
      allowlist is a distinctive workspace under `$HOME` (and the default denylist) —
      i.e. the same call `AgentFactory.create()` makes at `factory.py:380-387`.
      (Optionally also a `shell`-keyed `ExecutionConfig` for the network knob.)
- [x] **(a) Containment**: under real bwrap (`@requires_bwrap`), invoking the
      constructed shell tool's `execute()` to write a file **outside** the allowlist
      (e.g. a sibling dir under `$HOME` not in the allowlist, or `/etc/…`) leaves **no
      such file on the host** afterward (assert host-file absence — the real
      containment proof; do not parse error text).
- [x] **(b) Real policy sourced**: the constructed shell tool's shared
      `FilesystemConfig` carries the **distinctive operator allowlist path** — assert
      `shell_tool._cross_configs[FilesystemConfig].path_allowlist` contains the
      workspace path passed in — proving the construction path wires the resolved
      config through and does not fall back to the default `["~"]`. (b) is observable at
      construction time and needs **no bwrap** — it may be its own non-`requires_bwrap`
      test function.
- [x] No production source files (`.py` outside `tests/`) are modified.
- [x] `ruff check` + `ruff format --check` pass on the new test file.

## Verification Steps

- `docker exec the-one python -m pytest tests/test_cli_sandbox_parity.py -x --timeout 60 -m requires_bwrap` — both assertions green.
- Confirm assertion (a) reads **host filesystem state** (file absent), not the
  tool's returned error string.
- `docker exec the-one ruff check tests/test_cli_sandbox_parity.py && docker exec the-one ruff format --check tests/test_cli_sandbox_parity.py`.
- Confirm the (b) assertion targets the **distinctive workspace path** (not `~`), so a
  default-config fallback would fail it (guard against a vacuous pass). A quick
  negative check: temporarily key the config under `"shell"` instead of `"read_file"`
  and confirm (b) FAILS — then revert. (Do not leave this in the committed test.)

## Implementation Guidance

1. **Confirm the shared path (read-only).**
   - `interfaces/cli.py:38` — `factory = AgentFactory(store=store)`; `:40` —
     `agent = await factory.create()`.
   - `the_one/agent/factory.py:381-387` — inside `create()`, the builtin path is
     `BuiltinToolProvider` → `provider.get_tools(tool_configs_by_name, agent_overrides, agent_name=name, connector_ids=…, connector_acls=…)`.
   - `the_one/agent/factory.py:292-295` — `tool_configs_by_name = {c.name: c.config for c in configs}` where `configs = await ToolConfigRepository(conn).list()`. The dict values are **plain dicts** (not Pydantic models); `resolve()` types them.

2. **Build the tool the factory's way (hermetic).**
   - Construct `tool_configs_by_name` as a dict keying the `FilesystemConfig` fields
     under **`"read_file"`** (the first FilesystemConfig-Config tool — see Context),
     e.g.
     `{"read_file": {"path_allowlist": [<workspace-under-$HOME>], "path_denylist": [<default denylist incl ~/.ssh>]}}`.
     If you also want to exercise the network knob, add a `"shell"` entry for
     `ExecutionConfig` fields (e.g. `sandbox_network_allowed`). Confirm the exact field
     names against `the_one/tools/filesystem.py:FilesystemConfig` and
     `the_one/tools/execution.py:ExecutionConfig`.
   - Call `BuiltinToolProvider().get_tools(tool_configs_by_name, {}, agent_name="default")`.
   - Pull the `shell` tool out of the returned list (match on `tool.name == "shell"`).

3. **Assertion (b) — real policy sourced.**
   - The shell tool reads its filesystem policy from the **shared cross-config**, not a
     top-level attribute. Assert
     `shell_tool._cross_configs[FilesystemConfig].path_allowlist` is non-empty **and
     contains the distinctive workspace path** you passed under `"read_file"`. This
     proves `get_tools` → `resolve()` wired the operator config through, not the default
     `["~"]`. No bwrap required for this assertion.

4. **Assertion (a) — containment under bwrap.**
   - Create the workspace dir under `$HOME` **before** calling `execute()` — it is the
     tool's `cwd`, and `_cwd_check` (`execution.py:355` → `_filesystem_check(…,
     CheckMode.DIRECTORY)`, `filesystem.py:165`) enforces both in-allowlist scope and
     `is_dir()`; a missing/out-of-scope cwd raises before the spawn. Pass
     `cwd=str(workspace)`.
   - Pick an out-of-allowlist target that does **not** exist yet (e.g. a sibling dir
     under `$HOME` not in the allowlist, or `/etc/tsc_parity_fail`).
   - `await shell_tool.execute(...)` with a command that attempts to write the
     out-of-allowlist file (e.g. `echo x > <target>`). The seam builds the profile via
     `_build_tool_profile` and runs under bwrap (`--ro-bind / /` default → outside
     writable_paths is read-only).
   - Assert the **host** file does not exist afterward. Tear down the workspace dir.

5. **Reuse, don't duplicate.** This leg lands *before* `containment-behavior-suite`
   creates `tests/_sandbox_fixtures.py`. Keep helpers minimal and inline here; leg 2
   will fold any genuinely shared setup (workspace-under-`$HOME`) into the shared
   module and may refactor this test to import it. Do **not** pre-create
   `_sandbox_fixtures.py` in this leg.

## Edge Cases

- **AgentFactory.create() vs get_tools**: do NOT drive full `create()` — it requires a
  provider configured in the DB (`factory.py:240-262`) and an LLM. The architect
  endorsed the `get_tools` seam as the faithful shared-path stand-in. If a reviewer
  insists on `create()`, that is a divert-to-human, not a silent expansion.
- **Tautological (b) via wrong key**: keying the `FilesystemConfig` fields under
  `"shell"` routes them into `ExecutionConfig` (silently dropped) and leaves the shared
  `FilesystemConfig` at its default `["~"]` — (b) then passes vacuously. Key under
  `"read_file"` and assert the *distinctive* workspace path is present.
- **`@requires_bwrap` marker already registered** in `pyproject.toml:11` (the
  `markers = [...]` block) — `test_builtin_tool_sandbox.py` already uses it. Do **not**
  add or re-register the marker; just apply `@pytest.mark.requires_bwrap` to the
  containment test. No `conftest.py` change in scope.
- **bwrap absent**: the `@requires_bwrap` marker deselects the test off-bwrap hosts;
  do not add a runtime skip that masks a real bwrap failure.

## Files Affected

- `tests/test_cli_sandbox_parity.py` — **new**; the `@requires_bwrap` parity test.
- `the_one/interfaces/cli.py` — read-only (confirm shared path).
- `the_one/agent/factory.py` — read-only (confirm shared path).

---

## Post-Completion Checklist

> **Batched-commit flight**: this leg's changes are **not** committed at leg end.
> The Developer implements, updates the flight log, sets leg status to `landed`, and
> signals `[HANDOFF:review-needed]`. Review + commit happen once after the last
> autonomous leg (flight Phase 2d).

- [x] All acceptance criteria verified
- [x] `@requires_bwrap` parity test green; ruff clean
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed` — flight commits in batch)
- [x] Do NOT commit; do NOT check off the leg in flight.md yet (done at batch commit)
