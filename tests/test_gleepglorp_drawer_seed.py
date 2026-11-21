"""The GleepGlorp drawer seed script (M36 F3 L9): refusals, request bodies, exit codes.

A fake transport and a fake runner stand in for the instance; no network is used.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "gleepglorp_drawer_seed",
    Path(__file__).parent.parent / "scripts" / "gleepglorp_drawer_seed.py",
)
seed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed)

BASE = "http://127.0.0.1:8490"


class FakeServer:
    def __init__(self, *, dev_mode=True, ready=True, fills=None, agents=None, sessions=None):
        self.dev_mode = dev_mode
        self.ready = ready
        self.calls: list[tuple[str, str, object]] = []
        self.fills = fills if fills is not None else []
        self.agents = agents if agents is not None else []
        self.sessions = (
            sessions if sessions is not None else [{"id": "s1", "agent_name": "GleepGlorp"}]
        )
        self.providers: list[dict] = []
        self.headers_seen: list[dict] = []

    def __call__(self, method, url, headers, body):
        path = url[len(BASE) :]
        self.calls.append((method, path, body))
        self.headers_seen.append(headers)
        if path == "/api/config":
            return 200, {"dev_mode": self.dev_mode}
        if path == "/api/providers" and method == "GET":
            return 200, self.providers
        if path == "/api/providers" and method == "POST":
            return 201, {"id": "p-new"}
        if path.startswith("/api/providers/") and method == "DELETE":
            return 200, {}
        if path == "/api/gleepglorp" and method == "PUT":
            return 200, {}
        if path == "/api/gleepglorp":
            return 200, {"state": "ready" if self.ready else "needs_model"}
        if path == "/api/chat/sessions":
            return 200, self.sessions
        if path.startswith("/api/gleepglorp/fills"):
            return 200, {"fills": self.fills}
        if path == "/api/agents":
            return 200, [{"name": n} for n in self.agents]
        return 404, None


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "scratch-data"
    d.mkdir()
    (d / "api-credential").write_text("loc_abc.secret\n")
    return d


@pytest.fixture
def default(tmp_path):
    return tmp_path / "the-default-dir"


def run(args, server, default, runner=None):
    return seed.main(
        args,
        transport=server,
        runner=runner or (lambda argv, env: 0),
        default=default,
        sleep=lambda s: None,
    )


# --- refusals -----------------------------------------------------------------------------


@pytest.mark.parametrize("port", [8484, 8485])
def test_refuses_the_production_and_preview_ports(port, data_dir, default, capsys) -> None:
    server = FakeServer()
    rc = run(
        ["--base-url", f"http://127.0.0.1:{port}", "--data-dir", str(data_dir)], server, default
    )
    assert rc == 2 and server.calls == []
    assert str(port) in capsys.readouterr().err


def test_refuses_the_default_data_directory(default, capsys) -> None:
    default.mkdir()
    (default / "api-credential").write_text("loc_x.y")
    server = FakeServer()
    rc = run(["--base-url", BASE, "--data-dir", str(default)], server, default)
    assert rc == 2 and server.calls == []
    assert "default data directory" in capsys.readouterr().err


def test_refuses_the_default_data_directory_through_a_symlink(tmp_path, default) -> None:
    default.mkdir()
    (default / "api-credential").write_text("loc_x.y")
    link = tmp_path / "link"
    link.symlink_to(default)
    assert run(["--base-url", BASE, "--data-dir", str(link)], FakeServer(), default) == 2


def test_default_dir_falls_back_to_platformdirs_without_the_one(monkeypatch) -> None:
    """The runner has no repo environment: the per-OS computation is used."""
    monkeypatch.setitem(sys.modules, "the_one", None)
    monkeypatch.setitem(sys.modules, "the_one.config", None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert seed.default_data_dir() == Path.home() / ".local" / "share" / "the-one"


def test_refuses_the_computed_default_without_the_one(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setitem(sys.modules, "the_one", None)
    monkeypatch.setitem(sys.modules, "the_one.config", None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    d = tmp_path / ".local" / "share" / "the-one"
    d.mkdir(parents=True)
    (d / "api-credential").write_text("loc_x.y")
    server = FakeServer()
    # No `default` injected: the script must derive it itself.
    rc = seed.main(
        ["--base-url", BASE, "--data-dir", str(d)], transport=server, runner=lambda a, e: 0
    )
    assert rc == 2 and server.calls == []
    assert "default data directory" in capsys.readouterr().err


def test_platformdirs_per_os() -> None:
    env = {"HOME": "/h", "LOCALAPPDATA": "C:\\Users\\u\\AppData\\Local"}
    assert seed.platformdirs_default("darwin", env) == Path(
        "/h/Library/Application Support/the-one"
    )
    assert seed.platformdirs_default("linux", env) == Path("/h/.local/share/the-one")
    assert (
        seed.platformdirs_default("win32", env) == Path("C:\\Users\\u\\AppData\\Local") / "the-one"
    )


def test_refuses_an_extra_data_dir(data_dir, default, capsys) -> None:
    server = FakeServer()
    rc = run(
        ["--base-url", BASE, "--data-dir", str(data_dir), "--refuse-data-dir", str(data_dir)],
        server,
        default,
    )
    assert rc == 2 and server.calls == []
    assert "--refuse-data-dir" in capsys.readouterr().err


def test_refuses_a_subdirectory_of_the_default_dir(default, capsys) -> None:
    sub = default / "nested" / "scratch"
    sub.mkdir(parents=True)
    (sub / "api-credential").write_text("loc_x.y")
    server = FakeServer()
    assert run(["--base-url", BASE, "--data-dir", str(sub)], server, default) == 2
    assert server.calls == []
    assert "default data directory" in capsys.readouterr().err


def test_refuses_a_subdirectory_of_an_extra_refused_dir(tmp_path, default) -> None:
    parent = tmp_path / "lifecycle-data"
    sub = parent / "inner"
    sub.mkdir(parents=True)
    (sub / "api-credential").write_text("loc_x.y")
    args = ["--base-url", BASE, "--data-dir", str(sub), "--refuse-data-dir", str(parent)]
    assert run(args, FakeServer(), default) == 2


def test_a_sibling_with_the_same_name_prefix_is_not_refused(tmp_path) -> None:
    default = tmp_path / "the-one"
    default.mkdir()
    sibling = tmp_path / "the-one-scratch"
    sibling.mkdir()
    (sibling / "api-credential").write_text("loc_x.y")
    args = ["--base-url", BASE, "--data-dir", str(sibling), "--refuse-data-dir", str(default)]
    assert run(args, FakeServer(), default) == 0


def test_refuses_a_missing_credential_without_the_flag(tmp_path, default, capsys) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    server = FakeServer()
    assert run(["--base-url", BASE, "--data-dir", str(d)], server, default) == 2
    assert server.calls == []
    assert "no credential" in capsys.readouterr().err


def test_rotate_if_missing_runs_the_rotation_with_the_scratch_dir(tmp_path, default) -> None:
    d = tmp_path / "fresh"
    d.mkdir()
    seen = []

    def runner(argv, env):
        seen.append((argv, env))
        (d / "api-credential").write_text("loc_new.cred\n")
        return 0

    server = FakeServer()
    rc = run(
        ["--base-url", BASE, "--data-dir", str(d), "--rotate-if-missing"], server, default, runner
    )
    assert rc == 0
    assert seen == [(["the-one", "rotate-api-credential"], {"THE_ONE_DATA_DIR": str(d)})]
    assert server.headers_seen[0] == {"Authorization": "Bearer loc_new.cred"}


def test_a_failed_rotation_is_an_error(tmp_path, default) -> None:
    d = tmp_path / "fresh"
    d.mkdir()
    rc = run(
        ["--base-url", BASE, "--data-dir", str(d), "--rotate-if-missing"],
        FakeServer(),
        default,
        runner=lambda a, e: 1,
    )
    assert rc == 2


# --- seeding ------------------------------------------------------------------------------


def test_seed_request_bodies_and_output(data_dir, default, capsys) -> None:
    server = FakeServer()
    assert run(["--base-url", BASE, "--data-dir", str(data_dir)], server, default) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provider_id"] == "p-new" and out["dev_mode"] is True
    assert out["gleepglorp_state"] == "ready"
    posted = next(b for m, p, b in server.calls if (m, p) == ("POST", "/api/providers"))
    assert posted["type"] == "mock" and posted["base_url"] == ""
    first, second = posted["config"]["responses"]
    [tc] = first["tool_calls"]
    assert tc["name"] == "fill_form"
    assert tc["arguments"]["kind"] == "agent" and tc["arguments"]["action"] == "create"
    assert tc["arguments"]["changes"]["name"] == "Filled by mock"
    assert tc["arguments"]["changes"]["description"] and tc["arguments"]["changes"]["system_prompt"]
    assert second == {"content": "The form is filled, not saved. Click Save."}
    put = next(b for m, p, b in server.calls if (m, p) == ("PUT", "/api/gleepglorp"))
    assert put["provider_config_id"] == "p-new" and put["model"] == "mock-default"
    assert put["enabled"] is True


def test_seed_replaces_an_earlier_mock_provider(data_dir, default) -> None:
    server = FakeServer()
    server.providers = [{"id": "old", "name": seed.PROVIDER_NAME}, {"id": "keep", "name": "x"}]
    assert run(["--base-url", BASE, "--data-dir", str(data_dir)], server, default) == 0
    deletes = [p for m, p, _ in server.calls if m == "DELETE"]
    assert deletes == ["/api/providers/old?force=true"]


def test_seed_needs_dev_mode(data_dir, default, capsys) -> None:
    server = FakeServer(dev_mode=False)
    assert run(["--base-url", BASE, "--data-dir", str(data_dir)], server, default) == 2
    assert "dev mode" in capsys.readouterr().err
    assert not any(m == "POST" for m, _, _ in server.calls)


def test_seed_fails_when_gleepglorp_is_not_ready(data_dir, default, capsys) -> None:
    server = FakeServer(ready=False)
    rc = run(["--base-url", BASE, "--data-dir", str(data_dir), "--wait", "0"], server, default)
    assert rc == 2 and "needs_model" in capsys.readouterr().err


# --- --check-fill -------------------------------------------------------------------------


def check(server, data_dir, default):
    return run(["--base-url", BASE, "--data-dir", str(data_dir), "--check-fill"], server, default)


def test_check_fill_zero_only_for_filled_and_no_agent(data_dir, default, capsys) -> None:
    server = FakeServer(fills=[{"id": 1, "status": "filled"}], agents=["other"])
    assert check(server, data_dir, default) == 0
    assert json.loads(capsys.readouterr().out) == {"fill_status": "filled", "agent_exists": False}


@pytest.mark.parametrize("status", ["sent", "claimed", "partly_filled", "not_filled", "replaced"])
def test_check_fill_one_for_any_other_status(status, data_dir, default) -> None:
    assert check(FakeServer(fills=[{"id": 1, "status": status}]), data_dir, default) == 1


def test_check_fill_one_when_the_agent_was_created(data_dir, default) -> None:
    server = FakeServer(fills=[{"id": 1, "status": "filled"}], agents=["Filled by mock"])
    assert check(server, data_dir, default) == 1


def test_check_fill_one_with_no_fill(data_dir, default, capsys) -> None:
    assert check(FakeServer(fills=[]), data_dir, default) == 1
    assert json.loads(capsys.readouterr().out)["fill_status"] is None


def test_check_fill_reads_the_newest_fill_over_sessions(data_dir, default) -> None:
    class Two(FakeServer):
        def __call__(self, method, url, headers, body):
            if "session_id=a" in url:
                return 200, {"fills": [{"id": 1, "status": "filled"}]}
            if "session_id=b" in url:
                return 200, {"fills": [{"id": 2, "status": "sent"}]}
            return super().__call__(method, url, headers, body)

    server = Two(
        sessions=[{"id": "a", "agent_name": "GleepGlorp"}, {"id": "b", "agent_name": "GleepGlorp"}]
    )
    assert check(server, data_dir, default) == 1


def test_check_fill_ignores_other_agents_sessions(data_dir, default) -> None:
    server = FakeServer(
        fills=[{"id": 1, "status": "filled"}], sessions=[{"id": "x", "agent_name": "someone"}]
    )
    assert check(server, data_dir, default) == 1
