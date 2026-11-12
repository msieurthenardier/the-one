#!/usr/bin/env python3
"""The widget escape battery's sink as a command (M35 F2 L6, DD17/DD18).

Starts the three loopback listeners of ``tests/browser/_widget_sink.py`` (HTTP, UDP, TCP) and
serves two control routes on the HTTP port:

* ``GET /__sink/counts``   -> ``{"http", "http_requests", "udp", "tcp"}`` (control requests are
  never counted);
* ``GET /__sink/fixture``  -> the escape battery fixture (mode ``main``) with this sink's ports
  filled in; ``GET /__sink/fixture-focus`` is the same file in the focus-stealing mode.

The first stdout line is JSON: ``{"http": P, "udp": P, "tcp": P, "pid": N}``. It refuses any
non-loopback ``--host`` (exit 2) and stops on SIGTERM or SIGINT. Used by the ``widget-escape``
behavior test (``tests/behavior/widget-escape.md``). Run it with the repo venv::

    .venv/bin/python scripts/widget_sink.py
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

LOOPBACK_NAMES = {"localhost"}


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback only (default 127.0.0.1)")
    args = parser.parse_args(argv)
    if not is_loopback(args.host):
        print(f"widget_sink: refusing non-loopback host {args.host!r}", file=sys.stderr)
        return 2
    if args.host not in ("127.0.0.1", "localhost"):
        print("widget_sink: the sink binds 127.0.0.1 only", file=sys.stderr)
        return 2

    from browser._widget_sink import WidgetSink, escape_fixture

    sink = WidgetSink()
    sink.routes["/__sink/counts"] = lambda: (
        json.dumps(sink.counts()).encode(),
        "application/json",
    )
    sink.routes["/__sink/fixture"] = lambda: (
        sink.fill(escape_fixture(), "main").encode(),
        "text/plain; charset=utf-8",
    )
    sink.routes["/__sink/fixture-focus"] = lambda: (
        sink.fill(escape_fixture(), "focus").encode(),
        "text/plain; charset=utf-8",
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    print(
        json.dumps(
            {
                "http": sink.http_port,
                "udp": sink.udp_port,
                "tcp": sink.tcp_port,
                "pid": os.getpid(),
            }
        ),
        flush=True,
    )
    stop.wait()
    sink.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
