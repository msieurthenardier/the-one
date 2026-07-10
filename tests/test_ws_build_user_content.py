"""M16 F12 L08 — the WS message-branch content builder.

``_build_user_content`` decides the shape of the value threaded into
``_spawn_message_processing`` / ``Agent.step``:

- No images -> plain ``str`` (text-only path stays byte-identical to
  pre-L08 behaviour — no wrapping in a single-element list).
- Text + images -> ``[TextContent(text), *ImageContent(**img), ...]``.
- Images with NO text -> ``[ImageContent(**img), ...]`` — deliberately no
  empty ``TextContent``. Anthropic 400s on an empty-text content block
  ("text content blocks must contain non-whitespace text"), so an
  image-only turn must never synthesize a placeholder text block.
"""

from __future__ import annotations

import pytest

from the_one.interfaces.web.app import _build_user_content
from the_one.llm.base import ImageContent, TextContent


def test_no_images_returns_plain_string() -> None:
    result = _build_user_content("hello", [])
    assert result == "hello"
    assert isinstance(result, str)


def test_no_images_none_returns_plain_string() -> None:
    result = _build_user_content("hello", None)
    assert result == "hello"


def test_text_and_image_builds_text_then_image_blocks() -> None:
    images = [{"data": "abc123", "media_type": "image/png"}]
    result = _build_user_content("what is this?", images)
    assert result == [
        TextContent(text="what is this?"),
        ImageContent(media_type="image/png", data="abc123"),
    ]


def test_image_only_omits_empty_text_content() -> None:
    """The empty-text-block guard: no text -> no TextContent at all."""
    images = [{"data": "abc123", "media_type": "image/png"}]
    result = _build_user_content("", images)
    assert result == [ImageContent(media_type="image/png", data="abc123")]
    assert not any(isinstance(b, TextContent) for b in result)


def test_multiple_images_all_included() -> None:
    images = [
        {"data": "aaa", "media_type": "image/png"},
        {"data": "bbb", "media_type": "image/jpeg"},
    ]
    result = _build_user_content("compare these", images)
    assert result == [
        TextContent(text="compare these"),
        ImageContent(media_type="image/png", data="aaa"),
        ImageContent(media_type="image/jpeg", data="bbb"),
    ]


class TestMalformedImagePayloadRaises:
    """M18 F02 L01: the WS message branch wraps this call in a narrow
    ``try/except Exception`` (``the_one/interfaces/web/app.py``,
    ``websocket_endpoint``) specifically because ``_build_user_content``
    can raise on a malformed ``images`` entry. Pinned here at the
    function level; loop-survival (the guard actually catching these and
    keeping the WS alive) is covered by
    ``tests/test_ws_message_branch_crash_guard.py``.
    """

    def test_unexpected_image_key_raises_type_error(self) -> None:
        images = [{"media_type": "image/png", "data": "abc", "bogus_key": "x"}]
        with pytest.raises(TypeError):
            _build_user_content("what is this?", images)

    def test_missing_data_and_url_raises_assertion_error(self) -> None:
        images = [{"media_type": "image/png"}]
        with pytest.raises(AssertionError):
            _build_user_content("what is this?", images)
