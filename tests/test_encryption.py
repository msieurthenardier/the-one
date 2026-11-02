"""Tests for the_one.encryption module."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from the_one.encryption import (
    Encryptor,
    _encryptor_cache,
    _write_key_atomic,
    get_encryptor,
    next_key_path,
    resolve_pending_key,
)


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

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    def test_key_file_permissions(self, tmp_path: Path) -> None:
        get_encryptor(tmp_path)
        key_path = tmp_path / "encryption.key"
        mode = stat.S_IMODE(os.stat(key_path).st_mode)
        assert mode == 0o600

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    def test_write_key_atomic_no_temp_file_left_behind(self, tmp_path: Path) -> None:
        """Squawk 0011: the O_CREAT|O_EXCL temp-file + os.replace pattern leaves
        no `.tmp.*` sibling behind and lands the canonical file at 0o600."""
        key_path = tmp_path / "encryption.key"
        _write_key_atomic(key_path, b"some-key-bytes")
        assert key_path.read_bytes() == b"some-key-bytes"
        assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
        leftovers = [p for p in tmp_path.iterdir() if p.name != "encryption.key"]
        assert leftovers == []

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

    def test_promotion_propagates_through_cache(self, tmp_path: Path) -> None:
        """A promoted key is installed in place: the cached instance sees the new key."""
        enc1 = get_encryptor(tmp_path)
        old_ciphertext = enc1.encrypt("before")
        new_key = Fernet.generate_key()
        enc1.stage_pending_key(new_key)
        enc1.promote_pending_key()

        enc2 = get_encryptor(tmp_path)
        assert enc1 is enc2
        # Encrypted under the new key, checked with an independent Fernet.
        ct = enc2.encrypt("post-rotation")
        assert Fernet(new_key).decrypt(ct.encode()) == b"post-rotation"
        with pytest.raises(InvalidToken):
            enc2.decrypt(old_ciphertext)
        # The key file holds the new key: a fresh instance agrees.
        _encryptor_cache.clear()
        assert get_encryptor(tmp_path).decrypt(ct) == "post-rotation"


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


class TestPendingKey:
    """Tests for the two-phase sidecar rotation-handoff primitives."""

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    def test_promoted_key_file_permissions(self, tmp_path: Path) -> None:
        """Squawk 0011: the promoted canonical key file lands at 0o600."""
        enc = get_encryptor(tmp_path)
        enc.stage_pending_key(Fernet.generate_key())
        enc.promote_pending_key()
        key_path = tmp_path / "encryption.key"
        assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600

    def test_stage_without_key_path_raises(self) -> None:
        enc = Encryptor(Fernet.generate_key())
        with pytest.raises(RuntimeError, match="no key_path set"):
            enc.stage_pending_key(Fernet.generate_key())

    def test_promote_without_key_path_raises(self) -> None:
        enc = Encryptor(Fernet.generate_key())
        with pytest.raises(RuntimeError, match="no key_path set"):
            enc.promote_pending_key(Fernet.generate_key())

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    def test_stage_writes_sidecar_at_0600(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        new_key = Fernet.generate_key()
        sidecar = enc.stage_pending_key(new_key)
        assert sidecar == next_key_path(tmp_path / "encryption.key")
        assert sidecar.read_bytes() == new_key
        assert stat.S_IMODE(os.stat(sidecar).st_mode) == 0o600
        assert enc.pending_key == new_key

    def test_get_encryptor_with_next_decrypts_both_encrypts_canonical(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        canonical_key = (tmp_path / "encryption.key").read_bytes()
        old_ciphertext = enc.encrypt("old-value")

        new_key = Fernet.generate_key()
        _write_key_atomic(next_key_path(tmp_path / "encryption.key"), new_key)
        _encryptor_cache.clear()

        enc2 = get_encryptor(tmp_path)
        assert enc2.pending_key == new_key
        # Decrypts ciphertext produced under either key.
        assert enc2.decrypt(old_ciphertext) == "old-value"
        assert enc2.decrypt(Encryptor(new_key).encrypt("new-value")) == "new-value"
        # Encrypts under the canonical key.
        new_ciphertext = enc2.encrypt("fresh")
        assert Fernet(canonical_key).decrypt(new_ciphertext.encode()) == b"fresh"

    def test_get_encryptor_without_next_behaves_as_today(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        assert enc.pending_key is None

    def test_promote_replaces_file_and_drops_fallback(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        old_ciphertext = enc.encrypt("before")
        key_path = tmp_path / "encryption.key"
        key_before = key_path.read_bytes()
        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)
        enc.promote_pending_key()

        assert key_path.read_bytes() == new_key
        assert new_key != key_before
        # Values encrypted under the new key decrypt in place.
        assert enc.decrypt(Encryptor(new_key).encrypt("x")) == "x"
        assert not next_key_path(key_path).exists()
        assert enc.pending_key is None
        with pytest.raises(InvalidToken):
            enc.decrypt(old_ciphertext)

    def test_discard_unlinks_and_drops_pending(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        canonical_key = (tmp_path / "encryption.key").read_bytes()
        old_ciphertext = enc.encrypt("kept")
        new_key = Fernet.generate_key()
        sidecar = enc.stage_pending_key(new_key)
        assert sidecar.exists()

        enc.discard_pending_key()
        assert not sidecar.exists()
        # The canonical key file is untouched and old ciphertext still decrypts.
        assert (tmp_path / "encryption.key").read_bytes() == canonical_key
        assert enc.decrypt(old_ciphertext) == "kept"
        assert enc.pending_key is None
        # Still encrypts/decrypts under the canonical key.
        assert enc.decrypt(enc.encrypt("still-works")) == "still-works"
        assert Fernet(canonical_key).decrypt(enc.encrypt("x").encode()) == b"x"

    def test_resolve_pending_key_promotes_when_sample_decrypts_under_pending(
        self, tmp_path: Path
    ) -> None:
        enc = get_encryptor(tmp_path)
        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)
        sample = Encryptor(new_key).encrypt("new-row")

        outcome = resolve_pending_key(enc, [sample])
        assert outcome == "promoted"
        assert enc.pending_key is None
        assert (tmp_path / "encryption.key").read_bytes() == new_key

    def test_resolve_pending_key_discards_when_only_canonical_decrypts(
        self, tmp_path: Path
    ) -> None:
        enc = get_encryptor(tmp_path)
        canonical_key = (tmp_path / "encryption.key").read_bytes()
        old_ciphertext = enc.encrypt("old-row")
        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)

        outcome = resolve_pending_key(enc, [old_ciphertext])
        assert outcome == "discarded"
        assert enc.pending_key is None
        assert (tmp_path / "encryption.key").read_bytes() == canonical_key
        assert not next_key_path(tmp_path / "encryption.key").exists()

    def test_resolve_pending_key_undecidable_promotes(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)

        outcome = resolve_pending_key(enc, [])
        assert outcome == "promoted"
        assert (tmp_path / "encryption.key").read_bytes() == new_key

    def test_resolve_pending_key_mixed_promotes_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        enc = get_encryptor(tmp_path)
        old_ciphertext = enc.encrypt("old-row")
        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)
        new_sample = Encryptor(new_key).encrypt("new-row")

        with caplog.at_level(logging.WARNING, logger="the_one.encryption"):
            outcome = resolve_pending_key(enc, [old_ciphertext, new_sample])
        assert outcome == "promoted"
        assert (tmp_path / "encryption.key").read_bytes() == new_key
        assert any(
            record.levelno == logging.WARNING
            and "1" in record.getMessage()
            and "CLI-window" in record.getMessage()
            and "unreadable after promotion" in record.getMessage()
            for record in caplog.records
        )

    def test_undecidable_promote_is_safe_because_sidecar_precedes_commit(
        self, tmp_path: Path
    ) -> None:
        """The undecidable->promote branch is not vulnerable to losing readable data.

        Residue-only samples (plaintext that decrypts under neither key) plus a
        pending key give resolve_pending_key nothing decidable, so it promotes.
        That's safe only because the sidecar is staged before the DB commit
        (rotate_encryption_key step 3b): nothing was re-encrypted under a key that
        promotion could strand. Prove it by round-tripping ciphertext written
        under the (now-canonical) key *after* promotion.
        """
        enc = get_encryptor(tmp_path)
        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)
        residue_sample = "{}"  # plaintext residue: decrypts under neither key

        outcome = resolve_pending_key(enc, [residue_sample])
        assert outcome == "promoted"
        assert (tmp_path / "encryption.key").read_bytes() == new_key

        # Data written after promotion round-trips cleanly — nothing readable was lost.
        post_promotion_ciphertext = enc.encrypt("written-after-promotion")
        assert enc.decrypt(post_promotion_ciphertext) == "written-after-promotion"

    def test_resolve_pending_key_absent_without_pending(self, tmp_path: Path) -> None:
        enc = get_encryptor(tmp_path)
        assert resolve_pending_key(enc, ["anything"]) == "absent"

    def test_write_key_atomic_leaves_no_tmp_on_write_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_write = os.write

        def failing_write(fd: int, data: bytes) -> int:
            raise OSError("disk full")

        monkeypatch.setattr("the_one.encryption.os.write", failing_write)
        key_path = tmp_path / "encryption.key"
        with pytest.raises(OSError, match="disk full"):
            _write_key_atomic(key_path, b"some-key-bytes")
        monkeypatch.setattr("the_one.encryption.os.write", real_write)
        assert not key_path.exists()
        leftovers = list(tmp_path.iterdir())
        assert leftovers == []

    def test_corrupt_sidecar_ignored_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        key_path = tmp_path / "encryption.key"
        sidecar = next_key_path(key_path)
        get_encryptor(tmp_path)  # creates the canonical key
        sidecar.write_bytes(b"not-a-valid-fernet-key")

        _encryptor_cache.clear()
        with caplog.at_level(logging.WARNING, logger="the_one.encryption"):
            enc = get_encryptor(tmp_path)
        assert enc.pending_key is None
        assert any("sidecar" in record.getMessage() for record in caplog.records)
        assert resolve_pending_key(enc, ["anything"]) == "absent"
