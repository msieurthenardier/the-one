"""Execution-tool category Config + helpers (F4 L2).

Defines the per-category Pydantic ``ExecutionConfig`` shared by all execution
tools (`shell`, `python_exec`, and the four `shell_session_*` tools landing in
later legs) plus four module-level helpers the tools call:

* ``_command_check`` — substring denylist refusal (F4 Decision 3).
* ``_cwd_check``    — cross-Config cwd validation; thin shim over
  ``filesystem._filesystem_check(..., CheckMode.DIRECTORY)`` post-F5 L0
  (F4 Decision 7).
* ``_truncate_output`` — combined stdout+stderr tail-preserving cap formatter
  (F4 Decision 2).
* ``_build_subprocess_env`` — hardcoded 8-key env allowlist (F4 Decision 10).
* ``_build_tool_profile`` — construct a host-workspace ``SandboxProfile`` from
  ``FilesystemConfig`` + ``ExecutionConfig`` (F14 flight 01 leg 4, DD10).

The ``_ENV_ALLOWLIST`` and ``DEFAULT_COMMAND_DENYLIST`` constants are
module-level and intentionally NOT operator-configurable — Decision 10 (env
allowlist is part of the F4 trust contract) and Decision 3 (denylist baseline
ships with the tool; operators can ADD entries via the resolver, never REMOVE).

This leg is pure scaffolding: no tool wiring. L3 wires ``ShellTool``;
L4 wires ``PythonExecTool``; L6 wires the four pty session tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile

from the_one.platform.env import (  # noqa: F401  (re-export for L3/L4 backward-compat)
    _ENV_ALLOWLIST,
    _build_subprocess_env,
)
from the_one.tools.base import ConstraintError
from the_one.tools.filesystem import FilesystemConfig, _filesystem_check
from the_one.tools.resolver import Narrow, NarrowSuperset

# ---------------------------------------------------------------------------
# Module-level constants (NOT operator-configurable)
# ---------------------------------------------------------------------------

# F4 Decision 10: ``_ENV_ALLOWLIST`` and ``_build_subprocess_env`` are now
# defined in ``the_one/platform/env.py`` and re-exported above for
# backward-compat (existing L2/L3/L4 tests import them from this module).
# F4 L5a moved the definitions because ``the_one/platform/pty.py`` needs to
# call ``_build_subprocess_env`` — placing the env machinery in
# ``platform/env.py`` keeps the dependency direction correct
# (``platform/`` is the lower layer; reaching into ``tools/`` from
# ``platform/`` would be backwards).

# F4 L4: shared ``ui_choices`` payload for the ``timeout_seconds_default`` field
# on both ``ExecutionConfig`` and ``PythonExecConfig``. Hoisted to a module
# constant because Pydantic v2 does NOT inherit ``json_schema_extra`` when a
# subclass re-declares the field — without re-stating it, ``PythonExecConfig``
# would lose its F6 admin UI metadata. The single source of truth keeps the two
# Configs' dropdowns in lock-step (the ShellTool 30s default and the
# PythonExecTool 90s default both appear as labeled choices).
_TIMEOUT_DEFAULT_UI_CHOICES: list[dict[str, object]] = [
    {"value": 10, "label": "10s — very tight"},
    {"value": 30, "label": "30s — default (shell)"},
    {"value": 60, "label": "60s — moderate compute"},
    {"value": 90, "label": "90s — default (python)"},
    {"value": 300, "label": "5m — long compute"},
]

# F4 Decision 3: command denylist baseline. Trip-wire (NOT a fence) — catches
# obvious-stupid (typos, prompt-injection telegraphs in plaintext, the
# operator's company-specific dangerous patterns). Trailing space on
# ``"sudo "`` / ``"su "`` / ``"doas "`` avoids the ``sudoku`` false positive
# class. Substring match: ``bash -c "sudo ..."`` is caught (the wrapped
# command string contains ``"sudo "``); first-token splitting would miss it.
DEFAULT_COMMAND_DENYLIST: tuple[str, ...] = (
    # Privilege escalation (trailing space avoids the `sudoku` false positive)
    "sudo ",
    "su ",
    "doas ",
    # Destructive filesystem
    "rm -rf /",
    "rm -rf ~",
    "rm -rf $HOME",
    # Disk / partition
    "mkfs",
    "dd if=",
    "dd of=/dev/",
    # System control
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    # Fork bombs
    ":(){ :|:& };:",
    # Kernel / module loading
    "insmod ",
    "rmmod ",
    "modprobe ",
    # Network destructive
    "iptables -F",
)


# ---------------------------------------------------------------------------
# ExecutionConfig — per-category Pydantic Config
# ---------------------------------------------------------------------------


class ExecutionConfig(BaseModel):
    """Per-category Config for all 6 execution tools (F4 Decisions 1, 2, 3, 5).

    Six constraint fields:

    * ``timeout_seconds_default`` (Narrow int) — used when agent omits timeout.
    * ``timeout_seconds_max`` (Narrow int) — hard ceiling; agent value clipped.
    * ``output_cap_bytes`` (Narrow int) — combined stdout+stderr cap.
    * ``command_denylist`` (NarrowSuperset list[str]) — forbidden substrings.
    * ``pty_session_idle_ttl_seconds`` (Narrow int) — reaper TTL.
    * ``max_concurrent_sessions`` (Narrow int) — per-agent session cap.

    Plus a ``model_validator(mode="after")`` cross-field invariant
    enforcing ``timeout_seconds_default <= timeout_seconds_max``.

    Frozen (F4 Decision 7) so the per-call cross_configs view shared across
    tool instances cannot be mutated by one tool to corrupt another's view.
    Mirrors ``FilesystemConfig``'s freeze posture.

    Note: ``command_denylist`` MUST default-factory to a *list* (NOT the
    underlying tuple) — the resolver's ``_check_narrow_superset`` requires
    ``isinstance(tool_val, list)``. ``Field(default_factory=lambda: list(...))``
    is the precedent set by ``FilesystemConfig.path_denylist``.
    """

    model_config = ConfigDict(frozen=True)

    timeout_seconds_default: Annotated[
        int,
        Narrow,
        Field(
            ge=1,
            le=3600,
            description="Used when agent omits timeout.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": _TIMEOUT_DEFAULT_UI_CHOICES,
            },
        ),
    ] = 30

    timeout_seconds_max: Annotated[
        int,
        Narrow,
        Field(
            ge=1,
            le=3600,
            description="Hard ceiling; agent value clipped.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 30, "label": "30s — strict"},
                    {"value": 120, "label": "2m — default"},
                    {"value": 300, "label": "5m — long compute"},
                    {"value": 900, "label": "15m — long builds"},
                    {"value": 3600, "label": "1h — max"},
                ],
            },
        ),
    ] = 120

    output_cap_bytes: Annotated[
        int,
        Narrow,
        Field(
            ge=1024,
            le=104_857_600,  # 100 MB hard ceiling
            description="Combined stdout+stderr cap; tail-preserving truncation.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 32_768, "label": "32KB — very small models"},
                    {"value": 65_536, "label": "64KB — small/7B-class friendly"},
                    {"value": 262_144, "label": "256KB — default (typical test runs)"},
                    {"value": 524_288, "label": "512KB — long build logs"},
                    {"value": 1_048_576, "label": "1MB — Opus headroom"},
                    {"value": 5_242_880, "label": "5MB — Opus 1M only"},
                ],
            },
        ),
    ] = 262_144

    command_denylist: Annotated[
        list[str],
        NarrowSuperset,
        Field(
            default_factory=lambda: list(DEFAULT_COMMAND_DENYLIST),
            description=(
                "Substring tokens denied in any execution-tool command. Trip-wire "
                "for obvious-stupid; not a fence against adversarial agents."
            ),
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {
                        "value": list(DEFAULT_COMMAND_DENYLIST),
                        "label": "default baseline (recommended)",
                    },
                ],
            },
        ),
    ]

    pty_session_idle_ttl_seconds: Annotated[
        int,
        Narrow,
        Field(
            ge=10,
            le=3600,
            description="Reap pty sessions idle longer than this.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 60, "label": "1m — aggressive (fast turns only)"},
                    {"value": 300, "label": "5m — default"},
                    {"value": 900, "label": "15m — long thinking turns"},
                    {"value": 1800, "label": "30m — long multi-tool sequences"},
                    {"value": 3600, "label": "1h — max"},
                ],
            },
        ),
    ] = 300

    max_concurrent_sessions: Annotated[
        int,
        Narrow,
        Field(
            ge=1,
            le=50,
            description="Per-agent cap on simultaneous pty sessions.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 1, "label": "1 — single session only"},
                    {"value": 3, "label": "3 — minimal parallel work"},
                    {"value": 5, "label": "5 — default"},
                    {"value": 10, "label": "10 — heavy parallel work"},
                    {"value": 20, "label": "20 — max"},
                ],
            },
        ),
    ] = 5

    sandbox_network_allowed: Annotated[
        bool,
        Narrow,
        Field(
            description=(
                "Allow the sandboxed tool subprocess network access "
                "(deny-by-default; the agent's dedicated web tools are unaffected)."
            ),
        ),
    ] = False

    @model_validator(mode="after")
    def _default_le_max(self) -> "ExecutionConfig":
        """Enforce the cross-field invariant ``default <= max``.

        Runs at ``schema.model_validate(merged)`` time — i.e. AFTER the
        resolver's per-key narrowing dispatch. This guarantees that an
        agent cannot widen ``default`` past a narrowed ``max``: if
        narrowing leaves ``max < default``, this validator raises.
        """
        if self.timeout_seconds_default > self.timeout_seconds_max:
            raise ValueError(
                f"timeout_seconds_default ({self.timeout_seconds_default}s) "
                f"must be <= timeout_seconds_max ({self.timeout_seconds_max}s)"
            )
        return self


# ---------------------------------------------------------------------------
# PythonExecConfig — ExecutionConfig subclass with a 90s default timeout
# ---------------------------------------------------------------------------


class PythonExecConfig(ExecutionConfig):
    """``ExecutionConfig`` variant with a 90-second default timeout for
    ``PythonExecTool`` (F4 Decision 9). Python is more often used for
    compute (numerics, parsing) than shell is; the higher default reduces
    friction for typical workloads. The cap (``timeout_seconds_max``) and
    all other constraints — denylist, output cap, env allowlist, pty TTL,
    session cap — are inherited unchanged.

    Note: with the inherited ``timeout_seconds_max=120``, this gives agents
    only 30s of headroom above the new default. Operators running heavy
    compute should also raise ``timeout_seconds_max``.

    Pydantic v2 does NOT inherit ``json_schema_extra`` when a field is
    re-declared, so the ``ui_hint`` / ``ui_choices`` metadata must be
    re-stated. Both Configs reference ``_TIMEOUT_DEFAULT_UI_CHOICES`` so the
    dropdown stays in lock-step. The cross-field ``_default_le_max``
    validator and ``model_config = ConfigDict(frozen=True)`` are inherited.
    """

    timeout_seconds_default: Annotated[
        int,
        Narrow,
        Field(
            ge=1,
            le=3600,
            description="Default timeout (PythonExec: 90s vs Shell: 30s).",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": _TIMEOUT_DEFAULT_UI_CHOICES,
            },
        ),
    ] = 90


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _command_check(command: str, cfg: ExecutionConfig) -> None:
    """Refuse if any token in ``cfg.command_denylist`` is a substring of
    ``command``. F4 Decision 3 — trailing-space convention catches
    ``bash -c "sudo ..."`` while letting ``sudoku`` through.

    First match wins; the error names the matched token so small-model
    agents can recover without re-trying the same wrapped form.
    """
    for token in cfg.command_denylist:
        if token in command:
            raise ConstraintError(f"command contains denylisted token '{token}'")


def _cwd_check(cwd: str | Path, fs_cfg: FilesystemConfig) -> Path:
    """Shim — calls ``_filesystem_check(cwd, fs_cfg, CheckMode.DIRECTORY)``.

    Preserved as a name for execution-tool readability; the unified
    dispatch (scope check + ``is_dir()`` post-check, same
    ``"does not exist or is not a directory"`` wording) lives in
    ``the_one/tools/filesystem.py`` post-F5 L0.
    """
    # Local import keeps the existing top-of-file import block minimal
    # (the architect noted there is no actual cycle here; this is just
    # a one-line shim, not worth touching the module-level imports).
    from the_one.tools.filesystem import CheckMode

    return _filesystem_check(cwd, fs_cfg, CheckMode.DIRECTORY)


def _truncate_output(
    stdout: bytes,
    stderr: bytes,
    returncode: int,
    cfg: ExecutionConfig,
) -> tuple[str, bool]:
    """Combine stdout + stderr (with ``\\n[stderr]\\n`` marker), tail-preserve
    to ``cfg.output_cap_bytes``, append ``[exit code: N]`` suffix when
    ``returncode != 0``.

    Returns ``(formatted_text, was_truncated)``. The bool is for test
    purchase — ``assert was_truncated is True`` is sharper than
    substring-matching the marker line.

    Two distinct markers operate at different layers:

    * **``\\n[stderr]\\n`` marker** (10 bytes; F4 L3 refinement): inserted
      between ``stdout`` and ``stderr`` BEFORE capping when ``stderr`` is
      non-empty. Marker bytes ARE part of ``combined`` and ARE counted
      against ``cfg.output_cap_bytes``. Tail-preserving truncation may
      chop into or past this marker — acceptable. This makes the helper
      the single source of truth for the existing F1 ``[stderr]``
      contract; ``ShellTool`` and (L4) ``PythonExecTool`` both inherit it.
    * **Truncation marker ``[... truncated N bytes; ...]\\n``** (~80
      chars): prepended AFTER capping. NOT counted against the cap (per
      F4 Decision 2 — cap shapes the agent's view, it is not a hard byte
      budget). Returned text length can exceed ``cap`` by the marker.

    Tail-preserving (drop FRONT, retain LAST cap bytes): build/test
    output puts the actionable signal (failures, summary, traceback) at
    the end.

    Empty-output behavior matches today's ``ShellTool``:
    ``(b"", b"", 0)`` → ``"(no output)"``;
    ``(b"", b"", 1)`` → ``"[exit code: 1]"`` (the exit suffix is appended
    BEFORE ``.strip()``, so the text isn't empty when rc != 0).
    """
    if stderr:
        combined = stdout + b"\n[stderr]\n" + stderr
    else:
        combined = stdout
    cap = cfg.output_cap_bytes
    was_truncated = False
    if len(combined) > cap:
        dropped = len(combined) - cap
        tail = combined[-cap:]
        marker = (
            f"[... truncated {dropped} bytes; showing last {cap} bytes "
            f"of combined stdout+stderr ...]\n"
        )
        # `errors="replace"` handles UTF-8 codepoints split mid-sequence
        # by the byte-boundary tail slice (replacement char is fine).
        text = marker + tail.decode(errors="replace")
        was_truncated = True
    else:
        text = combined.decode(errors="replace")
    if returncode != 0:
        text += f"\n[exit code: {returncode}]"
    text = text.strip() or "(no output)"
    return text, was_truncated


# ``_build_subprocess_env`` is re-exported at the top of this module from
# ``the_one.platform.env`` (F4 L5a moved it).


def _build_tool_profile(fs_cfg: FilesystemConfig, exec_cfg: ExecutionConfig) -> "SandboxProfile":
    """Build a host-workspace ``SandboxProfile`` from the tool's Config pair (DD10).

    Maps the operator's ``FilesystemConfig`` allowlist/denylist and the
    ``ExecutionConfig.sandbox_network_allowed`` flag onto a ``SandboxProfile``
    suitable for ``get_sandbox_backend().prepare_spawn()``.

    * ``writable_paths`` — the canonical allowlist from ``fs_cfg`` (already
      ``expanduser`` + ``resolve``'d by ``model_post_init``; bwrap requires
      real absolute paths).
    * ``readonly_overlay_paths`` — the canonical denylist (optional-secret paths
      re-protected as read-only on top of a writable root, DD4).
    * ``network_allowed`` — ``exec_cfg.sandbox_network_allowed`` (deny-by-default,
      DD6).
    * ``home`` — the real home (``str(Path.home())``); the shell tool's default
      cwd is ``$HOME`` and ``~``-relative writes must persist (DD4).
    * Namespace flags (``pid_unshare``, ``ipc_unshare``, ``uts_unshare``) left
      at their ``SandboxProfile`` defaults (all True).

    cwd is not separately injected into ``writable_paths`` because
    ``_cwd_check`` already constrains cwd to the allowlist, so cwd ⊆ writable
    by construction.

    Shared by ``ShellTool`` and ``PythonExecTool`` — the hook Flight 4
    (boxed mode) branches in.
    """
    # Function-level import to avoid any tools↔platform.sandbox import cycle.
    from the_one.platform.sandbox import SandboxProfile

    return SandboxProfile(
        writable_paths=[str(p) for p in fs_cfg._canonical_allowlist],
        readonly_overlay_paths=[str(p) for p in fs_cfg._canonical_denylist],
        network_allowed=exec_cfg.sandbox_network_allowed,
        home=str(Path.home()),
    )
