"""Tests for the_one.encryption module."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

from the_one.encryption import Encryptor, _encryptor_cache, get_encryptor


@pytest.fixture(autouse=True)
def _clear_encryptor_cache():
    """Ensure each test starts with a clean encryptor cache."""
    _encryptor_cache.clear()
    yield
    _encryptor_cache.clear()


class TestGetEncryptor:
    """Tests for key file management via get_encryptor."""

    def test_creates_key_file(self, tmp_path: Path) -> None:
        get_encryptor(tmp_path)
        key_path = tmp_path / "encryption.key"
        assert key_path.exists()

    def test_key_file_permissions(self, tmp_path: Path) -> None:
        get_encryptor(tmp_path)
        key_path = tmp_path / "encryption.key"
        mode = stat.S_IMODE(os.stat(key_path).st_mode)
        assert mode == 0o600

    def test_reuses_existing_key_file(self, tmp_path: Path) -> None:
        enc1 = get_encryptor(tmp_path)
        enc2 = get_encryptor(tmp_path)
        # Both encryptors should use the same key — one can decrypt the other's output.
        plaintext = "reuse-check"
        assert enc2.decrypt(enc1.encrypt(plaintext)) == plaintext

    def test_key_file_not_recreated(self, tmp_path: Path) -> None:
        get_encryptor(tmp_path)
        key_path = tmp_path / "encryption.key"
        key_bytes = key_path.read_bytes()
        get_encryptor(tmp_path)
        assert key_path.read_bytes() == key_bytes

    def test_caches_by_data_dir(self, tmp_path: Path) -> None:
        """Calling get_encryptor twice with the same path returns the same instance."""
        enc1 = get_encryptor(tmp_path)
        enc2 = get_encryptor(tmp_path)
        assert enc1 is enc2

    def test_different_dirs_get_different_instances(self, tmp_path: Path) -> None:
        """Different data_dir paths should produce separate Encryptor instances."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        enc_a = get_encryptor(dir_a)
        enc_b = get_encryptor(dir_b)
        assert enc_a is not enc_b

    def test_rotation_propagates_through_cache(self, tmp_path: Path) -> None:
        """rotate_key() mutates in-place, so the cached instance sees the new key."""
        enc1 = get_encryptor(tmp_path)
        enc1.rotate_key(lambda old, new: None)
        enc2 = get_encryptor(tmp_path)
        assert enc1 is enc2
        # The rotated encryptor can encrypt/decrypt with the new key
        ct = enc2.encrypt("post-rotation")
        assert enc1.decrypt(ct) == "post-rotation"


class TestEncryptDecrypt:
    """Tests for encrypt/decrypt round-trip."""

    def test_round_trip(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        plaintext = "sk-secret-key-12345"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_encrypt_produces_different_output(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        plaintext = "same-value"
        # Fernet includes a timestamp, so two encryptions differ.
        assert enc.encrypt(plaintext) != enc.encrypt(plaintext)

    def test_unicode_round_trip(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        plaintext = "clave-secreta-\u00e9\u00e8\u00ea"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext


class TestEncryptOptional:
    """Tests for encrypt_optional / decrypt_optional pass-through."""

    def test_encrypt_optional_none(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        assert enc.encrypt_optional(None) is None

    def test_encrypt_optional_empty(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        assert enc.encrypt_optional("") == ""

    def test_decrypt_optional_none(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        assert enc.decrypt_optional(None) is None

    def test_decrypt_optional_empty(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        assert enc.decrypt_optional("") == ""

    def test_encrypt_optional_round_trip(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        plaintext = "optional-secret"
        encrypted = enc.encrypt_optional(plaintext)
        assert encrypted is not None
        assert enc.decrypt_optional(encrypted) == plaintext


class TestKeyRotation:
    """Tests for Encryptor.rotate_key."""

    def test_rotation_generates_different_key(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        key_before = (tmp_path / "encryption.key").read_bytes()
        enc.rotate_key(lambda old, new: None)
        key_after = (tmp_path / "encryption.key").read_bytes()
        assert key_before != key_after

    def test_rotation_calls_callback(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        called_with: list[tuple[Encryptor, Encryptor]] = []
        enc.rotate_key(lambda old, new: called_with.append((old, new)))
        assert len(called_with) == 1
        old_enc, new_enc = called_with[0]
        assert isinstance(old_enc, Encryptor)
        assert isinstance(new_enc, Encryptor)

    def test_new_encryptor_decrypts_new_values(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        new_encrypted: list[str] = []

        def reencrypt(old: Encryptor, new: Encryptor) -> None:
            new_encrypted.append(new.encrypt("rotated-secret"))

        enc.rotate_key(reencrypt)
        # After rotation, the encryptor uses the new key.
        assert enc.decrypt(new_encrypted[0]) == "rotated-secret"

    def test_old_values_fail_after_rotation(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        old_ciphertext = enc.encrypt("before-rotation")
        enc.rotate_key(lambda old, new: None)
        with pytest.raises(InvalidToken):
            enc.decrypt(old_ciphertext)

    def test_rotation_preserves_key_on_callback_failure(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        key_before = (tmp_path / "encryption.key").read_bytes()

        def failing_callback(old: Encryptor, new: Encryptor) -> None:
            raise ValueError("re-encryption failed")

        with pytest.raises(ValueError, match="re-encryption failed"):
            enc.rotate_key(failing_callback)

        # Key file should be unchanged.
        assert (tmp_path / "encryption.key").read_bytes() == key_before

    def test_rotation_without_key_path_raises(self) -> None:
        from cryptography.fernet import Fernet

        enc = Encryptor(Fernet.generate_key())
        with pytest.raises(RuntimeError, match="no key_path set"):
            enc.rotate_key(lambda old, new: None)
