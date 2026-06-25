"""PTY session tools (F4 L6).

Wires the four ``shell_session_*`` tools onto the L5a/L5b PTY scaffolding:

* ``shell_session_start`` — spawn a new interactive shell session and return
  a ``pty-{uuid4hex}`` handle.
* ``shell_session_send`` — write to an existing session and return the
  output (per-call denylist re-check).
* ``shell_session_close`` — terminate a session.
* ``shell_session_list`` — list sids owned by the current agent.

Design references:

* **F4 Decision 4** — per-explicit-handle session addressing. Each call to
  ``shell_session_start`` mints a fresh ``pty-{uuid4hex}`` token; the
  registry keys on ``(agent_name, session_id)`` so cross-agent isolation
  falls out of the keying naturally (see L5b ``_session_registry``).
* **F4 Decision 6** — discrete tools (one per action) over a single
  ``shell_session(action=...)`` polymorphic tool. Small-model-friendly
  affordances: each tool has its own ``description`` and parameters.
  F3 set the precedent (``read_file`` / ``write_file`` / ``edit_file``
  discrete, not ``file(action=...)``).
* **F4 Decision 11** — per-call denylist re-check on
  ``shell_session_send``. The session was already created via a
  denylist-checked ``shell_session_start``, but each ``send`` re-applies
  ``_command_check`` against the same ``cfg.command_denylist``. The
  false-positive surface is documented on the tool description (e.g.
  ``echo "do not run sudo"`` trips the ``"sudo "`` token) — accepted
  intentionally to keep the trip-wire uniform across one-shot and
  interactive shell paths.

``agent_name`` plumbing: every session tool requires
``self._agent_name is not None`` — the introspection path
(``BuiltinToolProvider().get_tools()`` zero-arg, used by ``/api/tools``)
constructs tools with ``agent_name=None``, which has no real agent
context to register cross-agent-isolated state under. Calls in that mode
return ``[error] [constraint] session tools require an agent context``.

Three-clause try/except envelope on ``shell_session_send``
(``ConstraintError → asyncio.TimeoutError → Exception``); two-clause on
the other three (no timeout-bearing await inside the envelope, so
``asyncio.TimeoutError`` cannot fire there).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from the_one.platform.pty import create_pty_session
from the_one.tools import _session_registry
from the_one.tools.base import ConstraintError, Tool
from the_one.tools.execution import (
    ExecutionConfig,
    _boxed_cwd_check,
    _build_boxed_profile,
    _build_tool_profile,
    _command_check,
    _cwd_check,
    _truncate_output,
)
from the_one.tools.filesystem import FilesystemConfig


def _require_agent_name(tool: Tool) -> str:
    """Return ``tool._agent_name`` or raise ``ConstraintError`` if it's
    ``None``.

    DRY helper for the four session tools — every ``execute`` rejects the
    introspection path (``agent_name=None``) up front. The error message
    matches the leg-spec exactly so agent retry heuristics keyed on
    ``"session tools require an agent context"`` work uniformly.
    """
    name = tool._agent_name
    if name is None:
        raise ConstraintError("session tools require an agent context")
    return name


class ShellSessionStartTool(Tool):
    name = "shell_session_start"
    description = (
        "Start a new interactive shell session and return a session_id token. "
        "Use shell_session_send to run commands; shell_session_close to "
        "terminate; shell_session_list to recover handles. Default mode is "
        "boxed (isolated scratch dir, no access to the user's files or "
        "network); the scratch workspace persists across shell_session_send "
        "calls within the session, so install-then-use workflows work. Set "
        "host_access=true only when the session needs the user's real files or "
        "network access (respects the path allowlist; default cwd is $HOME). "
        "Sessions persist across agent turns and idle-reap after the "
        "operator-set TTL (default 5 min)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "cwd": {
                "type": "string",
                "description": (
                    "Working directory. Boxed: defaults to scratch root, must be "
                    "within the scratch dir. Host: defaults to $HOME, refused if "
                    "outside the path allowlist."
                ),
            },
            "host_access": {
                "type": "boolean",
                "description": (
                    "Default false: start a boxed session (isolated scratch "
                    "workspace, no access to the user's files or network). Set "
                    "true only when the session concretely needs the user's real "
                    "files or network access (path-allowlist checked)."
                ),
            },
        },
        "required": [],
    }

    Config = ExecutionConfig
    Requires = (FilesystemConfig,)

    async def execute(
        self,
        cwd: str | None = None,
        host_access: bool = False,
        **kwargs: Any,
    ) -> str:
        exec_cfg: ExecutionConfig = self._config  # type: ignore[assignment]
        try:
            agent_name = _require_agent_name(self)
            fs_cfg: FilesystemConfig = self._cross_configs[FilesystemConfig]  # type: ignore[index]
            # F4 Decision 5: enforce per-agent max concurrent sessions
            # cap. NB the (cap, register) sequence is NOT atomic under one
            # lock acquisition — concurrent ``start`` calls from a single
            # agent could each see ``count < max`` and all proceed past
            # the cap. Accepted for F4 (small-model agents do not
            # pipeline tool calls); see flight-log L6 notes.
            count = await _session_registry.count_for_agent(agent_name)
            if count >= exec_cfg.max_concurrent_sessions:
                raise ConstraintError(
                    f"max concurrent sessions reached "
                    f"({exec_cfg.max_concurrent_sessions}); close an existing "
                    f"session first"
                )

            # Allocate sid before the branch so boxed sessions can include it
            # in the scratch dir name for traceability.
            sid = _session_registry.new_session_id()

            if host_access:
                # Host-workspace path (escalated): use the operator allowlist.
                # Always validate cwd through ``_cwd_check`` — even the $HOME
                # default, so an operator who narrows ``$HOME`` out of scope
                # gets a clean refusal rather than a successful session
                # against a forbidden path.
                target_cwd: str | Path = cwd if cwd is not None else Path.home()
                canonical_cwd = _cwd_check(target_cwd, fs_cfg)
                profile = _build_tool_profile(fs_cfg, exec_cfg)
                cleanup_dir = None
            else:
                # Boxed path (default): persistent scratch, isolated profile.
                # Function-local settings import mirrors the leg-3 precedent
                # (_ephemeral_box_scratch) — avoids module-level Settings()
                # instantiation that would break env-monkeypatching tests.
                from the_one.config import settings  # function-local — see docstring

                scratch = settings.data_dir / "boxes" / f"{agent_name}-{sid}-{uuid4().hex}"
                # parents=True: "boxes" parent may already exist (leg 3 creates it too).
                # No exist_ok on the leaf — UUID collision is loud, which won't happen.
                scratch.mkdir(parents=True)
                canonical_cwd = _boxed_cwd_check(cwd, scratch)
                profile = _build_boxed_profile(scratch)
                cleanup_dir = scratch

            # ``create_pty_session`` accepts ``Path | None`` directly —
            # do NOT ``str(canonical_cwd)`` here; the L5a signature is
            # typed to ``Path | None``.
            session = create_pty_session(
                cwd=canonical_cwd, profile=profile, cleanup_dir=cleanup_dir
            )

            # Inner try/except covers only the start+register sequence, nested
            # inside the outer try (which keeps the ConstraintError + Exception
            # handlers below intact).  On any failure after session is
            # constructed, close() removes the session and its scratch dir so
            # neither a process nor a scratch directory leaks.
            try:
                await session.start()
                await _session_registry.register(
                    agent_name,
                    sid,
                    session,
                    ttl_seconds=exec_cfg.pty_session_idle_ttl_seconds,
                )
            except Exception:
                # session.start() succeeded (process may be running) OR failed
                # (session.close() is safe on a never-started session).
                # Either way, close() removes the scratch dir via cleanup_dir
                # and kills any running process.
                await session.close()
                raise

            return sid
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class ShellSessionSendTool(Tool):
    name = "shell_session_send"
    # M16 F08 L01 (HIGH-2): tail-preserve under the context-budget governor —
    # interactive shell output keeps its most-recent (diagnostic) tail.
    truncation_direction = "tail"
    description = (
        "Send input to an interactive shell session and return the output. "
        "session_id from shell_session_start. Inputs are filtered against the "
        "same denylist as one-shot shell. Echoing or printing denylisted "
        "tokens (e.g. 'sudo') requires writing them through a file "
        "(echo $S > /tmp/x after setting S outside the denylist) — this is "
        "intentional, not a bug. Output is capped (tail-preserved). Timeout "
        "in seconds; clipped to operator-set max."
    )
    parameters = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session id from shell_session_start.",
            },
            "input": {
                "type": "string",
                "description": "Text to write to the session's stdin.",
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Read timeout in seconds. Uses the resolved default if "
                    "omitted; clipped to the operator-set max."
                ),
            },
        },
        "required": ["session_id", "input"],
    }

    Config = ExecutionConfig
    # ``FilesystemConfig`` is not directly consulted by ``send`` (no cwd
    # validation per call), but we declare it for consistency with the
    # other execution-family tools so ``Requires`` reflects the dispatch
    # surface uniformly.
    Requires = (FilesystemConfig,)

    async def execute(
        self,
        session_id: str,
        input: str,  # noqa: A002  (kwarg name mirrors the JSON schema field)
        timeout: float | None = None,
        **kwargs: Any,
    ) -> str:
        exec_cfg: ExecutionConfig = self._config  # type: ignore[assignment]
        # Float-preserving timeout clip — matches L3/L4 pattern. Computed
        # BEFORE the try/except so the timeout error message reflects the
        # value the read actually saw.
        if timeout is None:
            clipped_timeout: float = exec_cfg.timeout_seconds_default
        else:
            clipped_timeout = min(timeout, exec_cfg.timeout_seconds_max)
            if clipped_timeout <= 0:
                clipped_timeout = 1
        try:
            agent_name = _require_agent_name(self)
            # F4 Decision 11: per-call denylist re-check. Same trip-wire
            # the one-shot ``shell`` and ``python_exec`` tools apply at
            # call time; here we apply it on every ``send`` even though
            # the session was already denylist-checked at ``start``.
            _command_check(input, exec_cfg)
            session = await _session_registry.get(agent_name, session_id)
            if session is None:
                raise ConstraintError(
                    f"session '{session_id}' not owned by this agent or does not exist"
                )
            output = await session.send(input, timeout=clipped_timeout)
            # PTY merges stderr into stdout via the master fd; pass
            # ``b""`` for stderr so ``_truncate_output`` does NOT inject
            # the ``[stderr]`` marker. ``returncode=0`` is a fixed
            # sentinel — the PTY layer doesn't surface a per-command
            # return code (the agent sees shell errors via the output
            # text itself, e.g. ``bash: foo: command not found``).
            text, _ = _truncate_output(output, b"", 0, exec_cfg)
            return text
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except asyncio.TimeoutError:
            # Wording is deliberately distinct from one-shot Shell's
            # ``Command timed out`` and Python's ``Timed out`` — the
            # agent should be able to tell which surface produced the
            # error from the message alone.
            return f"[error] Send timed out after {clipped_timeout}s"
        except Exception as e:
            return f"[error] {e}"


class ShellSessionCloseTool(Tool):
    name = "shell_session_close"
    description = "Terminate an interactive shell session. session_id from shell_session_start."
    parameters = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session id from shell_session_start.",
            },
        },
        "required": ["session_id"],
    }

    Config = ExecutionConfig
    Requires = ()

    async def execute(self, session_id: str, **kwargs: Any) -> str:
        try:
            agent_name = _require_agent_name(self)
            closed = await _session_registry.close(agent_name, session_id)
            if closed:
                return f"closed {session_id}"
            raise ConstraintError(
                f"session '{session_id}' not owned by this agent or does not exist"
            )
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class ShellSessionListTool(Tool):
    name = "shell_session_list"
    description = (
        "List session_ids of all open interactive shell sessions for this "
        "agent. Useful after long context windows when the agent has "
        "forgotten its handles."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    Config = ExecutionConfig
    Requires = ()

    async def execute(self, **kwargs: Any) -> str:
        try:
            agent_name = _require_agent_name(self)
            sids = await _session_registry.list_for_agent(agent_name)
            if not sids:
                return "(no open sessions)"
            return "\n".join(sids)
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
