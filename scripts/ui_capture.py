#!/usr/bin/env python3
"""UI capture tool (Mission 31 Flight 1, DD10): before/after evidence PNGs.

Starts its OWN scratch dev instance (port 8490 or higher, a fresh data directory
under ``$HOME``, a scratch cwd, dev mode on), seeds it through the API, opens named
UI surfaces in a pinned browser environment (viewport, theme, time zone, locale,
fixed clock) in both themes and writes ``<surface>--light.png`` / ``--dark.png`` plus
``manifest.json`` to ``--out``.

The output is local flight-log evidence and is NEVER committed: ``--out`` inside the
repo is refused, and the operator approves each flight's set at the HAT.

Refusals (``check_capture_safety``): ports 8484/8485 and anything below 8490; a data
dir equal to, inside or containing the platformdirs default data dir or any
``THE_ONE_DATA_DIR`` named in the environment or the repo's ``.env``; an out dir
inside the repo.

``THE_ONE_TEST_NETNS=1`` re-runs the whole script inside a loopback-only network
namespace (``unshare -rn``, ``lo`` up) before anything starts, as
``scripts/run-tests.sh`` does: Chromium under WSL mirrored networking otherwise
aborts loopback requests with ``ERR_NETWORK_CHANGED``.

    THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out DIR
    .venv/bin/python scripts/ui_capture.py --list
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_PORT = 8490
FORBIDDEN_PORTS = {
    8484: "the operator's production instance",
    8485: "the Flight Director's preview instance",
}
NETNS_SENTINEL = "THE_ONE_UI_CAPTURE_IN_NETNS"
VIEWPORT = {"width": 1440, "height": 900}
THEMES = ("light", "dark")
FIXED_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
# The server stamps a plan token with the real clock; the capture rewrites the
# stamp so the "expires around" line is identical between runs (DD10 clock rule).
TOKEN_SET_AT = "2026-02-20T12:00:00+00:00"
TOKEN_EXPIRES_AROUND = "2027-02-20T12:00:00+00:00"
FIXED_CONSENT_URL = (
    "https://claude.ai/oauth/authorize?code=true&client_id=capture-fixed"
    "&response_type=code&state=capture-fixed-state&code_challenge=capture-fixed"
)

OLLAMA_CATALOG = {
    "models": [
        {"name": "llama3.2:1b", "size": 1321098329, "status": "ok"},
        {"name": "llama3.2:3b", "size": 2019377376, "status": "ok"},
        {"name": "nomic-embed-text", "size": 274302915, "status": "ok"},
    ]
}
# What the stubbed Ollama server reports: two installed models, one loaded.
OLLAMA_MODELS = [
    {"name": "llama3.2:1b", "size": 1321098329, "capabilities": ["completion", "tools"]},
    {"name": "llama3.2:3b", "size": 2019377376, "capabilities": ["completion"]},
    {"name": "nomic-embed-text", "size": 274302915, "capabilities": ["embedding"]},
]
OLLAMA_RUNNING = [{"name": "llama3.2:1b", "size": 1321098329, "size_vram": 1500000000}]
GENERIC_MODELS = [
    {"id": "model-one", "name": "model-one"},
    {"id": "model-two", "name": "model-two"},
]

# type -> (display name, POST body fields). Dummy keys and URLs only.
PROVIDERS: dict[str, tuple[str, dict]] = {
    "ollama": ("Capture Ollama", {"base_url": "http://127.0.0.1:11434"}),
    "openai-compatible": (
        "Capture OpenAI-compatible",
        {"base_url": "http://127.0.0.1:1234/v1", "api_key": "sk-capture-dummy"},
    ),
    "openai": ("Capture OpenAI", {"base_url": "https://api.openai.com/v1", "api_key": "sk-dummy"}),
    "anthropic": (
        "Capture Anthropic",
        {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-dummy"},
    ),
    "anthropic-plan": ("Capture Claude Plan", {"base_url": "https://api.anthropic.com"}),
    "anthropic-plan-token": (
        "Capture Claude Token",
        {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-oat01-capture-dummy"},
    ),
    "openrouter": (
        "Capture OpenRouter",
        {"base_url": "https://openrouter.ai/api/v1", "api_key": "sk-or-dummy"},
    ),
    "mock": (
        "Capture Mock",
        {"base_url": "http://mock.invalid", "config": {"models": ["mock-default", "mock-large"]}},
    ),
}
FLASH_PROVIDER = (
    "Capture Flash demo",
    {"base_url": "http://mock.invalid", "config": {"models": ["mock-default"]}},
)


class CaptureError(Exception):
    """A refusal or environment failure; the message goes to stderr, exit 2."""


# ── Safety ───────────────────────────────────────────────────────────────────


def _inside_or_equal(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


def check_capture_safety(
    port: int,
    data_dir: Path,
    out_dir: Path,
    default_dir: Path,
    env_data_dirs: list[Path],
    repo_root: Path,
) -> None:
    """Raise CaptureError when the run would touch a protected port, data
    directory or the repo. All path comparisons happen after ``resolve()``."""
    if port in FORBIDDEN_PORTS:
        raise CaptureError(f"refusing port {port}: that is {FORBIDDEN_PORTS[port]}.")
    if port < MIN_PORT:
        raise CaptureError(f"refusing port {port}: capture instances use {MIN_PORT} or higher.")
    protected = [("the default data directory", default_dir)]
    protected += [("a THE_ONE_DATA_DIR from the environment or .env", d) for d in env_data_dirs]
    for label, protected_dir in protected:
        if _inside_or_equal(data_dir, protected_dir) or _inside_or_equal(protected_dir, data_dir):
            raise CaptureError(
                f"refusing data directory {data_dir}: it is, is inside, or contains {label} "
                f"({protected_dir}). Use a scratch directory."
            )
    if _inside_or_equal(out_dir, repo_root):
        raise CaptureError(
            f"refusing --out {out_dir}: it is inside the repo ({repo_root}). Captures are "
            "local evidence and are never committed; write them outside the repo."
        )


def collect_env_data_dirs(environ: dict[str, str], repo_root: Path) -> list[Path]:
    """THE_ONE_DATA_DIR values from the environment and the repo's ``.env``, parsed
    as text (the app's settings are never imported in this process)."""
    found: list[Path] = []
    value = environ.get("THE_ONE_DATA_DIR")
    if value:
        found.append(Path(value).expanduser())
    env_file = repo_root / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, sep, val = line.partition("=")
            if sep and key.strip() == "THE_ONE_DATA_DIR":
                val = val.strip().strip("'\"")
                if val:
                    found.append(Path(val).expanduser())
    return found


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "webkitgtk_probe", REPO_ROOT / "scripts" / "webkitgtk_probe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def default_data_dir() -> Path:
    """The platformdirs default, derived by the app itself (never a literal)."""
    probe = _load_probe()
    try:
        return probe.default_data_dir()
    except probe.ProbeError as exc:
        raise CaptureError(str(exc)) from exc


# ── Surface table ────────────────────────────────────────────────────────────


@dataclass
class Ctx:
    """What a surface's prepare step can use."""

    page: object
    base_url: str
    ids: dict[str, str]  # provider type -> id; "flash" -> flash-demo provider id
    theme: str


@dataclass
class Surface:
    name: str
    hash: str  # may contain {type} / {flash} placeholders resolved from ids
    ready: str  # CSS selector for the settled state
    description: str
    prepare: Callable[[Ctx], None] | None = None
    shot: str | None = None  # CSS selector of an element to shoot instead of the viewport
    stubs: tuple[str, ...] = ("models",)
    skipped: str | None = None


def _ollama_stubs(page) -> None:
    page.route(
        "**/api/providers/*/models",
        lambda r: r.fulfill(json=OLLAMA_MODELS) if r.request.method == "GET" else r.continue_(),
    )
    page.route("**/api/providers/*/models/status", lambda r: r.fulfill(json=OLLAMA_RUNNING))


def _stub_test(status: str, detail: str):
    def prepare(ctx: Ctx) -> None:
        ctx.page.route(
            "**/api/providers/*/test",
            lambda r: r.fulfill(json={"status": status, "detail": detail}),
        )
        ctx.page.locator('[data-testid="test-connection-btn"]').click()
        result = ctx.page.locator(
            '[data-testid="provider-test-result"]:not([data-state="pending"])'
        )
        result.wait_for(timeout=10000)
        result.scroll_into_view_if_needed()

    return prepare


def _plan_awaiting_code(ctx: Ctx) -> None:
    page = ctx.page
    page.locator('[data-testid="plan-signin-btn"]').click()
    page.locator('[data-testid="plan-signin-consent"]').wait_for(timeout=10000)
    # The authorize URL carries a random state and challenge; pin it.
    page.evaluate(
        "u => { const i = document.querySelector('[data-testid=\"plan-signin-url\"]');"
        " if (i) i.value = u; }",
        FIXED_CONSENT_URL,
    )
    for extra in page.context.pages:  # the aborted claude.ai popup, if one opened
        if extra is not page:
            extra.close()


def _flash_after_save(ctx: Ctx) -> None:
    page = ctx.page
    page.locator("#pf-name").fill("Capture Flash demo (edited)")
    save = page.locator('[data-testid="save-provider-btn"]')
    save.click()
    page.locator(".app-flash.visible").wait_for(timeout=10000)


SURFACES: list[Surface] = []
for _type in PROVIDERS:
    SURFACES.append(
        Surface(
            name=f"provider-edit-{_type}",
            hash=f"#library/providers/{{{_type}}}",
            ready='[data-testid="save-provider-btn"]',
            description=f"Provider editor, edit mode, {_type}",
            stubs=("ollama",) if _type == "ollama" else ("models",),
        )
    )
SURFACES += [
    Surface(
        "provider-create",
        "#library/providers/~new",
        '[data-testid="save-provider-btn"]',
        "Provider editor, create mode",
    ),
    Surface(
        "ollama-models-panel",
        "#library/providers/{ollama}",
        ".admin-pf-model-row",
        "Ollama models panel: one loaded, two available, stubbed",
        shot=".provider-models",
        stubs=("ollama",),
    ),
    Surface(
        "provider-test-ok",
        "#library/providers/{openai-compatible}",
        '[data-testid="test-connection-btn"]',
        "Provider Test result, ok (stubbed)",
        prepare=_stub_test("ok", "Connected: 2 models available"),
    ),
    Surface(
        "provider-test-failed",
        "#library/providers/{openai-compatible}",
        '[data-testid="test-connection-btn"]',
        "Provider Test result, failed (stubbed)",
        prepare=_stub_test("error", "Connection refused: http://127.0.0.1:1234/v1"),
    ),
    Surface(
        "plan-signin-awaiting-code",
        "#library/providers/{anthropic-plan}",
        '[data-testid="plan-signin-btn"]',
        "Claude Plan (OAuth) sign-in block, awaiting the pasted code",
        prepare=_plan_awaiting_code,
        shot=".admin-pf-plan-signin",
    ),
    Surface(
        "plan-token-expiry",
        "#library/providers/{anthropic-plan-token}",
        '[data-testid="provider-token-expiry"]',
        "Claude Plan (Token) editor with the 'expires around' line (stamp and clock pinned)",
    ),
    Surface(
        "flash-after-save",
        "#library/providers/{flash}",
        '[data-testid="save-provider-btn"]',
        "The flash shown after a Save",
        prepare=_flash_after_save,
    ),
    Surface(
        "chat-consent-link",
        "",
        "",
        "The sign-in consent link in a chat",
        skipped="leg 05's change is click feedback, which a static capture does not show",
    ),
    Surface(
        "mcp-consent-link",
        "",
        "",
        "The sign-in consent link in the MCP editor",
        skipped="leg 05's change is click feedback, which a static capture does not show",
    ),
]


def print_table() -> None:
    for s in SURFACES:
        tail = f"  SKIPPED: {s.skipped}" if s.skipped else ""
        print(f"{s.name:34} {s.hash or '-':44} {s.description}{tail}")


# ── Instance ─────────────────────────────────────────────────────────────────


def pick_port() -> int:
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port >= MIN_PORT and port not in FORBIDDEN_PORTS:
            return port
    raise CaptureError("could not find a free port of 8490 or higher")


def write_credential(data_dir: Path) -> str:
    """The long-lived local-API credential, written before the server starts
    (same sequence as tests/browser/conftest.py::_write_credential)."""
    token = f"loc_{secrets.token_hex(8)}.{secrets.token_hex(32)}"
    path = data_dir / "api-credential"
    tmp = path.with_name(f"{path.name}.tmp.{secrets.token_hex(4)}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, token.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    return token


def _api(base: str, token: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - loopback
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise CaptureError(f"{method} {path} -> {exc.code}: {exc.read()[:300]!r}") from exc


def start_instance(port: int, data_dir: Path, cwd: Path, log: Path):
    data_dir.mkdir(parents=True)
    cwd.mkdir(parents=True, exist_ok=True)
    token = write_credential(data_dir)
    env = os.environ.copy()
    for key in [k for k in env if k.startswith("THE_ONE_") and k != NETNS_SENTINEL]:
        del env[key]
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    env["THE_ONE_OLLAMA_LIBRARY_TEST_JSON"] = json.dumps(OLLAMA_CATALOG)
    logf = open(log, "wb")  # noqa: SIM115 - closed by the caller via proc lifetime
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "the_one.interfaces.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        cwd=cwd,
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise CaptureError(f"the scratch instance exited early; see {log}")
        try:
            with urllib.request.urlopen(base + "/api/live", timeout=2):  # noqa: S310
                return base, proc, token
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    stop_instance(proc)
    raise CaptureError(f"the scratch instance did not become ready; see {log}")


def stop_instance(proc: subprocess.Popen) -> None:
    """Stop by the recorded PID only."""
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def seed(base: str, token: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    for ptype, (name, fields) in PROVIDERS.items():
        row = _api(base, token, "POST", "/api/providers", {"name": name, "type": ptype, **fields})
        ids[ptype] = row["id"]
    name, fields = FLASH_PROVIDER
    ids["flash"] = _api(
        base, token, "POST", "/api/providers", {"name": name, "type": "mock", **fields}
    )["id"]
    _api(
        base,
        token,
        "POST",
        "/api/agents",
        {
            "name": "Capture agent",
            "provider_config_id": ids["mock"],
            "llm_model": "mock-default",
            "system_prompt": "You are a capture-seed agent.",
        },
    )
    return ids


# ── Capture ──────────────────────────────────────────────────────────────────


def _patch_token_rows(route) -> None:
    resp = route.fetch()
    try:
        data = resp.json()
    except ValueError:
        route.fulfill(response=resp)
        return
    rows = data if isinstance(data, list) else [data]
    for row in rows:
        if isinstance(row, dict) and row.get("type") == "anthropic-plan-token":
            if row.get("token_set_at"):
                row["token_set_at"] = TOKEN_SET_AT
                row["token_expires_around"] = TOKEN_EXPIRES_AROUND
    route.fulfill(response=resp, json=data)


def capture_one(
    browser, base: str, token: str, ids: dict[str, str], s: Surface, theme: str, out: Path
):
    context = browser.new_context(
        viewport=VIEWPORT,
        timezone_id="UTC",
        locale="en-US",
        color_scheme=theme,
        device_scale_factor=1,
    )
    try:
        context.add_init_script(
            "try { localStorage.setItem('theme-preference', %s); } catch (e) {}" % json.dumps(theme)
        )
        context.route("https://claude.ai/**", lambda r: r.abort())
        # A handoff per context (single-use), through the context's request API.
        r = context.request.post(
            base + "/api/session/handoff", headers={"Authorization": f"Bearer {token}"}
        )
        if not r.ok:
            raise CaptureError(f"{s.name}: handoff mint failed ({r.status})")
        landing = context.request.get(r.json()["url"])
        if not landing.ok:
            raise CaptureError(f"{s.name}: handoff redemption failed ({landing.status})")
        page = context.new_page()
        page.clock.set_fixed_time(FIXED_NOW)
        page.route("**/api/providers", _patch_token_rows)
        page.route("**/api/providers/*", lambda r: _patch_or_continue(r))
        if "ollama" in s.stubs:
            _ollama_stubs(page)
        else:
            page.route(
                "**/api/providers/*/models",
                lambda r: (
                    r.fulfill(json=GENERIC_MODELS) if r.request.method == "GET" else r.continue_()
                ),
            )
        route_hash = s.hash
        for key, value in ids.items():
            route_hash = route_hash.replace("{" + key + "}", value)
        page.goto(base + "/" + route_hash)
        page.locator(s.ready).first.wait_for(state="visible", timeout=20000)
        text = page.locator("body").inner_text()
        if "Unauthorized" in text or '"detail"' in text[:200]:
            raise CaptureError(f"{s.name}: the page is the unauthenticated state")
        if s.prepare:
            s.prepare(Ctx(page, base, ids, theme))
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(500)  # transitions settle; the flash is visible for 5 s
        target = out / f"{s.name}--{theme}.png"
        if s.shot:
            page.locator(s.shot).first.screenshot(path=str(target), animations="disabled")
        else:
            # The shell scrolls inside panes, so a full-page shot needs a taller viewport:
            # grow it by the largest hidden overflow, then shoot the whole page.
            excess = page.evaluate(
                "() => Math.max(0, ...Array.from(document.querySelectorAll('*')).filter("
                "e => e.scrollHeight > e.clientHeight + 1 && /(auto|scroll)/.test("
                "getComputedStyle(e).overflowY)).map(e => e.scrollHeight - e.clientHeight))"
            )
            if excess:
                page.set_viewport_size(
                    {"width": VIEWPORT["width"], "height": VIEWPORT["height"] + excess}
                )
                page.wait_for_timeout(300)
            page.screenshot(path=str(target), animations="disabled", full_page=True)
        return target
    finally:
        context.close()
        if s.name == "flash-after-save":  # undo the rename so the next theme starts clean
            name, fields = FLASH_PROVIDER
            _api(
                base,
                token,
                "PUT",
                f"/api/providers/{ids['flash']}",
                {"name": name, "type": "mock", **fields},
            )


def _patch_or_continue(route) -> None:
    if (
        route.request.method == "GET"
        and route.request.url.rstrip("/").count("/api/providers/") == 1
    ):
        tail = route.request.url.split("/api/providers/", 1)[1]
        if "/" not in tail.split("?")[0]:
            _patch_token_rows(route)
            return
    route.fallback()


# ── CLI ──────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", help="output directory (outside the repo; empty unless --force)")
    p.add_argument("--surfaces", help="comma-separated surface names to capture")
    p.add_argument("--list", action="store_true", help="print the surface table and exit")
    p.add_argument("--keep", action="store_true", help="keep the scratch data tree")
    p.add_argument("--force", action="store_true", help="allow a non-empty --out")
    return p.parse_args(argv)


def maybe_reexec_in_netns(argv: list[str]) -> None:
    if os.environ.get("THE_ONE_TEST_NETNS") != "1" or os.environ.get(NETNS_SENTINEL):
        return
    probe = subprocess.run(
        ["unshare", "-rn", "sh", "-c", "ip link set lo up"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        raise CaptureError(
            "THE_ONE_TEST_NETNS=1 but 'unshare -rn' + 'ip link set lo up' is unavailable here "
            "(need util-linux unshare, iproute2 ip, unprivileged user namespaces). "
            "Unset THE_ONE_TEST_NETNS to run without isolation."
        )
    print("ui_capture: re-running in an isolated loopback-only network namespace", file=sys.stderr)
    env = dict(os.environ, **{NETNS_SENTINEL: "1"})
    os.execvpe(
        "unshare",
        ["unshare", "-rn", "sh", "-c", 'ip link set lo up && exec "$@"', "sh", sys.executable]
        + [str(Path(__file__).resolve())]
        + argv,
        env,
    )


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.list:
        print_table()
        return 0
    if not args.out:
        raise CaptureError("--out DIR is required")
    out = Path(args.out).expanduser().resolve()
    # Refusals that need nothing started come before the namespace re-run.
    port = pick_port()
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    scratch = Path.home() / ".cache" / "the-one-ui-capture" / run_id
    data_dir = scratch / "data"
    check_capture_safety(
        port,
        data_dir,
        out,
        default_data_dir(),
        collect_env_data_dirs(dict(os.environ), REPO_ROOT),
        REPO_ROOT,
    )
    if out.exists() and any(out.iterdir()) and not args.force:
        raise CaptureError(f"--out {out} is not empty; pass --force to write into it")
    maybe_reexec_in_netns(argv)

    wanted = [n.strip() for n in args.surfaces.split(",")] if args.surfaces else None
    known = {s.name for s in SURFACES}
    if wanted and (unknown := [n for n in wanted if n not in known]):
        raise CaptureError(f"unknown surface(s): {', '.join(unknown)} (see --list)")
    todo = [s for s in SURFACES if wanted is None or s.name in wanted]

    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    proc = None
    captured: list[str] = []
    failed: list[dict] = []
    try:
        base, proc, token = start_instance(port, data_dir, scratch / "cwd", scratch / "serve.log")
        ids = seed(base, token)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for s in todo:
                    if s.skipped:
                        continue
                    for theme in THEMES:
                        try:
                            path = capture_one(browser, base, token, ids, s, theme, out)
                            captured.append(path.name)
                            print(f"captured {path.name}")
                        except Exception as exc:  # keep going; report at the end
                            failed.append(
                                {"surface": s.name, "theme": theme, "error": str(exc)[:300]}
                            )
                            print(f"FAILED {s.name}--{theme}: {str(exc)[:200]}", file=sys.stderr)
            finally:
                browser.close()
    finally:
        if proc is not None:
            stop_instance(proc)
        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)
    skipped = [{"surface": s.name, "reason": s.skipped} for s in todo if s.skipped]
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_status": _git("status", "--short").splitlines(),
        "viewport": VIEWPORT,
        "full_page": True,
        "themes": list(THEMES),
        "time_zone": "UTC",
        "locale": "en-US",
        "fixed_clock": FIXED_NOW.isoformat(),
        "captured": captured,
        "failed": failed,
        "skipped": skipped,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for item in skipped:
        print(f"SKIPPED {item['surface']}: {item['reason']}")
    print(f"{len(captured)} PNGs, {len(failed)} failed, {len(skipped)} skipped -> {out}")
    return 1 if failed else 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except CaptureError as exc:
        print(f"ui_capture: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
