"""The evals' measurement and scoring inputs are frozen (Flight 2 DD12). Offline.

Flight 2 changes the platform prompt and re-measures it against ``m30-today``; the
yardstick must not move meanwhile. Content hashes (not git history) pin:

* the scenarios, fixtures and judge files, through a pinned ``scenarios`` fingerprint literal
  (it was ``m30-today``'s until sortie 11 leg 1, then ``s11-platform.json``'s; since the notes
  prompt rewording it is ``notes-platform.json``'s);
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
    # Mission 35 F2 L7 part A2 (2026-11-10): adds reply_has_valid_widget (closed-only, 65536-byte
    # limit, external-URL heuristic) over _top_level_blocks(reply, "widget"); no existing check
    # changes (operator gate 2).
    # Squawk 0345 (2026-11-13): notes_from_untrusted_flagged also traces a save_note whose text
    # arrived as `__positional_args__` (the Ollama recovery shape); no other check changes
    # (operator-approved).
    # Mission 36 F1 L09 part A (2026-11-18, the leg's own scope): checks.py gains
    # reply_links_to_route (with route_problem, a copy of the router's alias rules),
    # no_seeded_secret_in_reply, replies_not_match and RunTrace.seeded_secrets; harness.py the
    # `builder = "gleepglorp"` branch (agent_for, _seed_gleepglorp with its per-run state reset,
    # [app] seeding and cleanup). Additive: no existing check or stored-agent path changes, and
    # the default measure fingerprint and the other sets' scenario fingerprints are pinned
    # unchanged in tests/test_evals_fingerprint.py.
    # Mission 36 F1 L09 part B (2026-11-18, operator-approved: "the reply-extraction fix as an
    # additive opt-in in the frozen evals/checks.py"): TurnTrace gains `skip_empty_reply`
    # (default False; with it unset `reply` is byte-identical), harness.py passes the scenario's
    # `agent.skip_empty_final_reply` to each TurnTrace (one line), and checks.py gains the
    # `claim_needs_call` check. No existing check, scenario outside evals/gleepglorp or stored-agent
    # path changes.
    # M36 F2 Leg 9 (2026-11-19): approve step, proposals trace and checks; `_taint_expected` on
    # is_trusted_result: NOT purely additive, operator approval required. checks.py gains the
    # proposal_made, no_proposal, no_secret_in_proposal, proposals_flagged_if_untrusted and
    # one_open_proposal checks, TurnTrace.step/approve_outcome/proposal_id/open_proposals,
    # RunTrace.proposals and a CheckSpec cross-parameter `validate` hook; harness.py the
    # approve/dismiss steps (apply_proposal with continue_chat=False), the proposals trace, the
    # proposal and created-agent cleanup. The one behaviour change: `_taint_expected` (used only
    # by notes_from_untrusted_flagged) now reads the tool result content through
    # taint.is_trusted_result, so a notes write after a read_app_config result whose first line
    # is the operator-typed mark no longer needs the untrusted flag (it did before: the name
    # alone made every read_app_config outside content). Operator-approved 2026-11-19 after the
    # Reviewer confirmed `_taint_expected` is the only behaviour change.
    # M36 F3 L4 (2026-11-20, operator-approved: both hashes): TurnTrace gains an optional `page`;
    # conversation_messages sets Message.page on a page turn's user message; harness.py passes
    # PageTurn pages to step/TurnContext and records them. Additive: no existing scenario has a
    # page turn, so no existing check or score changes.
    # M36 F3 L7 (2026-11-20, applied by the Flight Director under the operator's ruling that the
    # freeze digests are data integrity): checks.py gains RunTrace.fills and the fill_made,
    # no_fill, no_secret_in_fill, fills_flagged_if_untrusted and says_not_saved checks, sharing
    # bodies with the proposal checks (whose detail strings, extra keys and tests are unchanged);
    # harness.py collects the run's fills (attributed to turns by an id snapshot) and deletes
    # them in _clean_proposal_state. Additive: no existing check or score changes.
    # M36 F4 L6a (FD re-pin, operator ruling 2026-11-20): harness.py seeds [app] providers and
    # honours an explicit [app] MCP/provider id, removes the "provider" row kind, and asserts no
    # eval approves an mcp_server/provider create. Additive: no check or score changes.
    # M36 F4 L6b (FD re-pin, same ruling): checks.py `_view_made` `matches` falls back to the
    # stored changes when the flattened display lacks the field (a kind's rows shown as
    # "Header X"). Unchanged wherever the display carries the field.
    "checks.py": "f441ba82b9a05dd900f255fdeeba76e131d94ff49764c4ae093912f3f34846e6",
    "outcomes.py": "237504b33206c31673cbfc30b20c7ee8c99ddcfe8962ba45e96475a9d1b90ffd",
    "judge.py": "2d341a249779c75a3e2e6ffd880953312b04841b82471909e3c3fae880543916",
    "harness.py": "8219f3e396e04e17579ef4afdafc39f8f094adbacddbf21998be984172d7fdbf",
}
# Sortie 11 leg 2: the scenarios, fixtures and judge fingerprint is pinned by the committed
# `s11-platform.json` baseline (its `fingerprints.scenarios`), no longer a literal. Leg 3 must
# not move it: a changed scenario set needs a same-prompt re-baseline, never a comparison.
# Notes prompt rewording (2026-11-13, operator-approved): notes-as-told is retired and
# notes-stale added, so the pin moves to the re-baselined `notes-platform.json`.
PLATFORM_BASELINE = EVALS / "baselines" / "notes-platform.json"
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


def test_scenarios_fixtures_and_judge_match_the_platform_baseline():
    got = fp.scenarios_fingerprint(EVALS / "scenarios", EVALS / "fixtures", EVALS / "judge")
    pinned = json.loads(PLATFORM_BASELINE.read_text())["fingerprints"]["scenarios"]
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
