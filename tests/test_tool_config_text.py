"""Operator-facing tool-config text (Mission 31 Flight 4, leg 05a).

Titles, descriptions, plain preset labels, per-tool summaries and per-tool
field lists are read only by the tools-config routes. None of it may reach the
model: a tool's model-facing schema is exactly ``{name, description,
parameters}``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from the_one.tools.builtins import _TOOL_CLASSES

WEB_SEARCH_DESCRIPTION = (
    "Search the web and return results (title, URL, snippet). The backend is "
    "operator-configurable (default DuckDuckGo). Useful for finding URLs to "
    "feed into fetch_url or read."
)


def _string_values(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            out.extend(_string_values(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_string_values(v))
    return out


def _config_text(cls: type) -> list[str]:
    schema = cls.Config.model_json_schema()
    texts: list[str] = []
    for prop in (schema.get("properties") or {}).values():
        for key in ("title", "description"):
            if prop.get(key):
                texts.append(prop[key])
        for choice in prop.get("ui_choices") or []:
            texts.append(str(choice.get("label", "")))
    return texts


@pytest.mark.parametrize("name", sorted(_TOOL_CLASSES))
def test_model_facing_schema_is_exactly_three_keys(name: str) -> None:
    tool = _TOOL_CLASSES[name]()
    assert set(tool.to_schema()) == {"name", "description", "parameters"}


@pytest.mark.parametrize("name", sorted(_TOOL_CLASSES))
def test_no_operator_text_reaches_the_model(name: str) -> None:
    cls = _TOOL_CLASSES[name]
    tool = cls()
    schema = tool.to_schema()
    values = set(_string_values(schema))
    blob = json.dumps(schema)
    summary = getattr(cls, "summary", "")
    if summary:
        assert summary not in blob
    for text in _config_text(cls):
        if len(text) >= 20:
            assert text not in blob, text
        assert text not in values, text


def test_web_search_description_is_the_new_literal() -> None:
    assert _TOOL_CLASSES["web_search"].description == WEB_SEARCH_DESCRIPTION


# ── Served text: titles, descriptions, summaries (A7, B1, B7) ─────────────

from unittest.mock import patch  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from tests._credential_helpers import auth_headers  # noqa: E402
from tests._schema_template import connect_template_db  # noqa: E402
from the_one.interfaces.web import api as api_mod  # noqa: E402
from the_one.interfaces.web.api import router  # noqa: E402


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


async def test_every_served_property_has_a_written_title_and_description(client) -> None:
    for name in sorted(_TOOL_CLASSES):
        detail = (await client.get(f"/api/tools/configs/{name}")).json()
        for key, prop in detail["schema"].get("properties", {}).items():
            auto = key.replace("_", " ").title()
            assert prop.get("title"), f"{name}.{key} has no title"
            assert prop["title"] != auto, f"{name}.{key} still has the auto title {auto!r}"
            assert prop["title"][0].isupper() and prop["title"][1:] == prop["title"][1:].replace(
                "  ", " "
            )
            assert (prop.get("description") or "").strip(), f"{name}.{key} has no description"


async def test_every_tool_has_a_short_summary_on_both_routes(client) -> None:
    listed = {r["name"]: r for r in (await client.get("/api/tools/configs")).json()}
    assert set(listed) == set(_TOOL_CLASSES)
    for name, cls in _TOOL_CLASSES.items():
        assert cls.summary.strip(), name
        assert len(cls.summary) <= 80, name
        assert cls.summary.endswith("."), name
        assert listed[name]["summary"] == cls.summary
        detail = (await client.get(f"/api/tools/configs/{name}")).json()
        assert detail["summary"] == cls.summary


def test_preset_labels_are_plain() -> None:
    jargon = ("Opus", "7B", "very small models", "(shell)", "(python)", "keyless", "—")
    seen: set[type] = set()
    for cls in _TOOL_CLASSES.values():
        if cls.Config in seen:
            continue
        seen.add(cls.Config)
        for key, prop in cls.Config.model_json_schema().get("properties", {}).items():
            for choice in prop.get("ui_choices") or []:
                label = choice["label"]
                for word in jargon:
                    assert word not in label, f"{cls.Config.__name__}.{key}: {label!r}"


def test_timeout_default_marks_each_tools_own_default() -> None:
    def defaults(config_cls: type) -> list[int]:
        prop = config_cls.model_json_schema()["properties"]["timeout_seconds_default"]
        return [c["value"] for c in prop["ui_choices"] if "(default)" in c["label"]]

    assert defaults(_TOOL_CLASSES["shell"].Config) == [30]
    assert defaults(_TOOL_CLASSES["python_exec"].Config) == [90]
    assert defaults(_TOOL_CLASSES["fetch_url"].Config) == [30]


# ── config_fields: which settings each tool shows (B6) ────────────────────

FS_PATHS = ["path_allowlist", "path_denylist"]
SHELL_FIELDS = [
    "timeout_seconds_default",
    "timeout_seconds_max",
    "output_cap_bytes",
    "command_denylist",
    "sandbox_network_allowed",
]
EXPECTED_FIELDS: dict[str, list[str] | None] = {
    "read_file": None,
    "edit_file": None,
    "grep": None,
    "write_file": FS_PATHS,
    "list_dir": FS_PATHS,
    "glob": FS_PATHS,
    "delete_file": FS_PATHS,
    "move_file": FS_PATHS,
    "mkdir": FS_PATHS,
    "shell": SHELL_FIELDS,
    "python_exec": SHELL_FIELDS,
    "shell_session_start": [
        "pty_session_idle_ttl_seconds",
        "max_concurrent_sessions",
        "sandbox_network_allowed",
    ],
    "shell_session_send": [
        "timeout_seconds_default",
        "timeout_seconds_max",
        "output_cap_bytes",
        "command_denylist",
    ],
    "shell_session_close": [],
    "shell_session_list": [],
    "http_request": None,
    "fetch_url": None,
    "download_file": None,
    "web_search": None,
}


@pytest.mark.parametrize("name", sorted(EXPECTED_FIELDS))
async def test_detail_schema_is_filtered_to_config_fields(client, name: str) -> None:
    detail = (await client.get(f"/api/tools/configs/{name}")).json()
    served = list(detail["schema"].get("properties", {}))
    expected = EXPECTED_FIELDS[name]
    if expected is None:
        assert served == list(_TOOL_CLASSES[name].Config.model_fields)
    else:
        assert sorted(served) == sorted(expected)
        for req in detail["schema"].get("required", []):
            assert req in expected


def test_config_fields_name_real_config_fields() -> None:
    for name, cls in _TOOL_CLASSES.items():
        if cls.config_fields is None:
            continue
        assert set(cls.config_fields) <= set(cls.Config.model_fields), name


async def test_hidden_value_survives_a_put_that_omits_it(client) -> None:
    # Store a custom read size on delete_file while the field is still part of the
    # tool's editor (monkeypatched), then hide it and PUT the visible fields only.
    cls = _TOOL_CLASSES["delete_file"]
    with patch.object(cls, "config_fields", None):
        resp = await client.put(
            "/api/tools/configs/delete_file",
            json={"config": {"read_size_cap_bytes": 51_200, "allow_binary_files": True}},
        )
        assert resp.status_code == 200
    resp = await client.put(
        "/api/tools/configs/delete_file",
        json={"config": {"path_allowlist": ["~/work"]}},
    )
    assert resp.status_code == 200
    body = resp.json()["config"]
    assert body["read_size_cap_bytes"] == 51_200
    assert body["allow_binary_files"] is True
    assert body["path_allowlist"] == ["~/work"]
    # an incoming differing hidden value is ignored; the stored one wins
    resp = await client.put(
        "/api/tools/configs/delete_file",
        json={"config": {"path_allowlist": ["~"], "read_size_cap_bytes": 1_048_576}},
    )
    assert resp.json()["config"]["read_size_cap_bytes"] == 51_200
    # a reset to defaults leaves hidden fields as stored
    resp = await client.put("/api/tools/configs/delete_file", json={"config": {}})
    cfg = resp.json()["config"]
    assert cfg["read_size_cap_bytes"] == 51_200
    assert cfg["path_allowlist"] == ["~"]


async def test_never_saved_tool_copies_nothing_and_defaults_apply(client) -> None:
    resp = await client.put(
        "/api/tools/configs/mkdir", json={"config": {"path_allowlist": ["~/x"]}}
    )
    assert resp.status_code == 200
    cfg = resp.json()["config"]
    assert cfg["read_size_cap_bytes"] == 1_048_576
    assert cfg["allow_binary_files"] is False


async def test_stored_hidden_value_that_no_longer_validates_falls_back(client) -> None:
    from the_one.interfaces.web.api import _tool_config_repo

    repo = await _tool_config_repo()
    await repo.upsert(
        "list_dir",
        {"path_allowlist": ["~"], "read_size_cap_bytes": 5},  # below the ge=1024 floor
        secrets={},
        enabled=True,
    )
    resp = await client.put(
        "/api/tools/configs/list_dir", json={"config": {"path_allowlist": ["~/y"]}}
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["read_size_cap_bytes"] == 1_048_576
    # a bad VISIBLE edit is still a 422
    resp = await client.put(
        "/api/tools/configs/list_dir", json={"config": {"path_allowlist": "nope"}}
    )
    assert resp.status_code == 422


async def test_resolver_still_applies_a_stored_hidden_value(client) -> None:
    from the_one.tools.builtins import BuiltinToolProvider

    cls = _TOOL_CLASSES["delete_file"]
    with patch.object(cls, "config_fields", None):
        await client.put(
            "/api/tools/configs/delete_file",
            json={"config": {"read_size_cap_bytes": 51_200}},
        )
    await client.put("/api/tools/configs/delete_file", json={"config": {"path_allowlist": ["~/z"]}})
    stored = (await client.get("/api/tools/configs/delete_file")).json()["config"]
    tools = {
        t.name: t for t in BuiltinToolProvider().get_tools(tool_configs={"delete_file": stored})
    }
    assert tools["delete_file"]._config.read_size_cap_bytes == 51_200


def test_merge_helper_secret_hidden_field_comes_from_stored() -> None:
    from the_one.tools._web_search_config import WebSearchConfig

    class _Tool:
        config_fields = ("search_backend",)

    merged = api_mod._merge_hidden_fields(
        WebSearchConfig,
        _Tool,
        {"search_backend": "brave", "brave_api_key": "attacker"},
        {"brave_api_key": "stored-secret"},
    )
    assert merged == {"search_backend": "brave", "brave_api_key": "stored-secret"}


# ── A8: a custom preset value is humanised from the field name's unit token ──

# Integer dropdowns with no unit in their name (a count, not a size or a duration).
UNITLESS_PRESETS = {"max_concurrent_sessions"}


def test_every_integer_preset_field_has_a_unit_token_or_is_listed_unitless() -> None:
    import re

    seen: set[type] = set()
    for cls in _TOOL_CLASSES.values():
        if cls.Config in seen:
            continue
        seen.add(cls.Config)
        for key, prop in cls.Config.model_json_schema().get("properties", {}).items():
            if prop.get("type") != "integer" or not prop.get("ui_choices"):
                continue
            has_unit = re.search(r"_(bytes|seconds)(_|$)", key) is not None
            assert has_unit or key in UNITLESS_PRESETS, (
                f"{cls.Config.__name__}.{key} is an integer preset with no unit token in its "
                "name: App.toolConfigFields would show a custom value as a bare number. "
                "Rename it or add it to UNITLESS_PRESETS."
            )
