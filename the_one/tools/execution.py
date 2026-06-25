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

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Iterator

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

    # M16 F08 L01 (HIGH-2, option b): RECLASSIFIED from a model-sized LLM cap to
    # a transport/safety CEILING. The central context-budget governor in
    # ``Agent._execute_tool`` now applies the model-derived LLM bound on top
    # (tail-preserving for shell/exec), so this field is no longer the
    # context-fit knob — it is the large absolute cap on how much combined
    # output the tool buffers/returns before the governor trims it. The
    # ``_truncate_output`` formatting ([exit code: N] suffix, stderr tail,
    # tail-preservation) is unchanged; the default (256 KB) is kept.
    output_cap_bytes: Annotated[
        int,
        Narrow,
        Field(
            ge=1024,
            le=104_857_600,  # 100 MB hard ceiling
            description="Combined stdout+stderr transport/safety ceiling; "
            "tail-preserving truncation. The context-budget governor applies the "
            "model-derived LLM bound on top.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 32_768, "label": "32KB — tight safety ceiling"},
                    {"value": 65_536, "label": "64KB — small ceiling"},
                    {"value": 262_144, "label": "256KB — default safety ceiling"},
                    {"value": 524_288, "label": "512KB — long build logs"},
                    {"value": 1_048_576, "label": "1MB — large logs"},
                    {"value": 5_242_880, "label": "5MB — very large logs"},
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


def _build_boxed_profile(scratch: "str | Path") -> "SandboxProfile":
    """Build a boxed (isolated) ``SandboxProfile`` rooted at *scratch*.

    Unlike the host-workspace sibling ``_build_tool_profile``, the boxed
    profile has no operator allowlist, no host FS overlay, and
    **unconditionally disables network access** — the box has no network by
    definition (not read from ``ExecutionConfig``).

    * ``minimal_rootfs=True`` — backend mounts a minimal read-only rootfs
      rather than binding the host filesystem.
    * ``writable_paths`` — ``[str(scratch)]`` only; the box is confined to
      the scratch directory.
    * ``readonly_overlay_paths`` — empty; there is no host FS to re-protect.
    * ``home`` — the scratch directory (no real ``$HOME`` in the box).
    * ``network_allowed`` — always ``False``.

    The caller (legs 3–4) is responsible for creating *scratch* before
    calling this function; ``is_dir()`` will fail on a non-existent path.
    """
    # Function-level import to avoid any tools↔platform.sandbox import cycle.
    from the_one.platform.sandbox import SandboxProfile

    # home=str(scratch) is what sets $HOME inside the box: bubblewrap injects
    # it via --setenv HOME (bubblewrap.py:131); passthrough sets os.environ["HOME"].
    return SandboxProfile(
        minimal_rootfs=True,
        writable_paths=[str(scratch)],
        readonly_overlay_paths=[],
        network_allowed=False,
        home=str(scratch),
    )


def _boxed_cwd_check(cwd: "str | Path | None", scratch: "str | Path") -> Path:
    """Validate *cwd* is within *scratch* and return the canonical ``Path``.

    Builds an ephemeral ``FilesystemConfig(path_allowlist=[str(scratch)],
    path_denylist=[])`` — **``path_denylist=[]`` is required**, not
    stylistic: omitting it would apply the default 19-entry denylist and
    could block paths inside the scratch — then delegates to
    ``_filesystem_check(..., CheckMode.DIRECTORY)`` which canonicalises the
    path and verifies it exists and is a directory.

    Decision (M14 F4): a caller-supplied *cwd* is **honored** if it is a
    subdirectory of (or equal to) *scratch*, and rejected with
    ``ConstraintError`` otherwise — symmetric with the host-mode
    ``_cwd_check`` contract.  When *cwd* is ``None`` the scratch root is
    used as the working directory.

    The caller (legs 3–4) must create *scratch* before invoking this
    function; ``is_dir()`` inside ``_filesystem_check`` will raise if the
    directory does not yet exist.
    """
    # Local import mirrors the pattern in _cwd_check (execution.py:353).
    from the_one.tools.filesystem import CheckMode

    effective_cwd = cwd if cwd is not None else str(scratch)
    ephemeral_cfg = FilesystemConfig(
        path_allowlist=[str(scratch)],
        path_denylist=[],
    )
    return _filesystem_check(effective_cwd, ephemeral_cfg, CheckMode.DIRECTORY)


def prune_box_scratch() -> None:
    """Remove every child of ``settings.data_dir / "boxes"`` at process startup.

    Called ONCE at process startup — from the FastAPI lifespan startup and from
    the CLI ``_run_cli`` startup — when THIS process has no live boxed sessions
    (the session registry starts empty at startup), so every ``boxes/<…>`` is an
    orphan left by a prior run (SIGKILL, OOM, or any other ungraceful exit that
    prevented the per-call or per-session cleanup from running).

    **Single-process-at-a-time assumption**: a concurrent process sharing the same
    data_dir (e.g. web + CLI running simultaneously) is unsupported and out of
    scope — a startup prune in one would remove the other's live boxes. Do NOT run
    this in ``settings.ensure_dirs()``; that is called per ``AgentFactory.create()``
    and would delete a live session's scratch mid-operation.

    Failures are non-fatal: individual ``shutil.rmtree`` calls use
    ``ignore_errors=True``; the function logs a count but never raises.

    The ``settings`` import is **function-local** (design-review requirement): a
    module-level import would eagerly instantiate ``Settings()`` at import time and
    break env-monkeypatching tests — mirrors the precedent in
    ``_ephemeral_box_scratch`` and in ``tools/connector_send.py``.
    """
    import logging

    from the_one.config import settings  # function-local — see docstring

    base = settings.data_dir / "boxes"
    if not base.exists():
        return
    count = 0
    for child in list(base.iterdir()):
        shutil.rmtree(child, ignore_errors=True)
        count += 1
    if count:
        logging.getLogger(__name__).info(
            "startup-prune: removed %d orphaned box scratch dir(s) from %s", count, base
        )


@contextmanager
def _ephemeral_box_scratch() -> Iterator[Path]:
    """Context manager: create a fresh ephemeral scratch dir, yield it, clean up.

    Creates ``settings.data_dir / "boxes" / <uuid4().hex>`` as the scratch root.
    The ``settings`` import is **function-local** (design-review requirement): a
    module-level ``from the_one.config import settings`` would eagerly instantiate
    ``Settings()`` at import time and break env-monkeypatching tests — mirrors the
    precedent in ``tools/connector_send.py`` / ``tools/connector_history.py``.

    Guarantees ``shutil.rmtree`` in ``finally`` so the scratch dir is removed on
    both clean return and exception (including timeouts that propagate as
    ``asyncio.TimeoutError`` out of the ``with`` block in the tool's ``try``).
    """
    from uuid import uuid4

    from the_one.config import settings  # function-local — see docstring

    base = settings.data_dir / "boxes"
    base.mkdir(parents=True, exist_ok=True)
    scratch = base / uuid4().hex
    scratch.mkdir()
    try:
        yield scratch
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
