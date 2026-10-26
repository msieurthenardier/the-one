"""The desktop session's shared lifecycle state (Mission 32, Flight 3, DD1).

Before the split, ``shell.py`` kept nine module globals that the launch
sequence (``DesktopSession.run``), the window callbacks and the HTTP window
routes (``focus_window``, ``window_state``, ``quit_desktop``) all read and wrote.
They live here, on one object, so the three modules that now use them
(``shell``, ``window_control``, ``takeover``) share a single copy and a test can
reset all of it in one call.

Locking rule (unchanged from ``shell.py``, DD4): everything the quit route reads
or the boot publishes is guarded by ``state.lock``; ``DesktopSession._on_quit``
(which blocks on ``icon.stop()`` and the window destroy) is NEVER called while
holding it. Each method below is one critical section that existed before and
returns what its caller must do *after* the lock is released, so no method calls
``_on_quit`` or any pywebview method under the lock.

The module-level instance ``state`` is never rebound; ``state.reset()`` restores
the defaults in place.
"""

from __future__ import annotations

import threading

from the_one.interfaces.desktop import boot_policy


class SessionState:
    """Process-wide lifecycle flags and the lock that guards the quit/boot race."""

    def __init__(self) -> None:
        # Guards the boot/quit race. Never rebound by ``reset()``.
        self.lock = threading.Lock()
        # Set by ``_boot`` on every exit (DD3): the terminate worker waits on it.
        self.boot_stopped = threading.Event()
        self._set_defaults()

    def _set_defaults(self) -> None:
        # True once the Quit callback asked for the real destroy, so the
        # ``closing`` handler allows it instead of hiding the window.
        self.really_quit: bool = False
        # The pywebview Window object; populated once the boot publishes it.
        self.desktop_window = None
        # How the tray was decided this launch: "indicator" | "xembed" | "none" |
        # "failed" | "dock" (macOS) | None (Windows, or not decided yet).
        self.tray_mode: str | None = None
        # The running DesktopSession (set at the top of run(), cleared when it
        # returns); quit_desktop() uses it from the HTTP route.
        self.session = None
        # Visibility tracked by the shell for non-GTK backends (GTK reads
        # get_visible()).
        self.tracked_visible: bool | None = None
        # True from just after the ``is_ours`` return in run() until the window
        # is published, the browser branch is entered, or run() ends.
        self.booting: bool = False
        # A quit that arrived while ``booting``; _boot honours it at each checkpoint.
        self.quit_requested: bool = False
        # The uvicorn server while the browser-fallback branch is active.
        self.browser_server = None
        # The uvicorn server and its thread, as ``run()`` starts them. ``run()``
        # also keeps them as locals for its ``finally``. Inert until leg 4 (DD3).
        self.server = None
        self.thread = None
        # macOS (DD3): a terminate is being drained (a repeat answers NSTerminateLater
        # and starts nothing), and ``webview.start`` has returned (path S).
        self.terminate_pending: bool = False
        self.loop_stopped: bool = False
        self.boot_stopped.clear()
        # The platform's boot policy: filled lazily by the ``policy`` property (the
        # first read takes ``boot_policy.current()``), cleared here.
        self._policy = None

    @property
    def policy(self) -> boot_policy.BootPolicy:
        """The boot policy, chosen on first read (so a test that patches the
        platform and calls ``reset()`` sees the new one)."""
        policy = self._policy
        if policy is None:
            policy = self._policy = boot_policy.current()
        return policy

    @policy.setter
    def policy(self, value: boot_policy.BootPolicy | None) -> None:
        self._policy = value

    def reset(self) -> None:
        """Restore every field to its default, in place (the instance is kept)."""
        self._set_defaults()

    # -- locked critical sections ----------------------------------------------

    def begin_boot(self) -> None:
        """A quit from here on is recorded for _boot (or the browser branch)."""
        with self.lock:
            self.booting = True

    def begin_quit(self):
        """Start a quit: set ``really_quit`` and ``quit_requested`` under the lock.

        Returns the published window to save the geometry of (read it OUTSIDE the
        lock), or None when there is none or a quit was already begun (so the
        geometry is saved once).
        """
        with self.lock:
            first = not self.really_quit
            self.really_quit = True
            self.quit_requested = True
            return self.desktop_window if first else None

    def mark_terminate_pending(self) -> bool:
        """Record a terminate in progress. False when one was already pending."""
        with self.lock:
            if self.terminate_pending:
                return False
            self.terminate_pending = True
            return True

    def clear_booting(self) -> None:
        with self.lock:
            self.booting = False

    def quit_was_requested(self) -> bool:
        """Whether a quit arrived while booting (``_boot``'s checkpoint read)."""
        with self.lock:
            return self.quit_requested

    def publish_window(self, window) -> bool:
        """Publish the window, clear ``booting`` and read ``quit_requested`` in ONE
        critical section, so a quit arriving at any moment is either seen here or
        finds the published window. Returns whether a quit was requested; the
        caller then runs ``_on_quit`` after the lock is released."""
        with self.lock:
            self.desktop_window = window
            self.booting = False
            return self.quit_requested

    def claim_browser_server(self, server) -> bool:
        """Enter the browser-fallback branch. Returns False when a quit recorded
        while booting wins (``booting`` is cleared either way)."""
        with self.lock:
            if self.quit_requested:
                self.booting = False
                return False
            self.browser_server = server
            self.booting = False
            return True

    def release_browser_server(self) -> None:
        with self.lock:
            self.browser_server = None

    def request_quit(self) -> tuple[str | None, object | None]:
        """The state-choosing half of ``quit_desktop`` (``POST /api/window/quit``).

        Returns ``(tag, session)``:

        - ``("already", None)``: a quit is already under way; never destroy twice.
        - ``("booting", None)``: ``quit_requested`` was set; ``_boot`` honours it.
        - ``("browser", None)``: the fallback server was told to drain
          (``should_exit`` set under the lock, as before).
        - ``("window", session)``: the caller runs ``session._on_quit`` after the
          lock is released.
        - ``(None, None)``: nothing to quit (``serve`` mode).
        """
        with self.lock:
            session = self.session
            if self.desktop_window is not None and session is not None:
                if self.really_quit:
                    return "already", None
                return "window", session
            elif self.booting:
                self.quit_requested = True
                return "booting", None
            elif self.browser_server is not None:
                self.browser_server.should_exit = True
                return "browser", None
            else:
                return None, None


# The one process-wide instance. Never rebound; tests call ``state.reset()``.
state = SessionState()
