#!/usr/bin/env python3
"""Seed a dev instance so GleepGlorp answers from a scripted mock (M36 F3 L9, DD11).

The desktop-engine runs (WebKitGTK, WebView2, WKWebView) drive the GleepGlorp drawer with no real
model or key: a mock provider whose ``responses`` list is one ``fill_form`` create-agent call
("Filled by mock"), then the closing text. This script creates that provider, points GleepGlorp at
it and waits for ``state: ready``. ``--check-fill`` reads back whether the fill reached ``filled``
and that no agent was created.

Standard library only (it runs on a hosted macOS runner with no repo environment).

    python3 scripts/gleepglorp_drawer_seed.py --base-url http://127.0.0.1:8486 \\
        --data-dir "$HOME/scratch/data" [--rotate-if-missing] [--refuse-data-dir PATH]
    python3 scripts/gleepglorp_drawer_seed.py ... --check-fill     # exit 0 iff filled, no agent

Safety: it refuses port 8484 and 8485, the platformdirs default data directory (derived by the
app's own helper when ``the_one`` imports, else computed per OS), any ``--refuse-data-dir``, and a
data directory with no credential unless ``--rotate-if-missing`` is given. Only a dev instance
(``THE_ONE_DEV_MODE=true``) accepts the mock provider.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

FORBIDDEN_PORTS = {
    8484: "the operator's production instance",
    8485: "the Flight Director's preview instance",
}
PROVIDER_NAME = "GleepGlorp drawer mock"
AGENT_NAME = "Filled by mock"
FINAL_TEXT = "The form is filled, not saved. Click Save."
FILL_CHANGES = {
    "name": AGENT_NAME,
    "description": "Written into the form by the scripted mock.",
    "system_prompt": "You are an example agent filled in by the scripted mock.",
}
RESPONSES = [
    {
        "content": "",
        "tool_calls": [
            {
                "id": "mock-fill-1",
                "name": "fill_form",
                "arguments": {"kind": "agent", "action": "create", "changes": FILL_CHANGES},
            }
        ],
    },
    {"content": FINAL_TEXT},
]
MESSAGE_TO_SEND = "Fill in a new agent for me"  # no ^ + % { } (the Windows key grammar)

# (method, url, headers, body-or-None) -> (status, parsed JSON or None)
Transport = Callable[[str, str, dict[str, str], Any], tuple[int, Any]]
Runner = Callable[[list[str], dict[str, str]], int]


class SeedError(Exception):
    """A refusal or a failed step; the message goes to stderr, exit 2."""


def platformdirs_default(system: str | None = None, env: dict[str, str] | None = None) -> Path:
    """The platformdirs ``user_data_dir("the-one", appauthor=False)`` per OS, with no import."""
    system = system or sys.platform
    env = os.environ if env is None else env
    home = Path(env.get("HOME") or Path.home())
    if system == "darwin":
        return home / "Library" / "Application Support" / "the-one"
    if system.startswith("win"):
        local = env.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(local) / "the-one"
    xdg = env.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "the-one"


def default_data_dir() -> Path:
    """The app's own default when ``the_one`` imports, else the per-OS computation."""
    try:
        from the_one.config import _default_data_dir  # type: ignore[import-not-found]

        return Path(_default_data_dir())
    except Exception:  # noqa: BLE001 - the runner has no repo environment
        return platformdirs_default()


def check_safety(
    base_url: str,
    data_dir: Path,
    refuse: list[Path],
    default: Path,
    *,
    rotate_if_missing: bool,
) -> None:
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SeedError(f"--base-url must be an absolute http(s) URL, got {base_url!r}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port in FORBIDDEN_PORTS:
        raise SeedError(f"refusing port {port}: that is {FORBIDDEN_PORTS[port]}.")
    target = Path(data_dir).resolve()
    default_dir = Path(default).resolve()
    if target == default_dir or target.is_relative_to(default_dir):
        raise SeedError(
            f"refusing {target}: it is, or lies inside, the default data directory "
            f"{default_dir}; use a scratch one."
        )
    for extra in refuse:
        extra_dir = Path(extra).resolve()
        if target == extra_dir or target.is_relative_to(extra_dir):
            raise SeedError(f"refusing {target}: it is, or lies inside, a --refuse-data-dir.")
    if not (target / "api-credential").is_file() and not rotate_if_missing:
        raise SeedError(
            f"no credential at {target / 'api-credential'} "
            "(start the instance, or pass --rotate-if-missing for a serve instance)."
        )


def urllib_transport(method: str, url: str, headers: dict[str, str], body: Any):
    data = None if body is None else json.dumps(body).encode()
    hdrs = dict(headers)
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - checked http(s)
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    try:
        return status, (json.loads(raw) if raw else None)
    except ValueError:
        return status, None


def subprocess_runner(argv: list[str], env: dict[str, str]) -> int:
    return subprocess.run(argv, env={**os.environ, **env}, timeout=120).returncode


class Client:
    def __init__(self, base_url: str, credential: str, transport: Transport):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {credential}"}
        self.transport = transport

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        return self.transport(method, self.base + path, self.headers, body)


def read_credential(data_dir: Path) -> str:
    return (Path(data_dir) / "api-credential").read_text().strip()


def seed(client: Client, *, wait_s: float, sleep: Callable[[float], None]) -> dict[str, Any]:
    status, info = client.call("GET", "/api/config")
    if status != 200 or not isinstance(info, dict):
        raise SeedError(f"GET /api/config answered {status}")
    if not info.get("dev_mode"):
        raise SeedError("the instance is not in dev mode (THE_ONE_DEV_MODE=true): no mock provider")
    status, providers = client.call("GET", "/api/providers")
    if status != 200 or not isinstance(providers, list):
        raise SeedError(f"GET /api/providers answered {status}")
    for p in providers:
        if p.get("name") == PROVIDER_NAME:
            client.call("DELETE", f"/api/providers/{p['id']}?force=true")
    status, created = client.call(
        "POST",
        "/api/providers",
        {
            "name": PROVIDER_NAME,
            "type": "mock",
            "base_url": "",
            "config": {"models": ["mock-default"], "responses": RESPONSES},
        },
    )
    if status != 201 or not isinstance(created, dict):
        raise SeedError(f"POST /api/providers answered {status}")
    provider_id = created["id"]
    status, _ = client.call(
        "PUT",
        "/api/gleepglorp",
        {
            "enabled": True,
            "provider_config_id": provider_id,
            "model": "mock-default",
            "web_access": False,
            "memory": False,
            "retention_days": 30,
        },
    )
    if status != 200:
        raise SeedError(f"PUT /api/gleepglorp answered {status}")
    deadline = time.monotonic() + wait_s
    state = None
    while True:
        status, body = client.call("GET", "/api/gleepglorp")
        state = body.get("state") if isinstance(body, dict) else None
        if state == "ready" or time.monotonic() >= deadline:
            break
        sleep(0.5)
    if state != "ready":
        raise SeedError(f"GleepGlorp state is {state!r}, not 'ready'")
    return {
        "provider_id": provider_id,
        "dev_mode": True,
        "gleepglorp_state": state,
        "message_to_send": MESSAGE_TO_SEND,
    }


def check_fill(client: Client) -> tuple[int, dict[str, Any]]:
    """Exit code 0 iff the newest fill is ``filled`` and no agent named AGENT_NAME exists."""
    status, sessions = client.call("GET", "/api/chat/sessions")
    if status != 200 or not isinstance(sessions, list):
        return 1, {"error": f"GET /api/chat/sessions answered {status}"}
    newest: dict[str, Any] | None = None
    for s in sessions:
        if s.get("agent_name") != "GleepGlorp":
            continue
        sid = urllib.parse.quote(str(s["id"]), safe="")
        status, body = client.call("GET", f"/api/gleepglorp/fills?session_id={sid}")
        if status != 200 or not isinstance(body, dict):
            continue
        for fill in body.get("fills", []):
            if newest is None or fill.get("id", 0) > newest.get("id", 0):
                newest = fill
    status, agents = client.call("GET", "/api/agents")
    names = [a.get("name") for a in agents] if status == 200 and isinstance(agents, list) else None
    exists = AGENT_NAME in names if names is not None else None
    fill_status = newest.get("status") if newest else None
    report = {"fill_status": fill_status, "agent_exists": exists}
    ok = fill_status == "filled" and exists is False
    return (0 if ok else 1), report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--base-url", required=True)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--rotate-if-missing", action="store_true")
    p.add_argument("--refuse-data-dir", action="append", default=[], metavar="PATH")
    p.add_argument("--check-fill", action="store_true")
    p.add_argument("--wait", type=float, default=15.0, help="seconds to wait for state ready")
    p.add_argument("--the-one-cmd", default="the-one", help="the-one executable (rotation only)")
    return p


def main(
    argv: list[str] | None = None,
    *,
    transport: Transport = urllib_transport,
    runner: Runner = subprocess_runner,
    default: Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    args = build_parser().parse_args(argv)
    data_dir = Path(args.data_dir)
    try:
        check_safety(
            args.base_url,
            data_dir,
            [Path(x) for x in args.refuse_data_dir],
            default if default is not None else default_data_dir(),
            rotate_if_missing=args.rotate_if_missing,
        )
        cred_file = data_dir / "api-credential"
        if not cred_file.is_file():
            rc = runner(
                [args.the_one_cmd, "rotate-api-credential"], {"THE_ONE_DATA_DIR": str(data_dir)}
            )
            if rc != 0 or not cred_file.is_file():
                raise SeedError(f"rotate-api-credential failed (exit {rc}) or wrote no credential")
        client = Client(args.base_url, read_credential(data_dir), transport)
        if args.check_fill:
            code, report = check_fill(client)
            print(json.dumps(report))
            return code
        print(json.dumps(seed(client, wait_s=args.wait, sleep=sleep)))
        return 0
    except SeedError as e:
        print(f"gleepglorp_drawer_seed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
