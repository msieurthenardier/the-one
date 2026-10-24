"""Probe module run inside a Briefcase Windows app (Mission 32 Flight 1 spike, leg windows-cost).

Run as the app's main module via ``BRIEFCASE_MAIN_MODULE=m32probe_win`` (copied next to
``the_one/`` in a COPY of the installed app first). Prints what the embedded interpreter looks
like from the inside, then tries the imports the Windows desktop path needs. Unscored: the
reader decides. Every line is prefixed ``PROBE`` and every import is wrapped.
"""

import os
import sys

print("PROBE sys.executable=%r exists=%s" % (sys.executable, os.path.exists(sys.executable)))
print(
    "PROBE sys.frozen=%r hasattr(_MEIPASS)=%s"
    % (getattr(sys, "frozen", "<absent>"), hasattr(sys, "_MEIPASS"))
)
print("PROBE sys.prefix=%r argv=%r" % (sys.prefix, sys.argv))
print("PROBE version=%s" % sys.version.split()[0])
print("PROBE stdout=%r stderr=%r stdin=%r" % (sys.stdout, sys.stderr, sys.stdin))
print("PROBE flags.no_site=%r path=%r" % (sys.flags.no_site, sys.path))
print(
    "PROBE exe_dir_has_app_packages=%s"
    % os.path.isdir(os.path.join(os.path.dirname(sys.executable), "app_packages"))
)

try:
    from the_one.platform.env import _bundle_dir, is_frozen
    from the_one.platform.interpreter import resolve_python

    print(
        "PROBE is_frozen=%r bundle_dir=%r resolve_python=%r"
        % (is_frozen(), _bundle_dir(), resolve_python())
    )
except Exception as exc:  # noqa: BLE001
    print("PROBE env/interpreter FAILED: %r" % (exc,))


def attempt(label, fn):
    try:
        print("PROBE %s: %s" % (label, fn()))
    except Exception as exc:  # noqa: BLE001
        print("PROBE %s: FAILED %s: %s" % (label, type(exc).__name__, exc))


def imp(name):
    import importlib

    mod = importlib.import_module(name)
    extra = ""
    if name.startswith("mcp."):
        # mcp's Windows helpers set win32api/win32job to None when pywin32 is not importable
        extra = " win32api=%r win32job=%r" % (
            getattr(mod, "win32api", "n/a"),
            getattr(mod, "win32job", "n/a"),
        )
    return "ok " + str(getattr(mod, "__file__", "<namespace>")) + extra


for name in (
    "winpty",
    "win32api",
    "win32job",
    "win32con",
    "pywintypes",
    "clr",
    "clr_loader",
    "webview",
    "pystray",
    "mcp.os.win32.utilities",
):
    attempt("import " + name, lambda n=name: imp(n))


def pty_echo():
    from winpty import PtyProcess

    p = PtyProcess.spawn(["cmd.exe", "/c", "echo", "m32" + "pty"])
    out = ""
    for _ in range(20):
        try:
            out += p.read(1024)
        except EOFError:
            break
    return repr(out[-80:])


attempt("pywinpty spawn", pty_echo)
