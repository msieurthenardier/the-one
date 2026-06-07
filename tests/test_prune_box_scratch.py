"""Unit tests for ``prune_box_scratch`` (M14 F4 L7).

Verifies:
  (a) A planted ``boxes/<x>`` directory is removed at prune time.
  (b) A non-boxes sibling directory under ``data_dir`` is left untouched.
  (c) Prune is a no-op (no error) when the ``boxes/`` directory does not exist.
  (d) Prune is a no-op (no error) when ``boxes/`` is empty.
  (e) ``prune_box_scratch`` is NOT called from ``settings.ensure_dirs()``
      (guard against per-create wiring that would delete live scratch).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from the_one.config import settings


def _prune_with_tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper: monkeypatch ``settings.data_dir`` to ``tmp_path`` and run prune."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # Import AFTER monkeypatching so the function-local ``from the_one.config import settings``
    # inside ``prune_box_scratch`` picks up the patched data_dir.
    from the_one.tools.execution import prune_box_scratch

    prune_box_scratch()


def test_prune_removes_orphaned_box_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(a) A planted boxes/<x> directory is removed by prune."""
    boxes_dir = tmp_path / "boxes"
    boxes_dir.mkdir()
    orphan = boxes_dir / "deadbeef1234"
    orphan.mkdir()
    (orphan / "some_file.txt").write_text("orphan data")

    _prune_with_tmp_data_dir(tmp_path, monkeypatch)

    assert not orphan.exists(), f"Orphaned box dir should have been removed; still at {orphan}"
    # boxes/ itself may or may not remain — only children matter.


def test_prune_leaves_non_boxes_sibling_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(b) A sibling directory (not under boxes/) is NOT removed by prune."""
    boxes_dir = tmp_path / "boxes"
    boxes_dir.mkdir()
    orphan = boxes_dir / "orphan123"
    orphan.mkdir()

    # Sibling dir (e.g. the agent DB location or cli history)
    sibling = tmp_path / "agents"
    sibling.mkdir()
    sentinel = sibling / "keep_me.txt"
    sentinel.write_text("important")

    _prune_with_tmp_data_dir(tmp_path, monkeypatch)

    assert not orphan.exists(), "Orphaned box dir must be removed"
    assert sentinel.exists(), f"Sibling data_dir file must NOT be removed; missing at {sentinel}"
    assert sentinel.read_text() == "important"


def test_prune_noop_when_boxes_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) Prune returns without error when boxes/ does not exist."""
    assert not (tmp_path / "boxes").exists()
    # Should not raise.
    _prune_with_tmp_data_dir(tmp_path, monkeypatch)


def test_prune_noop_when_boxes_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(d) Prune is a no-op (no error) when boxes/ exists but is empty."""
    (tmp_path / "boxes").mkdir()
    # Should not raise.
    _prune_with_tmp_data_dir(tmp_path, monkeypatch)


def test_prune_not_in_ensure_dirs() -> None:
    """(e) ``prune_box_scratch`` is NOT called from ``settings.ensure_dirs()``.

    ``ensure_dirs()`` is called per ``AgentFactory.create()``; wiring prune there
    would delete a live session's scratch mid-operation.  This test reads the
    source of ``ensure_dirs`` and asserts the name is absent.
    """
    src = inspect.getsource(settings.ensure_dirs)
    assert "prune_box_scratch" not in src, (
        "prune_box_scratch must NOT be called from settings.ensure_dirs() — "
        "that method runs per AgentFactory.create() and would delete live box scratch."
    )
