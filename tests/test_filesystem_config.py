"""Tests for FilesystemConfig (F3 L2a) — Pydantic shape, defaults, resolver
integration, model_post_init caching invariant, and ui_hint metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from the_one.platform import canonicalize
from the_one.tools.filesystem import (
    DEFAULT_PATH_DENYLIST,
    ConstraintError,
    FilesystemConfig,
    _filesystem_check,
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

    def test_path_denylist_dropped_tool_entry_is_unioned_back(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"path_denylist": ["/etc", "/proc"]},
            {"path_denylist": ["/etc"]},
        )
        assert r.path_denylist == ["/etc", "/proc"]

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
        # 3 allowlist + 4 explicit denylist + 1 dynamic data_dir/secrets = 8.
        baseline = counter["n"]
        assert baseline == 8, f"expected 8 init calls, got {baseline}"

        # 100 reads of each PrivateAttr — canonicalize must NOT be re-called.
        for _ in range(100):
            _ = cfg._canonical_allowlist
            _ = cfg._canonical_denylist
        assert counter["n"] == 8, (
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


# ---------------------------------------------------------------------------
# Frozen behavior (F4 L1b) — model_config = ConfigDict(frozen=True)
# ---------------------------------------------------------------------------


class TestFrozen:
    """FilesystemConfig is frozen so the per-call cross_configs view shared
    across tool instances cannot be mutated by one tool to corrupt another's
    view (F4 Decision 7)."""

    def test_attribute_assignment_raises_validation_error(self) -> None:
        cfg = FilesystemConfig()
        with pytest.raises(ValidationError):
            cfg.read_size_cap_bytes = 1  # type: ignore[misc]

    def test_assignment_to_other_fields_also_blocked(self) -> None:
        cfg = FilesystemConfig()
        with pytest.raises(ValidationError):
            cfg.allow_binary_files = True  # type: ignore[misc]
        with pytest.raises(ValidationError):
            cfg.path_allowlist = ["/tmp"]  # type: ignore[misc]

    def test_model_post_init_still_runs_post_freeze(self) -> None:
        # `frozen=True` blocks attribute assignment AFTER construction,
        # but `PrivateAttr` writes inside `model_post_init` use a different
        # path. The canonical-paths cache must still be populated.
        cfg = FilesystemConfig()
        assert cfg._canonical_allowlist  # non-empty (default ['~'] canonicalized)
        assert cfg._canonical_denylist  # non-empty (default DEFAULT_PATH_DENYLIST)

    def test_model_post_init_canonicalizes_custom_paths(self, tmp_path: Any) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        assert len(cfg._canonical_allowlist) == 1
        assert cfg._canonical_allowlist[0].is_absolute()


# ---------------------------------------------------------------------------
# Regression: data_dir/secrets always denied — tracks live data_dir (M15 F1)
# ---------------------------------------------------------------------------


class TestDataDirSecretsDenylist:
    """Regression net for the Leg-2 security regression where a placeholder
    ``"<data_dir>/secrets"`` literal was placed in ``DEFAULT_PATH_DENYLIST``
    instead of being resolved dynamically.  ``canonicalize("<data_dir>/secrets")``
    produces a bogus CWD-relative path that matches nothing — removing the
    ``~/.the-one/secrets`` protection.

    Fix: ``model_post_init`` appends ``canonicalize(str(settings.data_dir /
    "secrets"))`` to ``_canonical_denylist`` using the LIVE ``settings``
    singleton, so the protection tracks wherever ``data_dir`` actually
    resolves (default platformdirs or THE_ONE_DATA_DIR/init override).

    Tests reset the ``_settings`` cache and inject ``THE_ONE_DATA_DIR``
    so they are hermetic with respect to the real user data directory.
    """

    @pytest.fixture(autouse=True)
    def _isolated_data_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pin settings.data_dir to a tmp_path sub-dir for each test."""
        data_dir = tmp_path / "isolated-data-dir"
        monkeypatch.setenv("THE_ONE_DATA_DIR", str(data_dir))
        # Reset the PEP 562 lazy-singleton cache so settings re-reads the env var.
        monkeypatch.setattr("the_one.config._settings", None)

    def test_canonical_denylist_contains_data_dir_secrets(self, tmp_path: Path) -> None:
        """_canonical_denylist must include canonicalize(settings.data_dir / 'secrets')."""
        from the_one.config import settings

        expected = canonicalize(str(settings.data_dir / "secrets"))
        cfg = FilesystemConfig()
        assert expected in cfg._canonical_denylist, (
            f"data_dir/secrets ({expected}) missing from _canonical_denylist; "
            f"denylist = {cfg._canonical_denylist}"
        )

    def test_canonical_denylist_tracks_data_dir_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When THE_ONE_DATA_DIR is overridden, _canonical_denylist tracks the
        new location — not the platformdirs default and not the old value."""
        # Use a distinct sub-dir so the path differs from the autouse fixture's value.
        alt_data_dir = tmp_path / "alt-data-dir"
        monkeypatch.setenv("THE_ONE_DATA_DIR", str(alt_data_dir))
        monkeypatch.setattr("the_one.config._settings", None)  # flush cache again

        from the_one.config import settings

        expected = canonicalize(str(settings.data_dir / "secrets"))
        assert settings.data_dir == alt_data_dir  # sanity: override took effect
        cfg = FilesystemConfig()
        assert expected in cfg._canonical_denylist

    def test_filesystem_check_blocks_access_to_data_dir_secrets(self, tmp_path: Path) -> None:
        """_filesystem_check must raise ConstraintError for a path inside
        data_dir/secrets, exercising the full enforcement path."""
        from the_one.config import settings

        secrets_dir = settings.data_dir / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        target_file = secrets_dir / "api-key.txt"
        target_file.write_text("supersecret")

        # Allowlist must include secrets_dir for it to get past the allowlist
        # check and hit the denylist check (the real protection we are testing).
        cfg = FilesystemConfig(
            path_allowlist=[str(settings.data_dir)],
        )
        with pytest.raises(ConstraintError) as exc:
            _filesystem_check(str(target_file), cfg)
        assert "inside denylist" in str(exc.value)
