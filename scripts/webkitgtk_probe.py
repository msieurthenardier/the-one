#!/usr/bin/env python3
"""WebKitGTK probe: run the shared a11y resolver in the real desktop engine.

M25 F1 L1 (DD9). Runs with SYSTEM python (``/usr/bin/python3``) because only it
has ``gi`` + WebKit2 4.1; the repo venv has neither. ``gi`` imports live inside
``main()`` so the module imports anywhere (and ruff E402 stays quiet).

    /usr/bin/python3 scripts/webkitgtk_probe.py \\
        --url 'http://127.0.0.1:8485/#admin/design-language' \\
        --data-dir /tmp/the-one-probe-scratch \\
        --root-selector '[data-ui-demo]' --theme dark

Safety: this tool authenticates with the long-lived credential in ``--data-dir``.
It REFUSES port 8484 and the platformdirs default data directory (the operator's
production instance; squawk 0084). Drive a dev instance instead:
``THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> THE_ONE_DEV_MODE=true make up``.

The page is loaded with an ephemeral website data manager (no stale ``?v=``
cache between runs, squawk 0085) and a pinned, recorded environment. It prints
one JSON object and exits 0 iff ``ok``. A hard timeout stops a wedged WebView.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOLVER_JS = REPO_ROOT / "tests" / "browser" / "_a11y_resolve.js"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
FORBIDDEN_PORT = 8484


class ProbeError(Exception):
    """A refusal or environment failure; the message goes to stderr, exit 2."""


def default_data_dir() -> Path:
    """The platformdirs default data dir, derived by the app itself (never
    hardcoded) with ``THE_ONE_DATA_DIR`` removed from the child environment."""
    if not VENV_PYTHON.exists():
        raise ProbeError(
            f"cannot derive the default data dir: {VENV_PYTHON} missing "
            "(refusing to run unverified)"
        )
    env = {k: v for k, v in os.environ.items() if k != "THE_ONE_DATA_DIR"}
    proc = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            "from the_one.config import settings; print(settings.data_dir)",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=60,
    )
    lines = proc.stdout.strip().splitlines()
    if proc.returncode != 0 or not lines:
        raise ProbeError(f"cannot derive the default data dir: {proc.stderr.strip()[-300:]}")
    return Path(lines[-1]).resolve()


def check_safety(url: str, data_dir: Path, default_dir: Path | None = None) -> None:
    """Raise ProbeError when ``url`` targets port 8484 or ``data_dir`` is the
    platformdirs default (compared after ``Path.resolve()``)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ProbeError(f"--url must be an absolute http(s) URL, got {url!r}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port == FORBIDDEN_PORT:
        raise ProbeError(
            f"refusing port {FORBIDDEN_PORT}: that is the operator's production instance. "
            "Use a dev instance (THE_ONE_PORT=8485 + scratch THE_ONE_DATA_DIR)."
        )
    target = Path(data_dir).resolve()
    default = default_dir if default_dir is not None else default_data_dir()
    if target == default.resolve():
        raise ProbeError(
            f"refusing the default data directory {target}: use a scratch THE_ONE_DATA_DIR."
        )


def mint_handoff_url(origin: str, data_dir: Path) -> str:
    cred_file = Path(data_dir) / "api-credential"
    if not cred_file.is_file():
        raise ProbeError(f"no credential at {cred_file} (start the dev instance first)")
    credential = cred_file.read_text().strip()
    req = urllib.request.Request(
        origin + "/api/session/handoff",
        method="POST",
        headers={"Authorization": f"Bearer {credential}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - http(s) checked
            return json.load(resp)["url"]
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise ProbeError(f"handoff mint failed at {origin}: {exc}") from exc


def pin_environment() -> dict[str, str]:
    """Choose and record the display/render env BEFORE gi/Gtk is imported."""
    backend = "x11" if os.environ.get("DISPLAY") else "wayland"
    os.environ["GDK_BACKEND"] = backend
    os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
    return {
        "GDK_BACKEND": backend,
        "WEBKIT_DISABLE_DMABUF_RENDERER": "1",
        "hardware_acceleration_policy": "never",
        "DISPLAY": os.environ.get("DISPLAY", ""),
        "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", ""),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", required=True, help="app URL; its #hash is the route to render")
    ap.add_argument("--data-dir", required=True, type=Path, help="scratch data dir of the instance")
    ap.add_argument("--root-selector", default="body")
    ap.add_argument("--theme", choices=("dark", "light"), default="dark")
    ap.add_argument(
        "--setup-script",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help=(
            "JS file run in the page after load and the hash route, before the\n"
            "root-selector poll; repeatable, run in order. Each file is wrapped so it\n"
            "completes with true (never a DOM node)."
        ),
    )
    ap.add_argument("--timeout", type=int, default=60, help="hard timeout, seconds (default 60)")
    return ap.parse_args(argv)


def load_setup_scripts(paths: list[Path]) -> list[str]:
    """Validate every ``--setup-script`` path is an existing file (before any
    WebView is built) and return each script wrapped as a sync expression whose
    completion value is ``true`` (``to_json`` on a DOM node would abort the run)."""
    wrapped: list[str] = []
    for path in paths:
        if not Path(path).is_file():
            raise ProbeError(f"--setup-script {path} is not an existing file")
        wrapped.append("(function () {\n" + Path(path).read_text() + "\n;return true;\n})()")
    return wrapped


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        check_safety(args.url, args.data_dir)
        setup_scripts = load_setup_scripts(args.setup_script)
        parts = urlsplit(args.url)
        origin = f"{parts.scheme}://{parts.netloc}"
        handoff_url = mint_handoff_url(origin, args.data_dir)
    except ProbeError as exc:
        print(f"webkitgtk_probe: {exc}", file=sys.stderr)
        return 2
    env = pin_environment()
    resolver = RESOLVER_JS.read_text()

    import gi  # noqa: PLC0415 - must follow pin_environment()

    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    gi.require_version("JavaScriptCore", "4.1")
    from gi.repository import GLib, Gtk, WebKit2  # noqa: PLC0415

    if not Gtk.init_check()[0]:
        print("webkitgtk_probe: Gtk could not open a display (WSLg unavailable?)", file=sys.stderr)
        return 2

    out: dict = {
        "engine_version": (
            f"WebKitGTK {WebKit2.get_major_version()}."
            f"{WebKit2.get_minor_version()}.{WebKit2.get_micro_version()}"
        ),
        "env": env,
        "theme": args.theme,
        "url": args.url,
        "root_selector": args.root_selector,
        "results": None,
        "ok": False,
    }
    state = {"phase": "load", "polls": 0, "error": None}

    data_manager = WebKit2.WebsiteDataManager.new_ephemeral()
    context = WebKit2.WebContext.new_with_website_data_manager(data_manager)
    content = WebKit2.UserContentManager()
    content.add_script(
        WebKit2.UserScript(
            "try { localStorage.setItem('theme-preference', %s); } catch (e) {}"
            % json.dumps(args.theme),
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
    )
    view = WebKit2.WebView(web_context=context, user_content_manager=content)
    view.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
    window = Gtk.Window(title="webkitgtk-probe")
    window.set_default_size(1280, 900)
    window.add(view)
    window.show_all()

    def finish(error: str | None = None) -> None:
        if error and not state["error"]:
            state["error"] = error
        Gtk.main_quit()

    def run_js(script: str, callback) -> None:
        def done(source, result, _data=None):
            try:
                value = source.evaluate_javascript_finish(result)
                callback(json.loads(value.to_json(0)) if value is not None else None)
            except Exception as exc:  # noqa: BLE001 - reported in JSON
                finish(f"javascript evaluation failed: {exc}")

        view.evaluate_javascript(script, -1, None, None, None, done)

    def on_checked(result) -> None:
        out["results"] = result
        out["ok"] = bool(result and result.get("ok"))
        # A setup script may leave a JSON-serialisable observation on
        # window.__probeReport; it is echoed back as "report".
        run_js("window.__probeReport === undefined ? null : window.__probeReport", on_report)

    def on_report(report) -> None:
        if report is not None:
            out["report"] = report
        finish()

    def poll() -> bool:
        state["polls"] += 1
        sel = json.dumps(args.root_selector)

        def got(count) -> None:
            if count:
                run_js(f"({resolver})({sel})", on_checked)
            else:
                GLib.timeout_add(250, poll)

        run_js(f"document.querySelectorAll({sel}).length", got)
        return False

    def run_setup(index: int) -> None:
        if index >= len(setup_scripts):
            poll()
            return
        state["phase"] = f"setup-{index + 1}"

        def done(result) -> None:
            if result is not True:
                finish(f"setup script {index + 1} did not complete with true: {result!r}")
                return
            out.setdefault("setup_scripts", []).append(str(args.setup_script[index]))
            run_setup(index + 1)

        run_js(setup_scripts[index], done)

    def on_load(_view, event) -> None:
        if event != WebKit2.LoadEvent.FINISHED or state["phase"] != "load":
            return
        state["phase"] = "render"
        out["actual_theme"] = None

        def themed(theme) -> None:
            out["actual_theme"] = theme
            if theme != args.theme:
                finish(f"data-theme is {theme!r}, expected {args.theme!r}")
                return
            run_setup(0)

        # The handoff redirect stripped the query; the hash route renders client-side.
        route = json.dumps(parts.fragment)
        run_js(
            f"(function(){{ location.hash = {route};"
            " return document.documentElement.dataset.theme; })()",
            themed,
        )

    view.connect("load-changed", on_load)

    def on_timeout() -> bool:
        finish(f"hard timeout after {args.timeout}s in phase {state['phase']!r}")
        return False

    GLib.timeout_add_seconds(args.timeout, on_timeout)
    view.load_uri(handoff_url)
    Gtk.main()

    if state["error"]:
        out["error"] = state["error"]
        out["ok"] = False
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
