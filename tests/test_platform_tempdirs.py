"""Direct tests for ``the_one.platform.tempdirs``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from the_one.platform.tempdirs import temp_dir, user_config_dir, user_home


class TestTempDir:
    def test_returns_existing_path(self) -> None:
        result = temp_dir()
        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()


class TestUserHome:
    def test_returns_existing_path(self) -> None:
        result = user_home()
        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()
        assert result == Path.home()


class TestUserConfigDir:
    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only path shape")
    def test_posix_shape(self) -> None:
        assert user_config_dir("the-one") == Path.home() / ".the-one"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only path shape")
    def test_posix_does_not_create(self, tmp_path: Path, monkeypatch) -> None:
        # Use a unique app name so we can assert non-creation safely.
        unique = "the-one-test-no-create-xyz123"
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        result = user_config_dir(unique)
        assert result == tmp_path / f".{unique}"
        assert not result.exists()

    def test_returns_path_instance(self) -> None:
        assert isinstance(user_config_dir("any-app"), Path)
