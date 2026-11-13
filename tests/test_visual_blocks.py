"""``the_one.visuals.blocks.find_blocks``: the fence rule, held equal to the frozen
``evals.checks._top_level_blocks`` by the parity corpus (M35 F3 L3, AC1-AC2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals import checks
from the_one.visuals.blocks import Block, find_blocks

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "visual-blocks" / "replies.json").read_text("utf-8")
)


def test_the_corpus_is_big_enough() -> None:
    assert len(CORPUS) >= 20


@pytest.mark.parametrize("tag", ["chart", "widget"])
@pytest.mark.parametrize("reply", CORPUS, ids=range(len(CORPUS)))
def test_find_blocks_matches_the_frozen_evals_finder(reply: str, tag: str) -> None:
    ours = [(b.body, b.closed) for b in find_blocks(reply) if b.tag == tag]
    assert ours == checks._top_level_blocks(reply, tag)


@pytest.mark.parametrize("reply", CORPUS, ids=range(len(CORPUS)))
def test_spans_rebuild_the_text(reply: str) -> None:
    blocks = find_blocks(reply)
    out, pos = [], 0
    for b in blocks:
        assert b.start >= pos
        out.append(reply[pos : b.start])  # the gap
        out.append(reply[b.start : b.end])  # the block's source
        pos = b.end
    out.append(reply[pos:])
    assert "".join(out) == reply


def test_a_span_is_opener_through_closer() -> None:
    text = "a\n```chart\n{}\n```\nb"
    (b,) = find_blocks(text)
    assert text[b.start : b.end] == "```chart\n{}\n```\n"
    assert (b.tag, b.body, b.closed) == ("chart", "{}\n", True)


def test_a_closer_at_the_very_end_has_no_newline_in_its_span() -> None:
    text = "```chart\n{}\n```"
    (b,) = find_blocks(text)
    assert b.end == len(text)
    assert text[b.start : b.end] == text


def test_an_unterminated_block_runs_to_the_end() -> None:
    text = "x\n```widget\n<p>hi\n"
    (b,) = find_blocks(text)
    assert not b.closed
    assert b.end == len(text)
    assert text[b.start : b.end] == "```widget\n<p>hi\n"


def test_a_json_fence_swallows_a_chart_fence() -> None:
    text = "```json\n```chart\n{}\n```\n"
    assert [b.tag for b in find_blocks(text)] == ["json"]


def test_crlf_keeps_the_return_in_the_body() -> None:
    text = "```chart\r\n{}\r\n```\r\n"
    (b,) = find_blocks(text)
    assert b.body == "{}\r\n"  # "\r" stays on the line, as the frozen finder has it
    assert text[b.start : b.end] == text.rstrip("\n") + "\n"


def test_block_is_frozen() -> None:
    b = find_blocks("```chart\n```")[0]
    assert isinstance(b, Block)
    with pytest.raises(Exception):
        b.tag = "x"  # type: ignore[misc]
