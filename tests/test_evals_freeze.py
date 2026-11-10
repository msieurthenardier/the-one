"""The evals' measurement and scoring inputs are frozen (Flight 2 DD12). Offline.

Flight 2 changes the platform prompt and re-measures it against ``m30-today``; the
yardstick must not move meanwhile. Content hashes (not git history) pin:

* the scenarios, fixtures and judge files, through a pinned ``scenarios`` fingerprint literal
  (it was ``m30-today``'s until sortie 11 leg 1; since leg 2 it is ``s11-platform.json``'s);
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
    # Mission 33 F3 L4: harness.py maps the stored calendar recurrence back to the kind name
    # the routine checks read; the scenarios and their scoring are unchanged.
    # Mission 33 F4 L07: that helper is renamed `_schedule_class` (an output classification, not
    # input support); no behaviour change.
    # Mission 33 F4 L02: routines lose their target, so checks.py drops the `target` param and
    # RoutineView/RunTrace target fields, and harness.py drops the chat-row setup and target copies
    # (routine scenarios only; the evals/scenarios/ scoring is unchanged).
    # Sortie 11 leg 1: the fixture hostname and self-test, the not-exposed state, the report
    # class and claim check, the exposure record (operator-approved methodology change, DD10).
    # checks.py gains exposed_if, the tri-state CheckResult and claims_match_actions; harness.py
    # the hostname rewrite, the nonce self-test and the registry/exposure capture.
    # Mission 35 F1 L4: reply_has_valid_chart and the rich_visuals agent key (operator-approved,
    # DD13); the scenarios under evals/scenarios/ and their scoring are unchanged.
    # Mission 35 F2 L7 part A1 (2026-11-09): _chart_blocks becomes the tag-parametrised
    # _top_level_blocks(reply, tag) returning (body, closed) pairs; reply_has_valid_chart is
    # unchanged in behaviour (operator-approved at gate 1).
    "checks.py": "bff22d36c2ea4c8981110a3b89e2cc2141fef8751fda919b854af41212f64297",
    "outcomes.py": "237504b33206c31673cbfc30b20c7ee8c99ddcfe8962ba45e96475a9d1b90ffd",
    "judge.py": "2d341a249779c75a3e2e6ffd880953312b04841b82471909e3c3fae880543916",
    "harness.py": "6b4e4b96ccb2a983313ea40f7195866d3ad3680e0f5b2d7969e79aefe05ce735",
}
# Sortie 11 leg 2: the scenarios, fixtures and judge fingerprint is pinned by the committed
# `s11-platform.json` baseline (its `fingerprints.scenarios`), no longer a literal. Leg 3 must
# not move it: a changed scenario set needs a same-prompt re-baseline, never a comparison.
S11_PLATFORM = EVALS / "baselines" / "s11-platform.json"
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


def test_scenarios_fixtures_and_judge_match_the_s11_platform_baseline():
    got = fp.scenarios_fingerprint(EVALS / "scenarios", EVALS / "fixtures", EVALS / "judge")
    pinned = json.loads(S11_PLATFORM.read_text())["fingerprints"]["scenarios"]
    assert got == pinned, UPDATE_HINT


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
