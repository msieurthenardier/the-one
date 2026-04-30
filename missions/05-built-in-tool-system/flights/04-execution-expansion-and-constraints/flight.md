# Flight: Execution Expansion & Constraints

**Status**: ready
**Mission**: [Built-In Tool System](../../mission.md)

## Contributing to Criteria

- [ ] Execution tooling supports both one-shot command execution and multi-command interactive sessions, with sessions isolated from one another and from the agent's parent process environment *(F4 ships the full surface)*
- [ ] Subprocesses launched by execution tooling never inherit the parent process's environment beyond a fixed minimal allowlist sufficient for standard tools to function; the agent has no path to read or carry through host secrets via subprocess inheritance *(F4 enforces the hardcoded allowlist `(PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ)` at all 3 execution call sites)*
- [ ] Each tool category enforces tool-level constraints — path scope, read-size caps, output caps, timeout caps, URL/host scope — that apply to all agents by default, and per-agent overrides can only narrow those constraint values, never widen them *(F4 introduces output caps + timeout caps + cwd scoping for execution; F5 adds URL/host)*
- [ ] Each kept tool has automated coverage proving it behaves correctly under happy-path use and under constraint-violation use (path-scope rejections, size-cap truncation, timeout caps, SSRF blocks, binary-file refusals) *(F4 covers execution subset)*
- [ ] Filesystem and execution tooling are architected for cross-platform support: platform-specific concerns (path semantics, shell selection, interpreter resolution, pty handling) are isolated behind a clear abstraction layer *(F4 introduces `the_one/platform/pty.py` + a `PtySession` protocol; Unix `pty` ships, Windows `ConPTY` deferred)*

---

## Pre-Flight

### Objective

Land the full execution-tool surface and the first constraint enforcement on F2's resolver seam beyond filesystem. Migrate `ShellTool` and `PythonExecTool` to a per-category `ExecutionConfig` (timeout caps, output cap, command denylist, hardcoded subprocess env allowlist; cwd scoping borrows from `FilesystemConfig.path_allowlist` via a new cross-Config dispatch). Add an interactive shell session surface — `shell_session_start`, `shell_session_send`, `shell_session_close` (plus optional `shell_session_list`) — built on Unix `pty` (stdlib) behind a `PtySession` protocol; Windows `ConPTY` is **explicitly deferred** to a future mission. Sessions are per-explicit-handle, isolated per-agent, idle-reaped at 5 minutes, capped at 5 concurrent per agent.

L1 promotes `ConstraintError` from `filesystem.py` into `the_one/tools/base.py` (next to the `Tool` ABC — the two-clause `try/except` envelope is the tool authorship contract) and adds cross-Config dispatch to `BuiltinToolProvider.get_tools` so execution tools can read `FilesystemConfig` for cwd validation. The container source-vs-installed-package sync friction surfaced in F3's debrief is fixed as a **pre-flight routine-maintenance pass** (compose-bind-mount only, no Dockerfile surgery) so F4's implementation legs run without `docker cp` overhead.

Includes a guided HAT leg validating that the agent recovers gracefully from every new constraint type and that session isolation holds across concurrent agent invocations.

### Open Questions

- [x] **Session addressing** — per-explicit-handle (`session_id` token returned from `start`, passed back into `send`/`close`). Resolved during flight design discussion. *(see Decision 4)*
- [x] **Idle TTL default** — 5 minutes (configurable Narrow). Resolved. *(see Decision 5)*
- [x] **Max concurrent sessions per agent** — 5 (configurable Narrow). Resolved. *(see Decision 5)*
- [x] **Tool surface — discrete vs. action-enum** — three discrete tools (`shell_session_start`, `shell_session_send`, `shell_session_close`) plus optional `shell_session_list`. Resolved. *(see Decision 6)*
- [x] **Cross-turn lifetime** — sessions persist across agent turns for the FastAPI process lifetime; container restart kills all sessions; no SQLite persistence. Resolved. *(see Decision 5)*
- [x] **Timeout config shape** — two Narrow ints: `timeout_seconds_default` (default 30 for one-shot, 30 for pty-send) and `timeout_seconds_max` (default 120, hard `Field(le=3600)` ceiling). `model_validator(mode="after")` enforces `default ≤ max`. Resolved via architect review. *(see Decision 1)*
- [x] **Output cap default** — 256 KB single combined stdout+stderr cap; tail-preserving truncation; exit code always preserved separately; `ui_hint` dropdown with execution-specific scale. Resolved via architect review. *(see Decision 2)*
- [x] **Command denylist match shape** — substring on the full command line with trailing-space convention to avoid the `sudoku` false-positive class. "Trip-wire, not a fence" — operator-trusted threat model. Resolved via architect review. *(see Decision 3)*
- [x] **cwd scoping** — reuse `FilesystemConfig.path_allowlist`/`path_denylist` via new cross-Config dispatch in `BuiltinToolProvider.get_tools`. Resolved via architect review. *(see Decision 7)*
- [x] **L1 scaffolding scope** — `ConstraintError` extraction + cross-Config dispatch in L1; container sync fix as pre-flight routine-maintenance pass; `_filesystem_check_*` unification deferred to post-F4 maintenance. Resolved via architect review. *(see Decision 8)*
- [x] **`python_exec` retention** — retained + hardened, default timeout bumped 60s → 90s, description disambiguated from `shell_session_send`. Resolved via architect review. *(see Decision 9)*
- [ ] **`PtySession` protocol shape** — exact ABC method signatures (`start()`, `send(input, timeout) -> bytes`, `close()`, `is_alive: bool`, `last_activity: float`). Resolved at L5a leg-design time.
- [ ] **PTY readiness signal after `start`** — does `start` block until shell prompt is detected, or return immediately and let the agent observe via `send("")` round-trip? Recommend block-until-prompt (cleaner UX). Resolved at L5a leg-design time.
- [x] **Reaper task lifecycle** — single asyncio task spawned at first session creation, registered with FastAPI lifespan for clean shutdown. Resolved at flight-design time per architect feedback. *(see Decision 5)*
- [x] **Per-call denylist enforcement in pty sessions** — yes, per-call. Resolved. *(see Decision 11)*

### Design Decisions

**Decision 1 — Two timeout fields: `timeout_seconds_default` + `timeout_seconds_max`** (both `Annotated[int, Narrow]`):

```python
class ExecutionConfig(BaseModel):
    timeout_seconds_default: Annotated[int, Narrow] = Field(
        30, ge=1, le=3600, description="Used when agent omits timeout."
    )
    timeout_seconds_max: Annotated[int, Narrow] = Field(
        120, ge=1, le=3600, description="Hard ceiling; agent value clipped."
    )

    @model_validator(mode="after")
    def _default_le_max(self) -> "ExecutionConfig":
        if self.timeout_seconds_default > self.timeout_seconds_max:
            raise ValueError(
                f"timeout_seconds_default ({self.timeout_seconds_default}s) "
                f"must be <= timeout_seconds_max ({self.timeout_seconds_max}s)"
            )
        return self
```

- Rationale: F3's `FilesystemConfig.read_size_cap_bytes` precedent is "one Narrow field per orthogonal constraint with `Field(ge=..., le=...)` for hard bounds." Timeout has two orthogonal questions (default vs ceiling) so two fields are warranted. `Option A — max only` would force the agent to always pass `timeout`, regressing today's UX.
- Trade-off: two Narrow fields where one might do; the `model_validator` cross-field invariant adds a small validation step.
- Resolver interaction: both fields use existing `_check_narrow` int branch. The `model_validator` runs at `schema.model_validate(merged)` AFTER narrowing, so an agent can't widen `default` past a narrowed `max`.
- Per-tool defaults: `ShellTool` 30s default / 120s max; `PythonExecTool` 90s default / 120s max; `shell_session_send` 30s default / 120s max. (The `default` is **per-Config**, not per-tool — but each tool can have its own `Config = ExecutionConfig` with different declared defaults via subclass override if needed. Initial proposal: single `ExecutionConfig` shared across all 3 tools; Python's higher default is documented as a known asymmetry that doesn't matter at the cap-check layer.)
- **Decision sub-bullet**: Single shared `ExecutionConfig` for all 3 execution tools. Per-tool default-timeout asymmetry handled by `python_exec` description encouraging the agent to pass explicit `timeout` for compute-heavy work; the Config default is one number.

**Decision 2 — `output_cap_bytes` default 256 KB; tail-preserving truncation; combined cap**:

```python
output_cap_bytes: Annotated[
    int,
    Narrow,
    Field(
        ge=1024,
        le=104_857_600,  # 100 MB hard ceiling
        json_schema_extra={
            "ui_hint": "dropdown",
            "ui_choices": [
                {"value": 32_768,    "label": "32KB — very small models"},
                {"value": 65_536,    "label": "64KB — small/7B-class friendly"},
                {"value": 262_144,   "label": "256KB — default (typical test runs)"},
                {"value": 524_288,   "label": "512KB — long build logs"},
                {"value": 1_048_576, "label": "1MB — Opus headroom, parity with read-size cap"},
                {"value": 5_242_880, "label": "5MB — Opus 1M only"},
            ],
        },
    ),
] = 262_144
```

- Rationale: Output cap protects agent context — same calculus as F3's `read_size_cap_bytes` but tighter at the low end because execution output skews "all-or-nothing" log dumps. 256 KB ≈ 32% of an Opus 200K context for a single tool call — enough headroom for a few large outputs per turn without crowding tool definitions and history.
- **Truncation strategy**: tail-preserving. Drop the FRONT, retain the LAST `output_cap_bytes` bytes. Build/test output puts the actionable signal (failures, summary, traceback) at the end. Marker: prepend `[... truncated N bytes; showing last M bytes of combined stdout+stderr ...]\n` to the retained tail.
- **Tail-preserving applies uniformly to all 3 surfaces** — `shell`, `python_exec`, `shell_session_send`. `python_exec` users producing large output should print explicit summaries at the end; tool description encourages this convention. (Architect raised this as a possible asymmetry; we accept the uniform tail policy because the alternative — per-tool truncation strategy — adds Config surface for marginal gain.)
- **Single combined stdout+stderr cap** (not separate). CLIs interleave the two; agents reason about them as one stream. One knob, simpler operator UX.
- **Exit code always preserved**, never truncated. Reported in a separate suffix line: `[exit code: N]`.
- **`_truncate_output` helper signature**: `_truncate_output(stdout: bytes, stderr: bytes, returncode: int, cfg: ExecutionConfig) -> tuple[str, bool]` — returns `(formatted_text, was_truncated)`. The bool is for test purchase (`assert was_truncated is True` is sharper than substring-matching the marker line).
- Trade-off: an agent that wants "the first N bytes of a never-finishing log" can't get it; that's a deliberate trade — interactive sessions exist for that case.

**Decision 3 — Command denylist as substring match with trailing-space convention; "trip-wire not fence" framing**:

```python
DEFAULT_COMMAND_DENYLIST: tuple[str, ...] = (
    # Privilege escalation (trailing space avoids the `sudoku` false positive)
    "sudo ", "su ", "doas ",
    # Destructive filesystem
    "rm -rf /", "rm -rf ~", "rm -rf $HOME",
    # Disk / partition
    "mkfs", "dd if=", "dd of=/dev/",
    # System control
    "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
    # Fork bombs
    ":(){ :|:& };:",
    # Kernel / module loading
    "insmod ", "rmmod ", "modprobe ",
    # Network destructive
    "iptables -F",
)

# In ExecutionConfig:
command_denylist: Annotated[list[str], NarrowSuperset] = Field(
    default_factory=lambda: list(DEFAULT_COMMAND_DENYLIST)
)
```

- Match shape: `any(token in command_str for token in cfg.command_denylist)`. Substring match on the full command string.
- Error message: `[error] [constraint] command contains denylisted token '{token}'` — small-model-readable in one shot.
- **Threat model framing** (carry to `agents.md` and CLAUDE.md):
  - **IS for**: catching obvious-stupid (agent typos, prompt-injection telegraphs in plaintext, the operator's company-specific dangerous patterns). A trip-wire that produces a clean small-model-readable error rather than a destructive side-effect.
  - **IS NOT for**: preventing a determined adversarial agent. Bypass paths exist (env-var aliasing, `bash -c "..."`, base64-decoded scripts, write-then-execute). The real defense-in-depth lives in the env allowlist + filesystem path-scope + the operator's trust decision when enabling `shell` at all.
- Rationale for substring over regex: small-model-friendly applies to operator config too — non-experts can author `"sudo "`; `r"\bsudo\b"` requires regex literacy. Substring also catches `bash -c "sudo ..."` because `"sudo "` appears in the wrapped command string; first-token match (`command.split()[0]`) misses this. Regex's "precise word boundary" appeal is a security mirage given the threat model.
- `NarrowSuperset` semantic: agents can ADD entries (more restrictive); cannot REMOVE operator baseline entries. Same shape as `FilesystemConfig.path_denylist`.

**Decision 4 — Per-explicit-handle session addressing**:

`shell_session_start(cwd?: str) → session_id` returns an opaque token formatted as `f"pty-{uuid4().hex}"` (a 36-char string with the `pty-` prefix for visual recognition in logs). Subsequent `shell_session_send(session_id, input, timeout?)` and `shell_session_close(session_id)` calls take that token. The session registry is keyed on `(agent_name, session_id)`; cross-agent leakage is impossible at the storage layer (an agent passing another agent's `session_id` gets `[error] [constraint] session 'pty-xxx' not owned by this agent`).

- **`agent_name` plumbing requires non-trivial scaffolding work** — it is NOT currently available at `BuiltinToolProvider.get_tools` call time. Today's chain: `AgentFactory.create()` (`the_one/agent/factory.py:~117`) calls `provider.get_tools(tool_configs, agent_overrides)` — no agent name passed. The `ToolProvider` Protocol (`the_one/tools/provider.py:29-35`) must be widened to `get_tools(tool_configs=None, agent_overrides=None, agent_name=None)`. `BuiltinToolProvider` threads `agent_name` into `Tool.__init__(config, cross_configs=None, agent_name=None)`. F3 tools that don't need it ignore it.
- **Protocol widening is non-breaking for `runtime_checkable` Protocol** — adding kwargs to `get_tools` is a Liskov-safe widening; future MCP providers must accept the new kwarg, but existing `isinstance` checks still pass. Document in L1b's spec.
- The per-agent keying is for STATE ISOLATION, not adversarial separation — agents are not user-identifiable at the WebSocket level; the security model is "operator trusts agents identically".
- **Agent rename behavior**: if an operator renames `Qwen → Qwen-prod`, all that agent's open sessions become orphaned (keyed on old name) until idle-reaped. Acceptable trade-off; documented as known-non-issue for F4. Future F6 (admin) may revisit when rename UX lands.
- `shell_session_list() → list[session_id]` is **committed for F4** (NOT deferred). Single-method tool, ~30 LoC. Allows the agent to recover after long context windows where it forgot its handles. Total session-tool count is **4**, not 3-4.

**Decision 5 — 5-minute idle TTL + 5 concurrent + process-lifetime persistence + FastAPI-lifespan-registered reaper**:

```python
pty_session_idle_ttl_seconds: Annotated[
    int,
    Narrow,
    Field(
        300,
        ge=10,
        le=3600,
        description="Reap sessions idle longer than this.",
        json_schema_extra={
            "ui_hint": "dropdown",
            "ui_choices": [
                {"value": 60,   "label": "1m — aggressive (fast turns only)"},
                {"value": 300,  "label": "5m — default"},
                {"value": 900,  "label": "15m — long thinking turns"},
                {"value": 1800, "label": "30m — long multi-tool sequences"},
                {"value": 3600, "label": "1h — max"},
            ],
        },
    ),
]
max_concurrent_sessions: Annotated[
    int,
    Narrow,
    Field(
        5,
        ge=1,
        le=50,
        description="Per-agent cap on simultaneous sessions.",
        json_schema_extra={
            "ui_hint": "dropdown",
            "ui_choices": [
                {"value": 1,  "label": "1 — single session only"},
                {"value": 3,  "label": "3 — minimal parallel work"},
                {"value": 5,  "label": "5 — default"},
                {"value": 10, "label": "10 — heavy parallel work"},
                {"value": 20, "label": "20 — max"},
            ],
        },
    ),
]
```

- **Idle TTL**: time since last `send` response. NOT a per-call timeout (that's `timeout_seconds_*`). 5 minutes is generous enough for typical agent reasoning turns (Opus thinking ~30-60s; long multi-tool turns ~90s) and tight enough to reap abandons.
- **Reaper task lifecycle — registered with FastAPI lifespan**: the reaper is a single asyncio task. It is spawned lazily at first session creation AND registered with FastAPI's `lifespan` context (`app.state` or equivalent) so shutdown awaits and cancels it cleanly. On `make rebuild` and on container shutdown, lifespan teardown calls `task.cancel()`; reaper catches `CancelledError`, drains its registry by calling `close()` on each session, exits. This prevents a late-in-flight surprise where the reaper holds references and blocks shutdown. **L5b's spec must include a `lifespan_register(app)` hook AND an integration test asserting clean shutdown.**
- Reaper wakes every 30s, checks `last_activity` on each registered session, calls `close()` on expired ones.
- **Max concurrent (5)**: when an agent already has 5 sessions and calls `shell_session_start`, the tool returns `[error] [constraint] max concurrent sessions reached (5); close an existing session first`. Agent override can lower; can never widen above operator setting.
- **Cross-turn lifetime**: sessions persist across agent turns for the FastAPI process lifetime. Container restart kills all sessions (no SQLite persistence — keeps it simple, no resurrection migration story). This is documented in the tool description so agents understand they can resume sessions across turns.

**Decision 6 — Three discrete tools (plus one optional)**:

```
shell_session_start(cwd?: str) → str  # session_id token
shell_session_send(session_id: str, input: str, timeout_seconds?: int) → str  # output
shell_session_close(session_id: str) → str  # ack
shell_session_list() → str  # newline-delimited session_ids (optional)
```

- Discrete tools over `shell_session(action="start"|"send"|"close")` because:
  - Each tool has its own description string visible to small-model agents — clearer affordances.
  - F3 set the precedent (`read_file`/`write_file`/`edit_file` are discrete, not `file(action=...)`).
  - The action-enum form requires the model to pick the right action AND the right args; discrete tools collapse that to one decision.
- All four tools (`start`, `send`, `close`, `list`) ship in F4 per Decision 4. `list` is single-method (~30 LoC); committing at flight-design time avoids the F3 anti-pattern of "design discipline" being negotiable mid-flight.

**Decision 7 — cwd scoping reuses `FilesystemConfig.path_allowlist` via cross-Config dispatch**:

`BuiltinToolProvider.get_tools` is extended to:
1. **Resolve all distinct `Config` classes referenced by `_TOOL_CLASSES`** (NOT just the enabled subset — provider runs before factory's enabled-filter; resolving all is cheap and avoids leaking the enabled-set contract into `ToolProvider`).
2. Resolve each Config once via the existing `resolve(schema, tool_cfg, agent_override)` call.
3. Build a `dict[type[BaseModel], BaseModel]` (call it `cross_configs`).
4. Pass each tool BOTH its own resolved Config AND a read-only view of `cross_configs` into `Tool.__init__(config, cross_configs=None, agent_name=None)`.

The `Tool` ABC gains a class-level declaration:

```python
class Tool(ABC):
    Config: type[BaseModel] = _EmptyConfig
    Requires: tuple[type[BaseModel], ...] = ()  # NEW — empty default

    def __init__(
        self,
        config: BaseModel | None = None,
        cross_configs: dict[type[BaseModel], BaseModel] | None = None,
        agent_name: str | None = None,
    ) -> None:
        self._config = config or self.Config()
        self._cross_configs = cross_configs or {}
        self._agent_name = agent_name
```

Tools that need cross-Configs declare them at class level:

```python
class ShellTool(Tool):
    Config = ExecutionConfig
    Requires = (FilesystemConfig,)
```

The provider iterates `cls.Requires` to know what to inject. F3 tools that don't declare `Requires` get the empty default — backward-compatible.

Execution tools that need cwd validation pull `cross_configs[FilesystemConfig]` and call a shared helper:

```python
def _cwd_check(cwd: str | Path, fs_cfg: FilesystemConfig) -> Path:
    """Validate cwd against FilesystemConfig path scope; additionally
    enforce that the resolved path is a directory and exists."""
    canonical = _filesystem_check(cwd, fs_cfg)  # reuse F3 helper verbatim
    if not canonical.is_dir():
        raise ConstraintError(f"cwd '{canonical}' is not a directory")
    return canonical
```

- Rationale: single source of truth for "where can the agent operate"; an agent denied `read_file('/etc/passwd')` should also be denied `cd /etc && cat passwd`. F6's admin UI renders ONE "scope" panel governing both fs and execution.
- Trade-off: `Tool.__init__` signature gains TWO optional kwargs (`cross_configs`, `agent_name`); existing tools ignore. F3's tests use `cls(cfg)` calls — backward-compat preserved. New tests for execution will pass all three: `ShellTool(ExecutionConfig(), cross_configs={FilesystemConfig: FilesystemConfig()}, agent_name="test-agent")`.
- **Frozen Configs**: F4 sets `model_config = ConfigDict(frozen=True)` on both `FilesystemConfig` (retroactive in L1a/L1b) and `ExecutionConfig` (born frozen in L2). `cross_configs` are shared across tools; mutation by one tool would corrupt other tools' shared view. Frozen Pydantic guarantees immutability at runtime. Belt-and-suspenders for the cross-tool sharing contract.
- Forward-reference: when MCP integration arrives, MCP servers will likely need similar cross-Config access (e.g., a Slack tool reading a `CredentialsConfig`). The dispatch lives in the provider, not the resolver — clean. **F5's `download_file`** will declare `Requires=(FilesystemConfig,)` for write-target validation — same pattern.
- Same `[constraint] path '...' outside allowlist` error whether agent tried `read_file` it or `cd` to it (coherent error surface).

**Decision 8 — L1 split into L1a + L1b; container sync fix as strongly-recommended pre-flight maintenance; helper unification deferred**:

- **Pre-flight routine maintenance** (STRONGLY RECOMMENDED — not a hard prerequisite; standalone commit on `main` ideally before F4 L1a starts): bind-mount fix in `docker-compose.yml`. Mount `./the_one` to BOTH `/app/the_one` AND `/usr/local/lib/python3.11/site-packages/the_one` (read-write). Two compose lines, reversible. NO Dockerfile surgery. Validates with `docker compose up`, hit `/api/info`, run one filesystem tool through the API. **If skipped**: F4 ships fine; just costs ~10 min/leg of `docker cp` overhead per F3 debrief evidence.
- **L1a — `ConstraintError` extraction** (~30 LoC): move `ConstraintError` from `the_one/tools/filesystem.py` to `the_one/tools/base.py` (NOT a new `_constraint.py` module — the two-clause try/except envelope IS the tool authorship contract; documenting them together keeps the surface compact). Update `filesystem.py` to import. F3's test suite passes unchanged. Single-concern, mechanical move.
- **L1b — Cross-Config dispatch + agent_name plumbing** (~80 LoC): widen `ToolProvider.get_tools` signature to take `agent_name: str | None = None`; thread from `AgentFactory.create()` (`the_one/agent/factory.py:~117`); extend `BuiltinToolProvider.get_tools` to build `cross_configs` dict; widen `Tool.__init__` to `(config, cross_configs=None, agent_name=None)`; add `Requires: tuple[type[BaseModel], ...] = ()` default on `Tool` ABC; set `model_config = ConfigDict(frozen=True)` on `FilesystemConfig` (retroactive). F3 tests pass unchanged (all current tools have empty `Requires`). New tests for: provider builds cross_configs unconditionally; tool with Requires receives the right Config; agent_name threads through; frozen Config can't be mutated.
- **Deferred to post-F4 maintenance**: `_filesystem_check_*` helper unification. F4 doesn't directly need it; mixing filesystem cleanup with execution-tool design risks regressing F3.
- Rationale for the L1a/L1b split: each is a single-concern leg with a separate review surface. L1a is a 30-LoC mechanical move; L1b is the architectural foundation for D7 (cross-Config) and D4 (agent_name). Architect flagged L1 bundling as a smell. Splitting also unblocks parallel work — L2 (`ExecutionConfig`) only needs L1a's `ConstraintError` import, not L1b's full plumbing.

**Decision 9 — `python_exec` retained + hardened with description disambiguation**:

- Retain — small-model agents reach for `python_exec` differently than `shell` (Qwen 2.5:7b especially struggles with multi-line Python through shell quoting; documented in F3 mission Known Issues).
- Constraint surface mostly mirrors `shell`: same `ExecutionConfig`, same env allowlist, same output cap, same cwd scoping.
- **Default timeout bumped 60s → 90s**: Python is more often used for compute (numerics, parsing) than `shell` is. Defensive; the cap-check layer treats this as one number on the shared `ExecutionConfig`, but the per-tool description tells the agent "compute work is expected; pass higher `timeout` for long jobs."
- **Description tweak**: "Execute Python code in a one-shot subprocess. Prefer this over `shell` for computation, parsing, or any multi-line Python; use `shell_session_send` for interactive REPL work."
- Module-level denylist (`subprocess`, `os.system`, `socket`) explicitly OUT OF SCOPE for F4 — earn its complexity later if it surfaces a real attack.

**Decision 10 — Subprocess env hardcoded allowlist test + pty fork-then-exec mechanism**:

A single test asserts the env an execution subprocess sees is exactly `{"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TZ"}` and nothing else. Run for `ShellTool`, `PythonExecTool`, AND `shell_session_send` — same invariant, three call sites. Test pattern: subprocess prints `os.environ` to stdout; test parses and asserts `set(env.keys()) == expected_allowlist`.

**For `shell` and `python_exec`**: the env allowlist is passed via the existing `env=` kwarg on `run_shell` / `run_python` (`platform/shell.py:58`, `platform/interpreter.py:41`). Both helpers already accept `env: dict[str, str] | None`; F4 just constructs the allowlist from `os.environ` and passes it. Trivial.

**For `shell_session_send`**: subtler. `pty.fork()` (or `os.fork()` + `pty.openpty()`) inherits the parent process's full environment. To enforce the allowlist, the implementation MUST use **fork-then-execv** (NOT `pty.spawn`). Sequence: (1) fork; (2) child: `os.environ.clear()`, then `os.environ.update(ALLOWED_ENV)`; (3) child: `os.execvp(shell, [shell])`. The exec replaces the child process image with the shell, which now sees only the allowlisted env. **L5a's spec must describe this mechanism explicitly** — the simpler `pty.spawn(shell)` would inherit the parent env and silently break the invariant.

`ALLOWED_ENV` is constructed at session-start time from the parent's `os.environ`:
```python
_ENV_ALLOWLIST = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TZ")
def _build_subprocess_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
```

Out-of-scope: per-process env tweaks (operators may want to add `THE_ONE_DEV_MODE` or a custom var). Mission spec is firm: the allowlist is **hardcoded, NOT operator-configurable**. A future secrets-manager mission will inject named secrets on top of this baseline.

**Decision 11 — pty-session command-denylist enforcement is per-call; same substring shape as one-shot shell**:

`shell_session_send(session_id, input, ...)` re-checks `input` against `cfg.command_denylist` BEFORE writing to the pty. An agent must not be able to bypass the denylist by starting an unrestricted session and then sending denylisted commands through it. Same substring match shape as one-shot `shell`.

- **False-positive surface — accepted intentionally and documented in the tool description**: a denylisted token appearing in legitimate input (e.g., `echo "do not run sudo"`) is refused. The `shell_session_send` tool description states explicitly: *"Inputs are filtered against the same denylist as one-shot `shell`. Echoing or printing denylisted tokens (e.g. `'sudo'`) requires writing them through a file (`echo $S > /tmp/x` after setting `S` outside the denylist) — this is intentional, not a bug."* The operator's denylist is the operator's contract; legitimate-text use cases work via redirection.
- Refinements considered and rejected at flight-design time:
  - "Quote-aware substring" (only refuse outside quotes): more code, more edge cases (heredocs, escaped quotes), unclear semantics for shell metacharacters. Rejected.
  - "First-token-only" on pty input: defeats the use case (agent types `bash -c "sudo ..."` inside the session). Rejected.
- Forward-reference: an "interactive REPL" tool that lets an agent type FREELY into a Python REPL would need a different model (the agent is typing Python expressions, not shell commands). F4 keeps the simple substring check; F5+ may revisit if Python REPLs get added.

### Prerequisites

- [x] M05 Flight 3 landed and merged to `main` (commit `fae20c9`).
- [x] Schema is at v8 (no schema changes in F4; verified `the_one/db/schema.py:9 CURRENT_VERSION = 8`).
- [x] `the_one/tools/resolver.py` ships `Narrow` / `NarrowPrefix` / `NarrowSuperset` / `Substitute` / `_check_narrow` / `_EmptyConfig` / `resolve()` (F2 + F3 L1).
- [x] `the_one/tools/filesystem.py` ships `ConstraintError`, `FilesystemConfig`, `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `_check_read_size`, `_is_binary`, `_is_descendant` (F3 L2-L6).
- [x] `the_one/platform/shell.py` ships `select_shell`, `run_shell` with `env=None` kwarg + kill+reap (F2).
- [x] `the_one/platform/interpreter.py` ships `resolve_python`, `run_python` with `env=None` kwarg + kill+reap (F2).
- [x] `the_one/tools/builtins.py` `_TOOL_CLASSES` has 13 entries (post-F3); F4 mods 2 existing + adds 4 new = 17 entries post-F4.
- [x] All flight-design Open Questions resolved (12/15 fully resolved; 3 punted to L5 leg-design time).
- [ ] **Pre-flight routine maintenance pass landed**: container sync bind-mount commit on `main` BEFORE F4 L1 starts. (Not yet done; tracked as the first action item below the checklist.)
- [ ] No port/network conflicts — F4 doesn't introduce new services, ports, or env vars beyond the hardcoded subprocess allowlist.
- [ ] User approves leg breakdown (Phase 4 sign-off).

### Pre-Flight Checklist
- [x] All open questions resolved (13/15; 2 leg-design-time, both at L5a)
- [x] Design decisions documented (11; refined per architect feedback)
- [x] Prerequisites verified (8 of 9; pre-flight maintenance pass pending)
- [x] Validation approach defined → see Verification section
- [x] Legs defined → see Legs section below

**Pre-flight action**: land the container sync bind-mount commit on `main` before starting F4 L1. Estimated 30 min including manual smoke. Risk: if compose change breaks the running container, revert is two-line. Validates with `docker compose up`, `/api/info`, single `read_file` API call.

---

## In-Flight

### Technical Approach

**Order rationale (10 legs after pre-flight, executed in dependency order):**

1. **L1a — `ConstraintError` extraction.** Mechanical move from `filesystem.py` to `base.py`; ~30 LoC. F3 tests pass unchanged. Single-concern; unblocks downstream L2 imports.
2. **L1b — Cross-Config dispatch + `agent_name` plumbing + frozen Configs.** Widens `ToolProvider.get_tools` signature; widens `Tool.__init__`; adds `Requires` ABC attribute; sets `frozen=True` on `FilesystemConfig`. ~80 LoC + tests. Architectural foundation for D7 (cwd scoping) and D4 (per-agent session keying).
3. **L2 — `ExecutionConfig` model + `_command_check` + `_cwd_check` + `_truncate_output` helpers.** Defines the 5 constraint fields; helpers encapsulate the 3 enforcement points. `frozen=True`. Tested in isolation; no tool wiring yet.
4. **L3 — Migrate `ShellTool`.** Wire `Config = ExecutionConfig`; `Requires = (FilesystemConfig,)`; rewrite `execute` to call `_command_check`, `_cwd_check`, `run_shell` with hardcoded env, then `_truncate_output` via tail-preserving cap. Update existing tests; add new constraint-violation tests.
5. **L4 — Migrate `PythonExecTool`.** Same shape as L3 with the description tweak from Decision 9.
6. **L5a — `PtySession` protocol + Unix `pty` implementation.** `the_one/platform/pty.py` adds the ABC and the Unix implementation with fork-then-execv env-allowlist enforcement. Resolves the protocol-shape and readiness-signal OQs. Tests cover happy-path send/receive, timeout, env-allowlist invariant.
7. **L5b — Session registry + idle reaper + max-concurrent enforcement + lifespan hook.** `the_one/tools/_session_registry.py` (per-agent dict). Idle reaper as asyncio task registered with FastAPI lifespan. Resolves the reaper-lifecycle OQ. Tests cover idle reap, max-concurrent cap, cross-agent isolation, clean lifespan-shutdown.
8. **L6 — Four pty session tools.** `shell_session_start`, `_send`, `_close`, `_list`. Wire L5a/L5b infrastructure to Tool classes. Per-call denylist enforcement on `_send` (Decision 11). Register in `_TOOL_CLASSES` and Studio's `TOOL_CATEGORIES`.
9. **L7 — HAT (interactive; non-autonomous).** Operator drives the agent through every constraint type via the API; validates session isolation across two concurrent agent invocations.
10. **L8 — Integration verification.** Full unit + browser + AIAT live smoke; F4-specific regression sweeps; CLAUDE.md + agents.md refresh; mission Known Issues append for any HAT-surfaced small-model artifacts.

### Checkpoints

- [ ] **Pre-flight maintenance landed** — container bind-mount commit on `main`; `docker cp` overhead is gone for F4 implementation legs.
- [ ] **`ConstraintError` lives in `base.py` + cross-Config dispatch** — `ConstraintError` exported from `the_one/tools/base.py` (next to `Tool` ABC); `the_one/tools/filesystem.py` imports rather than defines; `BuiltinToolProvider.get_tools` builds `cross_configs` dict and passes to `Tool.__init__`; existing F3 tests pass unchanged; new tests for cross-Config dispatch.
- [ ] **`ExecutionConfig` + helpers landed** — Pydantic Config with 5 annotated fields + `model_validator` cross-field invariant; `_command_check`, `_cwd_check`, `_truncate_output` module-level helpers; full constraint-matrix tests.
- [ ] **`ShellTool` migrated** — `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`; constraint enforcement at all 3 sites (timeout, output cap, denylist) plus env allowlist and cwd scoping; existing tests adapted; new tests for each constraint type.
- [ ] **`PythonExecTool` migrated** — same as ShellTool with the 90s default + description tweak.
- [ ] **`PtySession` infrastructure shipped** — `the_one/platform/pty.py` + `PtySession` ABC + per-agent registry + idle reaper task; subprocess env allowlist enforced; tests for happy-path send/receive, timeout, idle reap, max-concurrent cap, cross-agent isolation.
- [ ] **4 pty session tools shipped** — `shell_session_start`, `_send`, `_close`, `_list`; registered in `_TOOL_CLASSES` and Studio; per-call denylist on `_send`.
- [ ] **HAT pass complete** — operator-driven walkthrough of all new constraint types; agent recovers gracefully; any error-string-clarity issues fixed inline.
- [ ] **Subprocess env allowlist invariant verified by test** — one test asserts `env.keys() == {PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ}` for all 3 execution call sites.
- [ ] **Integration verified** — full unit suite green (modulo pre-existing CSS-token red); browser suite green; AIAT live smoke green; F4 regression sweeps return zero unexpected matches.

### Adaptation Criteria

**Divert if**:
- Cross-Config dispatch in `BuiltinToolProvider` proves more invasive than the architect estimated (~30 LoC). Fall back to per-tool registry pattern (`ExecutionTools._fs_config = ...` set at provider time) — uglier but localized; document as Decision-revision.
- Unix `pty` stdlib proves insufficient for clean lifecycle management (e.g., zombie processes after `close`). Fall back to `subprocess.Popen` + manual stdin/stdout pipes WITHOUT pty (loses interactive-REPL coloring/curses but keeps multi-command sessions). Document; agent UX is preserved at the cost of some interactive niceties.
- Per-call denylist enforcement on `shell_session_send` (Decision 11) breaks legitimate inputs in HAT (e.g., agent typing `echo "do not sudo"`). Refine the substring shape (perhaps require denylist tokens to NOT be inside quotes); if the refinement is more than ~30 LoC, escalate to Decision-revision.
- Idle reaper task interferes with FastAPI lifecycle (e.g., reaper holds references preventing graceful shutdown). Switch to lazy-on-call reaping; document.

**Acceptable variations**:
- Whether `cross_configs` is passed as a dict or a typed `ResolvedPolicy` dataclass — readability trade-off; default to dict unless the kwarg surface gets unwieldy.
- Whether the reaper runs every 30s or every 60s — empirical tuning at L5 time.
- Whether `PtySession` is a `Protocol` or an ABC — F2 used ABC for `LLMProvider`; default to ABC for consistency unless `Protocol` clearly fits better.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [ ] `01a-constraint-error-extraction` — Move `ConstraintError` from `the_one/tools/filesystem.py` to `the_one/tools/base.py` (next to `Tool` ABC; the two-clause `try/except` envelope IS the tool authorship contract). Update `filesystem.py` to import. **Add a re-export alias** in `the_one/tools/filesystem.py` (e.g., `from the_one.tools.base import ConstraintError`) so any test code that imports `from the_one.tools.filesystem import ConstraintError` continues to work without migration. F3 test suite passes unchanged. ~30 LoC. Single-concern, mechanical.

- [ ] `01b-cross-config-dispatch-and-agent-name-plumbing` — Widen `ToolProvider.get_tools` signature to take `agent_name: str | None = None`. Thread `agent_name` from `AgentFactory.create()` (`the_one/agent/factory.py:~117`) into the provider call. Extend `BuiltinToolProvider.get_tools` to (a) resolve all distinct Config classes referenced by `_TOOL_CLASSES` once, (b) build `cross_configs: dict[type[BaseModel], BaseModel]`, (c) pass `(config, cross_configs, agent_name)` into `Tool.__init__`. Widen `Tool.__init__` signature to `(config, cross_configs=None, agent_name=None)`. Add `Requires: tuple[type[BaseModel], ...] = ()` class-level default on `Tool` ABC. Set `model_config = ConfigDict(frozen=True)` on `FilesystemConfig` (retroactive — F3 didn't set it). Tests: F3 suite passes unchanged (all existing tools have empty `Requires`); new tests for cross-Config dispatch (a fixture tool declaring `Requires = (FilesystemConfig,)` receives the resolved `FilesystemConfig` from the provider); test for `agent_name` threading; test for frozen-config immutability. Estimated ~80-120 LoC + tests.

- [ ] `02-execution-config-and-helpers` — Define `ExecutionConfig` Pydantic model in `the_one/tools/execution.py` (NEW file) with the 5 annotated fields per Decision 1, 2, 3, 5, plus `model_validator(mode="after")` cross-field invariant `default ≤ max`, plus `model_config = ConfigDict(frozen=True)`. Define `DEFAULT_COMMAND_DENYLIST` constant. Define `_command_check(command, cfg) -> None`, `_cwd_check(cwd, fs_cfg) -> Path`, `_truncate_output(stdout, stderr, returncode, cfg) -> tuple[str, bool]` module-level helpers (note: returns `(text, was_truncated)` tuple per Decision 2 sub-bullet). Define `_ENV_ALLOWLIST` and `_build_subprocess_env()` helper. Tests in `tests/test_execution_config.py` and `tests/test_execution_helpers.py` cover defaults, resolver-level narrowing for each marker, the `default ≤ max` invariant, denylist substring matching with the trailing-space convention (including the `"sudo "` vs `"sudoku"` case), cwd directory-existence check, tail-preserving truncation with the marker line + the bool flag, and `_build_subprocess_env` returning exactly the allowlisted keys. No tool changes yet.

- [ ] `03-migrate-shell-tool` — `ShellTool` declares `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`. Rewrite `execute(command, cwd?, timeout?)` to: (1) `_command_check(command, exec_cfg)`; (2) `canonical_cwd = _cwd_check(cwd or Path.home(), fs_cfg)` (default cwd is HOME if agent omits); (3) clip `timeout` to `[1, exec_cfg.timeout_seconds_max]`, defaulting to `exec_cfg.timeout_seconds_default`; (4) `run_shell(command, timeout=clipped_timeout, env=HARDCODED_ENV_ALLOWLIST, cwd=canonical_cwd)`; (5) `return _truncate_output(stdout, stderr, returncode, exec_cfg)`. Two-clause try/except matching F3 pattern. Update `tests/test_execution_tools.py::TestShellTool` to construct with `ExecutionConfig + FilesystemConfig`. New constraint tests: timeout-cap-clipped, output-truncated-at-cap, denylisted-command-refused, cwd-out-of-scope-refused, env-allowlist-invariant-via-`env`-command.

- [ ] `04-migrate-python-exec-tool` — Same shape as L3 with: (a) default timeout 90s applied per-tool (override mechanism: `python_exec` declares its own `Config` subclass `PythonExecConfig(ExecutionConfig)` with an overridden default — OR keeps the shared default and the description encourages explicit `timeout`. Leg-design call.); (b) description tweak per Decision 9. Same constraint tests. Subprocess env allowlist verified.

- [ ] `05a-pty-session-protocol-and-unix-implementation` — Add `the_one/platform/pty.py`: `PtySession` ABC (`start()`, `send(input, timeout) -> bytes`, `close()`, `is_alive: bool`, `last_activity: float`); Unix `pty`-based concrete implementation using **fork-then-execv** for env-allowlist enforcement (per Decision 10): fork; child clears `os.environ`, sets to `_build_subprocess_env()` result, then `os.execvp(shell, [shell])`. Use `select`/`asyncio` for non-blocking reads. Resolve the protocol-shape and readiness-signal OQs (recommend: `start()` blocks until shell prompt is detected via a short read with timeout). Tests cover: send/receive round-trip, timeout on `send`, env allowlist invariant (run `env` in the session and parse output). On `os.name == "nt"`, `pty.py` raises `NotImplementedError("Windows ConPTY support deferred to a future mission")` at import. ~150 LoC + tests.

- [ ] `05b-session-registry-reaper-and-lifespan` — Add `the_one/tools/_session_registry.py`: module-level `_sessions: dict[tuple[str, str], PtySession]` (keyed on `(agent_name, session_id)`) + thread-safe access. Add `_reaper_task` as a single asyncio task spawned lazily on first session registration. Reaper wakes every 30s; for each session, if `time.monotonic() - session.last_activity > cfg.pty_session_idle_ttl_seconds`, call `close()` and remove from registry. **Register reaper with FastAPI lifespan** (`the_one/interfaces/web/app.py` lifespan context): on shutdown, cancel the reaper task and await; reaper catches `CancelledError`, drains its registry by closing all sessions, exits. Add registry helper functions: `register(agent_name, session)`, `get(agent_name, session_id)`, `close(agent_name, session_id)`, `list_for_agent(agent_name)`, `count_for_agent(agent_name)`. Resolve the reaper-lifecycle OQ. Tests cover: idle reap fires after TTL, max-concurrent cap returns ConstraintError, cross-agent isolation (agent A's session_id raises ownership error when accessed via agent B), clean lifespan-shutdown (start session, send shutdown signal, assert `close()` was called). ~200 LoC + tests.

- [ ] `06-pty-session-tools` — Four Tool classes: `ShellSessionStartTool`, `ShellSessionSendTool`, `ShellSessionCloseTool`, `ShellSessionListTool` (all four ship per Decision 4). Each declares `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`. `ShellSessionStartTool.execute(cwd?)` resolves cwd via `_cwd_check` (default `Path.home()`), checks `_session_registry.count_for_agent(self._agent_name) < cfg.max_concurrent_sessions`, instantiates a `PtySession`, registers in `_session_registry` keyed on `(agent_name, session_id)`, returns `session_id` string. `ShellSessionSendTool.execute(session_id, input, timeout_seconds?)` looks up via `_session_registry.get(self._agent_name, session_id)` (returns `None` for cross-agent or unknown — formats as `[error] [constraint] session 'pty-xxx' not owned by this agent OR does not exist`), runs `_command_check(input, exec_cfg)` (per-call denylist per Decision 11), clips timeout to `[1, exec_cfg.timeout_seconds_max]` defaulting to `exec_cfg.timeout_seconds_default`, sends to pty, captures output with cap via `_truncate_output`. `ShellSessionCloseTool.execute(session_id)` calls `_session_registry.close(self._agent_name, session_id)`. `ShellSessionListTool.execute()` returns newline-joined output of `_session_registry.list_for_agent(self._agent_name)`. Add 4 entries to `_TOOL_CLASSES` and Studio's `TOOL_CATEGORIES` (under a new `Sessions` grouping; leg-design call). Update `tests/test_builtins.py` count assertions (post-L4 is 13 + 0 net, post-L6 is 13 + 4 = 17). Tests cover the full surface plus error paths.

- [ ] `hat-execution-walkthrough` *(interactive; non-autonomous)* — Operator drives the agent through every new constraint type via the API:
  1. **Timeout cap exceeded**: agent runs `sleep 200` with `timeout=200` → constraint clips to 120s; agent reads error, recovers.
  2. **Output truncated**: agent runs a command producing 500KB output → tool returns last 256KB with truncation marker; agent reads truncation hint, asks user OR uses `| tail -100` redirection.
  3. **Denylisted command**: agent runs `sudo whoami` → denylist trips; agent reports cannot run privileged commands.
  4. **cwd out of scope**: agent passes `cwd="/etc"` → constraint refuses; agent retries with in-scope path.
  5. **Env allowlist invariant**: agent runs `env` and checks output → only the 8 allowlisted vars present, NO `THE_ONE_*` or other secrets leaked.
  6. **PTY session start/send/close**: happy path; agent starts session, runs `pwd`, runs `ls`, closes.
  7. **PTY session idle reap**: HAT runs against an agent configured with `pty_session_idle_ttl_seconds=30` (override via the agent config; the default 5-min TTL would make HAT take 30+ minutes). Agent starts session, waits 35s, tries to `_send` — gets reap error; agent restarts.
  8. **PTY session max concurrent**: agent starts 5 sessions, tries 6th — gets cap error; closes one and retries.
  9. **PTY session cross-agent isolation**: operator creates two agents (e.g., Qwen and Haiku), starts a session on Qwen, attempts to `_send` from Haiku with Qwen's session_id — gets ownership error.
  10. **PTY session per-call denylist**: agent starts session, types `sudo whoami` — denylist trips at `_send`.

  Flight Director walks operator through each step, records agent's response, fixes error strings inline (spawning Developer agent for code changes if needed). API approach (per F3 L7 lessons) — drive via `POST /api/chat` with fresh sessions per scenario.

- [ ] `08-integration-verification` — Full default unit suite (target: post-L6 baseline + ~80-100 net new tests; modulo pre-existing CSS-token red); browser suite green; AIAT live smoke green. F4 regression sweeps:
  ```bash
  rg -n 'class ConstraintError' the_one/                    # 1 (in base.py)
  rg -n 'os\.environ\.copy\(\)' the_one/tools/                # 0 (no inherited-env copies)
  rg -n 'env=None' the_one/tools/                             # 0 (every subprocess call passes the allowlist)
  rg -n '^class \w+Tool' the_one/tools/execution.py           # 2 (Shell, PythonExec; if shell.py merges into execution.py)
  rg -n '^class \w+Tool' the_one/tools/sessions.py            # 3 (Start, Send, Close; +1 if List ships)
  rg -n 'NarrowSuperset' the_one/tools/                       # 2+ (FilesystemConfig path_denylist + ExecutionConfig command_denylist)
  ```
  Documentation: update `agents.md` to reflect 17 tools + the 5 constraint types + the env allowlist invariant + the trip-wire-not-fence threat model framing + the PTY session lifecycle. Update `CLAUDE.md` Tool Configuration Layer section with `ExecutionConfig` shape + cross-Config dispatch. Mission Open Questions for F4-assigned items marked resolved. Append L8 final entry to flight log.

---

## Post-Flight

### Completion Checklist

- [ ] All legs landed (L1-L8; L7 is the HAT)
- [ ] Pre-flight maintenance pass landed (container bind-mount)
- [ ] `ConstraintError` lives in `the_one/tools/base.py`; imported (not defined) by `filesystem.py` and execution-tool modules
- [ ] `BuiltinToolProvider.get_tools` builds `cross_configs` and passes to `Tool.__init__`
- [ ] `ExecutionConfig` shipped with 5 annotated fields + `model_validator` cross-field invariant
- [ ] `ShellTool` and `PythonExecTool` migrated; constraint tests cover all 5 constraint types per tool
- [ ] PTY infrastructure (`the_one/platform/pty.py`, `_session_registry`, idle reaper) in place
- [ ] 4 PTY session tools registered and tested (start, send, close, list)
- [ ] Subprocess env allowlist invariant verified by test at all 3 execution call sites
- [ ] HAT pass complete; small-model agency artifacts captured as mission Known Issues if any surface
- [ ] Default unit suite green (modulo pre-existing CSS-token red)
- [ ] Browser suite green
- [ ] AIAT live smoke green
- [ ] No regressions in F1-F3 surfaces
- [ ] CLAUDE.md and agents.md refreshed with F4 changes
- [ ] Code committed; flight log updated; flight status set to `landed`

### Verification

**Static (grep / read):**

```bash
# ConstraintError lives in shared module
rg -n 'class ConstraintError' the_one/                       # 1 match (in base.py)
rg -n 'from the_one.tools.base import.*ConstraintError' the_one/tools/  # 2+ (filesystem + execution)

# All 3 execution call sites pass the hardcoded env allowlist
rg -n 'run_shell\(.*env=' the_one/tools/                     # 1+ (passes ENV_ALLOWLIST)
rg -n 'run_python\(.*env=' the_one/tools/                    # 1+

# ExecutionConfig is the Config for execution tools
rg -n 'Config = ExecutionConfig' the_one/tools/              # 5 (Shell, PythonExec, SessionStart, SessionSend, SessionClose)

# Cross-Config dispatch
rg -n 'Requires\s*=' the_one/tools/                          # 6 matches (Shell, PythonExec + 4 session tools all declare FilesystemConfig)
rg -n 'cross_configs' the_one/tools/builtins.py              # 1+ matches in get_tools

# Windows pty deferred
rg -n 'ConPTY|os\.name\s*==\s*"nt"' the_one/platform/pty.py  # 1+ (NotImplementedError on Windows)
```

**Dynamic (test suite):**

```bash
make rebuild
make test-unit
make test-browser
docker exec the-one pytest -m live tests/test_aiat.py

# Env allowlist invariant smoke
docker exec the-one python -c "
import asyncio
from the_one.tools.shell import ShellTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    out = await ShellTool(
        ExecutionConfig(),
        cross_configs={FilesystemConfig: FilesystemConfig()},
    ).execute(command='env | sort')
    keys = {line.split('=', 1)[0] for line in out.splitlines() if '=' in line}
    expected = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM', 'TZ'}
    assert keys == expected, f'env leak: extra={keys-expected}, missing={expected-keys}'
    print('OK')
asyncio.run(main())
"

# PTY session round-trip smoke
docker exec the-one python -c "
import asyncio
from the_one.tools.sessions import ShellSessionStartTool, ShellSessionSendTool, ShellSessionCloseTool
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
async def main():
    cfgs = {FilesystemConfig: FilesystemConfig()}
    sid = await ShellSessionStartTool(ExecutionConfig(), cross_configs=cfgs).execute(cwd='/tmp')
    out = await ShellSessionSendTool(ExecutionConfig(), cross_configs=cfgs).execute(
        session_id=sid, input='echo hello'
    )
    assert 'hello' in out
    await ShellSessionCloseTool(ExecutionConfig(), cross_configs=cfgs).execute(session_id=sid)
    print('OK')
asyncio.run(main())
"
```

**Manual (HAT):** L7 walkthrough — operator drives the agent through 10 constraint scenarios (timeout, output cap, denylist, cwd scoping, env allowlist, PTY happy/idle-reap/max-concurrent/cross-agent-isolation/per-call-denylist) and confirms graceful recovery on each.

---

## Architect Q&A — design refinements captured

**Round 1 (deep review)** surfaced 1 high-severity issue + 8 medium + several low items. Major refinements applied:

- D4: `agent_name` plumbing is non-trivial scaffolding — added to L1b spec; `ToolProvider.get_tools` signature widened; session_id format pinned (`f"pty-{uuid4().hex}"`); `shell_session_list` committed (4 tools).
- D5: reaper task registered with FastAPI lifespan for clean shutdown; `ui_hint` dropdowns added to TTL + max-concurrent fields.
- D7: provider resolves all distinct Configs unconditionally (not enabled-set tracking); `Tool` ABC gains `Requires: tuple[type[BaseModel], ...] = ()` default; `frozen=True` on `FilesystemConfig` + `ExecutionConfig`; F5 `download_file` forward-reference noted.
- D8: L1 split into L1a (ConstraintError → `base.py`; 30 LoC) + L1b (cross-Config + agent_name; 80-120 LoC). Container fix relabeled "STRONGLY RECOMMENDED" not "hard prerequisite". `ConstraintError` lives in `base.py` (NOT new `_constraint.py`). L1a includes a re-export alias from `filesystem.py` for backward-compatible test imports.
- D2: tail-preserving applies uniformly to all 3 surfaces; `_truncate_output` returns `tuple[str, bool]`.
- D10: pty fork-then-execv mechanism documented for env-allowlist enforcement.
- D11: false-positive surface accepted intentionally; rejected refinements (quote-aware, first-token-only) documented.
- L5 split into L5a (protocol + Unix impl; ~150 LoC) + L5b (registry + reaper + lifespan; ~200 LoC). Open Questions reduced to 2 leg-design-time (both at L5a: protocol shape, readiness signal).
- HAT step 7: idle-reap test runs against an agent with TTL override of 30s (otherwise HAT takes 30+ min).

**Round 2 (validation)** surfaced only stale text inconsistencies — all mechanical. Cleaned up: 6× `_constraint.py` → `base.py`; 5× tool-count "3-4" / "15-16" → committed counts; removed contradicting "list optional" language; corrected `Requires` regression-sweep count (5 → 6); added L1a re-export alias note.

**Verdict**: structurally sound, ready to land in `ready` and proceed to L1a leg design.
