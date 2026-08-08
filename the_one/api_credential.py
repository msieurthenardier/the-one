"""The long-lived, persisted local-API credential.

Mission 20 / Flight 1 / Leg 1 (`credential-foundation`) — DD1, DD2, DD8, DD9.

This module owns the credential *primitive* the whole flight rests on: its
shape, its exclusive-mode creation, its constant-time verification, the
identified-caller type a successful lookup yields, and the lookup seam a
second credential source can register against. It enforces nothing on any
request path — that is `gate-middleware`'s job, two legs from now.

**Do not confuse this credential with the one-time browser-handoff
credential** (DD12). That one is per-process, in-memory, single-use, and
belongs to `gate-middleware`. This module builds only the long-lived one
that persists across restarts.

Sibling to `the_one/encryption.py`, but note the file-creation pattern here
is deliberately *not* copied from that module — see `_write_new_credential_atomic`.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from the_one.config import settings

logger = logging.getLogger(__name__)

# The on-disk filename, sibling to `encryption.key` inside the resolved data
# directory (`the_one/config.py:Settings.data_dir`).
_CREDENTIAL_FILENAME = "api-credential"

# The type-distinguishing prefix (DD1). Whatever future admin/agent token
# types this flight's DD8 note anticipates would carry a different prefix,
# so a credential's type is legible at a glance without decoding anything.
CREDENTIAL_PREFIX = "loc"

# THIS ENCODING IS A COMPATIBILITY SURFACE the moment it is written to disk.
# Changing the prefix, separator, or byte lengths invalidates every
# already-persisted credential file in the field.
_SEPARATOR = "."
_IDENTIFIER_NBYTES = 8  # 16 hex chars
_SECRET_NBYTES = 32  # 64 hex chars


class CredentialFileError(RuntimeError):
    """The on-disk credential file exists but is not a valid credential.

    Raised rather than silently regenerated: an empty/truncated/malformed
    file is a real problem (e.g. a crash mid-write on a filesystem that
    doesn't honor fsync, or hand-editing), and silently replacing it would
    invalidate every live session without the operator knowing why.
    """


# ---------------------------------------------------------------------------
# Credential shape (DD1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class LocalApiCredential:
    """An opaque credential string, parsed into a public identifier and a
    secret: ``loc_<identifier>.<secret>``.

    The identifier is safe to log and is what a future revoke-by-identifier
    store would key on. The secret never is — `repr()` and `str()` reveal
    only the prefix and identifier. `repr=False` on the dataclass plus the
    explicit overrides below both exist so an unhandled exception's
    traceback (which calls `repr()` on locals) can never leak the secret.
    """

    identifier: str
    secret: str

    @classmethod
    def generate(cls) -> LocalApiCredential:
        """Generate a fresh credential. Uses `secrets`, never `random`."""
        return cls(
            identifier=secrets.token_hex(_IDENTIFIER_NBYTES),
            secret=secrets.token_hex(_SECRET_NBYTES),
        )

    @classmethod
    def parse(cls, token: str) -> LocalApiCredential | None:
        """Parse an opaque credential string.

        Returns ``None`` (never raises) on anything that doesn't match the
        shape — a malformed *presented* credential is just a failed lookup,
        not an exceptional condition.
        """
        prefix = f"{CREDENTIAL_PREFIX}_"
        if not token.startswith(prefix):
            return None
        identifier, sep, secret = token[len(prefix) :].partition(_SEPARATOR)
        if not sep or not identifier or not secret:
            return None
        return cls(identifier=identifier, secret=secret)

    def encode(self) -> str:
        """Return the opaque on-the-wire / on-disk string form."""
        return f"{CREDENTIAL_PREFIX}_{self.identifier}{_SEPARATOR}{self.secret}"

    def __repr__(self) -> str:
        return f"LocalApiCredential(identifier={self.identifier!r}, secret=<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()


# ---------------------------------------------------------------------------
# Identified caller (DD8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentifiedCaller:
    """A resolved caller identity. Nothing in this module returns a bare
    `True`/`False` for "is this caller authorized" — a successful lookup
    always yields one of these, naming both the caller and which
    `CredentialSource` resolved it (useful for logging, and what the
    second-source seam test asserts on)."""

    identifier: str
    source: str


# ---------------------------------------------------------------------------
# File creation and stat-guarded, cache-invalidating read (DD2, Cache Contract)
# ---------------------------------------------------------------------------


def credential_path() -> Path:
    """The canonical on-disk path of the long-lived local-API credential, in
    the resolved data directory (`Settings.data_dir`, `THE_ONE_DATA_DIR`-
    overridable)."""
    return settings.data_dir / _CREDENTIAL_FILENAME


def _write_new_credential_atomic(path: Path, credential: LocalApiCredential) -> None:
    """Write *credential* to *path* with no world-readable window, atomically.

    Mirrors the connector-key rotation sequence in
    `the_one/interfaces/web/api.py` (the connector-key rotation block): open
    a uniquely-named sibling temp file with `O_EXCL` and mode `0o600` in a
    single `os.open` call, write, fsync, close, then `os.replace` onto the
    canonical path.

    Do **not** "simplify" this to `path.write_bytes(...)` followed by
    `os.chmod(...)` — that sequence has a brief window where the file is
    world-readable before the chmod lands, which is exactly the anti-pattern
    `the_one/encryption.py` uses and this module deliberately does not copy
    (see that module's `rotate_key` / `get_encryptor`, kept as-is out of
    scope for this leg).

    Callers must not trust the value they just wrote — always re-read through
    `_read_credential_cached`, since a racing writer (e.g. a second process
    also creating on first launch) may have won last. `os.replace` is
    last-write-wins and raises nothing; no `FileExistsError` arises anywhere
    in this design, because `O_EXCL` only ever guards the uniquely-suffixed
    temp file, never the canonical path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, credential.encode().encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp_path), str(path))


@dataclass
class _CachedCredential:
    identifier: str
    secret: str
    mtime_ns: int
    size: int


# Process-local cache, keyed by the resolved credential path (`str(path)`).
#
# Keying by path — rather than a single module-level slot — is deliberate:
# `settings.data_dir` is operator-overridable (`THE_ONE_DATA_DIR`) and can
# change within a process's lifetime (e.g. a test suite, or any harness that
# points at more than one data directory in sequence). A single unkeyed slot
# holding (identifier, secret, mtime_ns, size) has no record of *which* file
# it came from, so a data_dir swap followed by a read can be served the
# previous directory's credential whenever the new file's st_mtime_ns and
# st_size both happen to match the cached values — and st_size is a no-op
# guard for this fixed-length format, so the entire guard would rest on an
# st_mtime_ns collision between two distinct files. Unlikely on ext4, more
# likely on coarse-granularity filesystems (removable volumes are reachable
# here). Keying by path means a data_dir swap invalidates on its own: the
# previous directory's entry simply sits under a different key and is never
# consulted again — no caller has to remember to reset this cache for
# correctness. (Do not copy `encryption.py`'s `_encryptor_cache`, which
# *is* keyed by data_dir but has no invalidation at all — wrong for a
# credential that can also be rotated by a separate process.)
_cache: dict[str, _CachedCredential] = {}


def _warn_if_unsafe_permissions(path: Path, st: os.stat_result) -> None:
    """Log a warning (never raise) if the credential file's mode has drifted
    from 0600 — e.g. restored from a backup, or copied by a tool that
    widened the mode. This is a security finding, not a formatting nit, but
    refusing outright would risk bricking a reader over a fixable mistake.

    POSIX only: Windows synthesizes `st_mode` from a single read-only bit and
    does not model owner/group/other, so this check is meaningless there.
    """
    if os.name != "posix":
        return
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        logger.warning(
            "Credential file %s has mode %o, expected 0600 — it may be "
            "readable by other users on this machine. Run "
            "`the-one rotate-api-credential` to replace it with correctly "
            "scoped permissions.",
            path,
            mode,
        )


def _read_credential_cached(path: Path) -> LocalApiCredential:
    """Read the credential at *path*, rebuilding this path's cache entry only
    when the file's identity has changed since the last read.

    Raises `FileNotFoundError` (uncaught) if *path* does not exist — callers
    that must tolerate an absent file (the read-only lookup path,
    `lookup_credential`) catch that themselves rather than have this
    function silently return `None`, so that a caller which legitimately
    expects the file to exist still gets a loud failure.

    Cache Contract (see the leg artifact for the full rationale):
    - Source of truth is the file on disk.
    - Keyed by `str(path)` (see the `_cache` module comment) — a data_dir
      swap invalidates on its own, with no explicit reset required.
    - Rebuild trigger is exactly one: `st_mtime_ns` OR `st_size` differing
      from the cached values, compared with `!=`, never `>`. `st_mtime_ns`
      is wall-clock, not monotonic — a `>` comparison would silently defeat
      the guard for one request after a backward clock step, which is
      precisely the request the "maximum one request" staleness bound
      exists to cover. `size` is a no-op for this fixed-length format (every
      rotation produces a byte-identical size); it is included only as
      defense in depth against a future variable-length format, not as a
      second independent leg of the guard — `st_mtime_ns` carries the whole
      thing, including on coarse-granularity filesystems (reachable here
      since `THE_ONE_DATA_DIR` may point at a removable volume).
    - Maximum staleness is one request/call: the next read after an
      out-of-process rotation (which changes both mtime and inode via
      `os.replace`) always rebuilds.
    """
    key = str(path)
    st = path.stat()
    cached = _cache.get(key)
    if cached is None or cached.mtime_ns != st.st_mtime_ns or cached.size != st.st_size:
        _warn_if_unsafe_permissions(path, st)
        raw = path.read_text(encoding="ascii").strip()
        parsed = LocalApiCredential.parse(raw) if raw else None
        if parsed is None:
            raise CredentialFileError(
                f"Credential file at {path} is empty or malformed. "
                "Run `the-one rotate-api-credential` to replace it."
            )
        cached = _CachedCredential(
            identifier=parsed.identifier,
            secret=parsed.secret,
            mtime_ns=st.st_mtime_ns,
            size=st.st_size,
        )
        _cache[key] = cached
    return LocalApiCredential(identifier=cached.identifier, secret=cached.secret)


def get_credential() -> LocalApiCredential:
    """Return the current credential, creating it on first use.

    This is the **create-on-first-use** entry point. It calls
    `settings.ensure_dirs()` (a legacy-migration guard plus a `mkdir`
    syscall) and will create a credential file when none exists. Use it only
    from callers that legitimately need to *create* a credential: the CLI
    rotate subcommand's "no credential yet" branch, and the launcher/harness
    callers that arrive in later legs (`operational-callers`).

    Do **not** call this from a request-handling / lookup path —
    `gate-middleware` calls the lookup seam inline on every request (per DD6,
    including every static asset), and per-request `ensure_dirs()` calls plus
    a possible file creation on the hot path is exactly the cost that design
    smell would impose. Request-path lookups go through `resolve_caller`,
    whose `FileCredentialSource` uses `lookup_credential` (read-only, below)
    instead of this function.

    On first use in a data directory with no credential file, the file is
    created (mode 0600, no world-readable window — see
    `_write_new_credential_atomic`) before being read back. The read always
    goes through the same stat-guarded path as any other reader, so a
    concurrent creator's winning write (see the module-level race note) is
    what gets returned, not a stale in-memory copy of what this call itself
    wrote.
    """
    settings.ensure_dirs()
    path = credential_path()
    if not path.exists():
        _write_new_credential_atomic(path, LocalApiCredential.generate())
    return _read_credential_cached(path)


def lookup_credential() -> LocalApiCredential | None:
    """Read-only lookup of the current credential. Returns `None` if no
    credential file exists — never creates one.

    This is the **lookup** entry point, deliberately separate from
    `get_credential()`: unlike that function, this one does NOT call
    `settings.ensure_dirs()` and does NOT create the credential file when
    absent. It exists for `FileCredentialSource.resolve()`, which
    `gate-middleware` will call inline on every request (per DD6, including
    every static asset) — a lookup having the side effect of creating the
    thing it's looking up is a design smell on its own, and at request-path
    call volume the `ensure_dirs()` legacy-migration check plus a `mkdir`
    syscall on every hit is a real cost, not just a smell.

    An absent credential file on this path most likely means misconfiguration
    (nothing has ever called `get_credential()` to create one — e.g. the
    launcher/CLI paths that do that haven't run yet). Silently returning
    `None` for "no caller resolved" is the right behavior for a lookup — it
    must not raise just because no credential exists yet — but going quiet
    about *why* would make that misconfiguration invisible, so this logs a
    warning naming the expected path. A malformed/empty *existing* file is a
    different, louder problem and is NOT swallowed here: `CredentialFileError`
    from `_read_credential_cached` propagates uncaught, exactly as it does
    from `get_credential()`.
    """
    path = credential_path()
    try:
        return _read_credential_cached(path)
    except FileNotFoundError:
        logger.warning(
            "Local API credential file %s does not exist; no caller can "
            "resolve against it yet. If this is unexpected, a "
            "create-on-first-use caller (e.g. `the-one rotate-api-credential`) "
            "should have created it already.",
            path,
        )
        return None


def rotate_credential() -> LocalApiCredential:
    """Atomically replace the persisted credential with a freshly generated
    one and return it (secret included).

    Callers that surface anything to a terminal (the CLI rotate subcommand)
    must not print the returned secret — see `the_one.main.cli_entry`.
    Reuses `_write_new_credential_atomic`, so rotation inherits the same
    atomicity: an interrupted rotate leaves the previous credential file
    intact (the write lands on a temp file first; `os.replace` is the only
    step that touches the canonical path, and it's a single filesystem
    syscall).
    """
    settings.ensure_dirs()
    path = credential_path()
    _write_new_credential_atomic(path, LocalApiCredential.generate())
    return _read_credential_cached(path)


# ---------------------------------------------------------------------------
# Lookup seam (DD8)
# ---------------------------------------------------------------------------


class CredentialSource(Protocol):
    """Structural protocol (per this codebase's `structural-Protocol-
    satisfaction` convention) for a caller-identity source the lookup seam
    can walk.

    Deliberately narrow — "does this presented string resolve to a caller
    you own?" and nothing else. Held to exactly this shape per DD8's
    warning against "speculative generality at one implementation": no
    scopes, no expiry policy, no registry API richer than register-and-
    resolve.
    """

    name: str

    def resolve(self, presented: str) -> IdentifiedCaller | None: ...


class FileCredentialSource:
    """Resolves against the long-lived, file-backed credential (DD2).

    Registered by default and first in `_sources`.
    """

    name = "file"

    def resolve(self, presented: str) -> IdentifiedCaller | None:
        parsed = LocalApiCredential.parse(presented)
        if parsed is None:
            return None
        # Read-only lookup (see `lookup_credential`) — this is the entry
        # point `gate-middleware` will call inline on every request, and it
        # must not create a credential file or call `settings.ensure_dirs()`
        # as a side effect of looking one up.
        stored = lookup_credential()
        if stored is None:
            return None
        if parsed.identifier != stored.identifier:
            return None
        # Constant-time comparison — a later refactor to `==` here would
        # reopen a timing side-channel on the secret. Pinned by
        # tests/test_api_credential.py, which asserts this primitive is
        # actually called rather than merely inspecting the result.
        if not hmac.compare_digest(parsed.secret, stored.secret):
            return None
        return IdentifiedCaller(identifier=stored.identifier, source=self.name)


_sources: list[CredentialSource] = [FileCredentialSource()]


def register_source(source: CredentialSource) -> None:
    """Register an additional credential source, checked after those already
    registered. This is the whole seam API surface: register, then resolve
    through the single entry point below — no per-source branching anywhere
    else in this module or its callers."""
    _sources.append(source)


def resolve_caller(presented: str) -> IdentifiedCaller | None:
    """Synchronous lookup entry point (DD8). Walks registered sources in
    order and returns the first identified caller, or `None` if none
    resolve.

    Synchronous is deliberate, settled here rather than left to
    `gate-middleware`: that leg's ASGI handler will call this inline on
    every request, and a `stat` plus an occasional read is sub-millisecond
    on local disk — not worth an executor hop.
    """
    for source in _sources:
        caller = source.resolve(presented)
        if caller is not None:
            return caller
    return None
