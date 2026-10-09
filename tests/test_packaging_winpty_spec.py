"""Static guard for squawk 0162: the frozen bundle must ship pywinpty's .exe helpers.

The spec cannot be frozen off Windows, so this reads its source. pywinpty >= 3's
bundled conpty.dll launches OpenConsole.exe from its own directory; PyInstaller's
default dynamic-lib patterns skip *.exe, so the spec must ask for them.
"""

from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "the-one.spec"


def test_spec_collects_winpty_exe_helpers():
    src = SPEC.read_text(encoding="utf-8")
    start = src.index("winpty_bins = collect_dynamic_libs(")
    call = src[start : src.index(")", start) + 1]
    assert "search_patterns" in call
    assert '"*.exe"' in call
    assert "*winpty_bins" in src
