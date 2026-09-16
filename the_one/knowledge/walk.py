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
from pathlib import Path, PurePath

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


def is_hidden_name(name: str) -> bool:
    """True for a dot-prefixed name (``.git``, ``.hidden``). Extracted from
    ``walk_folder``'s inline check (Flight 4 Leg 1, DD-2) so the watcher's
    ``is_watch_candidate`` can apply the identical rule — used at exactly
    ``walk_folder``'s existing site, replacing only the boolean expression
    there; the by-design, uncounted-skip semantics of ``WalkResult`` are
    unchanged."""
    return name.startswith(".")


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
            if is_hidden_name(name):
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


def is_watch_candidate(
    path: str,
    *,
    root: Path,
    extensions: frozenset[str],
    excluded_roots: tuple[Path, ...],
) -> bool:
    """The watcher-side composite predicate (Flight 4 Leg 1, DD-2): a
    *trigger* filter, never a subscription filter — it decides whether an
    event's path should cause a ``request_index``, not what the native
    notifier watches. **Never raises.** All string and ``PurePath`` work —
    no ``stat``, no ``resolve``: ``root`` is expected already canonical
    (registration canonicalises it) and ``watchfiles`` reports paths as the
    subscribed root plus a relative part.

    Clause order (Architect-reviewed; do not reorder):

    1. ``path`` equals ``root`` itself, compared as
       ``PurePath(os.path.normcase(path)) == PurePath(os.path.normcase(str(root)))``
       — never a raw string compare, which a trailing or doubled separator
       would defeat, and never ``==`` on the raw strings, which a
       drive-letter case difference or a ``\\\\?\\`` prefix would defeat on
       Windows. Always **True** — the root's own deletion must reach the
       watcher even when the root's name carries a dotted suffix (e.g.
       ``notes.d``).
    2. Relativise ``path`` against ``root`` with the same normalisation,
       inside a ``try``: a ``ValueError`` (a path outside ``root`` — macOS
       reporting ``/private/var…`` for ``/var…``, a Windows drive-letter
       case difference, any future backend) returns **False** rather than
       propagating out of the generator and killing the subscription.
    3. Any relative path component that :func:`is_hidden_name` or is in
       :data:`SKIPPED_DIRS` → **False**. (Two recorded, latency-only
       divergences from :func:`walk_folder`: a directory rename or removal
       emits only directory-level events, so renaming or deleting a
       directory whose *name* carries an unsupported suffix produces no
       trigger until the periodic reconcile walk; and this clause tests
       ``normcase``\\ d components, so ``SKIPPED_DIRS`` matching is
       case-insensitive on Windows where the walk's is case-sensitive. The
       walk remains correctness in both cases — this predicate only ever
       decides whether an event *triggers* a pass.)
    4. The path under any of ``excluded_roots`` (``PurePath.is_relative_to``,
       also normalised) → **False** — the app's own data directory (and its
       database, WAL and vector sidecar) must never feed indexing writes
       back into the watcher as a new pass.
    5. The final path component's suffix, ``os.path.splitext`` **lower-cased**
       (``NOTES.MD`` is an ordinary filename on Windows and macOS) —
       outside ``extensions`` → **False**. A final component **without** a
       suffix → **True** (it may be a directory being created or removed;
       the walk is the one that finds out).
    """
    if not path:
        return False

    try:
        normalized_path = PurePath(os.path.normcase(path))
        normalized_root = PurePath(os.path.normcase(str(root)))
    except (TypeError, ValueError):
        return False

    if normalized_path == normalized_root:
        return True

    try:
        relative = normalized_path.relative_to(normalized_root)
    except ValueError:
        return False

    for part in relative.parts:
        if is_hidden_name(part) or part in SKIPPED_DIRS:
            return False

    for excluded in excluded_roots:
        normalized_excluded = PurePath(os.path.normcase(str(excluded)))
        if normalized_path.is_relative_to(normalized_excluded):
            return False

    suffix = os.path.splitext(str(normalized_path))[1].lower()
    if not suffix:
        return True
    return suffix in extensions


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
