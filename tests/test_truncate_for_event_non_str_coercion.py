"""Unit tests for ``truncate_for_event`` non-string content coercion.

M11 F7 L12.m: hotfix mirror of 12.l at the second consumer.

L10 channel-context tools (``list_visible_channels``,
``fetch_channel_history``, ``fetch_thread_history``, ``fetch_dm_history``)
return Python dicts / lists despite ``ToolResult.content``'s ``str`` type
annotation — dataclass type hints are not enforced at runtime. The
projection path through ``the_one.db.codec.truncate_for_event`` previously
crashed with ``TypeError: unhashable type: 'slice'`` when slicing a dict.

The fix coerces non-string content to ``json.dumps(content)`` before
truncation. This pins:

  - str input passes through truncated (legacy path, byte-identical),
  - dict input is JSON-stringified then truncated,
  - list input is JSON-stringified then truncated,
  - None input is gracefully coerced via ``json.dumps(None) == "null"``
    (matches 12.l's no-special-branch approach).
"""

from __future__ import annotations

import json

from the_one.db.codec import MAX_TOOL_RESULT_INLINE_CONTENT, truncate_for_event

# ---------------------------------------------------------------------------
# Legacy str path — pinned for back-compat
# ---------------------------------------------------------------------------


def test_str_input_under_cap_passes_through_unchanged() -> None:
    """A short string is returned verbatim — pre-12.m behaviour preserved."""
    s = "hello world"
    assert truncate_for_event(s) == s


def test_str_input_over_cap_is_truncated_to_cap() -> None:
    """The historic slice-by-codepoint truncation contract is unchanged."""
    s = "x" * (MAX_TOOL_RESULT_INLINE_CONTENT + 500)
    out = truncate_for_event(s)
    assert isinstance(out, str)
    assert len(out) == MAX_TOOL_RESULT_INLINE_CONTENT
    assert out == "x" * MAX_TOOL_RESULT_INLINE_CONTENT


# ---------------------------------------------------------------------------
# Non-str path — the bug site, now coerced via json.dumps
# ---------------------------------------------------------------------------


def test_dict_input_is_json_stringified_then_truncated() -> None:
    """Pre-12.m: ``dict[:N]`` raised TypeError. Post-12.m: JSON-encode first.

    Mirrors the shape returned by ``list_visible_channels`` and similar
    L10 channel-context tools.
    """
    payload = {"channels": [{"id": "ch1", "name": "general"}]}
    out = truncate_for_event(payload)
    assert isinstance(out, str)
    assert len(out) <= MAX_TOOL_RESULT_INLINE_CONTENT
    # Under cap — the full JSON-encoded form is preserved
    assert json.loads(out) == payload


def test_list_input_is_json_stringified_then_truncated() -> None:
    """Mirrors the shape returned by ``fetch_channel_history`` etc."""
    payload = [
        {"peer_id": "1234567890", "peer_name": "alice", "content": "hey bot"},
        {"peer_id": "9876543210", "peer_name": "bob", "content": "second"},
    ]
    out = truncate_for_event(payload)
    assert isinstance(out, str)
    assert len(out) <= MAX_TOOL_RESULT_INLINE_CONTENT
    assert json.loads(out) == payload


def test_large_dict_input_is_json_stringified_then_truncated_at_cap() -> None:
    """A dict whose JSON form exceeds the cap is truncated to exactly cap."""
    # A value string long enough to push the JSON encoding well past the cap
    payload = {"k": "v" * (MAX_TOOL_RESULT_INLINE_CONTENT + 500)}
    out = truncate_for_event(payload)
    assert isinstance(out, str)
    assert len(out) == MAX_TOOL_RESULT_INLINE_CONTENT
    # The prefix matches the JSON encoding of the payload, truncated at cap
    expected_prefix = json.dumps(payload)[:MAX_TOOL_RESULT_INLINE_CONTENT]
    assert out == expected_prefix


def test_none_input_is_coerced_via_json_dumps() -> None:
    """None is handled gracefully — coerced via the same json.dumps path.

    ``json.dumps(None) == "null"``, so the result is a 4-char string. This
    matches 12.l's no-special-branch approach: any non-str passes through
    json.dumps, no separate None handling needed.
    """
    out = truncate_for_event(None)
    assert out == "null"
    assert isinstance(out, str)
