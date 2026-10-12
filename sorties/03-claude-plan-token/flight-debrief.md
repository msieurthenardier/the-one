# Flight Debrief: Claude Plan (Token) provider

**Date**: 2026-10-12
**Flight**: [Claude Plan (Token) provider](flight.md)
**Status**: completed
**Duration**: 2026-10-12 (planned, executed and landed the same day)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
A second Claude-subscription provider type, `anthropic-plan-token` ("Claude Plan (Token)"), authenticates with a token pasted from `claude setup-token`. The OAuth type is relabelled "Claude Plan (OAuth)". The request path is the OAuth type's bearer path, reused unchanged through a 15-line subclass. The rest of the work:
- **Schema:** the v44 `llm_providers` rebuild (secrets preserved byte for byte).
- **API:** the create/update rules, including the type-change rules, the server-owned `token_set_at` stamp, and `/test` and `/models`.
- **Editor:** the Token field, the help line and the "expires around" line with ok/soon/past states.
- **Error text:** a readable refusal for the plan's bare `429 "Error"` on both plan types, and a rejected-token message (401) for the token type.

Leg 1 landed in one build pass (`d243eef`). Leg 2 proved it live with the operator's real token (`92a9121`). PR #271.

### Charter Criteria (sortie)
| Criterion | Met? | Note |
|---|---|---|
| Add flow offers both types; Token asks only for the token; editor shows added/expires-around | Met | Browser tests (providers lane) plus the operator walk; live step 3 |
| An agent on a Token provider completes a streamed chat turn live with a real token | Met | Live step 5 "PONG" in 1.3 s; step 6, 602 words streamed over 9.9 s, growing at every sample |
| Test and the model picker work with that token | Met | Live step 3 "Connected to Anthropic (plan token)"; step 4, 14 models listed |
| Token stored encrypted, never returned unmasked; OAuth rows survive the migration | Met | Unit (response-body scans, v44 secrets bytes); live steps 1-3 (booleans-only checks) |

Charter amendment (operator, planning): the OAuth type also gets the DD10 refusal text. It is otherwise unchanged.

## What Went Well
- **The live premise probe at planning** was the sortie's best decision. Two raw HTTP calls, reading the token from a file and printing status codes only, settled three things before any code existed:
  - that `models.list()` works as the `/test` probe;
  - that the request path is reuse, not new;
  - that the plan returns a bare 429 for every model except Haiku 4.5. That finding became DD10.

  The same probe was re-run at leg 2 start.
- **The design reviews caught every real defect before any code was written.** Architect cycle 1 found:
  - a false claim that an edit-mode Save re-mounts the editor;
  - the stamp being wiped on every save;
  - the DD1/DD10 wrapper contradiction.

  Cycle 2 found that "resolved" was unspecified and that a token could be left behind under the OAuth type. The leg-1 review found that masked-key resolution erases the "fresh token" signal, which led to `fresh_key_supplied`. After all that, code review found nothing blocking, in one cycle.
- **Token secrecy held end to end.** The token entered the app only through a script that read the file. Every behavior-test check printed booleans. The Executor redacted the masked value Playwright's accessibility snapshot exposes. Final scans found the token in 0 repo files and 0 of 50 evidence files.
- **Falsification of the refresh-after-Save browser test.** The Developer removed `renderTokenExpiry` from `performSave` and saw the test fail, which proves the test guards the stale-closure bug cycle 1 found.
- **The live behavior test ran 7/7 in about 13 minutes** in live mode (one Executor, one Validator). It produced the strongest evidence in the sortie, including in-flight screenshots of a growing reply.
- **The mid-leg checkpoint** (unit tier green after the backend, before the editor) gave a 38-file, high-risk leg a cheap rollback point: 6016 passed after the backend, 6019 at the end.

## What Could Be Improved

### Process
- **A fresh scratch data dir has no `api-credential` after `make up`.** `get_credential()` is create-on-first-use (`the_one/api_credential.py`), and a host-native server does not create the file at startup. CLAUDE.md's behavior-test convention says "it creates the file on first launch", which is wrong for a `make up` instance. Leg 2 had to run `rotate-api-credential` and restart. Every future live leg on a scratch dir will hit this.
- **Sortie 02 fallout surfaced only here**: `make verify-serving` still checks moved files (squawk 0193), and the testid registry's provider Test-button rows are stale (squawk 0194). A flight that moves or deletes static JS should grep the Makefile, scripts and the registry for the old paths.

### Technical
- **`api.py` `/test` and `/models` repeat per-type branches.** The Anthropic "live `models.list()`, map, fall back to the static catalog" block now exists three times (`anthropic`, `anthropic-plan`, `anthropic-plan-token`), and each route has 8 type branches. Before the next provider type, extract helpers or a per-type strategy.
- **Adding a provider type touches about 20 places**, made safe by the consistency tests but not cheap. One of those places is a full `llm_providers` rebuild, because SQLite's `CHECK (type IN …)` cannot be altered (v6, v12, v33, v44). App-level validation (`PROVIDER_TYPES` plus the Literal) already guards writes, so dropping the CHECK in one final rebuild would remove a migration from every future provider sortie. The labels, `BADGE_KINDS` and `KNOWN_BADGE_TYPES` could also derive from one table.
- **`update_provider` grew a type-specific state table inline**: the type change in or out, crossed with a fresh, masked or omitted key, crossed with stamp presence. It is correct and tested, but a pure `_resolve_type_secrets(existing, updated, fresh_key_supplied)` helper would make the matrix unit-testable without HTTP. Two related changes need recording:
  - `update_provider` now ignores every client-sent `secrets` key, for all types. That is safe today, but it was decided inside the leg; it should be stated as an API contract.
  - The pin and stamp run on `updated` after `model_validate`, through `model_copy`. That is safe only because the override values are already validated (documented in `agents.md`).
- **The chat's generic "Agent error: " prefix** (`interfaces/web/app.py`) wraps errors written for the user: `PlanRequestRefusedError`, `PlanTokenRejectedError`, `PlanTokenMissingError` and `ReauthRequiredError`. The live spec had to loosen "beginning" to "contains". A shared base class (e.g. `UserFacingProviderError`) would let the chat show them plainly.
- **Small debt:**
  - `PLAN_TOKEN_LIFETIME_DAYS` lives in `anthropic_oauth.py` (`api.py` needs it without the SDK). Its re-export from `anthropic_plan_provider.py` has no consumer.
  - `App.time.formatDate` is a third month-name formatter, beside `rules-notes-tab.js:526` and `chats-list.js:58`.
  - The new messages write "Library > Model providers" with an ASCII `>`, while the UI uses "›".
  - The expiry line does not re-render on `App.time.onChange`. It is day-granular, so the impact is low.
  - The `.admin-pf-*` class prefix carries on (accepted naming debt since sortie 02).
- **The SDK exception shape is pinned only by hand-built bodies.** The DD10/401 translation reads `exc.body`. The unit tests construct the body by hand, so an SDK shape change would pass CI and fail live. One test that builds the real SDK `RateLimitError`/`AuthenticationError` from an `httpx.Response` would close that gap.

### Documentation
- CLAUDE.md's credential-file claim (above).
- `ReauthRequiredError` still says "Administration" (squawk 0188, open).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| A planning-time live probe with the real credential (status codes only) | Settled the `/test` probe, the reuse premise and the 429 block before design was locked | Yes: for any flight whose premise depends on an external account's behaviour |
| DD10 added mid-planning (plan error translation for both types) | The probe found the bare 429; the operator chose a clearer error | No (case-specific) |
| `fresh_key_supplied` captured from the raw body | Masked-key resolution erases the masked-vs-fresh signal before validation | Yes: read request intent before any normalising step |
| `PLAN_TOKEN_LIFETIME_DAYS` placed in `anthropic_oauth.py` | `api.py` imports the SDK lazily and needs the constant at module level | No: move to an SDK-free plan-constants module if another constant appears |
| New testid `provider-api-key-help` | The help line needed a stable hook | No (minor; registered) |
| Step 4 used the dated `claude-haiku-4-5-20251001` | The live list has no bare alias | Yes: specs naming models accept dated ids (spec updated) |
| Behavior-test browser apparatus: Playwright, not goldfinch | The project crew file sets Playwright as the default until goldfinch input delivery is verified; the FD's run context had named goldfinch | Yes: the FD reads the crew file before naming an apparatus |
| `make up` needed a credential mint and restart on a fresh scratch dir | The credential is created on first use; the server does not create it at startup | Yes: add "credential file exists" to the dev-instance precondition, or fix startup |

## Key Learnings
- **Anthropic's plan-token restrictions are external, undocumented and change-prone.** Here only `claude-haiku-4-5` ran, and every Sonnet, Opus and Haiku 5.5 model tried got a bare 429. DD10 matches on `message == "Error"` and degrades safely. Any future plan work should repeat the live probe at leg start, as this sortie did.
- **On plan providers, new agents default to a model the plan refuses** (`claude-haiku-5-5`, the first listed). The refusal is now explained, but the agent fails on its first turn until its model is changed. The operator chose to note it as a known limitation, with no follow-up planned.
- **The agent editor can save an empty `llm_model`** (pre-existing on `main`). A keyboard selection during the Model select's async rebuild left `""`, Save accepted it, and the editor then showed a model that is not stored. It fails the squawk gate on design (is an empty model legal? `AgentConfig.llm_model` defaults to `""`). If it is picked up, it needs a sortie.
- **Booleans-only secret checks work in behavior tests.** They pair with an Orchestrator scan of the evidence directory at close. The one leak path found was Playwright's accessibility snapshot of a password input, which exposes the app's mask (`***` plus the last four characters).
- **Test metrics:**
  - **Unit:** 6019 passed, 12 skipped (expected), 194.8 s. Sortie 02 had 5953 passed / 12 skipped, so this flight added 66 unit tests; the time is flat.
  - **Gate:** `rc=0 total=1023s`, all nine lanes passing, no flakes (0168 and 0171 absent). Sortie 02's gate was 939 s (+84 s, +9%).
  - **Lane changes:** `providers` 217 → 260 s (+43 s, the new 8-test `test_flow_provider_plan_token.py`); `contracts` +11 s (`formatDate` cases); `settings` 227 → 260 s (+33 s, not explained by this diff; likely host variance).
  - **Budget risk:** `agents` is at **506/510 s** (4 s headroom), the gate's main risk. Re-measure and re-budget it before the next agent-editor flight.

## Methodology Observations
- **Subagent hand-backs in live behavior-test mode (behavior-test skill, Phase 4, plugin 1.2.0).**
  - **What happened:** after every step, each live agent produced a harness-required "final" hand-back. These arrived after (and duplicated) its SendMessage report, so the Orchestrator received two messages per step per agent and had to recognise each stale one.
  - **Expected:** one report per step.
  - **Cost:** no rework, but about 14 extra notifications in a 7-step run, each needing a "stale, waiting" reply. That is noise for the operator watching.
  - **Recorded, not judged:** it may be the harness's async-agent behaviour rather than the skill's.
- **The FD's behavior-test run context named the wrong apparatus (agentic-workflow → behavior-test hand-off, plugin 1.2.0).**
  - **What happened:** the Flight Director's skill arguments named goldfinch, while the project crew file makes Playwright the default until goldfinch input delivery is verified.
  - **Caught by:** the FD before spawning, and the Executor followed the crew file.
  - **Cost:** none, but a sentence of correction.
  - **Suggestion:** the behavior-test skill could tell the Orchestrator to take the apparatus from the crew file, not from the spec or the caller.
- **The sortie gate worked as designed (sortie skill, plan verb, plugin 1.2.0).** Qualification passed on all four criteria. Re-checking the gate after design caught nothing new: DD10 joined the same token-error cluster, and there were 2 legs. Two Architect cycles plus a leg design review were heavy for a sortie, but each found real defects, and the operator reported no friction.
- **The leg protocol for a HAT-style live leg (agentic-workflow, Phase 2b, plugin 1.2.0).** The interactive-leg path (no Developer/Reviewer, FD-guided, the behavior test invoked directly) fitted well. Out-of-scope findings were routed correctly: two squawks; one defect that failed the squawk gate on design, recorded as a recommendation; one feature idea, recorded as a known limitation.

## Recommendations
1. **Fix the dev-instance credential gap.** Make the host-native server create `<data_dir>/api-credential` at startup, or correct CLAUDE.md's behavior-test convention and add "credential file exists" to the standard dev-instance precondition. Every live leg on a scratch dir hits this today.
2. **Re-budget the `agents` lane** (506/510 s) from a fresh `--parallel 3` measurement, before the next flight that adds agent-editor browser tests.
3. **Before the next provider type**, run a maintenance flight that factors the Anthropic `/test` and `/models` branches into helpers. Decide there whether to drop the `llm_providers` `CHECK` (removing a rebuild from every future type) and whether to derive the type labels and badge lists from one table.
4. **Introduce a user-facing provider error base class** so the chat stops prefixing plan refusals, re-auth and token errors with "Agent error: ".
5. **Pin the SDK exception shape** with one test that builds a real `anthropic.RateLimitError`/`AuthenticationError` from an `httpx.Response`, so an SDK change to `exc.body` fails CI, not production.

## Action Items
- [ ] Operator: revoke the test `setup-token` token and delete `~/.config/the-one-hat/plan-token` (flight completion checklist).
- [ ] Complete squawks 0193 and 0194 (deferred, batch together).
- [x] Squawk candidates from this debrief (Phase 6), logged with the operator's approval, deferred: **0195** (CLAUDE.md credential-file claim / no credential at startup), **0196** (expiry line ignores `App.time.onChange`), **0197** (unused `PLAN_TOKEN_LIFETIME_DAYS` re-export). Fold the "Library > Model providers" ASCII `>` into squawk 0188 when it is completed (same plan-error copy).
- [ ] Recommendations 1-5 above, as maintenance or a sortie.
- [ ] Known limitations, no follow-up planned (operator): the plan-provider default model; the pre-existing empty-`llm_model` save (needs a sortie if picked up).
