"""``--prompt-file``: candidate GleepGlorp prompts for screening (M36 F1 L09 part B). Offline."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import run

from evals import prompt_file as pf
from evals import scripted, tokens
from the_one.gleepglorp import prompt as gp

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir

GG_DIR = Path(__file__).resolve().parent.parent / "evals" / "gleepglorp"
SCENARIOS = GG_DIR / "scenarios"
V1 = GG_DIR / "prompts" / "v1.toml"
MARK = "CANDIDATE-MARK-7731"


def candidate(tmp_path: Path, *, extra: str = "", scope_suffix: str = f" {MARK}") -> Path:
    data = tomllib.loads(V1.read_text(encoding="utf-8"))
    data["scope"] += scope_suffix
    body = "".join(f"{k} = {json.dumps(v)}\n" for k, v in data.items()) + extra
    path = tmp_path / "cand.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_v1_reproduces_the_shipped_prompt_byte_for_byte() -> None:
    sections = pf.load_sections(V1)
    with gp.override_sections(sections):
        capable = gp.base_prompt(tools=True)
        free = gp.base_prompt(tools=False)
        assert gp.compose(date_line="D") == capable + "\n\nD"
    assert capable == gp.base_prompt(tools=True)
    assert free == gp.base_prompt(tools=False)
    assert capable == "\n\n".join(
        [gp.IDENTITY, gp.SCOPE, gp.LIMITS, gp.SECRETS, gp.ANSWERING_TOOLS, gp.LINKS, gp.STYLE]
    )
    assert sections == {k: getattr(gp, k) for k in gp.SECTION_KEYS}


def test_the_override_applies_and_is_restored() -> None:
    before = gp.base_prompt()
    sections = {**gp.active_sections(), "SCOPE": "Changed scope."}
    with gp.override_sections(sections):
        assert "Changed scope." in gp.base_prompt()
    assert gp.base_prompt() == before


def test_web_off_variant_is_expressible_and_only_a_candidate_feature() -> None:
    sections = {**gp.active_sections(), "WEB_OFF_ANSWERING": "No web here."}
    assert gp.base_prompt(web=False) == gp.base_prompt()  # the shipped text has no variant
    with gp.override_sections(sections):
        assert "No web here." in gp.base_prompt(web=False)
        assert "No web here." not in gp.base_prompt(web=True)
        assert "No web here." not in gp.base_prompt(tools=False, web=False)


def test_a_bad_candidate_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('identity = "x"\nbogus = "y"\n', encoding="utf-8")
    with pytest.raises(pf.PromptFileError, match="missing sections"):
        pf.load_sections(bad)


def test_the_digest_follows_the_text(tmp_path: Path) -> None:
    a = candidate(tmp_path)
    d1 = pf.digest(a)
    assert pf.digest(a) == d1
    assert pf.digest(candidate(tmp_path, scope_suffix=" other")) != d1


def test_run_and_measure_prompt_take_a_prompt_file() -> None:
    from evals.__main__ import build_parser

    p = build_parser()
    assert p.parse_args(["run", "--prompt-file", "c.toml"]).prompt_file == Path("c.toml")
    assert p.parse_args(["measure-prompt", "--prompt-file", "c.toml"]).prompt_file == Path("c.toml")
    assert p.parse_args(["run"]).prompt_file is None


async def test_a_run_sees_the_candidate_text_and_the_override_is_restored(
    evals_isolation,
):
    tmp = evals_isolation
    cand = candidate(tmp)
    shipped = gp.base_prompt()
    code, run_dir = await run(
        tmp,
        SCENARIOS,
        h.script_hook(scripted.text("I can only help with this app.")),
        n=1,
        scenarios=["off-topic"],
        prompt_file=cand,
    )
    assert code == 0
    files = sorted((run_dir / "transcripts").glob("*.json"))
    assert files
    systems = json.loads(files[0].read_text())["system_prompts"]
    assert systems and all(MARK in s for s in systems)
    assert MARK not in gp.base_prompt() and gp.base_prompt() == shipped
    assert json.loads((run_dir / "prompt-file.json").read_text())["name"] == "cand"


async def test_the_candidate_is_refused_without_the_builder(evals_isolation):
    tmp = evals_isolation
    cand = candidate(tmp)
    from evals.runner import run_invocation

    plain = Path(__file__).resolve().parent.parent / "evals" / "scenarios"
    o = h.opts(tmp, plain, prompt_file=cand, dry_run=True)
    assert await run_invocation(o, h.hooks(), out=lambda s: None) == 2
    assert MARK not in gp.base_prompt()


async def test_the_fingerprint_follows_the_candidate_and_a_resume_refuses_a_change(
    evals_isolation,
):
    tmp = evals_isolation
    a = candidate(tmp)

    async def measured(path: Path | None, name: str) -> str:
        opts = tokens.MeasureOptions(
            counter=tokens.StandInCounter(),
            run_dir=tmp / name,
            measure_dir=GG_DIR / "measure",
            prompt_file=path,
        )
        return (await tokens.measure_prompt(opts))["fingerprints"]["prompt"]

    shipped = await measured(None, "m0")
    v1 = await measured(V1, "m1")
    cand = await measured(a, "m2")
    assert v1 == shipped  # v1 is the shipped prompt
    assert cand != shipped
    assert await measured(a, "m3") == cand
    assert MARK not in gp.base_prompt()

    # a resume with a different candidate is refused
    hook = h.script_hook(scripted.text("I can only help with this app."))
    code, run_dir = await run(tmp, SCENARIOS, hook, n=1, scenarios=["off-topic"], prompt_file=a)
    assert code == 0
    b = candidate(tmp, scope_suffix=" a different candidate")
    o = h.opts(tmp, SCENARIOS, scenarios=["off-topic"], run_dir=None, resume=run_dir, prompt_file=b)
    from evals.runner import run_invocation

    assert await run_invocation(o, h.hooks(hook), out=lambda s: None) == 2
