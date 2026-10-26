"""Unit tests for packaging/stage.py, the shared staging step (Mission 32 F2 L8, DD8)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "packaging" / "stage.py"
_SPEC = importlib.util.spec_from_file_location("packaging_stage", _PATH)
stage = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stage)


def _source(tmp_path: Path, init_text: str) -> Path:
    src = tmp_path / "src"
    (src / "the_one" / "interfaces" / "web" / "static" / "brand").mkdir(parents=True)
    (src / "the_one" / "__init__.py").write_text(init_text, encoding="utf-8")
    (src / stage.ICON).write_bytes(b"png")
    return src


def _run(monkeypatch, src: Path, out: Path, *flags: str) -> int:
    monkeypatch.setenv("M32_SOURCE", str(src))
    monkeypatch.setattr(
        sys, "argv", ["stage.py", "--version", "9.9.9.dev1", *flags, "--out", str(out)]
    )
    return stage.main()


def test_repo_resolves_one_level_up() -> None:
    assert stage.REPO == _PATH.parent.parent
    assert (stage.REPO / "the_one").is_dir()


def test_stages_from_another_tree_and_rewrites_one_version(tmp_path, monkeypatch, capsys) -> None:
    src = _source(tmp_path, '"""doc"""\n__version__ = "0.0.1"\nOTHER = 1\n')
    out = tmp_path / "out"
    assert _run(monkeypatch, src, out, "--target", "linux") == 0
    dest = out / "stage-linux-9.9.9.dev1"
    text = (dest / "the_one" / "__init__.py").read_text(encoding="utf-8")
    assert text.count("__version__") == 1 and '__version__ = "9.9.9.dev1"' in text
    assert "OTHER = 1" in text
    assert (dest / "icon-512.png").read_bytes() == b"png"
    # the source tree is untouched
    assert '"0.0.1"' in (src / "the_one" / "__init__.py").read_text(encoding="utf-8")


def test_candidate_alias_still_works(tmp_path, monkeypatch) -> None:
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    out = tmp_path / "out"
    assert _run(monkeypatch, src, out, "--candidate", "linux") == 0
    assert (out / "stage-linux-9.9.9.dev1" / "the_one" / "__init__.py").is_file()


def test_target_or_candidate_is_required(tmp_path, monkeypatch) -> None:
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    with pytest.raises(SystemExit) as e:
        _run(monkeypatch, src, tmp_path / "out")
    assert e.value.code == 2


@pytest.mark.parametrize(
    "init_text", ['"""no version here"""\n', '__version__ = "1"\n__version__ = "2"\n']
)
def test_zero_or_two_version_lines_fail(tmp_path, monkeypatch, init_text) -> None:
    src = _source(tmp_path, init_text)
    with pytest.raises(SystemExit) as e:
        _run(monkeypatch, src, tmp_path / "out", "--target", "linux")
    assert e.value.code == 1


def test_refuses_output_inside_the_repo(tmp_path, monkeypatch, capsys) -> None:
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    inside = stage.REPO / "packaging" / "_never_created_by_test"
    with pytest.raises(SystemExit) as e:
        _run(monkeypatch, src, inside, "--target", "linux")
    assert e.value.code == 1
    assert "inside the repo" in capsys.readouterr().err
    assert not inside.exists()


def test_script_runs_as_a_program_from_its_new_path(tmp_path) -> None:
    r = subprocess.run([sys.executable, "-I", str(_PATH), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--target" in r.stdout


# ---- no git needed (Mission 32 Flight 4 leg 3): `fly execute` uploads a worktree whose .git
# gitlink points at a path that does not exist on the worker, and a worker may lack git entirely.


def _fake_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(stage, "REPO", repo)
    return repo


def test_windows_target_stages(tmp_path, monkeypatch) -> None:
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    out = tmp_path / "out"
    assert _run(monkeypatch, src, out, "--target", "windows") == 0
    dest = out / "stage-windows-9.9.9.dev1"
    assert '__version__ = "9.9.9.dev1"' in (dest / "the_one" / "__init__.py").read_text()
    assert (dest / "icon-512.png").is_file()


def test_stages_with_no_git_on_path(tmp_path, monkeypatch) -> None:
    real_run = subprocess.run

    def no_git(cmd, *a, **kw):
        if cmd and cmd[0] == "git":
            raise FileNotFoundError(2, "No such file or directory: 'git'")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(stage.subprocess, "run", no_git)
    repo = _fake_repo(tmp_path, monkeypatch)
    assert stage.repo_toplevel() == repo.resolve()
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    assert _run(monkeypatch, src, tmp_path / "out", "--target", "windows") == 0


def test_stages_when_the_git_file_points_at_a_missing_path(tmp_path, monkeypatch) -> None:
    import shutil

    if not shutil.which("git"):
        pytest.skip("git is not installed")
    repo = _fake_repo(tmp_path, monkeypatch)
    (repo / ".git").write_text("gitdir: /nonexistent/worktrees/gone\n", encoding="utf-8")
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True)
    assert probe.returncode != 0, "premise: git must fail on this gitlink"
    assert stage.repo_toplevel() == repo.resolve()
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    assert _run(monkeypatch, src, tmp_path / "out", "--target", "windows") == 0


def test_a_real_repo_uses_git_toplevel(tmp_path, monkeypatch) -> None:
    import shutil

    if not shutil.which("git"):
        pytest.skip("git is not installed")
    repo = _fake_repo(tmp_path, monkeypatch)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert stage.repo_toplevel() == repo.resolve()


@pytest.mark.parametrize("mode", ["no-git", "bad-gitlink"])
def test_refuses_output_inside_the_repo_without_git(tmp_path, monkeypatch, capsys, mode) -> None:
    repo = _fake_repo(tmp_path, monkeypatch)
    if mode == "no-git":
        real_run = subprocess.run

        def no_git(cmd, *a, **kw):
            if cmd and cmd[0] == "git":
                raise FileNotFoundError("git")
            return real_run(cmd, *a, **kw)

        monkeypatch.setattr(stage.subprocess, "run", no_git)
    else:
        (repo / ".git").write_text("gitdir: /nonexistent/x\n", encoding="utf-8")
    src = _source(tmp_path, '__version__ = "0.0.1"\n')
    with pytest.raises(SystemExit) as e:
        _run(monkeypatch, src, repo / "out", "--target", "windows")
    assert e.value.code == 1
    assert "inside the repo" in capsys.readouterr().err
