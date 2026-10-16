"""Control-inventory source guards (M25 F1 L6, DD10/DD11; reshaped by M31 F1 L1, DD7).

The catalogue (``docs/ui-control-inventory.md``) and the ``App.ui`` factories in
``static/js/ui/*.js`` must agree in both directions, and every factory must be called by at
least one engine-parametrized contract test (``tests/browser/test_ui_*.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._ui_guard_helpers import UI_DIR

REPO = Path(__file__).resolve().parent.parent
INVENTORY = REPO / "docs" / "ui-control-inventory.md"

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


def control_table_rows(text: str) -> list[list[str]]:
    """Cells of every row of every control table (a table whose header starts ``| Control |``).

    Other tables (colour tokens, "Owned by controls built later") are not control rows.
    """
    rows: list[list[str]] = []
    in_control_table = False
    for line in text.splitlines():
        if not line.startswith("|"):
            in_control_table = False
            continue
        if line.startswith("| Control |"):
            in_control_table = True
            continue
        if line.startswith("|---") or not in_control_table:
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def test_inventory_rows_are_classified() -> None:
    """Six cells per control row; status is ``library: App.ui.<x>`` or ``not yet defined``;
    a ``library:`` row lists at least one owned class (M31 F1 L2, DD3)."""
    rows = control_table_rows(INVENTORY.read_text())
    for cells in rows:
        assert len(cells) == 6, cells
        status, owned = cells[2], cells[4]
        if status == "not yet defined":
            assert owned == "\u2014", cells
        else:
            assert re.fullmatch(r"library: App\.ui\.\w+", status), cells
            assert re.fullmatch(r"`[\w-]+`(, `[\w-]+`)*", owned), cells
    assert len(rows) >= 20


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


# ── Contract-test rule (M31 F1 L1, flight DD7) ────────


def test_every_factory_has_a_contract_test() -> None:
    """Each factory is called as ``App.ui.<name>(`` in at least one ``test_ui_*.py``."""
    browser_dir = REPO / "tests" / "browser"
    text = "\n".join(p.read_text() for p in sorted(browser_dir.glob("test_ui_*.py")))
    untested = [n for n in sorted(factory_names()) if not re.search(rf"App\.ui\.{n}\(", text)]
    assert not untested, f"no tests/browser/test_ui_*.py calls App.ui.<name>( for: {untested}"
