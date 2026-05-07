# Flight: Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend

**Status**: in-flight
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] Locally spawned MCP server processes run inside an OS-level sandbox with a fixed environment allowlist, no inherited host secrets, and a clear extension seam for additional platform backends; the implementation is verified on Linux against a reference local MCP server *(F3 lands the adapter + bubblewrap backend; idle-TTL reaper is F4)*
- [ ] Each layer of the integration has automated coverage proving its contract — the encrypted persistence layer, the client-side connection lifecycle for both transports, the sandbox spawn path, the idle-TTL reaper, the resolver's substitution behavior on MCP-shaped overrides, the tool-name-spacing logic, and the inspector's tool-list / tool-call round-trip *(F3 contributes the sandbox spawn path)*

---

## Pre-Flight

### Objective

Land the OS-level sandbox layer that wraps F2's stdio MCP transport. Two coordinated deliverables: (a) a `MCPSandbox` adapter contract under `the_one/platform/sandbox/` defining minimum guarantees (env-allowlist enforcement, filesystem scope, network policy, process supervision) versus optional/best-effort capabilities, exposed via a `prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec` Protocol method that returns a frozen dataclass capturing all process-creation parameters across Linux/macOS/Windows shapes; (b) a `BubblewrapSandbox` Linux backend implementing the contract via `bwrap(1)`. The contract is paper-exercised against documented capabilities of macOS `sandbox-exec` and Windows `AppContainer` + Job Objects with citations — even though only the Linux backend ships — so a future macOS/Windows mission doesn't force a contract rewrite. The trust model is **strict by default**: read-only filesystem outside an explicit list of operator-configured writable paths; network OFF unless operator opts in via a per-source boolean. F2's `connect_stdio` is wired to compose `BubblewrapSandbox.prepare_spawn(...)` so every stdio MCP source spawns sandboxed; F2's existing `mcp_fixture_stdio_params` pytest fixture is updated in L4 with a sandbox-aware shape so the existing F2 stdio integration tests pass under the new mandatory-sandbox path. Sandbox setup failure (`bwrap` missing, mount path nonexistent, container lacks privileges) raises a new `MCPSandboxError(MCPClientError)` with no silent unsandboxed fallback. F1's `_validate_mcp_source_config` is extended to validate `config["sandbox"] = {"network_allowed": bool, "writable_paths": list[str]}` — sandbox profile lives plaintext alongside `command/args/env`, no schema migration. The L6 stdio editor gains a "Sandbox" sub-section with `network_allowed` checkbox + `writable_paths` chip-list. Test coverage exercises sandbox refusal of disallowed FS paths via an extension to the L3 hello fixture (`write_outside_sandbox`, `dump_env`, `try_connect` test-only tools), env-allowlist invariant under `bwrap --clearenv`, and child-process boundary semantics. CI compatibility is the FIRST leg — verify `bwrap` runs in the dev container with the privilege model committed in this spec (§10). **No process lifecycle in this flight** — the idle-TTL reaper + per-source registry is F4.

### Open Questions

All resolved at flight-design (post-Architect-review for §10).

- [x] **Sandbox trust model defaults** → strict by default: read-only FS outside explicit per-source `writable_paths` list; network OFF unless `network_allowed: true`. May loosen later if burdensome (mission Open Q resolved). See §1
- [x] **Writable scope shape** → list of operator-configured absolute paths (`writable_paths: list[str]`); no auto-provisioned tmpdir; no per-path read-only/read-write toggle (entries are uniformly writable). See §2
- [x] **Network opt-in granularity** → per-source boolean (`network_allowed: bool`). Per-host allowlist deferred to routine maintenance. See §3
- [x] **Storage location** → `MCPSource.config["sandbox"] = {"writable_paths": [...], "network_allowed": false}` plaintext alongside `command/args/env`. F1's validator extends with a sandbox sub-block validator. No schema migration. See §4
- [x] **UI surface** → "Sandbox" sub-section in the F1 L6 stdio editor with a `network_allowed` checkbox + `writable_paths` chip-list. See §5
- [x] **Sandbox failure mode** → hard-fail with new `MCPSandboxError(MCPClientError)`; no unsandboxed fallback. Boundary: failures BEFORE bwrap successfully wraps-and-execs target = sandbox error; failures AFTER (target started, initialize fails) = connection error. See §6
- [x] **Adapter contract paper-exercise depth** → lightweight: capability matrix vs documented behaviors of macOS `sandbox-exec` and Windows `AppContainer` with citations. See §7
- [x] **Module placement** → `the_one/platform/sandbox/` sub-package (`__init__.py`, `base.py`, `bubblewrap.py`). See §8
- [x] **Test escape-attempt fixture** → extend `tests/fixtures/mcp/hello_server.py` with `write_outside_sandbox`, `dump_env`, `try_connect` test-only tools. See §9
- [x] **Privilege model in dev container + CI** → resolved post-Architect-review: option (a) **`cap_add: [SYS_ADMIN]` + `security_opt: [seccomp:unconfined]` BOTH** (single-line SYS_ADMIN alone won't unblock `unshare(CLONE_NEWUSER)` because docker's default seccomp profile filters that syscall regardless of capabilities) for dev container. Option (c) `THE_ONE_SANDBOX_DISABLED=1` env flag **gated by `THE_ONE_TEST_MODE=1`** double-flag (belt-and-suspenders against accidental production activation) for Playwright browser-test image where MCP isn't exercised. Production: no flag, sandbox always on. See §10
- [x] **`MCPSandbox` Protocol shape** → `prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec` returning a frozen dataclass with fields covering Linux/macOS shape (`command, args, env, cwd`) + Windows shape (`creation_flags: int = 0`, `attribute_list: dict | None = None`). Avoids `build_argv() -> (cmd, args, env)` triple which would lock Windows AppContainer out. See §11
- [x] **Namespace-unshare granularity** → `SandboxProfile` carries `pid_unshare: bool = True`, `ipc_unshare: bool = True`, `uts_unshare: bool = True` for forward-compat with process-introspection MCPs that need host visibility. UI exposes only `network_allowed` + `writable_paths`; namespace fields are JSON-edit-only via API for advanced use cases. See §12
- [x] **HOME under sandbox** → override to `/tmp` (which IS writable via `--tmpfs /tmp`). Subprocess writing to `~/.cache` finds a usable home dir; no host `/root` leakage. See §13
- [x] **`the_one/mcp/README.md` (F2 debrief follow-up #2)** → REMOVED from F3 scope. Defer to post-F3 routine maintenance — no dependency on F3, and including in F3 distracts from sandbox focus per Architect feedback

### Design Decisions

**§1. Strict-by-default trust model**

Read-only filesystem outside an explicit operator-configured list of writable paths. Network OFF unless operator opts in.

- Rationale: mission constraint #47 frames the spawn-with-an-env-allowlist pattern as "trip-wire, not fence" — appropriate for built-in execution tools the operator wrote, insufficient for arbitrary third-party MCP servers. Strict-by-default makes the trust contract explicit at every source-creation
- Trade-off: more friction per-source. Acceptable per user feedback ("operator has some responsibility to not do dumb things like use untrusted mcps")

**§2. Writable scope: list of operator-configured paths**

`config["sandbox"]["writable_paths"]: list[str]` — absolute paths the sandbox grants read+write access to. Empty list (default) = sandbox is fully read-only. Each entry is `bwrap --bind PATH PATH` (read-write); everything else outside the writable scope is `--ro-bind /` (read-only).

- Rationale: predictable shape, matches operator's mental model
- Trade-off: no automatic per-source isolation tmpdir; operators sharing `writable_paths` across sources share state. Operator's responsibility per §1's framing
- **`/tmp` is special**: always provided as `--tmpfs /tmp` (fresh ephemeral tmpfs per spawn, not bind-mounted from host). MCPs writing large temp files (>50% of RAM tmpfs default) should add `/tmp` to `writable_paths` to host-bind-mount it instead. Documented as known trade-off
- **cwd is read-only by default**: subprocess `chdir(cwd)` succeeds (cwd is inside the `--ro-bind / /` floor), but writes to cwd fail with EACCES. Operator must add cwd to `writable_paths` if writes are needed. L1a's 5-assertion probe verifies the cwd-inside-ro-floor behavior

**§3. Network policy: per-source boolean**

`config["sandbox"]["network_allowed"]: bool` (default `false`). When `false`, bwrap spawns with `--unshare-net`. When `true`, bwrap inherits the host network namespace (full network access). Per-host allowlist deferred to routine maintenance.

**§4. Sandbox profile storage: extension of `MCPSource.config`**

`config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` lives alongside `command/args/env` in the plaintext `config` JSON column (NOT encrypted). F1's `_validate_mcp_source_config` extends with a sandbox sub-block validator. Both fields default to safe values when absent (empty list, `false`).

**§5. UI: Sandbox sub-section in the L6 stdio editor**

Added to `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` for stdio sources only. Two fields: `Allow network access` checkbox, `Writable paths` chip-list. No per-path toggle; reuses `App.adminFormHelpers.renderChipListEditor`. Streamable-http transport doesn't get a Sandbox section (no local process to sandbox).

**§6. Sandbox failure mode: hard-fail with `MCPSandboxError`, no fallback**

New `MCPSandboxError(MCPClientError)` raised from `connect_stdio` for failures BEFORE bwrap successfully wraps-and-execs the target command. Failures AFTER (target started but exits 1, initialize handshake fails) raise `MCPConnectionError` per F2's existing contract.

Boundary cases:
- `bwrap` binary not found via `shutil.which("bwrap")` → `MCPSandboxError`
- bwrap exits with `!= 0` from setup (mount failure, namespace setup failure, `EPERM` on `unshare`) → `MCPSandboxError`
- `writable_paths` contains a path that doesn't exist or isn't accessible → `MCPSandboxError`
- bwrap successfully wraps and execs `python -m hello_server`; the wrapped Python exits 1 because the module is broken → `MCPConnectionError` (F2 path)
- bwrap successfully wraps; SDK's `initialize()` handshake fails → `MCPVersionMismatch` or `MCPConnectionError` per F2

**Error message catalog** (small-model-friendly per mission constraint #61, with remedies):
- `"MCP sandbox setup failed: bubblewrap binary not found in PATH. Install with: apt-get install bubblewrap. In test environments only, set THE_ONE_SANDBOX_DISABLED=1 with THE_ONE_TEST_MODE=1."`
- `"MCP sandbox setup failed: writable_paths entry {path!r} does not exist. Create the directory or remove from writable_paths."`
- `"MCP sandbox setup failed: bubblewrap exited with code {n}. Check that the dev/CI environment has cap_add: SYS_ADMIN AND security_opt: seccomp:unconfined per F3 design decision §10."`
- `"MCP sandbox setup failed: namespace creation refused (EPERM on unshare). The container likely lacks the privilege grants required by §10."`

**§7. Adapter contract: paper-exercise via documented-capability matrix**

Capability matrix in `base.py` module docstring + `agents.md` cross-reference. Citations:
- bubblewrap(1) man page; `@anthropic-ai/sandbox-runtime` reference
- Apple Developer documentation: "App Sandbox Design Guide"; SBPL (Sandbox Profile Language)
- Microsoft Learn: AppContainer Isolation, Job Objects

**§8. Module placement: `the_one/platform/sandbox/` sub-package**

- `the_one/platform/sandbox/__init__.py` — re-exports `MCPSandbox`, `BubblewrapSandbox`, `SandboxProfile`, `SpawnSpec`. `MCPSandboxError` lives canonically at `the_one/mcp/errors.py` (alongside other MCPClientError subclasses); `__init__.py` re-exports for convenience but docstrings cite `the_one.mcp.errors` as the canonical import path
- `the_one/platform/sandbox/base.py` — `MCPSandbox` Protocol + `SandboxProfile` dataclass + `SpawnSpec` dataclass + capability matrix in module docstring
- `the_one/platform/sandbox/bubblewrap.py` — `BubblewrapSandbox` implementation

**§9. Escape-attempt test fixture: extend `hello_server.py` with three test-only tools**

`tests/fixtures/mcp/hello_server.py` gains:
- `write_outside_sandbox(path: str, content: str) -> str` — calls `Path(path).write_text(content)`. Marked `# TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION`
- `dump_env() -> dict[str, str]` — returns `dict(os.environ)` for env-allowlist invariant tests. Same TEST-ONLY marker
- `try_connect(host: str, port: int) -> str` — calls `socket.create_connection((host, port), timeout=2.0)` and returns either success or formatted error. Same TEST-ONLY marker

**§10. Privilege model (Architect-recommended combo)**

**Dev container** — `docker-compose.yml` adds:
```yaml
cap_add:
  - SYS_ADMIN
security_opt:
  - seccomp:unconfined
```

**Both are necessary**: docker's default seccomp profile filters `unshare(CLONE_NEWUSER)` regardless of capabilities granted, so `cap_add: [SYS_ADMIN]` alone won't unblock the user-namespace ops bwrap needs. The dual change is the minimum-viable privilege grant.

Threat-model justification: this is a single-developer dev box. The container already bind-mounts the developer's source tree; the trust delegation to the container is already total. SYS_ADMIN does NOT grant container escape on its own; namespace-creation flexibility is its primary use here. The unconfined seccomp drops ~50 syscall filters but doesn't lower the kernel exploit bar meaningfully. This is the same trust posture VS Code Dev Containers and flatpak-dev tooling use.

**Browser-test CI** (`mcr.microsoft.com/playwright/python:v1.58.0-jammy`) — no privilege grants needed. Browser tests don't call MCP runtime; the sandbox path isn't exercised. Set `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` in the CI env. The double-flag guard in `connect_stdio` is:

```python
def _sandbox_disabled_for_tests() -> bool:
    return (
        os.environ.get("THE_ONE_SANDBOX_DISABLED") == "1"
        and os.environ.get("THE_ONE_TEST_MODE") == "1"
    )
```

`THE_ONE_TEST_MODE=1` is set ONLY by `tests/conftest.py`'s `pytest_configure` hook (not by Dockerfile, not by docker-compose, not by entrypoint script). Belt + suspenders. Production never reads either flag.

**Operational guardrail**: DO NOT set `THE_ONE_TEST_MODE` in any Dockerfile, docker-compose service env, entrypoint script, kubernetes manifest, or CI variable. The flag is a pytest-only signal; presence outside pytest is a deployment defect. The Playwright browser-test image sets `THE_ONE_SANDBOX_DISABLED=1` only in its CI workflow's pytest invocation (e.g., `pytest -m browser` with the env var) — never in the image itself.

**Production** — no flag, no skip. Bwrap mandatory; `MCPSandboxError` raises if missing. Operator's responsibility to deploy with bwrap + appropriate privileges in their image.

**Future-platform user (mac/Windows)** — out of scope this mission per criterion #71. Their backend (sandbox-exec/AppContainer) has its own privilege model.

**§11. `MCPSandbox` Protocol shape: `prepare_spawn() -> SpawnSpec`**

```python
@dataclass(frozen=True)
class SpawnSpec:
    """Process-creation parameters that span Linux/macOS/Windows backends."""
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: str | None = None
    # Windows-only fields (default safe values for Linux/macOS):
    creation_flags: int = 0  # CreateProcess dwCreationFlags (Windows AppContainer)
    attribute_list: dict[str, Any] | None = None  # AppContainerSidAndAttributes (Windows)


@runtime_checkable
class MCPSandbox(Protocol):
    """Adapter contract for OS-level sandboxing of MCP server subprocesses."""

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

`BubblewrapSandbox.prepare_spawn` returns `SpawnSpec(command="bwrap", args=[...wrapped], env={cleared_then_setenv}, cwd=cwd)`. macOS `sandbox-exec` would be similar (`command="sandbox-exec"`, `args=["-p", profile_text, "--", original_command, *original_args]`). Windows AppContainer would return `SpawnSpec(command=command, args=args, env=env, cwd=cwd, creation_flags=EXTENDED_STARTUPINFO_PRESENT, attribute_list={...AppContainerSid...})` — keeps `command/args/env` UNCHANGED but uses the Windows-only fields.

**Linux/macOS composition with `StdioServerParameters`**: the SDK accepts `command/args/env/cwd` only. F3 L4's `connect_stdio` does `params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env, cwd=spec.cwd)` — `creation_flags` and `attribute_list` are simply not read on Linux. They exist purely so future Windows backends can populate them via `subprocess.Popen` extended-startup-info pathways without changing the Protocol shape.

**§12. SandboxProfile namespace-unshare granularity**

```python
@dataclass(frozen=True)
class SandboxProfile:
    writable_paths: list[str] = field(default_factory=list)
    network_allowed: bool = False
    # Namespace-unshare flags (forward-compat; default secure):
    pid_unshare: bool = True   # bwrap --unshare-pid
    ipc_unshare: bool = True   # bwrap --unshare-ipc
    uts_unshare: bool = True   # bwrap --unshare-uts
```

UI exposes only `writable_paths` + `network_allowed`. Namespace fields are JSON-edit-only via the API for advanced use cases (e.g., a process-introspection MCP that needs `pid_unshare=False` to enumerate host processes). Operator-facing language stays simple; advanced operators have a forward-compatible escape hatch.

`SandboxProfile.from_dict(d)` factory method contract:
- **Unknown keys**: ignored (debug-log them; do NOT raise)
- **Missing keys**: default to dataclass field defaults (empty list, `False`, `True` for namespace flags)
- **Type mismatch on a known field** (e.g., `network_allowed=42` instead of bool): raise `ValueError` at construction time with a small-model-friendly message naming the offending field and expected type
- **`writable_paths` list contents**: each entry is coerced to `str` via `str(...)`; non-string-coercible entries (e.g., `None`) raise `ValueError`

**§13. HOME override under sandbox**

Under bwrap, the assembled environ has HOME pointing at the host's `/root` (dev container) or whatever the host has. With `--ro-bind / /`, `/root` is read-accessible but not writable; subprocesses writing to `~/.cache` hit EACCES. Override HOME to `/tmp` for sandboxed subprocesses (which IS writable via `--tmpfs /tmp`) so HOME-touching code finds a usable home dir.

`BubblewrapSandbox.prepare_spawn` overrides `env["HOME"] = "/tmp"` regardless of what the operator-assembled env contains. Document in module docstring + capability matrix.

**Trade-off**: operators can't override HOME via the kv-table. Acceptable — HOME under sandbox is sandbox-policy, not operator-configurable. If a future MCP needs a specific HOME, operators can add the path to `writable_paths` AND set `MY_HOME` env var pointing at it (or override HOME via a setenv inside their MCP startup script).

### Prerequisites

- [x] F2 landed and `completed`. `MCPClient` lifecycle, `connect_stdio` transport at `the_one/mcp/transports/stdio.py`, `MCPClientError` hierarchy — all present
- [x] F1 `_validate_mcp_source_config` accepts `command/args/env/cwd/headers/oauth` validation; F3 L1b extends with `sandbox` sub-block
- [x] `the_one/platform/env._ENV_ALLOWLIST` (8-key tuple) + `_build_subprocess_env()` helper; F3 reuses, does NOT re-declare
- [x] `tests/fixtures/mcp/hello_server.py` (FastMCP `echo` + `add` tools); F3 L5a extends with naughty tools
- [x] `mcp_fixture_stdio_params` pytest fixture in `tests/conftest.py`; F3 L4 updates with sandbox-aware shape (default profile = strict floor) so existing F2 stdio integration tests pass
- [x] HOST has `bwrap 0.9.0`; container does NOT — F3 L1a adds via Dockerfile apt
- [x] Mission constraint #50: env allowlist is the 8-key set + operator overlay decrypted from MCP source's encrypted config
- [x] Architect-approved privilege model committed in §10 (resolved at flight-design)

### Pre-Flight Checklist

- [x] All open questions resolved (10 + 3 carried = 13)
- [x] Design decisions documented (§§1–13)
- [x] Prerequisites verified
- [x] Validation approach defined (test strategy in legs L5a + L7)
- [x] Legs defined (see In-Flight § Legs)
- [x] Architect design review cycle 2 (Phase 5b): approve with minor changes — applied inline
- [ ] User approval (Phase 6)

---

## In-Flight

### Technical Approach

The flight builds on F2's `connect_stdio` transport by composing a new `BubblewrapSandbox.prepare_spawn(...)` step into the spawn pipeline. The sandbox wrap happens INSIDE `connect_stdio` (per F2 debrief recommendation): the operator-supplied `command, args, env, cwd` from `MCPSource.config` are passed through `BubblewrapSandbox.prepare_spawn(...)` which returns a `SpawnSpec`. The `SpawnSpec.command/args/env/cwd` are then fed into the SDK's `StdioServerParameters` exactly as before. The 2-layer environ assembly (`build_stdio_environ`) is preserved; `BubblewrapSandbox` then applies a sandbox-policy overlay (HOME→/tmp) and feeds the result into bwrap's `--clearenv` + `--setenv` per kept var, enforcing the allowlist + operator-overlay contract under bwrap's stricter env model.

**Bwrap argv structure** (compiled from `SandboxProfile`):
- `--die-with-parent` (subprocess dies if parent dies — process-supervision guarantee)
- `--unshare-user` (always — namespace isolation floor)
- `--unshare-pid` if `profile.pid_unshare` (default True)
- `--unshare-ipc` if `profile.ipc_unshare` (default True)
- `--unshare-uts` if `profile.uts_unshare` (default True)
- `--unshare-net` if `not profile.network_allowed`
- `--clearenv` (env-allowlist enforcement)
- `--setenv KEY VALUE` for each entry of the assembled environ (with HOME forced to `/tmp`)
- `--ro-bind / /` (read-only rootfs)
- `--bind PATH PATH` for each entry of `writable_paths`
- `--proc /proc` `--dev /dev` (minimal /proc + /dev furniture)
- `--tmpfs /tmp` (fresh ephemeral tmpfs)
- `--chdir cwd` if cwd is set (note: cwd must be inside the bwrap-mounted view; if cwd is outside `/`, that's an `MCPSandboxError`)
- `--` (separator)
- `command, *args` (the original target)

**cwd handling**: cwd is implicitly read-only-mounted via the `--ro-bind / /` floor. Subprocess `chdir(cwd)` succeeds; reads work; writes fail with EACCES. If the operator's MCP needs to write to cwd, they must add cwd (or a parent of it) to `writable_paths`. Documented in §2 + L4 docstring.

**Test fixture sandbox-aware shape** (L4 fixture update):
- `mcp_fixture_stdio_params` returns the params dict as before BUT the new caller (sandbox-wrapped `connect_stdio`) consumes them via `BubblewrapSandbox.prepare_spawn(...)`
- A new `mcp_fixture_sandbox_profile` fixture in `tests/conftest.py` provides the canonical strict floor: `SandboxProfile(writable_paths=[], network_allowed=False)`
- Tests that need writable paths or network extend the profile per-test

**The L1a CI compat probe** — runs 5 assertions in the rebuilt dev container (after docker-compose change):
1. `bwrap --version` prints a version line
2. `unshare -U /bin/echo test` runs without `Operation not permitted`
3. `bwrap --die-with-parent --unshare-user --unshare-pid --ro-bind / / --tmpfs /tmp -- /bin/echo hello` runs and prints `hello`
4. `bwrap --die-with-parent --unshare-user --ro-bind / / --chdir /tmp -- /bin/pwd` prints `/tmp` (cwd-handling stake-test per Architect feedback)
5. `bwrap --die-with-parent --unshare-user --unshare-net --ro-bind / / -- /bin/sh -c 'getent hosts api.github.com 2>&1; exit 0'` produces network-failure output (verifying `--unshare-net` actually blocks)

If ANY of the 5 assertions fail, L1a [BLOCKED:reason] escalates to user before continuing. Recovery path: per §10 + Adaptation Criteria, fall back to "HAT-on-host (developer's WSL2)" scope-trim if no privilege model gets bwrap working in the container.

### Checkpoints

- [x] **C1a** — Dev container has `bwrap` installed and the 5-assertion CI compat probe passes after the docker-compose privilege grant per §10 (L1a)
- [x] **C1b** — F1 validator extended for `config.sandbox`; CLAUDE.md + agents.md updated with F3 contracts (sandbox profile schema, strict-by-default trust model, privilege-model decision, MCPSandbox protocol forward-reference) (L1b)
- [x] **C2** — `MCPSandbox` Protocol + `SandboxProfile` + `SpawnSpec` dataclasses landed; paper-exercise capability matrix in `base.py` module docstring + `agents.md`; stub `BubblewrapSandbox` raises `NotImplementedError` (L2)
- [x] **C3** — `BubblewrapSandbox.prepare_spawn()` compiles SandboxProfile into bwrap-shaped SpawnSpec; unit tests for arg compilation (8-10 cases including HOME override, namespace flags, cwd handling, error paths) (L3)
- [x] **C4** — `connect_stdio` integration: BubblewrapSandbox wraps the spawned process; `MCPSandboxError` boundary enforced per §6; F2's existing `mcp_fixture_stdio_params` updated; F2 stdio integration tests still pass under sandbox; double-flag bypass `THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1` works (L4)
- [x] **C5a** — `hello_server.py` extended with 3 test-only tools; integration tests for FS escape + env-allowlist + network refusal pass (L5a)
- [x] **C5b** — L6 stdio editor has Sandbox sub-section; UI tests cover save/edit round-trip; chip-list helper reuse confirmed (L5b)
- [ ] **C6** — L7 HAT walkthrough complete against a real third-party Python MCP server with the sandbox enforced

### Adaptation Criteria

**Divert if**:
- L1a's 5-assertion probe fails AFTER applying §10's docker-compose changes — escalate to user with diagnostic; consider scope-trim to "ship adapter contract + mocked tests + HAT-on-WSL2-host" per Architect-flagged fallback (mission criterion #38 verified via developer's WSL2 host where bwrap IS installed; container does mocked tests only)
- bubblewrap's `--die-with-parent` doesn't behave as advertised under our specific kernel/seccomp combination — F3 documents the gap; consider if F4's AsyncExitStack refactor needs to land first
- F4-compatibility surfaces a previously-unknown contract requirement (e.g., F4's pool needs to inspect sandbox profile for keying) — add the contract method (`profile_changed(old, new) -> bool` or similar) to `MCPSandbox` Protocol in L2 before locking
- L4's update of `mcp_fixture_stdio_params` breaks more F2 tests than expected — fall back to a co-fixture (`mcp_fixture_stdio_params_sandboxed`) that wraps but leaves the original unchanged; F4 then migrates F2 tests one at a time

**Acceptable variations**:
- L5a or L5b splitting further if leg-design LOC estimate exceeds 500 (per F1 debrief sizing recommendation)
- Adding a `provides_network_allowlist: bool = False` placeholder to `MCPSandbox` Protocol now (even though F3 doesn't implement per-host filtering) so a future routine-maintenance pass can flip it to `True` without changing the Protocol shape
- Refining the error-message catalog in §6 if integration tests surface ambiguous failure modes
- Skipping the `creation_flags` and `attribute_list` fields from `SpawnSpec` if the Architect-cycle-2 review finds the layer mismatch is overengineering for a Linux-only-shipping flight

### Legs

> **Note**: tentative suggestions, not commitments. Refined per leg as work progresses.
> **Conventions for all legs**: leg artifacts use anchor-by-symbol-name (NOT `file.py:LINE`) per F1 debrief recommendation; each leg's post-completion checklist includes lint clean (or "no NEW ruff errors") before `[HANDOFF:review-needed]` per F1 debrief Action Item; leg artifacts include "stake-test probe" scripts when integration tests stake on a specific OS/SDK pattern (per F2 debrief Recommendation #5).

- [x] `01a-ci-compat-probe-and-privilege-model` — Add `bubblewrap` to the Dockerfile apt install line. Update `docker-compose.yml` with `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` per §10. Rebuild the container. Run the 5-assertion CI compat probe inside the rebuilt container; confirm all 5 pass. Document the privilege-model rationale + diagnostic recipe in flight log. **NO code changes outside Dockerfile + docker-compose.yml**. Critical: this leg is a hard gate — if any probe fails, [BLOCKED:reason] before L1b proceeds.

- [x] `01b-f1-validator-extension-and-docs` — Extend F1's `_validate_mcp_source_config` (in `the_one/interfaces/web/api.py`) with a `config.sandbox` sub-block validator: `writable_paths: list[str]` if present (each entry a string; absolute-path-shape NOT enforced at API layer per F1's "trust the runtime" pattern), `network_allowed: bool` if present. Both fields default to safe values when absent. Add 2 new validation tests in `TestMCPSourceAPI`. Update `CLAUDE.md` and `agents.md` with F3 contracts: sandbox profile schema, strict-by-default trust model, privilege-model decision and dev/CI implications, `MCPSandbox` protocol forward-reference (L2 lands the actual Protocol; this leg references it in docs).

- [x] `02-sandbox-adapter-contract` — Create `the_one/platform/sandbox/{__init__.py, base.py}`. Define `SandboxProfile`, `SpawnSpec`, and `MCPSandbox` Protocol per §11 + §12. Paper-exercise capability matrix in `base.py` module docstring + `agents.md` cross-reference: env-allowlist / FS scope / network policy / process supervision × bubblewrap / sandbox-exec / AppContainer, with citations to bwrap(1), Apple Developer docs, Microsoft Learn. Stub `BubblewrapSandbox` (`NotImplementedError`) at `the_one/platform/sandbox/bubblewrap.py`. Add `MCPSandboxError(MCPClientError)` to `the_one/mcp/errors.py`. Re-export from `the_one/platform/sandbox/__init__.py`. Contract tests (~5): Protocol shape (presence of `prepare_spawn` method, return type, parameter types), `SandboxProfile.from_dict` factory handles missing/extra keys gracefully, `SpawnSpec` is frozen.

- [x] `03-bubblewrap-backend` — Implement `BubblewrapSandbox.prepare_spawn()` in `the_one/platform/sandbox/bubblewrap.py`. Compile `SandboxProfile` into bwrap-wrapped `SpawnSpec` per the Technical Approach. Verify `bwrap` binary exists via `shutil.which("bwrap")` at construction; raise `MCPSandboxError` if missing (per §6 message catalog). Apply HOME→/tmp override (§13). Unit tests for arg compilation (8-10 cases): no writable + no net (default profile), with writable + no net, with net + no writable, mixed, env clearing + setenv, HOME override, cwd handling (cwd inside ro-bind floor; cwd outside floor → error), namespace fields (pid_unshare=False allows bwrap to skip --unshare-pid), `bwrap` not found → `MCPSandboxError`. NO real subprocess in this leg — pure arg-compilation testing.

- [x] `04-connect-stdio-sandbox-integration` — Modify `the_one/mcp/transports/stdio.py::connect_stdio` to wrap via `BubblewrapSandbox.prepare_spawn(...)`. Read sandbox profile from `source.config.get("sandbox", {})`; instantiate `SandboxProfile.from_dict(...)` with safe defaults when absent. Sandbox is mandatory for stdio per §6 (no fallback) — UNLESS double-flag bypass `THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1` is set (per §10). Add error translation: `MCPSandboxError` raised by sandbox is re-raised; bwrap exec failures are translated per §6 boundary. **Update `mcp_fixture_stdio_params`** (in `tests/conftest.py`) — its return-shape signature stays unchanged (still a dict-like params object compatible with `StdioServerParameters(**params)`); ADD a **separate** `mcp_fixture_sandbox_profile` co-fixture providing the canonical strict floor (`SandboxProfile(writable_paths=[], network_allowed=False)`); F2 tests that need writable paths or network extend the profile per-test via fixture parametrization. Verify F2's existing 14 stdio integration tests still pass. Tests in this leg:
  - 1 real-subprocess integration test using `/bin/echo` (verifies bwrap-shaped SpawnSpec actually runs end-to-end)
  - ~6 mocked tests covering: (a) bwrap CLI shape correctness, (b) double-flag bypass WORKS when both flags set (sandbox skipped, bare subprocess spawns), (c) double-flag bypass DOES NOT trigger when only `THE_ONE_SANDBOX_DISABLED=1` is set, (d) double-flag bypass DOES NOT trigger when only `THE_ONE_TEST_MODE=1` is set, (e) `MCPSandboxError` boundary (sandbox-setup failures vs target-exec failures), (f) **SDK default env preservation through bwrap `--clearenv` + per-key `--setenv`** — mock `stdio_client` and assert the StdioServerParameters.env passed to it includes the SDK's `get_default_environment()` keys + allowlist + operator env, all surviving the bwrap setenv round-trip

- [x] `05a-fixture-extension-and-integration-tests` — Extend `tests/fixtures/mcp/hello_server.py` with three test-only tools: `write_outside_sandbox(path, content)`, `dump_env() -> dict[str, str]`, `try_connect(host, port) -> str`. Each marked `# TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION`. Integration tests in `tests/test_mcp_integration.py`: (a) FS escape via `write_outside_sandbox("/etc/test_escape", "x")` raises `MCPCallError` under default profile; (b) FS escape passes when `writable_paths` includes `/etc` (validates the writable-path mechanism actually works, not just that things fail); (c) env-allowlist invariant via `dump_env()` returns exactly `_ENV_ALLOWLIST + config.env + secrets` keys with HOME forced to `/tmp`; (d) network refusal via `try_connect("api.github.com", 443)` with `network_allowed=false` raises socket.gaierror or similar → `MCPCallError`; (e) network allowed: same call with `network_allowed=true` succeeds (skipped if CI env can't make outbound calls; conditional via `pytest.mark.network`). ~6-8 integration tests.

- [x] `05b-stdio-editor-sandbox-section` — Add Sandbox sub-section to `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` for stdio mode only. Two fields: `network_allowed` checkbox + `writable_paths` chip-list. Reuses `App.adminFormHelpers.renderChipListEditor`. Saves to `config.sandbox = {"network_allowed": bool, "writable_paths": list[str]}`. Cancel-revert and dirty-tracking participate in the existing edit-form lifecycle. Browser tests in `tests/browser/test_flow_studio_mcp_editor.py`: section renders for stdio (NOT for streamable-http); save round-trip (set network_allowed=true + writable_paths=["/data"] → API receives correct config.sandbox); edit round-trip (load existing source with sandbox profile → form fields populate correctly); empty defaults (new stdio source has unchecked network + empty writable_paths). ~6-8 browser tests.

- [ ] `06-hat-sandbox-real-server` *(optional but planned per user)* — Structured 5-step verification:
  1. Install a real third-party Python MCP server (e.g., `pip install mcp-server-fetch` if available, or any well-known PyPI MCP). Confirm it's NOT the in-repo fixture
  2. Configure as an stdio MCP source via the Studio MCP Servers UI. Set `network_allowed=true` (mcp-server-fetch needs HTTP outbound), `writable_paths=[]` (no FS writes for a fetch server)
  3. From a Python REPL inside the dev container, instantiate `MCPClient(source)` and `await client.connect()` — confirm `is_alive=True`, sandbox is enforced (verify by inspecting the bwrap-spawned subprocess's PID via `pgrep -f mcp-server-fetch` from the dev container's main shell, then `cat /proc/{pid}/ns/user` returns a non-host namespace ID)
  4. `await client.list_tools()` returns the third-party server's tool list
  5. `await client.call_tool(<tool>, {<args>})` succeeds for an allowed action; the same source with `network_allowed=false` then re-tested fails with `MCPCallError` for any network-using tool
  
  Bonus (optional): try a second source pointing at the same server but with `writable_paths=["/data/x"]`, `network_allowed=false`, and verify the FS scope is honored.
  
  Binary go/no-go: all 5 required steps pass = ✓; any step fails or produces unexpected output = file an issue and fix before flight close.

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L1a–L5b) completed; L6 HAT planned to run per user request
- [ ] All checkpoints (C1a, C1b, C2–C5b) met; C6 contingent on L6 outcome
- [ ] `bwrap` runs in dev container with §10's privilege grants; documented in flight log + CLAUDE.md
- [ ] `pytest --tb=no -q` green; new test count documented in flight-debrief; F2's existing stdio integration tests still pass
- [ ] `ruff check the_one/ tests/` clean (per-leg gate; no accumulated drift)
- [ ] CLAUDE.md and agents.md updated with F3 contracts
- [ ] F4 design has F3 prerequisites met; F4 leg design can proceed without re-opening F3 contracts

### Verification

How to confirm the flight achieved its objective:

1. **Unit + integration tests pass**: `pytest tests/test_mcp_*.py tests/test_db_api.py::TestMCPSourceAPI tests/browser/test_flow_studio_mcp_editor.py -v` — green
2. **F2 stdio integration tests still pass**: `pytest tests/test_mcp_integration.py -v` — all 14+ existing F2 tests pass under the new mandatory-sandbox path with the updated fixture
3. **Manual smoke**: in a Python REPL inside the dev container, build an `MCPSource(type="stdio", config={..., "sandbox": {"writable_paths": [...], "network_allowed": false}})`, `async with MCPClient(source) as c: await c.list_tools()` returns the fixture's tools. Then `await c.call_tool("write_outside_sandbox", {"path": "/etc/test", "content": "x"})` raises `MCPCallError` (sandbox refused at OS level)
4. **Sandbox-bypass regression**: confirm `THE_ONE_SANDBOX_DISABLED=1` ALONE doesn't bypass sandbox (must also set `THE_ONE_TEST_MODE=1`); confirm production code path never reads either flag
5. **L7 HAT smoke**: third-party server end-to-end works under sandbox (FS scope + network policy enforced as configured)
6. **Lint + existing-suite regression**: lint clean; F2's 1169 + 1 skipped test count grows by F3's net new tests (estimated +20-25), no regressions

The flight delivers the sandbox foundation that F4 (warm-pool will pool sandboxed processes), F5 (OAuth doesn't touch stdio sandbox; remote-only), and F6 (agent integration calls into sandboxed MCPClients) all consume. F4's L1 should bundle the AsyncExitStack disconnect refactor (F2 debrief Action Item) and validate that sandbox-spawned subprocess teardown is clean under pool eviction.
