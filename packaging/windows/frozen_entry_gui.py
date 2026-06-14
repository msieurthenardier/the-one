"""Windowed (console-less) GUI entry for the frozen Windows app.

Built into ``the-one-app.exe`` with ``console=False`` so the Start-menu / Desktop
shortcut opens the native web-view window WITHOUT a stray console window (the
operator-HAT defect: the console-subsystem ``the-one.exe`` popped a blank cmd
window when launched as the GUI).

This launcher always runs the ``app`` (native window) path regardless of argv, so
the shortcut needs no parameters. The console ``the-one.exe`` remains the CLI
(``chat`` / ``serve`` / ``doctor`` / ``version``) and backs the CI packaged-smoke.
"""

from __future__ import annotations

import multiprocessing
import sys

from the_one.main import cli_entry

if __name__ == "__main__":
    multiprocessing.freeze_support()  # DD7: no-op off-Windows; fork-bomb insurance
    # Force the windowed `app` path; the CLI lives in the separate console exe.
    sys.argv = [sys.argv[0], "app"]
    cli_entry()
