"""M32 F4 L3: the Windows ``PATH`` walk for a frozen app's external Python (Flight 3 debrief item).

Linux-run unit tests: the app is "frozen", ``sys.platform`` is ``win32``, ``os.pathsep`` is ``;``
and ``PATH`` is a real ``;``-separated list of real directories holding real executable files, so
``shutil.which`` does the walking. Added beside what is already covered, not repeating it:

* ``tests/test_platform_interpreter.py`` (patched ``which``): the Store alias on its own raises with
  the Store text, an alias first then a real interpreter later, and ``THE_ONE_PYTHON`` on a
  ``WindowsApps`` path is never filtered;
* ``tests/test_macos_runtime_seam.py``: the alias-shadowing walk with fakes, empty entries,
  candidate-outer order (``python3`` anywhere beats ``python`` earlier).

New here, with real files: ``PATH`` order across several interpreters, an alias directory first and
a real one later, an entry that is a file / missing / empty, only ``py.exe`` on ``PATH`` (the walk
looks for ``python3``/``python`` only), and no interpreter at all.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from the_one.platform import env as env_mod
from the_one.platform import interpreter as interp_mod
from the_one.platform.interpreter import FrozenInterpreterError, resolve_python


@pytest.fixture(autouse=True)
def _windows_frozen(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(env_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(env_mod.sys, "_MEIPASS", "/bundle", raising=False)
    real_platform = sys.platform
    real_which = shutil.which
    monkeypatch.setattr(env_mod.sys, "platform", "win32")

    def which_on_this_host(cmd, mode=os.F_OK | os.X_OK, path=None):
        # shutil.which switches to its Windows implementation (needing _winapi) when
        # sys.platform is "win32"; the walk under test only cares that the platform is not
        # darwin, so the real lookup runs with the host's own platform.
        sys.platform = real_platform
        try:
            return real_which(cmd, mode, path)
        finally:
            sys.platform = "win32"

    monkeypatch.setattr(shutil, "which", which_on_this_host)
    monkeypatch.setattr(os, "pathsep", ";")
    monkeypatch.setattr(env_mod, "_PRIMED", None)
    monkeypatch.setattr(interp_mod, "_clt_installed_cache", None)
    monkeypatch.delenv("THE_ONE_PYTHON", raising=False)
    monkeypatch.delenv("THE_ONE_EXTRA_PATH", raising=False)
    # the frozen PATH is augmented with common install dirs; a developer's real ~/.local/bin or
    # /usr/local/bin must not leak a real interpreter into a "none found" case
    monkeypatch.setattr(env_mod, "_common_runtime_dirs", lambda: [])


def _exe(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def _set_path(monkeypatch: pytest.MonkeyPatch, *entries: object) -> None:
    monkeypatch.setenv("PATH", ";".join(str(e) for e in entries))


def test_the_first_real_interpreter_on_path_wins(monkeypatch, tmp_path) -> None:
    first = _exe(tmp_path / "py311", "python3")
    _exe(tmp_path / "py312", "python3")
    _exe(tmp_path / "py313", "python3")
    _set_path(monkeypatch, tmp_path / "py311", tmp_path / "py312", tmp_path / "py313")
    assert resolve_python() == str(first.resolve())
    _set_path(monkeypatch, tmp_path / "py313", tmp_path / "py311")
    assert resolve_python() == str((tmp_path / "py313" / "python3").resolve())


def test_an_alias_directory_first_then_a_real_interpreter_later(monkeypatch, tmp_path) -> None:
    alias_dir = tmp_path / "Microsoft" / "WindowsApps"
    _exe(alias_dir, "python3")
    _exe(alias_dir, "python")
    real = _exe(tmp_path / "Python311", "python")
    _set_path(monkeypatch, alias_dir, tmp_path / "Python311")
    assert resolve_python() == str(real.resolve())


def test_a_later_real_python3_beats_an_earlier_real_python(monkeypatch, tmp_path) -> None:
    # candidate-outer: every entry is tried for python3 before python is tried at all
    _exe(tmp_path / "a", "python")
    later = _exe(tmp_path / "b", "python3")
    _set_path(monkeypatch, tmp_path / "a", tmp_path / "b")
    assert resolve_python() == str(later.resolve())


def test_entries_that_are_a_file_missing_or_empty_are_passed_over(monkeypatch, tmp_path) -> None:
    a_file = tmp_path / "not-a-dir"
    a_file.write_text("x")
    missing = tmp_path / "gone"
    real = _exe(tmp_path / "real", "python3")
    _set_path(monkeypatch, "", a_file, missing, "", real.parent, "")
    assert resolve_python() == str(real.resolve())


def test_a_directory_with_a_non_executable_python_is_passed_over(monkeypatch, tmp_path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "python3").write_text("not executable")  # mode 0644
    real = _exe(tmp_path / "real", "python3")
    _set_path(monkeypatch, plain, real.parent)
    assert resolve_python() == str(real.resolve())


def test_only_py_exe_on_path_gives_the_actionable_error(monkeypatch, tmp_path) -> None:
    # the launcher is not a candidate: the walk looks for python3/python only
    _exe(tmp_path / "launcher", "py.exe")
    _exe(tmp_path / "launcher", "py")
    _set_path(monkeypatch, tmp_path / "launcher")
    with pytest.raises(FrozenInterpreterError) as exc:
        resolve_python()
    msg = str(exc.value)
    assert "no `python3`/`python` interpreter was found on PATH" in msg
    assert "THE_ONE_PYTHON" in msg and "python.org" in msg
    assert "docker" not in msg.lower()


def test_no_interpreter_at_all_gives_the_actionable_error(monkeypatch, tmp_path) -> None:
    (tmp_path / "empty").mkdir()
    _set_path(monkeypatch, tmp_path / "empty", tmp_path / "missing", "")
    with pytest.raises(FrozenInterpreterError) as exc:
        resolve_python()
    msg = str(exc.value)
    assert msg.startswith("The packaged app needs an external Python interpreter")
    assert "Install Python 3.11+" in msg and "THE_ONE_PYTHON" in msg
    assert "Microsoft Store" not in msg, "nothing was skipped, so no Store text"


def test_an_empty_path_gives_the_actionable_error(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(FrozenInterpreterError) as exc:
        resolve_python()
    assert "no `python3`/`python` interpreter was found on PATH" in str(exc.value)


def test_alias_directory_only_names_the_store_in_the_error(monkeypatch, tmp_path) -> None:
    alias_dir = tmp_path / "microsoft" / "windowsapps"  # the check ignores case
    _exe(alias_dir, "python3")
    _set_path(monkeypatch, alias_dir)
    with pytest.raises(FrozenInterpreterError) as exc:
        resolve_python()
    assert "Microsoft Store" in str(exc.value)


def test_the_bundle_directory_on_path_is_never_searched(monkeypatch, tmp_path) -> None:
    # a python3 next to the frozen exe must not shadow a real one: the bundle dir is stripped
    bundle = tmp_path / "bundle"
    _exe(bundle, "python3")
    real = _exe(tmp_path / "real", "python3")
    monkeypatch.setattr(env_mod.sys, "_MEIPASS", str(bundle), raising=False)
    _set_path(monkeypatch, bundle, real.parent)
    assert resolve_python() == str(real.resolve())
