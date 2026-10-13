"""Unit tests for the in-memory era map (M29 F2 DD2)."""

import subprocess
import sys

from the_one.mcp import _era


def test_era_for_unknown_is_none() -> None:
    assert _era.era_for("nope") is None


def test_remember_then_read() -> None:
    _era.remember_era("s1", "2026-07-28")
    assert _era.era_for("s1") == "2026-07-28"
    _era.remember_era("s1", "2025-11-25")
    assert _era.era_for("s1") == "2025-11-25"


def test_forget_is_idempotent() -> None:
    _era.remember_era("s1", "2026-07-28")
    _era.forget_era("s1")
    _era.forget_era("s1")
    assert _era.era_for("s1") is None


def test_clear_for_test_empties_everything() -> None:
    _era.remember_era("a", "x")
    _era.remember_era("b", "y")
    _era._clear_for_test()
    assert _era.era_for("a") is None and _era.era_for("b") is None


def test_autouse_fixture_starts_clean() -> None:
    assert _era.era_for("s1") is None


def test_era_module_is_a_leaf() -> None:
    """No ``the_one`` import in the source, and importing it never loads oauth."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(_era.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("the_one"), node.module
        elif isinstance(node, ast.Import):
            assert not any(a.name.startswith("the_one") for a in node.names)
    script = (
        "import sys; import the_one.mcp._era; "
        "leaked = sorted(k for k in sys.modules if k.startswith('the_one.mcp.oauth')); "
        "assert leaked == [], leaked; print('OK')"
    )
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
