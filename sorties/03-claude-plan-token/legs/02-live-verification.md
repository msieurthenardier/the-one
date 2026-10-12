# Leg: live-verification

**Status**: completed
**Flight**: [Claude Plan (Token) provider](../flight.md)

## Objective
Prove charter criteria 2 and 3 against the live API with the operator's real `setup-token` token, by running `anthropic-plan-token-chat` on a dev instance of the committed branch, then walk the editor with the operator; fix what surfaces.

## Context
- Interactive leg: the Flight Director runs it; no autonomous Developer cycle. Code fixes, if any, go through a Developer spawn and a new commit (no amend), with the fix-vs-feature gate applied out loud.
- Leg 1 committed at `d243eef`.
- DD9: the real token enters the app only through a shell script that reads `~/.config/the-one-hat/plan-token` itself; no agent types, prints or quotes it, and it is never written to a run log or evidence file.

## Inputs
- Branch `sortie/03-claude-plan-token` at `d243eef`, clean tree.
- Leg-start re-verify (flight Prerequisites), done 2026-10-12 before this leg: port 8487 free; token `GET /v1/models` 200, `claude-haiku-4-5` 200, `claude-sonnet-4-6` 429 (unchanged from planning); no `ANTHROPIC_*` in the launching shell; the repo `.env` names `ANTHROPIC_API_KEY`, but pydantic-settings reads `.env` only into `THE_ONE_*` fields and the Makefile does not export it (to confirm from the running process's environ, names only).

## Outputs
- A run log at `tests/behavior/anthropic-plan-token-chat/runs/{ts}.md` (committed; no token, no mask tail).
- Flight log entry; the dev instance stopped and its scratch data directory removed.

## Acceptance Criteria
- [x] AC1: the dev instance runs `d243eef` on port 8487 with a scratch data directory outside the repo; its process environment (names only) has no `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY`; goldfinch reaches `http://127.0.0.1:8487/api/live`.
- [x] AC2: `/mission-control:behavior-test anthropic-plan-token-chat` passes (steps 1-6 PASS; step 7 PASS, or inconclusive only if the plan actually answered on Sonnet, recorded).
- [x] AC3: operator walk: the operator opens the Token provider's editor in the dev instance and confirms the field, help, expiry line and Test result read as intended; any requested change is classified fix or feature out loud and handled per the workflow.
- [x] AC4: after the run, a scan of the repo working tree for the real token finds 0 files; the dev instance is stopped and the scratch directory deleted.

## Verification Steps
- AC1: `ss -ltn`; `/proc/<pid>/environ` names; a goldfinch tab on `/api/live`.
- AC2: the run log's verdicts.
- AC3: the operator's confirmation, recorded in the flight log.
- AC4: `grep -rlF -f <(token) --exclude-dir=.git --exclude-dir=.venv . | wc -l` → 0; `make down` with the same port and data dir; `ls` of the scratch path.

## Implementation Guidance
1. Start: `THE_ONE_PORT=8487 THE_ONE_DATA_DIR=<scratchpad>/sortie03-data make up`.
2. Check AC1.
3. Run the behavior test (the Flight Director invokes the skill; the Executor's shell steps read the token file themselves).
4. Guide the operator through AC3 with a handoff URL minted for their browser.
5. Clean up (AC4), log, commit the run log and artifacts.

## Edge Cases
- **Plan allows Sonnet at run time**: step 7 inconclusive, recorded, not a failure.
- **Usage limit hit mid-run**: record and re-run later; not a product failure.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
