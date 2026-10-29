"""The evals' measurement and scoring inputs are frozen (Flight 2 DD12). Offline.

Flight 2 changes the platform prompt and re-measures it against ``m30-today``; the
yardstick must not move meanwhile. Content hashes (not git history) pin:

* the scenarios, fixtures and judge files, through the baseline's own ``scenarios``
  fingerprint;
* ``evals/measure/`` (the three measured configurations and their KB fixture);
* the scoring modules ``checks.py``, ``outcomes.py``, ``judge.py`` and ``harness.py``.

The digests below are a snapshot taken at the end of Flight 2 leg 1 (evals-readiness).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evals import fingerprint as fp

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"

UPDATE_HINT = (
    "A frozen evals input changed. Flight 2 DD12 forbids that. If the change is deliberate "
    "(a new baseline, a methodology fix approved by the operator), recompute the digest with "
    "`sha256sum <file>` (for evals/measure, the per-file digests in MEASURE_DIGESTS) and "
    "update the constant in tests/test_evals_freeze.py in the same commit, saying why."
)

SCORING_DIGESTS = {
    # Mission 33 F2 L3: checks.py now imports TRUSTED_TOOL_NAMES from the_one.agent.taint (DD7).
    # Mission 33 F2 L4: checks.py gains the routine checks, harness.py the routines_enabled setup
    # (additive; the scenarios under evals/scenarios/ and their scoring are unchanged).
    "checks.py": "80f81a667434c7e93e9eff6c0be6ef04e707e90757218a14603319bc5f7bf395",
    "outcomes.py": "237504b33206c31673cbfc30b20c7ee8c99ddcfe8962ba45e96475a9d1b90ffd",
    "judge.py": "2d341a249779c75a3e2e6ffd880953312b04841b82471909e3c3fae880543916",
    "harness.py": "bfddc9c5e530a892fcaaae27f5b701acfbb00da86f9052b533d1a23bf9200221",
}
MEASURE_DIGESTS = {
    "all-on.toml": "b5a2276d0717896ec1103ba7a2a1e6f2f2927672b27249543818439e1d35f8db",
    "bare.toml": "599799154b0ecc42afe18e414dde5b380469436bf58c286eeb84ce0074d1c7fd",
    "fixtures/kb/measure-kb/readme.md": (
        "b5fea4c94f7040b10d046caa958205518b74f8ca4832bbb82b7d92e44ab8c6d3"
    ),
    # Mission 33 F2 L4: the all-on agent with Routines on (measured beside all-on, not instead).
    "routines-on.toml": "f804cc79de2818da5b04cf3e4310731996c00481dd038e7299d6be7679493c9c",
    "tool-free.toml": "987bc2b1435b3a50a68731a686bf203c7c0a6159c9acde6ee393ff5601274c68",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_scenarios_fixtures_and_judge_match_the_m30_today_fingerprint():
    base = json.loads((EVALS / "baselines" / "m30-today.json").read_text(encoding="utf-8"))
    got = fp.scenarios_fingerprint(EVALS / "scenarios", EVALS / "fixtures", EVALS / "judge")
    assert got == base["fingerprints"]["scenarios"], UPDATE_HINT


def test_the_measure_directory_is_frozen():
    root = EVALS / "measure"
    got = {
        p.relative_to(root).as_posix(): _sha(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert got == MEASURE_DIGESTS, UPDATE_HINT


def test_the_scoring_modules_are_frozen():
    got = {name: _sha(EVALS / name) for name in SCORING_DIGESTS}
    assert got == SCORING_DIGESTS, UPDATE_HINT
