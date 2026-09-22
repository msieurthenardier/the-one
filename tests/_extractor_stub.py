"""Test-only ``Extractor`` implementation (Flight 3 Leg 2, AC-3/M7).

Proves the extractor seam's mission criterion — indexing a brand-new
format needs no pipeline change — by registering a fake ``.stub``
extractor and letting ``index_item`` index it end to end, with
``the_one/knowledge/indexer.py`` completely unchanged: the test that uses
this imports nothing private from ``indexer.py`` and patches nothing in
it.
"""

from __future__ import annotations

from pathlib import Path

STUB_TEXT = "stub extractor output — always the same fixed string, regardless of file contents."


class StubExtractor:
    """Satisfies the ``Extractor`` Protocol structurally. Returns a fixed
    string for every ``.stub`` file, ignoring the file's actual contents."""

    name = "stub"
    extensions = frozenset({".stub"})

    def extract(self, path: Path) -> str:
        return STUB_TEXT
