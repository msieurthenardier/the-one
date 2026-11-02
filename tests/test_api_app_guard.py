"""The shared-API-app pattern cannot quietly regrow (Mission 34 F1 L01, AC4).

A test file that builds its own ``FastAPI()`` and includes the API router pays about
55 ms per test for nothing; ``tests/_api_app.py::shared_app()`` is the one app. A file
may keep its own only when it changes the app (state, middleware, a mount, a lifespan)
and is listed below with the reason.

Known false negatives (the guard reads text with a regex): the router reached through
a module alias (``api.router``), and an app built in a helper outside ``tests/``.
"""

from __future__ import annotations

import re
from pathlib import Path

_TESTS = Path(__file__).parent

_BUILDS_APP = re.compile(r"\bFastAPI\(")
_INCLUDES_ROUTER = re.compile(r"include_router\(\s*(api_)?router\b")

ALLOWLIST = {
    "_api_app.py": "the shared app itself",
    "test_api_config_sandbox.py": "writes app.state through a real lifespan",
    "test_encryption_status.py": "one test adds the credential-gate middleware",
    "test_self_configuration_surface.py": "own lifespan and credential-gate middleware",
    "test_oauth_callback_gate.py": "adds the origin-allowlist and credential-gate middleware",
    "test_tools_admin_grid_assets.py": "mounts /static on the app",
    "test_tools_test_button_assets.py": "mounts /static on the app",
    "test_tools_admin_editor_assets.py": "mounts /static on the app",
}


def _offenders(paths) -> list[str]:
    found = []
    for path in sorted(paths):
        text = path.read_text(encoding="utf-8")
        if _BUILDS_APP.search(text) and _INCLUDES_ROUTER.search(text):
            found.append(path.name)
    return found


def test_no_test_file_builds_its_own_api_app() -> None:
    paths = list(_TESTS.glob("test_*.py")) + list(_TESTS.glob("_*.py"))
    offenders = [n for n in _offenders(paths) if n not in ALLOWLIST]
    assert not offenders, (
        f"{offenders} build FastAPI() and include the API router: use "
        "tests/_api_app.py::shared_app(), or add the file to ALLOWLIST here with the reason"
    )


def test_allowlist_entries_still_build_an_app() -> None:
    """An allowlist entry that no longer matches is stale: delete it."""
    still = set(_offenders(_TESTS / name for name in ALLOWLIST))
    stale = sorted(set(ALLOWLIST) - still)
    assert not stale, f"allowlisted files that no longer build their own API app: {stale}"


def test_guard_detects_the_pattern(tmp_path: Path) -> None:
    f = tmp_path / "test_x.py"
    # Strings are split so this file does not match its own regexes.
    build = "app = FastAPI" + "()\n"
    f.write_text(build + "app.include_router" + "(router)\n", encoding="utf-8")
    assert _offenders([f]) == ["test_x.py"]
    g = tmp_path / "test_y.py"
    g.write_text(build, encoding="utf-8")
    assert _offenders([g]) == []
