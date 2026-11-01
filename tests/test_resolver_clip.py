"""Sortie 07 leg 1: the resolver's total clip, the denied-list union, the
any-when-empty host list, and the strict-resolve contract (DD1-DD4).

* ``TestClipTable`` pins one row of DD2's table per test.
* ``TestAnyWhenEmpty`` / ``TestUnion`` / ``TestStrictResolve`` pin the strict side.
* ``TestProperties`` runs seeded, hand-rolled (no ``hypothesis``) generators over
  the four marked schemas: ``clip_override`` never raises, ``resolve`` of its output
  never raises, the output never gains a key, and no effective value is wider than
  the app-wide value or, where the agent's value is interpretable, the agent's own.
"""

from __future__ import annotations

import logging
import math
import random
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from the_one.tools._web_config import WebConfig
from the_one.tools._web_search_config import WebSearchConfig
from the_one.tools.execution import ExecutionConfig, PythonExecConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.resolver import (
    NO_HOSTS,
    NarrowAnyWhenEmpty,
    OverrideWidensError,
    _EmptyConfig,
    baseline_value,
    check_field,
    clip_field,
    clip_override,
    field_marker,
    resolve,
)


def _clip(schema: type[BaseModel], row: dict | None, override: dict | None):
    return clip_override(schema, row, override)


def _change(result, field: str):
    return next(c for c in result.changes if c.field == field)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    (h / "work").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


# ---------------------------------------------------------------------------
# The clip table (DD2), one row per test
# ---------------------------------------------------------------------------


class TestClipTable:
    def test_bool_off_wins(self) -> None:
        r = _clip(FilesystemConfig, {"allow_binary_files": False}, {"allow_binary_files": True})
        assert r.override == {"allow_binary_files": False}
        c = _change(r, "allow_binary_files")
        assert (c.kind, c.dropped, c.effective) == ("narrowed", [True], False)

    def test_bool_that_fits_is_untouched(self) -> None:
        for agent, app in [(False, True), (True, True), (False, False)]:
            r = _clip(FilesystemConfig, {"allow_binary_files": app}, {"allow_binary_files": agent})
            assert r.override == {"allow_binary_files": agent} and r.changes == ()

    def test_int_above_the_app_wide_value_is_lowered_to_it(self) -> None:
        r = _clip(WebConfig, {"response_size_cap_bytes": 2048}, {"response_size_cap_bytes": 9999})
        assert r.override == {"response_size_cap_bytes": 2048}
        assert _change(r, "response_size_cap_bytes").kind == "narrowed"

    def test_int_at_or_below_fits(self) -> None:
        r = _clip(WebConfig, {"response_size_cap_bytes": 2048}, {"response_size_cap_bytes": 1024})
        assert r.override == {"response_size_cap_bytes": 1024} and r.changes == ()

    def test_int_default_comes_from_the_schema_when_the_row_is_silent(self) -> None:
        r = _clip(WebConfig, {}, {"timeout_seconds_max": 5000})
        assert r.override == {"timeout_seconds_max": 120}

    def test_subset_list_is_intersected(self) -> None:
        r = _clip(
            WebConfig,
            {"extra_allowed_hosts": ["a:1", "b:2"]},
            {"extra_allowed_hosts": ["b:2", "c:3"]},
        )
        assert r.override == {"extra_allowed_hosts": ["b:2"]}
        assert _change(r, "extra_allowed_hosts").dropped == ["c:3"]

    def test_subset_list_may_be_emptied(self) -> None:
        r = _clip(WebConfig, {"extra_allowed_hosts": ["a:1"]}, {"extra_allowed_hosts": ["z:9"]})
        assert r.override == {"extra_allowed_hosts": []}

    def test_path_allowlist_inside_fits(self, home: Path) -> None:
        r = _clip(FilesystemConfig, {"path_allowlist": ["~"]}, {"path_allowlist": ["~/work"]})
        assert r.override == {"path_allowlist": ["~/work"]} and r.changes == ()

    def test_path_allowlist_outside_is_dropped_and_may_empty(
        self, home: Path, tmp_path: Path
    ) -> None:
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        r = _clip(
            FilesystemConfig,
            {"path_allowlist": ["~"]},
            {"path_allowlist": [str(outside), "~/work"]},
        )
        assert r.override == {"path_allowlist": ["~/work"]}
        assert _change(r, "path_allowlist").dropped == [str(outside)]
        only = _clip(
            FilesystemConfig, {"path_allowlist": ["~"]}, {"path_allowlist": [str(outside)]}
        )
        assert only.override == {"path_allowlist": []}  # allowed nowhere, never inherit

    def test_agent_parent_with_a_tightened_app_wide_list_keeps_the_app_wide_subfolder(
        self, home: Path
    ) -> None:
        r = _clip(FilesystemConfig, {"path_allowlist": ["~/work"]}, {"path_allowlist": ["~"]})
        assert r.override == {"path_allowlist": ["~/work"]}
        assert _change(r, "path_allowlist").kind == "narrowed"
        # The result is a valid override for the strict resolver.
        assert resolve(FilesystemConfig, {"path_allowlist": ["~/work"]}, r.override)

    def test_path_allowlist_bad_entries_are_dropped_one_at_a_time(
        self, home: Path, tmp_path: Path
    ) -> None:
        loop_a, loop_b = tmp_path / "la", tmp_path / "lb"
        loop_a.symlink_to(loop_b)
        loop_b.symlink_to(loop_a)
        bad = ["~nosuchuser/x", "a\x00b", str(loop_a / "child"), 7, None]
        r = _clip(
            FilesystemConfig,
            {"path_allowlist": ["~", "~nosuchuser", "\x00"]},  # bad app-wide entries too
            {"path_allowlist": [*bad, "~/work"]},
        )
        assert r.override == {"path_allowlist": ["~/work"]}
        assert _change(r, "path_allowlist").kind == "invalid"
        # An allow list emptied by bad entries is [] (never inherit).
        assert _clip(FilesystemConfig, {}, {"path_allowlist": bad}).override == {
            "path_allowlist": []
        }

    def test_non_list_allow_value_clips_to_the_strictest(self) -> None:
        assert _clip(FilesystemConfig, {}, {"path_allowlist": "~"}).override == {
            "path_allowlist": []
        }
        assert _clip(WebConfig, {}, {"extra_allowed_hosts": "x"}).override == {
            "extra_allowed_hosts": []
        }
        assert _clip(WebConfig, {}, {"host_allowlist": "x"}).override == {
            "host_allowlist": [NO_HOSTS]
        }

    def test_denied_lists_clip_only_bad_entries_and_keep_the_union_semantic(
        self, tmp_path: Path
    ) -> None:
        r = _clip(
            FilesystemConfig,
            {"path_denylist": ["/etc"]},
            {"path_denylist": ["/proc", "~nosuchuser", 5, "a\x00b"]},
        )
        # Dropped: no canonical path can fall under an uncanonicalisable entry.
        assert r.override == {"path_denylist": ["/proc"]}
        assert _change(r, "path_denylist").kind == "invalid"
        # An agent list missing an app-wide entry is NOT clipped: the union restores it.
        fit = _clip(FilesystemConfig, {"path_denylist": ["/etc"]}, {"path_denylist": ["/proc"]})
        assert fit.override == {"path_denylist": ["/proc"]} and fit.changes == ()

    def test_non_list_deny_value_drops_the_key(self) -> None:
        r = _clip(ExecutionConfig, {}, {"command_denylist": "rm"})
        assert r.override == {}
        assert _change(r, "command_denylist").kind == "invalid"

    def test_non_string_command_denylist_entries_are_dropped(self) -> None:
        r = _clip(ExecutionConfig, {}, {"command_denylist": ["rm", 3, None]})
        assert r.override == {"command_denylist": ["rm"]}

    def test_substitute_is_not_clipped_but_must_be_the_right_type(self) -> None:
        ok = _clip(WebConfig, {}, {"default_user_agent": "bot/1"})
        assert ok.override == {"default_user_agent": "bot/1"} and ok.changes == ()
        bad = _clip(WebConfig, {}, {"default_user_agent": 5})
        assert bad.override == {} and _change(bad, "default_user_agent").kind == "invalid"

    def test_unmarked_fields_are_never_agent_settable(self) -> None:
        r = _clip(WebConfig, {}, {"redirect_cap": 0})
        assert r.override == {} and _change(r, "redirect_cap").kind == "invalid"
        s = _clip(WebSearchConfig, {}, {"search_backend": "brave", "brave_api_key": "k"})
        assert s.override == {}
        assert {c.field for c in s.changes} == {"search_backend", "brave_api_key"}
        # And the strict resolver still refuses them.
        with pytest.raises(ValueError, match="no Narrow/Substitute marker"):
            resolve(WebConfig, {}, {"redirect_cap": 0})

    def test_numbers_are_clamped_and_uninterpretable_values_inherit(self) -> None:
        r = _clip(
            WebConfig,
            {"timeout_seconds_max": 120},
            {"timeout_seconds_max": "10"},  # a string for an int: never applied
        )
        assert r.override == {} and _change(r, "timeout_seconds_max").kind == "invalid"
        neg = _clip(ExecutionConfig, {}, {"max_concurrent_sessions": -4})
        assert neg.override == {"max_concurrent_sessions": 1}  # clamped into the schema bounds
        frac = _clip(ExecutionConfig, {}, {"max_concurrent_sessions": 3.7})
        assert frac.override == {"max_concurrent_sessions": 3}  # the narrower whole number
        b = _clip(ExecutionConfig, {}, {"max_concurrent_sessions": True})
        assert b.override == {}
        nan = _clip(ExecutionConfig, {}, {"output_cap_bytes": math.nan})
        assert nan.override == {}

    def test_a_bool_field_with_a_non_bool_value_is_dropped(self) -> None:
        assert _clip(ExecutionConfig, {}, {"sandbox_network_allowed": 1}).override == {}

    def test_none_and_non_dict_overrides(self) -> None:
        assert _clip(WebConfig, {}, None).override is None
        assert _clip(WebConfig, {}, "junk").override == {}  # type: ignore[arg-type]
        assert _clip(WebConfig, "junk", {"timeout_seconds_max": 5}).override == {  # type: ignore[arg-type]
            "timeout_seconds_max": 5
        }

    def test_unknown_keys_pass_through_and_the_empty_schema_is_a_no_op(self) -> None:
        r = _clip(WebConfig, {}, {"nonsense": 1, "timeout_seconds_max": 60})
        assert r.override == {"nonsense": 1, "timeout_seconds_max": 60}
        e = _clip(_EmptyConfig, {}, {"x": 1})
        assert e.override == {"x": 1} and e.changes == ()


class TestClipHostAllowlist:
    def test_agent_any_against_an_app_wide_list_is_the_app_wide_list(self) -> None:
        r = _clip(WebConfig, {"host_allowlist": ["a.com", "b.com"]}, {"host_allowlist": []})
        assert r.override == {"host_allowlist": ["a.com", "b.com"]}
        c = _change(r, "host_allowlist")
        assert (c.kind, c.dropped) == ("narrowed", [])

    def test_any_on_both_sides_fits(self) -> None:
        r = _clip(WebConfig, {}, {"host_allowlist": []})
        assert r.override == {"host_allowlist": []} and r.changes == ()

    def test_a_list_against_any_fits(self) -> None:
        r = _clip(WebConfig, {"host_allowlist": []}, {"host_allowlist": ["a.com"]})
        assert r.override == {"host_allowlist": ["a.com"]} and r.changes == ()

    def test_subset_fits_and_extras_are_dropped(self) -> None:
        row = {"host_allowlist": ["a.com", "b.com"]}
        assert _clip(WebConfig, row, {"host_allowlist": ["a.com"]}).changes == ()
        r = _clip(WebConfig, row, {"host_allowlist": ["a.com", "z.com"]})
        assert r.override == {"host_allowlist": ["a.com"]}

    def test_an_empty_intersection_is_no_hosts_never_inherit(self) -> None:
        r = _clip(WebConfig, {"host_allowlist": ["a.com"]}, {"host_allowlist": ["z.com"]})
        assert r.override == {"host_allowlist": [NO_HOSTS]}

    def test_bad_entries_emptying_the_list_give_no_hosts(self) -> None:
        r = _clip(WebConfig, {}, {"host_allowlist": [1, None]})
        assert r.override == {"host_allowlist": [NO_HOSTS]}
        assert _change(r, "host_allowlist").kind == "invalid"

    def test_a_list_holding_no_hosts_always_fits(self) -> None:
        for row in ({}, {"host_allowlist": ["a.com"]}, {"host_allowlist": [NO_HOSTS]}):
            r = _clip(WebConfig, row, {"host_allowlist": [NO_HOSTS]})
            assert r.override == {"host_allowlist": [NO_HOSTS]} and r.changes == ()

    def test_app_wide_no_hosts_leaves_nothing_but_no_hosts(self) -> None:
        r = _clip(WebConfig, {"host_allowlist": [NO_HOSTS]}, {"host_allowlist": ["a.com"]})
        assert r.override == {"host_allowlist": [NO_HOSTS]}
        any_ = _clip(WebConfig, {"host_allowlist": [NO_HOSTS]}, {"host_allowlist": []})
        assert any_.override == {"host_allowlist": [NO_HOSTS]}


class TestClipDefaultFollowsMax:
    def test_a_lowered_max_lowers_the_inherited_default_report_only(self) -> None:
        row = {"timeout_seconds_default": 30, "timeout_seconds_max": 120}
        r = _clip(ExecutionConfig, row, {"timeout_seconds_max": 20})
        assert r.override == {"timeout_seconds_max": 20}  # never written to the override
        c = _change(r, "timeout_seconds_default")
        assert (c.kind, c.effective) == ("coupled", 20)
        cfg = resolve(ExecutionConfig, row, r.override)
        assert (cfg.timeout_seconds_default, cfg.timeout_seconds_max) == (20, 20)

    def test_python_exec_follows_its_own_default(self) -> None:
        cfg = resolve(PythonExecConfig, {}, {"timeout_seconds_max": 40})
        assert (cfg.timeout_seconds_default, cfg.timeout_seconds_max) == (40, 40)

    def test_an_own_default_above_a_tightened_app_wide_max_is_lowered(self) -> None:
        # An app-wide max tightened below the app-wide default (a row the Settings
        # PUT would not accept, but the clip is total): the agent's own default
        # (25, within the app default 30) is lowered to the max, kind narrowed.
        r = _clip(
            ExecutionConfig,
            {"timeout_seconds_default": 30, "timeout_seconds_max": 20},
            {"timeout_seconds_default": 25},
        )
        assert r.override == {"timeout_seconds_default": 20}
        assert _change(r, "timeout_seconds_default").kind == "narrowed"

    def test_an_own_default_above_the_app_wide_default_is_lowered_to_it(self) -> None:
        r = _clip(
            ExecutionConfig,
            {"timeout_seconds_default": 10, "timeout_seconds_max": 20},
            {"timeout_seconds_default": 30},
        )
        assert r.override == {"timeout_seconds_default": 10}

    def test_legacy_own_default_above_own_max_is_clipped_to_that_max(self) -> None:
        row = {"timeout_seconds_default": 30, "timeout_seconds_max": 120}
        r = _clip(ExecutionConfig, row, {"timeout_seconds_default": 25, "timeout_seconds_max": 20})
        assert r.override == {"timeout_seconds_default": 20, "timeout_seconds_max": 20}
        assert _change(r, "timeout_seconds_default").kind == "invalid"
        assert resolve(ExecutionConfig, row, r.override).timeout_seconds_default == 20


# ---------------------------------------------------------------------------
# The strict side
# ---------------------------------------------------------------------------


class TestAnyWhenEmpty:
    def test_marker_on_the_wire_field(self) -> None:
        assert field_marker(WebConfig, "host_allowlist") is NarrowAnyWhenEmpty

    def test_a_list_against_an_empty_app_wide_list_now_fits(self) -> None:
        cfg = resolve(WebConfig, {}, {"host_allowlist": ["a.com"]})
        assert cfg.host_allowlist == ["a.com"]

    def test_empty_means_any_on_both_sides(self) -> None:
        assert resolve(WebConfig, {}, {"host_allowlist": []}).host_allowlist == []

    def test_agent_empty_against_a_non_empty_list_widens_the_old_hole_is_closed(self) -> None:
        with pytest.raises(OverrideWidensError, match="widens WebConfig.host_allowlist"):
            resolve(WebConfig, {"host_allowlist": ["a.com"]}, {"host_allowlist": []})

    def test_a_list_outside_the_app_wide_list_widens(self) -> None:
        with pytest.raises(OverrideWidensError) as exc:
            resolve(
                WebConfig, {"host_allowlist": ["a.com"]}, {"host_allowlist": ["a.com", "b.com"]}
            )
        assert exc.value.value == "b.com"

    def test_no_hosts_always_fits(self) -> None:
        for row in ({}, {"host_allowlist": ["a.com"]}, {"host_allowlist": [NO_HOSTS]}):
            cfg = resolve(WebConfig, row, {"host_allowlist": [NO_HOSTS]})
            assert cfg.host_allowlist == [NO_HOSTS]

    def test_non_list_is_a_type_mismatch(self) -> None:
        with pytest.raises(NotImplementedError, match="NarrowAnyWhenEmpty on non-list"):
            check_field(WebConfig, "host_allowlist", ["a"], "a.com")


class TestAppWideNoHostsBesideOtherHosts:
    def test_the_entry_refuses_every_url_so_the_app_wide_value_is_no_hosts(self) -> None:
        row = {"host_allowlist": ["a.com", NO_HOSTS]}
        with pytest.raises(OverrideWidensError):
            resolve(WebConfig, row, {"host_allowlist": ["a.com"]})
        r = _clip(WebConfig, row, {"host_allowlist": ["a.com"]})
        assert r.override == {"host_allowlist": [NO_HOSTS]}
        assert resolve(WebConfig, row, r.override).host_allowlist == [NO_HOSTS]


class TestBuildPath:
    def test_get_tools_clips_each_override_and_passes_tool_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import the_one.tools.builtins as builtins_mod

        seen: dict[str, Any] = {}
        real = builtins_mod.resolve

        def spy(schema, tool_config, override, **kw):
            if "tool_name" in kw:
                seen[kw["tool_name"]] = (override, kw)
            return real(schema, tool_config, override, **kw)

        monkeypatch.setattr(builtins_mod, "resolve", spy)
        builtins_mod._clip_warned.clear()
        # A widening override (4096 > the 2048 row) reaches `resolve` already clipped.
        tools = builtins_mod.BuiltinToolProvider().get_tools(
            {"fetch_url": {"response_size_cap_bytes": 2048}},
            {"fetch_url": {"response_size_cap_bytes": 4096}},
            agent_name="spy-agent",
        )
        assert set(seen) == set(builtins_mod._TOOL_CLASSES)  # every per-tool call named its tool
        assert seen["fetch_url"][0] == {"response_size_cap_bytes": 2048}
        assert {t.name: t for t in tools}["fetch_url"]._config.response_size_cap_bytes == 2048

    def test_the_build_never_raises_for_a_junk_override(self) -> None:
        import the_one.tools.builtins as builtins_mod

        junk = {
            "read_file": {"path_allowlist": "~", "read_size_cap_bytes": "big"},
            "shell": {"timeout_seconds_max": -1, "command_denylist": 5},
            "fetch_url": {"host_allowlist": [1], "redirect_cap": 0},
            "web_search": {"search_backend": "brave"},
        }
        tools = builtins_mod.BuiltinToolProvider().get_tools({}, junk, agent_name="junk")
        names = {t.name for t in tools}
        assert {"read_file", "shell", "fetch_url", "web_search"} <= names


class TestUnion:
    def test_denied_list_is_app_wide_union_agent_and_never_raises(self) -> None:
        cfg = resolve(WebConfig, {"host_denylist": ["a"]}, {"host_denylist": ["b"]})
        assert cfg.host_denylist == ["a", "b"]
        assert resolve(
            WebConfig, {"host_denylist": ["a"]}, {"host_denylist": []}
        ).host_denylist == ["a"]

    def test_a_stored_full_union_resolves_to_the_same_set(self) -> None:
        row = {"host_denylist": ["a", "b"]}
        assert resolve(WebConfig, row, {"host_denylist": ["a", "b", "c"]}).host_denylist == [
            "a",
            "b",
            "c",
        ]
        assert resolve(WebConfig, row, {"host_denylist": ["a", "b"]}).host_denylist == ["a", "b"]

    def test_agent_empty_denylist_against_the_default_keeps_the_defaults(self) -> None:
        cfg = resolve(FilesystemConfig, {}, {"path_denylist": []})
        assert set(FilesystemConfig().path_denylist) <= set(cfg.path_denylist)


class TestStrictResolve:
    def test_widening_is_an_override_widens_error_with_unchanged_text(self) -> None:
        with pytest.raises(OverrideWidensError) as exc:
            resolve(WebConfig, {"timeout_seconds_max": 60}, {"timeout_seconds_max": 600})
        e = exc.value
        assert isinstance(e, ValueError)
        assert (
            str(e) == "agent override widens WebConfig.timeout_seconds_max; only narrowing allowed"
        )
        assert (e.schema_name, e.field, e.marker, e.value, e.tool) == (
            "WebConfig",
            "timeout_seconds_max",
            "Narrow",
            600,
            None,
        )

    def test_tool_name_is_carried(self) -> None:
        with pytest.raises(OverrideWidensError) as exc:
            resolve(
                WebConfig,
                {"timeout_seconds_max": 60},
                {"timeout_seconds_max": 600},
                tool_name="fetch_url",
            )
        assert exc.value.tool == "fetch_url"

    def test_path_widening_message_is_unchanged(self, home: Path, tmp_path: Path) -> None:
        outside = str(tmp_path / "elsewhere")
        with pytest.raises(OverrideWidensError) as exc:
            resolve(FilesystemConfig, {"path_allowlist": ["~"]}, {"path_allowlist": [outside]})
        assert str(exc.value) == (
            f"agent override widens FilesystemConfig.path_allowlist; "
            f"'{outside}' not within any tool entry"
        )
        assert exc.value.value == outside and exc.value.marker == "NarrowPrefix"

    def test_check_field_is_the_per_field_check(self) -> None:
        check_field(WebConfig, "timeout_seconds_max", 120, 60)  # fits: returns None
        with pytest.raises(OverrideWidensError) as exc:
            check_field(WebConfig, "timeout_seconds_max", 60, 120, tool_name="http_request")
        assert exc.value.field == "timeout_seconds_max" and exc.value.tool == "http_request"
        # Substitute: never checked.
        check_field(WebConfig, "default_user_agent", "a", "b")

    def test_clip_field_is_the_per_field_clip(self) -> None:
        fc = clip_field(WebConfig, "timeout_seconds_max", 60, 120)
        assert (fc.value, fc.kind, fc.dropped, fc.changed) == (60, "narrowed", [120], True)
        assert clip_field(WebConfig, "timeout_seconds_max", 60, 30).changed is False

    def test_baseline_value_prefers_the_row_then_the_default(self) -> None:
        assert baseline_value(WebConfig, "timeout_seconds_max", {"timeout_seconds_max": 7}) == 7
        assert baseline_value(WebConfig, "timeout_seconds_max", {}) == 120
        assert baseline_value(WebConfig, "host_denylist", None) == []


# ---------------------------------------------------------------------------
# Properties (seeded, hand-rolled)
# ---------------------------------------------------------------------------


CASES = 3000


class _Ctx:
    def __init__(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        (home / "work").mkdir(parents=True)
        for rel in ("a/b/c", "d", "e/f"):
            (tmp_path / rel).mkdir(parents=True)
        loop_a, loop_b = tmp_path / "loop_a", tmp_path / "loop_b"
        loop_a.symlink_to(loop_b)
        loop_b.symlink_to(loop_a)
        self.paths = [
            "~",
            "~/work",
            str(tmp_path / "a"),
            str(tmp_path / "a" / "b"),
            str(tmp_path / "a" / "b" / "c"),
            str(tmp_path / "d"),
            str(tmp_path / "e"),
            str(tmp_path / "e" / "f"),
            str(tmp_path / "a" / ".." / "d"),
            "/etc",
            "/proc",
        ]
        self.bad_paths = [
            "~nosuchuser",
            "~nosuchuser/x",
            "a\x00b",
            "\x00",
            str(loop_a),
            str(loop_a / "child"),
        ]
        self.hosts = ["a.com", "b.com", "c.org", "localhost:11434", "127.0.0.1", NO_HOSTS]
        self.commands = ["sudo ", "rm -rf", "curl ", "dd "]
        self.junk: list[Any] = [
            "abc",
            "",
            None,
            0,
            3,
            -5,
            10**12,
            5.5,
            -0.5,
            True,
            False,
            [],
            [1, "a", None],
            ["a.com", 3],
            {},
            {"a": 1},
            "5",
            "~nosuchuser/x",
            "\x00",
            ["\x00/x"],
            ["~nosuchuser"],
            self.bad_paths,
            [self.bad_paths[4]],
            [NO_HOSTS],
            [NO_HOSTS, "a.com"],
            math.nan,
            math.inf,
        ]

    def list_pool(self, name: str) -> list[str]:
        if "path" in name:
            return self.paths
        if "command" in name:
            return self.commands
        return self.hosts


def _bounds(info: Any) -> tuple[int, int]:
    lo, hi = 1, 10**8
    for m in info.metadata:
        if getattr(m, "ge", None) is not None:
            lo = m.ge
        if getattr(m, "le", None) is not None:
            hi = m.le
    return lo, hi


def _typed(rng: random.Random, schema: type[BaseModel], name: str, ctx: _Ctx) -> Any:
    info = schema.model_fields[name]
    ann = info.annotation
    if ann is bool:
        return rng.random() < 0.5
    if ann is int:
        lo, hi = _bounds(info)
        return rng.choice([lo, hi, rng.randint(lo, min(hi, lo + 5000)), rng.randint(lo, hi)])
    if ann is str:
        return rng.choice(["bot/1", "x" * 30, ""])
    pool = ctx.list_pool(name)
    return rng.sample(pool, rng.randint(0, min(4, len(pool))))


def _gen_row(rng: random.Random, schema: type[BaseModel], ctx: _Ctx, *, bad: bool) -> dict:
    row: dict[str, Any] = {}
    for name, info in schema.model_fields.items():
        if rng.random() < 0.4:
            continue
        if name in ("timeout_seconds_default", "timeout_seconds_max", "redirect_cap"):
            continue
        if name == "host_allowlist" and rng.random() < 0.3:
            row[name] = rng.choice([[], [NO_HOSTS]])
            continue
        v = _typed(rng, schema, name, ctx)
        if bad and name in ("path_allowlist", "host_allowlist") and isinstance(v, list):
            v = v + rng.sample(ctx.bad_paths, 2)
            rng.shuffle(v)
        row[name] = v
    if "timeout_seconds_max" in schema.model_fields:
        # Keep default <= max, both in range.
        mx = rng.choice([5, 30, 120, 600, 3600])
        df = rng.randint(1, mx)
        if rng.random() < 0.7:
            row["timeout_seconds_max"] = mx
            row["timeout_seconds_default"] = df
    return row


def _gen_override(rng: random.Random, schema: type[BaseModel], ctx: _Ctx) -> dict:
    out: dict[str, Any] = {}
    for name in schema.model_fields:
        if rng.random() < 0.55:
            continue
        r = rng.random()
        if r < 0.3:
            out[name] = rng.choice(ctx.junk)
        elif r < 0.4 and "path" in name:
            out[name] = rng.sample(ctx.bad_paths, rng.randint(1, 3)) + rng.sample(ctx.paths, 1)
        else:
            out[name] = _typed(rng, schema, name, ctx)
    if rng.random() < 0.05:
        out["not_a_field"] = rng.choice(ctx.junk)
    return out


def _hosts_set(lst: list) -> Any:
    """A host list as a set, with the empty list modelled as the universe."""
    if not lst:
        return None  # universe
    if NO_HOSTS in lst:
        return frozenset()
    return frozenset(lst)


def _hosts_subset(s: Any, t: Any) -> bool:
    if t is None:
        return True
    if s is None:
        return False
    return s <= t


def _canon(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _inside(p: str, roots: list[str]) -> bool:
    c = _canon(p)
    for r in roots:
        try:
            c.relative_to(_canon(r))
            return True
        except ValueError:
            continue
    return False


def _clean_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _canonical_ok(p: Any) -> bool:
    if not isinstance(p, str):
        return False
    try:
        _canon(p)
        return True
    except (RuntimeError, OSError, ValueError):
        return False


def _assert_not_wider(
    schema: type[BaseModel], row: dict, override: dict, eff: BaseModel, ctx: _Ctx
) -> None:
    for name, info in schema.model_fields.items():
        if name not in override and not name.endswith("denylist"):
            continue
        try:
            marker = field_marker(schema, name)
        except ValueError:
            continue  # unmarked: never agent-settable, nothing to bound
        app = row[name] if name in row else baseline_value(schema, name, row)
        val = getattr(eff, name)
        agent = override.get(name, None)
        has_agent = name in override
        mname = marker.__name__ if marker else ""
        if mname == "NarrowSuperset":
            assert isinstance(app, list)
            assert all(a in val for a in app), (name, app, val)
        elif mname == "Narrow" and isinstance(val, bool):
            if val:
                assert app is True
                if has_agent and isinstance(agent, bool):
                    assert agent is True
        elif mname == "Narrow" and isinstance(val, (int, float)):
            assert val <= app, (name, val, app)
            lo, hi = _bounds(info)
            if (
                has_agent
                and isinstance(agent, (int, float))
                and not isinstance(agent, bool)
                and math.isfinite(agent)
                and lo <= agent <= hi
                and name not in ("timeout_seconds_default",)
            ):
                assert val <= agent, (name, val, agent)
        elif mname == "Narrow" and isinstance(val, list):
            assert all(v in app for v in val), (name, val, app)
            if has_agent and _clean_list(agent):
                assert all(v in agent for v in val)
        elif mname == "NarrowAnyWhenEmpty":
            assert _hosts_subset(_hosts_set(val), _hosts_set(app)), (name, val, app)
            if has_agent and _clean_list(agent):
                assert _hosts_subset(_hosts_set(val), _hosts_set(agent)), (name, val, agent)
        elif mname == "NarrowPrefix":
            assert all(_inside(v, app) for v in val), (name, val, app)
            if has_agent and isinstance(agent, list):
                good = [a for a in agent if _canonical_ok(a)]
                assert all(_inside(v, good) for v in val), (name, val, agent)


@pytest.mark.parametrize("schema", [FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig])
class TestProperties:
    def test_clip_is_total_and_resolve_of_the_clip_never_raises(
        self,
        schema: type[BaseModel],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
        ctx = _Ctx(tmp_path)
        rng = random.Random(f"sortie-07-{schema.__name__}")
        resolved = 0
        with caplog.at_level(logging.ERROR, logger="the_one.tools.resolver"):
            for _ in range(CASES):
                row = _gen_row(rng, schema, ctx, bad=False)
                override = _gen_override(rng, schema, ctx)
                snapshot = repr(override)
                result = clip_override(schema, row, override)  # must not raise
                assert repr(override) == snapshot, "clip mutated its input"
                assert result.override is not None
                assert set(result.override) <= set(override), "the clip gained a key"
                try:
                    app_cfg = schema.model_validate(row)
                except Exception:
                    continue  # the generated app-wide row is itself invalid: skip resolve
                eff = resolve(schema, row, result.override)  # must not raise
                resolved += 1
                assert app_cfg is not None
                _assert_not_wider(schema, row, result.override, eff, ctx)
                # Wider than the agent's value is checked against the ORIGINAL override.
                _assert_not_wider(schema, row, override, eff, ctx)
        assert resolved > CASES * 0.8
        assert not [r for r in caplog.records if "clip failed" in r.getMessage()]

    def test_bad_app_wide_allow_list_entries_never_make_the_clip_raise(
        self,
        schema: type[BaseModel],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
        ctx = _Ctx(tmp_path)
        rng = random.Random(f"sortie-07-bad-{schema.__name__}")
        with caplog.at_level(logging.ERROR, logger="the_one.tools.resolver"):
            for _ in range(CASES):
                row = _gen_row(rng, schema, ctx, bad=True)
                override = _gen_override(rng, schema, ctx)
                result = clip_override(schema, row, override)
                assert set(result.override) <= set(override)
                # Every kept path entry lies within a canonicalisable app-wide entry
                # (an uncanonicalisable app-wide entry contains nothing).
                kept = (result.override or {}).get("path_allowlist")
                app = row.get("path_allowlist")
                if schema is FilesystemConfig and isinstance(kept, list):
                    roots = [p for p in (app if isinstance(app, list) else []) if _canonical_ok(p)]
                    if "path_allowlist" not in row:
                        roots = ["~"]
                    assert all(_inside(v, roots) for v in kept), (kept, app)
        assert not [r for r in caplog.records if "clip failed" in r.getMessage()]
