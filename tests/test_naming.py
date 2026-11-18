"""The naming rule (sortie 06 DD1-DD5) and the boxed scratch-directory slug (DD13)."""

import pytest

from the_one import naming
from the_one.naming import NameRuleError, check_name, name_rule_detail
from the_one.tools.sessions import _scratch_slug


@pytest.mark.parametrize(
    "value",
    ["default", "My.Notes", "café", "a?b", "x" * 64, "👩‍💻 helper", "with space", "a..b"],
)
def test_accepts(value) -> None:
    assert check_name(value) == value


@pytest.mark.parametrize("value", ["default", "Default", " GleepGlorp ", "GLEEPGLORP"])
def test_reserved_agent_names(value) -> None:
    assert naming.is_reserved_agent_name(value)
    with pytest.raises(NameRuleError):
        naming.check_agent_name(value)


@pytest.mark.parametrize("value", ["gleep-glorp", "GleepGlorpX", "defaults", None, 5])
def test_not_reserved_agent_names(value) -> None:
    assert not naming.is_reserved_agent_name(value)
    if isinstance(value, str):
        assert naming.check_agent_name(value) == value


def test_trims() -> None:
    assert check_name("  padded \t") == "padded"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", naming.EMPTY),
        ("   ", naming.EMPTY),
        (None, naming.EMPTY),
        (5, naming.EMPTY),
        (["a"], naming.EMPTY),
        ("a/b", naming.SEPARATOR),
        ("a\\b", naming.SEPARATOR),
        ("/", naming.SEPARATOR),
        ("a/..", naming.SEPARATOR),
        (".", naming.DOTS),
        (" .. ", naming.DOTS),
        ("a\x00b", naming.CONTROL),
        ("a\nb", naming.CONTROL),
        ("a‮b", naming.CONTROL),
        ("a⁦b", naming.CONTROL),
        ("x" * 65, naming.TOO_LONG),
    ],
)
def test_refuses(value, message) -> None:
    with pytest.raises(NameRuleError) as exc:
        check_name(value)
    assert exc.value.message == message


def test_length_counts_code_points_after_trim() -> None:
    assert check_name(" " + "x" * 64 + " ") == "x" * 64


def test_messages() -> None:
    assert naming.SEPARATOR == "A name can't contain / or \\."
    assert naming.DOTS == "A name can't be . or .."


def test_detail_shape() -> None:
    assert name_rule_detail("m") == [{"type": "name_rule", "loc": ["name"], "msg": "m"}]


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("plain-agent_1", "plain-agent_1"),
        ("a/../b", "a____b"),
        ("CON:", "CON_"),
        ("", "agent"),
        ("x" * 80, "x" * 40),
    ],
)
def test_scratch_slug(name, slug) -> None:
    assert _scratch_slug(name) == slug
    assert "/" not in _scratch_slug(name)


# ── repair_name ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        ("ops/bot", "agent", "ops bot"),
        ("a\\b", "agent", "a b"),
        ("a\tb", "agent", "a b"),
        ("a\nb", "agent", "a b"),
        ("a\x00b", "agent", "ab"),
        ("a‮b", "agent", "ab"),
        ("  a   /  b  ", "agent", "a b"),
        ("/", "agent", "Renamed agent"),
        ("..", "provider", "Renamed provider"),
        (".", "knowledge_base", "Renamed knowledge base"),
        ("", "mcp_source", "Renamed MCP server"),
        ("Café 🎉", "agent", "Café 🎉"),
        ("x" * 70, "agent", "x" * 64),
    ],
)
def test_repair_name(value, kind, expected) -> None:
    out = naming.repair_name(value, kind=kind, taken=set())
    assert out == expected
    assert check_name(out) == out


def test_repair_name_combining_cut_at_64() -> None:
    value = "x" * 63 + "é"
    out = naming.repair_name(value, kind="agent", taken=set())
    assert len(out) <= 64
    assert check_name(out) == out


def test_repair_name_numbers_collisions_case_insensitively() -> None:
    taken = {"ops bot", "OPS BOT 2"}
    assert naming.repair_name("ops/bot", kind="agent", taken=taken) == "ops bot 3"


def test_repair_name_numbering_stays_within_limit() -> None:
    base = "y" * 64
    out = naming.repair_name(base + "z", kind="agent", taken={base})
    assert len(out) == 64
    assert out.endswith(" 2")
    assert check_name(out) == out
