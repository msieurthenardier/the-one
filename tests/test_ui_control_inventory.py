"""Control-inventory and living-reference source guards (M25 F1 L6, DD10/DD11).

The inventory (``docs/ui-control-inventory.md``) and the ``App.ui`` factories in
``static/js/ui/*.js`` must agree in both directions, and the library sections of the
Design language page must be built only through the library.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._ui_guard_helpers import UI_DIR

REPO = Path(__file__).resolve().parent.parent
INVENTORY = REPO / "docs" / "ui-control-inventory.md"
SECTIONS_DIR = UI_DIR.parent / "areas" / "admin" / "design-language"

_FACTORY = re.compile(r"^\s*App\.ui\.(?!util\b)(\w+)\s*=\s*function\b", re.MULTILINE)
_CITATION = re.compile(r"\bApp\.ui\.(?!util\b)(\w+)\b")


def factory_names(ui_dir: Path = UI_DIR) -> set[str]:
    names: set[str] = set()
    for path in sorted(ui_dir.glob("*.js")):
        names.update(_FACTORY.findall(path.read_text()))
    return names


def inventory_citations(text: str) -> set[str]:
    return set(_CITATION.findall(text))


def check_inventory(text: str, factories: set[str]) -> list[str]:
    cited = inventory_citations(text)
    problems = [f"factory App.ui.{n} has no inventory row" for n in sorted(factories - cited)]
    problems += [
        f"inventory cites App.ui.{n}, which is not a factory" for n in sorted(cited - factories)
    ]
    return problems


def test_factories_found() -> None:
    assert {"button", "menu", "listPane", "badge"} <= factory_names()


def test_inventory_matches_factories() -> None:
    assert INVENTORY.is_file(), "docs/ui-control-inventory.md is missing"
    problems = check_inventory(INVENTORY.read_text(), factory_names())
    assert not problems, "\n".join(problems)


def test_inventory_rows_are_classified() -> None:
    """Every table row's status cell is ``library: App.ui.<x>`` or ``not yet defined``."""
    rows = 0
    for line in INVENTORY.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| Control") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 5, line
        status = cells[2]
        assert status == "not yet defined" or re.fullmatch(r"library: App\.ui\.\w+", status), line
        rows += 1
    assert rows >= 20


def test_guard_probe_fails_on_missing_row_and_stale_citation(tmp_path: Path) -> None:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "x.js").write_text(
        "  App.ui.alpha = function (opts) {\n  App.ui.beta = function (opts) {\n"
        "  App.ui.util.skipped = function () {\n  App.ui.alpha.KINDS = [];\n"
    )
    names = factory_names(ui)
    assert names == {"alpha", "beta"}
    assert check_inventory("library: App.ui.alpha, App.ui.beta", names) == []
    missing = check_inventory("library: App.ui.alpha", names)
    assert missing == ["factory App.ui.beta has no inventory row"]
    stale = check_inventory("App.ui.alpha App.ui.beta App.ui.gone", names)
    assert stale == ["inventory cites App.ui.gone, which is not a factory"]


# ── Living-reference source rules (AC2) ─────────────────────────────────────

LIBRARY_SECTIONS = sorted(SECTIONS_DIR.glob("ui-*-section.js"))
_RAW_CONTROL = re.compile(
    r"createElement\(\s*['\"](button|input|select|textarea)['\"]\s*\)|className\s*=\s*['\"]btn-"
)


def test_library_sections_exist() -> None:
    assert len(LIBRARY_SECTIONS) == 7


@pytest.mark.parametrize("path", LIBRARY_SECTIONS, ids=lambda p: p.name)
def test_library_section_uses_only_the_library(path: Path) -> None:
    text = path.read_text()
    assert not _RAW_CONTROL.search(text), path.name
    assert "innerHTML" not in text, path.name


def test_every_factory_is_demonstrated_in_source() -> None:
    """Each factory name appears as a ``demo(host, '<name>'`` call in a library section."""
    demoed: set[str] = set()
    for path in LIBRARY_SECTIONS:
        demoed.update(re.findall(r"\.demo\(host,\s*'(\w+)'", path.read_text()))
    assert demoed == factory_names()
