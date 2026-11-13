"""scripts/fake_platforms.py as a command (M35 F3 L5, AC7): refusals, the first-line JSON,
health, and a clean stop on SIGTERM."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "fake_platforms.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--host", "0.0.0.0"],
        ["--host", "example.com"],
        ["--port", "8484"],
        ["--port", "8485"],
        ["--port", "8000"],
        ["--port", "8489"],
        ["--save-dir", str(REPO / "somewhere")],
        ["--save-dir", str(REPO)],
    ],
)
def test_refusals_exit_2_and_print_nothing(args: list[str]) -> None:
    proc = _run(*args)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "refusing" in proc.stderr


def test_serves_health_prints_first_line_and_stops_on_sigterm(tmp_path: Path) -> None:
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--port", "0", "--save-dir", str(tmp_path / "s")],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = proc.stdout.readline()
        assert line, proc.stderr.read()
        info = json.loads(line)
        assert set(info) == {"port", "pid"}
        assert info["pid"] == proc.pid and info["port"] > 0
        with urllib.request.urlopen(
            f"http://127.0.0.1:{info['port']}/_control/health", timeout=5
        ) as r:
            assert r.status == 200
        proc.terminate()
        assert proc.wait(timeout=15) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
