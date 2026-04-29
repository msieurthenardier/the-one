"""Path helpers — cross-platform contract.

Provides canonicalization and containment checks that abstract OS-specific
quirks (UNC paths, drive-letter casing on Windows, symlink resolution on POSIX).
The contract is identical on every supported platform; the implementation may
diverge internally as Windows/macOS support lands in future missions.

Helpers:
    canonicalize(path) — expanduser + resolve; accepts str or Path.
    safe_resolve(path) — same as canonicalize today; documents the
        symlink-resolution contract that F3's path-scope check relies on.
    is_within(path, root) — bool; canonicalizes both inputs internally so
        callers cannot bypass containment checks with un-resolved input.

Edge cases:
    - canonicalize() of a non-existent path succeeds (Path.resolve has
      strict=False by default since Python 3.6). F3 will add explicit
      existence checks where required.
    - is_within compares fully-resolved paths; symlinks pointing outside
      root will be detected as outside (which is the desired behavior for
      security-sensitive callers).
"""

from __future__ import annotations

from pathlib import Path


def canonicalize(path: str | Path) -> Path:
    """Return the fully-canonicalized absolute path.

    Equivalent to ``Path(path).expanduser().resolve()``. Accepts a string or
    Path. The helper exists so a single site can absorb future Windows-specific
    quirks (UNC paths, drive-letter casing) without touching every caller.

    Note: ``Path.resolve`` with the default ``strict=False`` succeeds even if
    the target does not exist. Callers that require existence must check
    separately.
    """
    return Path(path).expanduser().resolve()


def safe_resolve(path: str | Path) -> Path:
    """Resolve symlinks for security-sensitive comparisons.

    Equivalent to ``canonicalize`` on this platform but documents the contract
    explicitly: the result has all symlinks resolved so callers can compare it
    against an allowlisted scope. F3's symlink-escape detection compares
    ``safe_resolve(target)`` against the configured path scope.
    """
    return Path(path).expanduser().resolve()


def is_within(path: str | Path, root: str | Path) -> bool:
    """Return True if ``path`` is ``root`` or a descendant of ``root``.

    Both arguments are canonicalized internally (``expanduser().resolve()``)
    before comparison — this is a deliberate choice so F3's path-scope check
    cannot be bypassed by passing an un-resolved input. Accepts ``str`` or
    ``Path`` for both arguments.

    Forward-reference: F3 may upgrade this to return a richer result
    (e.g., ``WITHIN | OUTSIDE | SYMLINK_ESCAPE``); for now a bool is sufficient.
    """
    canonical_path = canonicalize(path)
    canonical_root = canonicalize(root)
    try:
        canonical_path.relative_to(canonical_root)
        return True
    except ValueError:
        return False
