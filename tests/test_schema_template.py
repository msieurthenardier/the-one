"""Guards for ``tests/_schema_template.py``: the template matches a fresh
replay, copies are independent, and no new test builds a database the slow way.
"""

from __future__ import annotations

import ast
import os
import stat
from pathlib import Path

import aiosqlite
import pytest

from tests import _schema_template as tmpl
from the_one.db.schema import CURRENT_VERSION, ensure_schema

TESTS_DIR = Path(__file__).parent

# Files that may call ensure_schema( / init_db( directly, with the reason.
ALLOWED_DIRECT_CALLERS: dict[str, str] = {
    "tests/test_db_migration.py": "exercises the real migration path on purpose",
    "tests/test_schema.py": "exercises schema creation and upgrades on purpose",
    "tests/test_db_connection.py": "asserts get_connection/ensure_schema behaviour on fresh files",
    "tests/_schema_template.py": "builds the template (self-exempt)",
    "tests/test_schema_template.py": "equivalence guard builds a real replay (self-exempt)",
}


async def _snapshot(conn: aiosqlite.Connection) -> dict:
    snap: dict = {}
    async with conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master") as cur:
        master = sorted((tuple(r) for r in await cur.fetchall()), key=lambda r: (r[0], r[1]))
    snap["master"] = master
    async with conn.execute("SELECT version FROM schema_version") as cur:
        snap["versions"] = sorted(r[0] for r in await cur.fetchall())
    tables = [name for (typ, name, _t, sql) in master if typ == "table"]
    rows: dict = {}
    pragmas: dict = {}
    for name in tables:
        virtual = any(
            n == name and (s or "").upper().startswith("CREATE VIRTUAL") for _, n, _, s in master
        )
        if name != "schema_version" and not virtual:
            async with conn.execute(f'SELECT * FROM "{name}"') as cur:
                rows[name] = sorted(repr(tuple(r)) for r in await cur.fetchall())
        for pragma in ("foreign_key_list", "index_list", "table_info"):
            try:
                async with conn.execute(f'PRAGMA {pragma}("{name}")') as cur:
                    pragmas[(name, pragma)] = sorted(repr(tuple(r)) for r in await cur.fetchall())
            except Exception:
                assert name.startswith("sqlite_"), (name, pragma)
    snap["rows"] = rows
    snap["pragmas"] = pragmas
    return snap


class TestTemplateShape:
    def test_single_delete_mode_file(self) -> None:
        path = tmpl.template_path()
        assert path.is_file()
        assert not Path(f"{path}-wal").exists()
        assert not Path(f"{path}-shm").exists()
        assert tmpl.template_path() == path  # built once

    async def test_works_inside_running_loop(self) -> None:
        assert tmpl.template_path().is_file()

    def test_copy_mode_and_refuses_existing(self, tmp_path: Path) -> None:
        dest = tmp_path / "a.db"
        tmpl.copy_template(dest)
        assert stat.S_IMODE(os.stat(dest).st_mode) == 0o600
        with pytest.raises(FileExistsError):
            tmpl.copy_template(dest)

    async def test_copies_are_independent(self, tmp_path: Path) -> None:
        a = await tmpl.connect_template_db(tmp_path / "a.db")
        b = await tmpl.connect_template_db(tmp_path / "b.db")
        try:
            assert a.row_factory is aiosqlite.Row
            async with a.execute("PRAGMA foreign_keys") as cur:
                assert (await cur.fetchone())[0] == 1
            await a.execute("INSERT INTO knowledge_bases (id, name) VALUES ('k', 'K')")
            await a.commit()
            async with b.execute("SELECT COUNT(*) FROM knowledge_bases") as cur:
                assert (await cur.fetchone())[0] == 0
        finally:
            await a.close()
            await b.close()

    async def test_memory_copy_is_separate(self) -> None:
        a = await tmpl.connect_template_memory()
        b = await tmpl.connect_template_memory()
        try:
            await a.execute("INSERT INTO knowledge_bases (id, name) VALUES ('k', 'K')")
            async with b.execute("SELECT COUNT(*) FROM knowledge_bases") as cur:
                assert (await cur.fetchone())[0] == 0
        finally:
            await a.close()
            await b.close()


async def test_template_matches_fresh_replay(tmp_path: Path) -> None:
    fresh = await aiosqlite.connect(str(tmp_path / "fresh.db"))
    fresh.row_factory = aiosqlite.Row
    await fresh.execute("PRAGMA synchronous=OFF")
    await fresh.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(fresh)
    template = await tmpl.connect_template_db(tmp_path / "copy.db")
    try:
        a = await _snapshot(fresh)
        b = await _snapshot(template)
    finally:
        await fresh.close()
        await template.close()
    assert max(b["versions"]) == CURRENT_VERSION
    assert a["versions"] == b["versions"]
    assert a["master"] == b["master"]
    assert a["rows"] == b["rows"]
    assert a["pragmas"] == b["pragmas"]


def _direct_calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text())
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = (
                f.id
                if isinstance(f, ast.Name)
                else f.attr
                if isinstance(f, ast.Attribute)
                else None
            )
            if name in ("ensure_schema", "init_db"):
                lines.append(node.lineno)
    return lines


def test_no_direct_schema_builds_outside_allow_list() -> None:
    violations = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        rel = path.relative_to(TESTS_DIR.parent).as_posix()
        if rel in ALLOWED_DIRECT_CALLERS:
            continue
        for line in _direct_calls(path):
            violations.append(f"{rel}:{line}")
    assert not violations, (
        "These tests call ensure_schema()/init_db() directly, replaying every migration "
        "(~0.4 s each). Build the database through tests/_schema_template.py "
        "(connect_template_db / copy_template / connect_template_memory), or add the "
        "file to ALLOWED_DIRECT_CALLERS with a reason if it must exercise the real path:\n"
        + "\n".join(violations)
    )


def test_allow_list_entries_exist_and_are_used() -> None:
    root = TESTS_DIR.parent
    for rel in ALLOWED_DIRECT_CALLERS:
        path = root / rel
        assert path.exists(), f"stale allow-list entry: {rel}"
        if rel != "tests/test_schema_template.py":
            assert _direct_calls(path), f"allow-list entry makes no direct call: {rel}"
