"""Clear the widget hang-guard crash records before a clean quit (Mission 35, F2 L8, AC4).

``widget-lifecycle.js`` keeps ``localStorage["widget-running:{pageId}"]`` while a widget is
loaded and removes it on ``pagehide``. On the desktop shell ``pagehide`` never reaches the
page on a ``destroy()`` / terminate (measured on WebKitGTK, leg 8 Part A: the record was
still on disk after ``POST /api/window/quit`` and after ``the-one quit``), so the next
launch would read a clean quit as "This widget stopped responding last time.".

``clear_widget_records(window)`` runs a small script through ``window.run_js`` (which
returns nothing and never uses the native bridge) on a daemon thread joined with a bound.
GTK and Cocoa ``run_js`` wait on an unbounded semaphore, so a page frozen by a widget would
otherwise hang the quit; a timed-out thread is a leaked daemon thread, harmless at exit.
It is skipped on the main thread (the semaphore inside ``run_js`` would deadlock the loop).
It never raises. Logout and a kill run no shell code (accepted residual).
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger("the_one.interfaces.desktop.shell")

#: How long a quit waits for the page to run the script (seconds).
CLEAR_BOUND = 1.0

#: Removes every hang-guard record and stops the page writing a new one: the lifecycle's
#: tick rewrites its record every second, so a bare removal races the quit (measured, leg 8
#: Part A: a record survived a ``the-one quit`` that had removed it). The page is quitting,
#: so the guard on ``Storage.prototype.setItem`` lives only until the process exits.
#: Plain statements only: no bridge, no callback.
CLEAR_SCRIPT = (
    "(function(){try{var o=window.Storage.prototype.setItem;"
    "window.Storage.prototype.setItem=function(k){"
    "if(String(k).indexOf('widget-running:')===0)return;"
    "return o.apply(this,arguments);};}catch(e){}"
    "try{var ks=[];"
    "for(var i=0;i<window.localStorage.length;i++){"
    "var k=window.localStorage.key(i);"
    "if(k&&k.indexOf('widget-running:')===0)ks.push(k);}"
    "ks.forEach(function(k){window.localStorage.removeItem(k);});}catch(e){}})();"
)


def clear_widget_records(window, bound: float | None = None) -> str:
    """Run the clear script on ``window``; returns ``"cleared"``, ``"timeout"``, ``"error"``,
    ``"skipped"`` (main thread) or ``"no-window"``. Never raises."""
    if window is None:
        return "no-window"
    if threading.current_thread() is threading.main_thread():
        log.warning("widget records: not cleared (called on the main thread)")
        return "skipped"
    outcome: list[str] = []

    def _run() -> None:
        try:
            window.run_js(CLEAR_SCRIPT)
            outcome.append("cleared")
        except Exception:
            log.warning("widget records: run_js raised", exc_info=True)
            outcome.append("error")

    worker = threading.Thread(target=_run, name="widget-records-clear", daemon=True)
    worker.start()
    worker.join(CLEAR_BOUND if bound is None else bound)
    if worker.is_alive():
        log.warning("widget records: page did not answer within the bound; quitting anyway")
        return "timeout"
    return outcome[0] if outcome else "error"
