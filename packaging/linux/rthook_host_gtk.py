"""Runtime hook: make the frozen app use the HOST's GTK/WebKit stack, not the bundle's.

Spike prototype (Mission 32 Flight 1, candidate A). Runs inside the frozen process
before any application import. See excludes.txt for what the bundle leaves out.
"""

import os
import sys

# 1. Typelibs come from the host. PyInstaller's own gi runtime hook points
#    GI_TYPELIB_PATH at <bundle>/gi_typelibs; the bundle ships none (the spec drops
#    *.typelib), and the host's WebKit2/Gtk/AyatanaAppIndicator3 typelibs are the
#    ones that match the host libraries gi will load. (The stock gi/gio/glib/gtk runtime
#    hooks run after this one and would undo it, so the spec drops them.)
_HOST_TYPELIB_DIRS = [
    "/usr/lib/x86_64-linux-gnu/girepository-1.0",
    "/usr/lib64/girepository-1.0",
    "/usr/lib/girepository-1.0",
]
_typelib_dirs = list(_HOST_TYPELIB_DIRS)

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

# 4. Library fallback (AppImage only; flight 2 DD1). The AppImage carries a few libraries
#    a stock desktop may lack, in <AppDir>/usr/lib/gleepglorp-ai-fallback/ (never inside the
#    PyInstaller bundle, never on LD_LIBRARY_PATH). The host's copy always wins: each soname
#    is first loaded by its bare name (the system loader), and the AppImage copy is loaded by
#    absolute path only when that fails. RTLD_GLOBAL registers the soname, so later
#    NEEDED/dlopen of the same soname (the _gi extension, the Ayatana typelib) binds to the
#    copy loaded here. Best effort: any failure is swallowed (a bare host has no GTK, and the
#    desktop-shell gate reports that), and a chain stops at the first soname that loads from
#    neither place. The .deb has no fallback directory, so nothing here runs for it.
_GIREPO = ("libgirepository-2.0.so.0",)
_AYATANA = (
    "libdbusmenu-glib.so.4",
    "libdbusmenu-gtk3.so.4",
    "libayatana-ido3-0.4.so.0",
    "libayatana-indicator3.so.7",
    "libayatana-appindicator3.so.1",
)
_TYPELIBS = ("AyatanaAppIndicator3-0.1.typelib", "AppIndicator3-0.1.typelib")
_debug = os.environ.get("THE_ONE_PKG_DEBUG") == "1"
_force = _debug and os.environ.get("THE_ONE_PKG_FORCE_FALLBACK") == "1"
_sources = {}  # soname -> "host" | "fallback" | "skipped: <why>"


def _fallback_dir():
    if not _bundle:
        return None
    d = os.path.realpath(
        os.path.join(os.path.dirname(_bundle), os.pardir, "gleepglorp-ai-fallback")
    )
    return d if os.path.isdir(d) else None


def _preload(chain, fallback):
    import ctypes

    for soname in chain:
        path = os.path.join(fallback, "lib", soname)
        attempts = (
            [("fallback", path), ("host", soname)]
            if _force
            else [("host", soname), ("fallback", path)]
        )
        why = ""
        for source, target in attempts:
            if source == "fallback" and not os.path.exists(path):
                why = "no fallback copy"
                continue
            try:
                ctypes.CDLL(target, mode=ctypes.RTLD_GLOBAL)
            except OSError as exc:
                why = str(exc)
                continue
            _sources[soname] = source
            break
        else:
            _sources[soname] = "skipped: " + why
            break  # the rest of the chain would half-load


try:
    _fallback = _fallback_dir()
    if _fallback:
        _preload(_GIREPO, _fallback)
        _preload(_AYATANA, _fallback)
        # The typelib is decoupled from the preload: it is needed whenever the host has no
        # Ayatana/AppIndicator typelib, even when every library came from the host.
        _fb_typelibs = os.path.join(_fallback, "girepository-1.0")
        if os.path.isdir(_fb_typelibs) and not any(
            os.path.exists(os.path.join(d, t)) for d in _HOST_TYPELIB_DIRS for t in _TYPELIBS
        ):
            _typelib_dirs.append(_fb_typelibs)
except Exception as _exc:  # best effort: never break startup
    if _debug:
        print("[rthook_host_gtk] fallback error: %r" % (_exc,), file=sys.stderr)
os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(_typelib_dirs)
_gi_report = os.environ["GI_TYPELIB_PATH"]
if len(_typelib_dirs) > len(_HOST_TYPELIB_DIRS):
    # The AppImage's typelib directory is only needed by THIS process. GI_TYPELIB_PATH is
    # inherited by WebKit's helper processes, so once gi has read it (the first typelib
    # lookup fixes the search path) drop the variable: nothing under the AppImage mount is
    # left in any child's environment. The system typelib directories are searched anyway.
    try:
        import gi

        gi.require_version("GLib", "2.0")
        os.environ.pop("GI_TYPELIB_PATH", None)
    except Exception as _exc:
        if _debug:
            print("[rthook_host_gtk] gi search-path init failed: %r" % (_exc,), file=sys.stderr)

# Debug aid for leg 2: THE_ONE_PKG_DEBUG=1 prints what the hook left behind.
if os.environ.get("THE_ONE_PKG_DEBUG") == "1":
    _names = ("LD_LIBRARY_PATH", "GIO_MODULE_DIR", "GTK_PATH", "XDG_DATA_DIRS")
    print(
        "[rthook_host_gtk] GI_TYPELIB_PATH=%r " % (_gi_report,)
        + " ".join("%s=%r" % (n, os.environ.get(n)) for n in _names),
        file=sys.stderr,
    )
    print("[rthook_host_gtk] fallback sources: %r" % (_sources,), file=sys.stderr)

# 5. ABI probe (flight 2 AC4). Inert unless THE_ONE_PKG_ABI_PROBE=1; ships in both packages.
#    Exercises the libraries for real (window, WebView, indicator, a short main loop),
#    prints where the six fallback sonames were mapped from, and exits.
if os.environ.get("THE_ONE_PKG_ABI_PROBE") == "1":
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3, GLib, Gtk, WebKit2

        _win = Gtk.Window(title="m32 abi probe")
        _view = WebKit2.WebView()
        _win.add(_view)
        _ind = AyatanaAppIndicator3.Indicator.new(
            "m32-abi-probe",
            "dialog-information",
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        _ind.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        _menu = Gtk.Menu()
        _menu.append(Gtk.MenuItem(label="m32 probe"))
        _menu.show_all()
        _ind.set_menu(_menu)
        _win.show_all()
        _view.load_html("<p>m32 abi probe</p>", None)
        GLib.timeout_add(4000, Gtk.main_quit)
        Gtk.main()
        # tear down cleanly before exiting: closing the window while the loop still runs lets
        # WebKit's helper release its bus name instead of logging a connection-closed warning
        _win.destroy()
        GLib.timeout_add(1500, Gtk.main_quit)
        Gtk.main()
        _wanted = _GIREPO + _AYATANA
        with open("/proc/self/maps") as _m:
            for _line in _m:
                if any(w.split(".so")[0] in _line for w in _wanted):
                    print("PROBE_MAP " + _line.split(None, 5)[-1].strip())
        print("PROBE_OK")
        sys.stdout.flush()
        os._exit(0)
    except BaseException:
        import traceback

        traceback.print_exc()
        print("PROBE_FAIL")
        sys.stdout.flush()
        os._exit(1)
