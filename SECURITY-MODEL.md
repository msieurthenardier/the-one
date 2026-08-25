# Security Model

This project is a single-user local development tool. The threat model and
security posture below are deliberate design choices, not gaps to fix.

## Threat Model

- **Audience**: solo developer/operator running the agent on their own
  machine. No multi-user scenarios. No internet exposure. No untrusted
  LLM-supplied tool inputs from external clients.
- **Trust boundary**: the operator is trusted. Tool inputs from agents are
  constrained by per-tool config (resolver-narrowed) but are NOT treated as
  hostile.
- **F3 Decision 10 — REVISED by Mission 20** (`missions/20-local-api-
  authentication/`, GitHub issue #165): originally "operator-trusted setup,
  NOT malicious filesystem actor," used to justify a fully unauthenticated
  local API. Mission 20 reconsidered that: on a loopback API with no
  credential at all, "trust the operator" collapsed in practice into "trust
  every local process, no matter who or what started it" — any other OS
  account, any lower-privilege process, or any page open in the operator's
  own browser could reach the API with nothing presented. The
  filesystem-actor premise itself is unchanged and is still inherited by F4
  / F5 / F6 (the operator still owns the local environment; the tool
  denylists are defense-in-depth against agent mistakes, not an attacker
  already on the machine — see "What This Model Excludes" below) — what
  changed is that the premise no longer, by itself, justifies an
  unauthenticated API. **What replaced it**: the credential gate under
  "Authentication" below. This is now the canonical citation for "should we
  add auth to the local API?" (already done — see Authentication); for
  other "should we add auth/sandboxing/...?" questions, the calibration
  above — narrow what "operator-trusted" is asked to cover, don't discard
  the premise — is the citable precedent.

## Authentication

Mission 20 (`missions/20-local-api-authentication/`) closed the gap recorded
above under F3 Decision 10: every HTTP request, `/static/*` asset, and
WebSocket upgrade now requires an identified caller, enforced by
`CredentialGateMiddleware` (`the_one/interfaces/web/middleware.py`) sitting
in front of the whole application.

**What this now protects against**: other local OS accounts reading or
driving the API; lower-privilege processes on the same machine; and
browser-vectored access — a hostile page open in the operator's browser can
no longer reach the loopback API at all, including via a plain `GET`, which
the Origin-allowlist layer below never gated on its own.

**What this does not protect against**: a process running *as the operator*
can read the credential file (`<data_dir>/api-credential`, mode `0600`) and
therefore has exactly the same access the operator has. This is not a
deficiency to caveat away — it is the boundary this mission deliberately
chose. The credential file rests on the same trust boundary as every other
operator secret this project stores (the encryption key, provider API keys):
OS file permissions, not a second factor. A future flight adding real
multi-user isolation would need to revisit this (see "Future Work" below).

- **Exactly one exemption**: `GET /api/live`, a minimal liveness probe that
  returns `{"status": "ok"}` and nothing else — no version, no build info, no
  prompt text. `/api/info` was considered and rejected as the exemption
  instead: it returns `base_prompt` (the agent's full system prompt), and
  exempting it would have published that to every local process regardless
  of credential. `/api/info` is therefore credentialed like every other
  route; only the liveness probe is reachable with nothing presented, which
  is what lets a pure "did the server come up yet" readiness wait — the
  desktop launcher's own just-started-server poll
  (`the_one/interfaces/desktop/shell.py::_wait_until_serving`) and the
  browser-test harness's equivalent (`tests/browser/conftest.py`) — succeed
  before either process holds or needs a credential. Callers asking a
  *different* question ("is that other instance out there mine?") still use
  the credentialed `/api/info`, deliberately: the desktop launcher's
  `_select_port` port classifier, `make verify-serving`, and CI
  packaged-smoke all send the credential and treat the response as proof of
  ownership, not just liveness.
- **Two credentials, two lifetimes — do not conflate them:**
  - A **long-lived, persisted credential** (`the_one/api_credential.py`),
    stored at `<data_dir>/api-credential` (mode `0600`, written with no
    world-readable window between creation and the permission landing).
    Presented as `Authorization: Bearer loc_<identifier>.<secret>` by every
    non-browser caller — CLI tooling, tests, `curl`, MCP-style automation.
    Created on first use; replaced via `the-one rotate-api-credential`.
  - A **single-use, short-lived browser-handoff credential**
    (`the_one/interfaces/web/handoff_store.py`), minted either in-process
    (the desktop launcher, which shares a process with the server) or via
    `POST /api/session/handoff` for a caller that already holds the
    long-lived credential but runs in a separate process (the browser-test
    harness, a behavior-test Executor). It travels only as a query
    parameter on a `GET /` document request — never anywhere else, and the
    long-lived credential is never accepted from a query parameter — because
    a URL is the one channel that reliably leaks (shell history, server
    logs, browser history, referrers), so only a value that is worthless
    after one use may travel there. It is consumed on its first successful
    use, expires a few minutes after minting if unused, and can never be
    replayed.
  - Consuming a handoff credential sets an `HttpOnly` session cookie
    (`the_one_session`) and redirects back to `/`; the cookie authenticates
    the browser from then on. The cookie is **stateless** — there is no
    session store. Its value is `<nonce>.<HMAC-SHA256(key=current
    long-lived secret, msg=nonce)>`, verified on every request by
    recomputing the HMAC against whatever the long-lived credential
    currently is. That is why a session survives a server restart (a fresh
    process reads the same file and recomputes the same HMAC) and why
    **rotating the long-lived credential drops every outstanding session at
    once** — rotation *is* the revocation mechanism; there is deliberately
    no separate revoke-a-session endpoint.
  - The cookie is `SameSite=Strict`, **not** the `Lax` default — this is
    load-bearing, not a style choice. `SameSite=Lax` still attaches a
    cookie to a cross-site *top-level navigation* using a safe method (an
    ordinary link click is enough). The Origin-allowlist layer below
    deliberately never gates `GET` — so `Lax` would leave exactly the gap
    this mission exists to close: a hostile page could top-level-navigate
    the operator's browser to a loopback `GET` path, arrive carrying a
    valid session cookie, and no origin check would run either. `Strict`
    closes that path entirely. Do not "simplify" this back to `Lax` without
    re-deriving this paragraph first.
- **Layering: the credential gate is outermost, the Origin allowlist is
  inside it.** A request with a missing or invalid credential is refused
  with **401** before the Origin-allowlist logic ever runs. A request that
  presents a *valid* credential from a disallowed origin reaches the
  Origin-allowlist layer and is refused there with **403**. The two checks
  are independent and run in series, not alternatives to each other.
- **The Origin-allowlist middleware is a layer beneath the credential gate,
  not an alternative to it.** (M06 F1 L5;
  `the_one/interfaces/web/middleware.py::OriginAllowlistMiddleware`.) It
  enforces same-origin requests on state-mutating methods
  (POST/PUT/PATCH/DELETE) and on WebSocket upgrade handshakes. Allowed
  origins default to `scheme://host:port` derived from
  `settings.host`/`settings.port`; operators behind a reverse proxy extend
  via `THE_ONE_ORIGIN_ALLOWLIST` (`.env.example` carries a commented
  example). `GET` requests and missing-`Origin` callers (curl,
  server-to-server) pass through this layer by design — that used to be a
  known, accepted gap; it is now exactly the gap the credential gate above
  closes for every route except the one exemption. `/api/live` is the only
  request that can reach this layer without the credential gate having
  already checked it, and it returns nothing sensitive by construction, so
  passing through unauthenticated here costs nothing.
- Provider URL validation (M06 F1 L5) refuses non-`https://` `base_url`
  values for non-localhost hosts at all three create/update/test endpoints
  (HTTP 422). `mock` and `ollama` provider types are skipped.

### Self-configuration surface (M21 F01 L02)

An agent may be given a loopback MCP source through which it can read its
own configuration (`the_one/self_configuration/`). This is **off by
default for every agent** — the operator opts an agent in from that
agent's own Self-configuration tab in Studio.

- **A second, distinct credential source.** The surface mints one
  `agt`-prefixed credential per enabled agent (shape mirrors the long-lived
  `loc`-prefixed operator credential above, but a different prefix so a
  token's type is legible at a glance). It lives ONLY inside that agent's
  surface row's encrypted `secrets["Authorization"]` — never on
  `AgentConfig`, never returned by the enable endpoint, and masked like
  every other MCP-source secret in every API response. Resolution goes
  through an in-memory registry (`identifier → (source_id, secret)`),
  rebuilt at process startup from every marked row and mutated in-process
  by enable/disable — there is no per-request DB read on this path.
- **Confined to its own mount path — this is the load-bearing property.**
  `CredentialGateMiddleware` resolves an `agt` credential to an identified
  caller exactly like any other registered source, but a caller whose
  `source` appears in `the_one/self_configuration/constants.py:
  CONFINED_SOURCE_PATHS` is admitted ONLY to HTTP requests under that
  source's mapped path prefix (`/mcp/self-configuration`) — every other
  path, and every WebSocket upgrade, is refused with 403. Without this, an
  `agt` credential would be a full operator credential under a different
  prefix: Mission 20's gate resolves any registered source to an
  identified caller and admits it everywhere by default, and that
  mission's debrief named exactly this hazard as the reason per-route
  scope enforcement was deferred ("harmless today; live the moment a
  second `CredentialSource` exists" — it has). `file` and the browser
  session cookie's `session` source are absent from the map and are
  admitted exactly as before this surface existed.
- **The tool catalog IS the write allowlist, by construction.** The surface
  exposes four tools: `get_my_configuration` and `describe_my_capabilities`
  (read-only — neither builds an `Agent`, which would recurse into the
  surface from inside the agent's own tool call, and neither returns a
  source config, URL, header, or secret; `get_my_configuration`'s
  projection is an explicit field list that never touches
  `tool_overrides`, `mcp_overrides`, `provider_config_id`, `kb_ids`,
  `mcp_source_ids`, or `connector_ids`), and `update_my_description` /
  `update_my_system_prompt` (M21 F01 L03 — the write path). No tool takes
  a field name; the allowlist is the catalog's shape, so a future
  `AgentConfig` field is unwritable because nothing addresses it.
- **The write path (M21 F01 L03): whole-value replacement, persist-first,
  deferred-apply.** Each write tool takes only `text` and `apply` —
  `apply` is `"next_turn"` (the running conversation adopts the revision
  when its current turn ends — never mid-turn, since the agent loop
  re-binds its request messages inside the same turn's iteration loop) or
  `"next_session"` (the running conversation is untouched; the revision
  is visible the next time the agent is rebuilt, e.g. a rejoin). Either
  way the revision is written to the stored `AgentConfig` row
  immediately, before any deferral — a `next_turn` entry in the
  in-process pending registry (`the_one/self_configuration/pending.py`,
  keyed by agent name) is therefore always redundant with what the store
  already holds, not the source of truth. Input is bounded, not
  content-policed: `text` must be a non-empty string of at most 64 KiB,
  `apply` one of the two literals — anything else is refused with no
  partial write. No approval gate, pending queue, or revision log exists
  yet (Flight 2).
- **Ownership is enforced server-side**, not merely by convention:
  `create_agent`/`update_agent` reject (422) any `mcp_source_ids` entry
  that is another agent's surface row, and reject (422) any
  `mcp_overrides` entry targeting a surface row that carries a credential
  key (`env`/`headers`/`bearer_token`) — an agent can never be handed a
  foreign or attacker-supplied credential through the override path. The
  admin MCP Sources screen hides these rows by default (`GET
  /api/mcp-sources` — pass `?include_agent_surfaces=1` to include them,
  which only the owning agent's own Studio tabs do); a direct `PUT` on a
  marked row is refused with 409, and `DELETE` performs the full disable
  rather than an ordinary row delete.
- **Indirect prompt injection is the surface's live residual risk**,
  recorded here rather than treated as closed. Any content an agent's
  *other* tools feed into its context (web fetch, MCP servers, connector
  messages) can now, as of M21 F01 L03, instruct the agent to call
  `update_my_system_prompt` or `update_my_description` — nothing gates
  the write tools beyond the existing per-source/per-tool checkboxes an
  operator uses for every MCP tool. A prompt-injected agent that decides
  to revise its own guardrails does so with the SAME confinement,
  ownership, and input-bounds enforcement as a legitimate self-revision;
  none of those mechanisms distinguish agent intent from injected intent
  — they were never designed to. This is the mission's central,
  explicitly named risk, and this leg does not mitigate it: no approval
  gate, no pending-queue hold, and no revision log exist yet. Flight 2
  owns closing this gap (approval mode, a pending queue, a revision log
  and restore) before a write takes effect unattended. Until then, the
  only mitigation is the same one that governs any other MCP tool: the
  operator can withhold `update_my_description` / `update_my_system_prompt`
  from a specific agent via the per-tool checkboxes on that agent's MCPs
  tab, or disable the surface entirely from its Self-configuration tab.

## Network Bind

- Default `host=127.0.0.1` (localhost only). Host-native (`the-one serve` /
  `make up`) binds this default, so the dev server is reachable only on the
  loopback unless the operator overrides `THE_ONE_HOST`. Exposing the app on a
  routable interface is the operator's choice and the operator owns host
  firewalling.
- A future production form factor (e.g., desktop app) reverts to
  localhost-only. Any deployment exposing the app over a network is
  responsible for fronting it with a reverse proxy that adds auth — that
  configuration is out of scope for this project.

## Tool Execution Boundary

The per-category Pydantic Configs (`FilesystemConfig`, `ExecutionConfig`,
`PythonExecConfig`, `WebConfig`) and the resolver semantics
(`Narrow`/`NarrowPrefix`/`NarrowSuperset`/`Substitute`) are documented in
detail in [CLAUDE.md](CLAUDE.md) under "Tool Configuration Layer (M05
Flight 2)". The security-relevant invariants are:

- **Filesystem (M05 F3)**: per-tool path allowlist + denylist (default
  19-entry curated denylist covering system secrets, browser/app data,
  agent internals), read-size cap, binary-file refusal. See
  [CLAUDE.md](CLAUDE.md) "Filesystem constraint surface (F3)".
- **Execution (M05 F4)**: timeout/output caps, command denylist
  (trip-wire, not fence — see CLAUDE.md), per-agent PTY session isolation
  keyed on `(agent_name, session_id)`, per-call denylist re-check on
  `shell_session_send` so agents cannot pre-stage a denylisted command
  behind an open session.
- **Subprocess environment**: hardcoded 8-key allowlist (`PATH`, `HOME`,
  `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `TERM`, `TZ`) lives at
  `the_one/platform/env.py` and is **NOT operator-configurable** by
  design. The allowlist is enforced at the tool layer: `ShellTool`
  (`the_one/tools/shell.py`) and `PythonExecTool`
  (`the_one/tools/python_exec.py`) each call `_build_subprocess_env()`
  and pass the filtered env through the sandbox seam; `pty.py::UnixPtySession`
  builds `_build_subprocess_env()` in the parent and passes it through
  `get_sandbox_backend().prepare_spawn(...)` identically (M14 F2) — all
  four spawn paths are now covered.
- **OS-level execution fence (M14 F1+F2)**: all four spawn paths — `shell`,
  `python_exec`, MCP stdio servers, and PTY `shell_session_*` — route
  through a `get_sandbox_backend()` factory seam. On Linux with `bwrap`
  present, each invocation runs inside a bubblewrap jail using the
  host-workspace profile: write access limited to the `FilesystemConfig`
  allowlist, denylisted paths bound read-only via `--ro-bind-try` (not
  writable; read-scoping is satisfied for the boxed path — see below;
  host-workspace read-scoping still deferred), real `$HOME`, network
  deny-by-default (`ExecutionConfig.sandbox_network_allowed` opt-in).
  **`--ro-bind-try` silent-skip caveat**: `--ro-bind-try` (used for
  denylist paths) silently skips a path that does not exist on the host
  — the overlay is a no-op for absent paths. A denylist entry therefore
  only protects a path that already exists at sandbox launch time; a
  missing path is neither mounted nor protected. Tests that rely on
  denylist enforcement must ensure the target directory pre-exists before
  starting the sandbox (see `tests/_sandbox_fixtures.py:make_denylist_secret`).
  On
  non-Linux or bwrap-missing Linux, the seam falls through to
  `PassthroughSandbox` (observable via a one-time WARNING log). **PTY
  teardown**: a single-pid SIGKILL on the bwrap PID reaps the entire bwrap
  PID namespace via `--die-with-parent`, so `setsid`'d grandchildren are
  collected by kernel PID-namespace teardown without needing `killpg`.
  **`--new-session` omission**: the seam deliberately omits `--new-session`
  for PTY spawns to preserve the controlling tty required for interactive
  shell use; the accepted tradeoff is that the `TIOCSTI` input-injection
  surface remains open (recorded design decision).
- **Web (M05 F5)**: two-layer SSRF enforcement — `_url_check` at the tool
  boundary plus `SSRFGuardedTransport` resolving DNS once and pinning the
  connect target to that IP, refusing loopback / RFC1918 / link-local /
  cloud-metadata / IPv6 ULA + ULL by default. IP-literal hosts are gated
  on the same default-block list. See [CLAUDE.md](CLAUDE.md) lines
  142-144 for the canonical mechanism description and the **mission
  invariant** that `WebConfig` deliberately has no `disable_ssrf` field
  — SSRF protection is always-on; operators reaching specific internal
  hosts list them in `extra_allowed_hosts`.
- **Operator-supplied identifier allowlists**: any operator-config-derived
  string that flows into `Path()` joins, `subprocess.run()` argv elements,
  or filesystem operations MUST be validated against a spec-grounded
  allowlist regex, NOT a permissive character class. The character class
  `[A-Za-z0-9._@/-]` is NOT an allowlist for paths — every character is
  permitted individually, so `../etc/passwd` passes. The spec-grounded
  form is anchored, structure-aware, and rejects path-traversal patterns
  by construction.

  Exemplar regex (npm package-name spec — covers `lodash`, `@scope/pkg`,
  `pkg-with-dashes`, `pkg_with_underscores`; rejects `../etc/passwd`,
  `a/b/c`, `.hidden`, uppercase, shell metacharacters):

  ```python
  _VALID_NPX_PKG_RE = re.compile(r'^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$')
  ```

  Implementation: `the_one/mcp/cache_cleanup.py:71-83` defines
  `_VALID_NPX_PKG_RE` module-level, validates at function entry of
  `_clean_npx`, raises `ValueError` before any path operation.
  Established in F1 M09 Leg 3 after a design-review catch (the original
  draft used the broken char-class allowlist).

## Boxed Execution Mode (M14 F4)

The `shell` and `python_exec` tools support an agent-selectable **boxed** isolation
mode layered on top of the host-workspace fence described above.

### Isolation model

- **Box-by-default**: both tools default to boxed mode; the agent must explicitly set
  `host_access=true` to escalate out of the box and reach the host workspace. This is a
  least-privilege default — the agent must consciously decide it needs the user's real
  files or network.
- **True isolation via minimal rootfs**: a boxed spawn uses
  `SandboxProfile(minimal_rootfs=True, …)` — bubblewrap mounts a minimal read-only
  system rootfs (`/usr`, `/bin`, `/lib`, `/etc`, `/proc`, `/dev`, `/tmp`) rather than
  binding the host filesystem. The user's home directory, project files, credentials, and
  any host data are completely absent. There is no host FS overlay and no denylist to
  enumerate.
- **Only writable location is the box's scratch directory**: the scratch dir (`$HOME`
  inside the box) is the sole writable path. Nothing the agent writes inside the box can
  escape to the host filesystem except through that directory.
- **Network unconditionally off**: the boxed profile DOES NOT read
  `ExecutionConfig.sandbox_network_allowed` — network is always denied inside a box,
  regardless of operator configuration. (The host-workspace profile reads the config flag;
  the boxed profile ignores it — `_build_boxed_profile` in `the_one/tools/execution.py`
  hardcodes `network_allowed=False`.)

### Scratch directory lifecycle

Two scratch patterns, both rooted at `settings.data_dir / "boxes"`:

- **Per-call-ephemeral** (`boxes/<uuid>`): used by `shell` and `python_exec` one-shot
  tools. Created by `_ephemeral_box_scratch()` context manager; removed by its `finally`
  block on both clean return and exception (including `asyncio.TimeoutError`). Each tool
  call gets a fresh scratch and leaves nothing behind on normal exit.
- **Per-session-persistent** (`boxes/{agent_name}-{session_id}-{uuid}`): used by
  `shell_session_start` / `shell_session_send`. Created at session start; cleaned up by
  `_SessionBoxedScratch` on `session.close()`. The scratch persists across sends within a
  session so the agent can accumulate files between PTY commands.

### Startup prune of orphaned scratch dirs

On ungraceful process exit (SIGKILL, OOM, kernel crash), per-call and per-session cleanup
may not run, leaving orphaned `boxes/<…>` directories. `prune_box_scratch()` in
`the_one/tools/execution.py` removes all children of `settings.data_dir / "boxes"` at
process startup — before any sessions start, so every box present is an orphan from a
prior run.

Called once from the FastAPI lifespan startup and from the CLI `_run_cli` startup.
**Single-process-at-a-time assumption**: concurrent web + CLI processes sharing the same
`data_dir` are unsupported — a startup prune in one would remove the other's live boxes.
The prune is NOT in `settings.ensure_dirs()` (called per `AgentFactory.create()`) because
that would delete a live session's scratch mid-operation.

### Read-scoping status

- **Boxed path**: read-scoping is **satisfied** — the box has no user FS at all (minimal
  rootfs mount), so the agent cannot read outside its scratch directory by construction.
  No denylist is needed; the host is simply absent.
- **Host-workspace path**: read-scoping is still **deferred** — denylisted paths are
  bound read-only via `--ro-bind-try` (not writable) but are potentially readable. A
  future flight will add read enforcement on the host-workspace path.

### Merged-usr portability caveat

The boxed `minimal_rootfs` branch in `the_one/platform/sandbox/bubblewrap.py` recreates
the system runtime inside the box using `--ro-bind /usr /usr` plus four `--symlink`
entries (`usr/bin → /bin`, `usr/sbin → /sbin`, `usr/lib → /lib`, `usr/lib64 → /lib64`).
This mount set **assumes a merged-usr layout** — i.e. the host's `/bin`, `/sbin`, `/lib`,
and `/lib64` are already symlinks into `/usr` (Debian bookworm, Ubuntu 22.04+, the
`python:3.11-slim` image base). On a **non-merged-usr host** (older Debian/Red Hat with
real split directories at `/bin` and `/lib`), the `--symlink` entries shadow those real
directories with dangling symlinks pointing to `usr/bin` and `usr/lib` inside the
box — resulting in a broken dynamic linker or missing tools. Non-merged-usr deployments
must either add explicit `--ro-bind /bin /bin` (etc.) bind entries to the boxed profile,
or verify the host layout before running boxed spawns. The deployment target for this
project is merged-usr only (bookworm/Ubuntu 22.04+); this is a portability note, not a
current operational gap.

### Passthrough degradation

On non-Linux or bwrap-missing Linux, both boxed and host-workspace spawns fall through to
`PassthroughSandbox`. Passthrough runs the command unisolated; this is logged at WARNING
level and is observable (never silent). The isolation properties above (no user FS,
network off) are NOT enforced under passthrough.

### Windows: interactive tools run unsandboxed (M15 F3 — DD9)

On Windows, the sandbox factory (`get_sandbox_backend()`) returns `PassthroughSandbox`
— there is no AppContainer or equivalent backend. All four spawn paths (including
`shell_session_*` PTY sessions) run **unisolated** on Windows. This is a documented,
accepted gap (DD9), not a regression — the Linux bubblewrap enforcement path is the
production containment boundary; Windows ships at PTY feature parity without sandbox
enforcement. WSL2 users inherit the full Linux sandbox path.

**Win32 Job Object is lifecycle teardown, NOT containment.** The
`WindowsPtySession` backend (`the_one/platform/pty_windows.py`) assigns the spawned
`cmd.exe` process to a Win32 Job Object configured with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` immediately after spawn. This Job Object serves
one purpose: *lifecycle reaping*. When `close()` calls `CloseHandle` on the job, the OS
kills every surviving process in the tree (including backgrounded grandchildren). If the
Python process dies without calling `close()`, the OS automatically closes the job handle
and fires the same reap — this is the parent-crash guarantee (analogous to bwrap's
`--die-with-parent` on Unix). The Job Object does **not** restrict what the session can
read, write, or access over the network. It is not a containment boundary.

**Known gap — `run_shell` (non-PTY) Windows tree-kill.** The one-shot shell-execution
tool (`run_shell` / `ShellTool`) fires its timeout and returns the correct error, but
killing the spawned `cmd.exe` does **not** promptly reap its child tree on Windows (no
process-group or tree kill). A backgrounded child process will run to completion. This
is a robustness gap, tracked in the Mission 15 Known Issues; a `taskkill /F /T` or
Job Object fix for the `run_shell` Windows path is planned as a Flight-5 follow-up.
It does not affect the PTY backend (which has Job Object teardown) and is consistent
with the unsandboxed Windows posture.

## Secrets

- **LLM provider API keys**: encrypted at rest via `Encryptor` (Fernet
  symmetric encryption). The encryption key file (`encryption.key` in the
  project data dir) is created with mode `0o600`. See
  [CLAUDE.md](CLAUDE.md) line 74 for the `Encryptor` integration with
  `LLMProviderRepository`. Key rotation is exposed via
  `POST /api/encryption/rotate` — like every route, it requires the
  credential gate's identified caller (see "Authentication" above) and,
  behind that, the Origin-allowlist middleware.
- **MCP source, connector, and built-in tool-config secrets**: same
  Fernet field-segregated `config`+`secrets` encryption-at-rest as the
  provider keys. Built-in tool secrets (schema v32 `tool_configs.secrets`)
  are marker-driven — any tool Config field tagged `secret: true` is
  stored encrypted and masked over the API. `web_search`'s keyed-engine
  API keys (Brave/Google PSE/Tavily) are the first consumers. See
  `the_one/agents.md` "Tool config secrets storage".
- **`__MASKED__` sentinel**: provider edit form preserves stored API keys
  when the operator hasn't touched the field. The same mask-shape +
  preserve-on-masked semantics apply to MCP, connector, and tool-config
  secret fields. See [CLAUDE.md](CLAUDE.md)
  "`__MASKED__` sentinel for API key updates".
- **Per-agent MCP override credentials**: `agents.tool_overrides` and
  `agents.mcp_overrides` are both Fernet-encrypted at rest. Of the two,
  only `mcp_overrides` carries credential material — the three
  `Substitute`-marked inner keys `env`, `headers`, and `bearer_token` are
  masked on every agent-config GET/POST/PUT response; `enabled_tools` /
  `disabled_tools` and every `tool_overrides` value stay in the clear.
  Preserve-on-PUT is resolved server-side against the stored row (Studio
  renders no credential fields at all, so it cannot round-trip a
  sentinel) — an omitted or masked credential key keeps the stored
  value, an explicit `null` clears it, any other value overwrites. Join
  in `POST /api/encryption/rotate`'s single rotation transaction as the
  fifth surface. See `the_one/agents.md` "Agent override secrets
  storage".
- **Per-agent self-configuration credentials** (M21 F01 L02): each
  enabled agent's `agt`-prefixed credential lives only inside its surface
  row's `secrets["Authorization"]` — the same Fernet-encrypted,
  API-masked `MCPSource.secrets` column every other MCP source uses, no
  new storage surface. Never returned by the enable endpoint; never
  written to `AgentConfig`. See "Authentication" → "Self-configuration
  surface" above for the credential's scope.
- `.env` is gitignored.
- No secrets land in any committed file (e.g. `.env.example`, which carries
  placeholders only).

## What This Model Excludes

The following are explicitly out of scope. A future flight extending into
any of these would need to revisit (and likely revise) the threat model
above before implementation:

- Multi-user / multi-tenant deployments
- Public internet exposure (without a reverse proxy adding auth)
- Hostile LLM provider scenarios — the LLM provider's responses are
  trusted (the project does NOT defend against an adversarial provider
  that returns malicious tool-call payloads)
- Hostile filesystem actor scenarios — the operator owns the local
  environment; the filesystem denylist is defense-in-depth against
  agent-side mistakes, not against an attacker on the same machine

## Future Work (NOT in scope today)

- **Secrets manager**: would replace local-only `.env`-style secret
  storage and unify with the existing API-key encryption surface
- **MCP server trust boundaries**: each MCP server is a separate trust
  domain; connecting to a third-party MCP server widens the trust
  boundary in ways the current model does not address
- **MCP `streamable-http` source URL gating asymmetry**: the LLM
  provider create / update / test endpoints route `base_url` through
  `_is_safe_provider_url` (scheme = `https` for non-localhost hosts;
  see `the_one/interfaces/web/api.py`). The MCP source create / update
  path does NOT apply an equivalent gate to `MCPSource.config.url`
  for `transport_type == "streamable_http"`. Today this is safe under
  the operator-trusted posture (the operator configures the URL by
  hand), but the asymmetry would widen meaningfully if a future
  "import MCP server from registry" or "share MCP source" feature
  lands. Suggested resolution: apply an `_is_safe_provider_url`-shaped
  validator to `MCPSource.config.url` at create / update time, with
  the same `localhost` exemption and the same `https` floor.
- **Multi-user form factor**: Mission 20 added per-request authentication
  for the single-user case (see "Authentication" above), but every
  authenticated caller today is indistinguishable from "the operator" —
  there is one shared long-lived credential, not one per user. A genuine
  multi-user form factor still needs what auth alone didn't provide:
  per-user identity (multiple long-lived credentials, not one), per-user
  tool isolation, and per-user encryption keys. Substantial, but narrower
  than before this mission landed.
- **CORS / OPTIONS preflight**: `OriginAllowlistMiddleware` does not
  gate `OPTIONS` requests (see code comment above `GATED_METHODS` in
  `the_one/interfaces/web/middleware.py`). The project has no CORS
  need today (single-origin local-only). If a CORS need arises, gate
  `OPTIONS` AND emit explicit `Access-Control-Allow-Origin` headers
  from a dedicated CORS middleware. Do NOT enable wildcard CORS —
  preserve the same-origin posture.
- **X-Forwarded-Host / trusted proxy**: the middleware reads the raw
  `Origin` request header. The reverse-proxy guidance at L30 above
  assumes the proxy preserves `Origin` end-to-end (most modern
  proxies do). If the proxy strips or rewrites `Origin`, the
  operator must either (a) configure the proxy to forward it, or
  (b) replace the middleware with one that consults `X-Forwarded-Host`
  after explicitly validating the proxy's trustworthiness (e.g. via
  IP allowlist on the proxy's source). The current single-user
  local-only deployment has no proxy and does not need this.
