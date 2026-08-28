"""Fernet-based encryption for storing API credentials at rest."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from pathlib import Path

from cryptography.fernet import Fernet


def _write_key_atomic(path: Path, key: bytes) -> None:
    """Write *key* to *path* with no world-readable window, atomically.

    Mirrors `the_one/api_credential.py:_write_new_credential_atomic`: open a
    uniquely-named sibling temp file with `O_EXCL` and mode `0o600` in a
    single `os.open` call, write, fsync, close, then `os.replace` onto the
    canonical path.

    Do **not** "simplify" this to `path.write_bytes(...)` followed by
    `os.chmod(...)` — that sequence has a brief window where the file is
    world-readable before the chmod lands (squawk 0011 / GH #169).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp_path), str(path))


class Encryptor:
    """Encrypts and decrypts strings using a Fernet key."""

    def __init__(self, key: bytes, key_path: Path | None = None) -> None:
        self._fernet = Fernet(key)
        self._key = key
        self._key_path = key_path

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

    def install_key(self, new_key: bytes) -> None:
        """Replace the in-memory Fernet key without touching disk.

        Caller is responsible for ensuring the key file already reflects this key.
        """
        self._fernet = Fernet(new_key)
        self._key = new_key

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
        new_encryptor = Encryptor(new_key)

        # Let the caller re-encrypt all secrets. If this raises, the old key is preserved.
        reencrypt(self, new_encryptor)

        # Callback succeeded — persist the new key and update self.
        _write_key_atomic(self._key_path, new_key)
        self._fernet = Fernet(new_key)
        self._key = new_key


_encryptor_cache: dict[str, Encryptor] = {}


def get_encryptor(data_dir: Path) -> Encryptor:
    """Return an Encryptor backed by a key file in *data_dir*.

    The key file is auto-generated on first use and set to mode 0600.
    Results are cached by resolved *data_dir* — calling twice with the same
    path returns the same ``Encryptor`` instance.
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

    enc = Encryptor(key, key_path=key_path)
    _encryptor_cache[cache_key] = enc
    return enc
