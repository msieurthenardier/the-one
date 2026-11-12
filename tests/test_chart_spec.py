"""The Python chart validator against the shared corpus (M35 F1 L1, DD3).

``docs/chart-format.md`` is the single source of the error sentences and
``tests/fixtures/charts/`` is the executable form of the document. The browser control is
tested against the same files (``tests/browser/test_ui_chart_contract.py``).
"""

from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path

import pytest

from the_one.visuals import chart_spec
from the_one.visuals.chart_spec import ChartError, ChartSpec, format_full, format_tick, parse_chart

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(__file__).resolve().parent / "fixtures" / "charts"
DOC = ROOT / "docs" / "chart-format.md"
VALID = sorted((CORPUS / "valid").glob("*.json"))
INVALID = sorted(p for p in (CORPUS / "invalid").glob("*.json") if p.name != "expected.json")
EXPECTED = json.loads((CORPUS / "invalid" / "expected.json").read_text(encoding="utf-8"))


def _documented_sentences() -> set[str]:
    """The backticked sentence in the last cell of each row of the document's error table."""
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Error sentences", 1)[1].split("\n## ", 1)[0]
    found = set()
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("| Rule") or line.startswith("|---"):
            continue
        last = line.rstrip().rstrip("|").rsplit("|", 1)[1]
        found.update(re.findall(r"`([^`]+)`", last))
    return found


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_every_valid_file_parses(path: Path) -> None:
    result = parse_chart(path.read_text(encoding="utf-8"))
    assert isinstance(result, ChartSpec), result


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_every_invalid_file_yields_its_sentence(path: Path) -> None:
    result = parse_chart(path.read_text(encoding="utf-8"))
    assert isinstance(result, ChartError), "expected a refusal"
    assert result.message == EXPECTED[path.name]


def test_expected_json_keys_are_the_invalid_files() -> None:
    assert set(EXPECTED) == {p.name for p in INVALID}


def test_document_is_the_single_source_of_the_sentences() -> None:
    documented = _documented_sentences()
    # AC3b: every corpus sentence is in the document's list, and every listed sentence has a file.
    assert set(EXPECTED.values()) == documented


def test_corpus_covers_every_type_and_the_named_features() -> None:
    specs = [parse_chart(p.read_text(encoding="utf-8")) for p in VALID]
    assert {s.type for s in specs} == set(chart_spec.TYPES)
    assert any(s.stacked and s.type == "bar" for s in specs)
    assert any(s.stacked and s.type == "area" for s in specs)
    assert any(s.y2 is not None and any(x.axis == "right" for x in s.series) for s in specs)
    assert any(len({x.type for x in s.series}) > 1 for s in specs)
    assert any(s.y.scale == "log" for s in specs)
    assert {a.axis for s in specs for a in s.annotations} == {"y", "y2", "x"}
    assert any(v is None for s in specs for x in s.series for v in x.values)


def test_drift_traps_match_the_document() -> None:
    # An emoji label at exactly 60 code points is valid, one more is not.
    at_limit = json.loads((CORPUS / "valid" / "label-at-limit-emoji.json").read_text("utf-8"))
    assert len(at_limit["x"]["values"][0]) == 60
    over = json.loads((CORPUS / "invalid" / "label-over-limit-emoji.json").read_text("utf-8"))
    assert len(over["x"]["values"][0]) == 61
    # NaN / Infinity / booleans are never numbers.
    for body in (
        '{"type":"line","x":{"values":["a"]},"series":[{"values":[NaN]}]}',
        '{"type":"line","x":{"values":["a"]},"series":[{"values":[Infinity]}]}',
        '{"type":"line","x":{"values":["a"]},"series":[{"values":[true]}]}',
        '{"type":"line","x":{"values":["a"]},"series":[{"values":[1e999]}]}',
        '{"type":"line","x":{"values":["a"]},"series":[{"values":[1' + "0" * 400 + "]}]}",
    ):
        assert isinstance(parse_chart(body), ChartError), body
    # x.values on a scatter is ignored; a zero pie slice is kept.
    scatter = parse_chart((CORPUS / "valid" / "scatter-x-values-ignored.json").read_text("utf-8"))
    assert isinstance(scatter, ChartSpec) and scatter.x.values is None
    pie = parse_chart((CORPUS / "valid" / "pie-zero-slice.json").read_text("utf-8"))
    assert isinstance(pie, ChartSpec) and 0 in pie.series[0].values


def test_normalised_defaults() -> None:
    spec = parse_chart('{"type":"bar","x":{"values":["a"]},"series":[{"values":[1]}]}')
    assert isinstance(spec, ChartSpec)
    assert (spec.stacked, spec.y.scale, spec.series[0].axis, spec.y2) == (
        False,
        "linear",
        "left",
        None,
    )
    with pytest.raises(Exception):  # frozen
        spec.stacked = True  # type: ignore[misc]


NUMBER_ROWS = json.loads((CORPUS / "number-format.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("value,unit,tick,full", NUMBER_ROWS)
def test_number_format_rows(value: float, unit: str, tick: str, full: str) -> None:
    assert format_tick(value, unit) == tick
    assert format_full(value, unit) == full


def test_never_raises_on_truncated_prefixes_of_every_valid_file() -> None:
    for path in VALID:
        text = path.read_text(encoding="utf-8")
        for end in range(0, len(text) + 1, 3):
            result = parse_chart(text[:end])
            assert isinstance(result, (ChartSpec, ChartError))


@pytest.mark.parametrize(
    "source",
    ["", " ", "null", "[]", "0", '"x"', "{", "{}", '{"type":null}', "\x00", "[" * 5000, "{" * 5000],
)
def test_never_raises_on_odd_input(source: str) -> None:
    assert isinstance(parse_chart(source), ChartError)


def test_a_large_input_over_the_value_limit_is_refused_quickly() -> None:
    values = ",".join(["1"] * 30000)  # roughly 60 KB per series
    x = ",".join(f'"c{i}"' for i in range(30000))
    source = (
        '{"type":"line","x":{"values":['
        + x
        + ']},"series":[{"name":"a","values":['
        + values
        + ']},{"name":"b","values":['
        + values
        + "]}]}"
    )
    assert len(source) > 100_000
    started = time.perf_counter()
    result = parse_chart(source)
    assert time.perf_counter() - started < 1.0
    assert isinstance(result, ChartError)
    assert result.message == "This chart has 60000 values; the limit is 2000."


def test_module_imports_nothing_from_the_app_or_pillow() -> None:
    tree = ast.parse((ROOT / "the_one" / "visuals" / "chart_spec.py").read_text("utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "json", "math", "dataclasses", "decimal"}


def _imports_of(path: Path) -> list:
    """Every imported module name, with its relative level, from a source file (any depth)."""
    out = []
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.append(("." * node.level) + (node.module or ""))
    return out


def test_every_visuals_module_keeps_to_the_import_rules() -> None:
    """Only ``chart_image.py`` may import PIL, and no module in the package imports anything
    from ``the_one.`` outside ``the_one.visuals`` (M35 F3 L1, AC5)."""
    modules = sorted((ROOT / "the_one" / "visuals").glob("*.py"))
    assert {m.name for m in modules} >= {"__init__.py", "chart_spec.py", "chart_image.py"}
    for module in modules:
        for name in _imports_of(module):
            top = name.split(".")[0]
            if top == "PIL":
                assert module.name == "chart_image.py", f"{module.name} imports {name}"
            assert not name.startswith("."), f"{module.name}: relative import {name}"
            if top == "the_one":
                assert name == "the_one.visuals" or name.startswith("the_one.visuals."), (
                    f"{module.name} imports {name}"
                )


def test_the_visuals_guard_sees_a_forbidden_import(tmp_path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("from the_one.agent import core\nimport PIL\n", encoding="utf-8")
    names = _imports_of(bad)
    assert "the_one.agent" in names and "PIL" in names
