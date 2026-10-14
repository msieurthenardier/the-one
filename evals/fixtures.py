"""The local web fixture server (DD7) and knowledge-base fixture indexing (DD17).

The web server is a stdlib ``http.server`` on ``127.0.0.1`` on a free port, in a
thread, serving ``fixtures/web/``; it logs every request so a transcript can show
every fetch attempt and its target. A knowledge-base fixture folder is copied
under the run directory (outside ``data/`` and outside the scratch home, so the
filesystem tools cannot read the answers directly), registered and indexed once
per invocation with the real ``IndexingManager`` and the bundled embedding model.
"""

from __future__ import annotations

import functools
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evals.scenario import KBRef

FIXTURE_HOST = "127.0.0.1"


class FixtureServer:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.requests: list[tuple[str, str]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        assert self._server is not None, "fixture server not started"
        return f"http://{FIXTURE_HOST}:{self._server.server_address[1]}"

    def start(self) -> FixtureServer:
        log = self.requests
        directory = str(self.directory)

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:  # noqa: D102
                log.append((self.command, self.path))

        handler = functools.partial(Handler, directory=directory)
        self._server = ThreadingHTTPServer((FIXTURE_HOST, 0), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="evals-fixture-server", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def __enter__(self) -> FixtureServer:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()


def kb_id_for(fixture: str) -> str:
    return f"evkb-{fixture}"


class KBFixtures:
    """Registers and indexes each KB fixture once per invocation, then shares it."""

    def __init__(self, env, fixtures_root: Path, *, index_timeout: float = 900.0) -> None:
        self.env = env
        self.fixtures_root = fixtures_root
        self.index_timeout = index_timeout
        self._ids: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._manager = None

    async def _get_manager(self):
        if self._manager is None:
            from the_one.knowledge.manager import IndexingManager

            self._manager = IndexingManager()
            self.env.managers.append(self._manager)
            await self._manager.start_all()  # writes the vector-store settings record
        return self._manager

    async def ensure(self, ref: KBRef) -> str:
        """Return the knowledge base id for ``ref``, indexing it on first use."""
        if ref.fixture in self._ids:
            if self._names[ref.fixture] != ref.name:
                raise RuntimeError(
                    f"KB fixture {ref.fixture!r} is declared with two names: "
                    f"{self._names[ref.fixture]!r} and {ref.name!r}"
                )
            return self._ids[ref.fixture]
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.db.models import KBItem, KnowledgeBase
        from the_one.db.repositories import (
            KBChunkRepository,
            KBItemRepository,
            KnowledgeBaseRepository,
        )

        source = self.fixtures_root / "kb" / ref.fixture
        if not source.is_dir():
            raise RuntimeError(f"no KB fixture directory {source}")
        target = self.env.run_dir / "kb" / ref.fixture
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        # Mirror the API's refusal: a folder may not lie inside the app's data directory.
        data = Path(settings.data_dir).resolve()
        if target.resolve() == data or data in target.resolve().parents:
            raise RuntimeError("KB fixture folder lies inside the scratch data directory")

        kb_id = kb_id_for(ref.fixture)
        conn = await get_connection()
        await KnowledgeBaseRepository(conn).create(KnowledgeBase(id=kb_id, name=ref.name))
        items = KBItemRepository(conn)
        await items.create(
            KBItem(id=f"{kb_id}-folder", kb_id=kb_id, type="folder", path_or_url=str(target))
        )
        manager = await self._get_manager()
        manager.request_index(kb_id)
        await manager.wait_until_idle(kb_id, timeout=self.index_timeout)
        chunks = await KBChunkRepository(conn).count_for_kb(kb_id)
        if chunks <= 0:
            raise RuntimeError(f"KB fixture {ref.fixture!r} produced no chunks")
        failed = await items.count_by_status(kb_id)
        if failed.get("failed"):
            raise RuntimeError(f"KB fixture {ref.fixture!r} has {failed['failed']} failed item(s)")
        self._ids[ref.fixture] = kb_id
        self._names[ref.fixture] = ref.name
        return kb_id
