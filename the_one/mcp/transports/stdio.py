"""Stdio transport for MCPClient.

Implements the wire-shape glue between F1's MCPSource model and the
official mcp SDK's stdio_client. The transport itself is a single
async-context-manager (`connect_stdio`) that yields a fully-entered
`ClientSession`; MCPClient only sees the session, never the
(read, write) stream tuple.

Subprocess environ is assembled at spawn time from two layers:
  1. Host allowlist (the canonical 8-key set from
     `the_one.platform.env._ENV_ALLOWLIST`, materialized via
     `_build_subprocess_env()`).
  2. Operator-configured kv table — `config.env` (plaintext at rest)
     flat-merged with `secrets` (Fernet-encrypted at rest); secrets
     win on collision (over BOTH allowlist and config.env).

Allowlist sits at the floor (overridable by both operator layers).
The SDK applies its own `get_default_environment()` UNDER our env as
well — so the effective subprocess environ has 3 layers: SDK floor,
our allowlist, our operator kv. We never see the SDK floor because
we don't call `get_default_environment()` ourselves; the SDK applies
it inside `stdio_client`.

`_build_subprocess_env` is private by underscore convention but is the
canonical helper for filtering the host environ by the allowlist —
promoted-by-use-not-by-rename. F2 imports it directly.

NOTE: this helper does NOT consume `MCPSource.merged_config()` —
`merged_config()` flat-merges secrets at the config TOP level, which
would inject command/args/cwd-shaped keys into the env if we used it.
The kv table for stdio sources lives at `config["env"]`, never at
`config` top-level. See flight 02 design decision §11.

See flight 02 design decision §11 for the env-var-assembly contract,
and L4's `transports/streamable_http.py` for the structurally
parallel headers-assembly pattern.

**F3 sandbox wrap (M14 F1 L3)**: every stdio MCP source spawns sandboxed
via ``get_sandbox_backend().prepare_spawn``. The factory (``get_sandbox_backend``
from ``the_one.platform.sandbox.factory``) centralizes backend selection:
``BubblewrapSandbox`` on Linux with bwrap present and bypass off;
``PassthroughSandbox`` otherwise (non-Linux, bwrap-missing, or
double-flag test bypass). The wrap reads ``MCPSource.config["sandbox"]``
(optional dict; defaults to strict-floor ``SandboxProfile()``) via
``SandboxProfile.from_dict`` and, when the bubblewrap backend is selected,
applies bwrap's ``--clearenv`` + per-key ``--setenv`` env-allowlist
enforcement, ``--ro-bind / /`` + ``--bind PATH PATH`` filesystem scope,
``--unshare-net`` network policy (when ``network_allowed=False``), and
``--die-with-parent`` process supervision. Off-Linux or bwrap-missing hosts
now degrade silently to the passthrough backend rather than raising at
construction time (the mission's core fix for the MCP path). The
double-flag bypass (``THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1``)
is handled inside the factory; stdio no longer owns a copy of that predicate.
Per F3 §6's boundary, bwrap-side post-setup errors (``writable_paths``
nonexistent, ``EPERM`` on ``unshare``, generic exit-code != 0) are
translated to ``SandboxError`` via the SDK's ``errlog=`` parameter — see
leg ``02-bwrap-error-translation`` (mission 07 flight 04). The
bwrap-prefix discriminator (``_BWRAP_OWN_PREFIX_RE``) gates patterns
#2/#3 so inner-process failures (post-bwrap-success) continue to
surface as F2's ``MCPConnectionError`` — F3 §6's directionality contract.
"""

from __future__ import annotations

import re
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from the_one.db.models import MCPSource
from the_one.mcp.errors import MCPConnectionError
from the_one.platform.env import _build_subprocess_env
from the_one.platform.sandbox import (
    BubblewrapSandbox,
    SandboxError,
    SandboxProfile,
    ToolSandbox,
    get_sandbox_backend,
)

__all__ = ["build_stdio_environ", "connect_stdio"]


# ---------------------------------------------------------------------------
# Bwrap stderr → SandboxError translation (F3 §6)
# ---------------------------------------------------------------------------
#
# Probe results captured 2026-05-07 against bwrap inside the dev container
# (mcr.microsoft.com/playwright/python:v1.58.0-jammy + bwrap apt install,
# dev container running bwrap 0.11.0). EPERM probe via privilege-stripped
# `docker run --rm mcr.microsoft.com/playwright/python:v1.58.0-jammy ...
# su nobody ...` (bwrap 0.9.0 from Ubuntu noble). See flight log L2 Leg
# Progress entry for full output.
#
# Pattern 1 — writable_paths nonexistent (no prefix gate; `Can't find
# source path` is unambiguously a bwrap message):
#   probe stderr (verbatim):
#       bwrap: Can't find source path /this/path/does/not/exist: No such file or directory
#   regex: r"Can't find source path '?(?P<path>[^'\n:]+?)'?(?:\s*:\s*[^\n]*)?$"
#   exit-code: !=0 (typically 1)
#
# Pattern 2 — generic bwrap failure (prefix-gated; matches any "bwrap:"
# line that doesn't match #1 or #3):
#   probe stderr (verbatim, malformed-flag probe):
#       bwrap: Unknown option --invalid-flag-xyz
#   regex: (no match → fallback). The bwrap-prefix discriminator
#       (_BWRAP_OWN_PREFIX_RE) gates this path so inner-process failures
#       are NOT mistranslated as SandboxError.
#
# Pattern 3 — EPERM / namespace creation refused (prefix-gated):
#   probe stderr (verbatim, kernel without unprivileged_userns_clone):
#       bwrap: No permissions to create new namespace, likely because the
#       kernel does not allow non-privileged user namespaces. See
#       <https://deb.li/bubblewrap> or <file:///usr/share/doc/bubblewrap/README.Debian.gz>.
#   The probe environment (Ubuntu noble bwrap 0.9.0 under su nobody)
#   emits the "No permissions to create new namespace" form, NOT the
#   generic "Operation not permitted" string. The regex below accepts
#   either bwrap variant: the "No permissions to create new namespace"
#   wording from kernel-disabled-userns environments AND the Operation-
#   not-permitted ↔ unshare/user ns ordering for kernels that emit the
#   raw errno-strerror form. Both are catalog #3 cases.
#   regex: r"(No permissions to create new namespace|"
#          r"(?:unshare|user ns|create user namespace).*?(?:Operation not permitted|EPERM)|"
#          r"(?:Operation not permitted|EPERM).*?(?:unshare|user ns|create user namespace))"
#   exit-code: !=0 (typically 1)


# Compiled at module scope (CPython ~free since they're tiny).
_BWRAP_NONEXISTENT_PATH_RE = re.compile(
    r"Can't find source path '?(?P<path>[^'\n:]+?)'?(?:\s*:\s*[^\n]*)?$",
    re.MULTILINE,
)
# bwrap's error-line convention is `<context>: <errno-strerror>`. The
# context comes FIRST (e.g. `bwrap: setting up uid map: Operation not
# permitted` or `bwrap: unshare user ns: Operation not permitted`).
# This pattern accepts either order to be forgiving of bwrap minor-
# version drift, AND additionally matches the "No permissions to create
# new namespace" form that bwrap 0.9.0+ emits on kernels with
# unprivileged_userns_clone disabled (probe-confirmed 2026-05-07).
_BWRAP_EPERM_UNSHARE_RE = re.compile(
    r"(?:No permissions to create new namespace)"
    r"|(?:(?:unshare|user ns|create user namespace).*?(?:Operation not permitted|EPERM))"
    r"|(?:(?:Operation not permitted|EPERM).*?(?:unshare|user ns|create user namespace))",
    re.IGNORECASE | re.DOTALL,
)
# Discriminator: bwrap's own error lines start with "bwrap:". A captured
# stderr that does NOT start with "bwrap:" indicates the bwrap setup
# succeeded and the inner child wrote those bytes — F2's
# MCPConnectionError must handle that case, not us. This is the
# load-bearing test that prevents inner-process failures from being
# mistranslated as SandboxError (F3 §6 directionality contract;
# Test #6d locks it).
_BWRAP_OWN_PREFIX_RE = re.compile(r"^\s*bwrap:", re.MULTILINE)


def _translate_bwrap_stderr(stderr_text: str) -> SandboxError | None:
    """Pattern-match captured bwrap stderr → SandboxError per F3 §6.

    Returns ``None`` if the capture indicates a non-bwrap failure
    (e.g., the child target spawned successfully under bwrap and itself
    failed mid-handshake — no translation needed; F2's
    ``MCPConnectionError`` handles it). The bwrap-prefix discriminator
    is the load-bearing check; if the captured stderr does NOT contain a
    ``bwrap:`` line, this helper returns ``None`` for patterns #2/#3.

    Pattern #1 (``Can't find source path``) is exempt from the prefix
    gate because that message is unambiguously a bwrap signature and is
    the most operator-actionable case.

    Returns an :class:`SandboxError` for any of the three §6 catalog
    signatures.
    """
    # Path-#1 check is exempt from the prefix gate.
    m = _BWRAP_NONEXISTENT_PATH_RE.search(stderr_text)
    if m:
        path = m.group("path").strip()
        return SandboxError(
            f"MCP sandbox setup failed: writable_paths entry "
            f"{path!r} does not exist. "
            f"Create the directory or remove from writable_paths."
        )
    # Path-#3 (EPERM) and path-#2 (generic) require the bwrap-prefix
    # gate to discriminate from inner-process failures.
    if not _BWRAP_OWN_PREFIX_RE.search(stderr_text):
        return None
    if _BWRAP_EPERM_UNSHARE_RE.search(stderr_text):
        return SandboxError(
            "MCP sandbox setup failed: namespace creation refused "
            "(EPERM on unshare). The container likely lacks the "
            "privilege grants required by §10."
        )
    # bwrap printed something to stderr that we don't recognise → catalog #2.
    snippet = stderr_text.strip()[:500]
    return SandboxError(
        "MCP sandbox setup failed: bubblewrap exited non-zero. "
        "Check that the dev/CI environment has cap_add: SYS_ADMIN "
        "AND security_opt: seccomp:unconfined per F3 design decision §10. "
        f"bwrap stderr: {snippet!r}"
    )


# ---------------------------------------------------------------------------
# F9 L2 D3 — operator-actionable spawn-error translation
# ---------------------------------------------------------------------------
#
# Translates two common spawn-failure modes into messages the operator can
# act on directly. Runs AFTER the F3 §6 bwrap-stderr discriminator so a
# bwrap-side failure (sandbox profile misconfiguration, EPERM, missing
# inner command at the bwrap layer) is NOT mistranslated as a host-native
# "missing on PATH" message — those continue to surface as SandboxError
# per the F3 §6 directionality contract. The two D3 cases:
#
#   1. FileNotFoundError on subprocess spawn — the command isn't on PATH.
#      Translation: names the missing executable, gives a host-native
#      per-runtime install hint (node/npx/uv/uvx/python/python3 known;
#      generic fallback for other commands), and preserves the
#      runtime-fetch shape tip (uvx/npx).
#
#   2. ModuleNotFoundError surfaced via inner-process stderr (Python's
#      `python -m foo` when foo isn't installed). Inner-process stderr is
#      captured by the SDK's `errlog=` parameter alongside any bwrap
#      output; the bwrap-prefix gate ensures we only act on inner-process
#      stderr. Translation: "Use command=uvx args=[<pkg>] for runtime
#      install, or pre-install via pip."

# Host-native install hints for known MCP runtimes.
# Keyed by executable name; used in Pattern-1 FileNotFoundError messages.
_RUNTIME_INSTALL_HINTS: dict[str, str] = {
    "node": (
        "Install Node.js (e.g. from https://nodejs.org or your system package "
        "manager) so `node` and `npx` are on PATH."
    ),
    "npx": (
        "Install Node.js (e.g. from https://nodejs.org or your system package "
        "manager) so `npx` is on PATH."
    ),
    "uv": ("Install uv (https://docs.astral.sh/uv/) so `uv` and `uvx` are on PATH."),
    "uvx": ("Install uv (https://docs.astral.sh/uv/) so `uvx` is on PATH."),
    "python": (
        "Ensure a Python 3.11+ interpreter is on this app's PATH "
        "(e.g. install via your system package manager or https://python.org)."
    ),
    "python3": (
        "Ensure a Python 3.11+ interpreter is on this app's PATH "
        "(e.g. install via your system package manager or https://python.org)."
    ),
}

# Captures the missing command name from FileNotFoundError's args, which
# typically look like ``[Errno 2] No such file or directory: 'foo'`` or a
# bare command string in `.filename`. Both forms are covered downstream.
_MODULE_NOT_FOUND_RE = re.compile(
    r"(?:^|\n)(?:[^\s:]+:\s+)?(?:ModuleNotFoundError:\s+)?"
    r"No module named ['\"]?(?P<module>[^'\"\s\n]+)['\"]?",
    re.MULTILINE,
)

# F9 L2 vibing: Python launcher's "can't open file" error. Surfaces when the
# operator runs `python <script>` and the script path is wrong / nonexistent /
# quote-mangled. CPython 3.10+ prints
# ``python: can't open file '<path>': [Errno 2] No such file or directory``;
# pre-3.10 prints ``python: can't open file '<path>': [Errno 2] ...``. We
# capture the path between matching quote characters — the outer pair is the
# delimiter and the inner content may itself contain the OTHER quote type
# (the operator-mangled `args=["\"-m\""]` case literally surfaces as
# ``'"-m"'`` in stderr, so we must allow `"` inside `'…'` and vice versa).
_PYTHON_CANT_OPEN_FILE_RE = re.compile(
    r"can't open file (?:'(?P<sq_path>[^'\n]+)'|\"(?P<dq_path>[^\"\n]+)\")",
    re.MULTILINE,
)


def _translate_inner_spawn_error(
    *,
    exc: BaseException | None,
    stderr_text: str,
    command: str,
) -> MCPConnectionError | None:
    """Pattern-match spawn-time failures → MCPConnectionError (D3).

    Critical interaction with F3's bwrap-stderr discriminator: this helper
    MUST run only AFTER ``_translate_bwrap_stderr`` has already been
    consulted (and returned None) AND the captured stderr does NOT carry a
    ``bwrap:`` prefix line. Otherwise a sandbox-side failure (bwrap can't
    find the inner command, e.g., misconfigured sandbox profile) would be
    mistranslated as "missing in container" when the actual root cause is
    the sandbox profile.

    Returns ``None`` if no D3 pattern matches; the caller falls back to
    the existing ``MCPConnectionError`` translation in
    ``MCPClient.connect``.

    Args:
        exc: The exception that surfaced (e.g., FileNotFoundError) — None
            if translation is being driven solely from captured stderr.
        stderr_text: Captured inner-process stderr (post-bwrap-discriminator
            gate; safe to scan for ModuleNotFoundError without confusing
            bwrap-side failures).
        command: The command the operator configured (e.g., ``uvx``,
            ``python``, ``npx``) — used in the operator-actionable
            message. Caller passes ``MCPSource.config["command"]``.
    """
    # Pattern 1: command not found on subprocess spawn.
    if isinstance(exc, FileNotFoundError):
        # FileNotFoundError.filename is typically the missing executable;
        # fall back to the configured command if the OS error doesn't carry
        # one (rare on Linux, possible on Windows variants).
        missing = getattr(exc, "filename", None) or command
        hint = _RUNTIME_INSTALL_HINTS.get(
            missing,
            f"Install `{missing}` and ensure it is on this app's PATH.",
        )
        return MCPConnectionError(
            f"The command `{missing}` was not found on PATH. "
            f"{hint} "
            f"For one-off Python/JS MCPs, prefer the runtime-fetch "
            f"shape: command=uvx args=[<pkg>] (Python), command=npx "
            f"args=[-y, <pkg>] (JS)."
        )

    # Pattern 2: ModuleNotFoundError in the inner process's stderr (e.g.,
    # `python -m foo` when foo isn't installed). The inner-process stderr
    # flows through the SDK's errlog when bwrap is in front of the inner
    # process; on the bypass path, anyio.open_process pipes stderr to
    # errlog directly. The bwrap-discriminator gate ensures the captured
    # text we're scanning is NOT a bwrap-side message.
    if stderr_text:
        m = _MODULE_NOT_FOUND_RE.search(stderr_text)
        if m:
            module = m.group("module").strip()
            return MCPConnectionError(
                f"The Python module {module!r} is not installed. "
                f"Use command=uvx args=[{module}] for runtime install, or "
                f"pre-install via `pip install {module}`. (Inner process "
                f"reported ModuleNotFoundError before MCP handshake "
                f"completed.)"
            )

        # Pattern 3 (F9 L2 vibing): Python launcher couldn't open the script
        # path it was given. Most common operator cause is args carrying
        # literal quote characters (e.g., ``["\"-m\""]`` instead of
        # ``["-m"]``) so Python interprets the quoted token as a script
        # filename. Same bwrap-discriminator gate applies: the caller has
        # already filtered out bwrap-prefixed stderr per F3 §6, so any
        # ``can't open file`` line we see here is from the inner Python
        # process, not from bwrap's own argv-parsing.
        m = _PYTHON_CANT_OPEN_FILE_RE.search(stderr_text)
        if m:
            # Either the single-quoted or double-quoted alternative matched;
            # the other group is None. Pick whichever is non-None.
            path = m.group("sq_path") or m.group("dq_path")
            return MCPConnectionError(
                f"Python could not open the script {path!r}. Common causes: "
                f"the args field has literal quote characters around values "
                f'(use `-m` not `"-m"`); the script path is wrong; or you '
                f"meant to use command=uvx args=[<package>] for a "
                f"runtime-fetched MCP."
            )

    return None


def build_stdio_environ(source: MCPSource, allowlist_env: dict[str, str]) -> dict[str, str]:
    """Materialize the spawned-child environ for a stdio MCP source.

    Two-layer flat merge in precedence order:
      1. allowlist_env — the canonical host-environment-filtered allowlist
         (caller passes `_build_subprocess_env()` in production; tests
         inject a known-shape dict for determinism).
      2. operator-configured kv table — config["env"] (plaintext at rest)
         ∪ source.secrets (encrypted at rest), with secrets winning on
         collision (over BOTH allowlist and config.env — so an
         operator-marked-sensitive value beats any plaintext default of
         the same name AND any host-inherited allowlist value).

    Layer 2 is one logical concept (the operator's kv table from the L6
    editor); the at-rest config/secrets split is purely the F1
    encryption-at-rest implementation detail.

    Returns a fresh dict; does not mutate inputs. Pure function — no I/O.

    NOTE: do NOT call source.merged_config() — that produces
    {**config, **secrets} which would inject command/args/cwd as
    env-var-shaped keys. The kv table for stdio sources lives at
    config["env"], not at config top-level.
    """
    config_env: dict[str, str] = source.config.get("env", {}) or {}
    return {**allowlist_env, **config_env, **source.secrets}


def _build_stdio_params(source: MCPSource) -> tuple[StdioServerParameters, ToolSandbox]:
    """Build StdioServerParameters for an MCPSource.

    Obtains the sandbox backend from the factory (``get_sandbox_backend``)
    rather than constructing ``BubblewrapSandbox`` directly. Always builds
    the ``SandboxProfile`` and runs ``backend.prepare_spawn`` — for
    ``PassthroughSandbox`` this produces the unwrapped command (same as the
    old bypass branch); for ``BubblewrapSandbox`` it produces the
    bwrap-wrapped command.

    Backend selection is fully centralized in the factory:
    - Double-flag test bypass → ``PassthroughSandbox``
    - Non-Linux host → ``PassthroughSandbox``
    - bwrap absent on Linux → ``PassthroughSandbox`` (degrades silently,
      no ``SandboxError`` at construction time — the mission's core fix)
    - Linux + bwrap present + bypass off → ``BubblewrapSandbox``

    May raise ``ValueError`` (from ``SandboxProfile.from_dict`` on a
    type-mismatched ``config["sandbox"]`` field — propagates as a
    programmer/validator boundary error per F3 §6). ``SandboxError`` at
    construction time is no longer reachable from this site; the factory
    absorbs bwrap-missing by returning passthrough.

    Returns ``(params, backend)`` — callers derive
    ``sandboxed = isinstance(backend, BubblewrapSandbox)`` to gate the
    bwrap-stderr-capture path.
    """
    command: str = source.config["command"]
    # SDK's StdioServerParameters has args: list[str] with default_factory=list,
    # so args is technically NOT required at the Pydantic layer. We still pass
    # `.get("args", [])` defensively in case F1 validator drift ever lets args
    # go absent — guarantees an explicit empty list reaches the SDK regardless.
    args: list[str] = source.config.get("args", [])
    # F1 validator restricts cwd to str|None; SDK also accepts pathlib.Path
    # but we don't surface that — keeps the contract tight at the API edge.
    cwd: str | None = source.config.get("cwd")
    env = build_stdio_environ(source, _build_subprocess_env())

    # Always build the profile — passthrough ignores it, bubblewrap applies it.
    # (Prior code skipped from_dict on the bypass path; the new code validates
    # always, which is strictly better. A malformed config["sandbox"] now raises
    # ValueError even under bypass — acceptable deliberate behaviour change.)
    profile = SandboxProfile.from_dict(source.config.get("sandbox") or {})
    backend = get_sandbox_backend()
    spec = backend.prepare_spawn(profile, command, args, env, cwd)
    return (
        StdioServerParameters(command=spec.command, args=spec.args, env=spec.env, cwd=spec.cwd),
        backend,
    )


@asynccontextmanager
async def connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]:
    """Open an entered ClientSession over (sandboxed) stdio transport.

    Yields a fully-entered ClientSession (initialize() NOT called — the
    caller — typically MCPClient.connect — runs the handshake). The
    session and transport contexts close in correct LIFO order on exit.

    The subprocess environ is materialized via `build_stdio_environ`
    passing the result of `_build_subprocess_env()` (the canonical host
    allowlist filter). The SDK applies its own
    `get_default_environment()` UNDER our env, providing additional
    defense-in-depth defaults for HOME/LANG/etc.

    The spawn is wrapped by the sandbox backend selected by the factory
    (F3 sandbox layer). ``BubblewrapSandbox`` is used on Linux with bwrap
    present and bypass off; ``PassthroughSandbox`` is used otherwise
    (non-Linux, bwrap-missing, or double-flag test bypass). Sandbox-setup
    failures via bwrap propagate as ``SandboxError`` post-spawn; the factory
    absorbs bwrap-missing silently, so off-Linux / bwrap-missing hosts
    degrade to passthrough without raising at connect time.

    On the sandboxed path (``isinstance(backend, BubblewrapSandbox)``),
    bwrap stderr is captured via the SDK's ``errlog=`` parameter into a
    ``SpooledTemporaryFile``; on transport-CM failure the captured text is
    pattern-matched against the F3 §6 catalog signatures and re-raised as
    the appropriate ``SandboxError``. The passthrough path retains the
    SDK's default ``errlog=sys.stderr`` passthrough.
    """
    params, backend = _build_stdio_params(source)
    # True iff the factory selected the bubblewrap backend — the only backend
    # that wraps the spawn in `bwrap` and writes bwrap stderr to errlog.
    # Uses the concrete class, NOT the ToolSandbox Protocol (which both backends
    # satisfy) — the isinstance check must discriminate between the two.
    sandboxed = isinstance(backend, BubblewrapSandbox)
    # D3: capture the operator-configured command for translation messages
    # (the post-prepare-spawn `params.command` is "bwrap" on the sandboxed
    # path, which would not be operator-actionable in a translated error).
    operator_command: str = source.config.get("command", "")
    if sandboxed:
        # Sandboxed path: capture bwrap stderr for translation.
        #
        # Translation runs in a `finally` (not just an `except`) because
        # MCPClient.connect()'s outer `except Exception:` catches an
        # initialize-time McpError BEFORE the AsyncExitStack is unwound
        # — so by the time `transport_stack.aclose()` calls our
        # generator's __aexit__(None, None, None), no exception is
        # flowing through the yield. We can't rely on the except branch.
        #
        # bwrap writes to stderr ONLY on failure (verified via probe
        # 2026-05-07: success path = empty stderr; any of the three §6
        # failure modes = non-empty bwrap-prefixed stderr). So if the
        # buffer holds content matching `_translate_bwrap_stderr`, we
        # raise even on the "clean exit" path — the upstream caller's
        # connection-close error is downstream of bwrap's failure.
        original_exc: BaseException | None = None
        with tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errbuf:
            try:
                async with stdio_client(params, errlog=errbuf) as (read, write):
                    async with ClientSession(read, write) as session:
                        yield session
            except BaseException as exc:
                original_exc = exc
                raise
            finally:
                # Read whatever bwrap wrote to stderr (success → empty).
                try:
                    errbuf.seek(0)
                    stderr_text = errbuf.read()
                except Exception:
                    stderr_text = ""
                if stderr_text:
                    sandbox_err = _translate_bwrap_stderr(stderr_text)
                    if sandbox_err is not None:
                        if original_exc is not None:
                            raise sandbox_err from original_exc
                        raise sandbox_err
                # F9 L2 D3: after the bwrap-discriminator gate, look for
                # operator-actionable inner-process failures. Only fires
                # when no bwrap-side translation matched AND stderr is
                # non-empty AND lacks the bwrap-prefix (the gate inside
                # _translate_inner_spawn_error mirrors this contract).
                if stderr_text and not _BWRAP_OWN_PREFIX_RE.search(stderr_text):
                    inner_err = _translate_inner_spawn_error(
                        exc=original_exc,
                        stderr_text=stderr_text,
                        command=operator_command,
                    )
                    if inner_err is not None:
                        if original_exc is not None:
                            raise inner_err from original_exc
                        raise inner_err
    else:
        # Passthrough path (non-bwrap backend): SDK's default errlog=sys.stderr.
        # F9 L2 D3: catch FileNotFoundError synchronously here so the
        # passthrough path also benefits from the operator-actionable
        # translation. The SDK pipes inner stderr to sys.stderr on this
        # path so we don't capture it for ModuleNotFoundError translation
        # — that path remains unchanged for the passthrough.
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    yield session
        except FileNotFoundError as exc:
            inner_err = _translate_inner_spawn_error(
                exc=exc,
                stderr_text="",
                command=operator_command,
            )
            if inner_err is not None:
                raise inner_err from exc
            raise


async def _open_stdio_transport_stack(
    source: MCPSource,
) -> tuple[ClientSession, AsyncExitStack]:
    """Open an entered ClientSession over (sandboxed) stdio transport.

    SAME-TASK CONTRACT: caller MUST drive ``stack.aclose()`` from the same task.

    L2's bwrap-stderr translation must fire on EVERY teardown (matching
    the existing ``connect_stdio`` ``finally:`` semantics). bwrap setup
    can fail asynchronously: setup may succeed enough that
    ``stdio_client.__aenter__`` returns, but bwrap then dies before the
    MCP handshake completes — the ``McpError`` surfaces from
    ``session.initialize()`` (run by the caller, OUTSIDE this helper).
    Translation therefore CANNOT live in our ``except BaseException``
    clause alone; it must run when the caller eventually closes the
    returned stack.

    Mechanism: push a translation callback onto the stack BEFORE
    entering ``stdio_client``. AsyncExitStack runs callbacks in LIFO
    order, so on unwind the order is:

        ClientSession.__aexit__
        stdio_client.__aexit__   (flushes bwrap stderr into errbuf)
        translation callback     (reads errbuf, raises SandboxError if matched)
        SpooledTemporaryFile.__exit__  (closes errbuf — but only AFTER
                                        translation has read it)

    The translation callback raises the translated ``SandboxError``
    if the captured stderr matches an F3 §6 catalog pattern, replacing
    any in-flight exception so the caller sees the bwrap diagnostic
    rather than the downstream ``McpError`` / ``Connection closed``
    wrapping.

    The existing ``connect_stdio`` ``@asynccontextmanager`` continues to
    exist for back-compat with its 9 prior async-CM callers in
    ``tests/test_mcp_stdio_sandbox.py``.
    """
    params, backend = _build_stdio_params(source)
    # True iff the factory selected the bubblewrap backend — the only backend
    # that wraps the spawn in `bwrap` and writes bwrap stderr to errlog.
    sandboxed = isinstance(backend, BubblewrapSandbox)
    # F9 L2 D3: capture the operator-configured command for translation
    # messages — `params.command` is "bwrap" on the sandboxed path and
    # would not be operator-actionable in a translated error.
    operator_command: str = source.config.get("command", "")
    stack = AsyncExitStack()
    # cycle-1 M1: init before try so the except-clause guard is safe even
    # if `enter_context(SpooledTemporaryFile(...))` raises before assignment.
    errbuf = None
    try:
        if sandboxed:
            errbuf = stack.enter_context(
                tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", errors="replace")
            )

            # Push translation callback BEFORE entering stdio_client so
            # that LIFO unwind runs translation AFTER stdio_client's
            # __aexit__ flushes stderr and BEFORE SpooledTemporaryFile
            # closes. The closure captures errbuf by reference; the
            # callback reads it, pattern-matches, and raises the
            # translated SandboxError on match.
            #
            # F9 L2 D3: callback also runs the inner-spawn translation
            # AFTER the bwrap-discriminator gate. Bwrap-side translation
            # takes precedence (preserves F3 §6 directionality contract);
            # only when no bwrap match fires AND stderr lacks the bwrap-
            # prefix do we attempt the D3 inner-process patterns.
            errbuf_ref = errbuf

            def _translate_on_unwind() -> None:
                stderr_text = ""
                try:
                    errbuf_ref.seek(0)
                    stderr_text = errbuf_ref.read()
                except Exception:
                    stderr_text = ""
                if not stderr_text:
                    return
                sandbox_err = _translate_bwrap_stderr(stderr_text)
                if sandbox_err is not None:
                    raise sandbox_err
                # Bwrap-discriminator gate: only translate inner-process
                # patterns when stderr is NOT bwrap-prefixed.
                if _BWRAP_OWN_PREFIX_RE.search(stderr_text):
                    return
                inner_err = _translate_inner_spawn_error(
                    exc=None,
                    stderr_text=stderr_text,
                    command=operator_command,
                )
                if inner_err is not None:
                    raise inner_err

            stack.callback(_translate_on_unwind)

            read, write = await stack.enter_async_context(stdio_client(params, errlog=errbuf))
        else:
            read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        return session, stack
    except BaseException as exc:
        # Entry-failure path: stdio_client or ClientSession entry raised
        # before we could return. Drain the stack (which runs the
        # translation callback if it was registered) and let any
        # SandboxError replace the original exception.
        #
        # F9 L2 D3: on the passthrough path, FileNotFoundError surfaces here
        # synchronously (anyio.open_process raises before stack.aclose
        # walks). Translate to MCPConnectionError with an operator-
        # actionable message ahead of MCPClient.connect's catchall
        # translation.
        try:
            await stack.aclose()
        except SandboxError as sandbox_err:
            raise sandbox_err from exc
        except MCPConnectionError as conn_err:
            # D3 callback raised an inner-spawn translation.
            raise conn_err from exc
        if not sandboxed and isinstance(exc, FileNotFoundError):
            inner_err = _translate_inner_spawn_error(
                exc=exc,
                stderr_text="",
                command=operator_command,
            )
            if inner_err is not None:
                raise inner_err from exc
        raise
