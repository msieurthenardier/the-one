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

---

## Decisions

> Runtime decisions not in the original plan. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Flight Director Notes

> Populated by the orchestrator (mission-control) during agentic-workflow execution.
