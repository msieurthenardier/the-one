"""Unit tests for packaging/linux/audit.py, the post-freeze bundle audit (M32 F2 L8, DD2)."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

_PATH = Path(__file__).parent.parent / "packaging" / "linux" / "audit.py"
_SPEC = importlib.util.spec_from_file_location("packaging_audit", _PATH)
audit = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = audit
_SPEC.loader.exec_module(audit)

EXCLUDES = _PATH.parent / "excludes.txt"


def _fake_readelf(table: dict[str, list[str]]):
    return lambda path: table.get(Path(path).name, [])


def _bundle(tmp_path: Path) -> Path:
    b = tmp_path / "dist" / "the-one"
    (b / "_internal").mkdir(parents=True)
    (b / "the-one").write_bytes(b"\x7fELF fake")
    (b / "_internal" / "data.txt").write_text("x")
    return b


def test_clean_tree_passes(tmp_path, monkeypatch, capsys) -> None:
    b = _bundle(tmp_path)
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({"the-one": ["2.17", "2.38"]}))
    assert audit.main([str(b)]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "2 files" in out and "GLIBC_2.38" in out


def test_excluded_library_fails_and_is_named(tmp_path, monkeypatch, capsys) -> None:
    b = _bundle(tmp_path)
    (b / "_internal" / "libglib-2.0.so.0").write_text("not elf")
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({}))
    assert audit.main([str(b)]) == 1
    out = capsys.readouterr().out
    assert "libglib-2.0.so.0" in out and "FAIL" in out


def test_wheel_vendored_hashed_name_is_not_an_exclusion(tmp_path, monkeypatch) -> None:
    b = _bundle(tmp_path)
    (b / "_internal" / "pillow.libs").mkdir()
    (b / "_internal" / "pillow.libs" / "libharfbuzz-abc123.so.0").write_text("x")
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({}))
    assert audit.main([str(b)]) == 0


def test_typelib_fails(tmp_path, monkeypatch, capsys) -> None:
    b = _bundle(tmp_path)
    (b / "_internal" / "Gtk-3.0.typelib").write_text("x")
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({}))
    assert audit.main([str(b)]) == 1
    assert "Gtk-3.0.typelib" in capsys.readouterr().out


def test_newer_glibc_fails(tmp_path, monkeypatch, capsys) -> None:
    b = _bundle(tmp_path)
    (b / "_internal" / "libnew.so").write_bytes(b"\x7fELF fake")
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({"libnew.so": ["2.34", "2.41"]}))
    assert audit.main([str(b)]) == 1
    out = capsys.readouterr().out
    assert "GLIBC_2.41" in out and "libnew.so" in out


def test_glibc_version_compare_is_numeric(tmp_path, monkeypatch) -> None:
    b = _bundle(tmp_path)
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({"the-one": ["2.4", "2.39"]}))
    problems, _, highest = audit.audit(b, [], "2.39")
    assert problems == [] and highest == "2.39"
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({"the-one": ["2.100"]}))
    assert audit.audit(b, [], "2.39")[0]


def test_non_elf_files_are_not_sent_to_readelf(tmp_path, monkeypatch) -> None:
    b = _bundle(tmp_path)
    seen: list[str] = []

    def spy(path):
        seen.append(Path(path).name)
        return []

    monkeypatch.setattr(audit, "glibc_requirements", spy)
    audit.audit(b, [], "2.39")
    assert seen == ["the-one"]


def test_fallback_directory_is_never_scanned(tmp_path, monkeypatch) -> None:
    b = _bundle(tmp_path)
    fb = tmp_path / "dist" / "the-one-fallback" / "lib"
    fb.mkdir(parents=True)
    (fb / "libgirepository-2.0.so.0").write_text("x")
    (fb.parent / "AyatanaAppIndicator3-0.1.typelib").write_text("x")
    monkeypatch.setattr(audit, "glibc_requirements", _fake_readelf({}))
    # audit scopes to the bundle directory it is given; the sibling is out of scope
    assert audit.main([str(b)]) == 0


def test_missing_bundle_is_an_error(tmp_path) -> None:
    assert audit.main([str(tmp_path / "nope")]) == 2


def test_excludes_file_lines_are_valid_unique_patterns() -> None:
    raw = EXCLUDES.read_text(encoding="utf-8").splitlines()
    pats = audit.load_patterns(EXCLUDES)
    assert pats, "excludes.txt holds no patterns"
    assert len(pats) == len(set(pats)), "duplicate pattern lines"
    for p in pats:
        assert p == p.strip() and " " not in p and "/" not in p, p
        assert re.fullmatch(r"[A-Za-z0-9_.+*?\[\]-]+", p), p
        re.compile(__import__("fnmatch").translate(p))
    # a line that is only whitespace (not a comment, not empty) is a mistake
    assert not [ln for ln in raw if ln and not ln.strip()]
