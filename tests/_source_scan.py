"""Cached reads of the working tree for the source-scan guards (Mission 34 F1 L01).

Several guards walk every ``.py`` file under ``tests/`` and ``the_one/`` (and the static
tree). Each used to list and read the files itself; this module lists and reads each once per
process. The working tree does not change during a test run, so a process-wide cache is safe;
the guards still see the tree as of the run.
"""

from __future__ import annotations

import functools
from pathlib import Path


@functools.cache
def py_files(root: Path) -> tuple[Path, ...]:
    """Every ``*.py`` file under ``root``, sorted."""
    return tuple(sorted(root.rglob("*.py")))


@functools.cache
def text(path: Path) -> str:
    """The UTF-8 text of ``path``."""
    return path.read_text(encoding="utf-8")


@functools.cache
def static_js_files(js_dir: Path) -> tuple[Path, ...]:
    """Every ``*.js`` file under ``js_dir``, sorted."""
    return tuple(sorted(js_dir.rglob("*.js")))
