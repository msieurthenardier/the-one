"""The GleepGlorp state sentences: one server table, one client copy (M36 F1 L04)."""

from __future__ import annotations

import re
from pathlib import Path

from the_one.agent.factory import GleepGlorpUnavailableError
from the_one.gleepglorp.messages import UNAVAILABLE_SENTENCES, unavailable_sentence

_JS = (
    Path(__file__).resolve().parent.parent
    / "the_one/interfaces/web/static/js/areas/chat/agent-kind.js"
)


def _client_sentences() -> dict[str, str]:
    text = _JS.read_text(encoding="utf-8")
    block = re.search(r"var UNAVAILABLE = \{(.*?)\};", text, re.S)
    assert block, "UNAVAILABLE table not found in agent-kind.js"
    pairs = re.findall(r'(\w+):\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')', block.group(1))
    return {key: value[1:-1] for key, value in pairs}


def test_the_client_banner_sentences_match_the_server_table() -> None:
    assert _client_sentences() == UNAVAILABLE_SENTENCES


def test_the_table_has_the_three_states_and_the_error_uses_it() -> None:
    assert set(UNAVAILABLE_SENTENCES) == {"off", "needs_model", "provider_missing"}
    for state, sentence in UNAVAILABLE_SENTENCES.items():
        assert str(GleepGlorpUnavailableError(state)) == sentence
        assert unavailable_sentence(state) == sentence
    assert unavailable_sentence("other") == "GleepGlorp is not available."


def test_the_client_statuses_map_to_the_server_statuses() -> None:
    from the_one.interfaces.web import app

    text = _JS.read_text(encoding="utf-8")
    block = re.search(r"var STATUSES = \{(.*?)\};", text, re.S)
    assert block
    client = dict(re.findall(r"(\w+):\s*'(\w+)'", block.group(1)))
    assert client == {
        app.SESSION_STATUS_GLEEPGLORP_OFF: "off",
        app.SESSION_STATUS_GLEEPGLORP_NEEDS_MODEL: "needs_model",
        app.SESSION_STATUS_GLEEPGLORP_PROVIDER_MISSING: "provider_missing",
    }
