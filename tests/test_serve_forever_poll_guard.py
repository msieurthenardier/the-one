"""Guard (squawk 0307): a test-owned ``serve_forever`` always names a short ``poll_interval``.

``http.server``'s ``serve_forever()`` polls every 0.5 s by default, so each ``shutdown()``
waits about 0.35 s. Mission 34 Flight 1 found this was the largest single cost in the evals
tests and ``test_cli_quit``. This guard parses every ``.py`` file under ``tests/`` and
``evals/`` (after an exact substring pre-filter) and fails on:

* a call ``x.serve_forever(...)`` with no ``poll_interval`` keyword and no positional argument
  (a multiline call is the same AST node, so it is covered);
* a bare reference ``x.serve_forever`` that is not a call, unless it is an argument of a call
  that carries ``poll_interval=`` (``functools.partial(x.serve_forever, poll_interval=0.02)``)
  - ``Thread(target=x.serve_forever)`` therefore fails, since it runs with the default.

It cannot see a ``getattr(x, "serve_forever")`` or an alias made in a variable.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests import _source_scan

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = (ROOT / "tests", ROOT / "evals")


def _violations(source: str) -> list[int]:
    if "serve_forever" not in source:
        return []
    tree = ast.parse(source)
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def has_poll(call: ast.Call) -> bool:
        return any(k.arg == "poll_interval" for k in call.keywords)

    hits: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "serve_forever"):
            continue
        up = parent.get(node)
        if isinstance(up, ast.Call) and up.func is node:
            if not has_poll(up) and not up.args:
                hits.append(node.lineno)
        else:
            # a reference: find the call it is an argument (or keyword value) of
            call = up
            while call is not None and not isinstance(call, ast.Call):
                call = parent.get(call)
            if call is None or not has_poll(call):
                hits.append(node.lineno)
    return hits


def test_no_default_poll_serve_forever() -> None:
    found = []
    for base in SCAN_DIRS:
        for path in _source_scan.py_files(base):
            for line in _violations(_source_scan.text(path)):
                found.append(f"{path.relative_to(ROOT)}:{line}")
    assert not found, (
        "serve_forever() without poll_interval waits ~0.35 s on every shutdown; "
        "pass poll_interval=0.02: " + ", ".join(found)
    )


def test_detector_catches_planted_violations() -> None:
    assert _violations("srv.serve_forever()\n") == [1]
    assert _violations("srv.serve_forever(\n)\n") == [1]
    assert _violations("Thread(target=srv.serve_forever)\n") == [1]
    assert _violations("partial(srv.serve_forever)\n") == [1]
    assert _violations("Thread(target=lambda: srv.serve_forever())\n") == [1]


def test_detector_accepts_short_interval() -> None:
    assert _violations("srv.serve_forever(poll_interval=0.02)\n") == []
    assert _violations("srv.serve_forever(0.02)\n") == []
    assert _violations("partial(srv.serve_forever, poll_interval=0.02)\n") == []
    assert _violations("x = 1\n") == []
