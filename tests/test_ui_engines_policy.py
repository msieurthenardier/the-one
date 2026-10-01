"""Unit tests (unmarked, run in ``make test-unit``) for the WebKit skip/require
policy function in ``tests/browser/_ui_engines.py`` (M25 F1 L1, AC8)."""

from __future__ import annotations

from browser._ui_engines import (
    FORCE_UNAVAILABLE_ENV,
    REQUIRE_ENV,
    PolicyResult,
    webkit_policy,
)


def test_launch_ok_is_ok() -> None:
    assert webkit_policy({}, None) == PolicyResult("ok", "")
    assert webkit_policy({REQUIRE_ENV: "1"}, None).kind == "ok"


def test_failure_skips_when_not_required() -> None:
    r = webkit_policy({}, "libwoff missing")
    assert r.kind == "skip" and "libwoff missing" in r.reason
    assert webkit_policy({REQUIRE_ENV: "0"}, "x").kind == "skip"


def test_failure_fails_when_required() -> None:
    r = webkit_policy({REQUIRE_ENV: "1"}, "libwoff missing")
    assert r.kind == "fail" and "libwoff missing" in r.reason and REQUIRE_ENV in r.reason


def test_force_unavailable_seam() -> None:
    r = webkit_policy({FORCE_UNAVAILABLE_ENV: "1"}, None)
    assert r.kind == "skip" and FORCE_UNAVAILABLE_ENV in r.reason
    assert webkit_policy({FORCE_UNAVAILABLE_ENV: "1", REQUIRE_ENV: "1"}, None).kind == "fail"
    # A real error is kept over the forced reason.
    assert "boom" in webkit_policy({FORCE_UNAVAILABLE_ENV: "1"}, "boom").reason
