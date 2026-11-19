"""The app guide and ``get_app_guide`` (M36 F1 L07, DD6).

Three things are pinned here:

* the tool: exact, case-insensitive ids; the list for an unknown or empty topic; the ids
  in the tool description; its place in ``TRUSTED_TOOL_NAMES``;
* the guide's own rules (``validate_topic``): a ``# Title`` then a one-sentence summary
  paragraph, at most 600 words, no internal names, and every link a route the router
  serves and does not redirect. Each rule has a planted case that must fail, so a rule
  that stops working is noticed;
* packaging: the guide files are package data and in all three freeze specs, and the tool
  lists the topics through the same ``Path(__file__)`` layout the installed package has.

The route sets come from the client source (``tests/_app_routes.py``), never a copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import _app_routes as routes_mod
from tests._app_routes import Routes, check_route, link_targets
from the_one.agent.taint import TRUSTED_TOOL_NAMES
from the_one.gleepglorp import guide_tool
from the_one.gleepglorp.guide_tool import GET_APP_GUIDE_TOOL_NAME, TOPICS, GetAppGuideTool

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "the_one" / "gleepglorp" / "guide"
MAX_WORDS = 600

_TITLE = re.compile(r"^# \S.*$")
_INTERNAL = [
    (re.compile(r"the_one"), "an internal package path"),
    (re.compile(r"test-?id", re.I), "a test id"),
    (re.compile(r"\b[\w-]+\.(?:js|py|css|html|toml|spec|sh|md)\b"), "a source file name"),
    (re.compile(r"/api/"), "an API route"),
    (re.compile(r"\bApp\.[a-z]"), "a client object"),
    (re.compile(r"\bagents\.md\b|CLAUDE"), "a project document"),
]


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def validate_topic(topic_id: str, text: str, routes: Routes | None = None) -> list[str]:
    """Every rule a guide topic breaks, as plain sentences (empty when it is fine)."""
    problems: list[str] = []
    lines = text.splitlines()
    if not lines or not _TITLE.match(lines[0]):
        problems.append(f"{topic_id}: the first line must be '# Title'")
    rest = [ln for ln in lines[1:]]
    while rest and not rest[0].strip():
        rest.pop(0)
    summary = []
    for ln in rest:
        if not ln.strip():
            break
        summary.append(ln)
    if not summary:
        problems.append(f"{topic_id}: no summary paragraph after the title")
    else:
        first = summary[0].lstrip()
        sentence = " ".join(s.strip() for s in summary)
        if first.startswith(("#", "-", "*", ">", "1.")):
            problems.append(f"{topic_id}: the summary must be a plain paragraph")
        elif not sentence.endswith(".") or re.search(r"[.!?]\s+[A-Z]", sentence):
            problems.append(f"{topic_id}: the summary must be exactly one sentence")
    n = words(text)
    if n > MAX_WORDS:
        problems.append(f"{topic_id}: {n} words, over the {MAX_WORDS} limit")
    for pattern, what in _INTERNAL:
        m = pattern.search(text)
        if m:
            problems.append(f"{topic_id}: contains {what} ({m.group(0)!r})")
    for target in link_targets(text):
        if not target.startswith("#"):
            problems.append(f"{topic_id}: link {target!r} must be an in-app route")
            continue
        why = check_route(target, routes)
        if why:
            problems.append(f"{topic_id}: link {target!r}: {why}")
    return problems


def _good(extra: str = "") -> str:
    return "# A topic\n\nThis is the summary.\n\nSome help text. " + extra + "\n"


# ── The route sets come from the client source ───────────────────────────────


def test_the_parsers_read_the_real_tables() -> None:
    assert routes_mod.library_groups() == ["providers", "knowledge", "mcp", "connectors", "secrets"]
    assert "gleepglorp" in routes_mod.settings_sections()
    assert "knowledge-indexing" in routes_mod.settings_sections()
    assert "providers" not in routes_mod.settings_sections()
    assert routes_mod.agent_tabs() == [
        "general",
        "rules-and-notes",
        "knowledge",
        "tools",
        "routines",
        "self-configuration",
    ]


@pytest.mark.parametrize(
    "route",
    [
        "#chats",
        "#chats/~new/GleepGlorp",
        "#agents",
        "#agents/~new",
        "#agents/Helper",
        "#agents/Helper/tools",
        "#agents/Helper/self-configuration",
        "#library",
        "#library/mcp/~new",
        "#library/providers/~new",
        "#library/secrets/~new",
        "#settings/gleepglorp",
        "#settings/date-and-time",
        "#settings/tools",
        "#settings/tools/web_search",
        "settings/knowledge-indexing",
    ],
)
def test_served_routes_pass(route: str) -> None:
    assert check_route(route) is None


@pytest.mark.parametrize(
    ("route", "why"),
    [
        ("#library/mcp", "alias"),
        ("#library/knowledge", "alias"),
        ("#library/widgets/~new", "not a Library group"),
        ("#settings", "alias"),
        ("#settings/general", "alias"),
        ("#settings/general/theme", "alias"),
        ("#settings/providers", "not a Settings section"),
        ("#settings/appearance/x", "no item pages"),
        ("#agents/Helper/mcps", "alias"),
        ("#agents/Helper/billing", "not an agent tab"),
        ("#agents/~new/x", "dropped"),
        ("#chats/~new", "alias"),
        ("#chat", "legacy"),
        ("#studio/agents", "legacy"),
        ("#admin/system", "legacy"),
        ("#help", "not a destination"),
        ("#", "empty"),
    ],
)
def test_aliases_and_unknown_routes_fail(route: str, why: str) -> None:
    got = check_route(route)
    assert got is not None and why in got, (route, got)


def test_a_route_missing_from_the_tables_fails_by_planting() -> None:
    """A table row that goes away fails the guide link that used it (planted sets)."""
    real = routes_mod.load_routes()
    no_secrets = Routes(real.library_groups - {"secrets"}, real.settings_sections, real.agent_tabs)
    assert check_route("#library/secrets/~new", real) is None
    assert "not a Library group" in (check_route("#library/secrets/~new", no_secrets) or "")
    no_page = Routes(real.library_groups, real.settings_sections - {"encryption"}, real.agent_tabs)
    assert "not a Settings section" in (check_route("#settings/encryption", no_page) or "")
    no_tab = Routes(real.library_groups, real.settings_sections, real.agent_tabs - {"routines"})
    assert "not an agent tab" in (check_route("#agents/A/routines", no_tab) or "")


# ── The guide's own rules, each with a planted failing case ──────────────────


def test_a_good_topic_passes() -> None:
    assert validate_topic("t", _good("See [Library](#library/mcp/~new).")) == []


@pytest.mark.parametrize(
    ("text", "expect"),
    [
        ("No title here.\n\nSummary.\n", "first line"),
        ("#Title\n\nSummary.\n", "first line"),
        ("# Title\n", "no summary"),
        ("# Title\n\n- a list, not a paragraph.\n", "plain paragraph"),
        ("# Title\n\nOne. Two sentences here.\n", "exactly one sentence"),
        ("# Title\n\nNo full stop\n", "exactly one sentence"),
        ("# Title\n\nSummary.\n\n" + "word " * 601, "over the 600 limit"),
        ("# Title\n\nSummary.\n\nSee the_one/agent for it.", "internal package path"),
        ("# Title\n\nSummary.\n\nUse data-testid to find it.", "test id"),
        ("# Title\n\nSummary.\n\nOpen router.js to see.", "source file name"),
        ("# Title\n\nSummary.\n\nEdit api.py now.", "source file name"),
        ("# Title\n\nSummary.\n\nCall /api/agents.", "API route"),
        ("# Title\n\nSummary.\n\nSee [x](#library/mcp).", "alias"),
        ("# Title\n\nSummary.\n\nSee [x](#settings/nowhere).", "not a Settings section"),
        ("# Title\n\nSummary.\n\nSee [x](https://example.com).", "in-app route"),
    ],
)
def test_each_rule_has_a_planted_failure(text: str, expect: str) -> None:
    problems = validate_topic("t", text)
    assert any(expect in p for p in problems), problems


def test_exactly_600_words_pass_and_601_fail() -> None:
    head = "# T\n\nSummary here.\n\n"  # 4 words
    assert validate_topic("t", head + "word " * 596) == []
    assert any("limit" in p for p in validate_topic("t", head + "word " * 597))


# ── The real guide ───────────────────────────────────────────────────────────


def test_every_topic_id_has_a_file_and_every_file_a_topic() -> None:
    files = {p.stem for p in GUIDE.glob("*.md")}
    assert files == set(TOPICS), files ^ set(TOPICS)
    for topic_id in TOPICS:
        assert re.fullmatch(r"[a-z0-9-]+", topic_id)


def test_the_required_topics_exist() -> None:
    required = {
        "overview",
        "agents",
        "agent-tools",
        "rules-and-notes",
        "routines",
        "self-configuration",
        "mcp-servers",
        "model-providers",
        "knowledge-bases",
        "connectors",
        "secrets",
        "settings",
        "gleepglorp",
    }
    assert required <= set(TOPICS)


@pytest.mark.parametrize("topic_id", list(TOPICS))
def test_the_real_topic_follows_the_rules(topic_id: str) -> None:
    text = (GUIDE / f"{topic_id}.md").read_text(encoding="utf-8")
    assert validate_topic(topic_id, text) == []


def test_a_missing_file_for_a_topic_id_is_caught(monkeypatch) -> None:
    """Planted: a topic id with no file fails the id/file tie, and the tool lists around it."""
    monkeypatch.setitem(TOPICS, "ghost", "a topic with no file")
    assert {p.stem for p in GUIDE.glob("*.md")} != set(TOPICS)
    assert guide_tool.read_topic("ghost") is None


# ── The tool ─────────────────────────────────────────────────────────────────


async def test_the_tool_returns_a_topic_by_exact_case_insensitive_id() -> None:
    tool = GetAppGuideTool()
    text = await tool.execute(topic="agent-tools")
    assert text == (GUIDE / "agent-tools.md").read_text(encoding="utf-8")
    assert await tool.execute(topic="  Agent-Tools ") == text
    assert await tool.execute(topic="AGENT-TOOLS") == text


async def test_an_unknown_or_empty_topic_lists_every_topic_with_its_summary() -> None:
    tool = GetAppGuideTool()
    for given in ("nope", "", None, "agent", 7, "agent-tools extra"):
        listing = await tool.execute(topic=given)
        assert listing.startswith("App guide topics.")
        for topic_id in TOPICS:
            assert f"- {topic_id}: " in listing
            title, summary = guide_tool.title_and_summary(
                (GUIDE / f"{topic_id}.md").read_text(encoding="utf-8")
            )
            assert f"{title}. {summary}" in listing
    assert await tool.execute() == await tool.execute(topic="nope")


def test_the_description_names_every_topic() -> None:
    tool = GetAppGuideTool()
    for topic_id in TOPICS:
        assert topic_id in tool.description
    props = tool.to_schema()["parameters"]["properties"]
    assert set(props) == {"topic"}


def test_the_tool_is_trusted_and_the_names_agree() -> None:
    assert GET_APP_GUIDE_TOOL_NAME == "get_app_guide"
    assert GET_APP_GUIDE_TOOL_NAME in TRUSTED_TOOL_NAMES
    # The tools that read outside text or configuration stay untrusted.
    for name in ("read_app_config", "fetch_url", "web_search"):
        assert name not in TRUSTED_TOOL_NAMES


def test_the_tool_does_no_network_and_no_write() -> None:
    src = (ROOT / "the_one" / "gleepglorp" / "guide_tool.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for banned in ("httpx", "requests", "urllib", "socket", "write_text", "write_bytes", "open("):
        assert banned not in code, banned


# ── Packaging ────────────────────────────────────────────────────────────────


def test_the_guide_is_package_data_and_in_every_freeze_spec() -> None:
    assert '"gleepglorp/guide/*.md"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for platform in ("windows", "linux", "macos"):
        text = (ROOT / "packaging" / platform / "the-one.spec").read_text(encoding="utf-8")
        assert re.search(
            r'collect_data_files\("the_one",\s*includes=\["gleepglorp/guide/\*\.md"\]\)', text
        ), platform
        assert re.search(r"^\s*\*guide_datas,$", text, re.M), platform


def test_the_tool_reads_the_guide_through_its_own_package_path() -> None:
    """The directory the tool reads is the one beside its own module, the layout an
    installed or frozen package keeps (no importlib.resources, no repo-relative path)."""
    assert guide_tool.GUIDE_DIR == Path(guide_tool.__file__).parent / "guide"
    assert {p.stem for p in guide_tool.GUIDE_DIR.glob("*.md")} == set(TOPICS)
    listing = guide_tool.topic_list()
    assert all(f"- {t}: " in listing for t in TOPICS)
