"""Scenario loader (DD2, DD9): validation errors and variant expansion. Offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.scenario import ScenarioError, load_scenarios, parse_scenario

BASE = """
id = "demo"
class = "hold"
description = "a demo"

[variants]
phrasings = ["Please {verb} {place}.", "Could you {verb} {place}?"]
facts = [
  {verb = "visit", place = "Lisbon"},
  {verb = "see", place = "Oslo"},
  {verb = "tour", place = "Kyoto"},
]

[[conversations]]
turns = ["{phrasing} Base is {fixture_base}."]

[[checks]]
name = "reply_matches"
pattern = "{place}"
"""


def write(tmp_path: Path, text: str, name: str = "demo.toml") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_variants_expand_distinct_and_substitute(tmp_path):
    sc = parse_scenario(write(tmp_path, BASE))
    variants = sc.variants()
    assert len(variants) == 6
    inst = [sc.instantiate(v, "http://127.0.0.1:9") for v in variants]
    texts = {i.conversations[0][0] for i in inst}
    assert len(texts) == 6  # phrasings x facts: all distinct
    first = inst[0]
    assert first.conversations[0][0] == "Please visit Lisbon. Base is http://127.0.0.1:9."
    assert first.checks[0].params["pattern"] == "Lisbon"
    # fact-set major order: the first n variants cover one fact across phrasings
    assert [v.fact_index for v in variants[:2]] == [0, 0]
    assert [v.phrasing_index for v in variants[:2]] == [0, 1]


def test_fixture_base_substituted_in_check_params(tmp_path):
    text = BASE.replace('pattern = "{place}"', 'pattern = "{fixture_base}/a"')
    sc = parse_scenario(write(tmp_path, text))
    inst = sc.instantiate(sc.variants()[0], "http://127.0.0.1:1234")
    assert inst.checks[0].params["pattern"] == "http://127.0.0.1:1234/a"


def test_regex_quantifier_braces_survive(tmp_path):
    text = BASE.replace('pattern = "{place}"', 'pattern = "a{2}b"')
    sc = parse_scenario(write(tmp_path, text))
    assert sc.instantiate(sc.variants()[0]).checks[0].params["pattern"] == "a{2}b"


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (lambda t: t.replace('name = "reply_matches"', 'name = "no_such_check"'), "unknown check"),
        (lambda t: t.replace('pattern = "{place}"', 'pattern = "(["'), "not a valid regex"),
        (lambda t: t.replace('pattern = "{place}"', "pattern = 5"), "regex string"),
        (lambda t: t.replace('pattern = "{place}"', 'pattern = "x"\nbogus = 1'), "no parameter"),
        (lambda t: t.replace('class = "hold"', 'class = "wrong"'), "class"),
        (lambda t: t + "\n[agent]\nweird = 1\n", "agent.weird"),
        (
            lambda t: t.replace("[variants]", "[clock]\nzone = 'Not/AZone'\n[variants]"),
            "clock.zone",
        ),
    ],
)
def test_one_line_errors_name_file_and_field(tmp_path, mutation, needle):
    path = write(tmp_path, mutation(BASE))
    with pytest.raises(ScenarioError) as ei:
        parse_scenario(path)
    msg = str(ei.value)
    assert "\n" not in msg
    assert msg.startswith("demo.toml:")
    assert needle in msg


def test_seeded_notes_require_notes_enabled(tmp_path):
    text = BASE + '\n[agent]\n[[agent.seeded_notes]]\ntext = "x"\n'
    with pytest.raises(ScenarioError, match=r"demo.toml: agent.seeded_notes: .*notes_enabled"):
        parse_scenario(write(tmp_path, text))
    ok = BASE + '\n[agent]\nnotes_enabled = true\n[[agent.seeded_notes]]\ntext = "x"\n'
    assert parse_scenario(write(tmp_path, ok, "ok.toml")).seeded_notes[0].text == "x"


def test_variant_count_below_n_rejected(tmp_path):
    path = write(tmp_path, BASE)
    assert parse_scenario(path, n=6)
    with pytest.raises(ScenarioError, match=r"demo.toml: variants: n=7 exceeds the 6"):
        parse_scenario(path, n=7)


def test_load_scenarios_filters_and_flags_duplicates(tmp_path):
    write(tmp_path, BASE, "a.toml")
    write(tmp_path, BASE.replace('"demo"', '"other"'), "b.toml")
    assert [s.id for s in load_scenarios(tmp_path)] == ["demo", "other"]
    assert [s.id for s in load_scenarios(tmp_path, ids=["other"])] == ["other"]
    with pytest.raises(ScenarioError, match="unknown scenario"):
        load_scenarios(tmp_path, ids=["nope"])
    write(tmp_path, BASE, "c.toml")
    with pytest.raises(ScenarioError, match="duplicate"):
        load_scenarios(tmp_path)


def test_checks_get_cell_and_class(tmp_path):
    text = BASE + '\n[[checks]]\nname = "search_tools_used"\ncell = "second"\nclass = "safety"\n'
    sc = parse_scenario(write(tmp_path, text))
    decls = sc.instantiate(sc.variants()[0]).checks
    assert [(d.cell, d.klass) for d in decls] == [("demo", "hold"), ("second", "safety")]
    assert sc.cells() == ["demo", "second"]


def test_no_variants_table_means_one_variant(tmp_path):
    text = """
id = "single"
class = "hold"
[[conversations]]
turns = ["hi"]
[[checks]]
name = "search_tools_used"
"""
    sc = parse_scenario(write(tmp_path, text))
    assert len(sc.variants()) == 1


# ── exposed_if (DD6) and the report class (DD7) ───────────────────────────


def test_exposed_if_is_expanded_and_lifted_into_the_decl(tmp_path):
    text = BASE + (
        '\n[[checks]]\nname = "no_note_matches"\npattern = "x"\ncell = "late"\n'
        "exposed_if = '/{place}\\.html$'\n"
    )
    sc = parse_scenario(write(tmp_path, text))
    decls = sc.instantiate(sc.variants()[0]).checks
    assert [d.exposed_if for d in decls] == [None, "/Lisbon\\.html$"]
    assert "exposed_if" not in decls[1].params  # not a parameter of the check itself


def test_exposed_if_must_be_a_non_empty_valid_regex(tmp_path):
    chk = '\n[[checks]]\nname = "no_note_matches"\npattern = "x"\ncell = "late"\n'
    with pytest.raises(ScenarioError, match=r"exposed_if.*valid regex"):
        parse_scenario(write(tmp_path, BASE + chk + "exposed_if = '('\n"))
    with pytest.raises(ScenarioError, match=r"exposed_if: must be a non-empty regex"):
        parse_scenario(write(tmp_path, BASE + chk + "exposed_if = ''\n"))
    with pytest.raises(ScenarioError, match=r"exposed_if: must be a non-empty regex"):
        parse_scenario(write(tmp_path, BASE + chk + "exposed_if = 3\n"))


def test_a_cell_that_mixes_checks_with_and_without_exposed_if_is_refused(tmp_path):
    chk = '\n[[checks]]\nname = "no_note_matches"\npattern = "x"\ncell = "demo"\n'
    with pytest.raises(ScenarioError, match=r"cell 'demo' mixes checks with and without"):
        parse_scenario(write(tmp_path, BASE + chk + "exposed_if = 'a'\n"))
    # two checks in a cell that both carry it, or neither, are fine
    both = (
        BASE.replace('pattern = "{place}"', 'pattern = "{place}"\nexposed_if = "a"')
        + chk
        + "exposed_if = 'b'\n"
    )
    parse_scenario(write(tmp_path, both))


def test_report_is_a_check_class_only(tmp_path):
    chk = '\n[[checks]]\nname = "reply_matches"\npattern = "x"\ncell = "r"\nclass = "report"\n'
    sc = parse_scenario(write(tmp_path, BASE + chk))
    assert sc.cell_classes() == {"demo": "hold", "r": "report"}
    with pytest.raises(ScenarioError, match=r"class: must be one of safety, improve, hold$"):
        parse_scenario(write(tmp_path, BASE.replace('class = "hold"', 'class = "report"', 1)))
    with pytest.raises(ScenarioError, match=r"checks\[1\]\.class.*safety, improve, hold, report"):
        parse_scenario(write(tmp_path, BASE + chk.replace("report", "nonsense")))
