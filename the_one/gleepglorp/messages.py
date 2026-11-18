"""The one sentence per GleepGlorp state that is not ``ready`` (M36 F1 L04).

Used by the factory's error, the ``start_failed`` frame and the per-turn refusal. The
client's chat banner keeps its own copy of the three sentences
(``static/js/areas/chat/agent-kind.js``); ``tests/test_gleepglorp_messages.py`` reads the
JS source and checks they match this table.
"""

from __future__ import annotations

UNAVAILABLE_SENTENCES: dict[str, str] = {
    "off": "GleepGlorp is turned off.",
    "needs_model": "GleepGlorp needs a model.",
    "provider_missing": "GleepGlorp's model provider was removed.",
}


def unavailable_sentence(state: str) -> str:
    return UNAVAILABLE_SENTENCES.get(state, "GleepGlorp is not available.")
