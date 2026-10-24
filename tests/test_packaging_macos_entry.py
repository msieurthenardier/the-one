"""The macOS frozen entry's argv handling (M32 F2 L8). Loaded by path; never runs main."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "packaging" / "macos" / "frozen_entry_mac.py"
_SPEC = importlib.util.spec_from_file_location("frozen_entry_mac", _PATH)
entry = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(entry)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ["app"]),
        (["-psn_0_12345"], ["app"]),
        (["doctor"], ["doctor"]),
        (["-psn_0_1", "serve", "--x"], ["serve", "--x"]),
        (["quit"], ["quit"]),
    ],
)
def test_launch_args(argv: list[str], expected: list[str]) -> None:
    assert entry.launch_args(argv) == expected
