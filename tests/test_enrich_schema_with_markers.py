"""Tests for `_enrich_schema_with_markers` (F6 L1).

The helper walks `config_class.model_fields[name].metadata` and injects
`x_marker: str` per top-level property in the JSON schema. Pydantic v2
strips the marker classes from `model_json_schema()` output, so this
helper is the only way the L3 form renderer learns which fields carry
narrowing semantics vs substitute semantics.
"""

from __future__ import annotations

import copy

from the_one.interfaces.web.api import _enrich_schema_with_markers
from the_one.tools._web_config import WebConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.resolver import _EmptyConfig


def test_enriches_narrow() -> None:
    """`WebConfig.host_allowlist` carries the `Narrow` marker."""
    schema = WebConfig.model_json_schema()
    out = _enrich_schema_with_markers(schema, WebConfig)
    assert out["properties"]["host_allowlist"].get("x_marker") == "NarrowAnyWhenEmpty"


def test_enriches_narrow_prefix() -> None:
    """`FilesystemConfig.path_allowlist` carries the `NarrowPrefix` marker."""
    schema = FilesystemConfig.model_json_schema()
    out = _enrich_schema_with_markers(schema, FilesystemConfig)
    assert out["properties"]["path_allowlist"].get("x_marker") == "NarrowPrefix"


def test_enriches_narrow_superset() -> None:
    """`WebConfig.host_denylist` carries the `NarrowSuperset` marker."""
    schema = WebConfig.model_json_schema()
    out = _enrich_schema_with_markers(schema, WebConfig)
    assert out["properties"]["host_denylist"].get("x_marker") == "NarrowSuperset"


def test_enriches_substitute() -> None:
    """`WebConfig.default_user_agent` carries the `Substitute` marker."""
    schema = WebConfig.model_json_schema()
    out = _enrich_schema_with_markers(schema, WebConfig)
    assert out["properties"]["default_user_agent"].get("x_marker") == "Substitute"


def test_omits_x_marker_for_unmarked_field() -> None:
    """`WebConfig.redirect_cap` is Field-only (no marker per F5 D9)."""
    schema = WebConfig.model_json_schema()
    out = _enrich_schema_with_markers(schema, WebConfig)
    # Contract: helper does not inject `x_marker` for unmarked fields.
    assert "x_marker" not in out["properties"]["redirect_cap"]


def test_empty_config_helper_no_op() -> None:
    """`_EmptyConfig` has empty `model_fields`; helper is a no-op."""
    schema = _EmptyConfig.model_json_schema()
    before = copy.deepcopy(schema)
    out = _enrich_schema_with_markers(schema, _EmptyConfig)
    # Returned schema equals input — no properties were added or modified.
    assert out == before
    # And `properties` (if present) carries no x_marker entries.
    for prop in out.get("properties", {}).values():
        assert "x_marker" not in prop


def test_helper_does_not_mutate_unrelated_keys() -> None:
    """The helper mutates `properties[name]` in place (documented contract)
    but must NOT touch unrelated top-level schema keys (`title`, `type`,
    `required`, `$defs`, etc.)."""
    schema = WebConfig.model_json_schema()
    # Capture every top-level key except `properties` and assert untouched.
    untouched = {k: copy.deepcopy(v) for k, v in schema.items() if k != "properties"}
    _enrich_schema_with_markers(schema, WebConfig)
    for k, v in untouched.items():
        assert schema[k] == v, f"helper mutated unrelated key {k!r}"
