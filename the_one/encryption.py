"""Fernet-based encryption for storing API credentials at rest."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from cryptography.fernet import Fernet


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
        self._key_path.write_bytes(new_key)
        os.chmod(self._key_path, 0o600)
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
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)

    enc = Encryptor(key, key_path=key_path)
    _encryptor_cache[cache_key] = enc
    return enc
