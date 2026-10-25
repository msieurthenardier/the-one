"""M32 F3 L5: the macOS runtime seam (DD6 stub + PATH walk, DD7 login-shell PATH).

Everything runs on a Linux host: ``sys.platform`` is patched to ``darwin`` where
needed, and only fakes (``tmp_path`` shell scripts, patched ``which``) are used.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from the_one.platform import env as env_mod
from the_one.platform import interpreter as interp_mod
from the_one.platform.env import (
    _build_subprocess_env,
    _common_runtime_dirs,
    clean_subprocess_env,
    path_source,
    prime_login_shell_path,
)
from the_one.platform.interpreter import FrozenInterpreterError, resolve_python

BUNDLE = "/bundle"


def _freeze(monkeypatch: pytest.MonkeyPatch, platform: str = "darwin") -> None:
    monkeypatch.setattr(env_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(env_mod.sys, "_MEIPASS", BUNDLE, raising=False)
    monkeypatch.setattr(env_mod.sys, "platform", platform)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(env_mod, "_PRIMED", None)
    monkeypatch.setattr(interp_mod, "_clt_installed_cache", None)
    monkeypatch.delenv("THE_ONE_PYTHON", raising=False)
    monkeypatch.delenv("THE_ONE_EXTRA_PATH", raising=False)


def _fake_which(table: dict[tuple[str, str], str]):
    """``which(cmd, path=entry)`` -> the table's hit for that (cmd, entry)."""
    return lambda cmd, path=None: table.get((cmd, path))


# --------------------------------------------------------------- interpreter


class TestStubAndWalk:
    def test_stub_first_without_clt_falls_to_later_real_python(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("PATH", "/usr/bin:/opt/py")
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: False)
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            _fake_which(
                {
                    ("python3", "/usr/bin"): "/usr/bin/python3",
                    ("python3", "/opt/py"): "/opt/py/python3",
                }
            ),
        )
        assert resolve_python() == str(Path("/opt/py/python3").resolve())

    def test_stub_with_clt_is_accepted(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("PATH", "/usr/bin:/opt/py")
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: True)
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            _fake_which({("python3", "/usr/bin"): "/usr/bin/python3"}),
        )
        assert resolve_python() == str(Path("/usr/bin/python3").resolve())

    def test_only_the_stub_raises_the_dd6_error(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: False)
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            _fake_which(
                {
                    ("python3", "/usr/bin"): "/usr/bin/python3",
                    ("python", "/usr/bin"): "/usr/bin/python",
                }
            ),
        )
        with pytest.raises(FrozenInterpreterError) as exc:
            resolve_python()
        msg = str(exc.value)
        assert "only the macOS Command Line Tools stub `/usr/bin/python3` was found" in msg
        assert "install Python 3 (python.org or Homebrew)" in msg
        assert "THE_ONE_PYTHON" in msg

    def test_real_clt_python_under_library_is_not_a_stub(self, monkeypatch) -> None:
        monkeypatch.setattr(interp_mod.sys, "platform", "darwin")
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: False)
        found = "/Library/Developer/CommandLineTools/usr/bin/python3"
        assert interp_mod._is_clt_stub(found) is False
        assert interp_mod._is_clt_stub("/usr//bin/../bin/python3") is True

    def test_stub_check_never_runs_off_darwin(self, monkeypatch) -> None:
        monkeypatch.setattr(interp_mod.sys, "platform", "linux")

        def boom() -> bool:
            raise AssertionError("xcode-select must not run off darwin")

        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", boom)
        assert interp_mod._is_clt_stub("/usr/bin/python3") is False

    def test_windows_alias_shadowing_walks_to_the_real_python(self, monkeypatch) -> None:
        _freeze(monkeypatch, "win32")
        monkeypatch.setattr(env_mod.os, "pathsep", ":")
        monkeypatch.setattr(interp_mod.os, "pathsep", ":")
        monkeypatch.setenv("PATH", "alias:real")
        alias = r"C:\Users\a\AppData\Local\Microsoft\WindowsApps\python3.exe"
        real = "/real/python3"
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            _fake_which({("python3", "alias"): alias, ("python3", "real"): real}),
        )
        assert resolve_python() == str(Path(real).resolve())

    def test_override_is_never_filtered(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("THE_ONE_PYTHON", "/usr/bin/python3")
        monkeypatch.setattr(interp_mod, "_command_line_tools_installed", lambda: False)
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            lambda cmd, path=None: cmd if cmd == "/usr/bin/python3" else None,
        )
        assert resolve_python() == str(Path("/usr/bin/python3").resolve())

    def test_empty_path_entries_are_skipped(self, monkeypatch) -> None:
        seen: list[object] = []

        def which(cmd, path=None):
            seen.append(path)
            return None

        monkeypatch.setattr(interp_mod.shutil, "which", which)
        interp_mod.walk_python_candidates(["python3"], "::/a::/b:")
        assert seen == ["/a", "/b"]

    def test_walk_is_candidate_outer(self, monkeypatch) -> None:
        monkeypatch.setattr(
            interp_mod.shutil,
            "which",
            _fake_which({("python", "/a"): "/a/python", ("python3", "/b"): "/b/python3"}),
        )
        found, _ = interp_mod.walk_python_candidates(["python3", "python"], "/a:/b")
        assert found == "/b/python3"


class TestXcodeSelect:
    def _fake(self, tmp_path: Path, body: str) -> str:
        script = tmp_path / "xcode-select"
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(0o755)
        return str(script)

    def test_installed_when_prints_existing_dir_and_is_cached(self, monkeypatch, tmp_path) -> None:
        counter = tmp_path / "count"
        fake = self._fake(tmp_path, f'echo x >> "{counter}"; echo "{tmp_path}"\n')
        monkeypatch.setattr(interp_mod, "_XCODE_SELECT", fake)
        assert interp_mod._command_line_tools_installed() is True
        assert interp_mod._command_line_tools_installed() is True
        assert counter.read_text().count("x") == 1

    def test_removed_directory_counts_as_no_clt(self, monkeypatch, tmp_path) -> None:
        fake = self._fake(tmp_path, 'echo "/nonexistent/CommandLineTools"\n')
        monkeypatch.setattr(interp_mod, "_XCODE_SELECT", fake)
        assert interp_mod._command_line_tools_installed() is False

    def test_nonzero_exit_counts_as_no_clt(self, monkeypatch, tmp_path) -> None:
        fake = self._fake(tmp_path, f'echo "{tmp_path}"; exit 2\n')
        monkeypatch.setattr(interp_mod, "_XCODE_SELECT", fake)
        assert interp_mod._command_line_tools_installed() is False

    def test_hang_is_bounded(self, monkeypatch, tmp_path) -> None:
        fake = self._fake(tmp_path, "exec sleep 30\n")
        monkeypatch.setattr(interp_mod, "_XCODE_SELECT", fake)
        monkeypatch.setattr(interp_mod, "_XCODE_SELECT_TIMEOUT", 0.5)
        start = time.monotonic()
        assert interp_mod._command_line_tools_installed() is False
        assert time.monotonic() - start < 3
        # Cached: a second call does not wait again.
        start = time.monotonic()
        assert interp_mod._command_line_tools_installed() is False
        assert time.monotonic() - start < 0.2


# ------------------------------------------------------------ login-shell PATH


def _shell(tmp_path: Path, body: str, name: str = "fakesh") -> str:
    script = tmp_path / name
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    return str(script)


# A fake login shell that exports a PATH then runs the -c command, as a real one would.
_RUNS_COMMAND = 'PATH="{path}"; export PATH; eval "$4"\n'


def _gone(pid: int, bound: float = 5.0) -> bool:
    """A process is gone when /proc/<pid>/stat is missing or its state is Z."""
    deadline = time.monotonic() + bound
    while time.monotonic() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return True
        if state == "Z":
            return True
        time.sleep(0.05)
    return False


class TestPrimeLoginShellPath:
    def test_not_applicable_off_frozen_darwin(self, monkeypatch) -> None:
        assert prime_login_shell_path() == "not applicable"
        assert path_source() == ("not applicable", "")
        _freeze(monkeypatch, "linux")
        assert prime_login_shell_path() == "not applicable"
        assert env_mod._PRIMED is None
        monkeypatch.delattr(env_mod.sys, "frozen", raising=False)
        monkeypatch.delattr(env_mod.sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(env_mod.sys, "platform", "darwin")
        assert prime_login_shell_path() == "not applicable"
        assert env_mod._PRIMED is None

    def test_markers_are_parsed(self, monkeypatch, tmp_path) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, _RUNS_COMMAND.format(path="/a/bin:/b/bin")))
        assert path_source() == ("unprimed", "")
        assert prime_login_shell_path() == "login shell"
        assert env_mod._PRIMED[2] == ("/a/bin", "/b/bin")
        assert path_source() == ("login shell", "")

    def test_fish_style_path_goes_through_printenv(self, monkeypatch, tmp_path) -> None:
        # fish keeps PATH as a list; only an exported child sees the joined string.
        body = 'set_fish_list() { :; }; PATH="/fish/one:/fish/two"; export PATH; eval "$4"\n'
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, body))
        assert prime_login_shell_path() == "login shell"
        assert env_mod._PRIMED[2] == ("/fish/one", "/fish/two")

    def test_rc_file_noise_outside_the_markers_is_ignored(self, monkeypatch, tmp_path) -> None:
        body = 'echo "Welcome!"; echo "/not/a/path"; ' + _RUNS_COMMAND.format(path="/x/bin")
        body += 'echo "bye /not/either"\n'
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, body))
        assert prime_login_shell_path() == "login shell"
        assert env_mod._PRIMED[2] == ("/x/bin",)

    def test_last_block_wins_when_markers_print_twice(self, monkeypatch, tmp_path) -> None:
        _freeze(monkeypatch)
        body = (
            f"echo {env_mod._PATH_BEGIN}; echo /first; echo {env_mod._PATH_END}; "
            f"echo {env_mod._PATH_BEGIN}; echo /second:/third; echo {env_mod._PATH_END}\n"
        )
        monkeypatch.setenv("SHELL", _shell(tmp_path, body, "twice"))
        assert prime_login_shell_path() == "login shell"
        assert env_mod._PRIMED[2] == ("/second", "/third")

    def test_timeout_kills_the_process_group(self, monkeypatch, tmp_path) -> None:
        pidfile = tmp_path / "child.pid"
        body = f'sleep 60 & echo $! > "{pidfile}"; wait\n'
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, body))
        start = time.monotonic()
        assert prime_login_shell_path(timeout=0.5) == "static fallback"
        assert time.monotonic() - start < 1.5
        assert "did not answer" in path_source()[1]
        assert _gone(int(pidfile.read_text()))

    def test_a_shell_that_never_exits_is_bounded(self, monkeypatch, tmp_path) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, "exec sleep 60\n"))
        start = time.monotonic()
        assert prime_login_shell_path(timeout=0.5) == "static fallback"
        assert time.monotonic() - start < 1.5

    @pytest.mark.parametrize("shell", ["/nonexistent/shell", "relative-shell"])
    def test_missing_or_relative_shell_falls_back(self, monkeypatch, shell) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", shell)
        assert prime_login_shell_path() == "static fallback"
        assert path_source()[0] == "static fallback"
        assert path_source()[1]

    def test_nonzero_exit_falls_back(self, monkeypatch, tmp_path) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, "exit 1\n"))
        assert prime_login_shell_path() == "static fallback"
        assert "exited 1" in path_source()[1]

    def test_empty_marker_block_falls_back(self, monkeypatch, tmp_path) -> None:
        body = f"echo {env_mod._PATH_BEGIN}; echo {env_mod._PATH_END}\n"
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, body))
        assert prime_login_shell_path() == "static fallback"
        assert "no PATH" in path_source()[1]

    def test_missing_markers_fall_back(self, monkeypatch, tmp_path) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, "echo /only/noise\n"))
        assert prime_login_shell_path() == "static fallback"

    def test_unset_shell_uses_the_passwd_entry(self, monkeypatch, tmp_path) -> None:
        import pwd

        fake = _shell(tmp_path, _RUNS_COMMAND.format(path="/pw/bin"))
        _freeze(monkeypatch)
        monkeypatch.delenv("SHELL", raising=False)

        class _Entry:
            pw_shell = fake

        monkeypatch.setattr(pwd, "getpwuid", lambda uid: _Entry())
        assert prime_login_shell_path() == "login shell"
        assert env_mod._PRIMED[2] == ("/pw/bin",)

    def test_idempotent_and_a_fallback_is_cached(self, monkeypatch, tmp_path) -> None:
        counter = tmp_path / "count"
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, f'echo x >> "{counter}"; exit 3\n'))
        assert prime_login_shell_path() == "static fallback"
        assert prime_login_shell_path() == "static fallback"
        assert counter.read_text().count("x") == 1

    def test_two_concurrent_first_calls_run_one_probe(self, monkeypatch, tmp_path) -> None:
        counter = tmp_path / "count"
        body = f'echo x >> "{counter}"; sleep 0.3; ' + _RUNS_COMMAND.format(path="/c/bin")
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, body))
        results: list[str] = []
        threads = [
            threading.Thread(target=lambda: results.append(prime_login_shell_path()))
            for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results == ["login shell", "login shell"]
        assert counter.read_text().count("x") == 1


class TestPathOrder:
    def _env(self, path: str) -> dict[str, str]:
        return {"PATH": path, "HOME": "/home/u"}

    def test_primed_order_login_then_inherited_then_static_then_extra(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("THE_ONE_EXTRA_PATH", "/extra")
        monkeypatch.setattr(env_mod, "_PRIMED", ("login shell", "", ("/login/a", "/usr/bin")))
        monkeypatch.setattr(env_mod, "_common_runtime_dirs", lambda: ["/static/s"])
        out = clean_subprocess_env(self._env("/usr/bin:/bin"))["PATH"].split(os.pathsep)
        assert out == ["/login/a", "/usr/bin", "/bin", "/static/s", "/extra"]

    def test_unprimed_order_is_unchanged_and_never_primes(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setattr(env_mod, "_common_runtime_dirs", lambda: ["/static/s"])

        def boom(*a, **k):
            raise AssertionError("must not prime lazily")

        monkeypatch.setattr(env_mod, "_run_login_shell", boom)
        out = clean_subprocess_env(self._env("/usr/bin:/bin"))["PATH"].split(os.pathsep)
        assert out == ["/usr/bin", "/bin", "/static/s"]
        assert env_mod._PRIMED is None

    def test_static_fallback_state_keeps_todays_order(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setattr(env_mod, "_PRIMED", ("static fallback", "why", ()))
        monkeypatch.setattr(env_mod, "_common_runtime_dirs", lambda: ["/static/s"])
        out = clean_subprocess_env(self._env("/usr/bin"))["PATH"].split(os.pathsep)
        assert out == ["/usr/bin", "/static/s"]

    def test_bundle_dir_in_login_path_is_stripped(self, monkeypatch, tmp_path) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("SHELL", _shell(tmp_path, _RUNS_COMMAND.format(path=f"{BUNDLE}:/l/bin")))
        assert prime_login_shell_path() == "login shell"
        monkeypatch.setattr(env_mod, "_common_runtime_dirs", lambda: [])
        out = clean_subprocess_env(self._env(f"{BUNDLE}:/usr/bin"))["PATH"].split(os.pathsep)
        assert BUNDLE not in out
        assert out == ["/l/bin", "/usr/bin"]

    def test_build_subprocess_env_carries_the_primed_path(self, monkeypatch) -> None:
        _freeze(monkeypatch)
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setattr(env_mod, "_PRIMED", ("login shell", "", ("/login/a",)))
        assert _build_subprocess_env()["PATH"].split(os.pathsep)[0] == "/login/a"

    def test_login_path_is_not_applied_off_darwin(self, monkeypatch) -> None:
        _freeze(monkeypatch, "linux")
        monkeypatch.setattr(env_mod, "_PRIMED", ("login shell", "", ("/login/a",)))
        monkeypatch.setattr(env_mod, "_common_runtime_dirs", lambda: [])
        assert clean_subprocess_env(self._env("/usr/bin"))["PATH"] == "/usr/bin"


def test_static_additions_present(monkeypatch) -> None:
    monkeypatch.setattr(env_mod.os, "name", "posix")
    dirs = _common_runtime_dirs()
    home = Path.home()
    assert str(home / ".volta" / "bin") in dirs
    assert str(home / ".local" / "share" / "fnm" / "aliases" / "default" / "bin") in dirs


def test_static_dirs_survive_an_unresolvable_home(monkeypatch) -> None:
    def boom():
        raise RuntimeError("no home")

    monkeypatch.setattr(env_mod.Path, "home", staticmethod(boom))
    monkeypatch.setattr(env_mod.os, "name", "posix")
    assert "/usr/local/bin" in _common_runtime_dirs()


# ------------------------------------------------------------------- main


@pytest.mark.parametrize("command", ["serve", "doctor"])
def test_main_primes_before_serve_and_doctor(monkeypatch, command) -> None:
    import sys

    import the_one.main as main_mod

    calls: list[str] = []
    monkeypatch.setattr(
        env_mod, "prime_login_shell_path", lambda timeout=5.0: calls.append("prime") or "x"
    )
    monkeypatch.setattr(main_mod.uvicorn, "run", lambda *a, **k: calls.append("run"))
    import the_one.diagnostics as diag

    monkeypatch.setattr(diag, "run_doctor", lambda: calls.append("doctor") or 0)
    monkeypatch.setattr(sys, "argv", ["the-one", command])
    if command == "doctor":
        with pytest.raises(SystemExit):
            main_mod.cli_entry()
        assert calls == ["prime", "doctor"]
    else:
        main_mod.cli_entry()
        assert calls == ["prime", "run"]
