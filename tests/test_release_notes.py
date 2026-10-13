"""Release notes files and the splitter the publish workflow uses (squawk 0200)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RELEASES = ROOT / "docs" / "releases"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"
SCRIPT = ROOT / "scripts" / "release_notes.py"

_spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)


def _note_files() -> list[Path]:
    return sorted(RELEASES.glob("v*.md"))


def test_release_files_exist() -> None:
    assert [p.stem for p in _note_files()][:1], "docs/releases has no vX.Y.Z.md files"


@pytest.mark.parametrize("path", _note_files(), ids=lambda p: p.name)
def test_release_file_parses(path: Path) -> None:
    title, body = release_notes.split_notes(path.read_text(encoding="utf-8"))
    assert re.fullmatch(r"v\d+\.\d+\.\d+", path.stem)
    assert title.startswith(path.stem)
    assert body.strip()
    assert not body.startswith("\n")


def test_split_trims_blank_lines_and_strips_marker() -> None:
    title, body = release_notes.split_notes("# v1.2.3 — Thing\n\n\nSummary.\n\n## Fixed\n- x\n\n")
    assert title == "v1.2.3 — Thing"
    assert body == "Summary.\n\n## Fixed\n- x\n"


def test_split_handles_crlf() -> None:
    title, body = release_notes.split_notes("# v1.2.3 — Thing\r\n\r\nBody\r\n")
    assert title == "v1.2.3 — Thing"
    assert body.startswith("Body")


@pytest.mark.parametrize("text", ["v1.2.3\n\nBody\n", "#v1.2.3\nBody\n", "# \nBody\n", ""])
def test_split_rejects_missing_title_marker(text: str) -> None:
    with pytest.raises(ValueError):
        release_notes.split_notes(text)


def test_split_rejects_empty_body() -> None:
    with pytest.raises(ValueError):
        release_notes.split_notes("# v1.2.3 — Thing\n\n\n")


def test_cli_prints_title_and_writes_body(tmp_path: Path) -> None:
    src = tmp_path / "v9.9.9.md"
    src.write_text("# v9.9.9 — Demo\n\nHello.\n", encoding="utf-8")
    out = tmp_path / "body.md"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), "--body-out", str(out), "--title"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "v9.9.9 — Demo"
    assert out.read_text(encoding="utf-8") == "Hello.\n"


def test_cli_title_out_is_utf8(tmp_path: Path) -> None:
    src = tmp_path / "v9.9.9.md"
    src.write_text("# v9.9.9 — Demo\n\nHello.\n", encoding="utf-8")
    out = tmp_path / "title.txt"
    subprocess.run([sys.executable, str(SCRIPT), str(src), "--title-out", str(out)], check=True)
    raw = out.read_bytes()
    assert "—".encode("utf-8") in raw
    assert raw.strip() == "v9.9.9 — Demo".encode("utf-8")


def test_cli_fails_on_bad_file(tmp_path: Path) -> None:
    src = tmp_path / "v9.9.9.md"
    src.write_text("no title\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), "--title"], capture_output=True, text=True
    )
    assert result.returncode == 1


def test_workflow_publish_step_uses_notes_files() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text[text.index("name: Publish GitHub Release with installer") :]
    assert "docs/releases/" in step
    assert "scripts/release_notes.py" in step
    assert "--notes-file" in step
    assert "gh release edit" in step
    assert "--generate-notes" in step, "the no-notes-file fallback must remain"
    assert 'gh release upload "$TAG" "$EXE" --clobber' in step
    assert "set -eo pipefail" in step
    assert "--title-out" in step
    assert "--title |" not in step and "--title)" not in step, "title must not use stdout"
    assert "::warning::" in step, "a malformed notes file must warn and fall back"
    assert 'PYTHONUTF8: "1"' in step
