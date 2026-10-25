"""The Info.plist dict for the macOS bundle, a pure function of the render values.

Build recipe, not app code (Mission 32 Flight 3 leg 6, DD8). ``the-one.spec`` loads it through
``sys.path.insert(0, SPECPATH)``; tests import it by path. ``values`` is the flat map that
``packaging/render.py --json`` prints (``product.json`` in the build).
"""

from __future__ import annotations

COPYRIGHT = "Copyright © GleepGlorp AI contributors. MIT License."


def info_plist(values: dict[str, str]) -> dict[str, object]:
    return {
        "CFBundleName": values["bundle_name"],
        "CFBundleDisplayName": values["bundle_name"],
        "CFBundleShortVersionString": values["bundle_short_version"],
        "CFBundleVersion": values["bundle_version"],
        "LSMinimumSystemVersion": values["min_os"],
        "LSApplicationCategoryType": values["bundle_category"],
        "NSHumanReadableCopyright": COPYRIGHT,
        # Retina rendering for the web view and the window chrome.
        "NSHighResolutionCapable": True,
        # With the window hidden (the app stays in the Dock) the server must keep serving
        # connectors, indexing and MCP at full speed (DD2).
        "LSAppNapIsDisabled": True,
        # The app talks to its own loopback server.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    }
