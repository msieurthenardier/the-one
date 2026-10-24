"""Runtime hook: make the frozen app use the HOST's GTK/WebKit stack, not the bundle's.

Spike prototype (Mission 32 Flight 1, candidate A). Runs inside the frozen process
before any application import. See excludes.txt for what the bundle leaves out.
"""

import os
import sys

# 1. Typelibs come from the host. PyInstaller's own gi runtime hook points
#    GI_TYPELIB_PATH at <bundle>/gi_typelibs; the bundle ships none (the spec drops
#    *.typelib), and the host's WebKit2/Gtk/AyatanaAppIndicator3 typelibs are the
#    ones that match the host libraries gi will load. Assigning here (not
#    appending) also wins over the stock hook if that one ran first.
os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(
    [
        "/usr/lib/x86_64-linux-gnu/girepository-1.0",
        "/usr/lib64/girepository-1.0",
        "/usr/lib/girepository-1.0",
    ]
)

# 2. Keep the bundle off LD_LIBRARY_PATH for everything this process spawns.
#    The PyInstaller bootloader sets LD_LIBRARY_PATH=<bundle>[:<original>] and saves
#    the original in LD_LIBRARY_PATH_ORIG. WebKit starts WebKitWebProcess and
#    WebKitNetworkProcess as children that inherit the environment; with the bundle
#    first they could load bundled duplicates of libstdc++/libz/... instead of the
#    host's. The dynamic loader read its search path at process start, so changing
#    the variable now only affects children, which is the point.
_bundle = getattr(sys, "_MEIPASS", None)
_orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
if _orig is not None:
    os.environ["LD_LIBRARY_PATH"] = _orig
else:
    _parts = [
        p
        for p in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)
        if p and os.path.realpath(p) != os.path.realpath(_bundle or "")
    ]
    if _parts:
        os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(_parts)
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

# 3. Undo the stock gio/glib/gtk runtime hooks (pyi_rth_gio, pyi_rth_glib, pyi_rth_gtk).
#    They point GIO_MODULE_DIR, GTK_PATH, GTK_DATA_PREFIX, GTK_EXE_PREFIX, PANGO_LIBDIR
#    and PANGO_SYSCONFDIR at directories inside the bundle, and put <bundle>/share first
#    on XDG_DATA_DIRS. The bundle ships none of those directories (the host owns the
#    GTK stack), and the variables are inherited by WebKit's helper processes, where a
#    GIO_MODULE_DIR pointing at nothing hides the host's GIO modules (TLS, proxies).
if _bundle:
    _b = os.path.realpath(_bundle)

    def _inside(value):
        v = os.path.realpath(value)
        return v == _b or v.startswith(_b + os.sep)

    for _name in (
        "GIO_MODULE_DIR",
        "GTK_PATH",
        "GTK_DATA_PREFIX",
        "GTK_EXE_PREFIX",
        "PANGO_LIBDIR",
        "PANGO_SYSCONFDIR",
    ):
        if os.environ.get(_name) and _inside(os.environ[_name]):
            del os.environ[_name]
    if os.environ.get("XDG_DATA_DIRS"):
        _keep = [p for p in os.environ["XDG_DATA_DIRS"].split(os.pathsep) if p and not _inside(p)]
        if _keep:
            os.environ["XDG_DATA_DIRS"] = os.pathsep.join(_keep)
        else:
            del os.environ["XDG_DATA_DIRS"]

# Debug aid for leg 2: M32_DEBUG_ENV=1 prints what the hook left behind.
if os.environ.get("M32_DEBUG_ENV") == "1":
    _names = ("GI_TYPELIB_PATH", "LD_LIBRARY_PATH", "GIO_MODULE_DIR", "GTK_PATH", "XDG_DATA_DIRS")
    print(
        "[rthook_host_gtk] " + " ".join("%s=%r" % (n, os.environ.get(n)) for n in _names),
        file=sys.stderr,
    )
