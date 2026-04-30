"""Tests for FilesystemConfig (F3 L2a) — Pydantic shape, defaults, resolver
integration, model_post_init caching invariant, and ui_hint metadata."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from the_one.tools.filesystem import (
    DEFAULT_PATH_DENYLIST,
    FilesystemConfig,
)
from the_one.tools.resolver import resolve

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaultConstruction:
    def test_zero_arg_construction_succeeds(self) -> None:
        cfg = FilesystemConfig()
        assert isinstance(cfg, FilesystemConfig)

    def test_default_path_allowlist_is_tilde(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.path_allowlist == ["~"]

    def test_default_denylist_matches_module_constant(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.path_denylist == list(DEFAULT_PATH_DENYLIST)

    def test_default_denylist_does_not_share_module_list(self) -> None:
        # Mutating one Config's denylist must not poison the module baseline.
        cfg1 = FilesystemConfig()
        cfg1.path_denylist.append("/should-not-leak")
        cfg2 = FilesystemConfig()
        assert "/should-not-leak" not in cfg2.path_denylist

    def test_default_read_size_cap_is_1mib(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.read_size_cap_bytes == 1_048_576

    def test_default_allow_binary_files_false(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.allow_binary_files is False


# ---------------------------------------------------------------------------
# Resolver integration — narrowing semantics on each marker
# ---------------------------------------------------------------------------


class TestResolverIntegration:
    """FilesystemConfig-specific shape: the four fields exist, are wired to
    the right markers, bounds fire, and the bool semantic is positively-named.

    NOTE: marker mechanics themselves (NarrowPrefix descendant rules,
    NarrowSuperset agent-⊇-tool rules, etc.) are covered generically by
    `tests/test_resolver.py` (L1). These FilesystemConfig tests duplicate
    a small slice of that coverage on purpose — to pin the per-field
    wiring (right marker on right field) end-to-end on this concrete
    schema. Tests use absolute paths instead of `~/projects` so they
    don't depend on the runtime HOME (matches L1's TestNarrowPrefix
    convention)."""

    def test_path_allowlist_narrow_descendant(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"path_allowlist": ["/home/u/projects"]},
            {"path_allowlist": ["/home/u/projects/foo"]},
        )
        assert r.path_allowlist == ["/home/u/projects/foo"]

    def test_path_allowlist_widen_outside_root_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                FilesystemConfig,
                {"path_allowlist": ["/home/u/projects"]},
                {"path_allowlist": ["/etc"]},
            )
        assert "widens" in str(exc.value).lower() or "not within" in str(exc.value).lower()

    def test_path_denylist_agent_superset(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"path_denylist": ["/etc"]},
            {"path_denylist": ["/etc", "/proc"]},
        )
        assert r.path_denylist == ["/etc", "/proc"]

    def test_path_denylist_drops_tool_entry_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                FilesystemConfig,
                {"path_denylist": ["/etc", "/proc"]},
                {"path_denylist": ["/etc"]},
            )
        assert "widens" in str(exc.value)

    def test_read_size_cap_narrow(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"read_size_cap_bytes": 1_048_576},
            {"read_size_cap_bytes": 102_400},
        )
        assert r.read_size_cap_bytes == 102_400

    def test_read_size_cap_widen_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve(
                FilesystemConfig,
                {"read_size_cap_bytes": 102_400},
                {"read_size_cap_bytes": 1_048_576},
            )

    # Bounds tests bypass `resolve()` and call FilesystemConfig() directly —
    # they verify Pydantic's `ge`/`le` schema validation independent of the
    # resolver path. (Through `resolve()`, the Narrow check passes first
    # because 512 <= tool_default; then `model_validate(merged)` raises
    # ValidationError. Both paths converge on rejection.)
    def test_read_size_cap_below_floor_raises_validation(self) -> None:
        with pytest.raises(ValidationError):
            FilesystemConfig(read_size_cap_bytes=512)  # under 1024 floor

    def test_read_size_cap_above_ceiling_raises_validation(self) -> None:
        with pytest.raises(ValidationError):
            FilesystemConfig(read_size_cap_bytes=200_000_000)  # over 100MB ceiling

    def test_allow_binary_widen_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve(
                FilesystemConfig,
                {"allow_binary_files": False},
                {"allow_binary_files": True},
            )

    def test_allow_binary_revoke_passes(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"allow_binary_files": True},
            {"allow_binary_files": False},
        )
        assert r.allow_binary_files is False


# ---------------------------------------------------------------------------
# Caching invariant — model_post_init runs once
# ---------------------------------------------------------------------------


class TestCachingInvariant:
    def test_canonicalize_called_exactly_n_plus_m_times(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from the_one.tools import filesystem as fs_module

        counter = {"n": 0}
        original = fs_module.canonicalize

        def counting_canonicalize(p: Any) -> Any:
            counter["n"] += 1
            return original(p)

        monkeypatch.setattr(fs_module, "canonicalize", counting_canonicalize)

        cfg = FilesystemConfig(
            path_allowlist=["~", "/tmp", "/var/data"],
            path_denylist=["/etc", "/proc", "/sys", "/dev"],
        )
        # 3 + 4 = 7 — counter resets the assertion baseline before reads.
        baseline = counter["n"]
        assert baseline == 7, f"expected 7 init calls, got {baseline}"

        # 100 reads of each PrivateAttr — canonicalize must NOT be re-called.
        for _ in range(100):
            _ = cfg._canonical_allowlist
            _ = cfg._canonical_denylist
        assert counter["n"] == 7, (
            f"canonicalize re-executed on read: counter went from {baseline} to {counter['n']}"
        )


# ---------------------------------------------------------------------------
# UI hint round-trip via model_json_schema
# ---------------------------------------------------------------------------


class TestUiHint:
    def test_read_size_cap_carries_dropdown_hint(self) -> None:
        schema = FilesystemConfig.model_json_schema()
        prop = schema["properties"]["read_size_cap_bytes"]
        assert prop.get("ui_hint") == "dropdown"
        assert "ui_choices" in prop
        assert len(prop["ui_choices"]) == 6
        # Sanity: 1MB choice present
        values = [c["value"] for c in prop["ui_choices"]]
        assert 1_048_576 in values
