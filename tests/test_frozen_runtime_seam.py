"""Tests for the M15 F5 L1 frozen-runtime seam in ``the_one.platform.env``.

Covers ``is_frozen``/``_bundle_dir``, ``clean_subprocess_env`` (strip +
augment), ``strip_bundle_dir_from_path``, and the loader-var allowlist
invariant. Frozen state is simulated with ``monkeypatch.setattr`` on ``sys``.
"""

from __future__ import annotations

import os

import pytest

from the_one.platform import env as env_mod
from the_one.platform.env import (
    _ENV_ALLOWLIST,
    _EXTRA_PATH_ENV,
    _WINDOWS_ENV_ALLOWLIST,
    _build_subprocess_env,
    clean_subprocess_env,
    is_frozen,
    strip_bundle_dir_from_path,
)


def _freeze(monkeypatch: pytest.MonkeyPatch, bundle: str = "/bundle") -> None:
    """Simulate a PyInstaller-frozen process with ``_MEIPASS=bundle``."""
    monkeypatch.setattr(env_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(env_mod.sys, "_MEIPASS", bundle, raising=False)


class TestIsFrozen:
    def test_false_on_normal_interpreter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        assert is_frozen() is False

    def test_true_when_meipass_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch)
        assert is_frozen() is True

    def test_bundle_dir_none_when_not_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        assert env_mod._bundle_dir() is None

    def test_bundle_dir_uses_meipass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch, bundle="/some/bundle")
        assert env_mod._bundle_dir() == "/some/bundle"


class TestCleanSubprocessEnv:
    def test_non_frozen_returns_path_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        original = {"PATH": "/usr/bin:/bin", "HOME": "/home/x"}
        result = clean_subprocess_env(original)
        # Fast-path returns the same object unchanged.
        assert result is original
        assert result["PATH"] == "/usr/bin:/bin"

    def test_frozen_strips_bundle_dir_from_front(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch, bundle="/bundle")
        monkeypatch.delenv(_EXTRA_PATH_ENV, raising=False)
        result = clean_subprocess_env({"PATH": f"/bundle{os.pathsep}/usr/bin"})
        entries = result["PATH"].split(os.pathsep)
        assert "/bundle" not in entries
        assert "/usr/bin" in entries

    def test_frozen_augments_with_common_dirs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.delenv(_EXTRA_PATH_ENV, raising=False)
        result = clean_subprocess_env({"PATH": "/usr/bin"})
        entries = result["PATH"].split(os.pathsep)
        # Existing entry keeps priority (appears before the augmentation).
        assert entries[0] == "/usr/bin"
        assert len(entries) > 1  # augmentation appended

    def test_frozen_operator_override_appended(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv(_EXTRA_PATH_ENV, f"/opt/custom{os.pathsep}/opt/more")
        result = clean_subprocess_env({"PATH": "/usr/bin"})
        entries = result["PATH"].split(os.pathsep)
        assert "/opt/custom" in entries
        assert "/opt/more" in entries

    def test_frozen_dedups_preserving_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv(_EXTRA_PATH_ENV, "/usr/bin")  # already present
        result = clean_subprocess_env({"PATH": "/usr/bin"})
        entries = result["PATH"].split(os.pathsep)
        assert entries.count("/usr/bin") == 1

    def test_empty_path_does_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.delenv(_EXTRA_PATH_ENV, raising=False)
        # No PATH key at all.
        result = clean_subprocess_env({"HOME": "/home/x"})
        assert "PATH" in result  # augmentation still produces a PATH


class TestStripBundleDirFromPath:
    def test_non_frozen_is_copy_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        original = {"PATH": "/usr/bin:/bin"}
        result = strip_bundle_dir_from_path(original)
        assert result == original
        assert result is not original  # fresh dict

    def test_frozen_removes_bundle_anywhere(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch, bundle="/bundle")
        result = strip_bundle_dir_from_path(
            {"PATH": f"/bundle{os.pathsep}/usr/bin{os.pathsep}/bundle"}
        )
        assert "/bundle" not in result["PATH"].split(os.pathsep)

    def test_missing_path_returns_copy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch)
        result = strip_bundle_dir_from_path({"HOME": "/home/x"})
        assert result == {"HOME": "/home/x"}


class TestAllowlistInvariant:
    """DD2 invariant: PyInstaller loader-path vars must never be allowlisted
    and never appear in a built child env. No restore-``*_ORIG`` code exists."""

    LOADER_VARS = (
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
    )

    def test_loader_vars_not_in_allowlists(self) -> None:
        combined = _ENV_ALLOWLIST + _WINDOWS_ENV_ALLOWLIST
        for var in self.LOADER_VARS:
            assert var not in combined
        # No ``*_ORIG`` stash key is allowlisted either.
        assert not any(k.endswith("_ORIG") for k in combined)

    def test_loader_vars_absent_from_built_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in self.LOADER_VARS:
            monkeypatch.setenv(var, "/leaked/lib")
        monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/leaked/orig")
        built = _build_subprocess_env()
        for var in self.LOADER_VARS:
            assert var not in built
        assert "LD_LIBRARY_PATH_ORIG" not in built


class TestBuildSubprocessEnvAppliesSeam:
    def test_non_frozen_env_path_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        built = _build_subprocess_env()
        assert built["PATH"] == "/usr/bin:/bin"

    def test_frozen_env_strips_bundle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch, bundle="/bundle")
        monkeypatch.delenv(_EXTRA_PATH_ENV, raising=False)
        monkeypatch.setenv("PATH", f"/bundle{os.pathsep}/usr/bin")
        built = _build_subprocess_env()
        assert "/bundle" not in built["PATH"].split(os.pathsep)
