# Flight Log: Extended thinking follows the model

**Flight**: [Extended thinking follows the model](flight.md)

## Summary
Chartered on 2026-11-14 from squawk 0361. The charter was agreed with the operator the same day, with two decisions: new providers only, and adaptive thinking only. Flight design is in progress.

---

## Leg Progress

### Leg 01 thinking-follows-model: landed (2026-11-14)
- Rule `supports_adaptive_thinking`, process-wide `_NO_THINKING_MODELS`, `thinking_active` capability check, in-place strip branch, create-time stamp in `create_provider`, editor default checked on create plus the new help text, model-aware eval record, docs.
- **Thinking-only assistant message (edge case):** after the in-place filter such a message has an empty content list. The thinking-inactive build of the same stored message yields `{"role": "assistant", "content": ""}` (a plain empty string, also not acceptable to the API). Chosen: the strip drops the emptied assistant message entirely (adjacent user messages are accepted by the API and merged), so no empty content is ever sent. Pinned by `test_thinking_only_assistant_message_is_dropped`.
- Existing tests `test_non_thinking_model_error_reraised_unchanged[_stream]` pinned the old behaviour (a "thinking is not supported" 400 re-raised at once); they now give a second 400 and assert the re-raise after the one retry. An autouse fixture in `tests/conftest.py` clears the process-wide set around every test.

---

## Decisions

### 2026-11-14 — charter decisions (operator)
- **New providers only.** A provider saved before this change keeps its stored value; nothing is flipped at startup.
- **Adaptive only.** Models that can think only through the fixed-budget option get no thinking. Budget thinking would be a second cluster of decisions and is out of scope.
- The operator's direction: keep the setting on the provider, on by default, applied only to models that can think, with the label updated.

### 2026-11-14 — Architect design review, cycle 1: approve with changes
Every spot-checked citation held (one correction: the plan types are registered in `anthropic_plan_provider.py`, not `registry.py`). Changes taken into the flight:
- DD2: the strip is in place (pop `thinking`, filter thinking blocks), not a rebuild, which would re-add keys earlier strips removed.
- DD2: the error match is narrow, placed after the temperature branch and fires only while `thinking` is in the request; two other thinking-related 400 texts are negative cases.
- DD2: the app remembers a model id found unable to think per process, not per provider instance, because a provider instance is built per connector message, per web join and per routine run.
- DD1: versions compare as integer tuples; "unparseable is capable" is recorded as load-bearing for about 15 existing tests.
- DD4: the stamp is in the route only (evals create providers through the repository); `null` counts as absent; a type change on PUT stamps nothing; the environment override now reaches only providers with no stored value.
- DD5: the help text is worded by version ("from version 4.6 on"), to match the rule. Two text options with the operator's choice are enough; no mockup is needed for a text-only change.
- DD6: `evals/models.py::effective_values` becomes model-aware.
- Two browser tests in `test_flow_provider_editor.py` are named as rewrites.

Not re-reviewed: the changes refine the decisions and do not restructure the flight. Left for the operator: whether the HAT leg is required (the Architect recommends it, since the real API's error text is pinned from one sample).

---

## Deviations

---

## Anomalies

---

## Session Notes

### 2026-11-14 — qualification
- One outcome: extended thinking works on a mixed-model Claude provider.
- One cluster of decisions: how the app knows a model can think, and what "on by default" means for stored providers.
- One flight: one implementation leg plus an optional HAT.
- No new subsystem: the change is in `AnthropicProvider._build_kwargs` (shared by the three Claude provider types), the provider create route and the provider editor.
- No active mission covers it. Sorties 12 and 13 (both `planning`) do not overlap.

### 2026-11-14 — design approved, sortie ready
- The operator approved wording option A (label "Extended thinking" unchanged; the help text carries the rule).
- The operator confirmed both HAT models are available and that the HAT leg is required.
- Gate re-check: still one cluster of decisions, one implementation leg plus the HAT. Status `planning` → `ready`.

### Flight Director Notes

#### 2026-11-14 — execution start
- Phase file `.flightops/agent-crews/leg-execution.md` loaded and valid (Crew, Interaction Protocol, Prompts).
- Branch `sortie/17-thinking-follows-the-model` created from `main` at `85292a4e`. Flight status `ready` → `in-flight`.
- Two legs: `thinking-follows-model` (autonomous) and `hat-and-alignment` (required, interactive).

#### 2026-11-14 — leg 1 designed, tiered low-risk
`legs/01-thinking-follows-model.md` is `ready`. **Risk tier: low, no per-leg design review.** Rationale: no schema, lifecycle, cache-freshness or security-sensitive change; the one behaviour with existing consumers (the create route now returns `config.thinking_enabled` for Claude types) is additive. The leg adds no decision beyond the flight's, and the Architect checked those same decisions against the code, with file and line, earlier the same day. The process-wide set is new in-memory state, with one writer (the strip) and no staleness concern beyond a restart. The flight-end Reviewer and the Accessibility Reviewer (the editor changes) cover the code.
- Reachability check: "unparseable id is capable" keeps the ~15 existing `claude-test` thinking tests reachable; the evals create providers through the repository, so the route stamp cannot reach them.
- Tests the design breaks are named for rewrite in the leg (two in `test_flow_provider_editor.py`).
- Developer spawned on Sonnet with the "Implement" prompt.

#### 2026-11-14 — leg 1 landed; flight review
- Developer signalled `[LAND:leg]` with all 17 criteria met. Reported gates: `THE_ONE_TEST_NETNS=1 make test-unit` 10221 passed, 15 skipped (the expected netns count); `providers` lane 141 passed; the three static guards 396 passed; `ruff check` and `ruff format --check` clean.
- Falsification, as the Developer reported it (fix removed by editing, then put back): criterion 3 yes; criterion 4 yes (10 tests fail with the strip branch off); criterion 7 yes for the replay-400 case, and the temperature-400 case rests on branch order only (not separately falsified); criterion 10 yes. Not falsified: the id table and edge-id tests, the eval and static tests, `test_create_non_claude_config_untouched`, `test_put_stamps_nothing`, and the browser tests.
- Two existing tests changed meaning and were rewritten in place: `test_non_thinking_model_error_reraised_unchanged` and its stream twin now script two "not supported" 400s and assert the re-raise after the one retry.
- **Reviewer** (Haiku tier: the diff touches no credential, key material, gate, sandbox or self-configuration identity): approve, no blocking issues. It re-ran the `providers` lane (141 passed), the four unit files plus the static guards (793 passed) and ruff. It did not re-run the falsification.
- **Accessibility Reviewer** (Sonnet; the editor's default and help text changed): `[HANDOFF:confirmed]`, no issues, from a static read.
- Non-blocking findings, accepted without a fix pass:
  - The strip matches "thinking" together with "not supported", which a differently worded future 400 could also trip, marking a model as unable to think until restart. Accepted: the app sends only adaptive thinking, so a "not supported" answer about thinking means this model should not be sent it; an exact-sentence match would break on any rewording by the API. The HAT checks the real text. Carried to the debrief.
  - `_CLAUDE_PROVIDER_TYPES` in `api.py` repeats two type literals beside `_PLAN_TOKEN_TYPE`. Cosmetic; carried to the debrief.
- Developer spawned to commit; draft PR to follow.
