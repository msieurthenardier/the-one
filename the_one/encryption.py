"""Fernet-based encryption for storing API credentials at rest."""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger(__name__)


def _write_key_atomic(path: Path, key: bytes) -> None:
    """Write *key* to *path* with no world-readable window, atomically.

    Mirrors `the_one/api_credential.py:_write_new_credential_atomic`: open a
    uniquely-named sibling temp file with `O_EXCL` and mode `0o600` in a
    single `os.open` call, write, fsync, close, then `os.replace` onto the
    canonical path.

    Do **not** "simplify" this to `path.write_bytes(...)` followed by
    `os.chmod(...)` — that sequence has a brief window where the file is
    world-readable before the chmod lands (squawk 0011 / GH #169).

    If any step of the write/fsync/close/replace sequence raises, the
    partial temp file is unlinked before the exception propagates — a
    failed staging write must never leave a `.tmp.*` sibling behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    try:
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, key)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(path))
    except BaseException:
        try:
            os.unlink(str(tmp_path))
        except OSError:
            pass
        raise


def next_key_path(key_path: Path) -> Path:
    """Return the sidecar path used to stage a pending key rotation."""
    return key_path.with_name(key_path.name + ".next")


class Encryptor:
    """Encrypts and decrypts strings using a Fernet key.

    Supports a two-phase rotation handoff: while a *pending* key is staged
    (via `stage_pending_key`), the encryptor still *encrypts* under the
    canonical key but *decrypts* under either key (`MultiFernet`, canonical
    first). This lets in-flight reads succeed across the window between a
    DB commit under the new key and the on-disk key file promotion.
    """

    def __init__(
        self,
        key: bytes,
        key_path: Path | None = None,
        pending_key: bytes | None = None,
    ) -> None:
        self._key = key
        self._key_path = key_path
        self._pending_key = pending_key
        self._rebuild()

    def _rebuild(self) -> None:
        if self._pending_key is None:
            self._fernet = Fernet(self._key)
        else:
            # Canonical first: encrypt() always uses the first Fernet in a
            # MultiFernet; decrypt() tries each in order.
            self._fernet = MultiFernet([Fernet(self._key), Fernet(self._pending_key)])

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string, returning a Fernet-encrypted base64 string."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet-encrypted base64 string, returning the original plaintext."""
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def encrypt_optional(self, value: str | None) -> str | None:
        """Encrypt a value, passing through None and empty strings unchanged."""
        if not value:
            return value
        return self.encrypt(value)

    def decrypt_optional(self, value: str | None) -> str | None:
        """Decrypt a value, passing through None and empty strings unchanged."""
        if not value:
            return value
        return self.decrypt(value)

    @property
    def key_path(self) -> Path | None:
        """Return the on-disk key file path, or None if this Encryptor is not file-backed."""
        return self._key_path

    @property
    def pending_key(self) -> bytes | None:
        """Return the staged-but-not-yet-promoted key, or None if none is pending."""
        return self._pending_key

    def key_for(self, ciphertext: str) -> Literal["pending", "canonical"] | None:
        """Classify which key decrypts *ciphertext*.

        Tries the pending key only when one is set, then the canonical key.
        Returns None if neither decrypts — never raises for a missing
        pending key or an undecryptable ciphertext.
        """
        if self._pending_key is not None:
            try:
                Fernet(self._pending_key).decrypt(ciphertext.encode())
                return "pending"
            except InvalidToken:
                pass
        try:
            Fernet(self._key).decrypt(ciphertext.encode())
            return "canonical"
        except InvalidToken:
            return None

    def install_key(self, new_key: bytes) -> None:
        """Replace the in-memory Fernet key without touching disk.

        Caller is responsible for ensuring the key file already reflects this key.
        Clears any pending key.
        """
        self._key = new_key
        self._pending_key = None
        self._rebuild()

    def stage_pending_key(self, new_key: bytes) -> Path:
        """Write *new_key* to the `.next` sidecar and start decrypting under it too.

        Raises:
            RuntimeError: If this Encryptor was not created with a key_path.
        """
        if self._key_path is None:
            raise RuntimeError(
                "Cannot stage a pending key: no key_path set. "
                "Use get_encryptor() to create an Encryptor with a managed key file."
            )
        sidecar = next_key_path(self._key_path)
        _write_key_atomic(sidecar, new_key)
        self._pending_key = new_key
        self._rebuild()
        return sidecar

    def promote_pending_key(self, key: bytes | None = None) -> None:
        """Promote the staged sidecar to the canonical key file and install it in memory.

        Args:
            key: The key to promote. Defaults to the currently pending key.
                An explicit argument is required when the caller has already
                called `install_key` (which clears the in-memory pending
                key) before promoting on disk — the route does this so the
                in-memory encryptor matches the just-committed DB state
                before the disk write is attempted.

        Raises:
            RuntimeError: If neither *key* nor a pending key is available.
            OSError: Propagated from the `os.replace` promotion — the
                caller decides how to handle a failed promotion.
        """
        if key is None:
            key = self._pending_key
        if key is None:
            raise RuntimeError("No pending key to promote and none was provided.")
        if self._key_path is None:
            raise RuntimeError(
                "Cannot promote a pending key: no key_path set. "
                "Use get_encryptor() to create an Encryptor with a managed key file."
            )
        sidecar = next_key_path(self._key_path)
        os.replace(str(sidecar), str(self._key_path))
        self.install_key(key)

    def discard_pending_key(self) -> None:
        """Unlink the staged sidecar (if present) and stop decrypting under it."""
        if self._key_path is not None:
            sidecar = next_key_path(self._key_path)
            sidecar.unlink(missing_ok=True)
        self._pending_key = None
        self._rebuild()

    def rotate_key(self, reencrypt: Callable[[Encryptor, Encryptor], None]) -> None:
        """Generate a new key, re-encrypt secrets via callback, then persist the new key.

        Args:
            reencrypt: Called with (old_encryptor, new_encryptor). The caller is
                responsible for re-encrypting all stored secrets inside this callback.

        Raises:
            RuntimeError: If this Encryptor was not created with a key_path
                (e.g. a test-only instance created directly).
        """
        if self._key_path is None:
            raise RuntimeError(
                "Cannot rotate key: no key_path set. "
                "Use get_encryptor() to create an Encryptor with a managed key file."
            )

        new_key = Fernet.generate_key()
        self.stage_pending_key(new_key)

        try:
            # Let the caller re-encrypt all secrets. While staged, self
            # decrypts under both keys — harmless for the callback contract.
            reencrypt(self, Encryptor(new_key))
        except BaseException:
            self.discard_pending_key()
            raise

        # Callback succeeded — promote the sidecar and install the new key.
        self.promote_pending_key()


def resolve_pending_key(
    encryptor: Encryptor, samples: Iterable[str]
) -> Literal["absent", "promoted", "discarded"]:
    """Decide the fate of *encryptor*'s pending key given sampled ciphertexts.

    This is the reconcile's effector, not a pure classifier: the promote and
    discard branches perform the corresponding mutation on *encryptor*
    before returning.

    Returns:
        "absent": no pending key was set; nothing was sampled or mutated.
        "promoted": at least one sample decrypted under the pending key
            (or nothing was decidable), so the pending key was promoted.
        "discarded": no sample decrypted under the pending key but at
            least one decrypted under the canonical key, so the pending
            key was discarded.
    """
    if encryptor.pending_key is None:
        return "absent"

    under_pending = 0
    under_canonical_only = 0
    for sample in samples:
        classification = encryptor.key_for(sample)
        if classification == "pending":
            under_pending += 1
        elif classification == "canonical":
            under_canonical_only += 1

    if under_pending > 0:
        encryptor.promote_pending_key()
        if under_canonical_only > 0:
            logger.warning(
                "encryption key reconcile: promoted pending key; %d sample(s) were "
                "still encrypted under the canonical key at promotion time "
                "(rows written during the crash window, if any, may need re-encrypting)",
                under_canonical_only,
            )
        logger.info(
            "encryption key reconcile: promoted (under_pending=%d, under_canonical_only=%d)",
            under_pending,
            under_canonical_only,
        )
        return "promoted"

    if under_canonical_only > 0:
        encryptor.discard_pending_key()
        logger.info(
            "encryption key reconcile: discarded (under_pending=0, under_canonical_only=%d)",
            under_canonical_only,
        )
        return "discarded"

    # Nothing decidable (no encrypted rows, or only plaintext residue) — promote.
    encryptor.promote_pending_key()
    logger.info("encryption key reconcile: promoted (nothing decidable)")
    return "promoted"


_encryptor_cache: dict[str, Encryptor] = {}


def get_encryptor(data_dir: Path) -> Encryptor:
    """Return an Encryptor backed by a key file in *data_dir*.

    The key file is auto-generated on first use and set to mode 0600.
    Results are cached by resolved *data_dir* — calling twice with the same
    path returns the same ``Encryptor`` instance.

    If a leftover `<key_path>.next` sidecar exists from an interrupted
    rotation, it is loaded as the pending key so reads never fail before
    the startup reconcile runs. A sidecar that fails to parse as a valid
    Fernet key is logged and ignored (the reconcile then sees no pending
    key and the corrupt file is left for the operator).
    """
    cache_key = str(data_dir.resolve())
    if cache_key in _encryptor_cache:
        return _encryptor_cache[cache_key]

    key_path = data_dir / "encryption.key"

    if key_path.exists():
        key = key_path.read_bytes()
    else:
        key = Fernet.generate_key()
        _write_key_atomic(key_path, key)

    pending: bytes | None = None
    sidecar = next_key_path(key_path)
    if sidecar.exists():
        candidate = sidecar.read_bytes()
        try:
            Fernet(candidate)
        except ValueError:
            logger.warning(
                "encryption key sidecar at %s is not a valid key; ignoring it (canonical key only)",
                sidecar,
            )
        else:
            pending = candidate

    enc = Encryptor(key, key_path=key_path, pending_key=pending)
    _encryptor_cache[cache_key] = enc
    return enc
