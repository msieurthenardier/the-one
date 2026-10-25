"""Version takeover and port selection for the desktop launcher.

Mission 32, Flight 3, DD1: moved verbatim out of ``shell.py`` (the DD13 takeover
and ``_select_port``). The logger keeps the shell's name so every log line is
unchanged. This module needs no other desktop module.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import sys
import time

import httpx

from the_one import __version__
from the_one.api_credential import get_credential
from the_one.interfaces.desktop import host as desktop_host

log = logging.getLogger("the_one.interfaces.desktop.shell")

# -- Version takeover (DD13) -------------------------------------------------
# Small, individually stubbable seams: the unit tests drive the whole takeover
# through them with no real clock, process or network.

_TAKEOVER_WAIT_BOUND = 75.0  # `_graceful_shutdown`'s 60 s join plus margin
_TAKEOVER_POLL = 0.5
_TAKEOVER_NOTICE_AFTER = 3.0


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _parse_version(text: str):
    """Parse ``X.Y.Z[.devN]`` into a sortable key, or None when it is not that.

    A ``.devN`` build sorts before its release (``0.11.9.dev1 < 0.11.9``) and dev
    numbers compare as integers (``dev9 < dev10``) -- the same order dpkg gives
    ``0.11.9~dev1``. ``packaging`` is not a declared dependency, so this is
    deliberately tiny; anything else (a local suffix, rc, junk) is None.
    """
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?", text.strip())
    if not m:
        return None
    major, minor, patch, dev = m.groups()
    # A release (no dev) sorts after every dev of the same X.Y.Z.
    return (int(major), int(minor), int(patch), (0, int(dev)) if dev is not None else (1, 0))


def _is_older(running: str | None, ours: str) -> bool:
    """True only when both parse and ``running`` is strictly older than ``ours``."""
    if running is None:
        return False
    a, b = _parse_version(running), _parse_version(ours)
    if a is None or b is None:
        return False
    return a < b


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_credential().encode()}"}


def _running_version(host: str, port: int) -> str | None:
    """The running instance's version from ``GET /api/info``, or None (unknown)."""
    try:
        r = httpx.get(f"http://{host}:{port}/api/info", headers=_auth_headers(), timeout=2.0)
        if r.status_code != 200:
            return None
        version = r.json().get("version")
        return version if isinstance(version, str) else None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def _request_quit(host: str, port: int) -> dict | None:
    """``POST /api/window/quit``. Returns ``{"status": int, "body": dict|None}``.

    None on a connection error.
    """
    try:
        r = httpx.post(
            f"http://{host}:{port}/api/window/quit", headers=_auth_headers(), timeout=5.0
        )
    except httpx.HTTPError:
        return None
    try:
        body = r.json() if r.status_code == 200 else None
    except ValueError:
        body = None
    return {"status": r.status_code, "body": body if isinstance(body, dict) else None}


def _pid_alive(pid: int) -> bool:
    """Is process ``pid`` still running? Never ``os.kill`` on Windows, where any
    signal other than CTRL_C/CTRL_BREAK is ``TerminateProcess``."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(synchronize, False, int(pid))
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_exit(pid: int, bound: float = _TAKEOVER_WAIT_BOUND) -> bool:
    """Wait until ``pid`` exits. True when it did, False at ``bound`` seconds."""
    start = _now()
    notified = False
    while _pid_alive(pid):
        elapsed = _now() - start
        if elapsed >= bound:
            return False
        if not notified and elapsed >= _TAKEOVER_NOTICE_AFTER:
            notified = True
            desktop_host.send_notification("GleepGlorp AI", "Updating GleepGlorp AI\u2026")
        _sleep(_TAKEOVER_POLL)
    return True


def _activation_token() -> str | None:
    token = os.environ.get("XDG_ACTIVATION_TOKEN") or os.environ.get("DESKTOP_STARTUP_ID")
    if token and len(token) <= 256 and not any(c.isspace() for c in token):
        return token
    return None


def _post_focus(host: str, port: int) -> None:
    """Raise the running instance's window, forwarding any activation token.

    A failed or rejected POST is tolerated (logged): the existing instance keeps
    running either way and this process is about to exit.
    """
    token = _activation_token()
    try:
        kwargs = {"json": {"activation_token": token}} if token else {}
        httpx.post(
            f"http://{host}:{port}/api/window/focus",
            headers=_auth_headers(),
            timeout=2.0,
            **kwargs,
        )
    except httpx.HTTPError:  # intentionally broad: ConnectError + TimeoutException
        log.warning("focus POST to running instance failed; exiting anyway")


def _takeover(host: str, port: int) -> tuple[int, bool]:
    """Handle an instance that shares our credential (DD13).

    Returns ``(port, True)`` to mean "done: a running instance was focused or
    left alone, exit" and ``(port, False)`` after an older instance was quit
    and the port re-selected ("start normally").
    """
    running = _running_version(host, port)
    if not _is_older(running, __version__):
        _post_focus(host, port)
        return port, True
    log.info("running GleepGlorp AI %s is older than %s; replacing it", running, __version__)
    answer = _request_quit(host, port)
    if answer is None:
        log.warning("quit request to the older instance failed; focusing it")
        _post_focus(host, port)
        return port, True
    status, body = answer["status"], answer["body"]
    if status in (401, 403):
        log.warning(
            "port %s answered %s to the quit request: another program, or a "
            "different credential, holds it",
            port,
            status,
        )
        return port, True
    if status in (404, 405):
        log.warning(
            "the running GleepGlorp AI has no quit route; restart GleepGlorp AI "
            "to finish the upgrade"
        )
        _post_focus(host, port)
        return port, True
    if status != 200 or body is None:
        log.warning("unexpected answer to the quit request (HTTP %s); focusing it", status)
        _post_focus(host, port)
        return port, True
    if body.get("quit") is not True:
        log.warning("a server-only instance holds the port; not replacing it")
        return port, True
    pid = body.get("pid")
    if type(pid) is not int or pid <= 0:
        log.warning("quit answer carries no valid pid; focusing the running instance")
        _post_focus(host, port)
        return port, True
    if not _wait_for_exit(pid):
        log.warning("the older instance (pid %s) did not exit in time; focusing it", pid)
        _post_focus(host, port)
        return port, True
    # Two near-simultaneous launches can still race here; documented.
    return _select_port(host, port)


def _select_port(host: str, port: int, retries: int = 3, delay: float = 0.3) -> tuple[int, bool]:
    """Select the port to use and determine if a the-one instance is already running.

    Returns (port_to_use, is_our_instance):
    - (port, False): port is free — start a new server on the configured port.
    - (port, True): a the-one that shares OUR credential is already answering
      on that port (DD4 case b, DD11) — do NOT start a second server.
    - (free_port, False): a foreign process holds the configured port (DD4 case c)
      — bind-0 a free port for this instance.

    Uses a connect-probe (not a bind-probe with SO_REUSEADDR, which gives a
    false "free" on a TIME_WAIT port). Includes a startup-retry so a the-one
    that just bound but hasn't finished lifespan startup (/api/info not yet 200)
    isn't misclassified as foreign.

    DD11: "ours" is credentialed. The prior version-only check (200 +
    matching `__version__`) misclassified a *different* instance running the
    same version against a *different* data directory as ours — version
    alone says nothing about which data directory (and therefore which
    credential) answered. Sending our own credential and treating a 200 as
    success is what "ours" should always have meant: the server on the other
    end validated the exact credential this process would also use, which
    only happens when it reads the same credential file. A foreign server
    that also 401s (wrong or absent credential) simply resolves to "not
    ours" — already the safe answer for the fall-through below.

    Edge case: no credential file exists yet (fresh machine, first launch).
    `get_credential()` creates one on first use rather than raising, so a
    missing-credential machine still gets a well-formed probe — and "cannot
    be ours" falls out naturally (nothing on a fresh machine could share a
    credential that didn't exist a moment ago).
    """
    auth_headers = {"Authorization": f"Bearer {get_credential().encode()}"}
    for attempt in range(retries):
        # (b) a the-one that shares OUR credential already answering?
        try:
            r = httpx.get(f"http://{host}:{port}/api/info", headers=auth_headers, timeout=1.0)
            if r.status_code == 200:
                return port, True
        except httpx.HTTPError:
            pass
        # Is ANYTHING listening? connect-probe — no bind race.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            occupied = s.connect_ex((host, port)) == 0
        if not occupied:
            return port, False  # (a) free — fast path, no retry
        if attempt < retries - 1:
            # occupied-not-(yet)-ours: a starting the-one? give it the startup window
            time.sleep(delay)
    # (c) occupied by a foreign process, or by a the-one that never confirmed
    # OUR credential (a different data dir or a rotated credential): bind-0 a
    # free port. Ownership is decided by credential, never by version — a the-one
    # of another version that shares our credential answered (b) above.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1], False
