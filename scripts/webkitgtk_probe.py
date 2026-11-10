#!/usr/bin/env python3
"""WebKitGTK probe: run the shared a11y resolver in the real desktop engine.

M25 F1 L1 (DD9). Runs with SYSTEM python (``/usr/bin/python3``) because only it
has ``gi`` + WebKit2 4.1; the repo venv has neither. ``gi`` imports live inside
``main()`` so the module imports anywhere (and ruff E402 stays quiet).

    /usr/bin/python3 scripts/webkitgtk_probe.py \\
        --url 'http://127.0.0.1:8486/#settings/appearance' \\
        --data-dir /tmp/the-one-probe-scratch \\
        --root-selector 'main' --theme dark

Safety: this tool authenticates with the long-lived credential in ``--data-dir``.
It REFUSES port 8484 and the platformdirs default data directory (the operator's
production instance; squawk 0084), and port 8485 (the Flight Director's preview
instance, M25 F4 DD13). Drive a dev instance on 8486 or higher instead:
``THE_ONE_PORT=8486 THE_ONE_DATA_DIR=<scratch> THE_ONE_DEV_MODE=true make up``.

Key injection (M25 F4 L7, DD9): ``--press-keys ctrl+k`` sends a REAL GTK key event
to the focused WebView after the setup scripts, optionally after focusing
``--focus-selector`` in the page, then polls ``--assert-selector`` (for example
``[data-testid=jump-to]``); the resolver then runs over ``--root-selector`` only
when it matched. ``--key-method event`` (the default) is a ``Gdk.EventKey``
press/release pair (keyval, modifier state, the keymap's hardware keycode, the
seat's keyboard) through ``WebView.event``; ``gtk-test`` is
``Gtk.test_widget_send_key``, an X ``XSendEvent`` that never reached the page under
WSLg's XWayland (M25 F4 L7). A GTK-level synthetic key proves less than an OS-level
one, so a pass is reported as ``"partially verified (GTK-level key)"`` in
``keys.key_verdict``; a miss is ``"unverified"`` and fails the run.

The page is loaded with an ephemeral website data manager (no stale ``?v=``
cache between runs, squawk 0085) and a pinned, recorded environment. It prints
one JSON object and exits 0 iff ``ok``. A hard timeout stops a wedged WebView.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOLVER_JS = REPO_ROOT / "tests" / "browser" / "_a11y_resolve.js"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
# Refused ports: the operator's production instance, and the Flight Director's
# DD13 preview instance (M25 F4 L7). Probe a dev instance on 8486 or higher.
FORBIDDEN_PORTS = {
    8484: "the operator's production instance",
    8485: "the Flight Director's preview instance (M25 F4 DD13)",
}
KEY_VERDICT_PASS = "partially verified (GTK-level key)"


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
    """Raise ProbeError when ``url`` targets port 8484 or 8485 or ``data_dir`` is
    the platformdirs default (compared after ``Path.resolve()``)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ProbeError(f"--url must be an absolute http(s) URL, got {url!r}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port in FORBIDDEN_PORTS:
        raise ProbeError(
            f"refusing port {port}: that is {FORBIDDEN_PORTS[port]}. "
            "Use a dev instance on 8486 or higher (THE_ONE_PORT=8486 + scratch THE_ONE_DATA_DIR)."
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
    ap.add_argument(
        "--press-keys",
        action="append",
        default=[],
        metavar="COMBO",
        help=(
            "a key combo sent to the WebView as a real GTK key event after the\n"
            "setup scripts, e.g. ctrl+k (modifiers: ctrl, shift, alt, super);\n"
            "repeatable, sent in order"
        ),
    )
    ap.add_argument(
        "--key-method",
        choices=("event", "gtk-test"),
        default="event",
        help=(
            "event: a Gdk.EventKey press and release through WebView.event\n"
            "(default); gtk-test: Gtk.test_widget_send_key (an XSendEvent)"
        ),
    )
    ap.add_argument(
        "--focus-selector",
        metavar="CSS",
        help="focus this element in the page (a text input) before the keys",
    )
    ap.add_argument(
        "--assert-selector",
        metavar="CSS",
        help="after the keys, poll until this selector matches (else the run fails)",
    )
    ap.add_argument(
        "--assert-timeout", type=float, default=5.0, help="--assert-selector poll limit, seconds"
    )
    ap.add_argument(
        "--register-message-handler",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "register a script message handler NAME on the WebView's UserContentManager\n"
            "exactly as pywebview does for its bridge (register_script_message_handler\n"
            "plus script-message-received), before the page loads; every message a\n"
            "script posts through window.webkit.messageHandlers.NAME.postMessage is\n"
            "reported under message_handlers.NAME.received in the JSON (M35 F2 L1:\n"
            "can a sandboxed widget frame reach the shell's bridge?); repeatable"
        ),
    )
    ap.add_argument("--timeout", type=int, default=60, help="hard timeout, seconds (default 60)")
    return ap.parse_args(argv)


_HANDLER_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def validate_handler_names(names: list[str]) -> list[str]:
    """``--register-message-handler`` names: a JS identifier, no duplicates."""
    for name in names:
        if not _HANDLER_NAME.match(name):
            raise ProbeError(f"--register-message-handler {name!r}: expected a JS identifier")
    if len(set(names)) != len(names):
        raise ProbeError("--register-message-handler: a name is given twice")
    return list(names)


_MODIFIER_NAMES = {
    "ctrl": "CONTROL_MASK",
    "control": "CONTROL_MASK",
    "shift": "SHIFT_MASK",
    "alt": "MOD1_MASK",
    "super": "SUPER_MASK",
    "meta": "META_MASK",
}


def parse_key_combo(combo: str) -> tuple[list[str], str]:
    """``"ctrl+k"`` -> (``["CONTROL_MASK"]``, ``"k"``): the Gdk.ModifierType
    member names and the Gdk keyval name. Raises ProbeError on a bad combo."""
    parts = [p.strip() for p in str(combo).split("+")]
    if not parts or not parts[-1] or any(not p for p in parts):
        raise ProbeError(f"--press-keys {combo!r}: expected MOD+...+KEY, e.g. ctrl+k")
    *mods, key = parts
    names = []
    for mod in mods:
        name = _MODIFIER_NAMES.get(mod.lower())
        if name is None:
            raise ProbeError(
                f"--press-keys {combo!r}: unknown modifier {mod!r} "
                f"(want one of {sorted(_MODIFIER_NAMES)})"
            )
        names.append(name)
    return names, key


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
        combos = [parse_key_combo(c) for c in args.press_keys]
        handler_names = validate_handler_names(args.register_message_handler)
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
    gi.require_version("Gdk", "3.0")
    gi.require_version("WebKit2", "4.1")
    gi.require_version("JavaScriptCore", "4.1")
    from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: PLC0415

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
    # pywebview (webview/platforms/gtk.py) registers its bridge exactly like this.
    handlers: dict[str, list] = {name: [] for name in handler_names}

    def make_receiver(name: str):
        def received(_manager, message) -> None:
            try:
                # WebKit2 4.1 hands the callback a JavascriptResult wrapping the posted value.
                value = message.get_js_value() if hasattr(message, "get_js_value") else message
                text = value.to_json(0)
            except Exception:  # noqa: BLE001 - a non-serialisable value is still a delivery
                text = str(message)
            handlers[name].append(text)

        return received

    for name in handler_names:
        content.register_script_message_handler(name)
        content.connect(f"script-message-received::{name}", make_receiver(name))
    if handlers:
        out["message_handlers"] = {n: {"received": r} for n, r in handlers.items()}
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

    # ── Key injection (M25 F4 L7, DD9) ─────────────────────────────────────
    def send_key(keyval: int, mods) -> bool:
        if args.key_method == "gtk-test":
            return bool(Gtk.test_widget_send_key(view, keyval, mods))
        display = view.get_display()
        keymap = Gdk.Keymap.get_for_display(display)
        found, entries = keymap.get_entries_for_keyval(keyval)
        if not found or not entries:
            return False
        keyboard = display.get_default_seat().get_keyboard()
        handled = True
        for etype in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
            ev = Gdk.Event.new(etype)
            ev.key.window = view.get_window()
            ev.key.send_event = 1
            ev.key.time = Gdk.CURRENT_TIME
            ev.key.state = mods
            ev.key.keyval = keyval
            ev.key.hardware_keycode = entries[0].keycode
            ev.key.group = entries[0].group
            ev.set_device(keyboard)
            handled = bool(view.event(ev)) and handled
        return handled

    def press_keys(then) -> None:
        state["phase"] = "keys"
        window.present()
        view.grab_focus()
        sent = []
        for names, key in combos:
            keyval = Gdk.keyval_from_name(key)
            mods = Gdk.ModifierType(0)
            for name in names:
                mods |= getattr(Gdk.ModifierType, name)
            ok = send_key(keyval, mods) if keyval else False
            sent.append(
                {
                    "combo": "+".join([*(n.split("_")[0].lower() for n in names), key]),
                    "keyval": keyval,
                    "sent": ok,
                }
            )
        out["keys"] = {
            "method": args.key_method,
            "sent": sent,
            "webview_has_focus": bool(view.has_focus()),
        }
        then()

    def assert_after_keys(then) -> None:
        sel = json.dumps(args.assert_selector)
        deadline = GLib.get_monotonic_time() + int(args.assert_timeout * 1_000_000)
        out.setdefault("keys", {})["assert_selector"] = args.assert_selector

        def check() -> bool:
            def got(count) -> None:
                if count:
                    out["keys"]["assert_found"] = True
                    then()
                elif GLib.get_monotonic_time() >= deadline:
                    out["keys"]["assert_found"] = False
                    then()
                else:
                    GLib.timeout_add(100, check)

            run_js(f"document.querySelectorAll({sel}).length", got)
            return False

        check()

    def finish_with_report() -> None:
        run_js("window.__probeReport === undefined ? null : window.__probeReport", on_report)

    def focus_then_keys() -> None:
        def after_assert() -> None:
            # The resolver runs only over what the keys opened; a miss ends the
            # run here (with any setup-script report), never in a hard timeout.
            if out["keys"].get("assert_found"):
                poll()
            else:
                state["phase"] = "assert"
                finish_with_report()

        def after_keys() -> None:
            if args.assert_selector:
                assert_after_keys(after_assert)
            else:
                poll()

        if not combos and not args.assert_selector:
            poll()
            return
        if args.focus_selector:
            sel = json.dumps(args.focus_selector)

            def focused(result) -> None:
                out["focus"] = result
                press_keys(after_keys)

            run_js(
                f"(function(){{ var el = document.querySelector({sel}); if (!el) return null;"
                " el.focus(); var a = document.activeElement;"
                " return {selector: " + sel + ", focused: a === el,"
                " tag: a ? a.tagName : null}; })()",
                focused,
            )
        else:
            press_keys(after_keys)

    def run_setup(index: int) -> None:
        if index >= len(setup_scripts):
            focus_then_keys()
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

    if "keys" in out:
        keys = out["keys"]
        sent_ok = all(k.get("sent") for k in keys.get("sent", [])) if combos else True
        found = keys.get("assert_found", True) if args.assert_selector else None
        if args.assert_selector:
            keys["key_verdict"] = KEY_VERDICT_PASS if (sent_ok and found) else "unverified"
            if not found:
                out["ok"] = False
    if state["error"]:
        out["error"] = state["error"]
        out["ok"] = False
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
