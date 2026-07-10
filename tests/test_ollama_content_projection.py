"""M16 F12 L06: multimodal USER-content projection for both Ollama wire paths.

Ollama has two distinct USER-turn projections, both forked here for
``list[ContentBlock]`` content:

- ``/v1`` (OpenAI-compat, ``_to_api_message``): base64 data-URI image_url
  content parts only — Ollama's ``/v1`` layer has no remote-URL support
  (DD5), so a url-only ``ImageContent`` is skipped + a warning logged.
- native (``/api/chat``, ``_to_native_message``): a text ``content`` string
  (joined ``TextContent`` texts) plus a message-level ``images: [base64,
  …]`` array; a url-only image is likewise skipped + warned, and the
  ``images`` key is omitted entirely when no base64 image is present.

The ``str`` content path must stay byte-identical to pre-L06 behavior on
both projections (no fork triggers for plain-string content).
"""

from __future__ import annotations

import logging

import pytest

from the_one.llm.base import ImageContent, Message, TextContent
from the_one.llm.ollama_provider import OllamaProvider


def _provider() -> OllamaProvider:
    return OllamaProvider(model="m", base_url="http://localhost:11434/v1")


class TestV1ContentProjection:
    def test_list_projects_text_and_base64_image(self) -> None:
        prov = _provider()
        msg = Message.user(
            [
                TextContent(text="hello"),
                ImageContent(media_type="image/png", data="abc123"),
            ]
        )
        assert prov._to_api_message(msg) == {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,abc123"},
                },
            ],
        }

    def test_url_only_image_skipped_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        prov = _provider()
        msg = Message.user([ImageContent(media_type="image/jpeg", url="http://x/img.jpg")])
        with caplog.at_level(logging.WARNING):
            result = prov._to_api_message(msg)
        assert result == {"role": "user", "content": []}
        assert any(
            "ollama /v1" in r.message and "remote image URL" in r.message for r in caplog.records
        )

    def test_prefix_block_folds_into_leading_text_part(self) -> None:
        prov = _provider()
        msg = Message.user(
            [TextContent(text="hi")],
            peer_name="Ann",
            channel_name="general",
        )
        result = prov._to_api_message(msg)
        assert result["content"][0] == {
            "type": "text",
            "text": "[from Ann in #general]:",
        }
        assert result["content"][1] == {"type": "text", "text": "hi"}

    def test_str_content_byte_identical(self) -> None:
        prov = _provider()
        msg = Message.user("plain text")
        assert prov._to_api_message(msg) == {"role": "user", "content": "plain text"}


class TestNativeContentProjection:
    def test_list_projects_joined_content_and_images_array(self) -> None:
        prov = _provider()
        msg = Message.user(
            [
                TextContent(text="hello"),
                TextContent(text="world"),
                ImageContent(media_type="image/png", data="abc123"),
            ]
        )
        assert prov._to_native_message(msg) == {
            "role": "user",
            "content": "hello world",
            "images": ["abc123"],
        }

    def test_url_only_image_skipped_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        prov = _provider()
        msg = Message.user([ImageContent(media_type="image/jpeg", url="http://x/img.jpg")])
        with caplog.at_level(logging.WARNING):
            result = prov._to_native_message(msg)
        assert result == {"role": "user", "content": ""}
        assert "images" not in result
        assert any(
            "ollama native" in r.message and "remote image URL" in r.message for r in caplog.records
        )

    def test_images_key_omitted_when_no_base64_image(self) -> None:
        prov = _provider()
        msg = Message.user([TextContent(text="just text")])
        result = prov._to_native_message(msg)
        assert result == {"role": "user", "content": "just text"}
        assert "images" not in result

    def test_prefix_block_folds_into_joined_content(self) -> None:
        prov = _provider()
        msg = Message.user(
            [TextContent(text="hi")],
            peer_name="Ann",
            channel_name="general",
        )
        result = prov._to_native_message(msg)
        assert result["content"] == "[from Ann in #general]: hi"

    def test_str_content_byte_identical(self) -> None:
        prov = _provider()
        msg = Message.user("plain text")
        assert prov._to_native_message(msg) == {"role": "user", "content": "plain text"}
