"""Guard (squawk 0280): every session turn takes its lock through ``track_turn``.

The Chats row activity (``busy``, ``turn_seq``, the ``sessions_changed`` start and end
pushes) depends on every turn acquiring the per-session lock through
``the_one.sessions.track_turn``. A turn path that wrote ``async with session_locks[...]``
directly would run with no row activity and no new-reply dot, and every other test would
stay green. This AST scan fails on any ``session_locks[...]`` subscript under ``the_one/``
outside ``the_one/sessions/_locks.py`` (where ``track_turn`` itself is the one site).
Comments and strings are not code, so mentions in them are not flagged; ``.pop`` and
``.get`` are not acquisitions.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests import _source_scan

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "the_one"
LOCKS_MODULE = PACKAGE / "sessions" / "_locks.py"


def _lock_subscripts(source: str) -> list[int]:
    """Line numbers of ``session_locks[...]`` / ``x.session_locks[...]`` subscripts."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Subscript):
            continue
        target = node.value
        name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
        if name == "session_locks":
            hits.append(node.lineno)
    return hits


def test_the_guard_flags_a_direct_acquisition_but_not_comments_or_pop() -> None:
    planted = "async def turn(sid):\n    async with session_locks[sid]:\n        pass\n"
    assert _lock_subscripts(planted) == [2]
    assert _lock_subscripts("async with sessions.session_locks[sid]:\n    pass\n") == [1]
    assert _lock_subscripts("session_locks.pop(sid, None)\nsession_locks.get(sid)\n") == []
    assert _lock_subscripts('# async with session_locks[sid]:\nx = "session_locks[sid]"\n') == []


def test_only_track_turn_acquires_a_session_lock() -> None:
    files = _source_scan.py_files(PACKAGE)
    assert LOCKS_MODULE in files, "the_one/sessions/_locks.py not found"
    offenders: dict[str, list[int]] = {}
    for path in files:
        if path == LOCKS_MODULE:
            continue
        hits = _lock_subscripts(_source_scan.text(path))
        if hits:
            offenders[str(path.relative_to(REPO))] = hits
    assert offenders == {}, (
        "take the per-session lock through the_one.sessions.track_turn, never "
        f"session_locks[...] directly: {offenders}"
    )
    # The one allowed site still exists, so the scan is not passing on an empty target.
    assert _lock_subscripts(_source_scan.text(LOCKS_MODULE)), "track_turn's acquisition moved"
