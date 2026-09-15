"""Filesystem walk, filter rules and reconcile planner for knowledge-base
folder items (Flight 3 Leg 1, DD-3).

``walk_folder`` is **stat-only**: it never opens a file's contents — the
10 MiB size cap and the binary sniff belong to Leg 2's indexer, because
``failed`` is reachable only from ``indexing`` in ``KB_ITEM_TRANSITIONS``
and a walk that tried to fail a freshly-discovered ``pending`` row would
need two transitions and an extra read per file per pass. Over-cap and
binary files with a supported extension become ``pending`` items the
indexer fails on its first pass; unsupported extensions are never items
at all (a by-design filter, not a failure).

``walk_folder`` is synchronous — the worker (Leg 3) runs it under
``asyncio.to_thread``. ``plan_reconcile`` is pure and unit-tested standalone:
it takes already-discovered files and already-loaded ``KBItem`` rows and
returns a classification, touching neither the database nor the
filesystem.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from the_one.db.models import KBItem

# Directory names skipped by construction, anywhere in the tree (in
# addition to any dot-prefixed name, which is skipped unconditionally).
SKIPPED_DIRS: frozenset[str] = frozenset({"node_modules", "__pycache__", "venv", "site-packages"})

_HASH_BLOCK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class DiscoveredFile:
    """One file found by :func:`walk_folder`. ``size_bytes``/``mtime`` come
    from ``entry.stat(follow_symlinks=False)`` at walk time."""

    path: str
    size_bytes: int
    mtime: float


@dataclass
class WalkResult:
    """The walk's output plus its skip counters (Leg 3 logs these per
    pass). See the module-level "Counter semantics" note in the leg spec:
    ``skipped_dirs``/``skipped_entries`` count only *conditional* skips
    (symlinked, unreadable, non-UTF-8 name, or ``SKIPPED_DIRS``) — dot-
    prefixed names and unsupported extensions are by-design filters and
    are never counted.
    """

    files: list[DiscoveredFile]
    skipped_dirs: int
    skipped_entries: int


def walk_folder(root: Path, *, extensions: frozenset[str]) -> WalkResult:
    """Iteratively walk ``root``, yielding (in the returned
    :class:`WalkResult`) every regular file whose lower-cased suffix is in
    ``extensions``.

    ``root`` is expected already canonical (the registration route
    resolves it). Raises ``NotADirectoryError`` if ``root`` does not exist
    or is not a directory. Skipped, never descended and never counted:
    dot-prefixed names (files or directories). Skipped and counted in
    ``skipped_dirs``/``skipped_entries``: anything under a
    ``SKIPPED_DIRS``-named directory, symlinked files, symlinked
    directories (not descended), names that cannot be encoded as UTF-8,
    an unreadable subdirectory (``PermissionError``/``FileNotFoundError``
    from ``scandir``), and a file that vanishes between ``scandir`` and
    ``stat``. Skipped and never counted (by design, not a condition):
    files with an unsupported suffix.

    Iterative (an explicit directory stack, no recursion) so an
    arbitrarily deep tree cannot raise ``RecursionError``. Opens no file —
    everything here is directory listing and ``stat``, never a ``read``.
    """
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    files: list[DiscoveredFile] = []
    skipped_dirs = 0
    skipped_entries = 0
    stack: list[str] = [str(root)]

    while stack:
        dirpath = stack.pop()
        try:
            entries = list(os.scandir(dirpath))
        except (PermissionError, FileNotFoundError):
            skipped_dirs += 1
            continue

        for entry in entries:
            name = entry.name
            if name.startswith("."):
                # By-design filter — never counted.
                continue

            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                # Before the dir/file split (design review, medium): a
                # non-UTF-8 *directory* name must never be pushed onto the
                # stack, or every path joined under it would itself be
                # unencodable.
                if _entry_is_dir_for_counting(entry, follow_symlinks=False):
                    skipped_dirs += 1
                else:
                    skipped_entries += 1
                continue

            if entry.is_symlink():
                # A symlinked directory counts in skipped_dirs, a
                # symlinked file in skipped_entries — determined by
                # following the link (a broken link counts as a file).
                if _entry_is_dir_for_counting(entry, follow_symlinks=True):
                    skipped_dirs += 1
                else:
                    skipped_entries += 1
                continue

            if entry.is_dir(follow_symlinks=False):
                if name in SKIPPED_DIRS:
                    skipped_dirs += 1
                    continue
                stack.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                suffix = os.path.splitext(name)[1].lower()
                if suffix not in extensions:
                    # By-design filter — never counted.
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    # Vanished between scandir and stat.
                    skipped_entries += 1
                    continue
                files.append(DiscoveredFile(entry.path, st.st_size, st.st_mtime))

    files.sort(key=lambda f: f.path)
    return WalkResult(files=files, skipped_dirs=skipped_dirs, skipped_entries=skipped_entries)


def _entry_is_dir_for_counting(entry: os.DirEntry, *, follow_symlinks: bool) -> bool:
    """Best-effort dir/file classification for a skip counter — an
    ``OSError`` (e.g. a broken symlink target) counts as a file, never
    raises."""
    try:
        return entry.is_dir(follow_symlinks=follow_symlinks)
    except OSError:
        return False


@dataclass
class ReconcilePlan:
    """The pure classification :func:`plan_reconcile` returns."""

    new: list[DiscoveredFile]
    removed: list[KBItem]
    changed: list[tuple[KBItem, DiscoveredFile]]
    unchanged: int


def plan_reconcile(
    discovered: Sequence[DiscoveredFile], existing: Sequence[KBItem]
) -> ReconcilePlan:
    """Pure: classify ``discovered`` files against ``existing`` items,
    keyed on the exact ``path_or_url`` string. Never touches the database
    or the filesystem.

    - ``new``: discovered paths with no existing item.
    - ``removed``: existing items whose path was not discovered.
    - ``changed``: existing items with a non-``None`` ``content_hash``
      whose ``size_bytes`` or ``mtime`` differs from the fresh stat — a
      candidate for a content check (the caller hashes the file and only
      requeues on an actual hash difference).
    - ``unchanged``: everything else, including items with no identity yet
      (``content_hash is None`` — still ``pending`` and will be indexed
      anyway, so a stat difference does not matter).
    """
    by_path = {item.path_or_url: item for item in existing}
    seen_paths: set[str] = set()
    new: list[DiscoveredFile] = []
    changed: list[tuple[KBItem, DiscoveredFile]] = []
    unchanged = 0

    for disc in discovered:
        seen_paths.add(disc.path)
        item = by_path.get(disc.path)
        if item is None:
            new.append(disc)
            continue
        if item.content_hash is not None and (
            item.size_bytes != disc.size_bytes or item.mtime != disc.mtime
        ):
            changed.append((item, disc))
        else:
            unchanged += 1

    removed = [item for item in existing if item.path_or_url not in seen_paths]
    return ReconcilePlan(new=new, removed=removed, changed=changed, unchanged=unchanged)


def content_hash(path: Path) -> str:
    """Lower-case hex sha256 of ``path``'s bytes, streamed in 1 MiB
    blocks — equal to ``hashlib.sha256(path.read_bytes()).hexdigest()``
    without materialising the whole file in memory."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(_HASH_BLOCK_SIZE)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def is_filesystem_root(path: Path) -> bool:
    """True for ``/`` (and ``C:\\`` on Windows: ``path.parent == path`` is
    the cross-platform test for "no parent left")."""
    return path.parent == path
