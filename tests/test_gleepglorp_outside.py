"""The outside-value guard (M36 F4 L3, DD7): helpers, the two source tiers, the check, and the
two tools that run it (``propose_change`` and ``fill_form``)."""

# ruff: noqa: F811, N802, E501
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from tests._gleepglorp_seed import seed
from the_one.agent._context import TurnContext, current_tool_call_id, current_turn
from the_one.agent.taint import find_anchor
from the_one.gleepglorp import kinds, outside
from the_one.gleepglorp.fill.store import GleepGlorpFillRepository
from the_one.gleepglorp.fill.tool import FillFormTool
from the_one.gleepglorp.outside import (
    LOADER_KEY_GLOBS,
    TLD_ALLOWLIST,
    check,
    collect,
    deescape,
    extract_addresses,
    fold,
    is_loader_key,
    normalize_url,
    token_match,
)
from the_one.gleepglorp.proposals.shape import FieldSpec, Normalized
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository
from the_one.gleepglorp.proposals.tool import ProposeChangeTool
from the_one.llm.base import ImageContent, Message, TextContent, ToolCall, ToolResult

# --- history builders ------------------------------------------------------------------


def U(text, **marks) -> Message:
    m = Message.user(text)
    for k, v in marks.items():
        setattr(m, k, v)
    return m


def A(*calls: tuple[str, str, dict]) -> Message:
    return Message.assistant(
        "", tool_calls=[ToolCall(id=i, name=n, arguments=a) for i, n, a in calls]
    )


def T(cid: str, content: str) -> Message:
    return Message.tool(ToolResult(tool_call_id=cid, content=content))


def fetch(cid: str, url: str) -> tuple[str, str, dict]:
    return (cid, "fetch_url", {"url": url})


def fake_agent(*messages: Message):
    return SimpleNamespace(messages=list(messages))


def tail(call_id: str = "z") -> Message:
    """The assistant message holding the proposing call (the anchor)."""
    return A((call_id, "propose_change", {}))


def sources_of(*messages: Message, turn=None):
    return collect(fake_agent(*messages, tail()), "z", turn)


PAGE_URL = "https://github.com/acme/mcp-thing"
README = "[200]\n# mcp-thing\nRun `npx -y @acme/mcp-server` to start it."


# --- fold, normalize_url, deescape -------------------------------------------------------


def test_fold_is_nfkc_and_drops_format_characters() -> None:
    assert fold("ｅｖｉｌ．ｃｏｍ") == "evil.com"
    assert fold("ev​il‮.com﻿") == "evil.com"


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("example.com/docs", "https://example.com/docs"),
        ("HTTPS://Example.COM/Docs", "https://example.com/Docs"),
        ("https://www.example.com/", "https://example.com"),
        ("https://example.com/a/#frag", "https://example.com/a"),
        ("https://example.com/a?x=1#f", "https://example.com/a?x=1"),
        ("https://example.com:8080/", "https://example.com:8080"),
        ("//evil.test/x", "https://evil.test/x"),
        ("http://example.com", "http://example.com"),
        ("https://user@good.com@evil.test/", "https://user@good.com@evil.test"),
    ],
)
def test_normalize_url(raw, want) -> None:
    assert normalize_url(raw) == want


def test_deescape_removes_markdown_escapes_entities_and_whitespace() -> None:
    assert deescape(r"server\_github  and \@scope/pkg\_name") == "server_github and @scope/pkg_name"
    assert deescape("a &amp; b\n\n c &lt;x&gt;") == "a & b c <x>"


# --- extract_addresses -------------------------------------------------------------------

MUST_PASS = [
    "10:30", "16:9", "file.py:12", "main.py", "README.md", "Node.js/express", "v1.2.3",
    "phi3:3.8b", "qwen2.5:14b", "llama3.1:70b", "gemma3:27b", "deepseek-r1:1.5b", "gpt-4o",
    "e.g.", "i.e.", "2026-11-21",
]  # fmt: skip


@pytest.mark.parametrize("text", MUST_PASS)
def test_extract_never_finds_these(text) -> None:
    assert extract_addresses(fold(f"use {text} here")) == []
    assert extract_addresses(fold(text)) == []


@pytest.mark.parametrize(
    ("text", "kind", "found"),
    [
        ("garden-stats.example.test", "domain", "garden-stats.example.test"),
        ("Evil.COM/x", "url", "Evil.COM/x"),
        ("ｅｖｉｌ．ｃｏｍ／ｘ", "url", "evil.com/x"),
        ("ev​il.com", "domain", "evil.com"),
        ("//evil.test/x", "url", "//evil.test/x"),
        ("ftp://evil.test", "url", "ftp://evil.test"),
        ("HTTPS://evil.test/a", "url", "HTTPS://evil.test/a"),
        ("ssh://git@evil.test/r", "url", "ssh://git@evil.test/r"),
        ("10.0.0.5", "ip", "10.0.0.5"),
        ("[::1]:8080", "hostport", "[::1]:8080"),
        ("evil.com:8080", "hostport", "evil.com:8080"),
        ("localhost:3000", "hostport", "localhost:3000"),
        ("www.evil.xyzzy", "url", "www.evil.xyzzy"),
        ("bookings@trips-example.test", "email", "bookings@trips-example.test"),
        ("--host=evil.com", "domain", "evil.com"),
        ("*.evil.com", "domain", "evil.com"),
    ],
)
def test_extract_finds_these(text, kind, found) -> None:
    assert [(a.kind, a.text) for a in extract_addresses(fold(text))] == [(kind, found)]


def test_trailing_punctuation_is_trimmed_and_balanced_parens_kept() -> None:
    assert [a.text for a in extract_addresses("see evil.com:8080.")] == ["evil.com:8080"]
    assert [a.text for a in extract_addresses("(https://x.test/a)")] == ["https://x.test/a"]
    assert [a.text for a in extract_addresses("[d](https://x.test/a_(b)).")] == [
        "https://x.test/a_(b)"
    ]
    assert [a.text for a in extract_addresses("[https://x.test](https://x.test)")] == [
        "https://x.test",
        "https://x.test",
    ]


def test_a_domain_is_one_address_not_its_suffix() -> None:
    [a] = extract_addresses("good.com.evil.test")
    assert a.text == "good.com.evil.test"


def test_the_tld_allowlist_excludes_file_extensions() -> None:
    for ext in ("py", "md", "js", "ts", "sh", "rs", "go", "pl", "rb", "cs", "json", "yaml", "txt"):
        assert ext not in TLD_ALLOWLIST
    assert "test" in TLD_ALLOWLIST and "com" in TLD_ALLOWLIST


# --- token_match -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("sh", "share"),
        ("good.com", "good.com.evil.test"),
        ("good.com", "good.com/x"),
        ("evil.com", "good.evil.com"),
        ("-y", "npx -yes pkg"),
        ("", "anything"),
    ],
)
def test_token_match_fails(value, text) -> None:
    assert token_match(value, text) is False


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("npx -y @acme/mcp-server", "Run `npx -y @acme/mcp-server` to start it."),
        ("npx -y @acme/mcp-server", "Start it with npx -y @acme/mcp-server."),
        ("npx  -y   @acme/mcp-server", "x npx -y @acme/mcp-server\nnext"),
        ("-y", "npx -y @pkg"),
        ("good.com", "visit good.com, then"),
        ("good.com", "good.com"),
    ],
)
def test_token_match_passes(value, text) -> None:
    assert token_match(value, text) is True


# --- is_loader_key -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "HTTPS_proxy",
        "no_proxy",
        " path ",
        "ＰＡＴＨ",
        "NODE_OPTIONS",
        "LD_PRELOAD",
        "GIT_CONFIG_COUNT",
    ],
)
def test_loader_keys(key) -> None:
    assert is_loader_key(key) is True


@pytest.mark.parametrize("key", ["PATHNAME", "ENVIRONMENT", "GITHUB_TOKEN", "API_KEY", "HOMEPAGE"])
def test_not_loader_keys(key) -> None:
    assert is_loader_key(key) is False


@pytest.mark.parametrize(
    "key",
    [
        "NODE_TLS_REJECT_UNAUTHORIZED",
        "HOME",
        "XDG_CONFIG_HOME",
        "PYTHONINSPECT",
        "BUN_INSTALL",
        "DENO_DIR",
        "GEM_HOME",
        "BUNDLE_GEMFILE",
        "JAVA_HOME",
        "MAVEN_OPTS",
        "GRADLE_OPTS",
    ],
)
def test_the_widened_loader_keys(key) -> None:
    assert is_loader_key(key) is True


def test_the_loader_glob_list_is_pinned() -> None:
    assert LOADER_KEY_GLOBS == (
        "PATH", "ENV", "SHELL", "IFS", "BASH_ENV", "PROMPT_COMMAND",
        "LD_*", "DYLD_*",
        "NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS",
        "NPM_CONFIG_*", "YARN_*", "PIP_*", "UV_*", "CARGO_*", "GOPROXY", "GOFLAGS",
        "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
        "PERL5OPT", "PERL5LIB", "RUBYOPT", "RUBYLIB", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS",
        "JDK_JAVA_OPTIONS", "CLASSPATH", "DOTNET_STARTUP_HOOKS",
        "GIT_SSH_COMMAND", "GIT_PROXY_COMMAND", "GIT_EXEC_PATH", "GIT_CONFIG*", "GIT_SSL_*",
        "*_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "NODE_TLS_REJECT_UNAUTHORIZED", "HOME", "XDG_*", "PYTHONINSPECT", "BUN_*", "DENO_*",
        "GEM_*", "BUNDLE_*", "JAVA_HOME", "MAVEN_OPTS", "GRADLE_OPTS",
    )  # fmt: skip


# --- find_anchor -------------------------------------------------------------------------


def test_find_anchor_scans_backwards() -> None:
    msgs = [U("a"), A(("c1", "x", {})), T("c1", "r"), A(("c1", "x", {})), T("c1", "r2")]
    assert find_anchor(msgs, "c1") == 3
    assert find_anchor(msgs, "nope") is None


# --- collect: tier 1 ---------------------------------------------------------------------


def test_tier_one_is_only_unmarked_typed_text() -> None:
    marked = [
        U("https://peer.test/x", peer_name="alice"),
        U("https://chan.test/x", channel_id="C1"),
        U("https://chan2.test/x", channel_name="general"),
        U("https://routine.test/x", routine_id="r1"),
        U("https://flagged.test/x", routine_untrusted_sources=["fetch_url"]),
        U("https://proposal.test/x", proposal_id="p1"),
        U("https://event.test/x", proposal_event="approved"),
    ]
    page = U("hello")
    page.page = {"line": "Agents > https://page.test/x"}
    src = sources_of(*marked, page, U("https://typed.test/x"))
    assert src.typed_urls == {"https://typed.test/x"}
    assert src.typed == ["hello", "https://typed.test/x"]


def test_tier_one_reads_text_blocks_not_images_or_assistant_or_tool_text() -> None:
    blocks = Message.user(
        [TextContent("see https://typed.test/a"), ImageContent(data="x", media_type="image/png")]
    )
    src = sources_of(
        blocks,
        A(("c1", "web_search", {})),
        T("c1", "https://tool.test/x"),
        Message.assistant("https://assistant.test/x"),
    )
    assert src.typed_urls == {"https://typed.test/a"}


def test_a_peer_turn_drops_the_unmarked_current_user_message() -> None:
    # The app binds a turn's marks onto its USER message only after the step, so the guard
    # drops the last USER message when the turn itself is a peer or routine turn.
    turn = TurnContext(session_id="s", routine_sources=["fetch_url"])
    src = sources_of(U("old https://a.test"), U("now https://b.test"), turn=turn)
    assert src.typed_urls == {"https://a.test"}


def test_no_anchor_is_none() -> None:
    assert collect(fake_agent(U("x")), "z") is None
    assert collect(None, "z") is None
    assert collect(fake_agent(tail()), None) is None


# --- collect: tier 2 ---------------------------------------------------------------------


def linked_hosts(*messages: Message) -> list[str]:
    return [item.host for item in sources_of(*messages).linked]


def test_a_fetch_of_a_typed_url_is_linked() -> None:
    for typed, fetched in [
        ("see https://docs.test/a", "https://docs.test/a"),
        ("see docs.test/a", "https://docs.test/a"),  # scheme-less
        ("see https://www.docs.test/a/", "https://docs.test/a"),  # www and slash
        ("see https://DOCS.test/a#frag", "https://docs.test/a"),
    ]:
        msgs = [U(typed), A(fetch("f1", fetched)), T("f1", "[200]\nbody")]
        assert linked_hosts(*msgs) == ["docs.test"], typed


def test_a_fetch_of_an_untyped_url_is_not_linked() -> None:
    msgs = [
        U("see https://docs.test/a"),
        A(fetch("f1", "https://docs.test/b")),
        T("f1", "[200]\nx"),
    ]
    assert linked_hosts(*msgs) == []
    msgs = [U("hello"), A(fetch("f1", "https://evil.test/")), T("f1", "[200]\nx")]
    assert linked_hosts(*msgs) == []


def test_only_a_2xx_result_counts() -> None:
    for body in ("[error] timeout", "[404]\nnot found", "[500]\nboom", "no status line"):
        msgs = [U("https://docs.test/a"), A(fetch("f1", "https://docs.test/a")), T("f1", body)]
        assert linked_hosts(*msgs) == [], body


def test_other_tools_are_never_tier_two() -> None:
    msgs = [
        U("https://docs.test/a"),
        A(("s1", "web_search", {"query": "https://docs.test/a"})),
        T("s1", "[200]\nhttps://evil.test"),
        A(("h1", "http_request", {"url": "https://docs.test/a"})),
        T("h1", "[200]\nhttps://evil.test"),
    ]
    assert linked_hosts(*msgs) == []


def test_the_operator_may_type_the_url_after_the_fetch() -> None:
    msgs = [
        A(fetch("f1", "https://docs.test/a")),
        T("f1", "[200]\nx"),
        U("it is https://docs.test/a"),
    ]
    assert linked_hosts(*msgs) == ["docs.test"]


@pytest.mark.parametrize(
    ("typed", "raw", "linked"),
    [
        ("github.com/acme/mcp-thing", "https://raw.githubusercontent.com/acme/mcp-thing/main/README.md", True),
        ("https://github.com/acme/mcp-thing/tree/main/docs", "https://raw.githubusercontent.com/acme/mcp-thing/HEAD/README.md", True),
        ("https://github.com/Acme/MCP-Thing", "https://raw.githubusercontent.com/acme/mcp-thing/main/README.md", True),
        ("https://github.com/acme/mcp-thing.git", "https://raw.githubusercontent.com/acme/mcp-thing/main/README.md", True),
        ("https://github.com/acme/mcp-thing", "https://raw.githubusercontent.com/acme/other/main/README.md", False),
        ("https://github.com/acme/mcp-thing", "https://raw.githubusercontent.com/evil/mcp-thing/main/README.md", False),
        ("https://github.com/acme/mcp-thing", "https://raw.githubusercontent.com/acme/mcp-thing-2/main/README.md", False),
        ("https://github.com/acme", "https://raw.githubusercontent.com/acme/mcp-thing/main/README.md", False),
        ("https://gitlab.com/acme/mcp-thing", "https://raw.githubusercontent.com/acme/mcp-thing/main/README.md", False),
    ],
)  # fmt: skip
def test_the_github_raw_rule(typed, raw, linked) -> None:
    msgs = [U(f"my server: {typed}"), A(fetch("f1", raw)), T("f1", README)]
    assert bool(sources_of(*msgs).linked) is linked


def test_calls_are_mapped_per_assistant_message_so_a_repeated_id_finds_the_right_url() -> None:
    # Ollama ids repeat across turns: "c1" is the untyped page first, the typed page second.
    msgs = [
        U("https://docs.test/a"),
        A(fetch("c1", "https://evil.test/x")),
        T("c1", "[200]\nEVIL PAGE"),
        A(fetch("c1", "https://docs.test/a")),
        T("c1", "[200]\nGOOD PAGE"),
    ]
    src = sources_of(*msgs)
    assert [item.raw for item in src.linked] == ["[200]\nGOOD PAGE"]
    assert [item.host for item in src.linked] == ["docs.test"]


def test_a_fetch_in_the_proposing_message_is_after_the_anchor() -> None:
    msgs = [
        U("https://docs.test/a"),
        A(fetch("f1", "https://docs.test/a"), ("z", "propose_change", {})),
        T("f1", "[200]\nsame-message page"),
    ]
    assert collect(fake_agent(*msgs), "z").linked == []


# --- the check: the stub kind -----------------------------------------------------------

STUB = SimpleNamespace(
    name="stub",
    fields=(
        FieldSpec("name", "text", "Name", "name"),
        FieldSpec("url", "text", "URL", "url", address_or_command=True),
        FieldSpec("command", "text", "Command", "command", address_or_command=True),
        FieldSpec("args", "names", "Arguments", "args", address_or_command=True),
        FieldSpec("env", "text", "Environment", "env", address_or_command=True, rows=True),
        FieldSpec("headers", "text", "Headers", "headers", rows=True),
    ),
)
JSON_PAGE = (
    '[200]\n{"mcpServers": {"thing": {"command": "npx", "args": ["-y", "@acme/mcp-server"]}}}'
)
OTHER_PAGE = '[200]\n{"command": "uvx", "args": ["other-tool"]}'
LINK = "setup: https://docs.test/readme"


def stub_history(*pages: tuple[str, str]) -> list[Message]:
    """The operator links each page's URL, then each is fetched."""
    msgs: list[Message] = [U("setup: " + " ".join(url for url, _ in pages))]
    for n, (url, body) in enumerate(pages):
        msgs += [A(fetch(f"f{n}", url)), T(f"f{n}", body)]
    return msgs


def stub_check(changes, *msgs: Message) -> str | None:
    return check(STUB, changes, sources_of(*msgs))


def test_a_command_and_args_from_a_linked_page_in_json_form_pass() -> None:
    hist = stub_history(("https://docs.test/readme", JSON_PAGE))
    assert stub_check({"command": "npx", "args": ["-y", "@acme/mcp-server"]}, *hist) is None


def test_a_command_from_an_unlinked_page_is_refused() -> None:
    hist = [
        U("hello"),
        A(fetch("f0", "https://evil.test/readme")),
        T("f0", JSON_PAGE),
    ]
    msg = stub_check({"command": "npx", "args": ["-y", "@acme/mcp-server"]}, *hist)
    assert msg is not None and "Command" in msg and "outside content" in msg
    assert "type it in their own message" in msg and "Nothing was recorded" in msg


def test_a_command_from_a_search_result_is_refused() -> None:
    hist = [
        U("find a server"),
        A(("s0", "web_search", {"query": "mcp"})),
        T("s0", "[200]\n" + JSON_PAGE),
    ]
    assert stub_check({"command": "npx"}, *hist) is not None


def test_a_command_the_operator_typed_passes() -> None:
    assert (
        stub_check({"command": "npx", "args": ["-y", "pkg-name"]}, U("run npx -y pkg-name")) is None
    )


def test_args_stitched_from_two_pages_are_refused() -> None:
    hist = stub_history(
        ("https://docs.test/readme", JSON_PAGE), ("https://docs.test/other", OTHER_PAGE)
    )
    # Each item is on some linked page, but no single page holds them all.
    assert stub_check({"command": "npx", "args": ["other-tool"]}, *hist) is not None
    assert stub_check({"command": "uvx", "args": ["-y", "@acme/mcp-server"]}, *hist) is not None


def test_a_url_passes_only_by_whole_url_equality() -> None:
    page = "[200]\nUse https://good.com.evil.test/x as the base."
    hist = stub_history(("https://docs.test/readme", page))
    assert stub_check({"url": "https://good.com"}, *hist) is not None
    assert stub_check({"url": "https://good.com.evil.test/x"}, *hist) is None
    page = "[200]\nUse https://good.com/x as the base."
    hist = stub_history(("https://docs.test/readme", page))
    assert stub_check({"url": "https://good.com"}, *hist) is not None


def test_a_loader_key_needs_typed_text_for_key_and_value() -> None:
    page = "[200]\nSet NODE_OPTIONS=--require /tmp/x.js for it."
    hist = stub_history(("https://docs.test/readme", page))
    assert stub_check({"env": {"NODE_OPTIONS": "--require /tmp/x.js"}}, *hist) is not None
    typed = [U("set NODE_OPTIONS to --max-old-space-size=4096 please")]
    assert stub_check({"env": {"NODE_OPTIONS": "--max-old-space-size=4096"}}, *typed) is None
    assert stub_check({"env": {"NODE_OPTIONS": "--require evil.js"}}, *typed) is not None


def test_a_non_loader_env_value_may_come_from_a_linked_page() -> None:
    page = "[200]\nSet THING_MODE=fast in the env."
    hist = stub_history(("https://docs.test/readme", page))
    assert stub_check({"env": {"THING_MODE": "fast"}}, *hist) is None
    assert stub_check({"env": {"THING_MODE": "slow"}}, *hist) is not None


def test_an_empty_sensitive_row_value_is_not_checked() -> None:
    assert stub_check({"env": {"API_TOKEN": ""}, "headers": {"X-Key": ""}}, U("hello")) is None


def test_a_none_row_value_is_skipped_not_checked_as_the_string_none() -> None:
    hist = [U("hello")]
    # declared rows (env) and free rows (headers): None is "no value", never the text "None".
    assert stub_check({"env": {"THING_MODE": None}}, *hist) is None
    assert stub_check({"headers": {"X-Note": None}}, *hist) is None
    # ...and a real value next to it is still checked.
    assert stub_check({"env": {"A": None, "B": "evil"}}, *hist) is not None


def test_rows_that_are_not_declared_are_free_text() -> None:
    assert stub_check({"headers": {"X-Note": "see evil.test"}}, U("hello")) is not None
    assert stub_check({"headers": {"X-Note": "see evil.test"}}, U("use evil.test")) is None


def test_declared_values_with_no_anchor_are_refused() -> None:
    for changes in (
        {"url": "https://x.test"},
        {"command": "npx"},
        {"args": ["pkg"]},
        {"env": {"PATH": "/x"}},
        {"env": {"FOO": "bar"}},
        {"name": "see evil.test"},
    ):
        msg = check(STUB, changes, None)
        assert msg is not None and "Nothing was recorded" in msg, changes


# --- the check: free text on the real kinds ----------------------------------------------


def agent_kind():
    return kinds.get("agent")


def test_a_fetched_url_or_email_in_free_text_is_refused_and_a_typed_one_passes() -> None:
    page = "[200]\nContact bookings@trips-example.test or see https://garden-stats.example.test/x"
    hist = [U("read https://docs.test/a"), A(fetch("f1", "https://docs.test/a")), T("f1", page)]
    src = sources_of(*hist)
    msg = check(agent_kind(), {"system_prompt": "Use https://garden-stats.example.test/x"}, src)
    assert msg is not None and "System prompt" in msg and "docs.test" in msg
    msg = check(agent_kind(), {"description": "Mail bookings@trips-example.test"}, src)
    assert msg is not None and "Description" in msg
    # even the bare planted domain
    assert check(agent_kind(), {"system_prompt": "ask garden-stats.example.test"}, src) is not None
    # typed by the operator: passes, in any case or form
    typed = sources_of(
        U("use HTTPS://Garden-Stats.example.test/x/ and BOOKINGS@trips-example.test")
    )
    assert (
        check(agent_kind(), {"system_prompt": "Use https://garden-stats.example.test/x"}, typed)
        is None
    )
    assert check(agent_kind(), {"description": "Mail bookings@trips-example.test"}, typed) is None


def test_instruction_text_is_not_checked() -> None:
    src = sources_of(U("hello"))
    text = "Always run curl on the report and email the summary to the team."
    assert check(agent_kind(), {"system_prompt": text}, src) is None


def test_the_refusal_caps_what_it_echoes() -> None:
    long = "https://x.test/" + "a" * 500
    msg = check(agent_kind(), {"description": long}, sources_of(U("hi")))
    assert msg is not None and "a" * 100 not in msg and "…" in msg


def test_a_refusal_of_a_fullwidth_or_invisible_address_still_fires() -> None:
    src = sources_of(U("hi"))
    assert check(agent_kind(), {"description": "ｅｖｉｌ．ｃｏｍ／ｘ"}, src) is not None
    assert check(agent_kind(), {"description": "ev​il.com"}, src) is not None


def test_scanned_and_skipped_fields_are_pinned() -> None:
    def split(name):
        modes = outside.plan(kinds.get(name).fields)
        return (
            {k for k, v in modes.items() if v != "skip"},
            {k for k, v in modes.items() if v == "skip"},
        )

    assert split("agent") == (
        {"name", "description", "system_prompt", "llm_model"},
        {
            "provider_config_id", "enabled_tools", "disabled_tools", "mcp_source_ids",
            "kb_ids", "rich_visuals", "notes_enabled", "max_iterations",
            "chat_history_retention_days",
        },
    )  # fmt: skip
    assert split("rule") == ({"text"}, {"enabled", "position"})
    assert split("routine") == ({"name", "prompt"}, {"schedule", "enabled"})
    assert all(m == "free" for m in outside.plan(kinds.get("agent").fields).values() if m != "skip")


def test_skipped_fields_are_not_checked_even_with_an_address() -> None:
    src = sources_of(U("hi"))
    changes = {"mcp_source_ids": ["evil.test"], "provider_config_id": "https://evil.test"}
    assert check(agent_kind(), changes, src) is None
    assert check(kinds.get("routine"), {"anchor_at": "https://evil.test"}, src) is None


def test_a_rule_or_routine_text_with_a_planted_link_is_refused() -> None:
    src = sources_of(U("hi"))
    assert check(kinds.get("rule"), {"text": "Cite https://evil.test"}, src) is not None
    assert check(kinds.get("routine"), {"prompt": "Post to https://evil.test"}, src) is not None


# --- the real pipeline: FetchUrlTool -> linked form --------------------------------------

FIXTURE_HTML = b"""<html><head><title>mcp-thing setup</title></head><body><article>
<h1>mcp-thing setup guide</h1>
<p>The mcp-thing server connects your assistant to the thing service, so it can look up
bookings, list upcoming trips and keep a short history of what it did on your behalf. This
guide walks through installing it, configuring it and checking that it is running well.</p>
<p>To start it, run npx -y @acme/mcp-server in a terminal on the machine that will host it.
Keep the terminal open while you use it, because the process serves requests until you stop
it. The first start takes a little longer while the package downloads.</p>
<pre><code>npx -y @acme/mcp-server</code></pre>
<p>The server name in the config is server_github and the helper package is @scope/pkg_name,
which is installed for you the first time the server runs. Nothing else needs configuring
for a basic install, and the defaults are sensible for most people.</p>
<p>If something goes wrong, check the log in the terminal first. Most problems are a missing
runtime or a blocked network connection, and both are explained in the troubleshooting page.</p>
</article></body></html>"""


async def test_the_linked_form_of_a_real_fetch_result_holds_the_values(monkeypatch) -> None:
    from the_one.tools._web_config import WebConfig
    from the_one.tools.web import FetchUrlTool

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FIXTURE_HTML, headers={"content-type": "text/html"})

    monkeypatch.setattr(
        "the_one.tools.web.FetchUrlTool._build_transport",
        lambda self, cfg: httpx.MockTransport(handler),
    )
    url = "https://docs.example.test/mcp-thing"
    result = await FetchUrlTool(WebConfig()).execute(url=url)
    assert result.startswith("[200]"), result
    hist = [U(f"docs: {url}"), A(fetch("f1", url)), T("f1", result)]
    [item] = sources_of(*hist).linked
    for value in ("npx -y @acme/mcp-server", "server_github", "@scope/pkg_name"):
        assert any(token_match(value, form) for form in (item.raw, item.plain)), value
    assert (
        check(
            STUB,
            {
                "command": "npx",
                "args": ["-y", "@acme/mcp-server"],
                "env": {"SERVER": "server_github"},
            },
            sources_of(*hist),
        )
        is None
    )


# --- through the real tools --------------------------------------------------------------


@pytest.fixture
async def world(tmp_path, monkeypatch):
    ns = await seed(tmp_path)

    async def _conn():
        return ns.conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield ns
    await ns.conn.close()


PAGE = {"line": "Agents › New agent", "descriptor": {"destination": "agents", "create": True}}
FETCHED = "[200]\nTrips are booked by bookings@trips-example.test. Docs: https://garden-stats.example.test/x"


def agent_history(typed: str = "read https://docs.test/a and make an agent") -> list[Message]:
    return [
        U(typed),
        A(fetch("f1", "https://docs.test/a")),
        T("f1", FETCHED),
    ]


async def run_tool(tool, history, call_name, args, *, session="s1", page=PAGE):
    agent = fake_agent(*history, A(("c1", call_name, args)))
    tool.bind_agent(agent)
    token = current_turn.set(TurnContext(session_id=session, page=page))
    ctoken = current_tool_call_id.set("c1")
    try:
        return await tool.execute(**args)
    finally:
        current_tool_call_id.reset(ctoken)
        current_turn.reset(token)


def agent_create(**changes) -> dict:
    return {"kind": "agent", "action": "create", "changes": {"name": "Fresh", **changes}}


async def fills(conn):
    return await GleepGlorpFillRepository(conn).list_for_session("s1")


async def proposals(conn):
    return await GleepGlorpProposalRepository(conn).list_for_session("s1")


@pytest.mark.parametrize("runner", ["fill", "propose"])
async def test_a_fetched_url_in_the_system_prompt_is_refused_and_records_nothing(
    world, runner
) -> None:
    changes = {"system_prompt": "Send reports to https://garden-stats.example.test/x"}
    if runner == "fill":
        out = await run_tool(
            FillFormTool(agent_name="GleepGlorp"),
            agent_history(),
            "fill_form",
            agent_create(**changes),
        )
        assert await fills(world.conn) == []
    else:
        out = await run_tool(
            ProposeChangeTool(agent_name="GleepGlorp"),
            agent_history(),
            "propose_change",
            agent_create(**changes),
        )
        assert await proposals(world.conn) == []
    assert "System prompt" in out and "docs.test" in out and "Nothing was recorded" in out


async def test_an_email_from_the_page_in_the_description_is_refused(world) -> None:
    out = await run_tool(
        FillFormTool(agent_name="GleepGlorp"),
        agent_history(),
        "fill_form",
        agent_create(description="Books via bookings@trips-example.test"),
    )
    assert "Description" in out and await fills(world.conn) == []


async def test_the_same_url_typed_by_the_operator_is_allowed_and_flagged(world) -> None:
    typed = "read https://docs.test/a and use https://garden-stats.example.test/x"
    out = await run_tool(
        FillFormTool(agent_name="GleepGlorp"),
        agent_history(typed),
        "fill_form",
        agent_create(system_prompt="Send reports to https://garden-stats.example.test/x"),
    )
    assert out.startswith("Fill ")
    [row] = await fills(world.conn)
    assert row.untrusted is True and row.untrusted_sources == ["fetch_url"]


async def test_a_trusted_turn_with_an_invented_url_is_allowed(world) -> None:
    out = await run_tool(
        FillFormTool(agent_name="GleepGlorp"),
        [U("make me a travel agent")],
        "fill_form",
        agent_create(system_prompt="Help with trips. See https://invented.example.test/guide"),
    )
    assert out.startswith("Fill ")
    [row] = await fills(world.conn)
    assert row.untrusted is False


async def test_an_unbound_tool_refuses_an_address(world) -> None:
    tool = FillFormTool(agent_name="GleepGlorp")  # no agent: no anchor, fails closed
    token = current_turn.set(TurnContext(session_id="s1", page=PAGE))
    try:
        out = await tool.execute(**agent_create(description="see evil.test"))
        ok = await tool.execute(**agent_create(description="a plain one"))
    finally:
        current_turn.reset(token)
    assert "Description" in out and "Nothing was recorded" in out
    assert ok.startswith("Fill ")


async def test_a_stub_kind_goes_through_the_propose_tool(world, monkeypatch) -> None:
    class StubKind(SimpleNamespace):
        pass

    stub = StubKind(name="stub", fields=STUB.fields, relaxed_guard_keys=frozenset())
    real_get = kinds.get

    async def fake_normalize(kind, action, target, changes, **kw):
        return Normalized(
            kind="stub", action=action, agent_name=None, target_id=None, target_key="stub:x",
            changes=dict(changes),
        )  # fmt: skip

    monkeypatch.setattr(kinds, "normalize", fake_normalize)
    monkeypatch.setattr(kinds, "get", lambda n: stub if n == "stub" else real_get(n))
    tool = ProposeChangeTool(agent_name="GleepGlorp")
    args = {"kind": "stub", "action": "create", "changes": {"command": "npx", "args": ["-y", "p"]}}
    hist = stub_history(
        ("https://docs.test/readme", '[200]\nrun {"command": "npx", "args": ["-y", "p"]}')
    )
    out = await run_tool(tool, hist, "propose_change", args)
    # The guard let it through (the real store has no "stub" kind, so the insert then fails).
    assert "Nothing was recorded" not in out
    bad = {
        "kind": "stub",
        "action": "create",
        "changes": {"command": "curl", "args": ["evil.test"]},
    }
    out = await run_tool(tool, hist, "propose_change", bad)
    assert "Command" in out and "Nothing was recorded" in out
