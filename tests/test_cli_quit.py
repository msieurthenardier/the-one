"""``the-one quit`` (M32 F2 L05): every output branch against a local stub server."""

from __future__ import annotations

import http.server
import json
import socket
import threading

import pytest

from the_one.api_credential import credential_path, rotate_credential
from the_one.config import settings


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "host", "127.0.0.1")
    monkeypatch.setattr(settings, "port", _free_port())
    return tmp_path / "data"


@pytest.fixture()
def stub_server(data_dir):
    """A server answering POST /api/window/quit with a programmable (status, body)."""
    box = {"status": 200, "body": b'{"quit": true, "pid": 1, "state": "window"}', "auth": None}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            box["auth"] = self.headers.get("Authorization")
            box["path"] = self.path
            self.send_response(box["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(box["body"])))
            self.end_headers()
            self.wfile.write(box["body"])

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", settings.port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield box
    srv.shutdown()
    srv.server_close()


def _run(capsys) -> tuple[int, str]:
    from the_one.main import _quit_command

    code = _quit_command()
    return code, capsys.readouterr().out


def test_no_credential_file_is_not_running_and_creates_nothing(data_dir, capsys):
    code, out = _run(capsys)
    assert code == 0 and "is not running" in out
    assert not credential_path().exists()
    assert not data_dir.exists()


def test_connection_refused_is_not_running(data_dir, capsys):
    rotate_credential()
    code, out = _run(capsys)
    assert code == 0 and out.strip() == "GleepGlorp AI is not running."


def test_quit_true(stub_server, capsys):
    cred = rotate_credential()
    code, out = _run(capsys)
    assert code == 0 and out.strip() == "GleepGlorp AI is quitting."
    assert stub_server["path"] == "/api/window/quit"
    assert stub_server["auth"] == f"Bearer {cred.encode()}"


def test_quit_false_is_server_only(stub_server, capsys):
    rotate_credential()
    stub_server["body"] = b'{"quit": false, "pid": 1, "state": null}'
    code, out = _run(capsys)
    assert code == 0 and "running as a server only" in out and "Ctrl+C" in out


@pytest.mark.parametrize("status", [401, 403])
def test_foreign_or_rotated_credential(stub_server, capsys, status):
    rotate_credential()
    stub_server["status"] = status
    stub_server["body"] = b"{}"
    code, out = _run(capsys)
    assert code == 1 and f"using port {settings.port}" in out and "different credential" in out


@pytest.mark.parametrize("status", [404, 405])
def test_old_server_without_quit_route(stub_server, capsys, status):
    rotate_credential()
    stub_server["status"] = status
    stub_server["body"] = b"{}"
    code, out = _run(capsys)
    assert code == 1 and "too old" in out


def test_unexpected_status_and_body(stub_server, capsys):
    rotate_credential()
    stub_server["status"] = 500
    stub_server["body"] = b"boom"
    code, out = _run(capsys)
    assert code == 1 and "HTTP 500" in out
    stub_server["status"] = 200
    stub_server["body"] = b"not json"
    code, out = _run(capsys)
    assert code == 1 and "Unexpected answer" in out
    stub_server["body"] = json.dumps({"other": 1}).encode()
    code, out = _run(capsys)
    assert code == 1 and "Unexpected answer" in out


def test_malformed_credential_file_is_a_one_line_error(data_dir, capsys):
    credential_path().parent.mkdir(parents=True, exist_ok=True)
    credential_path().write_text("")
    code, out = _run(capsys)
    assert code == 1 and "Cannot read the local API credential" in out
    assert len(out.strip().splitlines()) == 1


def test_cli_dispatch_and_usage(monkeypatch, capsys):
    import the_one.main as main

    monkeypatch.setattr(main, "_quit_command", lambda wait=False: 0)
    monkeypatch.setattr("sys.argv", ["the-one", "quit"])
    with pytest.raises(SystemExit) as e:
        main.cli_entry()
    assert e.value.code == 0
    monkeypatch.setattr("sys.argv", ["the-one", "bogus"])
    with pytest.raises(SystemExit) as e:
        main.cli_entry()
    assert e.value.code == 1
    assert "quit" in capsys.readouterr().out


def test_wait_waits_for_pid_exit(data_dir, stub_server, capsys, monkeypatch):
    import the_one.interfaces.desktop.shell as shell
    from the_one.main import _quit_command

    rotate_credential()
    seen = []
    monkeypatch.setattr(shell, "_wait_for_exit", lambda pid: seen.append(pid) or True)
    assert _quit_command(wait=True) == 0
    assert seen == [1]
    assert "has quit" in capsys.readouterr().out


def test_wait_timeout_exits_one(data_dir, stub_server, capsys, monkeypatch):
    import the_one.interfaces.desktop.shell as shell
    from the_one.main import _quit_command

    rotate_credential()
    monkeypatch.setattr(shell, "_wait_for_exit", lambda pid: False)
    assert _quit_command(wait=True) == 1
    assert "did not exit" in capsys.readouterr().out


def test_no_wait_does_not_poll(data_dir, stub_server, capsys, monkeypatch):
    import the_one.interfaces.desktop.shell as shell
    from the_one.main import _quit_command

    rotate_credential()
    monkeypatch.setattr(
        shell, "_wait_for_exit", lambda pid: (_ for _ in ()).throw(AssertionError("polled"))
    )
    assert _quit_command(wait=False) == 0


@pytest.mark.parametrize(
    ("argv", "tty", "expected"),
    [
        (["quit"], True, True),
        (["quit"], False, False),
        (["quit", "--wait"], False, True),
        (["quit", "--no-wait"], True, False),
    ],
)
def test_cli_entry_wait_default(monkeypatch, argv, tty, expected):
    import sys

    import the_one.main as main

    got = []
    monkeypatch.setattr(main, "_quit_command", lambda wait=False: got.append(wait) or 0)
    monkeypatch.setattr(sys, "argv", ["the-one", *argv])
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty, raising=False)
    with pytest.raises(SystemExit):
        main.cli_entry()
    assert got == [expected]


@pytest.mark.parametrize("bad", ["true", "0", "-3", "null", '"7"'])
def test_wait_ignores_invalid_pid(data_dir, stub_server, capsys, monkeypatch, bad):
    import the_one.interfaces.desktop.shell as shell
    from the_one.main import _quit_command

    rotate_credential()
    stub_server["body"] = ('{"quit": true, "pid": %s, "state": "window"}' % bad).encode()
    monkeypatch.setattr(
        shell, "_wait_for_exit", lambda pid: (_ for _ in ()).throw(AssertionError("polled"))
    )
    assert _quit_command(wait=True) == 0
