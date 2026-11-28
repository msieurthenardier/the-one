"""The 800-line rule for Python modules (Mission 37, Flight 2 leg 03).

The Python twin of ``tests/test_area_module_size.py``: no module under ``the_one/`` grows
past 800 lines without a visible, reasoned allowance.

``ALLOWANCE`` lists the modules that are over 800 today, each at its CURRENT line count as a
ceiling. An entry is a ceiling, not an exact count:

- an unlisted module over 800 lines fails: split it, or add an entry with a reason;
- a listed module over its ceiling fails (it grew): split it, or raise the ceiling in the same
  PR with a one-line reason on the entry (growth must be visible, not impossible);
- a listed module at 800 lines or fewer fails too, naming the entry to remove, so the
  allowance only ever shrinks.

No generated or vendored Python lives under ``the_one/`` (checked at landing), so nothing is
excluded.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "the_one"
LIMIT = 800

REMEDY = "split the module, or raise its ALLOWANCE ceiling in this PR with a one-line reason"

# path relative to the_one/ -> ceiling (the line count when the guard landed).
ALLOWANCE: dict[str, int] = {
    # The route table; routes moved out in M37 F2 L1. 5126 -> 5040 (Sortie 22: sign-in flow moved).
    "interfaces/web/api.py": 5040,
    # The app factory and its wiring. Raised 4139 -> 4171 (Sortie 20, PR #392: agent delete).
    "interfaces/web/app.py": 4171,
    # Every repository in one module. Raised 4121 -> 4170 (Sortie 20, PR #392: delete cascade).
    "db/repositories.py": 4170,
    # The schema and its migration chain, append-only. Raised 3627 -> 3662 (Sortie 20, schema v57).
    "db/schema.py": 3662,
    # The diagnostics report builders.
    "diagnostics.py": 1364,
    # The MCP client.
    "mcp/client.py": 1171,
    # The desktop shell.
    "interfaces/desktop/shell.py": 1162,
    # The chart renderer.
    "visuals/chart_image.py": 1095,
    # The filesystem tools.
    "tools/filesystem.py": 844,
    # The agent factory.
    "agent/factory.py": 836,
    # The tool resolver.
    "tools/resolver.py": 826,
    # The routine service.
    "routines/service.py": 805,
}


def _sizes() -> dict[str, int]:
    return {
        p.relative_to(PACKAGE).as_posix(): len(p.read_text(encoding="utf-8").splitlines())
        for p in sorted(PACKAGE.rglob("*.py"))
    }


def violations(sizes: dict[str, int], allowance: dict[str, int]) -> list[str]:
    out: list[str] = []
    for path, n in sizes.items():
        ceiling = allowance.get(path)
        if ceiling is None:
            if n > LIMIT:
                out.append(
                    f"{path} is {n} lines (limit {LIMIT}) and has no allowance entry: {REMEDY}"
                )
        elif n > ceiling:
            out.append(f"{path} is {n} lines, over its allowance ceiling of {ceiling}: {REMEDY}")
        elif n <= LIMIT:
            out.append(f"{path} is {n} lines (<= {LIMIT}): remove its ALLOWANCE entry")
    for path in allowance:
        if path not in sizes:
            out.append(f"{path} no longer exists: remove its ALLOWANCE entry")
    return out


def test_python_modules_respect_the_line_rule() -> None:
    assert violations(_sizes(), ALLOWANCE) == []


def test_guard_detects_each_failure_mode() -> None:
    sizes = {"a.py": 801, "b.py": 900, "c.py": 800, "d.py": 120}
    assert violations(sizes, {}) == [
        f"a.py is 801 lines (limit 800) and has no allowance entry: {REMEDY}",
        f"b.py is 900 lines (limit 800) and has no allowance entry: {REMEDY}",
    ]
    assert violations({"b.py": 901}, {"b.py": 900}) == [
        f"b.py is 901 lines, over its allowance ceiling of 900: {REMEDY}"
    ]
    assert violations({"c.py": 800}, {"c.py": 900}) == [
        "c.py is 800 lines (<= 800): remove its ALLOWANCE entry"
    ]
    assert violations({}, {"gone.py": 900}) == [
        "gone.py no longer exists: remove its ALLOWANCE entry"
    ]


def test_every_allowance_entry_has_a_comment() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    body = source[source.index("ALLOWANCE: dict") : source.index("def _sizes")]
    lines = [ln.strip() for ln in body.splitlines()[1:] if ln.strip() and ln.strip() != "}"]
    for prev, cur in zip(lines[::2], lines[1::2], strict=True):
        assert prev.startswith("#") and cur.startswith('"'), (prev, cur)
