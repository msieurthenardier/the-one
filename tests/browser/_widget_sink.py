"""The widget escape battery's sink (M35 F2 L1, DD17): three listeners on ``127.0.0.1`` that count
what a sandboxed widget frame manages to send out.

* an HTTP server that logs every request except the harness page itself (``/harness``), which is
  served with the app's own ``FRAME_POLICY`` header so a frame test runs under the real page
  policy;
* a UDP socket that counts datagrams (WebRTC STUN);
* a TCP listener that counts accepts (a WebKit ``preconnect`` opens a bare connection).

Used by the contract tests and by the measurement probes. Under ``THE_ONE_TEST_NETNS=1`` all of
it is loopback.
"""

from __future__ import annotations

import functools
import http.server
import socket
import socketserver
import threading
from pathlib import Path

from the_one.interfaces.web.app import FRAME_POLICY

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "widgets"
HARNESS_PATH = "/harness"


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class WidgetSink:
    def __init__(self) -> None:
        # Control routes (path -> () -> (body bytes, content type)), answered and never counted.
        self.routes: dict[str, object] = {}
        self.requests: list[str] = []
        self.udp: list[bytes] = []
        self.tcp_accepts = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        sink = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # noqa: D102
                pass

            def _serve(self) -> None:
                route = sink.routes.get(self.path)
                if route is not None:
                    # A control route (scripts/widget_sink.py): answered, never counted.
                    body, ctype = route()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == HARNESS_PATH:
                    body = b"<!doctype html><html><head></head><body></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Security-Policy", FRAME_POLICY)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path != "/favicon.ico":
                    with sink._lock:
                        sink.requests.append(f"{self.command} {self.path}")
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = do_HEAD = do_PUT = _serve  # noqa: N815

        self._http = _Server(("127.0.0.1", 0), Handler)
        self.http_port = self._http.server_address[1]
        self._tcp = socket.socket()
        self._tcp.bind(("127.0.0.1", 0))
        self._tcp.listen(64)
        self._tcp.settimeout(0.2)
        self.tcp_port = self._tcp.getsockname()[1]
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp.bind(("127.0.0.1", 0))
        self._udp.settimeout(0.2)
        self.udp_port = self._udp.getsockname()[1]
        self._threads = [
            threading.Thread(
                target=functools.partial(self._http.serve_forever, poll_interval=0.02), daemon=True
            ),
            threading.Thread(target=self._accept, daemon=True),
            threading.Thread(target=self._recv, daemon=True),
        ]
        for t in self._threads:
            t.start()

    # ── listeners ──
    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._tcp.accept()
            except (TimeoutError, OSError):
                continue
            with self._lock:
                self.tcp_accepts += 1
            conn.close()

    def _recv(self) -> None:
        while not self._stop.is_set():
            try:
                data, _ = self._udp.recvfrom(4096)
            except (TimeoutError, OSError):
                continue
            with self._lock:
                self.udp.append(data)

    # ── api ──
    @property
    def harness_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}{HARNESS_PATH}"

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self.udp.clear()
            self.tcp_accepts = 0

    def counts(self) -> dict[str, object]:
        with self._lock:
            return {
                "http": len(self.requests),
                "http_requests": list(self.requests),
                "udp": len(self.udp),
                "tcp": self.tcp_accepts,
            }

    def fill(self, text: str, mode: str = "main") -> str:
        """Fill the battery fixture's placeholders (before ``buildDocument``)."""
        return (
            text.replace("{{HTTP}}", str(self.http_port))
            .replace("{{UDP}}", str(self.udp_port))
            .replace("{{TCP}}", str(self.tcp_port))
            .replace("{{MODE}}", mode)
        )

    def close(self) -> None:
        self._stop.set()
        self._http.shutdown()
        self._http.server_close()
        self._tcp.close()
        self._udp.close()


def escape_fixture() -> str:
    return (FIXTURES / "escape.html").read_text()
