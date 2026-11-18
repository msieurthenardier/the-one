"""GleepGlorp's shipped prompt (M36 F1 L08): its links, its must-keep items, its size."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tests._app_routes import check_route, link_targets
from the_one.gleepglorp import prompt as gp

TOOL_NAMES = ("get_app_guide", "read_app_config", "fetch_url", "web_search", "note")


def test_every_link_in_the_prompt_is_a_page_the_app_serves() -> None:
    for tools in (True, False):
        text = gp.base_prompt(tools=tools)
        targets = [t for t in link_targets(text) if t != "#route"]  # "#route" is the format
        assert len(targets) >= 9
        for target in targets:
            assert target.startswith("#"), target
            assert check_route(target) is None, (target, check_route(target))


def test_the_link_check_catches_an_alias() -> None:
    bad = gp.LINKS + "\n- [Providers](#library/providers)"
    assert check_route(link_targets(bad)[-1]) is not None


def test_the_must_keep_items_are_in_both_variants() -> None:
    for tools in (True, False):
        text = gp.base_prompt(tools=tools).lower()
        assert "only help with this app" in text and "decline" in text
        assert "own agents" in text
        assert "cannot change anything" in text
        assert "never say or imply that you changed" in text
        assert "never ask for, repeat or write a secret" in text
        assert "do not repeat it" in text
        assert "never promise an ability" in text
        assert "[text](#route)" in text


def test_the_tool_free_variant_names_no_tool() -> None:
    free = gp.base_prompt(tools=False)
    for name in TOOL_NAMES:
        assert name not in free
    full = gp.base_prompt(tools=True)
    assert "get_app_guide" in full and "read_app_config" in full


def test_the_sections_are_joined_in_order() -> None:
    parts = [gp.IDENTITY, gp.SCOPE, gp.LIMITS, gp.SECRETS, gp.ANSWERING_TOOLS, gp.LINKS, gp.STYLE]
    assert gp.base_prompt() == "\n\n".join(parts)
    assert gp.base_prompt(tools=False) == "\n\n".join(
        [*parts[:4], gp.ANSWERING_TOOL_FREE, *parts[5:]]
    )


def test_the_tool_capable_prompt_fits_450_tokens() -> None:
    os.environ.setdefault(
        "TIKTOKEN_CACHE_DIR", str(Path(__file__).resolve().parent.parent / "evals/.cache/tiktoken")
    )
    tiktoken = pytest.importorskip("tiktoken")
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception:  # noqa: BLE001 - no cached encoding and no network
        pytest.skip("o200k_base is not cached")
    assert len(enc.encode(gp.base_prompt(tools=True))) <= 450
    assert len(enc.encode(gp.base_prompt(tools=False))) <= 450


def test_no_section_has_an_unfilled_placeholder() -> None:
    assert not re.search(r"\{[a-z_ ]+\}", gp.base_prompt())
