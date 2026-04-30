from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from the_one.platform import canonicalize
from the_one.tools.base import (  # noqa: F401  (ConstraintError re-export for backward-compat)
    ConstraintError,
    Tool,
)
from the_one.tools.resolver import Narrow, NarrowPrefix, NarrowSuperset


class CheckMode(str, Enum):
    """Dispatch mode for `_filesystem_check`. F5 L0 unification of
    F3's read/write-parent/write-path helpers + F4's ``_cwd_check``.

    The four modes have genuinely divergent post-canonicalize shapes
    — see the dispatcher implementation. ``str`` mixin allows
    ergonomic test asserts like ``mode == "read"``."""

    READ = "read"  # scope only on canonicalize(path)
    WRITE_NEW = "write_new"  # scope on canonicalize(parent)/leaf, re-canonicalized
    WRITE_EXISTING_PARENT = "write_existing_parent"  # WRITE_NEW + parent.exists()
    DIRECTORY = "directory"  # READ + is_dir()

DEFAULT_PATH_DENYLIST: tuple[str, ...] = (
    # System secrets / credentials (8)
    "~/.ssh",
    "~/.aws",
    "~/.gcloud",
    "~/.azure",
    "~/.config/gh",
    "~/.netrc",
    "~/.docker/config.json",
    "~/.kube",
    # Browser / app data (4)
    "~/.mozilla",
    "~/.config/google-chrome",
    "~/.config/Code",
    "~/.config/Slack",
    # Agent's own internals (1)
    "~/.the-one/secrets",
    # Outside ~ — system paths (6)
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/var/log",
)


class FilesystemConfig(BaseModel):
    """Per-category Config for all 9 filesystem tools (F3 Decision 2).

    Four constraint fields: path-scope allowlist (narrowing-by-prefix),
    path-scope denylist (narrowing-by-superset — agent ADDS restrictions),
    read-size cap (Narrow), allow-binary-files flag (Narrow with positive
    naming so resolver's natural True=permissive/False=denied reading aligns).

    Eagerly canonicalizes allowlist/denylist entries via `model_post_init`
    + `PrivateAttr`. NOT `@computed_field @property` — those re-execute on
    every access and would defeat the N×M canonicalize-avoidance.

    Frozen (F4 Decision 7) so `cross_configs` shared by reference across
    tool instances in one `BuiltinToolProvider.get_tools(...)` call cannot
    be mutated by one tool to corrupt a peer's view. Pydantic's freeze
    blocks attribute *assignment*; `PrivateAttr` writes inside
    `model_post_init` use a different path and remain permitted.
    Note: list-content mutation (e.g. `cfg.path_denylist.append(...)`) is
    NOT blocked by `frozen=True` — freezing only guards the attribute
    binding, not contained mutable values.
    """

    model_config = ConfigDict(frozen=True)

    path_allowlist: Annotated[list[str], NarrowPrefix] = ["~"]

    path_denylist: Annotated[list[str], NarrowSuperset] = Field(
        default_factory=lambda: list(DEFAULT_PATH_DENYLIST)
    )

    read_size_cap_bytes: Annotated[
        int,
        Narrow,
        Field(
            ge=1024,
            le=104_857_600,
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 51_200, "label": "50KB — very small models"},
                    {"value": 102_400, "label": "100KB — small/7B-class friendly"},
                    {"value": 262_144, "label": "256KB — most models comfortable"},
                    {"value": 524_288, "label": "512KB — middle"},
                    {"value": 1_048_576, "label": "1MB — default (Opus 200K headroom)"},
                    {"value": 5_242_880, "label": "5MB — Opus 1M only"},
                ],
            },
        ),
    ] = 1_048_576

    allow_binary_files: Annotated[bool, Narrow] = False

    # Eagerly-computed canonical paths cached as PrivateAttr.
    # NOT @computed_field @property — those re-execute on every access and
    # would defeat the N×M canonicalize avoidance. PrivateAttr stores the
    # value once at model_post_init; subsequent reads are O(1).
    _canonical_allowlist: list[Path] = PrivateAttr(default_factory=list)
    _canonical_denylist: list[Path] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        # Runs after Pydantic finishes constructing the model. Compute the
        # canonical paths once and stash them on the private attrs.
        self._canonical_allowlist = [canonicalize(p) for p in self.path_allowlist]
        self._canonical_denylist = [canonicalize(p) for p in self.path_denylist]


def _is_descendant(path: Path, root: Path) -> bool:
    """True if ``path`` is strictly under ``root`` (NOT equal). Both
    arguments must be pre-canonicalized; this helper does not canonicalize.

    Implementation: ``Path.relative_to`` raises ``ValueError`` for unrelated
    paths and succeeds (returns ``Path('.')``) for equal paths. The
    ``path != root`` guard treats the equal case as "not strictly under"."""
    try:
        path.relative_to(root)
        return path != root
    except ValueError:
        return False


def _filesystem_check(
    path: str | Path,
    cfg: FilesystemConfig,
    mode: CheckMode = CheckMode.READ,
) -> Path:
    """Canonicalize ``path`` against ``cfg.path_allowlist``/``path_denylist``
    and run the mode's post-check. Returns the canonical Path on success.

    F5 L0 unified dispatcher — replaces the previous trio of
    ``_filesystem_check`` (READ), ``_filesystem_check_write_parent``
    (WRITE_EXISTING_PARENT), ``_filesystem_check_write_path`` (WRITE_NEW)
    plus F4's ``_cwd_check`` (DIRECTORY). The two-arg call form
    (``_filesystem_check(path, cfg)``) preserves identical READ behavior,
    so the 7+ existing call sites in ``the_one/tools/`` need no changes.

    Modes:
        - READ: scope check on ``canonicalize(path)``. No existence check.
        - WRITE_NEW: scope check on ``canonicalize(canonical_parent / leaf)``
          (parent canonicalized first, leaf composed, then re-canonicalized
          so a leaf-symlink-to-out-of-scope is rejected). Parent may not
          exist. Use for ``write_file``/``mkdir`` (caller mkdirs intermediates).
        - WRITE_EXISTING_PARENT: WRITE_NEW + assert parent exists. Raises
          ``FileNotFoundError`` (NOT ``ConstraintError``) on missing parent
          — environmental error distinct from policy refusal. Use for
          ``move_file`` destination, ``edit_file`` write-back.
        - DIRECTORY: scope check on ``canonicalize(path)`` + assert
          ``canonical.is_dir()``. Use for cwd validation in execution tools.

    Raises:
        ConstraintError: scope refusal (allowlist-fail or denylist-hit).
            Always checked FIRST so a hostile prompt cannot learn whether
            out-of-scope paths exist.
        FileNotFoundError: WRITE_EXISTING_PARENT mode only, when parent
            is in-scope but does not exist.

    Symlinks: ``canonicalize`` calls ``Path.resolve``, which follows
    symlinks. A symlink pointing outside the allowlist is therefore
    detected as out-of-scope (the symlink target's canonical form is
    used in the comparison). For WRITE_* modes, the second canonicalize
    pass on the composed path is what catches a leaf-symlink whose
    target lies out of scope."""
    p = Path(path).expanduser()

    # Canonicalize per mode shape. For WRITE_* modes, canonicalize the
    # PARENT first (handles non-existent leafs lexically), compose with
    # the leaf, then re-canonicalize the composed path. The second
    # canonicalize is required to resolve a leaf that IS an existing
    # symlink (otherwise a symlink to an out-of-scope target slips past
    # the scope check). This matches F3's pre-L0 behavior — the legacy
    # ``_filesystem_check_write_parent``/``_filesystem_check_write_path``
    # both delegated to ``_filesystem_check(composed, cfg)`` and got the
    # second resolve for free.
    if mode in (CheckMode.WRITE_NEW, CheckMode.WRITE_EXISTING_PARENT):
        canonical_parent = canonicalize(p.parent)
        canonical = canonicalize(canonical_parent / p.name)
    else:  # READ, DIRECTORY
        canonical_parent = None
        canonical = canonicalize(p)

    # Scope check (allowlist + denylist) — same across all modes,
    # checked FIRST to avoid leaking filesystem layout for out-of-scope
    # paths.
    in_allowlist = any(
        canonical == r or _is_descendant(canonical, r) for r in cfg._canonical_allowlist
    )
    if not in_allowlist:
        raise ConstraintError(f"path '{canonical}' outside allowlist")
    for deny in cfg._canonical_denylist:
        if canonical == deny or _is_descendant(canonical, deny):
            raise ConstraintError(f"path '{canonical}' inside denylist '{deny}'")

    # Mode-specific post-check.
    if mode == CheckMode.WRITE_EXISTING_PARENT:
        # ``canonical_parent`` is always set in this branch (set above
        # when mode is WRITE_NEW or WRITE_EXISTING_PARENT). Guard
        # explicitly rather than via ``assert`` so behavior is identical
        # under ``python -O`` (which strips asserts).
        if canonical_parent is None:
            raise RuntimeError(
                "unreachable: canonical_parent unset in WRITE_EXISTING_PARENT"
            )
        if not canonical_parent.exists():
            raise FileNotFoundError(
                f"parent does not exist for path '{path}': {canonical_parent}"
            )
    elif mode == CheckMode.DIRECTORY:
        if not canonical.is_dir():
            # ``Path.is_dir()`` returns False for both nonexistent and
            # non-directory paths; the combined wording is the F4 contract
            # downstream agents depend on — DO NOT change.
            raise ConstraintError(
                f"cwd '{canonical}' does not exist or is not a directory"
            )
    # READ and WRITE_NEW have no post-check.

    return canonical


def _filesystem_check_write_parent(path: str | Path, cfg: FilesystemConfig) -> Path:
    """Shim — calls ``_filesystem_check(path, cfg, CheckMode.WRITE_EXISTING_PARENT)``.
    Preserved so external imports (tests, future tools) keep resolving
    after the F5 L0 unification."""
    return _filesystem_check(path, cfg, CheckMode.WRITE_EXISTING_PARENT)


def _filesystem_check_write_path(path: str | Path, cfg: FilesystemConfig) -> Path:
    """Shim — calls ``_filesystem_check(path, cfg, CheckMode.WRITE_NEW)``.
    Preserved so external imports (tests, future tools) keep resolving
    after the F5 L0 unification."""
    return _filesystem_check(path, cfg, CheckMode.WRITE_NEW)


def _check_read_size(path: Path, cfg: FilesystemConfig) -> int:
    """Return the file size in bytes if it is at-or-under
    ``cfg.read_size_cap_bytes``; otherwise raise ``ConstraintError`` with
    the bare numerics. The pure-numerics form is unambiguous and survives
    either future read-shape (read-then-slice today, possibly stream-and-
    slice in a future leg) — no hint locks in either choice."""
    size = path.stat().st_size
    if size > cfg.read_size_cap_bytes:
        raise ConstraintError(
            f"file size {size} bytes exceeds cap {cfg.read_size_cap_bytes} bytes "
            "(operator can raise the cap; pagination cannot bypass it)"
        )
    return size


def _is_binary(path: Path) -> bool:
    """Heuristic binary-file detection: read up to 8192 bytes and check
    for any null byte. Files smaller than 8KB are scanned in full;
    larger files are sniffed only at the head (acceptable per Decision 2
    — null bytes after offset 8192 are not detected)."""
    with path.open("rb") as f:
        chunk = f.read(8192)
    return b"\x00" in chunk


# Number of context lines shown before/after the edit in `_format_edit_preview`.
# Module-level so ruff's N806 (in-function uppercase) doesn't flag it; this is
# a tuning constant, not a local variable.
_EDIT_PREVIEW_CONTEXT = 3


def _format_edit_preview(canonical: Path, old_text: str, old_string: str, new_string: str) -> str:
    """Render a diff-style preview of an edit.

    Format:
        Edited /path/to/file.py
        @@ around line N @@
           N-3 |   context line
           N-2 |   context line
           N-1 |   context line
        -    N |   old line
        +    N |   new line
           N+1 |   context line
           N+2 |   context line
           N+3 |   context line

    Multi-line edits emit one `-` line per old line and one `+` line per
    new line. Line numbers in the `-` rows count from `old_text`; line
    numbers in the `+` rows count from the new text (so post-edit line
    numbers show what the file now looks like)."""
    # Find the start line of the edit (1-indexed).
    edit_offset = old_text.index(old_string)
    start_line = old_text[:edit_offset].count("\n") + 1

    old_lines = old_text.splitlines()
    new_text = old_text.replace(old_string, new_string, 1)
    new_lines = new_text.splitlines()

    # How many lines does old_string span? new_string?
    # Use splitlines() length, NOT count("\n") + 1. The latter overcounts
    # when the string ends in `\n` (the trailing newline closes the last
    # line; no partial line follows). `"b\nc\n".splitlines() == ["b","c"]`
    # (length 2 = the actual span) vs `count + 1 == 3` (wrong).
    # old_span is always >= 1 because empty old_string would have been
    # rejected by the count==0 check upstream.
    old_span = len(old_string.splitlines())
    # new_span CAN be 0 when new_string is empty (deletion case). That
    # produces `new_block = new_lines[start_line-1:start_line-1] = []`,
    # so zero `+` rows are emitted — exactly the deletion preview.
    new_span = len(new_string.splitlines())

    # Build the segments. start_line is 1-indexed; old_lines is 0-indexed.
    pre_start = max(0, start_line - 1 - _EDIT_PREVIEW_CONTEXT)
    pre_end = start_line - 1
    pre_lines = old_lines[pre_start:pre_end]

    old_block = old_lines[start_line - 1 : start_line - 1 + old_span]
    new_block = new_lines[start_line - 1 : start_line - 1 + new_span]

    post_start_in_new = start_line - 1 + new_span
    post_lines = new_lines[post_start_in_new : post_start_in_new + _EDIT_PREVIEW_CONTEXT]

    out = [f"Edited {canonical}", f"@@ around line {start_line} @@"]
    for i, line in enumerate(pre_lines):
        out.append(f"  {pre_start + i + 1:>5} | {line}")
    for i, line in enumerate(old_block):
        out.append(f"- {start_line + i:>5} | {line}")
    for i, line in enumerate(new_block):
        out.append(f"+ {start_line + i:>5} | {line}")
    for i, line in enumerate(post_lines):
        out.append(f"  {start_line + new_span + i:>5} | {line}")
    return "\n".join(out)


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "offset": {"type": "integer", "description": "Line number to start from (0-based)."},
            "limit": {"type": "integer", "description": "Max number of lines to read."},
        },
        "required": ["path"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check(path, cfg)
            _check_read_size(canonical, cfg)
            if _is_binary(canonical) and not cfg.allow_binary_files:
                raise ConstraintError(
                    "binary file refused (set by operator only; not an agent-passable parameter)"
                )
            text = canonical.read_text(errors="replace")
            lines = text.splitlines()
            if offset or limit:
                end = (offset + limit) if limit else None
                lines = lines[offset:end]
            return "\n".join(f"{i + offset + 1:>5} | {line}" for i, line in enumerate(lines))
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file, creating directories as needed."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "content": {"type": "string", "description": "Content to write."},
        },
        "required": ["path", "content"],
    }
    Config = FilesystemConfig

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check_write_path(path, cfg)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_text(content)
            return f"Wrote {len(content)} bytes to {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class ListDirTool(Tool):
    name = "list_dir"
    description = "List files and directories at a given path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: current dir)."},
            "recursive": {"type": "boolean", "description": "List recursively.", "default": False},
        },
        "required": [],
    }
    Config = FilesystemConfig

    async def execute(self, path: str = ".", recursive: bool = False, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check(path, cfg)
            if recursive:
                entries = sorted(canonical.rglob("*"))
            else:
                entries = sorted(canonical.iterdir())
            lines = []
            for e in entries[:500]:  # cap output
                prefix = "d " if e.is_dir() else "f "
                lines.append(f"{prefix}{e.relative_to(canonical)}")
            result = "\n".join(lines)
            if len(entries) > 500:
                result += f"\n... and {len(entries) - 500} more"
            return result or "(empty directory)"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Edit a file by replacing exactly-once-matching text. The old_string "
        "must be unique in the file; if it matches multiple times, add "
        "surrounding context to make the match unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "old_string": {
                "type": "string",
                "description": "Text to replace; must appear exactly once.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            if old_string == new_string:
                raise ConstraintError("old_string and new_string are identical; no change to apply")
            canonical = _filesystem_check(path, cfg)
            _check_read_size(canonical, cfg)
            if _is_binary(canonical) and not cfg.allow_binary_files:
                raise ConstraintError(
                    "binary file refused (set by operator only; not an agent-passable parameter)"
                )
            text = canonical.read_text(errors="replace")
            n = text.count(old_string)
            if n == 0:
                raise ConstraintError(f"old_string not found in '{canonical}'")
            if n > 1:
                raise ConstraintError(
                    f"old_string matched {n} times in '{canonical}'; "
                    "add surrounding context to make the match unique"
                )
            new_text = text.replace(old_string, new_string, 1)
            canonical.write_text(new_text)
            return _format_edit_preview(canonical, text, old_string, new_string)
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Delete a file. Refuses directories — use a different approach for those."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to delete."},
        },
        "required": ["path"],
    }
    Config = FilesystemConfig

    async def execute(self, path: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check(path, cfg)
            if canonical.is_dir():
                raise ConstraintError(
                    f"path '{canonical}' is a directory; delete_file operates on files only"
                )
            canonical.unlink()
            return f"Deleted {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class MoveFileTool(Tool):
    name = "move_file"
    description = (
        "Move or rename a file from source to destination. By default "
        "refuses to overwrite an existing destination — pass overwrite=true "
        "to permit."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path."},
            "destination": {"type": "string", "description": "Destination path."},
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite an existing destination.",
                "default": False,
            },
        },
        "required": ["source", "destination"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical_src = _filesystem_check(source, cfg)
            canonical_dst = _filesystem_check_write_parent(destination, cfg)
            if canonical_dst.exists() and not overwrite:
                raise ConstraintError(
                    f"destination '{canonical_dst}' exists; pass overwrite=true to replace it"
                )
            canonical_src.replace(canonical_dst)
            return f"Moved {canonical_src} → {canonical_dst}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class MkdirTool(Tool):
    name = "mkdir"
    description = (
        "Create a directory and any missing parent directories. "
        "Idempotent — succeeds silently if the directory already exists."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to create."},
        },
        "required": ["path"],
    }
    Config = FilesystemConfig

    async def execute(self, path: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check_write_path(path, cfg)
            canonical.mkdir(parents=True, exist_ok=True)
            return f"Created {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class GlobTool(Tool):
    name = "glob"
    description = (
        "Find files matching a pattern (Python pathlib glob syntax — "
        "'**' for recursive, '*' for any chars in a name). Returns "
        "canonical paths, one per line. Capped at 500 matches."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g. '*.py', '**/*.txt').",
            },
            "root": {
                "type": "string",
                "description": "Directory to search from (default: '.').",
                "default": ".",
            },
        },
        "required": ["pattern"],
    }
    Config = FilesystemConfig

    async def execute(self, pattern: str, root: str = ".", **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical_root = _filesystem_check(root, cfg)
            if not canonical_root.is_dir():
                raise ConstraintError(f"glob root '{canonical_root}' is not a directory")
            included: list[Path] = []
            skipped_oos = 0
            for match in canonical_root.glob(pattern):
                try:
                    canonical_match = _filesystem_check(match, cfg)
                except ConstraintError:
                    skipped_oos += 1
                    continue
                included.append(canonical_match)
            included.sort()
            capped = included[:500]
            lines = [str(p) for p in capped]
            if len(included) > 500:
                lines.append(f"... and {len(included) - 500} more")
            if skipped_oos > 0:
                lines.append(f"(skipped {skipped_oos} paths outside scope)")
            return "\n".join(lines) if lines else "(no matches)"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class GrepTool(Tool):
    name = "grep"
    description = (
        "Search file contents for a pattern (regex by default, or "
        "literal-string with fixed_string=true). Returns matches as "
        "'path:line_num:matched_line'. Skips binary and oversized files "
        "silently. Capped at 500 total matches and 100 per file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern (regex by default).",
            },
            "path": {
                "type": "string",
                "description": "Directory to search.",
            },
            "fixed_string": {
                "type": "boolean",
                "description": "If true, treat pattern as literal text.",
                "default": False,
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob filter for files to search (default '*').",
                "default": "*",
            },
        },
        "required": ["pattern", "path"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        pattern: str,
        path: str,
        fixed_string: bool = False,
        file_pattern: str = "*",
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical_root = _filesystem_check(path, cfg)
            if not canonical_root.is_dir():
                raise ConstraintError(f"grep root '{canonical_root}' is not a directory")
            regex: re.Pattern[str] | None = None
            if not fixed_string:
                regex = re.compile(pattern)
            matches: list[str] = []
            skipped_binary = 0
            skipped_oversized = 0
            truncated_files = 0
            global_cap_hit = False

            for candidate in canonical_root.rglob(file_pattern):
                if global_cap_hit:
                    break
                if not candidate.is_file():
                    continue
                try:
                    canonical_candidate = _filesystem_check(candidate, cfg)
                except ConstraintError:
                    continue
                try:
                    _check_read_size(canonical_candidate, cfg)
                except ConstraintError:
                    skipped_oversized += 1
                    continue
                if _is_binary(canonical_candidate) and not cfg.allow_binary_files:
                    skipped_binary += 1
                    continue
                text = canonical_candidate.read_text(errors="replace")
                per_file_count = 0
                for line_idx, line in enumerate(text.splitlines(), start=1):
                    if fixed_string:
                        matched = pattern in line
                    else:
                        assert regex is not None
                        matched = regex.search(line) is not None
                    if not matched:
                        continue
                    if len(matches) >= 500:
                        global_cap_hit = True
                        break
                    if per_file_count >= 100:
                        truncated_files += 1
                        break
                    matches.append(f"{canonical_candidate}:{line_idx}:{line}")
                    per_file_count += 1

            lines: list[str] = list(matches)
            if global_cap_hit:
                lines.append("... and more matches (global cap of 500 reached)")
            if truncated_files > 0:
                lines.append(
                    f"(per-file cap reached for {truncated_files} file(s); "
                    "first 100 matches per file shown)"
                )
            if skipped_binary > 0:
                lines.append(f"(skipped {skipped_binary} binary file(s))")
            if skipped_oversized > 0:
                lines.append(f"(skipped {skipped_oversized} oversized file(s))")
            return "\n".join(lines) if lines else "(no matches)"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
