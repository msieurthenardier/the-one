"""``the_one.visuals.outbound.plan_outbound`` (M35 F3 L3, AC3-AC5, AC12)."""

from __future__ import annotations

import json

from the_one.connectors import base
from the_one.visuals import outbound
from the_one.visuals.outbound import (
    CHART_MARKER,
    MAX_IMAGES,
    WIDGET_NOTE,
    plan_outbound,
)


def _chart(title: str = "", n: int = 3) -> str:
    spec = {
        "type": "bar",
        "x": {"values": [f"Q{i}" for i in range(n)]},
        "series": [{"values": list(range(n))}],
    }
    if title:
        spec["title"] = title
    return "```chart\n" + json.dumps(spec) + "\n```\n"


def test_plain_text_and_non_visual_fences_have_no_plan() -> None:
    assert plan_outbound("hello") is None
    assert plan_outbound("```python\nprint(1)\n```\n") is None
    assert plan_outbound("") is None


def test_invalid_and_unterminated_charts_have_no_plan() -> None:
    assert plan_outbound("```chart\n{not json}\n```\n") is None
    assert plan_outbound("```chart\n" + json.dumps({"type": "bar"})) is None
    assert plan_outbound(_chart("t").rstrip("\n").rsplit("```", 1)[0]) is None


def test_a_valid_chart_is_a_candidate_with_a_marker() -> None:
    text = "before\n" + _chart("Revenue by region") + "after"
    plan = plan_outbound(text)
    assert plan is not None and len(plan.candidates) == 1
    cand = plan.candidates[0]
    assert (cand.index, cand.number, cand.alt) == (0, 1, "Revenue by region")
    assert plan.render({0}) == (
        "before\n" + CHART_MARKER.format(title="Revenue by region") + "\nafter"
    )
    assert plan.render({0}).startswith("before\n\U0001f4ca Chart: Revenue by region (below)\n")


def test_fallback_text_is_the_original_text_for_a_chart_only_reply() -> None:
    text = "before\n" + _chart("T") + "after"
    plan = plan_outbound(text)
    assert plan.fallback_text == plan.render(set()) == text


def test_the_title_collapses_whitespace_and_empty_uses_the_number() -> None:
    plan = plan_outbound(_chart("  a\n\tb   c ") + _chart("   "))
    # the second block's title is whitespace only
    assert plan.candidates[0].alt == "a b c"
    assert plan.candidates[1].alt == "Chart 2"
    assert plan.render({0, 1}).splitlines() == [
        "\U0001f4ca Chart: a b c (below)",
        "\U0001f4ca Chart 2 (below)",
    ]


def test_numbering_counts_invalid_chart_blocks() -> None:
    text = "```chart\n{bad}\n```\n" + _chart()
    plan = plan_outbound(text)
    assert len(plan.candidates) == 1
    assert plan.candidates[0].number == 2
    assert plan.candidates[0].index == 0
    assert plan.render({0}).endswith("\U0001f4ca Chart 2 (below)\n")
    assert plan.render({0}).startswith("```chart\n{bad}\n```\n")


def test_every_widget_block_becomes_the_note_closed_or_not() -> None:
    plan = plan_outbound("a\n```widget\n<p>x</p>\n```\nb\n```widget\n<p>cut")
    assert plan.candidates == ()
    assert plan.fallback_text == f"a\n{WIDGET_NOTE}\nb\n{WIDGET_NOTE}"
    assert plan.render(set()) == plan.fallback_text


def test_widget_at_the_end_of_text_without_newline_has_none() -> None:
    plan = plan_outbound("x\n```widget\n```")
    assert plan.fallback_text == "x\n" + WIDGET_NOTE


def test_a_block_directly_after_text_gets_its_own_line() -> None:
    plan = plan_outbound("intro\n" + _chart("T"))
    assert plan.render({0}) == "intro\n\U0001f4ca Chart: T (below)\n"


def test_only_the_first_ten_candidates_are_kept() -> None:
    text = "".join(_chart(f"c{i}") for i in range(12))
    plan = plan_outbound(text)
    assert len(plan.candidates) == MAX_IMAGES == 10
    rendered = plan.render({c.index for c in plan.candidates})
    assert rendered.count("(below)") == 10
    # the 11th and 12th stay as code in every rendering
    assert rendered.count("```chart") == 2
    assert plan.fallback_text == text
    assert plan.candidates[-1].number == 10


def test_render_by_index_with_a_mixed_drawn_set_and_duplicate_titles() -> None:
    a, b, c = _chart("Same"), _chart("Same", n=4), _chart("Other")
    plan = plan_outbound(a + b + c)
    out = plan.render({1})
    assert out == a + CHART_MARKER.format(title="Same") + "\n" + c
    assert plan.render({0, 2}) == (
        CHART_MARKER.format(title="Same") + "\n" + b + CHART_MARKER.format(title="Other") + "\n"
    )


def test_a_chart_and_a_widget_together() -> None:
    plan = plan_outbound(_chart("T") + "```widget\n<i/>\n```\n")
    assert len(plan.candidates) == 1
    assert plan.render({0}) == f"\U0001f4ca Chart: T (below)\n{WIDGET_NOTE}\n"
    assert plan.fallback_text == _chart("T") + WIDGET_NOTE + "\n"


def test_outbound_image_is_the_connector_base_export() -> None:
    assert base.OutboundImage is outbound.OutboundImage
    assert issubclass(base.VisualUploadError, base.ConnectorClientError)
