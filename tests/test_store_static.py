"""Static guards for App.store (M25 F2 L7, AC2/AC4)."""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/js"
LITERAL_LIST = re.compile(r"""fetch\(\s*['"]/api/(agents|providers)['"]\s*\)""")


def test_no_literal_list_fetches_outside_store() -> None:
    offenders = [
        str(p.relative_to(JS))
        for p in JS.rglob("*.js")
        if p.name != "store.js" and LITERAL_LIST.search(p.read_text())
    ]
    assert offenders == []


def test_oauth_and_provider_mutations_invalidate_providers() -> None:
    src = (JS / "areas/admin/provider-editor.js").read_text()
    assert src.count("App.store.invalidate('providers')") >= 4  # code, reset, save, delete


def test_cross_collection_mutations_invalidate_agents() -> None:
    for rel, minimum in (
        ("areas/studio/knowledge-section.js", 2),
        ("areas/studio/mcp-server-editor.js", 2),
        ("areas/studio.js", 5),
    ):
        src = (JS / rel).read_text()
        assert src.count("App.store.invalidate('agents')") >= minimum, rel
