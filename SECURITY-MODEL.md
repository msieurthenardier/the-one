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
- **F3 Decision 10**: "operator-trusted setup, NOT malicious filesystem
  actor." This decision is inherited by F4 / F5 / F6 and is the canonical
  citation for any future "should we add auth/sandboxing/...?" question.

## Authentication

- **No auth on HTTP/WebSocket routes by design.** Every endpoint, including
  state-mutating routes (`POST /api/encryption/rotate`,
  `PUT /api/agents/{name}`, etc.), is unauthenticated. Adding auth would
  violate the single-user posture documented above.
- The **Origin-allowlist middleware** (M06 F1 L5) enforces same-origin
  requests on state-mutating methods (POST/PUT/PATCH/DELETE) and on
  WebSocket upgrade handshakes, closing the drive-by-LAN attack surface
  without adding auth. Implementation:
  `the_one/interfaces/web/middleware.py::OriginAllowlistMiddleware`. Allowed
  origins default to `scheme://host:port` derived from
  `settings.host`/`settings.port`; operators behind a reverse proxy extend
  via `THE_ONE_ORIGIN_ALLOWLIST` (`.env.example` carries a commented
  example). `GET` requests and missing-`Origin` callers (curl,
  server-to-server) pass through.
- Provider URL validation (M06 F1 L5) refuses non-`https://` `base_url`
  values for non-localhost hosts at all three create/update/test endpoints
  (HTTP 422). `mock` and `ollama` provider types are skipped.

## Network Bind

- Default `host=127.0.0.1` (localhost only).
- `docker-compose.yml` overrides to `0.0.0.0` so the dev container is
  reachable from the host loopback. This is intentional for the dev form
  factor; the operator owns the docker bridge network.
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

### Passthrough degradation

On non-Linux or bwrap-missing Linux, both boxed and host-workspace spawns fall through to
`PassthroughSandbox`. Passthrough runs the command unisolated; this is logged at WARNING
level and is observable (never silent). The isolation properties above (no user FS,
network off) are NOT enforced under passthrough.

## Secrets

- **LLM provider API keys**: encrypted at rest via `Encryptor` (Fernet
  symmetric encryption). The encryption key file (`encryption.key` in the
  project data dir) is created with mode `0o600`. See
  [CLAUDE.md](CLAUDE.md) line 74 for the `Encryptor` integration with
  `LLMProviderRepository`. Key rotation is exposed via
  `POST /api/encryption/rotate` (gated by the Origin-allowlist
  middleware).
- **`__MASKED__` sentinel**: provider edit form preserves stored API keys
  when the operator hasn't touched the field. See [CLAUDE.md](CLAUDE.md)
  "`__MASKED__` sentinel for API key updates".
- `.env` is gitignored.
- No secrets land in `.env.example`, `Dockerfile`, or
  `docker-compose.yml`.

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
- **Multi-user form factor**: would require auth + per-user tool
  isolation + per-user encryption keys — a substantial change that
  inverts F3 Decision 10
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
