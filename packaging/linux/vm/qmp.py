#!/usr/bin/env python3
"""Small QMP client for the Mission 32 fresh-VM apparatus (stdlib only).

Verbs: screendump, key, type, move, click, wait-for-screen, raw.

The socket is ``<M32_VM>/run/<distro>/qmp.sock`` (``-d`` / ``M32_DISTRO``) or
an explicit ``--sock``. QEMU runs in a container with the run dir mounted at
``/run/vm``, so file names handed to QEMU are translated to that path.
"""

import argparse
import json
import os
import shutil
import socket
import sys
import time

WIDTH, HEIGHT = 1280, 800
TOP_BAR_PX = 40  # ignored by wait-for-screen (the clock changes)
CONTAINER_RUN = "/run/vm"

_SHIFTED = {
    "~": "grave_accent",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "minus",
    "+": "equal",
    "{": "bracket_left",
    "}": "bracket_right",
    "|": "backslash",
    ":": "semicolon",
    '"': "apostrophe",
    "<": "comma",
    ">": "dot",
    "?": "slash",
}
_PLAIN = {
    " ": "spc",
    "\n": "ret",
    "\t": "tab",
    "`": "grave_accent",
    "-": "minus",
    "=": "equal",
    "[": "bracket_left",
    "]": "bracket_right",
    "\\": "backslash",
    ";": "semicolon",
    "'": "apostrophe",
    ",": "comma",
    ".": "dot",
    "/": "slash",
}
_ALIASES = {
    "super": "meta_l",
    "win": "meta_l",
    "enter": "ret",
    "return": "ret",
    "esc": "esc",
    "escape": "esc",
    "space": "spc",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "del": "delete",
    "backspace": "backspace",
    "pgup": "pgup",
    "pgdn": "pgdn",
}


class Qmp:
    def __init__(self, path, timeout=30.0):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.buf = b""
        self._read()  # greeting
        self.cmd("qmp_capabilities")

    def _read(self):
        while True:
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                if line.strip():
                    return json.loads(line)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("QMP socket closed")
            self.buf += chunk

    def cmd(self, name, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        self.sock.sendall(json.dumps(msg).encode() + b"\n")
        while True:
            reply = self._read()
            if "return" in reply:
                return reply["return"]
            if "error" in reply:
                raise RuntimeError(f"{name}: {reply['error'].get('desc', reply['error'])}")

    def close(self):
        self.sock.close()


def _keys(names):
    return [{"type": "qcode", "data": n} for n in names]


def char_keys(ch):
    if ch.isupper():
        return ["shift", ch.lower()]
    if ch.isalnum() and ch.isascii():
        return [ch]
    if ch in _PLAIN:
        return [_PLAIN[ch]]
    if ch in _SHIFTED:
        return ["shift", _SHIFTED[ch]]
    raise ValueError(f"cannot type {ch!r}")


def combo_keys(combo):
    names = []
    for part in combo.split("+"):
        low = part.lower()
        names.append(_ALIASES.get(low, low))
    return names


def _abs(value, size):
    return int(max(0, min(size - 1, value)) * 32767 / (size - 1))


def move(q, x, y):
    q.cmd(
        "input-send-event",
        events=[
            {"type": "abs", "data": {"axis": "x", "value": _abs(x, WIDTH)}},
            {"type": "abs", "data": {"axis": "y", "value": _abs(y, HEIGHT)}},
        ],
    )


def click(q, button="left", double=False):
    name = {"left": "left", "right": "right", "double": "left"}[button]
    for _ in range(2 if (double or button == "double") else 1):
        q.cmd("input-send-event", events=[{"type": "btn", "data": {"button": name, "down": True}}])
        time.sleep(0.06)
        q.cmd("input-send-event", events=[{"type": "btn", "data": {"button": name, "down": False}}])
        time.sleep(0.08)


def screendump(q, sock, out, fmt="png"):
    """Write a screendump to ``out`` (any host path; staged in the run dir)."""
    run_dir = os.path.dirname(os.path.abspath(sock))
    stage = f".shot-{os.getpid()}.{fmt}"
    q.cmd("screendump", filename=f"{CONTAINER_RUN}/{stage}", format=fmt)
    staged = os.path.join(run_dir, stage)
    for _ in range(50):
        if os.path.exists(staged) and os.path.getsize(staged) > 0:
            break
        time.sleep(0.1)
    shutil.move(staged, out)
    return out


def _ppm_pixels(path):
    with open(path, "rb") as f:
        data = f.read()
    # P6\nW H\n255\n
    parts = data.split(b"\n", 3)
    w, h = (int(v) for v in parts[1].split())
    return w, h, parts[3]


def wait_for_screen(q, sock, secs, tol=0.002, interval=1.0):
    """Wait until two dumps `interval` apart match outside the top bar."""
    run_dir = os.path.dirname(os.path.abspath(sock))
    deadline = time.time() + secs
    prev = None
    n = 0
    while time.time() < deadline:
        path = os.path.join(run_dir, f".wait-{os.getpid()}-{n % 2}.ppm")
        n += 1
        screendump(q, sock, path, fmt="ppm")
        w, h, px = _ppm_pixels(path)
        os.unlink(path)
        cur = px[TOP_BAR_PX * w * 3 :]
        if prev is not None and len(prev) == len(cur):
            if prev == cur:
                return 0.0
            diff = sum(1 for a, b in zip(prev, cur) if a != b)
            frac = diff / len(cur)
            if frac <= tol:
                return frac
        prev = cur
        time.sleep(interval)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-d", "--distro", default=os.environ.get("M32_DISTRO"))
    ap.add_argument("--sock")
    sub = ap.add_subparsers(dest="verb", required=True)
    s = sub.add_parser("screendump")
    s.add_argument("png")
    s = sub.add_parser("key")
    s.add_argument("combo", help="e.g. ctrl+alt+t, super, ret")
    s = sub.add_parser("type")
    s.add_argument("text")
    s.add_argument("--delay", type=float, default=0.04)
    s = sub.add_parser("move")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s = sub.add_parser("click")
    s.add_argument("button", nargs="?", default="left", choices=["left", "right", "double"])
    s = sub.add_parser("wait-for-screen")
    s.add_argument("secs", type=float)
    s = sub.add_parser("raw")
    s.add_argument("name")
    s.add_argument("json_args", nargs="?", default="{}")
    a = ap.parse_args(argv)

    sock = a.sock
    if not sock:
        if not a.distro:
            ap.error("need -d <distro> (or M32_DISTRO) or --sock")
        base = os.environ.get("M32_VM", os.path.expanduser("~/the-one-m32-vm"))
        sock = os.path.join(base, "run", a.distro, "qmp.sock")
    q = Qmp(sock)
    try:
        if a.verb == "screendump":
            print(screendump(q, sock, a.png))
        elif a.verb == "key":
            q.cmd("send-key", keys=_keys(combo_keys(a.combo)), **{"hold-time": 100})
        elif a.verb == "type":
            for ch in a.text:
                q.cmd("send-key", keys=_keys(char_keys(ch)), **{"hold-time": 40})
                time.sleep(a.delay)
        elif a.verb == "move":
            move(q, a.x, a.y)
        elif a.verb == "click":
            click(q, a.button)
        elif a.verb == "wait-for-screen":
            frac = wait_for_screen(q, sock, a.secs)
            if frac is None:
                print(f"timeout after {a.secs}s: screen still changing", file=sys.stderr)
                return 1
            print(f"stable (diff {frac:.5f})")
        elif a.verb == "raw":
            print(json.dumps(q.cmd(a.name, **json.loads(a.json_args))))
    finally:
        q.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
