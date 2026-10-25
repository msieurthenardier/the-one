"""Tests for ExecutionConfig (F4 L2) — Pydantic shape, defaults, bounds,
freeze, cross-field invariant, resolver narrowing per field, and the
default-factory + resolver interaction limitation.

Sister suite to ``tests/test_filesystem_config.py`` (F3 L2a). Uses absolute
values to keep tests independent of runtime state.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_one.tools.execution import (
    DEFAULT_COMMAND_DENYLIST,
    ExecutionConfig,
    PythonExecConfig,
)
from the_one.tools.resolver import resolve

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaultConstruction:
    def test_zero_arg_construction_succeeds(self) -> None:
        cfg = ExecutionConfig()
        assert isinstance(cfg, ExecutionConfig)

    def test_default_timeout_default_30(self) -> None:
        assert ExecutionConfig().timeout_seconds_default == 30

    def test_default_timeout_max_120(self) -> None:
        assert ExecutionConfig().timeout_seconds_max == 120

    def test_default_output_cap_256kb(self) -> None:
        assert ExecutionConfig().output_cap_bytes == 262_144

    def test_default_pty_idle_ttl_300(self) -> None:
        assert ExecutionConfig().pty_session_idle_ttl_seconds == 300

    def test_default_max_concurrent_sessions_5(self) -> None:
        assert ExecutionConfig().max_concurrent_sessions == 5

    def test_default_denylist_matches_module_constant(self) -> None:
        cfg = ExecutionConfig()
        assert cfg.command_denylist == list(DEFAULT_COMMAND_DENYLIST)

    def test_default_denylist_does_not_share_module_tuple(self) -> None:
        # Mutating one Config's denylist must not poison the module baseline.
        cfg1 = ExecutionConfig()
        cfg1.command_denylist.append("not-real")
        cfg2 = ExecutionConfig()
        assert "not-real" not in cfg2.command_denylist

    def test_command_denylist_is_list_not_tuple(self) -> None:
        # The resolver's `_check_narrow_superset` requires
        # `isinstance(tool_val, list)`. Default-factory MUST return list.
        cfg = ExecutionConfig()
        assert isinstance(cfg.command_denylist, list)

    def test_command_denylist_tuple_input_coerced_to_list(self) -> None:
        cfg = ExecutionConfig(command_denylist=("a", "b"))
        assert cfg.command_denylist == ["a", "b"]
        assert isinstance(cfg.command_denylist, list)


# ---------------------------------------------------------------------------
# Bounds — Pydantic ge/le validation
# ---------------------------------------------------------------------------


class TestBounds:
    def test_timeout_default_below_floor_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(timeout_seconds_default=0)

    def test_timeout_default_above_ceiling_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(timeout_seconds_default=3601, timeout_seconds_max=3601)

    def test_timeout_max_below_floor_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(timeout_seconds_max=0)

    def test_timeout_max_above_ceiling_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(timeout_seconds_max=3601)

    def test_output_cap_below_floor_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(output_cap_bytes=512)  # under 1024 floor

    def test_output_cap_above_ceiling_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(output_cap_bytes=200_000_000)  # over 100 MB

    def test_pty_ttl_below_floor_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(pty_session_idle_ttl_seconds=5)

    def test_pty_ttl_above_ceiling_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(pty_session_idle_ttl_seconds=3601)

    def test_max_concurrent_sessions_below_floor_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(max_concurrent_sessions=0)

    def test_max_concurrent_sessions_above_ceiling_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionConfig(max_concurrent_sessions=51)


# ---------------------------------------------------------------------------
# Cross-field invariant — _default_le_max
# ---------------------------------------------------------------------------


class TestDefaultLeMax:
    def test_default_greater_than_max_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ExecutionConfig(timeout_seconds_default=200, timeout_seconds_max=120)
        assert "must be <=" in str(exc.value)

    def test_default_equal_max_succeeds(self) -> None:
        cfg = ExecutionConfig(timeout_seconds_default=120, timeout_seconds_max=120)
        assert cfg.timeout_seconds_default == cfg.timeout_seconds_max == 120

    def test_default_less_than_max_succeeds(self) -> None:
        cfg = ExecutionConfig(timeout_seconds_default=10, timeout_seconds_max=60)
        assert cfg.timeout_seconds_default == 10
        assert cfg.timeout_seconds_max == 60


# ---------------------------------------------------------------------------
# Frozen behavior
# ---------------------------------------------------------------------------


class TestFrozen:
    """ExecutionConfig is frozen so the per-call cross_configs view shared
    across tool instances cannot be mutated by one tool to corrupt another's
    view (F4 Decision 7)."""

    def test_attribute_assignment_to_int_field_raises(self) -> None:
        cfg = ExecutionConfig()
        with pytest.raises(ValidationError):
            cfg.timeout_seconds_default = 1  # type: ignore[misc]

    def test_attribute_assignment_to_list_field_raises(self) -> None:
        cfg = ExecutionConfig()
        with pytest.raises(ValidationError):
            cfg.command_denylist = ["only"]  # type: ignore[misc]

    def test_attribute_assignment_to_other_int_field_raises(self) -> None:
        cfg = ExecutionConfig()
        with pytest.raises(ValidationError):
            cfg.output_cap_bytes = 1024  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UI hint round-trip via model_json_schema
# ---------------------------------------------------------------------------


class TestUiHint:
    """All Narrow/NarrowSuperset fields carry a dropdown ui_hint so F6's
    admin UI can render type-correct choosers (F4 Decisions 1, 2, 3, 5)."""

    @pytest.mark.parametrize(
        "field",
        [
            "timeout_seconds_default",
            "timeout_seconds_max",
            "output_cap_bytes",
            "command_denylist",
            "pty_session_idle_ttl_seconds",
            "max_concurrent_sessions",
        ],
    )
    def test_field_carries_dropdown_hint(self, field: str) -> None:
        schema = ExecutionConfig.model_json_schema()
        prop = schema["properties"][field]
        assert prop.get("ui_hint") == "dropdown", f"{field} missing ui_hint"
        assert "ui_choices" in prop, f"{field} missing ui_choices"
        assert isinstance(prop["ui_choices"], list)
        assert len(prop["ui_choices"]) >= 1


# ---------------------------------------------------------------------------
# Resolver integration — per-field narrowing semantics
# ---------------------------------------------------------------------------


class TestResolverNarrowing:
    """Per-field narrowing wiring on the concrete schema. Marker mechanics
    themselves are covered generically by ``tests/test_resolver.py``; this
    suite pins each field's marker selection end-to-end."""

    def test_timeout_default_narrow(self) -> None:
        r = resolve(
            ExecutionConfig,
            {"timeout_seconds_default": 30},
            {"timeout_seconds_default": 10},
        )
        assert r.timeout_seconds_default == 10

    def test_timeout_default_widen_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {"timeout_seconds_default": 30},
                {"timeout_seconds_default": 60},
            )
        assert "widens" in str(exc.value)

    def test_timeout_max_narrow(self) -> None:
        r = resolve(
            ExecutionConfig,
            {"timeout_seconds_max": 120},
            {"timeout_seconds_max": 60},
        )
        assert r.timeout_seconds_max == 60

    def test_timeout_max_widen_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {"timeout_seconds_max": 120},
                {"timeout_seconds_max": 180},
            )
        assert "widens" in str(exc.value)

    def test_output_cap_narrow(self) -> None:
        r = resolve(
            ExecutionConfig,
            {"output_cap_bytes": 262_144},
            {"output_cap_bytes": 65_536},
        )
        assert r.output_cap_bytes == 65_536

    def test_output_cap_widen_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {"output_cap_bytes": 262_144},
                {"output_cap_bytes": 524_288},
            )
        assert "widens" in str(exc.value)

    def test_command_denylist_agent_superset(self) -> None:
        r = resolve(
            ExecutionConfig,
            {"command_denylist": ["sudo "]},
            {"command_denylist": ["sudo ", "rm -rf"]},
        )
        assert r.command_denylist == ["sudo ", "rm -rf"]

    def test_command_denylist_drops_tool_entry_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {"command_denylist": ["sudo "]},
                {"command_denylist": ["rm -rf"]},
            )
        assert "widens" in str(exc.value)

    def test_pty_ttl_narrow(self) -> None:
        r = resolve(
            ExecutionConfig,
            {"pty_session_idle_ttl_seconds": 300},
            {"pty_session_idle_ttl_seconds": 60},
        )
        assert r.pty_session_idle_ttl_seconds == 60

    def test_pty_ttl_widen_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {"pty_session_idle_ttl_seconds": 300},
                {"pty_session_idle_ttl_seconds": 600},
            )
        assert "widens" in str(exc.value)

    def test_max_concurrent_narrow(self) -> None:
        r = resolve(
            ExecutionConfig,
            {"max_concurrent_sessions": 5},
            {"max_concurrent_sessions": 3},
        )
        assert r.max_concurrent_sessions == 3

    def test_max_concurrent_widen_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {"max_concurrent_sessions": 5},
                {"max_concurrent_sessions": 10},
            )
        assert "widens" in str(exc.value)


# ---------------------------------------------------------------------------
# Cross-field invariant interacting with narrowing
# ---------------------------------------------------------------------------


class TestCrossFieldInteractsWithNarrowing:
    def test_agent_narrowing_max_below_default_raises(self) -> None:
        """Documented guarantee from Decision 1: agent can't widen `default`
        past a narrowed `max`. Tool sets default=30, max=120; agent narrows
        max=20. The resolver applies per-key narrowing first (max=20 is OK
        — narrows 120 → 20), then `model_validate(merged)` triggers
        `_default_le_max` since 30 > 20."""
        with pytest.raises(ValidationError) as exc:
            resolve(
                ExecutionConfig,
                {"timeout_seconds_default": 30, "timeout_seconds_max": 120},
                {"timeout_seconds_max": 20},
            )
        assert "must be <=" in str(exc.value)


# ---------------------------------------------------------------------------
# Resolver default-factory fallback — documented limitation
# ---------------------------------------------------------------------------


class TestResolverDefaultFactoryFallback:
    """When `tool_config` omits `command_denylist` and the agent provides an
    override, the resolver's baseline is the field's default factory
    (`DEFAULT_COMMAND_DENYLIST`).

    Squawk 0248 replaced the earlier documented limitation: the resolver read
    ``field_info.default``, which is ``PydanticUndefined`` for a
    default-factory field, so ``_check_narrow_superset`` raised
    ``NotImplementedError`` and the agent could not be built. The baseline is
    now materialised, so an override must still contain every default entry.
    """

    def test_omitted_tool_config_override_dropping_defaults_is_refused(
        self,
    ) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                ExecutionConfig,
                {},
                {"command_denylist": ["sudo "]},
            )
        assert "widens ExecutionConfig.command_denylist" in str(exc.value)

    def test_omitted_tool_config_override_extending_defaults_resolves(self) -> None:
        r = resolve(
            ExecutionConfig,
            {},
            {"command_denylist": list(DEFAULT_COMMAND_DENYLIST) + ["company-secret"]},
        )
        assert r.command_denylist == list(DEFAULT_COMMAND_DENYLIST) + ["company-secret"]

    def test_locked_down_null_path_uses_default_factory(self) -> None:
        # Locked-down NULL path (agent_override is None) bypasses per-key
        # dispatch entirely, so the default-factory fires via Pydantic
        # construction normally. The denylist baseline is intact.
        r = resolve(ExecutionConfig, {}, None)
        assert r.command_denylist == list(DEFAULT_COMMAND_DENYLIST)
        assert isinstance(r.command_denylist, list)

    def test_explicit_tool_baseline_avoids_limitation(self) -> None:
        # Explicit tool-level baseline → resolver narrows correctly.
        r = resolve(
            ExecutionConfig,
            {"command_denylist": list(DEFAULT_COMMAND_DENYLIST)},
            {"command_denylist": list(DEFAULT_COMMAND_DENYLIST) + ["company-secret"]},
        )
        assert "company-secret" in r.command_denylist


# ---------------------------------------------------------------------------
# PythonExecConfig — F4 L4 subclass with 90s default timeout
# ---------------------------------------------------------------------------


class TestPythonExecConfig:
    """``PythonExecConfig`` overrides only ``timeout_seconds_default`` (30s →
    90s) per F4 Decision 9 — Python is more often used for compute than
    shell, so a higher default reduces friction. Everything else is
    inherited verbatim from ``ExecutionConfig``: cap, denylist, frozen
    posture, ``_default_le_max`` cross-field validator. These tests pin the
    inheritance shape and the override site.
    """

    def test_default_timeout_is_90(self) -> None:
        assert PythonExecConfig().timeout_seconds_default == 90

    def test_default_timeout_max_inherited_120(self) -> None:
        assert PythonExecConfig().timeout_seconds_max == 120

    def test_is_subclass_of_execution_config(self) -> None:
        # Subclass relation is what makes the inherited validator and
        # `command_denylist` default-factory work without re-declaration.
        assert issubclass(PythonExecConfig, ExecutionConfig)
        assert isinstance(PythonExecConfig(), ExecutionConfig)

    def test_denylist_inherited(self) -> None:
        # Denylist default-factory is inherited unchanged.
        assert PythonExecConfig().command_denylist == list(DEFAULT_COMMAND_DENYLIST)
        assert PythonExecConfig().command_denylist == ExecutionConfig().command_denylist

    def test_default_greater_than_max_raises(self) -> None:
        # Inherited cross-field invariant — `_default_le_max` runs on the
        # subclass too. Pin it to guard against a future override that
        # accidentally drops the validator.
        with pytest.raises(ValidationError) as exc:
            PythonExecConfig(timeout_seconds_default=200, timeout_seconds_max=120)
        assert "must be <=" in str(exc.value)

    def test_frozen_inherited(self) -> None:
        cfg = PythonExecConfig()
        with pytest.raises(ValidationError):
            cfg.timeout_seconds_default = 60  # type: ignore[misc]

    def test_timeout_default_carries_dropdown_hint(self) -> None:
        """Drift guard: re-declaring ``timeout_seconds_default`` in the
        subclass must re-state ``json_schema_extra`` (Pydantic v2 does
        NOT inherit it). Without this, F6's admin UI would lose the
        dropdown for the Python config."""
        schema = PythonExecConfig.model_json_schema()
        prop = schema["properties"]["timeout_seconds_default"]
        assert prop.get("ui_hint") == "dropdown"
        assert "ui_choices" in prop
        assert isinstance(prop["ui_choices"], list)
        assert len(prop["ui_choices"]) >= 1

    def test_timeout_default_choices_match_execution_config(self) -> None:
        """Both Configs' ``timeout_seconds_default`` dropdowns are built by the
        same helper; admin UI renders the same values for either tool (the
        only legitimate difference is which value is labelled the default)."""
        exec_choices = ExecutionConfig.model_json_schema()["properties"]["timeout_seconds_default"][
            "ui_choices"
        ]
        py_choices = PythonExecConfig.model_json_schema()["properties"]["timeout_seconds_default"][
            "ui_choices"
        ]
        assert [c["value"] for c in exec_choices] == [c["value"] for c in py_choices]
        # Each list marks "(default)" on its own Config's default, and only there.
        assert [c["value"] for c in exec_choices if "(default)" in c["label"]] == [30]
        assert [c["value"] for c in py_choices if "(default)" in c["label"]] == [90]
