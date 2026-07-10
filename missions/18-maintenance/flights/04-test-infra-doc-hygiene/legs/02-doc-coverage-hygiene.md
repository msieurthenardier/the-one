# Leg: doc-coverage-hygiene

**Status**: completed
**Flight**: [Test-infra & doc hygiene](../flight.md)

## Objective
Clear the small documentation + coverage debts: emit the live-thinking `visibility` field, promote two conventions into `agents.md`, verify the two Mission-16 corrections are in place, and author the two recommended `/behavior-test` specs.

## Context
Maintenance report 2026-07-10 findings **DOC1**, **DOC2**, **T2**, **T3**. The Mission-16 artifact corrections (Leg-09 "dead code" → retained; Windows packaging → resolved) were already applied in the maintenance-report commit (PR #153) — this leg only *verifies* them, doesn't re-do them.

## Inputs
- `the_one/interfaces/web/app.py` (the live thinking broadcast, ~line 1613) + `the_one/db/codec.py` (the replay projection that spreads `visibility`, ~line 381-387 / `vis` at ~332) — the asymmetry.
- `the_one/agents.md` (conventions doc — no existing "rule-of-three" or "seed-before-overlay" section).
- `missions/16-llm-provider-hardening/mission.md` + `mission-debrief.md` (verify the corrections).
- `tests/behavior/` (the behavior-test spec directory) + `.claude/skills/behavior-test/AUTHORING.md` (on the mission-control side) + `.flightops/ARTIFACTS.md` (the spec format).
- Prior specs under `tests/behavior/` as format exemplars (e.g. the F10 thinking / F08 governance specs).

## Acceptance Criteria
- [x] **DOC1** — the live thinking broadcast in `app.py` (~1645-1647) emits a `visibility` field consistent with the replay projection in `codec.py` (~332/380-388, which spreads `{"visibility": msg.visibility}` when non-None). Match the replay shape exactly (same key, same when-None handling). A test asserts the live thinking event carries `visibility` (or its documented absence-when-None) parallel to the replay event. **Timing caveat (design-review [5]):** `tag_post_step_visibility` (`connectors/post_step_metadata.py:57`) sets `msg.visibility` for connector-tagged sessions *after* the step loop, i.e. *after* the live broadcast fires — so for the connector case, the live event will typically still carry no visibility (value doesn't exist yet); full parity is only reached after persistence + rejoin. This is still strictly better than today (correct for non-connector sessions) — document the limitation in a code comment + the flight log so a future reader doesn't mistake "no live visibility on a connector session" for a regression. Low-risk (broadcast-only), closes the F10 action item.
- [x] **DOC2** — two conventions in `the_one/agents.md`. Slot both under a **new `### Mission-specific (M16)` subsection** placed right after `provider-request-param-config-surface (M16 F11)` (mirrors the existing `Mission-specific (M10/M11)` categorization — design-review suggestion):
      (a) **NEW convention — OpenAI-compat mapping "rule-of-three" duplication** (currently code-comment-only): cite both duplicated pairs (F11 `_a4_request_kwargs`/`_v1_a4_kwargs` request-kwargs; F12 `_content_block_to_api` content-blocks) and the "lift at a genuine 3rd `/v1` provider; the conformance parity test is the drift net" rule.
      (b) **EXTRACT existing prose, do NOT author new** (design-review [4]): the seed-before-overlay pattern is **already documented at `agents.md:509-513`** (inside `provider-request-param-config-surface`). Promote it into its own named convention subsection (cross-referenced from `provider-request-param-config-surface`) rather than writing a second description — writing new content would DUPLICATE it (the opposite of doc hygiene).
- [x] **M16 corrections verified** — confirm `mission-16 mission.md` Known Issue (Windows packaging) reads resolved and the criterion-#8 footnote is corrected, and `mission-debrief.md` Leg-09 line reads "conditionally-reachable ... retained." If any is missing/incorrect, fix it; if already correct (expected — done in PR #153), note "verified, no change."
- [x] **T2** — author `tests/behavior/save-preserves-config.md` (spec only, status `draft`): open Admin → set `response_format`+`stop` on a provider via API → edit `reasoning_effort` via the UI editor → Save → re-fetch → assert all keys survive. Follow the ARTIFACTS.md behavior-test spec format + AUTHORING.md guidance (Intent, Preconditions, Observables, Zephyr Action|Expected table, Out of Scope).
- [x] **T3** — author `tests/behavior/vision-round-trip.md` (spec only, status `draft`): attach an image → assert the model's reply is grounded in the image; image-only-no-text; session rejoin no-crash. (Mirror the L08 HAT steps from Flight 12.)
- [x] The behavior-test specs are **authored, NOT run** (running needs live agents + environment + the operator; that's `/behavior-test {slug}` later). No run logs created.
- [x] Any Python touched (DOC1 + its test) passes `make test-unit` with no regression; `ruff check` + `ruff format --check` clean.
- [x] `git diff` limited to `app.py`, the DOC1 test, `agents.md`, `tests/behavior/*.md` (new), + flight artifacts (+ any M16-correction fix if needed).

## Verification Steps
- DOC1 test green; grep the live thinking broadcast for the `visibility` key.
- `agents.md` — the two new convention sections present with the cited symbols.
- The two behavior specs parse as valid markdown tables and match the ARTIFACTS.md format; status `draft`.

## Implementation Guidance
1. **DOC1**: read the `codec.py` replay projection's exact `visibility` handling and mirror it at the `app.py` live broadcast site. Add/extend a test parallel to any existing thinking-event test.
2. **DOC2**: add two clearly-titled convention subsections to `agents.md` near the existing provider conventions, each citing the exact symbols/files.
3. **M16 verify**: read the two M16 files; confirm the corrections; note "verified" in the flight log.
4. **T2/T3**: read `.flightops/ARTIFACTS.md` (behavior-test spec format) + an existing spec — **`tests/behavior/system-provider-config.md` is a strong format exemplar for T2** (design-review). For T3, mine the Flight 12 L08 HAT steps (`missions/16-.../flights/12-message-content-multimodal/legs/08-ingestion-and-vision-hat.md`) as *source material* for the steps (it's a leg, not a spec — don't copy its structure, use the behavior-test format). Keep steps concrete and operator-checkable. Do NOT run them.

## Edge Cases
- DOC1: if `visibility` is `None`, match the replay's when-None handling (omit vs null) exactly — don't introduce a shape divergence in the other direction.
- Behavior specs are drafts — mark status `draft`, `Last Run: never`.

## Files Affected
- `the_one/interfaces/web/app.py`, a test file, `the_one/agents.md`, `tests/behavior/save-preserves-config.md` (new), `tests/behavior/vision-round-trip.md` (new). Possibly M16 artifacts (only if a correction is missing).

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] **Final leg of the mission** — batch-reviewed (confirmed, no blocking; reviewer re-ran the full suite + permutations), committed/PR
