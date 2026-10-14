"""``App.formatBytes`` uses decimal units (squawk 0137): 1 GB = 1e9 B, matching ollama.com."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent
    / "the_one"
    / "interfaces"
    / "web"
    / "static"
    / "js"
    / "app.js"
)


def _run(values: list[int]) -> list[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"  function formatBytes\(bytes\) \{.*?\n  \}\n", src, re.S)
    assert m, "formatBytes not found in app.js"
    script = m.group(0) + f"\nconsole.log(JSON.stringify({json.dumps(values)}.map(formatBytes)));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_format_bytes_is_decimal() -> None:
    got = _run([0, 999, 1000, 1_500_000, 13_793_441_244, 2_000_000_000, 5 * 10**12])
    assert got == ["0 B", "999 B", "1 KB", "1.5 MB", "13.8 GB", "2.0 GB", "5.0 TB"]
