"""One migrated SQLite template per pytest process, copied into each test.

Building a database with ``ensure_schema`` replays every migration step
(about 0.4 s). Tests that only need a current-schema database copy the
template instead (about 1 ms). The template is built by the real
``ensure_schema``, in ``journal_mode=DELETE``, so it is a single file.

Never open the template itself through production code (it would convert
to WAL); only copy it. Do not import ``tests/conftest.py`` from here.

Tests that exercise migrations, partial schemas or file-creation behaviour
keep calling ``ensure_schema`` directly; they are allow-listed in
``tests/test_schema_template.py``.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import shutil
import tempfile
import threading
from pathlib import Path

import aiosqlite

_lock = threading.Lock()
_template: Path | None = None
_tmpdir: str | None = None


def _cleanup() -> None:
    if _tmpdir is not None:
        shutil.rmtree(_tmpdir, ignore_errors=True)


async def _build(path: Path) -> None:
    from the_one.db.schema import ensure_schema

    conn = await aiosqlite.connect(str(path))
    try:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA synchronous=OFF")
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        await conn.execute("PRAGMA journal_mode=DELETE")
        await conn.commit()
    finally:
        await conn.close()


def template_path() -> Path:
    """Return the migrated template file, building it once per process."""
    global _template, _tmpdir
    with _lock:
        if _template is not None:
            return _template
        _tmpdir = tempfile.mkdtemp(prefix="the-one-schema-template-")
        atexit.register(_cleanup)
        path = Path(_tmpdir) / "template.db"
        errors: list[BaseException] = []

        def run() -> None:
            try:
                asyncio.run(_build(path))
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=run, name="schema-template-build")
        thread.start()
        thread.join()
        if errors:
            raise errors[0]
        _template = path
        return _template


def copy_template(dest: str | os.PathLike[str]) -> Path:
    """Copy the template to ``dest`` (which must not exist) at mode 0o600."""
    dest_path = Path(dest)
    if dest_path.exists():
        raise FileExistsError(f"refusing to overwrite existing database: {dest_path}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path(), dest_path)
    os.chmod(dest_path, 0o600)
    return dest_path


async def connect_template_db(dest: str | os.PathLike[str]) -> aiosqlite.Connection:
    """Copy the template to ``dest`` and open the usual test connection."""
    copy_template(dest)
    conn = await aiosqlite.connect(str(dest))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def connect_template_memory() -> aiosqlite.Connection:
    """A fresh ``:memory:`` connection holding a copy of the template schema."""
    src = await aiosqlite.connect(f"file:{template_path()}?mode=ro", uri=True)
    mem = await aiosqlite.connect(":memory:")
    try:
        await src.backup(mem)
    except BaseException:
        await mem.close()
        raise
    finally:
        await src.close()
    mem.row_factory = aiosqlite.Row
    await mem.execute("PRAGMA foreign_keys=ON")
    return mem
