# agents.md

Development-facing reference for the-one. This file **codifies decisions, contracts, and invariants** that aren't visible from reading the code. For module layout, exports, and dependency direction, read the code — `ls the_one/`, `grep`, and the package-level READMEs (`the_one/mcp/README.md`, `tests/CONVENTIONS.md`) are the truth.

For usage, commands, and conventions, see `CLAUDE.md`. For the security threat model, see `SECURITY-MODEL.md`.

---

## Architecture Overview

Four layers, bottom-up:

```
Interfaces (cli.py, web/app.py)         — user-facing shells
Agent (core.py, factory.py, ...)        — loop, config, persistence
Tools / LLM / MCP                       — peer subsystems
Config (config.py)                      — pydantic-settings singleton
```

Rules: `config.py` is the leaf (imported by everything, imports nothing). `llm/`, `tools/`, and `mcp/` are peers — none imports the others. `agent/` imports from all three. `interfaces/` only imports `agent/factory.py`. No circular imports.

---

## Project Conventions

Named project-wide patterns. Apply across the codebase, not only where they were first introduced. Reviewers flag deviations by name.

### `trust-the-runtime`

Don't validate at the API layer what the runtime will catch with a clear error. Pre-validation duplicates the check, introduces TOCTOU windows, and bloats the surface translating good-enough runtime errors into hand-written API errors.

Applies whenever the runtime emits a clear, actionable error that can be matched + translated. Does NOT apply when the runtime's error is opaque (a generic `OSError` with no discriminator) — pre-check + named exception is the right call then.

### `canonical-import + convenience-re-export`

Each symbol has ONE canonical import path; lower packages MAY re-export for convenience. Code that touches the symbol's identity (subclassing, isinstance, exception handlers) MUST use the canonical path. Re-export, never re-define.

Example: `MCPSandboxError` is canonical at `the_one.mcp.errors`; `the_one.platform.sandbox.__init__` re-exports for convenience but the canonical import is `from the_one.mcp.errors import MCPSandboxError`.

### `structural-Protocol-satisfaction`

Classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. `runtime_checkable` already gives `isinstance` semantics; inheritance couples implementers to the Protocol's identity and forces no-op defaults across all implementers when the Protocol grows. Multiple unrelated classes can satisfy the same Protocol with zero retrofit.

### `verbatim-message-equality`

Error messages are tested via verbatim string equality (or substring `in str(exc)` when the message interpolates values), NOT regex. Verbatim equality pins the operator-facing wording, surfaces rephrasings as deliberate test updates, and avoids regex-overkill on string literals. Applies only to operator-facing error strings, not log messages or internal debug text.

### `gated-debug-instrumentation`

Debug-only / measurement-only modules are gated by **both** a URL query-string flag and a `localStorage` key, capture the enabled state at module-load time, and short-circuit to no-ops when disabled. Production pays zero cost; the gate survives SPA navigation. Two activation channels by design: URL is ad-hoc (no operator commitment); localStorage is sticky (survives reloads).

Reference: `App.perf` in `static/js/perf.js` — `?perf=1` or `localStorage.getItem('the-one-perf') === '1'`.

### `host-side-bench-drift-detection`

Targets that detect drift between the host bench and the canonical container run on the host (not `docker exec`), surface a clean diagnostic on failure, and are invoked manually (not on every dev iteration). Container-first tooling (`make test`, `make lint`) cannot see host venv drift.

Pattern: live under `# ── Drift detection (host-side) ──` in the `Makefile`; use `.venv/bin/python3 -c "..."` (NOT bare `python -c`, which has a PATH foot-gun); exit 0 if clean, non-zero with a clear `ModuleNotFoundError` / `AssertionError` if drift detected. Spec MUST include both a positive probe (clean → exit 0) AND a negative probe (deliberate violation → non-zero) — "clean tree exits 0" alone doesn't prove detection. For `git grep` recursive `**` pathspecs, use the `:(glob)` prefix; git's default mode treats `**` literally.

Reference: `make doctor`, `make audit`, `make audit-bytes`.

### `live-read-across-lazy-resolver-boundary`

When a provider field is **lazily resolved** on first call (sentinel → real value after a one-time upstream probe), every downstream consumer must read the field **live at the point of use**, not pre-capture it at the entry of a surrounding function. Eager capture sees the pre-resolution sentinel; the resolver fires later inside the provider call, but the captured local is never re-read.

Example: `LLMProvider.max_context_tokens` (Ollama queries `/api/show` once per model and caches on the instance). The contract is pinned by `test_usage_event_reflects_live_max_context_tokens_at_emission`.

Generalises to any field where the upstream value is unknown until a per-model / per-session probe completes. Lazily-resolved fields are owned by the provider and must be read through the provider, never copied across a function boundary.

### `container-test-entrypoints-reach-via-make`

Tests run in the container image (the canonical test environment). The `make test-*` targets chain required preconditions; raw `docker exec the-one pytest -m <marker>` bypasses them.

Concrete foot-gun: `make rebuild` wipes `~/.cache/ms-playwright/`; raw `docker exec the-one pytest -m browser` then produces hundreds of "Executable doesn't exist" errors. `make test-browser` chains `_ensure-playwright` (conditional re-install, no-op when present). Raw `docker exec ... pytest` is a debugging tool — fine for one isolated failure, wrong as the default invocation.

Before adding a NEW mitigation to a recurring foot-gun, audit whether the existing `make` chain already mitigates and the bug is in invocation form, not infrastructure form.

### `landmark-elements-over-aria-roles`

For shell-level navigation surfaces, prefer native HTML5 landmark elements (`<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>`) over `<div role="...">`. Native semantics survive ARIA spec churn and tooling improvements; ARIA roles on generic containers carry the same semantic load but require explicit role-assignment plus dev-mode regression guards.

Canonical shape for active-item nav: `<nav aria-label="..."><ul><li><button [aria-current="page"]>item</button></li>…</ul></nav>`. Active-item toggle uses `setAttribute('aria-current', 'page')` on the new active + `removeAttribute('aria-current')` on the prior — NOT `setAttribute('aria-current', 'false')` (ambiguous to AT). `role="listbox"` is INVALID when descendants are interactive (`<button>` inside `role="option"`); use `<nav>` + `<ul>` + `<button>` with `aria-current` instead.

**Selector-continuity tax**: when a leg restructures DOM (changing the container element, ARIA roles, or class hierarchy), distinguish **class-name preservation** (lexical — the class still exists) from **selector-continuity preservation** (structural — descendant/sibling selectors still resolve). Class names can survive a `<div>` → `<nav>` change while `.parent .child` descendant selectors silently break. Pre-edit, enumerate test selectors touching the restructured surface and mark each as SURVIVES or UPDATES.

---

## Subsystem contracts

These sections record decisions and invariants. Module layout, exports, and per-file behaviour live in the code and package-level READMEs (especially `the_one/mcp/README.md`).

### Encryption rotation invariant

`POST /api/encryption/rotate` re-encrypts ALL provider credentials AND ALL MCP source secrets in a single crash-safe transaction, commits the DB, then atomically replaces the key file via `os.replace`. The single-pass rotation is authoritative: a partial rotation that handled only one of the two surfaces would leave the other encrypted under a key no longer on disk.

### `__MASKED__` sentinel (LLM providers)

The provider edit form sends the literal string `__MASKED__` for unchanged `api_key` values. `update_provider` in `interfaces/web/api.py` detects this sentinel and preserves the stored value. Anyone touching the provider edit form needs to know this contract.

The same form-side validator (`_is_safe_provider_url`) must run on the **resolved** `base_url` post-`model_copy(update=data)`, not on the request payload — `__MASKED__` would otherwise fail validation.

### MCP source secrets storage

`mcp_sources` (schema v10) uses **field-segregated encryption with two columns**: `config TEXT` holds plaintext non-sensitive fields (transport-aware: `command`/`args`/`env` for `'stdio'`, `url`/`headers` for `'streamable-http'`); `secrets TEXT` holds a single Fernet-encrypted JSON blob whose decoded value is a dict of operator-marked sensitive field values. Encryption is per-row (one `Fernet.encrypt/decrypt` per row), NOT per-field inside the JSON.

The repository stores the `Encryptor` **as a reference, not a copy**, so post-rotation `install_key()` propagates to live repository instances.

**Per-key `__MASKED__` semantics**: GET returns `{secrets: {key: "***...{tail4}", ...}}` with each VALUE masked individually. On PUT, `secrets[key] == "__MASKED__"` preserves the existing stored value for that key; other keys overwrite.

**OAuth-managed secret keys**: `dcr_credentials`, `access_token`, `refresh_token`, `token_expires_at`. Written exclusively by `MCPSourceTokenStorage`; stripped + preserved on PUT by the API layer's `_OAUTH_MANAGED_SECRET_KEYS` logic.

### MCP F2 Client Foundation (authoritative for F3+)

1. **Module layout** — `the_one/mcp/` is a peer of `the_one/llm/`, NOT a sub-package of `the_one/tools/`. `MCPClient` is a service abstraction; `MCPToolProvider` wraps individual `MCPTool`s into the project's `Tool` abstraction.

2. **`_PINNED_PROTOCOL_VERSION`** — Defined in `the_one/mcp/__init__.py`. **Read at call time** via `the_one.mcp._PINNED_PROTOCOL_VERSION`, NOT `from the_one.mcp import _PINNED_PROTOCOL_VERSION` — the latter binds at module-load time and breaks `monkeypatch.setattr` in tests. Upgrade procedure: bump SDK pin → re-read `LATEST_PROTOCOL_VERSION` → update the constant → run `test_pinned_protocol_version_matches_sdk`.

3. **Pool-compat invariants** — `MCPClient` exposes `is_alive: bool` (false until `connect()` returns, false from `disconnect()` start) and `last_activity: float` (monotonic, updated per `list_tools`/`call_tool`). `disconnect()` is **idempotent and never raises**. No thread-locals, no module-globals. Naming is aligned with `PtySession` so the pool builds one reaper code path.

4. **`build_stdio_environ`** — `(source, allowlist_env) -> dict[str, str]` performs a 2-layer flat merge: `allowlist_env ∪ (config.env ∪ secrets)`, secrets winning on collision. **Do NOT consume `MCPSource.merged_config()`** for stdio env assembly — that helper produces a flat top-level merge that would inject `command`/`args` as env-var-shaped keys.

5. **Fail-hard version handshake** — `connect()` raises `MCPVersionMismatch` when `protocolVersion != _PINNED_PROTOCOL_VERSION` (exact match required). Narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist; the SDK's own `RuntimeError` is caught and re-raised as `MCPVersionMismatch` so operators see one error type. Pre-release stance; revisit at 1.0.

For runtime invariants (test-seam pattern, AsyncExitStack composition, `_DEFAULT` sentinel rationale, env-var assembly, sandbox-wrap composition, pool semantics), see `the_one/mcp/README.md`.

### MCP F3 Sandbox (authoritative for F4+)

1. **Strict-by-default trust** — Locally-spawned stdio MCP servers run in a bubblewrap jail: read-only filesystem outside an operator-configured `writable_paths` list; network OFF unless `network_allowed=True`. Operator-trust threat model: the sandbox does not defend against operator mistakes (broad `writable_paths`, `network_allowed=True` on untrusted sources), only against MCP-author mistakes / supply-chain compromise within the sandboxed scope.

2. **Profile storage** — `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` lives plaintext alongside `command`/`args`/`env`. Both fields optional; defaults `[]` and `false`. Namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`, bool-defaulting-True) are JSON-edit-only advanced knobs — API validator passes them through unchanged.

3. **`MCPSandbox` Protocol** — `prepare_spawn(profile, command, args, env, cwd=None) -> SpawnSpec`. `SpawnSpec` is `@dataclass(frozen=True)` with `command/args/env/cwd` plus Windows-only `creation_flags: int = 0` and `attribute_list`. Windows fields exist purely so a future backend can populate them without changing the Protocol.

4. **`MCPSandboxError` boundary** — Failures BEFORE bwrap successfully wraps-and-execs raise `MCPSandboxError` (bwrap missing, writable_paths entry doesn't exist, `EPERM` on `unshare`, container lacks §10 privilege grants). Failures AFTER (target spawned but exits non-zero, init handshake fails) raise `MCPConnectionError` / `MCPVersionMismatch`. NO unsandboxed fallback in production; `THE_ONE_SANDBOX_DISABLED` is never read in production paths. Catalog messages (operator-facing, verbatim-tested) live in `the_one/mcp/errors.py`.

5. **Privilege model** — Dev container: `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` (BOTH — SYS_ADMIN alone is filtered by docker's default seccomp profile). Browser-test CI: no privilege grants; `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` (BOTH; set ONLY by `tests/conftest.py::pytest_configure`). Production: no flags — bwrap is mandatory.

   **Operational guardrail**: `THE_ONE_TEST_MODE` MUST NOT appear in any Dockerfile, compose env, entrypoint script, k8s manifest, or CI variable. Presence outside pytest is a deployment defect.

6. **HOME override** — `BubblewrapSandbox.prepare_spawn` forces `env["HOME"] = "/tmp"` regardless of operator config. Reasoning: inherited HOME (`/root` in dev) becomes read-only-but-not-writable under `--ro-bind / /`; subprocess writes to `~/.cache` would EACCES; `/tmp` is writable via `--tmpfs`. Operators cannot override HOME via kv-table — sandbox policy, not configurable.

### MCP error translation

`MCPClient.{connect, list_tools, call_tool}` raise one of: `MCPVersionMismatch`, `MCPAuthRequired`, `MCPSandboxError` (stdio only), or `MCPConnectionError` (catchall). `MCPToolProvider.get_tools_for_agent` graceful-skips all four. Adding a fifth typed exception requires updating BOTH the translator AND the consumer's match list.

**Nested `try/except*` in `connect()`** — Python (PEP 654) forbids mixing `except` and `except*` in one block. The OAuth `except*` nests inside an inner `try` so the version-mismatch `except RuntimeError` can stay flat. `list_tools`/`call_tool` use a flat shape because they have no `except` siblings. Don't "tidy up" the asymmetry.

**Three 401 sources in `connect()`** — inner `except* (OAuthFlowError, OAuthTokenError)`, outer `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` walk, and `except asyncio.CancelledError` (narrowed to non-OAuth/non-401 only). Narrowing is preserved by comments; don't collapse them.

**`MCPAuthRequired` propagation** — `connect()`'s outer `except (MCPClientError, NotImplementedError): … raise` already propagates `MCPAuthRequired` cleanly. `list_tools`/`call_tool` DO need an explicit `except MCPAuthRequired: raise` guard because their outer `except McpError` would re-wrap. Asymmetry by design.

**Synthetic csid pattern** — Three csid shapes pass through `oauth/handlers.py::redirect_handler`: real csids (12-char hex), `f"test:{source_id}"` (Test connection endpoint), `f"agent_build:{source.id}"` (pool entry-worker). Disjoint by character-set construction — hex cannot produce `:`. Synthetic csids no-op the `auth_required` broadcast.

### Tool authorship contract (F4+)

Tools subclass `Tool` and declare:

- `Config: type[BaseModel]` — per-tool config schema (per-category Config classes: `FilesystemConfig`, `ExecutionConfig`/`PythonExecConfig`, `WebConfig`).
- `Requires: tuple[type[BaseModel], ...]` — opts into the shared `cross_configs` view.
- `__init__(config, cross_configs=None, agent_name=None)`.
- `execute(**kwargs) -> str`.

The two-clause `try/except` envelope (catch `ConstraintError` → `[error] [constraint] {e}`, catch other exceptions → `[error] {e}`) IS the authorship contract. `ConstraintError` lives at `the_one.tools.base` (canonical) for that reason.

**Tool policy resolver** (`the_one/tools/resolver.py`) composes tool-level config with agent-level overrides per per-key marker semantics on the tool's `Config` schema:

- `Annotated[type, Narrow]` — agent override must not widen the value (bool, int/float lower-cap, list/tuple subset). Other types raise `NotImplementedError`.
- `Annotated[type, NarrowPrefix]` — `list[str]` of paths is narrowing iff every agent entry is descendant-of (or equal to) at least one tool entry. Used by `FilesystemConfig.path_allowlist`.
- `Annotated[type, NarrowSuperset]` — `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent adds restrictions). Used by `FilesystemConfig.path_denylist`. Membership uses raw `==`; canonicalisation is consumer-side.
- `Annotated[type, Substitute]` — agent override replaces (no comparison).
- Unmarked field — agent override raises `ValueError("... no Narrow/Substitute marker ...")`.

Session-bound freshness: mid-session operator updates apply at the next `AgentFactory.create()`.

**Cross-Config dispatch**: tools declaring `Requires` receive a per-`get_tools()`-call shared `cross_configs: dict[type[BaseModel], BaseModel]` view. Configs are `frozen=True` so one tool cannot mutate the view to corrupt another's read. Both `BuiltinToolProvider` and tests inject via the same dict (e.g. fake `SearchBackend` for tests).

### Constraint surface

Active constraint types after F5:

| Type | Config field(s) | Marker(s) | Applies to |
|------|-----------------|-----------|------------|
| Path scope | `FilesystemConfig.path_allowlist`, `path_denylist` | `NarrowPrefix` + `NarrowSuperset` | 9 filesystem tools + cwd validation in 6 execution tools (cross-Config) + `download_file` destination |
| Read-size cap | `FilesystemConfig.read_size_cap_bytes`, `allow_binary_files` | `Narrow` × 2 | `read_file`, `grep`, indirect via `edit_file` pre-read |
| Output cap | `ExecutionConfig.output_cap_bytes` | `Narrow` | 6 execution tools (combined stdout+stderr, tail-preserving) |
| Timeout caps | `ExecutionConfig.timeout_seconds_default`, `timeout_seconds_max` | `Narrow` × 2 + `default <= max` model_validator | 6 execution tools |
| Command denylist | `ExecutionConfig.command_denylist` | `NarrowSuperset` | `shell`, `python_exec`, `shell_session_send` (per-call re-check). Substring match with trailing-space convention to avoid the `sudoku` false-positive class. |
| URL/host scope + SSRF | `WebConfig.*` (see below) | mixed | 4 web tools |

**`WebConfig.redirect_cap`** is `Field`-only — NO `Annotated` marker. Tool-level only; agent override raises `ValueError`.

**SSRF "no full-disable" mission invariant**: `WebConfig` has no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field. SSRF protection is always-on; operators reaching internal hosts list them in `extra_allowed_hosts` (host-by-host opt-in), not a global kill-switch. The invariant is encoded by the field's ABSENCE — no enforcement code needed. Sweep: `grep -rn 'disable_ssrf\|ssrf_disabled' the_one/` must return zero source hits (only docs allowed).

**Two-layer SSRF enforcement**: (1) `_url_check(url, cfg)` at the tool boundary refuses non-`http(s)` schemes, enforces host allowlist/denylist. (2) `SSRFGuardedTransport` resolves DNS once and pins the connect target to the resolved IP, refusing loopback / link-local / RFC1918 / cloud-metadata / IPv6 ULA + ULL by default. **IP-literal hosts** are also gated by `_is_ssrf_blocked(host)` in the transport's IP-literal short-circuit branch (gated BEFORE `super().handle_async_request`). `extra_allowed_hosts` is the operator override for both paths. DNS-rebind protection: the resolve-then-pin strategy means the second-call rebind to a private IP never reaches the connect layer.

### Subprocess environment invariant

All three execution call sites — `the_one/platform/shell.py`, `the_one/platform/interpreter.py`, `the_one/platform/pty.py::UnixPtySession` — pass an explicit subprocess env built from a hardcoded 8-key allowlist defined as `_ENV_ALLOWLIST` in `the_one/platform/env.py`:

```
PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ
```

**NOT operator-configurable** — part of the F4 trust contract: the agent has no path to read or carry through host secrets via subprocess inheritance. `the_one/platform/pty.py` consumes `_build_subprocess_env` directly to avoid a backwards `platform/ → tools/` dependency.

### Threat model — trip-wire, not fence

The `command_denylist` is a **trip-wire** catching obvious-stupid (agent typos, prompt-injection telegraphs in plaintext, operator-specific dangerous patterns). It is **NOT a fence** against adversarial agents — `bash -c "$(echo c3VkbyB3aG9hbWk= | base64 -d)"` is not in the denylist. The trip-wire produces a clean small-model-readable error rather than a destructive side-effect; bypasses are accepted because the operator-trust threat model assumes the agent is not actively adversarial. Operators wanting fence-grade isolation run the agent in a sandbox (container, VM, namespace).

False-positive surface is also accepted: `echo "do not run sudo"` is refused; workaround documented in `shell_session_send`'s tool description.

### PTY session lifecycle

- **Addressing** (Decision 4): per-explicit-handle. `shell_session_start` returns a `pty-{12hex}` token; the agent passes it back into `_send`/`_close`. Four discrete tools (`_start`, `_send`, `_close`, `_list`), not an action-enum.
- **Per-agent isolation**: registry keyed on `(agent_name, session_id)`. Cross-agent `_send`/`_close` returns the SAME error shape as a non-existent session ("not owned by this agent or does not exist") — agents cannot probe for other agents' session ids.
- **Idle reap**: single lazy asyncio reaper; wakes every 30s; closes sessions where `monotonic() - last_activity > pty_session_idle_ttl_seconds` (default 5min, `Narrow`). Registered with FastAPI lifespan for clean drain on shutdown.
- **Max concurrent**: `count_for_agent < max_concurrent_sessions` (default 5, `Narrow`). The L6 spec accepts a documented race on concurrent `_start` calls; the registry's internal lock has so far serialised correctly under single-process asyncio.
- **Idle-mark prompt detection**: `_read_until_idle` blocks until the master_fd has been silent for 100ms (2s hard cap). Robust against inconsistent shell prompts (zsh themes, sudo prompts).
- **Per-call denylist re-check** (Decision 11): every `_send` runs `_command_check(input, exec_cfg)` BEFORE forwarding. Agents cannot pre-stage a denylisted command behind an open session.

Windows: `UnixPtySession` raises `NotImplementedError("Windows ConPTY support deferred")` on import under `os.name == "nt"`.

### Origin allowlist

`OriginAllowlistMiddleware` gates state-mutating HTTP (POST/PUT/PATCH/DELETE) and WS upgrades by `Origin`/`Referer` against `THE_ONE_ORIGIN_ALLOWLIST`. Default: `http://127.0.0.1:*` and `http://localhost:*` — port-wildcard with strict-digits enforcement to reject `http://127.0.0.1.evil.com`-class confusion attacks. Missing-Origin requests pass through (server-to-server clients are NOT browser-originating). WS upgrades close at the ASGI layer (`{"type": "websocket.close", "code": 1008}`) BEFORE the route handler can `accept()` — `Depends()` runs post-`accept()` and cannot do this. Policy: `SECURITY-MODEL.md`.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`, defined inline in `core.py`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

**Capability gate**: `Agent.step()` consults `LLMProvider.supports_tools()` once per turn. When tools are unsupported (e.g. Ollama Gemma — `/api/show` capabilities lack `"tools"`), the agent drops EVERYTHING from the wire payload — both real tool schemas AND `CONTINUE_SCHEMA` — and runs a single LLM iteration as plain chat. Silent fallback is deliberate; Studio's red `no tools` chip on the model selector is the only operator-facing signal.

### Model capability surface

`LLMProvider.supports_tools()` is async, default `True` for cloud providers (OpenAI, Anthropic, mock). `OllamaProvider` overrides via `ollama_api.get_model_capabilities(base_url, model)`:

- Fetches `/api/show`, reads the `capabilities` array.
- Caches per `(base_url, model)` with 5-minute TTL.
- Returns `frozenset[str] | None`. `None` means "couldn't determine" — the agent treats that as `True` (trust the provider; surface errors via the 400-body diagnostic).

`GET /api/providers/{id}/models` async-gathers per-model capabilities for Ollama providers. Failures are non-fatal: a single capability fetch failing degrades to `null`, the rest of the list still renders.

The Pull Model dropdown is **deliberately NOT enriched** — `/api/tags` doesn't carry capabilities, so per-option chips would mean N×`/api/show` round-trips per dropdown open.

### Dev iteration

The dev container at `localhost:8484` runs `uvicorn ... --reload --reload-dir /app/the_one`. Host edits under `./the_one/` trigger a graceful uvicorn restart within ~1s. `./tests/` is bind-mounted but **not** watched (test edits don't bounce the server). Run tests with `docker exec the-one pytest ...` — fresh interpreters always see latest test code.

---

## Provider type extension checklist

Six layers must coordinate. Missing any one causes either silent rejection (validation) or runtime errors.

### Provider URL validation

`_is_safe_provider_url` (`interfaces/web/api.py`) enforces `https://` for non-localhost hosts on LLM provider `base_url`. Called at endpoint time from `create_provider`, `update_provider`, and `test_provider` — NOT a Pydantic validator (must run on the resolved `base_url` post-`model_copy`, after `__MASKED__` substitution). Two skip layers: (a) `_URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})` bypass entirely; (b) for the rest, `http://` is allowed only when host is `localhost`, `127.0.0.1`, `::1`, or `*.localdomain`. RFC1918 / link-local / `0.0.0.0` require `https://`.

### Checklist

1. **Pydantic `Literal`** — `db/models.py` `LLMProviderConfig.type`. Add the new value to the `Literal[...]` tuple, or `model_validate` rejects.
2. **`_PROVIDER_TYPE_MAP`** — `agent/factory.py`. Add `"<type>": "<registry-name>"`, or `AgentFactory.create()` raises `ValueError`.
3. **Registry `loaders`** — `llm/registry.py:_try_load_builtin`. Add the lazy-loader lambda, or `get_provider("<type>")` raises a misleading `ImportError("requires extra dependencies")`.
4. **SQLite `CHECK` constraint** — `db/schema.py` (table definition AND migration). The `llm_providers.CHECK (type IN (...))` clause hard-codes allowed values. Adding a new type requires a schema migration (see v6 for the pattern: `PRAGMA foreign_keys=OFF` + table rebuild). Without this, `INSERT` fails with `IntegrityError`.
5. **API gating / branches** — `interfaces/web/api.py`: type-specific gating in `create_provider`/`update_provider` (e.g. dev-mode gate for `mock`); branch in `test_provider`; branch in `list_provider_models`; inclusion/exclusion in `GET /api/providers/types`.
6. **Frontend** — `interfaces/web/static/js/areas/admin.js`: add `TYPE_DEFAULTS["<type>"]` (unconditional — needed for editing existing providers even if hidden from creation); add `<type>` to `KNOWN_BADGE_TYPES`; add `--badge-<type>` token in `tokens.css` + matching `.admin-provider-badge--<type>` rule in `admin.css`.
7. **`_init_provider_state(self, kwargs)`** (optional hook on `LLMProvider`) — when the new provider needs to capture configuration outside the base field set (e.g. OpenRouter's `app_url`/`app_name` analytics headers; Ollama's lazy `max_context_tokens` state).

---

## Streaming protocol

Provider-agnostic at the agent layer; per-provider native streaming sits behind `LLMProvider.stream(...)`. The base class supplies a default implementation that calls `complete()` and yields exactly one `StreamChunk(is_final=True, ...)`. Subclasses MAY override.

### `StreamChunk` contract

```python
@dataclass
class StreamChunk:
    content: str = ""               # NEW tokens since last chunk; delta semantics
    is_final: bool = False
    tool_calls: list[ToolCall] = []  # populated on final chunk
    usage: TokenUsage | None = None  # populated on final chunk where exposed
    message: Message | None = None   # synthesised assistant Message; final chunk
```

**Delta semantics**: `content` is NEW tokens, NOT cumulative. The agent accumulates by string concatenation. The final chunk MAY carry a delta (some providers emit stop-event trailing text); the accumulator checks `chunk.content` regardless of `is_final`.

**Final-chunk contract**: providers populate `message` so `Agent.step` can prefer it. When `message` is None, the agent rebuilds from accumulated `content` + `tool_calls` + `usage`.

### Per-provider notes

- **Anthropic**: native via `client.messages.stream(...)`. Catches `BadRequestError` mentioning "temperature", strips the kwarg, retries once. Gated by `yielded_any` so the retry is only safe BEFORE any chunk has emitted (Anthropic raises pre-stream in practice).
- **OpenAI**: native via `chat.completions.create(stream=True, stream_options={"include_usage": True}, ...)`. The `include_usage` flag is **required** — without it the trailing metadata chunk has no `usage` and end-of-stream telemetry breaks. Tool-call deltas accumulate by `index`.
- **Ollama**: native via `ollama_api.chat_stream`. True SSE (`data: {...}` + `data: [DONE]` terminator), distinct from `pull_model`'s JSONL. Reuses the OpenAI-shape tool-call accumulation.
- **Mock**: honours `config["stream_chunks"]: list[str]`. When unset, falls back to default-impl **inline** (NOT `super().stream(...)` delegation) for clarity.

### WS event vocabulary

| Event | When | Notes |
|------|-----|-------|
| `assistant_chunk` | Per-content-delta during streaming | |
| `assistant` | Direct-action shortcut path only | Suppressed when chunks fire |
| `tool_call` | Tool-call emitted by the model | Carries `parent_message_id` + `tool_call_id` |
| `tool_result` | Tool execution result | Carries the same pair |
| `usage` | Per-iteration final-chunk usage | |
| `done` | End of agent step | |

The streaming WS contract is **chunks-only-no-final-assistant**: when the chunk path fires, the legacy `assistant` event is suppressed server-side. The client has the accumulated text via chunks. The legacy event survives for the direct-action shortcut path (early-return in `Agent.step` before any LLM call).

**`parent_message_id` namespace convention**: live sessions use `{session.id}-msg-N`; replayed sessions use `replay-msg-N`. The frontend treats these as opaque grouping keys — different namespace prefixes between live and replay are not collisions.

### `chunks_seen` invariant

The server distinguishes streaming from direct-action via a per-iteration `chunks_seen` flag captured in the agent-step closure. The flag is set inside `_broadcast_chunk` and reset **unconditionally at the end of each Role.ASSISTANT block** in the `async for msg in agent.step(...)` loop. Unconditional matters for multi-iteration loops: a tool-call-only iteration (empty content, non-empty `tool_calls`) must still reset the flag for iteration N+1.

### Persistence contract

The synthesised final assistant `Message` is **NOT broadcast** as `{"type": "assistant"}` over the WS during streaming (the client already has the text). It IS:

- Appended to `session.history` via `session.add_event` so rejoin/refresh re-renders from server-side history.
- Appended to `result_messages` so the HTTP API caller receives the full message list.

This split — stream-deltas-over-WS, persist-full-message-server-side — is the F4 leg-04 contract. Enforced end-to-end by `test_streaming_message_persists_to_history`.

---

## Markdown rendering

Hand-rolled CommonMark-subset library at `static/js/markdown.js`. Public API: `App.markdown.parse(text) → AST`, `App.markdown.render(text) → DocumentFragment`, `App.markdown.NodeType`.

### Supported subset (v1) — contract for callers

paragraphs, ATX headers (`#`..`######`), fenced code blocks with language tag, blockquotes (single level), unordered + ordered lists (one nesting level), horizontal rules (`---`/`***`), emphasis (`*` or `_`), strong (`**` or `__`), inline code, links (including balanced-paren URLs), soft breaks (single `\n`), hard breaks (trailing TWO spaces + `\n`).

**Out of subset (v1 non-goals)**: tables, footnotes, definition lists, autolinks, reference-style links, HTML passthrough, recursive nested emphasis. The test corpus locks v1 in; expanding requires a new flight with test-case expansion.

### Nested-emphasis v1 contract

`***word***` renders as `<em><strong>word</strong></em>` (outer-em-first). Recursive nested emphasis is v2 scope. `**bold *with em***` renders as `<strong>bold *with em*</strong>` — the inner `*with em*` is literal. Mechanism: `inEmphasisRun` suppression flag once an emphasis run opens.

### XSS guarantee

Renderer constructs DOM via `document.createElement` + `textContent` exclusively. The library NEVER uses `innerHTML` — `grep -n innerHTML markdown.js` returns zero hits (including comments). SVG icon injection on the copy button uses `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` to keep the invariant. Link `href` values pass through a scheme allow-list (`http`, `https`, `mailto`, `tel`, `/`, `#`); other schemes (`javascript:`, `data:`, `vbscript:`, `file:`) are stripped to `#`. "No innerHTML anywhere in the markdown pipeline" is a structural property — future contributors cannot accidentally introduce XSS via crafted markdown.

### Robustness for streaming

`parse(null)`, `parse(undefined)`, `parse('')` all return `{type: 'document', children: []}` — no exception. Streaming callers can pass partial buffers without try/catch ceremony.

### Mid-stream rendering NOT supported

Partial markdown syntax has no canonical semantics (`**bold` mid-token has no end). The streaming path uses `textContent` accumulation followed by a single swap on `done`. Chat integration: `App.chat.renderMessage(cls, text)` markdown-renders assistant messages by default; user/tool/system stay `textContent`. Detection uses a first-token whitespace split (`cls.split(' ')[0] === 'assistant'`) so `'assistant-error'` would NOT trigger markdown.

### Extension contract

Adding a new construct: (1) `NodeType` constant, (2) tokeniser/parser case, (3) renderer branch, (4) ≥3 parametrised test cases. All four in the same leg. PRs missing test cases fail review.

---

## Design system

### Color contrast (WCAG AA regression contract)

Token contrast pairs are audited by `tests/test_design_tokens_a11y.py` against:
- **4.5:1** for body text (WCAG 1.4.3)
- **3.0:1** for large text, UI components, non-text contrast (WCAG 1.4.11)

The test file hardcodes token values to mirror `tokens.css`; canonical mirror lives in `tests/browser/design_tokens.py` (`DARK` / `LIGHT` dicts). **Before changing a color token, re-run `pytest tests/test_design_tokens_a11y.py`.** If CSS values change, update `design_tokens.py` in lockstep — the brittleness is intentional (lightweight; no CSS-parser dependency).

`tests/test_token_definitions.py` parses every `var(--x)` reference across `static/css/*.css` and asserts each token has a definition. Catches typos like `var(--accnet)` that CSS silently treats as `unset`.

### Deliberate AA exceptions

`--fg-faint` (dark `#444` on `#0a0a0a` ≈ 2.03:1; light `#94a3b8` on `#fafbfc` ≈ 2.47:1) is intentionally below body AA. Used for de-emphasized annotation labels (telemetry "in:"/"out:"/"ctx:", env-var hints), disabled placeholders, decorative recessive marks. NEVER body prose, NEVER an interactive UI affordance. Each carries a `# DELIBERATE EXCEPTION` comment in the test file; the assertion bands trip if a future retune drifts the value out of "faint" territory.

### Focus visibility convention

All `:focus-visible` rules use the same pattern: `outline: 1px/2px solid var(--accent); box-shadow: 0 0 0 3px var(--accent-glow);`. Both themes meet the 3:1 non-text contrast threshold against adjacent surfaces.

### Theme switching contract

Tri-state preference (`'dark'` | `'light'` | `'auto'`) persisted in `localStorage` under `theme-preference`. `<html data-theme="dark|light">` is applied synchronously by `static/js/theme.js` BEFORE any stylesheet load — the `<script>` is in `<head>` ahead of `<link rel="stylesheet">` to avoid FOUC.

API on `App.theme`:
- `get()` → preference or `'auto'` if unset
- `resolved()` → currently-applied theme (reads `data-theme`)
- `set(pref)` — throws on values other than `'dark'`/`'light'`/`'auto'`. `'auto'` REMOVES the localStorage key (page falls back to OS).

Auto-mode resolution: `darkMedia.matches` → dark, else `lightMedia.matches` → light, else **dark** (canonical default — the design language is dark-first). Reads/writes are try/catch-wrapped so private-browsing degrades to in-memory non-persistent.

Test environment: Playwright pins `color_scheme="no-preference"` so tests don't inherit host OS preference. To capture a specific theme: `page.evaluate("App.theme.set('light')")` + wait for `App.theme.resolved() === 'light'`.

### Typography & icons

Sizes / weights / families / icons are defined in `static/css/fonts.css` and `static/js/icons.js` — read the source rather than mirror the catalog here. Icons pinned to `lucide@v0.265.0`; the pin matters for snapshot-test stability. Add icons by appending to `Icons` in `icons.js` (preserve Lucide's `width="24" height="24" viewBox="0 0 24 24" stroke="currentColor"`).

### App shell — invariants

- The `<a class="skip-link" href="#main-content">` is the FIRST element in `<body>` (before topbar). Activating it sets `location.hash = '#main-content'`; the `hashchange` listener bails because `main-content` is not a registered area. `<main tabindex="-1">` receives programmatic focus.
- App-picker (hamburger) wiring lives INSIDE `renderTopBar()` so `closePicker` is in shared closure scope — no separate `wirePicker` function (that pattern introduced a closure-scope hazard in F3 design review).
- `App.registerArea({sidebarLabel})` — after each `switchTo`, `<aside id="app-sidebar">` receives `aria-label` = `descriptor.sidebarLabel` OR `descriptor.label + ' sidebar'`.

### Hash routing

URL format: `#area[/sub]`. `area` ∈ `{chat, studio, admin}` (defaults to `chat`); `sub` is area-specific (`sessions/<uuid>`, `agents/<name>`, bare admin-category id).

**Critical history invariant**: cross-area navigation uses `location.hash =` (pushes history); area-internal sub-change uses `history.replaceState` (replaces). `replaceState` does NOT fire `hashchange`. If this invariant is broken by using `location.hash =` for sub-navigation, a recursion loop results: `switchTo` → `replaceSub` → `hashchange` → `switchTo` → ...

Net effect: browser back exits the area entirely (or returns to the previous area) — it does NOT walk back through sub-page history within an area.

**Lifecycle**: cold entry runs `init() → activate() → hydrateState(sub)`; same-area sub-change runs `hydrateState(sub)` only. `hydrateState` runs synchronously after `activate` returns, but `activate` may have kicked off async work — `hydrateState` MUST stash a pending target and resolve it when async work completes; it MUST NOT assume data is ready synchronously.

### Keyboard operability patterns

**Listbox/option** — used where a parent row is clickable AND contains a child action affordance (the nested-button rule prohibits `<button>` inside `<button>`). Parent stays `<div role="listbox">`; rows are `<div role="option" tabindex="0" aria-selected="...">`. Keydown fires the activation handler on Enter or Space (preventDefault on Space). All options use `tabindex="0"` (no roving) — WCAG-compliant for 5-20 items.

**Deliberate accepted deviation**: `role="option"` technically should not contain interactive children. In practice NVDA and VoiceOver handle this correctly (announce the option, then the inner button separately).

**Button reset for `<span>` → `<button>` conversions**: add `background: transparent; border: none; cursor: pointer; padding: 0;`.

**SVG-resilient click dispatch**: use `e.target.closest('.chip-remove')` (not `e.target.classList.contains`). Clicking on a child SVG yields `e.target = <svg>` and the `classList` check fails silently.

**`:focus-within` reveal**: hover-only delete affordances (hidden by `display: none`) reveal via the parent's `:focus-within` selector when the user Tabs into the child button.

---

## Testing patterns

### Pytest markers

| Marker | Tests | Default `pytest` | CI |
|---|---|---|---|
| (none) | unit | runs | runs |
| `live` | real LLM APIs (paid) | skipped | skipped |
| `browser` | Playwright functional | skipped (`-m browser`) | runs `-m browser` |
| `pixel` | Playwright visual snapshot | skipped (`-m pixel`) | **never runs** |
| `requires_bwrap` | bwrap integration | skipped | skipped |

Default `addopts` deselects `live`, `browser`, `pixel`, and `requires_bwrap`.

### Test fixtures and conventions

Tests monkeypatch built-in tool registration via `the_one.tools.builtins._TOOL_CLASSES` (module-level dict) — the supported seam; do NOT reach into `BuiltinToolProvider` internals.

The four established test patterns (asyncio_mode auto; `monkeypatch.setenv` HOME for tilde-expansion tests; httpx `MockTransport` `_install_mock` recursion avoidance; kill+reap timeout-budget assertions) live in `tests/CONVENTIONS.md`.

Tests inject a fake `SearchBackend` (and other Protocol-keyed services) by overriding `cross_configs[SearchBackend]` on the per-call view — no monkeypatching of module internals. This IS the supported test seam.

### Browser test isolation

Each browser test gets its own app subprocess on a random port (`socket.bind(('', 0))`) with isolated `tmp_path` data_dir. Teardown sends SIGTERM, escalates to SIGKILL after 10s. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2.

Playwright fixtures (`playwright_instance`, `browser`) are **module-scoped**, NOT session-scoped — session scope kept the asyncio loop alive across modules and broke standalone smoke tests. Module scope still amortises Chromium within a module.

Tests rely on `data-testid` attributes on load-bearing UI elements rather than CSS classes, so they survive UI redesigns.

### Visual snapshots — local-only

Baselines under `tests/browser/__snapshots__/` are **gitignored** — local regression artifacts, not shared source. First run: `pytest -m pixel --snapshot-update`. Subsequent runs compare; >2% diff fails and writes `<name>-actual.png` + `<name>-diff.png`. CI never runs `-m pixel`. Pixel diffs are a developer's local feedback loop, not a regression gate.

### UI schema metadata

Pydantic Config schemas may declare UI-presentation hints via `Field(json_schema_extra={"ui_hint": "...", "ui_choices": [...]})`. `ui_hint` is the rendering strategy (`"dropdown"`, future: `"slider"`, `"toggle"`); `ui_choices` is a list of `{"value": ..., "label": ...}` dicts. The F6 admin form generator (`App.adminFormHelpers.renderField`) renders finite-set fields as dropdowns rather than free-form inputs. Server-side `_enrich_schema_with_markers` injects `x_marker` per property so the renderer can dispatch on marker class — admin and Studio share the same renderer with mode-specific widget shapes.

---

## Performance instrumentation

`App.perf` (`static/js/perf.js`) is the canonical surface for ad-hoc UI performance measurement. Gated per `gated-debug-instrumentation` convention (URL `?perf=1` OR `localStorage.getItem('the-one-perf') === '1'`). The `enabled` flag is captured at module-load time — toggling localStorage mid-session requires a reload.

**Browser support**: `performance.memory` is Chromium-only and only exposed in same-origin-isolated contexts; values are throttled to 100KB precision. `App.perf.captureHeap()` returns `null` when unavailable; callers must handle null.

Public surface: `mark`, `measure`, `captureHeap`, `dump`, `summary`, `reset`. Every method short-circuits when disabled. Measurement procedures and budgets for specific scenarios (area-switch cycles, long-chat rendering, large session-history list, many-agents-in-studio) live in flight design documents, not this file.

### `make rebuild` wipes Playwright Chromium

After `make rebuild`, `~/.cache/ms-playwright/` is gone — raw `docker exec the-one pytest -m browser` errors with hundreds of "Executable doesn't exist" failures. Recovery: `make _ensure-playwright` (idempotent re-install, ~30-60s). The `make test-browser` chain already chains this; only the raw invocation hits the foot-gun. See `container-test-entrypoints-reach-via-make` convention.
