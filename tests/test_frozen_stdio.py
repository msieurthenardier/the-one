"""Unit tests for ``ensure_stdio_streams()`` in ``the_one.platform.env``.

M15 F6 review-fix: frozen windowed-app stdio guard.

When a PyInstaller ``console=False`` EXE runs, ``sys.stdout`` and ``sys.stderr``
are ``None``.  ``ensure_stdio_streams()`` must replace the None stream(s) with a
writable file (a line-buffered log under ``settings.data_dir / "logs"``), so that
downstream code (uvicorn's ``sys.stdout.isatty()`` call) does not raise
``AttributeError``.

These tests monkeypatch ``sys.stdout``/``sys.stderr`` to ``None`` and verify the
postconditions; real streams are restored by monkeypatch automatically on teardown
so no other test is affected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from the_one.platform import env as env_mod
from the_one.platform.env import ensure_stdio_streams


class TestEnsureStdioStreams:
    """Functional tests for ensure_stdio_streams()."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _patch_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Point settings.data_dir at tmp_path for the duration of the test."""
        # ensure_stdio_streams() does a *late* import of the_one.config.settings,
        # so we patch the module-level singleton attribute directly.
        from the_one.config import settings  # noqa: PLC0415

        monkeypatch.setattr(settings, "data_dir", tmp_path, raising=True)

    # ------------------------------------------------------------------
    # no-op when both streams are real
    # ------------------------------------------------------------------

    def test_noop_when_both_streams_real(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ensure_stdio_streams() must be a no-op when stdout and stderr are real."""
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        self._patch_data_dir(monkeypatch, tmp_path)
        ensure_stdio_streams()

        # streams must not have been replaced
        assert sys.stdout is original_stdout
        assert sys.stderr is original_stderr
        # log dir must NOT have been created (no-op means no side-effects)
        assert not (tmp_path / "logs").exists()

    # ------------------------------------------------------------------
    # stdout is None
    # ------------------------------------------------------------------

    def test_replaces_null_stdout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When sys.stdout is None, it must be replaced with a writable stream."""
        self._patch_data_dir(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "stdout", None)

        ensure_stdio_streams()

        assert sys.stdout is not None
        # Must be writable without raising
        sys.stdout.write("test-stdout\n")
        # isatty() must return False (a file is not a tty — satisfies uvicorn)
        assert sys.stdout.isatty() is False

    # ------------------------------------------------------------------
    # stderr is None
    # ------------------------------------------------------------------

    def test_replaces_null_stderr(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When sys.stderr is None, it must be replaced with a writable stream."""
        self._patch_data_dir(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "stderr", None)

        ensure_stdio_streams()

        assert sys.stderr is not None
        sys.stderr.write("test-stderr\n")
        assert sys.stderr.isatty() is False

    # ------------------------------------------------------------------
    # both streams are None
    # ------------------------------------------------------------------

    def test_replaces_both_null_streams(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When both streams are None, both must be replaced."""
        self._patch_data_dir(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)

        ensure_stdio_streams()

        assert sys.stdout is not None
        assert sys.stderr is not None
        sys.stdout.write("x")
        sys.stderr.write("y")
        assert sys.stdout.isatty() is False
        assert sys.stderr.isatty() is False

    # ------------------------------------------------------------------
    # log directory and file are created
    # ------------------------------------------------------------------

    def test_log_dir_and_file_created(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The logs/ sub-directory and the log file must be created."""
        self._patch_data_dir(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)

        ensure_stdio_streams()

        log_dir = tmp_path / "logs"
        assert log_dir.is_dir(), "logs/ dir must be created"
        log_file = log_dir / "the-one-app.log"
        assert log_file.exists(), "the-one-app.log must be created"

    # ------------------------------------------------------------------
    # idempotent — second call is a no-op
    # ------------------------------------------------------------------

    def test_idempotent_second_call(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A second call must not replace the already-real stream a first call installed."""
        self._patch_data_dir(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "stdout", None)

        ensure_stdio_streams()
        first_stdout = sys.stdout

        ensure_stdio_streams()  # second call — idempotent
        assert sys.stdout is first_stdout

    # ------------------------------------------------------------------
    # fallback to devnull when settings import fails
    # ------------------------------------------------------------------

    def test_devnull_fallback_on_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the settings import raises, fall back to devnull — never crash startup."""
        import builtins  # noqa: PLC0415

        original_import = builtins.__import__

        def _mock_import(name: str, *args, **kwargs):  # type: ignore[override]
            if "the_one.config" in name or name == "the_one.config":
                raise ImportError("simulated import failure")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(builtins, "__import__", _mock_import)

        ensure_stdio_streams()

        # Must have recovered to a writable stream (devnull)
        assert sys.stdout is not None
        sys.stdout.write("fallback-write")
        assert sys.stdout.isatty() is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-v"]))
