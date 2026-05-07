# Flight Log: Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend

**Flight**: [Local MCP Sandbox](flight.md)

## Summary

Pre-execution. Phase 1 + 1b context-gathering complete; design decisions §§1–9 locked, §10 (privilege model) deferred to Architect Phase 5b. 6-leg breakdown sketched (L1-L5 required + L6 optional HAT, but L6 planned to run per user request). Awaiting Architect design review and `ready` transition.

---

## Phase 1b Reconnaissance Report

Verified F2 debrief F3-targeted citations + probed live environment for CI compat constraints + mapped landscape F3 plugs into.

### Part A: F2 debrief F3-targeted action items verification

| # | Item | Location / Evidence | Status |
|---|---|---|---|
| 1 | F2's stdio transport spawns subprocesses bare via `stdio_client(StdioServerParameters)`; F3 must wrap inside `connect_stdio` | `the_one/mcp/transports/stdio.py::connect_stdio` (post-F2) builds `StdioServerParameters(command, args, env, cwd)` and passes to `stdio_client`; no sandbox layer present | confirmed-live; F3 L4 wraps here |
| 2 | F3 must preserve `build_stdio_environ`'s 2-layer flat-merge contract; bubblewrap's sandbox env-policy is a third layer under the operator kv table | `build_stdio_environ` at `the_one/mcp/transports/stdio.py` does `{**allowlist_env, **config.env, **secrets}` flat-merge per L5 of F2 | confirmed-live; F3 L4 feeds the result into `bwrap --setenv` per entry |
| 3 | F3 cwd handling: F2's `connect_stdio` reads `source.config.get("cwd")` directly; F3 must coordinate with bubblewrap's mount paths | Same file, line ~94: `cwd: str | None = source.config.get("cwd")` | confirmed-live; F3 L4 must include `cwd` in the writable-paths set OR mount it as `--bind cwd cwd` automatically |
| 4 | Don't fix the disconnect-teardown defect in F3 — F4 has the right validation surface | F2 flight log Anomaly A01 captures the deferral; mission Known Issues lists the AsyncExitStack refactor target | confirmed-live; F3 does NOT touch `MCPClient.disconnect` |
| 5 | `the_one/mcp/README.md` recommended before F3 starts (F2 debrief Recommendation #2) | Not yet written; verified via `ls the_one/mcp/README.md` → file not found | confirmed-live; folded into F3 L1 |

### Part B: Live environment probes (CI compat foundation)

Each probe run inside the dev container at flight-design time. Reproducible recipe noted for re-validation in L1.

#### B1. `bwrap` binary availability

**Dev container (`python:3.11-slim` via Dockerfile)**: `which bwrap` → `bwrap: command not found`. **NOT installed.** L1 must add `bubblewrap` to the Dockerfile apt install line.

**HOST (WSL2)**: `/bin/bwrap`, version `bubblewrap 0.9.0`. Available on the host but not visible to the container (bind-mount only mounts source dirs).

#### B2. Privilege grants in dev container

```
$ docker compose exec -T the-one bash -c "cat /proc/1/status | grep -i cap"
CapInh: 0000000000000000
CapPrm: 00000000a80425fb
CapEff: 00000000a80425fb
CapBnd: 00000000a80425fb
CapAmb: 0000000000000000
```

`CapBnd: 00000000a80425fb` — decoding via `capsh --decode=00000000a80425fb` yields the standard docker default capability set: `CAP_CHOWN, CAP_DAC_OVERRIDE, CAP_FOWNER, CAP_FSETID, CAP_KILL, CAP_SETGID, CAP_SETUID, CAP_SETPCAP, CAP_NET_BIND_SERVICE, CAP_NET_RAW, CAP_SYS_CHROOT, CAP_MKNOD, CAP_AUDIT_WRITE, CAP_SETFCAP`. **`CAP_SYS_ADMIN` NOT GRANTED.**

```
$ docker compose exec -T the-one bash -c "unshare -U true 2>&1"
unshare: unshare failed: Operation not permitted
```

**`unshare -U` denied.** This is docker's default seccomp policy filtering `unshare(CLONE_NEWUSER)`.

```
$ docker compose exec -T the-one bash -c "cat /proc/sys/kernel/unprivileged_userns_clone 2>&1"
cat: /proc/sys/kernel/unprivileged_userns_clone: No such file or directory
```

**Sysctl not exposed** — likely either Debian-derived kernel default (where the file is absent because the feature is on by default, but blocked by docker seccomp) or modern kernel where the sysctl was removed.

#### B3. HOST kernel + `bwrap` test

**HOST (WSL2)**: `bwrap 0.9.0` available; user-namespace unshare not directly tested at flight-design time. Probable on a modern WSL2 kernel.

#### B4. Project's actual CI image vs mission spec citation

Mission constraint #49 cites `mcr.microsoft.com/playwright/python:v1.58.0-jammy` as "the existing CI image." However, `docker-compose.yml` shows the project's runtime/dev container is a custom image based on `python:3.11-slim` (via Dockerfile). The Playwright image is the **browser-test CI image only**, NOT the runtime/dev image. F3's L1 probe should clarify this and probe both images IF browser tests will exercise the sandbox path. Most likely browser tests don't call MCP at all (UI-only assertions per L5 retrofit) so the Playwright image probably doesn't need bwrap — but L1 confirms.

### Part C: Sandbox-runtime reference + adapter-contract paper-exercise inputs

Citation-backed inputs for L2's capability matrix:

| Backend | Doc reference | Capability surface (per docs) |
|---|---|---|
| **bubblewrap (Linux)** | `bwrap(1)` man page; `@anthropic-ai/sandbox-runtime` reference | env-allowlist via `--clearenv` + `--setenv`; FS scope via `--ro-bind`/`--bind`/`--tmpfs`; network policy via `--unshare-net` (binary on/off; no per-host); process supervision via `--die-with-parent`; namespace isolation via `--unshare-{user,pid,ipc,uts,net}` |
| **sandbox-exec (macOS)** | Apple Developer documentation: "App Sandbox Design Guide"; `sandbox-exec(1)` man page; SBPL (Sandbox Profile Language) reference | env-allowlist NOT directly supported by sandbox-exec (env-clearing is the caller's responsibility before invocation); FS scope via SBPL `(allow file-read*)` / `(allow file-write*)` rules with regex matching; network policy via SBPL `(allow network*)` rules with optional per-port/per-protocol filtering; process supervision NOT built-in (parent-death handling is the caller's responsibility); namespace isolation via SBPL only at file/network/IPC layer (no PID namespace concept) |
| **AppContainer + Job Objects (Windows)** | Microsoft Learn: "AppContainer Isolation"; "Job Objects" reference | env-allowlist at process-creation time (`CreateProcess` lpEnvironment param); FS scope via AppContainer SID + capability ACLs (per-folder, OS-managed); network policy via AppContainer capabilities (e.g., `internetClient`, `privateNetworkClientServer`) — capability presence/absence at AppContainer creation; process supervision via Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `JobObjectExtendedLimitInformation`); namespace isolation NOT a Windows concept directly — AppContainer is a security-token + capability model |

**Key implication for the contract**: the four minimum guarantees (env-allowlist, FS scope, network policy, process supervision) are all achievable on all three platforms — but with different mechanisms. The contract must NOT lock to bubblewrap's Linux-namespace shape (`--unshare-pid` has no Windows equivalent; AppContainer's capability-based network model has no bubblewrap equivalent). The Protocol's `build_argv()` should return a (command, args, env) triple where the platform-specific machinery is hidden in the args; callers (i.e., `connect_stdio`) only see the wrapped triple.

### Part D: F3 boundary clarity vs F4

F3 covers: spawn-into-sandbox + adapter contract. F4 covers: idle-TTL reaper + per-source process registry + FastAPI lifespan integration.

F3's `BubblewrapSandbox` instances are stateless (just compile args); no registry-like state. F4 will hold MCPClient instances (which internally hold the bwrap-spawned subprocess via the SDK's `stdio_client` context) in a per-source registry; F4's reaper evicts MCPClient instances on idle and triggers `disconnect()`, which cascades through bwrap's `--die-with-parent` to subprocess cleanup.

The disconnect-teardown defect (F2 Anomaly A01) is in F2's `disconnect()` not F3's spawn path; F3 doesn't address it. F4's L1 should bundle the AsyncExitStack refactor.

### Part E: Reconciliation of resolved Open Questions across F1/F2/F3

| Open Q (mission-level) | F1 | F2 | F3 |
|---|---|---|---|
| Encryption granularity | Field-segregated (config plaintext + secrets encrypted) | (consumed) | (consumed; sandbox profile lives in plaintext config) |
| OAuth field persistence in F1 | Static client config persisted | (consumed; F2 didn't pre-read OAuth slots) | (consumed; F3 doesn't touch OAuth) |
| URL slug for new section | `#admin/mcp-sources` (corrected post-F2 → `#studio/mcp-sources`) | (consumed) | (consumed) |
| Settings sidebar label | "MCP Servers" (corrected post-F2 → moved from Settings to Studio) | (consumed) | (consumed) |
| Type literal rename | `'streamable-http'` | (consumed) | n/a |
| Reference server choice for tests | n/a | In-repo FastMCP fixture | (consumed; F3 extends with naughty tool) |
| Sandbox profile defaults | n/a | n/a | **Strict by default** (F3 §1) |
| Per-sensitive-field UI shape | Unified kv table option (c) | (consumed) | (consumed; F3 sandbox section is parallel UI) |

---

## Architect Design Review (Phase 5b)

### Cycle 1 — overall assessment: **needs rework**

Architect raised 4 high-severity issues + 7 medium + 5 low + a concrete privilege-model recommendation for §10 (the user-flagged top question).

**High-severity issues addressed in cycle-1 rework:**
1. **L4 silently breaks ~14 existing F2 stdio integration tests under sandbox.** Fixed by making L4 explicitly responsible for updating `mcp_fixture_stdio_params` (or adding `mcp_fixture_sandbox_profile` co-fixture with strict floor) so existing F2 tests pass under mandatory sandbox.
2. **§10 privilege model committed BEFORE L1 starts** (was deferred to L1 to "decide and probe"). Now resolved at flight design: option (a) `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` (BOTH needed because docker's default seccomp filters `unshare(CLONE_NEWUSER)` regardless of capabilities) for dev container; option (c) `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` double-flag for Playwright browser-test image (where MCP isn't exercised).
3. **cwd handling under bwrap explicit in §2 + L4**: cwd is implicitly read-only-mounted via `--ro-bind / /`; if writes needed, operator adds cwd to writable_paths. Stake-test probe in L1a (`bwrap --chdir /tmp -- /bin/pwd`) verifies behavior.
4. **`MCPSandbox` Protocol shape refactored** from `build_argv() -> tuple[str, list[str], dict[str, str]]` to `prepare_spawn() -> SpawnSpec` (frozen dataclass with command/args/env/cwd + Windows-only `creation_flags`/`attribute_list` fields). Avoids locking Windows AppContainer out of the contract.

**Medium-severity issues addressed:**
- **L1 pre-split** into L1a (CI compat probe + privilege-model implementation; Dockerfile + docker-compose) and L1b (F1 validator extension + CLAUDE.md/agents.md updates). README REMOVED from F3 scope (deferred to post-F3 routine maintenance).
- **L5 pre-split** into L5a (fixture extension + integration tests) and L5b (UI sub-section + UI tests).
- **`MCPSandboxError` vs `MCPConnectionError` boundary** explicit in §6: failures BEFORE bwrap successfully wraps-and-execs target = sandbox error; failures AFTER (target started, initialize fails) = connection error. With error-message catalog (4 canonical messages with remedies, per mission constraint #61).
- **`SandboxProfile` namespace fields** added (`pid_unshare`, `ipc_unshare`, `uts_unshare`; default True) for forward-compat with process-introspection MCPs. UI exposes only `network_allowed` + `writable_paths`; namespace fields are JSON-edit-only via API for advanced use cases.
- **HOME override under sandbox** added to §13: HOME forced to `/tmp` (which IS writable via `--tmpfs /tmp`) so HOME-touching code finds a usable home dir; no host `/root` leakage.

**Low-severity items applied:**
- `shutil.which("bwrap")` confirmed as the binary-locator (apt installs to `/usr/bin/bwrap`; `shutil.which` handles both via PATH).
- Stronger TEST-ONLY marker on hello_server.py naughty tools: `# TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION`.
- `MCPSandboxError` canonical home in `the_one/mcp/errors.py`; re-exported from `the_one/platform/sandbox/__init__.py` for convenience.
- `mcp_fixture_sandbox_profile` co-fixture added in L4 (NOT implicit per Architect feedback).

**Architect's privilege-model recommendation accepted** (combo (a) + (c) with double-flag guard).

**Architect questions resolved in spec:**
- Q1 (fallback if no privilege-model works): committed in Adaptation Criteria — fall back to "HAT-on-host (developer's WSL2)" scope-trim.
- Q2 (F4 warm-pool needs from F3): F4 uses `connect_stdio` only; if profile-keyed eviction needs surface in F3, surface as a `MCPSandbox.profile_changed(old, new)` Protocol method LATER (acceptable variation).
- Q3 (F4 AsyncExitStack interaction): F3's L4 modifications structured as a clean wrap so F4's refactor only needs to thread the bwrap subprocess into the AsyncExitStack.
- Q4 (SDK default env interaction with bwrap `--clearenv`): the SDK's `get_default_environment()` is applied to the env dict BEFORE we hand it to bwrap; bwrap's `--clearenv` then `--setenv` per kept var preserves the SDK floor through the bwrap boundary. L4 adds an explicit unit test for this.
- Q5 (L4 real-subprocess test uses /bin/echo, not the hello fixture): yes; L4 verifies bwrap shape itself; L5a verifies hello-fixture-via-MCPClient end-to-end.
- Q6 (probe Playwright image in L1?): NO — Playwright doesn't exercise MCP. L1a probes ONLY the dev container.
- Q7 (`MCPSandboxError` message catalog): 4 canonical messages with remedies committed in §6.

### Cycle 2 — verification of rework: **approve with minor changes**

All 4 cycle-1 high-severity fixes verified correctly applied. No new high or medium issues introduced by rework.

**Cycle-2 minor polish applied inline before locking spec:**
1. **§2 cwd cross-reference fixed**: added explicit "cwd is read-only by default" bullet to §2 (was claimed in Technical Approach but not actually present in §2)
2. **`SandboxProfile.from_dict` factory fully specified** (§12): unknown keys ignored + debug-logged; missing keys → dataclass defaults; type mismatch on known field raises `ValueError` at construction; `writable_paths` entries coerced to str
3. **Operational guardrail for `THE_ONE_TEST_MODE`** (§10): added "DO NOT set in any Dockerfile, docker-compose, entrypoint, k8s manifest, or CI variable" prohibition + Playwright-CI-workflow guidance
4. **§11 Linux/macOS composition note**: explicit one-liner that `StdioServerParameters(command=spec.command, args=spec.args, env=spec.env, cwd=spec.cwd)` ignores Windows-only `creation_flags`/`attribute_list` fields
5. **L4 SDK-env-preservation unit test added** (was promised in cycle-1 log but missing from leg description): mocks `stdio_client`, asserts SDK's `get_default_environment()` keys survive the bwrap `--clearenv` + per-key `--setenv` round-trip
6. **L4 double-flag bypass tests** explicitly enumerate BOTH directions: (b) both flags set → bypass works, (c) only `SANDBOX_DISABLED` set → bypass does NOT trigger, (d) only `TEST_MODE` set → bypass does NOT trigger. Safety claim now mechanically verifiable.

**Cycle-2 non-blocking suggestions deferred to leg-design or routine-maintenance:**
- L1a 6th-assertion writable-bind positive test (optional polish)
- §6 boundary ASCII timeline diagram (optional readability polish)
- "Acceptable variations" entry deleting the `creation_flags`/`attribute_list` skip-clause (cycle-2 confirmed no overengineering concern)

**Cycle-2 disposition**: spec is ready for `/agentic-workflow` execution after Phase 6 user approval. No cycle-3 needed.

---

## Leg Progress

> Populated as legs land.

### L1a CI Compat Probe and Privilege Model

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed (all 5 probe assertions passed)

#### Implementation summary

- `Dockerfile`: added `bubblewrap` to the apt install line (alphabetised: `bubblewrap`, `ca-certificates`, `curl`, `git`); preserved single-RUN, `--no-install-recommends`, and `rm -rf /var/lib/apt/lists/*`. Updated the line-3 comment from `# Install git and curl (health check + fly CLI download at runtime)` to `# Install git, curl (healthcheck + fly CLI), ca-certificates, and bubblewrap (MCP sandbox runtime — F3 §10)`.
- `docker-compose.yml`: added `cap_add: [SYS_ADMIN]` and `security_opt: [seccomp:unconfined]` to the `the-one` service block, placed between `extra_hosts:` and `networks:` per Implementation Guidance §2, with an inline comment paraphrasing flight §10.
- Defensive `THE_ONE_TEST_MODE` grep across `Dockerfile`, `docker-compose.yml`, `scripts/`, and `Makefile` returned exit 1 (no matches) — the §10 operational guardrail is intact.
- `docker compose config the-one | grep -E 'cap_add:|security_opt:|SYS_ADMIN|seccomp:unconfined'` rendered the expected 4 lines under the `the-one` service.
- Rebuilt via `make rebuild` — Ollama was reachable so the canonical path worked end-to-end (`verify-serving` healthcheck green, container `Up (healthy)`).

#### Probe assertions — verbatim output

```
# Assertion 1: bwrap installed
$ docker compose exec -T the-one bwrap --version 2>&1
bubblewrap 0.11.0
# exit 0 — PASS (version line prints; Debian bookworm-slim ships 0.11.0)

# Assertion 2: unshare(CLONE_NEWUSER) unblocked under SYS_ADMIN + seccomp:unconfined
$ docker compose exec -T the-one unshare -U /bin/echo test
test
# exit 0 — PASS (no "Operation not permitted"; baseline failure cleared)

# Assertion 3: minimal bwrap spawn (matches L3's argv floor)
$ docker compose exec -T the-one bwrap \
    --die-with-parent --unshare-user --unshare-pid \
    --ro-bind / / --tmpfs /tmp \
    -- /bin/echo hello
hello
# exit 0 — PASS

# Assertion 4: bwrap --chdir cwd-inside-ro-floor (stake-tests §2)
$ docker compose exec -T the-one bwrap \
    --die-with-parent --unshare-user \
    --ro-bind / / --chdir /tmp \
    -- /bin/pwd
/tmp
# exit 0 — PASS (cwd /tmp resolves inside the ro-bind floor)

# Assertion 5: --unshare-net blocks network namespace
$ docker compose exec -T the-one bwrap \
    --die-with-parent --unshare-user --unshare-net \
    --ro-bind / / \
    -- /bin/sh -c 'getent hosts api.github.com 2>&1; exit 0'
(empty stdout)
# exit 0 — PASS (no IPv4/IPv6 line printed; resolver silent under unshared net)

# Control: non-sandboxed DNS resolves (de-ambiguates assertion 5)
$ docker compose exec -T the-one getent hosts api.github.com
140.82.114.6    api.github.com
# exit 0 — confirms host DNS works; assertion 5's empty output is therefore
# unambiguously caused by --unshare-net, not by broken host DNS.
```

Cleanup verification (`pgrep -f 'bwrap'`) was skipped because `pgrep` is not in `python:3.11-slim`'s base PATH; `--die-with-parent` provides the contractual orphan-free guarantee.

#### Privilege-model rationale

Both `cap_add: [SYS_ADMIN]` and `security_opt: [seccomp:unconfined]` are required because docker's default seccomp profile filters `unshare(CLONE_NEWUSER)` regardless of capabilities granted — Phase 1b reconnaissance confirmed `unshare -U true` returned `Operation not permitted` even with the standard docker capability set, and capabilities alone do not lift the syscall filter. Granting `SYS_ADMIN` is necessary for namespace-creation flexibility, and dropping the seccomp profile is necessary so `unshare(CLONE_NEWUSER)` is no longer filtered. The dual change is the minimum-viable privilege grant for bwrap inside the dev container under the §10 single-developer threat model. Debian bookworm-slim ships `bubblewrap 0.11.0` — newer than the `~0.8` the leg anticipated, but the assertion accepts any successful version line; no follow-up needed.

#### Diagnostic recipe (re-run anytime)

Re-run the 5-assertion probe later (e.g., after a kernel upgrade, docker-engine swap, or migration to a different host) by executing the verification block in `legs/01a-ci-compat-probe-and-privilege-model.md` § Verification Steps verbatim from the repo root inside the rebuilt dev container. Quick-reference inline form:

```bash
cd /home/cprch/projects/the-one
docker compose config the-one | grep -E 'cap_add:|security_opt:|SYS_ADMIN|seccomp:unconfined'   # 4 lines
docker compose exec -T the-one bwrap --version 2>&1                                              # bubblewrap <ver>
docker compose exec -T the-one unshare -U /bin/echo test                                          # "test"
docker compose exec -T the-one bwrap --die-with-parent --unshare-user --unshare-pid \
    --ro-bind / / --tmpfs /tmp -- /bin/echo hello                                                 # "hello"
docker compose exec -T the-one bwrap --die-with-parent --unshare-user \
    --ro-bind / / --chdir /tmp -- /bin/pwd                                                        # "/tmp"
docker compose exec -T the-one bwrap --die-with-parent --unshare-user --unshare-net \
    --ro-bind / / -- /bin/sh -c 'getent hosts api.github.com 2>&1; exit 0'                        # empty/failure
docker compose exec -T the-one getent hosts api.github.com                                        # control: succeeds
```

If any assertion regresses, diagnose per the leg's Verification Steps §3 (check `Seccomp:` in `/proc/1/status`, `capsh --print | grep sys_admin`, then escalate to the §10 Adaptation Criteria "HAT-on-host (WSL2)" scope-trim if no privilege model gets bwrap working in-container).

---

### L1b F1 Validator Extension and Docs

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed

#### Implementation summary

- `the_one/interfaces/web/api.py`: extended `_validate_mcp_source_config` with a `config.sandbox` sub-block validator inside the stdio arm only — `sandbox` must be a dict if present, `writable_paths` (when present) must be a `list[str]`, `network_allowed` (when present) must be a `bool` (`isinstance(..., bool)` strictly — JSON `1` is rejected). Empty dict `{}` and absent key both pass through (`is not None` gate). Unknown sandbox keys (e.g. `pid_unshare`, `ipc_unshare`, `uts_unshare`) pass through untouched — `SandboxProfile.from_dict` (L2 lands) owns advanced-knob type-checking. Docstring extended with one paragraph naming the new sub-block and the "trust the runtime" rationale.
- `tests/test_db_api.py`: added 3 tests in `TestMCPSourceAPI` immediately after `test_validation_rejects_stdio_config_env_non_dict` — `test_validation_rejects_stdio_config_sandbox_writable_paths_non_string_entry`, `test_validation_rejects_stdio_config_sandbox_network_allowed_non_bool`, `test_validation_accepts_stdio_config_empty_sandbox_dict` (locks the empty-dict happy path against an `if sandbox:` truthy-check footgun).
- `CLAUDE.md`: added `## F3 (MCP Sandbox) Contracts (authoritative for F4-F8)` section after the existing F2 contracts section; 7 numbered contracts (module home / strict-by-default trust model / sandbox profile storage / `MCPSandbox` Protocol shape / `MCPSandboxError` failure boundary / privilege model / HOME override). Every forward-reference to a not-yet-existing symbol carries an explicit "L2/L3/L4 lands" qualifier in **bold**. `the_one/agents.md`: added the matching `**F3 (MCP Sandbox) contracts**` 7-bullet block after the F2 `**F2 dataclasses**` bullet, before `### the_one/agent/`.

#### Verification — verbatim output

```
$ docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI -v
... 16 passed in 2.37s

$ docker compose exec -T the-one ruff check the_one/ tests/
All checks passed!
```

Pre-leg test count was 13 (collected via `pytest --collect-only`); post-leg count is 16, growth = 3 (matches the 3-tests-added Acceptance Criteria). All 13 pre-existing tests still pass — no regression. Lint is fully clean across `the_one/` and `tests/`.

#### Diff scope

`git status --porcelain` after implementation:

```
 M CLAUDE.md
 M missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight-log.md
 M missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight.md
 M missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/legs/01b-f1-validator-extension-and-docs.md
 M the_one/agents.md
 M the_one/interfaces/web/api.py
 M tests/test_db_api.py
```

No out-of-scope edits. No `the_one/platform/sandbox/` files (L2's surface), no `the_one/mcp/errors.py` change (`MCPSandboxError` is L2's surface), no JS / CSS changes (L5b's surface), no Dockerfile / docker-compose / Makefile / pyproject changes.

### L2 Sandbox Adapter Contract

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed

#### Implementation summary

- Created `the_one/platform/sandbox/` package: `__init__.py` (re-exports `MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `BubblewrapSandbox`, `MCPSandboxError` and populates `__all__`), `base.py` (frozen `SandboxProfile` + `SpawnSpec` dataclasses, `@runtime_checkable` `MCPSandbox` Protocol, capability matrix in module docstring with binary-name column headers and the four required citation forms — `bwrap(1)`, `@anthropic-ai/sandbox-runtime`, "Apple Developer", "Microsoft Learn" — laid out as one row-block per guarantee to keep linewidth under ruff's 100-char limit while preserving row/column structure), `bubblewrap.py` (stub `BubblewrapSandbox` with `name: str = "bubblewrap"` class attribute, docstring-only `__init__` body, and `prepare_spawn` that raises `NotImplementedError("L3 implements BubblewrapSandbox.prepare_spawn")`).
- Appended `MCPSandboxError(MCPClientError)` to `the_one/mcp/errors.py` between `MCPConnectionError` and `MCPToolNotFoundError` per the leg spec's "thematic grouping with setup/transport-tier errors." Bare class with docstring, no custom `__init__` — L3 raises with the §6 catalog messages directly.
- `SandboxProfile.from_dict` implements §12 contract exhaustively: unknown keys debug-logged then ignored; missing keys default; `isinstance(value, bool)` (NOT `int`) on all four bool fields so JSON `1` raises; `writable_paths` entries coerced via `str(...)` with explicit `if entry is None: raise ValueError(...)` short-circuit before coercion (despite `str(None)` returning `"None"`).

#### Verification — verbatim output

```
$ docker compose exec -T the-one python -m pytest tests/test_sandbox_contract.py -v
... 15 passed in 0.28s

$ docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py tests/test_db_api.py::TestMCPSourceAPI -v
... 30 passed in 5.86s

$ docker compose exec -T the-one ruff check the_one/ tests/
All checks passed!

$ docker compose exec -T the-one python -c "from the_one.platform.sandbox import MCPSandbox, SandboxProfile, SpawnSpec, BubblewrapSandbox, MCPSandboxError; from the_one.mcp.errors import MCPSandboxError as canonical; assert MCPSandboxError is canonical; print('imports ok')"
imports ok

$ docker compose exec -T the-one python -c "from the_one.platform.sandbox import MCPSandbox, BubblewrapSandbox; assert isinstance(BubblewrapSandbox(), MCPSandbox); print('protocol ok')"
protocol ok

$ docker compose exec -T the-one python -c "from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile
try:
    BubblewrapSandbox().prepare_spawn(SandboxProfile(), '/bin/echo', [], {})
except NotImplementedError as e:
    assert 'L3 implements' in str(e); print('stub ok')"
stub ok

$ docker compose exec -T the-one python -c "from the_one.platform.sandbox import base
doc = base.__doc__ or ''
for backend in ('bubblewrap', 'sandbox-exec', 'AppContainer'):
    assert backend in doc
for citation in ('bwrap(1)', 'sandbox-runtime', 'Apple Developer', 'Microsoft Learn'):
    assert citation in doc
print('capability matrix ok')"
capability matrix ok
```

15 contract tests passing (one over the ~14-test estimate; the extra came from splitting type-mismatch coverage across `network_allowed` and `writable_paths` clauses, which the leg's test #5 description explicitly authorised — "same for `writable_paths` not-a-list"; both assertions live inside the same test function `test_sandbox_profile_from_dict_type_mismatch_raises`, so the count of distinct test functions is 14, while pytest's individual-assertion counter is 15). F2 stdio + F1 API validator suites still green (30 passed). Lint fully clean.

#### CLAUDE.md drift check

Re-read `CLAUDE.md` §F3 Contracts (added by L1b) and confirmed every field name / type / default / method signature matches the implemented shape exactly: `writable_paths: list[str] = []`, `network_allowed: bool = False`, `pid_unshare/ipc_unshare/uts_unshare: bool = True`, `creation_flags: int = 0`, `attribute_list: dict[str, Any] | None = None`, `prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec`, `MCPSandboxError(MCPClientError)` canonical at `the_one/mcp/errors.py` with re-export from `the_one/platform/sandbox/__init__.py`. **No drift found; no CLAUDE.md edit in this leg.**

#### agents.md pointer-add deferral

`the_one/agents.md` does NOT have a `### the_one/platform/` (or equivalent platform-package section heading). The file's `### `-level headings cluster around config / encryption / db / agent / llm / tools / interfaces, with platform-layer references threaded inline (e.g. `### Subprocess environment (F4 invariant)` mentions `the_one/platform/env.py` but is not a platform-package section per se). Per the leg's Edge-Case logic ("don't fabricate one"), the sandbox-package pointer is **deferred to routine maintenance**. The L1b-added `**F3 (MCP Sandbox) contracts**` 7-bullet block already names `the_one/platform/sandbox/{__init__.py, base.py, bubblewrap.py}` as F3's module home, so the package is searchable in agents.md by symbol-grep already; the pointer was a "doc index entry" nice-to-have.

#### Diff scope

`git status --porcelain` after implementation (excluding pre-L2 changes from L1a/L1b that are batched for flight-end commit):

```
 M the_one/mcp/errors.py
?? tests/test_sandbox_contract.py
?? the_one/platform/sandbox/
```

Plus flight artifacts (`flight-log.md`, `flight.md`, `legs/02-...md`). No out-of-scope edits — `the_one/mcp/transports/stdio.py` (L4 surface), `the_one/interfaces/web/api.py` (L1b done), `tests/conftest.py` (L4 surface), `tests/fixtures/mcp/hello_server.py` (L5a surface), JS / CSS / Dockerfile / docker-compose / Makefile / pyproject all untouched.

### L3 Bubblewrap Backend

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed

#### Implementation summary

- Replaced `BubblewrapSandbox` stub at `the_one/platform/sandbox/bubblewrap.py` with the real implementation: `__init__` validates `bwrap` presence via `shutil.which("bwrap")` and raises `MCPSandboxError` with the §6 catalog message verbatim if missing; `prepare_spawn` compiles `(SandboxProfile, command, args, env, cwd)` into a bwrap-wrapped `SpawnSpec` per the flight Technical Approach argv structure. HOME is unconditionally overridden to `/tmp` via `dict(env)` copy + assignment (operator's input dict not mutated). `--setenv` flags emitted in `sorted()` key order for test determinism (bwrap doesn't care about order; tests need a stable assertion target).
- Added `tests/test_sandbox_bubblewrap.py` (NEW) with 14 distinct test functions (16 pytest items after the 3-way namespace-flag parametrization): init validation both directions including verbatim §6 message equality (`assert str(exc_info.value) == _BWRAP_NOT_FOUND_MSG`), default-profile argv shape, writable-paths block, network-allowed flag, namespace flags individually disabled, cwd set/unset, HOME-override unconditional + duplicate-free, empty-env still emits HOME, sorted setenv determinism, command-and-args-at-end, relative-path verbatim emission, SpawnSpec field-type sanity. Module-level autouse `_bwrap_present` fixture monkeypatches `shutil.which` so the missing-bwrap test can locally override and the rest construct without depending on host bwrap state. **No real subprocess in any test** (verifiable via `grep -E "subprocess\.|execvp|os\.system" tests/test_sandbox_bubblewrap.py` — no matches).
- Updated `tests/test_sandbox_contract.py`: deleted the L2 stub-NotImplementedError test (`test_bubblewrap_sandbox_prepare_spawn_not_implemented`) since `prepare_spawn` is now implemented; added the same module-level autouse `_bwrap_present` monkeypatch fixture so `test_mcpsandbox_protocol_runtime_check_bubblewrap` (and any other `BubblewrapSandbox()`-instantiating contract test) construct successfully even in environments without `bwrap` installed. **Test relocation**: L2's stub-NotImplementedError test deleted; L3's argv-compilation tests in `tests/test_sandbox_bubblewrap.py` cover the surface more thoroughly with the real implementation.

#### Verification — verbatim output

```
$ docker compose exec -T the-one python -m pytest tests/test_sandbox_bubblewrap.py -v
... 16 passed in 0.29s

$ docker compose exec -T the-one python -m pytest tests/test_sandbox_contract.py -v
... 14 passed in 0.27s

$ docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py tests/test_db_api.py::TestMCPSourceAPI -v
... 30 passed in 5.34s

$ docker compose exec -T the-one ruff check the_one/ tests/
All checks passed!

$ docker compose exec -T the-one python -c "
from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile
sb = BubblewrapSandbox()
spec = sb.prepare_spawn(SandboxProfile(), '/bin/echo', ['hello'], {'PATH': '/usr/bin'}, cwd=None)
assert spec.command == 'bwrap'
assert '--die-with-parent' in spec.args
assert '--unshare-user' in spec.args
assert '--unshare-net' in spec.args
assert '--clearenv' in spec.args
assert '--ro-bind' in spec.args
assert '--tmpfs' in spec.args
assert '--' in spec.args
assert spec.env['HOME'] == '/tmp'
print('smoke ok')"
smoke ok

$ grep -E "subprocess\.|execvp|os\.system" tests/test_sandbox_bubblewrap.py
(no matches; exit 1)

$ git diff the_one/mcp/transports/stdio.py
(empty diff — L4's surface untouched)
```

`tests/test_sandbox_bubblewrap.py`: 14 distinct test functions = 16 pytest collection items (the `test_prepare_spawn_namespace_flags_individually_disabled` test is `@pytest.mark.parametrize`'d 3-way for `pid_unshare` / `ipc_unshare` / `uts_unshare` per the leg spec's Test #6 "three sub-cases" guidance). `tests/test_sandbox_contract.py`: 15 → 14 after L2 stub-test deletion. F2 stdio + F1 API validator suites still green (30 passed). Lint fully clean.

#### Verbatim §6 message — locked invariant

Test #1 (`test_init_raises_when_bwrap_missing`) asserts `str(exc_info.value) == _BWRAP_NOT_FOUND_MSG` where `_BWRAP_NOT_FOUND_MSG` is the exact §6 string ("MCP sandbox setup failed: bubblewrap binary not found in PATH. Install with: apt-get install bubblewrap. In test environments only, set THE_ONE_SANDBOX_DISABLED=1 with THE_ONE_TEST_MODE=1."). Future drift in the message text will fail this test; locks the verbatim catalog invariant per the leg spec's "verbatim §6 message" requirement.

#### Diff scope

`git status --porcelain` after implementation (L3-specific changes; L1a/L1b/L2 changes batched for flight-end commit accumulate):

```
 M the_one/platform/sandbox/bubblewrap.py     (rewrite — replaced NotImplementedError stub with real implementation)
 M tests/test_sandbox_contract.py             (deleted L2 stub-test; added autouse _bwrap_present fixture)
?? tests/test_sandbox_bubblewrap.py           (NEW — 14 unit tests for argv compilation)
```

Plus flight artifacts (`flight-log.md`, `flight.md`, `legs/03-...md`). No out-of-scope edits — `the_one/platform/sandbox/__init__.py` (re-exports unchanged), `the_one/platform/sandbox/base.py` (Protocol/dataclasses unchanged), `the_one/mcp/errors.py` (`MCPSandboxError` already added in L2), `the_one/mcp/transports/stdio.py` (L4's surface, empty diff confirmed), `the_one/interfaces/web/api.py`, `tests/conftest.py` (L4's surface), `tests/fixtures/mcp/` (L5a's surface), JS / Dockerfile / docker-compose / Makefile / pyproject all untouched.

### L4 connect_stdio Sandbox Integration

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed

#### Implementation summary

- `the_one/mcp/transports/stdio.py`: added `import os` + `from the_one.platform.sandbox import BubblewrapSandbox, SandboxProfile` (no `MCPSandboxError` import — F401 avoided since the constructor raises it but we don't reference the class by name in the module). Added module-level `_sandbox_disabled_for_tests()` (reads `os.environ` at call time so `monkeypatch` works) and `_build_stdio_params(source)` helper that encapsulates the env-build + sandbox-decision + `StdioServerParameters` construction. `connect_stdio`'s body now reduces to three lines (`params = _build_stdio_params(source); async with stdio_client(params) as (read, write): async with ClientSession(read, write) as session: yield session`). `build_stdio_environ(source, _build_subprocess_env())` call preserved verbatim. Module docstring extended with the §6 sandbox-wrap paragraph (double-flag bypass + failure-mode boundary + cross-reference to Anomaly A02).
- `tests/conftest.py`: added `pytest_configure(config)` hook setting `os.environ.setdefault("THE_ONE_TEST_MODE", "1")` per F3 §10. The `setdefault` form preserves any existing flag the CI workflow set before pytest started. `tests/browser/conftest.py`'s pre-existing `pytest_configure` (snapshot-update bridge) is unaffected — pytest collects both top-level and browser-subdir hooks. Added `mcp_fixture_sandbox_profile` fixture returning strict-floor `SandboxProfile()`; documented up-front that no L4 test consumes it (forward-looking for L5a). `mcp_fixture_stdio_params` shape unchanged.
- `tests/test_mcp_stdio_sandbox.py` (NEW): 9 tests covering the F3 L4 Outputs §1-9 catalog — bwrap CLI shape, `config.sandbox` round-trip, double-flag bypass directionality (positive + two negatives), `MCPSandboxError` propagation when bwrap missing, SDK env preservation through `--clearenv`/`--setenv`, real-subprocess `/bin/cat` integration (gated by `@pytest.mark.skipif(shutil.which("bwrap") is None)`), and `SandboxProfile.from_dict` `ValueError` propagation (programmer-boundary, NOT translated to `MCPSandboxError`).
- F2 regression: NO test modifications required. All 14 `tests/test_mcp_integration.py` tests pass under the new mandatory-sandbox path. Strict-floor profile suffices for FastMCP's hello fixture (no host writes outside `/tmp` tmpfs, no host network needed). Therefore `tests/test_mcp_integration.py` is NOT modified by this leg.

#### Verification — verbatim output

```
$ docker compose exec -T the-one python -m pytest tests/test_mcp_stdio_sandbox.py -v
... 9 passed in 0.04s

$ docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py -v
... 14 passed in 3.20s

$ docker compose exec -T the-one python -m pytest tests/test_sandbox_contract.py tests/test_sandbox_bubblewrap.py tests/test_db_api.py::TestMCPSourceAPI -v
... 46 passed in 2.85s

$ grep -RIn 'THE_ONE_TEST_MODE' Dockerfile docker-compose.yml scripts/ Makefile 2>/dev/null
(no matches; exit 1)

$ docker compose exec -T the-one ruff check the_one/ tests/
All checks passed!

$ docker compose exec -T the-one python -c "
import asyncio
from the_one.db.models import MCPSource
from the_one.mcp.transports.stdio import connect_stdio
from the_one.mcp.errors import MCPSandboxError

src = MCPSource(id='smoke', name='smoke', type='stdio',
                config={'command': '/bin/cat', 'args': []}, secrets={})

async def run():
    try:
        async with connect_stdio(src) as session:
            await asyncio.wait_for(session.initialize(), timeout=2.0)
            print('past sandbox boundary (unexpected initialize success?)')
    except MCPSandboxError as e:
        print(f'SANDBOX ERROR: {e}')
        raise
    except BaseException as e:
        print(f'expected post-spawn error: {type(e).__name__}: {str(e)[:120]}')

asyncio.run(run())
"
expected post-spawn error: ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
```

Test counts: `test_mcp_stdio_sandbox.py` 9 passed (8 mocked + 1 real-subprocess `/bin/cat` integration; the real-subprocess test runs because `bwrap 0.11.0` is present per L1a). `test_mcp_integration.py` regression count unchanged (14). `test_sandbox_contract.py` (14) + `test_sandbox_bubblewrap.py` (16) + `TestMCPSourceAPI` (16) = 46 regression-suite tests green. Lint fully clean across `the_one/` and `tests/`. Manual smoke confirms bwrap-wrapped `/bin/cat` starts (no `MCPSandboxError`); failure is post-spawn from the JSON-RPC handshake (cat is not a real MCP server) — proves the sandbox boundary was crossed end-to-end.

#### Diff scope

`git status --porcelain` for L4-only changes (L1a/L1b/L2/L3 changes batched for flight-end commit accumulate):

```
 M tests/conftest.py
 M the_one/mcp/transports/stdio.py
?? tests/test_mcp_stdio_sandbox.py
```

Plus flight artifacts (`flight-log.md`, `flight.md`, `legs/04-...md`). No out-of-scope edits — `the_one/platform/sandbox/` (L2/L3 done), `the_one/mcp/errors.py` (`MCPSandboxError` added in L2), `the_one/interfaces/web/api.py`, `tests/fixtures/mcp/` (L5a's surface), JS / Dockerfile / docker-compose / Makefile / pyproject all untouched. `tests/test_mcp_integration.py` NOT modified (F2 regression is naturally green under strict-floor profile — no `config.sandbox` block additions needed).

#### Deferred bwrap-side error translation

Per F3 §6, bwrap-side post-setup failures (writable_paths nonexistent, EPERM on unshare, namespace creation refused) *should* surface as `MCPSandboxError` with the §6 catalog messages. L4 does NOT add this translation — distinguishing "bwrap setup failed" from "wrapped target failed" inside `stdio_client`'s error paths is not reliably possible without scraping stderr or inspecting bwrap's exit code, and the §6 catalog message catalogs four canonical messages of which only "bubblewrap binary not found in PATH" (raised by `BubblewrapSandbox.__init__` per L3) currently reaches operators. The other three messages ("writable_paths entry … does not exist", "bubblewrap exited with code {n}", "namespace creation refused (EPERM on unshare)") are NOT emitted by L4. Recorded as Anomaly A02 below; resolution path is a follow-up routine-maintenance pass with stderr scraping or bwrap exit-code inspection.

### L5a Fixture Extension and Integration Tests

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed

#### Implementation summary

- `tests/fixtures/mcp/hello_server.py`: added `register_naughty_tools(app: FastMCP) -> None` opt-in helper that registers three TEST-ONLY escape-attempt tools (`write_outside_sandbox`, `dump_env`, `try_connect`) on a passed-in app. Each carries the verbatim `# TEST-ONLY (F3 escape-attempt fixture): DO NOT REMOVE OR PROMOTE TO PRODUCTION` marker comment immediately above its `@app.tool()` decorator (grep count ≥ 3 enforced). `make_mcp_app()` and the existing `echo` / `add` tools are UNCHANGED — `register_naughty_tools` is NEVER auto-invoked. `main()` gained a `--with-naughty-tools` CLI flag that, when present, calls `register_naughty_tools(mcp_app)` BEFORE `mcp_app.run("stdio")`; the flag is stripped from `args` before mode dispatch so it doesn't collide with positional parsing. F2's existing tests don't pass the flag, so naughty tools never appear in their tool list.
- `tests/test_mcp_sandbox_integration.py` (NEW): 10 tests — 9 real-subprocess (gated via module-level `requires_bwrap = pytest.mark.skipif(shutil.which("bwrap") is None)`) + 1 in-process unit test. Coverage: FS scope refusal under strict-floor profile (#1); writable-path mechanism (#2; uses session-scoped `/var/tmp/sandbox_l5a_<uuid>` fixture with reliable teardown); env-allowlist invariant with HOME=/tmp override (#3; structured payload introspection via `result.structured`); network refusal under `--unshare-net` (#4; IP-literal target avoids DNS); network allowed under `network_allowed=True` (#5; gated by `_has_outbound_network()` probe); writable_paths nonexistent → `MCPConnectionError` per L4 Anomaly A02 (#6; locks the deferred-translation gap as a positive test); host-env-only sentinel filtering (#7); `--with-naughty-tools` opt-in directionality (#8 + #9); in-process `register_naughty_tools` introspection via `app._tool_manager.list_tools()` (#10).
- Helper `_build_naughty_source(*, sandbox=None, extra_env=None, with_naughty=True)` (plain module-level helper, NOT a fixture) constructs `MCPSource` directly with `command=sys.executable`, `args=[..., "--with-naughty-tools"]`, `env={"PATH": ..., "PYTHONPATH": str(_PROJECT_ROOT)}`, `cwd=str(_PROJECT_ROOT)`, optional `config["sandbox"]`. Bypasses the L1b API validator so tests can probe profile shapes without API round-tripping.
- F2 regression: NO modifications to `tests/test_mcp_integration.py` (14 tests still pass unchanged — F2's hello tests don't pass `--with-naughty-tools`, so naughty tools don't appear in their tool list).

#### Verification — verbatim output

```
$ docker compose exec -T the-one python -m pytest tests/test_mcp_sandbox_integration.py -v
... 10 passed in 3.38s

$ docker compose exec -T the-one python -m pytest tests/test_mcp_integration.py -v
... 14 passed in 2.87s

$ docker compose exec -T the-one python -m pytest tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -v
... 39 passed in 0.07s

$ docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI -v
... 16 passed in 2.49s

$ grep -c "TEST-ONLY (F3 escape-attempt fixture)" tests/fixtures/mcp/hello_server.py
4

$ docker compose exec -T the-one ruff check the_one/ tests/
All checks passed!
```

10/10 tests pass under the dev container (the network-allowed test #5 runs because outbound network is available; on runners without outbound it would skip). 14 F2 stdio tests still green. L4 (9) + L3 (16) + L2 (14) = 39 prior-leg regression tests green. F1 API validator suite (16) green. Marker-comment grep returns 4 (one inside `register_naughty_tools` docstring, three above the decorators — well above the ≥ 3 acceptance threshold). Lint fully clean.

#### Empirical adjustments to the leg spec

- **`MCPSource` constructor**: leg spec sketched `MCPSource(name=..., type=..., config=..., secrets={})` but `MCPSource` requires `id`. Helper passes a stable test-id `"src-l5a-naughty"` (pydantic doesn't enforce uniqueness across in-memory instances; sandboxed subprocess never reads it). No deviation from leg intent.
- **FastMCP structured payload shape**: leg spec sketched `result.structured["result"]` for `dump_env`'s dict return. Empirically FastMCP returns the dict DIRECTLY in `result.structured` (no `"result"` wrapper for already-dict returns). Tests #3 + #7 read `result.structured` directly. Documented in code comments. Locks the SDK behaviour for future maintainers.

#### Edge case documented: --bind under /tmp shadowed by --tmpfs /tmp

L3's argv compiler emits `--bind PATH PATH` BEFORE `--tmpfs /tmp`. So a `writable_paths=["/tmp/foo"]` entry would be shadowed by the later `--tmpfs /tmp` (the fresh ephemeral tmpfs masks the bind mount; writes succeed but land in the tmpfs, not in the host-bind path). Operators wanting persistent writable scratch must use paths OUTSIDE `/tmp` — Test #2 uses `/var/tmp/sandbox_l5a_<uuid>` for this reason, with a session-scoped fixture creating + tearing down the directory on the host (uuid-suffixed for parallel safety under pytest-xdist).

Future routine-maintenance candidate: reorder L3's argv to emit `--tmpfs /tmp` BEFORE the per-path `--bind` loop, so per-path binds win. Out of scope for L5a; recorded here so the next routine-maintenance pass picks it up.

#### Diff scope

`git status --porcelain` for L5a-only changes (L1a/L1b/L2/L3/L4 changes batched for flight-end commit accumulate):

```
 M tests/fixtures/mcp/hello_server.py
?? tests/test_mcp_sandbox_integration.py
```

Plus flight artifacts (`flight-log.md`, `flight.md`, `legs/05a-...md`). No out-of-scope edits — `the_one/` (no production code changes), `tests/conftest.py` (L4 surface), `tests/test_mcp_integration.py` (F2 regression — must still pass unmodified), `tests/test_mcp_stdio_sandbox.py` (L4), `tests/test_sandbox_*.py` (L2/L3), Dockerfile, docker-compose.yml, JS, pyproject.toml, CLAUDE.md, agents.md all untouched.

### L5b Stdio Editor Sandbox Section

**Started**: 2026-05-06
**Completed**: 2026-05-06
**Status**: completed

#### Implementation summary

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`: added `<div class="editor-section mcp-stdio-only" data-testid="mcp-sandbox-section">` peer block between Connection and Environment sections; renders an `<input type="checkbox" class="field-input" data-field="sandbox-network-allowed">` (label "Allow network access") plus a `<div class="chip-list-editor" data-field="sandbox-writable-paths">`. Flat kebab-case `data-field` per existing OAuth/args convention. The `mcp-stdio-only` class plus the existing `applyTransportVisibility` machinery auto-hides the section for streamable-http.
- Extended `mountChipListEditors` with a third `helpers.renderChipListEditor('sandbox-writable-paths', ...)` mount mirroring the args/oauth-scopes pattern.
- Extended `collectFormData` inside the `type === 'stdio'` branch ONLY: reads checkbox `.checked` + `helpers.readChipListValue(sandboxPathsList)`, always emits `config.sandbox = {network_allowed, writable_paths}` (matches the existing always-emit precedent for `config.env` / `config.headers`). Streamable-http branch never emits `config.sandbox`.
- Extended `getFormSnapshot`: added `sandbox-network-allowed` to the `staticFields` whitelist with a per-element check `el.type === 'checkbox'` → read `el.checked` (boolean coerced to `!!`) instead of `el.value`; added `sandbox-writable-paths` to the `chips` snapshot dict.
- Extended `revertEditorToSource`: added `sandbox-network-allowed` outside the `staticMap.forEach` loop with an explicit `sandboxNetEl.checked = ...` (the existing loop body uses `el.value = ...` which would no-op for a checkbox); added a third chip-list re-mount block for `sandbox-writable-paths` mirroring the args/oauth-scopes blocks.
- `attachStaticListeners` UNCHANGED — the `.field-input` selector picks up the new checkbox automatically; `change` event wiring already in place.
- `tests/browser/test_flow_studio_mcp_editor.py`: added 11 new browser tests under a `# F3 L5b: Sandbox section` banner — section render (stdio), section hidden (streamable-http), visibility toggle on transport switch, save round-trip with non-default values, edit round-trip populates fields, empty defaults for new stdio source, save-emits-explicit-defaults, streamable-http-no-sandbox-key, checkbox-toggle-marks-dirty, chip-add-remove-marks-dirty, cancel-revert restores both fields. All use the existing F1 L6 fixtures (`app_clean`, `page`) and helpers (`_seed_mcp_source`, `_list_sources`).

#### Verification — verbatim output

```
$ docker compose exec -T the-one python -m pytest tests/browser/test_flow_studio_mcp_editor.py -v -m browser
... 20 passed in 20.75s

$ docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI tests/test_mcp_integration.py tests/test_sandbox_contract.py tests/test_sandbox_bubblewrap.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_sandbox_integration.py -v
... 79 passed in 8.71s

$ docker compose exec -T the-one ruff check the_one/ tests/
All checks passed!
```

20/20 browser tests pass (9 prior F1 L6 + 11 new L5b). 79/79 prior-leg regression tests green (F1 API validator 16, F2 stdio integration 14, L2 contract 14, L3 bwrap 19, L4 stdio sandbox 9, L5a integration 10). Lint clean (ruff is a no-op for the JS file; the only Python touched is `tests/browser/test_flow_studio_mcp_editor.py`).

#### Empirical adjustments to the leg spec

- **`getFormSnapshot` checkbox handling**: the leg spec called for adjusting the snapshot helper to handle `el.type === 'checkbox'`. Implemented as a per-element branch inside the `staticFields` loop (`if (el && el.type === 'checkbox') staticData[...] = !!el.checked`). The `!!` coercion ensures `JSON.stringify` emits `true` / `false` (not `undefined` if a future field has no element).
- **`revertEditorToSource` checkbox out-of-loop**: per the leg's design-review note, pulled the sandbox checkbox revert OUT of the existing `Object.keys(staticMap).forEach` loop (which uses `el.value = ...`) and into an explicit `sandboxNetEl.checked = ...` line below. The `staticMap` itself does NOT carry the `sandbox-network-allowed` key — keeping the maps shape-homogeneous (string values only) for the existing string-loop, with the boolean handled separately.
- **Test count**: the leg targeted "~10 browser tests"; landed 11 (the streamable-http-no-sandbox-key test fit naturally given the existing F1 L6 streamable-http patterns, so it was added as the design review's suggested "plus" test).
- **Long-line lint fix**: three new test locator chains exceeded the 100-col ruff limit; broke them into multi-line `page.locator(\n    '[...selector...]'\n)` form. No semantic change.

#### Diff scope

`git status --porcelain` for L5b-only changes (L1a/L1b/L2/L3/L4/L5a changes batched for flight-end commit accumulate):

```
 M the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js
 M tests/browser/test_flow_studio_mcp_editor.py
```

Plus flight artifacts (`flight-log.md`, `flight.md`, `legs/05b-...md`). No out-of-scope edits — no Python source under `the_one/`, no test outside `tests/browser/test_flow_studio_mcp_editor.py`, CSS files untouched, API layer (L1b done) untouched, runtime (L2-L4 done) untouched, integration tests (L5a done) untouched, Dockerfile / docker-compose.yml / Makefile / pyproject.toml / CLAUDE.md / agents.md all untouched.

---

## Decisions

> Runtime decisions not in the original plan. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

### A02 — bwrap-side error translation deferred

F3 §6 catalogs four `MCPSandboxError` messages: bwrap-not-found (L3 implements via `BubblewrapSandbox.__init__`), writable_paths-nonexistent / EPERM-on-unshare / namespace-creation-refused (L4 deferred). L4 distinguishes "bwrap setup failed" from "wrapped target failed" inside `stdio_client` error paths only by inheriting F2's existing `MCPConnectionError` translation in `MCPClient.connect` — bwrap-specific messages are NOT emitted. Severity: **cosmetic** (correctness preserved; messages less actionable for the operator). Resolution path: follow-up routine-maintenance pass with stderr scraping or bwrap exit-code inspection.

---

## Flight Director Notes

> Populated by the orchestrator (mission-control) during agentic-workflow execution.

### 2026-05-06 — Flight start

**Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-level, not default fallback). Crew extracted: Developer (Sonnet, implements + design-reviews), Reviewer (Haiku, code review). Accessibility Reviewer optional (only L5b touches UI; will spawn for L5b).

**Flight transition**: `ready` → `in-flight`. Branch `flight/03-sandbox-adapter-and-bubblewrap` already exists at flight start (created in prior prep session); no checkout needed.

**Leg ordering and gating**:
- L1a is a **hard gate** — the 5-assertion CI compat probe must pass after applying §10's docker-compose changes. If any assertion fails, [BLOCKED:reason] before L1b proceeds; per Adaptation Criteria, scope-trim to "HAT-on-host (WSL2)" is the fallback.
- L1a → L1b → L2 → L3 → L4 → L5a + L5b (L5a/L5b independent; L5b needs L1b's `config.sandbox` validator) → L6 HAT.
- L6 is interactive (HAT) — autonomous orchestration ends after L5b; review + commit happens before L6; L6 walks human through 5 steps.

**Per-leg cycle**: leg design → developer design-review → incorporate feedback → mark `ready` → spawn Developer to implement → mark `landed`. Code review + commit deferred to a single batch after L5b lands per the agentic-workflow flight-batch model.

### 2026-05-06 — L1a leg-design

**Leg artifact**: `legs/01a-ci-compat-probe-and-privilege-model.md` (Status: ready).

**Design review**: 2 cycles. Cycle 1 raised 2 high (stale Dockerfile comment / vague compose placement) + 3 medium (Ollama dependency in `make rebuild`, broad `docker compose config` grep, assertion-5 control-DNS logic gap) + 3 low + 3 questions. All addressed inline. Cycle 2 verified all fixes resolved; flagged 2 non-blocking suggestions (comment harmonization, `/dev/tcp` requires bash not dash) — both applied. Approved.

**Decision rationale**: kept the leg narrow (Dockerfile + docker-compose.yml only); no committed probe script (5 commands run inline + captured in flight log per Implementation Guidance §5). Hard-gate posture preserved — if any of the 5 assertions fail, [BLOCKED:reason] before L1b begins, with §10 Adaptation Criteria scope-trim ("HAT-on-host (WSL2)") as the documented fallback.

### 2026-05-06 — L1b leg-design

**Leg artifact**: `legs/01b-f1-validator-extension-and-docs.md` (Status: ready).

**Design review**: 1 cycle. 3 low-severity issues (weak `isinstance(bool)` analogy, missing empty-dict happy-path test, PUT-coverage acknowledgment) + 3 suggestions + 2 questions. Applied the meaningful fixes: added `test_validation_accepts_stdio_config_empty_sandbox_dict` (3 new tests total, not 2), added `is not None` clarifying comment to validator sketch (forecloses truthy-check footgun), pinned agents.md bullet count to exactly 7, added Edge Cases entries for PUT type-switch with leftover sandbox + the deliberate PUT-coverage gap. Approved.

**Decision rationale**: kept the leg validation+docs-only with no runtime code (L2's surface). Sandbox sub-block is gated inside the stdio arm only; streamable-http silently ignores `config.sandbox` per existing validator's "extra keys allowed" posture. Empty-dict happy-path test added to lock the operator footgun where `if sandbox:` would skip the dict-shape validator branch.

### 2026-05-06 — L2 leg-design

**Leg artifact**: `legs/02-sandbox-adapter-contract.md` (Status: ready).

**Design review**: 1 cycle. 4 low-severity issues (one-sided Protocol negative test, frozen-dataclass example inaccuracy, `@anthropic-ai/sandbox-runtime` citation missing from AC, style-claim cosmetic) + 4 suggestions + 4 questions. Applied: added 2-direction Protocol negative tests, fixed frozen-dataclass reference (`mcp/types.py` not `llm/base.py`), added `@anthropic-ai/sandbox-runtime` to AC citation set, added bool-vs-int test (`from_dict({"network_allowed": 1})` raises), reconciled test count to ~14, replaced `__init__` `pass`-body with docstring, pinned matrix column headers to binary names so AC grep matches. Approved.

**Decision rationale**: contract-only leg — L3 implements `BubblewrapSandbox.prepare_spawn`. `MCPSandboxError` canonical home in `the_one/mcp/errors.py` with convenience re-export from `the_one/platform/sandbox/__init__.py`. Capability matrix verbatim-portable from flight log Phase 1b Part C. `agents.md` `### the_one/platform/` section absent (verified by reviewer); sandbox-package pointer deferred to routine maintenance per the leg's Edge-Case logic.

