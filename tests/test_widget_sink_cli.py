"""scripts/widget_sink.py (M35 F2 L6): the widget-escape sink as a command.

It prints its ports as JSON on the first line, counts one hit per channel (HTTP, UDP, TCP) while
never counting its own control requests, serves the escape fixture with the ports filled in,
refuses a non-loopback bind, and stops on SIGTERM.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "widget_sink.py"


@pytest.fixture
def sink():
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT)],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = proc.stdout.readline()
        assert line, proc.stderr.read()
        yield proc, json.loads(line)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                proc.kill()
                proc.wait()


def _get(port: int, path: str) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.read()


def _counts(port: int) -> dict:
    return json.loads(_get(port, "/__sink/counts"))


def test_first_line_is_the_ports_and_a_baseline_is_zero(sink) -> None:
    _proc, info = sink
    assert set(info) == {"http", "udp", "tcp", "pid"}
    assert all(isinstance(v, int) and v > 0 for v in info.values())
    c = _counts(info["http"])
    # reading the counts is not a hit
    assert c == {"http": 0, "http_requests": [], "udp": 0, "tcp": 0}
    assert _counts(info["http"])["http"] == 0


def test_counts_one_hit_per_channel(sink) -> None:
    _proc, info = sink
    _get(info["http"], "/leak?p=x")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(b"stun", ("127.0.0.1", info["udp"]))
    with socket.create_connection(("127.0.0.1", info["tcp"]), timeout=5):
        pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        c = _counts(info["http"])
        if c["udp"] == 1 and c["tcp"] == 1:
            break
        time.sleep(0.05)
    assert c["http"] == 1 and c["http_requests"] == ["GET /leak?p=x"]
    assert c["udp"] == 1
    assert c["tcp"] == 1


def test_the_fixture_has_the_ports_filled_in(sink) -> None:
    _proc, info = sink
    text = _get(info["http"], "/__sink/fixture").decode()
    assert "{{" not in text
    assert f"HTTP = '{info['http']}'" in text
    assert f"UDP = '{info['udp']}'" in text and f"TCP = '{info['tcp']}'" in text
    assert "MODE = 'main'" in text
    focus = _get(info["http"], "/__sink/fixture-focus").decode()
    assert "MODE = 'focus'" in focus and "{{" not in focus
    assert _counts(info["http"])["http"] == 0


def test_stops_on_sigterm(sink) -> None:
    proc, _info = sink
    proc.terminate()
    assert proc.wait(timeout=10) == 0


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com"])
def test_refuses_a_non_loopback_bind(host: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--host", host],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2
    assert "non-loopback" in proc.stderr
    assert proc.stdout == ""
