"""The 800-line rule for area modules (Mission 31, Flight 4 leg 01).

Mission 31's criterion: no module under ``static/js/areas/`` grows past 800
lines. ``studio.js`` has its own pin in ``test_store_static.py``; this guard
covers every area module.

``ALLOWANCE`` lists the modules that are over 800 today, each at its CURRENT
line count as a ceiling. An entry is a ceiling, not an exact count:

- an unlisted module over 800 lines fails;
- a listed module over its ceiling fails (it grew);
- a listed module at 800 lines or fewer fails too, naming the entry to remove,
  so the allowance only ever shrinks.
"""

from __future__ import annotations

from pathlib import Path

AREAS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/js/areas"
LIMIT = 800

# path relative to js/areas -> ceiling (the line count when the guard landed).
ALLOWANCE: dict[str, int] = {
    "chat.js": 2399,
    "studio/mcp-server-editor.js": 2153,
    "studio/provider-models.js": 1014,
    "studio/provider-editor.js": 896,
}


def _sizes() -> dict[str, int]:
    return {
        p.relative_to(AREAS).as_posix(): len(p.read_text(encoding="utf-8").splitlines())
        for p in sorted(AREAS.rglob("*.js"))
    }


def violations(sizes: dict[str, int], allowance: dict[str, int]) -> list[str]:
    out: list[str] = []
    for path, n in sizes.items():
        ceiling = allowance.get(path)
        if ceiling is None:
            if n > LIMIT:
                out.append(f"{path} is {n} lines (limit {LIMIT}) and has no allowance entry")
        elif n > ceiling:
            out.append(f"{path} is {n} lines, over its allowance ceiling of {ceiling}")
        elif n <= LIMIT:
            out.append(f"{path} is {n} lines (<= {LIMIT}): remove its ALLOWANCE entry")
    for path in allowance:
        if path not in sizes:
            out.append(f"{path} no longer exists: remove its ALLOWANCE entry")
    return out


def test_area_modules_respect_the_line_rule() -> None:
    assert violations(_sizes(), ALLOWANCE) == []


def test_guard_detects_each_failure_mode() -> None:
    sizes = {"a.js": 801, "b.js": 900, "c.js": 800, "d.js": 120}
    assert violations(sizes, {}) == [
        "a.js is 801 lines (limit 800) and has no allowance entry",
        "b.js is 900 lines (limit 800) and has no allowance entry",
    ]
    assert violations({"b.js": 901}, {"b.js": 900}) == [
        "b.js is 901 lines, over its allowance ceiling of 900"
    ]
    assert violations({"c.js": 800}, {"c.js": 900}) == [
        "c.js is 800 lines (<= 800): remove its ALLOWANCE entry"
    ]
    assert violations({}, {"gone.js": 900}) == [
        "gone.js no longer exists: remove its ALLOWANCE entry"
    ]
