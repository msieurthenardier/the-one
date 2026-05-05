"""Tests for execution helpers (F4 L2) — `_command_check`, `_cwd_check`,
`_truncate_output`, `_build_subprocess_env`.

Helpers are tested in isolation; L3-L6 wire them into tools.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_one.tools.base import ConstraintError
from the_one.tools.execution import (
    _ENV_ALLOWLIST,
    ExecutionConfig,
    _build_subprocess_env,
    _command_check,
    _cwd_check,
    _truncate_output,
)
from the_one.tools.filesystem import FilesystemConfig

# ---------------------------------------------------------------------------
# _command_check — substring denylist refusal (F4 Decision 3)
# ---------------------------------------------------------------------------


class TestCommandCheck:
    def test_empty_denylist_never_raises(self) -> None:
        cfg = ExecutionConfig(command_denylist=[])
        _command_check("rm -rf /", cfg)  # no raise

    def test_safe_command_no_raise(self) -> None:
        cfg = ExecutionConfig(command_denylist=["sudo "])
        _command_check("ls", cfg)  # no raise

    def test_sudoku_false_positive_avoided(self) -> None:
        """Trailing-space convention: ``sudoku`` does NOT match ``"sudo "``."""
        cfg = ExecutionConfig(command_denylist=["sudo "])
        _command_check("sudoku", cfg)  # no raise

    def test_sudo_whoami_raises(self) -> None:
        cfg = ExecutionConfig(command_denylist=["sudo "])
        with pytest.raises(ConstraintError) as exc:
            _command_check("sudo whoami", cfg)
        assert str(exc.value) == "command contains denylisted token 'sudo '"

    def test_wrapped_bash_form_caught(self) -> None:
        """Substring catches the wrapped form per Decision 3 rationale —
        first-token splitting would miss this; substring matching does not."""
        cfg = ExecutionConfig(command_denylist=["sudo "])
        with pytest.raises(ConstraintError) as exc:
            _command_check('bash -c "sudo whoami"', cfg)
        assert "sudo " in str(exc.value)

    def test_first_match_wins(self) -> None:
        """When multiple denylist entries match, the error names the FIRST
        match (iteration order = denylist order)."""
        cfg = ExecutionConfig(command_denylist=["foo ", "bar "])
        with pytest.raises(ConstraintError) as exc:
            _command_check("foo bar baz", cfg)
        # "foo " is the first match in iteration order.
        assert "'foo '" in str(exc.value)

    def test_error_message_format(self) -> None:
        cfg = ExecutionConfig(command_denylist=["mkfs"])
        with pytest.raises(ConstraintError) as exc:
            _command_check("mkfs.ext4 /dev/sda1", cfg)
        assert str(exc.value) == "command contains denylisted token 'mkfs'"

    def test_empty_command_no_raise(self) -> None:
        cfg = ExecutionConfig(command_denylist=["sudo "])
        _command_check("", cfg)  # empty contains nothing


# ---------------------------------------------------------------------------
# _cwd_check — cross-Config cwd validation (F4 Decision 7)
# ---------------------------------------------------------------------------


class TestCwdCheck:
    def test_default_allowlist_home_canonical(self) -> None:
        """Default FilesystemConfig allowlist is `["~"]`; `_cwd_check("~")`
        returns the canonical Path equal to `Path.home()`."""
        cfg = FilesystemConfig()
        result = _cwd_check("~", cfg)
        assert result == Path.home().resolve()

    def test_default_denylist_etc_raises(self) -> None:
        """`/etc` is in the default denylist; `_cwd_check` raises (allowlist
        check passes only if `~` somehow contains `/etc`, which it does
        not on any real system)."""
        cfg = FilesystemConfig()
        with pytest.raises(ConstraintError):
            _cwd_check("/etc", cfg)

    def test_in_scope_existing_directory_returns_canonical(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = _cwd_check(str(tmp_path), cfg)
        assert result == tmp_path.resolve()
        assert result.is_dir()

    def test_in_scope_file_not_directory_raises(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        leaf = tmp_path / "not_a_dir.txt"
        leaf.write_text("hi")
        with pytest.raises(ConstraintError) as exc:
            _cwd_check(str(leaf), cfg)
        assert "is not a directory" in str(exc.value)

    def test_in_scope_nonexistent_raises_with_combined_message(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        ghost = tmp_path / "does_not_exist"
        with pytest.raises(ConstraintError) as exc:
            _cwd_check(str(ghost), cfg)
        # `Path.is_dir()` returns False for both nonexistent and
        # non-directory paths — combined message per leg spec.
        assert "does not exist or is not a directory" in str(exc.value)

    def test_out_of_scope_raises_via_filesystem_check(self, tmp_path: Path) -> None:
        """Allowlist check is delegated to ``_filesystem_check`` — out-of-scope
        paths raise the filesystem-style refusal, NOT the cwd-shape one."""
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        with pytest.raises(ConstraintError) as exc:
            _cwd_check("/usr", cfg)
        # `_filesystem_check` raises "outside allowlist"; not the cwd msg.
        assert "outside allowlist" in str(exc.value)


# ---------------------------------------------------------------------------
# _truncate_output — combined cap, tail-preserving (F4 Decision 2)
# ---------------------------------------------------------------------------


class TestTruncateOutput:
    def test_below_cap_success(self) -> None:
        cfg = ExecutionConfig(output_cap_bytes=1024)
        text, was_truncated = _truncate_output(b"hello", b"", 0, cfg)
        assert text == "hello"
        assert was_truncated is False

    def test_below_cap_with_stderr(self) -> None:
        cfg = ExecutionConfig(output_cap_bytes=1024)
        text, was_truncated = _truncate_output(b"hi", b"warn", 0, cfg)
        assert "hi" in text
        assert "warn" in text
        # F4 L3 refinement: ``\n[stderr]\n`` marker inserted between stdout
        # and stderr by the helper itself (single source of truth for the
        # existing F1 ``[stderr]`` contract).
        assert "[stderr]" in text
        assert "hi\n[stderr]\nwarn" in text
        assert "[exit code:" not in text  # rc=0 → no suffix
        assert was_truncated is False

    def test_no_stderr_marker_when_stderr_empty(self) -> None:
        """With ``stderr=b""``, the helper does NOT insert the marker —
        avoids spurious ``[stderr]`` substrings in stdout-only output."""
        cfg = ExecutionConfig(output_cap_bytes=1024)
        text, was_truncated = _truncate_output(b"out", b"", 0, cfg)
        assert text == "out"
        assert "[stderr]" not in text
        assert was_truncated is False

    def test_below_cap_failure_appends_exit_suffix(self) -> None:
        cfg = ExecutionConfig(output_cap_bytes=1024)
        text, was_truncated = _truncate_output(b"oops", b"", 1, cfg)
        assert text.endswith("[exit code: 1]")
        assert was_truncated is False

    def test_above_cap_tail_preserved(self) -> None:
        # Cap floor is 1024 (Pydantic ge=1024), so pick 1024 here.
        cfg = ExecutionConfig(output_cap_bytes=1024)
        stdout = b"A" * 3000
        text, was_truncated = _truncate_output(stdout, b"", 0, cfg)
        assert was_truncated is True
        # Marker line first.
        expected_marker = (
            "[... truncated 1976 bytes; showing last 1024 bytes of combined stdout+stderr ...]"
        )
        assert text.startswith(expected_marker)
        # Tail = LAST 1024 A's preserved.
        assert text.endswith("A" * 1024)

    def test_above_cap_with_failure_exit_code_after_tail(self) -> None:
        cfg = ExecutionConfig(output_cap_bytes=1024)
        stdout = b"A" * 3000
        text, was_truncated = _truncate_output(stdout, b"", 1, cfg)
        assert was_truncated is True
        assert text.endswith("[exit code: 1]")

    def test_combined_cap_uses_concatenated_tail(self) -> None:
        """Cap applies to ``stdout + b"\\n[stderr]\\n" + stderr`` (F4 L3
        refinement). Tail preserves the LAST cap bytes of that concatenation,
        marker bytes included."""
        cfg = ExecutionConfig(output_cap_bytes=1024)
        stdout = b"X" * 700
        stderr = b"Y" * 700
        text, was_truncated = _truncate_output(stdout, stderr, 0, cfg)
        assert was_truncated is True
        # combined = X*700 + b"\n[stderr]\n" (10 bytes) + Y*700 = 1410 bytes.
        # Tail of last 1024 bytes drops 386 leading X's, so tail starts at
        # X #387 (314 X's remain), then the full marker, then all 700 Y's:
        #   314 + 10 + 700 = 1024 bytes.
        assert text.endswith("X" * 314 + "\n[stderr]\n" + "Y" * 700)

    def test_stderr_marker_inside_tail_when_truncated(self) -> None:
        """A small cap with stdout/stderr sized so the marker survives in
        the tail — pin the byte math so a future ``_truncate_output`` change
        cannot silently swallow the marker."""
        cfg = ExecutionConfig(output_cap_bytes=1024)
        # Same payload shape as combined-cap test; assertion is sharper —
        # just the marker substring (the surrounding bytes are pinned by
        # the combined-cap test above).
        stdout = b"X" * 700
        stderr = b"Y" * 700
        text, _ = _truncate_output(stdout, stderr, 0, cfg)
        assert "\n[stderr]\n" in text

    def test_empty_output_rc_zero_returns_no_output(self) -> None:
        cfg = ExecutionConfig()
        text, was_truncated = _truncate_output(b"", b"", 0, cfg)
        assert text == "(no output)"
        assert was_truncated is False

    def test_empty_output_rc_nonzero_returns_exit_code(self) -> None:
        """Matches today's ShellTool: exit suffix appended BEFORE strip(),
        so the text isn't empty when rc != 0."""
        cfg = ExecutionConfig()
        text, was_truncated = _truncate_output(b"", b"", 1, cfg)
        assert text == "[exit code: 1]"
        assert was_truncated is False

    def test_byte_boundary_split_handled_via_replace(self) -> None:
        """Tail-slicing on raw bytes can split a UTF-8 codepoint mid-sequence;
        ``errors="replace"`` handles this gracefully (no UnicodeDecodeError)."""
        cfg = ExecutionConfig(output_cap_bytes=1024)
        # 'é' = b'\xc3\xa9' (2 bytes); craft a payload where the tail starts
        # mid-sequence. We just need it to not blow up.
        payload = b"\xc3\xa9" * 600  # 1200 bytes > cap of 1024
        text, was_truncated = _truncate_output(payload, b"", 0, cfg)
        assert was_truncated is True
        # Should not raise; exact decoded shape depends on slice point.
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# _build_subprocess_env — hardcoded 8-key allowlist (F4 Decision 10)
# ---------------------------------------------------------------------------


class TestBuildSubprocessEnv:
    def test_returns_only_allowlisted_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")
        env = _build_subprocess_env()
        assert "THE_ONE_TEST_LEAK" not in env
        for k in env:
            assert k in _ENV_ALLOWLIST

    def test_setenv_allowlisted_key_appears(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "C.UTF-8")
        env = _build_subprocess_env()
        assert env.get("LANG") == "C.UTF-8"

    def test_missing_allowlist_key_absent_no_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TZ", raising=False)
        env = _build_subprocess_env()  # no KeyError
        assert "TZ" not in env

    def test_eight_allowlist_keys_canonical_set(self) -> None:
        # The allowlist tuple itself is the source of truth; pin its shape
        # so an accidental edit to the constant trips a test.
        assert _ENV_ALLOWLIST == (
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "LANG",
            "LC_ALL",
            "TERM",
            "TZ",
        )

    def test_returns_dict_str_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        env = _build_subprocess_env()
        assert isinstance(env, dict)
        for k, v in env.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
