"""The drawer's client copy of the create-editor names equals the server's (squawk 0396)."""

from __future__ import annotations

import re
from pathlib import Path

from the_one.gleepglorp.page import CREATE_NAMES

_JS = (
    Path(__file__).resolve().parent.parent
    / "the_one/interfaces/web/static/js/gleepglorp-drawer/shell.js"
)


def _client_names() -> dict[str, str]:
    text = _JS.read_text(encoding="utf-8")
    block = re.search(r"var CREATE_NAMES = \{(.*?)\};", text, re.S)
    assert block, "CREATE_NAMES table not found in shell.js"
    return dict(re.findall(r"(\w+):\s*'([^']*)'", block.group(1)))


def test_the_client_create_names_match_the_server_table() -> None:
    assert _client_names() == CREATE_NAMES
