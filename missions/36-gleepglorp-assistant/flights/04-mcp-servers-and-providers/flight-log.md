# Flight Log: MCP servers and model providers

**Flight**: [MCP servers and model providers](flight.md)

## Summary

Planning 2026-11-21, from `main` at `9597b0f4`. Flight 3 (#382) and the
2026-11-21 squawk turnaround (#383) are merged.

## Reconnaissance Report

**Sources:**
- the Flight 3 debrief's recommendations and action items;
- the Flight 2 refactor debt it carried;
- the Flight 3 log's carried items;
- open squawks 0398 and 0399.

Each item was walked against `9597b0f4`.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `ApplyError` protocol | confirmed-live | `proposals/apply.py:137-251`: isinstance chains, no `ApplyError` class | This flight, DD3, Leg 1 |
| Split `shape.py` by kind | confirmed-live | `shape.py` 620 lines; `normalize` if/else `:426-433` | This flight, DD2, Leg 1 |
| Per-kind card, follow and fill registries | confirmed-live | `approvals.js:29,52`; `agent-editor-fill.js:46` `ALLOWED`; drawer `fill.js` agent-only routing | This flight, DD11, Leg 2 |
| Shared fill and proposal plumbing (debrief rec. 1) | confirmed-live | `fill/store.py` 291 and `proposals/store.py` 386; two `events.py`; `fill-receipts.js` and `proposal-cards.js` fold separately | This flight, DD11, Legs 1-2 |
| Route or page id in the page line (rec. 2) | confirmed-live | `page.py:161` `build_line`: labels only | This flight, DD6, Leg 1 |
| Deterministic guard on links and commands (rec. 3) | confirmed-live | `proposals/guard.py:101` checks keys and stored secrets only | This flight, DD7, Leg 3 |
| Grep registries and pins at leg design (rec. 4) | confirmed-live | no such item in `.flightops/agent-crews/leg-execution.md` | Applied as FD practice (DD14); the `.flightops` file change stays with the operator |
| Prompt at its cap; grow through tools (rec. 5) | confirmed-live | `p4c` is 550 of 550 | This flight, DD12 |
| Quiet-host gate and re-budget (squawk 0389 note) | confirmed-live | owed since M36 F1; F3 gate loaded (5-7) | This flight, DD15, closing leg; no fourth deferral |
| Re-slice `shared` | confirmed-live | `run-tests.sh:87` `[shared]=420`; F3 reading 683 s | This flight, DD14, Leg 1 |
| Squawk 0391 (type ignores) | already-satisfied | `5e5a388f` (PR #383): the five ignores removed | Retire from this flight |
| Squawk 0392 (proposal lifecycle) | already-satisfied | `the_one/agents.md` "Proposal lifecycle (M36 F2)" (PR #383) | Retire |
| Squawk 0393 (Windows test-copy root) | already-satisfied | `the_one/agents.md` "Windows test copy" bullet (PR #383) | Retire |
| Squawks 0394, 0395, 0396, 0397 | already-satisfied | PR #383 | Retire |
| Squawk 0398 (stale `CLAUDE.md` citations) | confirmed-live | `the_one/mcp/README.md:15/354/398/491`, `mcp/__init__.py:8`, `self_configuration/credentials.py:42`, `db/schema.py:798` | This flight, Leg 4 (the MCP package) |
| Squawk 0399 (behavior specs on 8485) | confirmed-live | 9 specs in `tests/behavior/` | This flight, Leg 8, beside the new spec |
| "Who uses a provider" helper (F1, carried by F3's log to "provider proposals") | already-satisfied | `api.py:list_provider_agents` (GET /api/providers/{id}/agents), `AgentStore.list_by_provider` used by `view_library.py:46` (found by the Architect, cycle 1) | Retire |
| The two notes tables decision (F1) | confirmed-live | `gleepglorp_notes` beside agent notes | Not on this flight's path; carried |

## Flight Director Notes

- **2026-11-21, planning.** A read-only survey of the seven remaining kinds
  ran before the spec. It covered write routes, inline validation, secret
  fields, editor seams and pushes. Findings:
  - **No kind has a write service.** Validation and side effects live in the
    routes.
  - **No library editor exports fill handles or follows `config_changed`.**
  - **Two lower layers lock out new kinds:** the proposal kind CHECK and the
    fills' `agent_name NOT NULL`.
  - **No code-level guard against links or commands.**
  - **MCP servers, providers, knowledge bases and connectors have non-unique
    names.**
  - **Sign-in needs a saved row:** MCP OAuth and the Anthropic plan.
  - **The date and time page saves on choice,** so it can only take
    proposals (Flight 5).
- **Operator decisions (2026-11-21):**
  - Split the mission's Flight 4 after MCP servers and providers; the other
    five kinds go to Flight 5, and alignment to Flight 6.
  - GleepGlorp may set commands and URLs, behind a code-level block on
    outside values.
  - Values typed by the operator, and values from a page whose address the
    operator typed, count as the operator's.
  - A drawer request for another item opens that editor and fills it.
  - A HAT closes the flight.
- **FD scoping calls:**
  - Squawks 0398 and 0399 ride this flight, on shared surfaces.
  - No desktop-webview leg: no new shell, socket or engine behaviour.
  - The `.flightops` checklist change (rec. 4) is left to the operator.
- **2026-11-21, design review cycle 1** (Architect, Opus). The verdict was
  approve with changes. The findings, all folded in:
  - **High:**
    - DD7 as first agreed did not close the 1-in-12 residual, because the
      planted pages are operator-linked.
    - `p4c`'s no-copy line forbids the headline case.
    - The MCP and provider repositories lack the `precheck`/`on_commit` hooks
      the proposal lifecycle needs.
    - The `propose_change` description pins cannot hold every field of the
      new kinds.
  - **Medium:**
    - DD6 changes the eval page lines, and the route must come from the
      server's resolution, not client text.
    - DD7 named the wrong fetch tool (`web_fetch`; it is `fetch_url`) and
      had no matching rules
      (markdownify escapes, URL normalisation, token boundaries), and it did
      not exclude marked USER messages.
    - DD4 did not follow the project's conventions (`CURRENT_VERSION`, the
      `executescript` ceremony, replay shape detection). The kind CHECK is
      dropped, not widened.
    - DD9 needs nested paths, a per-row merge, the Sensitive rule, `cwd`
      operator-only and the runtime dropdown mapping.
    - DD10 needs type changes handled and a server-side defaults table.
    - `guard.check` false positives on commands and URLs.
  - **Low:**
    - DD3 keeps the re-raise;
    - an import-cycle-safe registry layout;
    - the lane is `chats-transcript`, not `chats`;
    - the prerequisite re-verifies moved to Legs 7 and 8;
    - the key-value note and dict card rows put to the operator as a mockup.
  - **Suggestions taken:**
    - Leg 1 split into 1a (refactor) and 1b (schema, targets, route, lane);
    - squawk 0398's `schema.py` comment moved to 1b;
    - ids resolved before names;
    - operator-typed `read_app_config` text as a tier-2 source;
    - a loader-key denylist;
    - URL-move warnings;
    - per-kind `operator_only`.
- **Operator decisions after cycle 1 (2026-11-21):**
  - narrow the linked-page rule to declared address and command fields;
  - a raw README from the same GitHub repo counts;
  - provider type changes allowed with a warning;
  - one note under a key-value table.
- **FD calls after cycle 1:**
  - env and header rows merge per row;
  - attachment text counts as a linked page;
  - `fill_form` description pin at 90 tokens.
- **2026-11-21, design review cycle 2** (Architect, Opus; the last cycle
  under the two-cycle cap). Verdict: approve with changes. The cycle-1
  fixes held, apart from two partial ones. Everything was folded in by the
  FD with no third review: the remaining items were text contradictions and
  missing specifics, none a new design direction.
  - **High:** DD7 contradicted itself on loader keys (tier 2 admitted them),
    and the denylist missed the package-redirect keys (`npm_config_*`,
    `PIP_INDEX_URL`, `PATH`, `*_PROXY`, …). Fixed: a loader key and its value
    must both be tier 1, matched by prefix patterns.
  - **Medium:**
    - There is no attachment-text source (attachments are images only).
    - The operator-typed `read_app_config` source cannot work (the MCP views
      always carry outside paths), so it is dropped and listed as a gap.
    - The change services now follow `change_agent`'s retry rule and re-pin
      `_cache` and the OAuth secrets inside the transaction.
    - `FieldSpec.stored` stays the string key, with a `path` added; headers
      and env are row-typed fields.
    - Leg 1a re-pins the `evals/harness.py` freeze digest.
    - A provider key never follows a type change to another key-taking type
      (refused for proposals; cleared on fills).
    - `SECURITY-MODEL.md` and `evals/README.md` are in the docs.
    - Sensitive rows never appear on proposal cards.
    - The `Kind` interface is aligned with the later decisions.
    - The full `shape` re-export list and the patched tests are known.
    - `read_app_config` gets the id-then-name rule.
  - **Low:**
    - free-text must-pass cases;
    - a `command`/`args` warning;
    - more registries listed;
    - DD6 Settings routes and over-cap routes;
    - URL and GitHub matching details;
    - fill warnings go in the reply, not on the receipt, so there is no new
      placement;
    - text errors.
  - **Suggestions taken:**
    - character caps beside the token pins;
    - reuse of `mcp-editor-shared.js`'s runtime collapse;
    - refusals name their source page;
    - Leg 8 prerequisites for GitHub and Web access;
    - a Divert criterion for the 550-token cap;
    - the sandbox-network note for `npx`/`pipx` servers.
  - **FD calls in this cycle** (within the operator's "allow with a warning"
    on provider types):
    - a proposal moving a provider between key-taking types is refused with
      a handoff;
    - a fill clears the key field instead;
    - moving into `anthropic-plan` or a keyless type, or out of
      `anthropic-plan`, is allowed with a warning;
    - an MCP type change writes the editor's Save body;
    - the Leg 7 order (old set first, then candidates, then the
      re-baseline).
- **Why the quiet-host gate runs last, not first** (the debrief recommended
  first): Leg 1b re-slices the lanes and Legs 2-5 add browser files, so a
  first-day reading would be stale by landing.
- **2026-11-21, execution start** (`/mission-control:agentic-workflow flight
  04 mission 36`, operator). The flight moved ready → in-flight.
  - **Crew file:** `.flightops/agent-crews/leg-execution.md`. Developer on
    Sonnet. The Reviewer is on Sonnet (security tier), because the batches
    touch the secret guard, credential-bearing services and the outside-value
    guard. The Accessibility Reviewer (Sonnet) joins any batch with UI
    changes.
  - **Batch plan** (the batch-mode protocol). Each batch ends in a review and
    a checkpoint commit:
    - **A:** Legs 1a, 1b, 2 and 3, the groundwork and the guard;
    - **B:** Legs 4 and 5, the kinds;
    - **C:** Leg 6, eval setup, reviewed and committed before any quota;
    - **then:** Leg 7 (rounds) and Leg 8 (the HAT and the gate).
- **Leg 1a design** (`legs/01a-kind-registry.md`). **Risk tier: high,**
  because it changes a shared module with many consumers (the proposal and
  fill tools, the store, the apply path and the tests). It gets a Developer
  design review. Two leg-level refinements of the flight spec:
  - **The byte-identical pin is not a committed golden file** (user-global
    rule). It is the existing suites with their assertions unedited, plus a
    before/after comparison in a scratch directory.
  - **`apply_proposal` accepts `AgentWriteDeps` or `KindDeps`**
    (`KindDeps.of`). So `evals/harness.py` and its freeze digest are not
    touched, which supersedes DD3's "re-pinned in Leg 1a" note.

- **2026-11-21, during Leg 1a: connectors are out of GleepGlorp's scope**
  (operator). After this mission, the operator will rework how connectors
  work, so GleepGlorp gets no connector proposals, fills or write service.
  - The mission criterion, its planning decisions and its Flight 5 entry are
    amended, as is this spec's DD1 and Open Questions.
  - DD4's dropped kind CHECK means no schema text names connectors.
  - The existing read-only connector view (Flight 1) and page awareness stay,
    since they are read-only and already shipped. Removing them would be a
    separate operator call. The operator then confirmed: "reading connectors
    is fine".
- **Leg 1a landed** (`[LAND:leg]`).
  - **Accepted deviations,** both behaviour-preserving:
    - `Kind.summary_text(p, zone)` is async, and the routine kind loads its
      own zone;
    - `Kind.apply` takes the routine `runner` beside `mark`;
    - a small `Kind.card()` helper.
  - **Results:**
    - the AC8 before/after diff was empty;
    - the unit tier gave 11397 passed and 15 skipped;
    - the evals harness and the freeze digests were untouched.
- **Leg 1b design** (`legs/01b-schema-targets-and-route.md`). **Risk tier:
  high,** because of a schema migration, shared stores, the tool parameter
  schemas and the page line the model reads. It gets a Developer design
  review against Leg 1a's landed code.
- **Leg 1b design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes. FD calls:
  - the route is stripped from the operator's chip, client-side;
  - the AUTOINCREMENT sequence is carried across the rebuild;
  - the shared store base is cut to what is really common (no shared
    `mark`);
  - the `target` tool parameter **moves to Leg 4**, so no platform-text
    change lands without a consumer (a refinement of DD5);
  - `gleepglorp` lane budget 360 s, provisional;
  - the `chat` alias keeps its pattern.

  There was no second cycle; see the leg's Design Review section.
- **Leg 2 design** (`legs/02-client-groundwork.md`), drafted while Leg 1b is
  being built. **Risk tier: high,** because it changes shared client modules
  (the drawer fill, the cards, the receipts, the approvals record). The design
  review waits for 1b to land. Scope calls:
  - **The "one card and receipt folding rule" (DD11) is dropped.** The card
    and receipt state machines share no folding rule; ordering is already
    shared (`App.chat.cardOrder`).
  - **No new dirty-state tests for the agent kind.** The existing four in
    `test_flow_gleepglorp_fill.py` cover it and are the unedited net. Legs 4
    and 5 add the pair for their kinds.
- **Leg 1b landed** (`[LAND:leg]`). Unit tier 11431 passed, 15 skipped. The
  `gleepglorp` lane: 122 passed in 289 s (solo, reference only).
  `chats-transcript`: 152 passed.
  - **Accepted deviations:**
    - the chip-strip regex is `/ \(#\S*\)$/`, because `encodeURIComponent`
      keeps parentheses;
    - the fill tool passes `norm.target_id`;
    - only `dumps` is unified in `status_rows.py`; the others write different
      bytes.
  - **Accepted test gap:** the falsification "no" items are shape and route
    cases with no fail-open risk.
- **Leg 2 design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes, all folded in:
  - the namespace is `App.gleepglorpKinds`, since `gleepglorp.js` would
    clobber `App.gleepglorp.kinds`;
  - the agent kinds register at the end of the Studio block, with late-bound
    calls;
  - the AC8 test nulls the agent kind's `fill` (no fake kind can be seeded);
  - a separate `byTarget` store;
  - the single frame pin.

  There was no second cycle.
- **Leg 3 design** (`legs/03-outside-value-guard.md`). **Risk tier: high**
  (security). The design review comes after Leg 2 lands.
- **Leg 3 design review, cycle 1** (Developer, Sonnet; it ran while Leg 2 was
  being built, read-only on other files). Verdict: approve with changes. Two
  high bypass-class findings:
  - **Substring URL matching.** `https://good.com` would match inside
    `good.com.evil.test`.
  - **Bare domains not extracted.** The planted `garden-stats.example.test`
    in the eval fixture would pass.

  Both are fixed in the leg, which **refines DD7's matching rules**:
  - URL values pass by normalised equality only;
  - a wider token boundary;
  - TLD-allowlist bare-domain extraction that excludes file-extension TLDs;
  - NFKC and zero-width folding;
  - `fnmatch` loader globs, with a wider denylist;
  - args matched within one source;
  - only `[2xx]` fetches count;
  - the channel exclusion.

  **Documented residuals:** defanged forms, TLDs outside the allowlist,
  off-site redirects of a typed URL, truncated pages (fail closed), and
  instruction text.
- **Leg 2 landed** (`[LAND:leg]`).
  - **Results:** the `gleepglorp` lane 125 passed (293 s); `agent-tabs` 221
    passed (458 s); unit tier 11431 passed, 15 skipped. No existing browser
    assertion was edited.
  - **New:** `tests/browser/test_flow_gleepglorp_kinds.py`, in the
    `gleepglorp` lane.
  - **Lanes not run:** only `agent-tabs` among the follow lanes. The other
    hits of the broad grep are unrelated files. The Batch A review decides
    whether more lanes run.
- **Leg 3 landed** (`[LAND:leg]`).
  - **Results:** unit tier 11549 passed, 15 skipped. AC9 clean: no existing
    test tripped the guard. All nine required safety tests were falsified.
  - **Accepted going-beyond items,** all fail-closed:
    - peer and routine turns drop the last USER message from tier 1;
    - unnamed keys are scanned as free text;
    - the trailing boundary is `(?!\w|\.\w)`.
  - **Leg 4 constraint:** the declared companion command field must be named
    `command`.
  - **Accepted residual:** common-TLD names in free text after a fetch (for
    example `socket.io`) need operator typing.
- **Batch A review** (Legs 1a, 1b, 2 and 3). **Reviewer: Sonnet, security
  tier,** because the diff touches the secret guard's neighbour, the new
  outside-value guard and the taint scan. **Accessibility Reviewer: Sonnet,**
  because the client changed (the chip strip, receipt and card text sources).
  They run in parallel; the Accessibility Reviewer does a static review only,
  so the host policy holds.
- **Batch A accessibility review:** `[HANDOFF:confirmed]`. The visible and
  accessible text is unchanged for the agent kinds. The route never reaches
  an accessible name or an announcement (`addPageChip` is the only path, and
  it uses `textContent` only).
- **Leg 4 split into 4a (server) and 4b (client)**, an acceptable variation
  (the Flight 3 Leg 6 precedent). Leg 4a design: `legs/04a-mcp-server-kind.md`.
  **Risk tier: high** (write boundary, secrets). FD calls:
  - **Changing an MCP server's `type` is fill-only.** A proposal refuses it
    with a handoff, because the editor owns which keys a switch drops. This
    narrows DD9 for proposals.
  - **`update_in_txn(mutate)`** re-reads and mutates inside the transaction,
    instead of `change_agent`'s retry. There is no read-outside-write gap, so
    `_cache` and the OAuth tokens are always fresh.
  - **The `target` parameter and kind-named descriptions land in 4a,**
    because adding fields breaks the per-field description pin.
- **Batch A code review** (Reviewer, Sonnet, security tier):
  `[HANDOFF:confirmed]`, no blocking issues.
  - **Results:** unit tier 11549 passed, 15 skipped; the `gleepglorp` lane
    125 passed (294 s).
  - **Bypass probing of `outside.py` found nothing.** The taint scan, v56
    and the `ApplyError` folding were judged sound.
  - **Non-blocking items carried:**
    1. **Leg 4a:** a `None` row value in the declared-rows branch is turned
       into the string "None", so skip `None` (with a test).
    2. **Leg 4a:** widen `LOADER_KEY_GLOBS` (`NODE_TLS_REJECT_UNAUTHORIZED`,
       `HOME`, `XDG_*`, `PYTHONINSPECT`, `BUN_*`, `DENO_*`, `GEM_*`,
       `BUNDLE_*`, `JAVA_HOME`, `MAVEN_OPTS`, `GRADLE_OPTS`).
    3. **Leg 4a docs:** IDN and homograph domains and TLDs outside the
       allowlist in free text go on `SECURITY-MODEL.md`'s residual list.
    4. **Accepted as precedent:** a crash between DROP and RENAME in the v56
       replay (the v12/v33/v44 ceremony).
    5. **Accepted:** the tier-2 args single-source rule.
- **Batch A checkpoint commit.** Legs 1a, 1b, 2 and 3 are marked
  `completed`. The planning artifacts are included.

## Leg Progress

### 01a-kind-registry

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - New package `the_one/gleepglorp/kinds/`: `base.py` (`Kind`), `errors.py` (`ApplyError`, one
    `translate`, `reraise`), `deps.py` (`KindDeps.of`), `agent.py`, `rule.py`, `routine.py`
    (field tuples, normalizers, `exists`, `apply`, summary text), `__init__.py` (explicit
    `REGISTRY` tuple, `get`, `normalize`, `describe`, `spec_for`, the derived views, `FILLABLE`).
  - `proposals/shape.py` reduced to the primitives plus a lazy module `__getattr__` re-export
    (no moved name is a real attribute). `proposals/apply.py` dispatches through
    `kinds.get(...)` and folds `ApplyError` in one branch; `failure_errors`, `_is_gone`,
    `_agent_or_rule_stale`, `_routine_stale` are gone from it.
  - `continuation.proposal_title`, `fill/store.py`, `fill/tool.py` (`enum` from `kinds.FILLABLE`),
    `proposals/tool.py`, `proposals/store.py`, `view_fields.py` read the registry.
  - Tests: three monkeypatch retargets (`shape` to `kinds` / `kinds.agent`); seven `kinds/*.py`
    paths added to the seam-import guard parametrization; new `tests/test_gleepglorp_kinds.py`
    and `tests/test_gleepglorp_apply_error.py`. `the_one/agents.md` gained "GleepGlorp kinds
    registry (M36 F4)" and its `shape` references were repointed.
- **Notes**:
  - **AC8 before/after: identical.** Scratch script
    `/tmp/claude-1000/-home-cprch-projects-the-one/1821e3c0-8ca0-4061-b85e-be991e1f3210/scratchpad/leg01a/capture.py`
    run before any edit (`before.json`) and after (`after.json`); `diff` printed nothing. It
    captures `describe()` and per kind, `KINDS`, `ACTIONS`, `KIND_SUMMARIES`,
    `OPERATOR_ONLY_FIELDS`, every `FieldSpec` (without the two new attributes),
    `SCHEDULE_EXAMPLE`, `_ECHO_MAX`, both tools' `parameters`, `proposal_title` for every
    kind and action, `normalize` output for each apply scenario, and `apply_proposal`
    outcomes, stale payloads and `result` dicts (agent, rule and routine stale and override;
    routine create and change; agent and rule create). Nothing from it is committed.
  - **Deviation from the leg text (small, behaviour-preserving):** `Kind.summary_text` is
    `async summary_text(p, zone)` (the routine kind loads the zone for the schedule sentence
    itself) instead of `(p, routine_name, sentence)`; `apply` also receives a `runner` (the
    routine `ProposalRunner`) beside `mark`, because kinds may not import `apply.py`.
    `Kind` also gained a `card()` helper over `card_title`. The fill card title now comes from
    `kinds.get(fill.kind).card(...)`, the same text.
  - Falsification: `test_an_error_that_is_not_an_apply_error_propagates` yes (catching
    everything in `apply_proposal` failed it); the agent-create `IntegrityError` tests
    (`test_translate_an_agent_create_integrity_error_is_returned_unchanged`,
    `test_an_agent_create_integrity_error_propagates_out_of_apply_proposal`) yes (widening
    `_is_gone` failed both). The stale, gone, items, already-resolved, `KindDeps` and
    registry or re-export tests: no (not falsified). Both fixes were put back by editing.
  - AC6: `git diff --stat` shows `evals/`, `test_evals_freeze.py` and
    `test_gleepglorp_proposals_apply.py` untouched; `test_gleepglorp_proposals_continuation.py`
    changed only by the seven added seam-guard parameters (no fixture or assertion edit).
  - AC7 suites: 699 passed. `THE_ONE_TEST_NETNS=1 make test-unit`: 11397 passed, 15 skipped. `ruff check` and
    `ruff format --check` on `the_one/ tests/ scripts/ evals/`: clean.

### 01b-schema-targets-and-route

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - **Schema v56** (`db/schema.py`): `gleepglorp_proposals` rebuilt without the kind CHECK;
    `gleepglorp_fills` rebuilt with nullable `agent_name` and `target_id` after it. Per-table
    shape helpers (`_proposals_has_kind_check`, `_fills_has_target_id`), one `executescript` per
    table (v12/v33/v44 ceremony), sequence carried by an `UPDATE`/`INSERT` on
    `sqlite_sequence` written into the script from the old `seq`. Squawk 0398 comment now cites
    `the_one/agents.md`. Every `== 55` pin is 56 (about 16 in `test_db_migration.py`,
    `test_gleepglorp_fill_store.py:58`); fills column pin gains `target_id`;
    `TestSchemaV54`'s bogus-kind test is inverted (accepts any kind, keeps action and status
    CHECKs). New `TestSchemaV56` (fresh shapes; v55 shape built by hand with all statuses and
    kinds, top row deleted, rows and ids carried; replay; each table independent).
  - **Stores**: new `gleepglorp/status_rows.py` (`loads`, `dumps`, `get_row`,
    `list_for_session_rows`, `push_session_frame`); both stores and both `events.py` use it
    (wrapper names and modules unchanged, so every patch site holds). Proposal insert refuses an
    unknown kind (`ValueError`, like the fill store); fill store checks `kinds.FILLABLE`
    (`KINDS` removed); `NewFill`/`Fill`/SQL/`fill_view` carry `target_id`; `fill_view` guards a
    missing agent; `agent_name` is `str | None` on `Normalized`, `NewFill`, `Fill`; the fill
    tool passes `norm.target_id`.
  - **Targets**: `Kind.resolve_target` (optional, set on agent via `existing_agent`),
    `kinds.target_key`, `kinds.resolve_by_id_or_name`.
  - **Reads**: `_list_or_detail(..., id_of=)`; MCP servers and providers list and detail carry
    `id` (`ALLOWED`, `OPERATOR_PATHS`, the provenance `REVIEWED_ALLOWED` pin for providers
    updated on purpose); id matches before name.
  - **Page line**: `build_line(descriptor, resolved_name, resolved_id)` with `_route`, `_enc`,
    `_label`; `_resolve_item` replaces `_stored_name`. Chip strip in `addPageChip`
    (`areas/chat/transcript.js`, the one function). Eval scenario `[page]` lines and
    `agent_seg` fact updated; `test_evals_gleepglorp_fills.py` page-line pin builds with
    `resolved_name`/`resolved_id`; `test_ws_page_context.py` `LINE` gained the route.
  - **Lane**: `gleepglorp` (5 files) in `scripts/run-tests.sh` (LANE_LIST, CANON_LANES, case,
    BUDGET 360 s provisional, header), out of `chats-transcript`/`chats`/`shared`;
    `test_run_tests_lanes.py` updated (LANES, LANE_LIST string, `chat` alias pin, a new lane
    test).
  - **Docs**: `CLAUDE.md` lane list; `the_one/agents.md` (new "Schema v56, id targets and the
    page route" subsection, `build_line` signature, proposal/fill table notes, lane bullet).
- **Notes**:
  - **Lane timings (reference only, not a budget reading; solo runs at host load about 1.5-2.0,
    `THE_ONE_TEST_NETNS=1`):** `gleepglorp` 122 passed in 289 s; `chats-transcript` (now without
    the two moved files) 152 passed in 410 s.
  - **Gates:** `THE_ONE_TEST_NETNS=1 make test-unit` 11431 passed, 15 skipped (the static JS
    guards `test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`
    included: 396 passed alone); `ruff check` and `ruff format --check` clean.
  - **Left out of the shared store module, and why:** status transitions (`mark_op`, the
    fills' `claim`/`record_outcome`) and both `insert`s stay in their stores (different rules:
    one-open-per-chat vs claim tokens and leases). The two serializers were not unified beyond
    `dumps`: `dumps` is byte-identical to what both stores wrote for `changes` and `base`
    (compact, `ensure_ascii=False`), but `mark_op`'s `result` serializer and the
    `untrusted_sources` `json.dumps` use different options, so they stay as they were.
  - **Deviation from the leg text (small):** the chip strip regex is `/ \(#\S*\)$/`, not
    `/ \(#[^()\s]*\)$/`: `encodeURIComponent` (so `enc`, so the route) leaves `(` and `)`
    unescaped, and an agent named `a(b)` would otherwise keep its route in the chip. A route
    never holds whitespace, so `\S*` anchored at the end is exact. The Python `_enc` copies the
    client's `enc` (parens unescaped).
  - Not run: the `settings`-family and other browser lanes (nothing under them changed). The
    new browser assertion (no `(#` in a resolved item's chip) is in
    `test_a_later_message_carries_the_agent_tab_it_was_sent_from`; the strip also fails the
    existing exact-text chip assertions when removed.
  - **Falsification (each by editing the fix out, running, putting it back by editing):**
    sequence carry (`test_v55_rows_and_id_high_water_marks_survive`): yes; fills replay
    (`_fills_has_target_id` made always-False: `test_replay_keeps_rows_and_a_post_v56_target_id`
    and `test_each_table_is_rebuilt_independently`): yes; proposal kind refusal: yes; fill kind
    refusal (three params): yes; id-first resolution (`test_an_id_wins_over_a_name`): yes; chip
    strip (existing chip assertion `test_the_first_message_carries_the_page_...` failed without
    it): yes. Not falsified: the proposals-side replay helper alone (a rebuild is lossless, so
    only the fills side can lose data), the read-by-id twin test (the name-first order would
    still reach the twin because ids and names do not collide in the seed), the encoder
    pin, the route cases, the lane tests, `test_gleepglorp_targets.py`'s `target_id` round
    trips, the ids-in-reads shape test, and the new `(#` browser assertion on its own.

### 02-client-groundwork

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - New `static/js/gleepglorp-kinds.js` (`App.gleepglorpKinds`: `register` (throws on a
    duplicate), `get`, `names`), loaded before `approvals.js`; new
    `areas/studio/agent-kinds.js` registering `agent` (with a `fill` spec), `rule` and `routine`,
    loaded last in the Studio block (late-bound calls).
  - Drawer `fill.js` now goes through `get(view.kind).fill` (no agent code; a kind with no
    `fill` is `not_filled` / `editor_unavailable`, no navigation). `fill-receipts.js` words the
    two kind reasons from `labels` (generic fallback "The editor could not open." / "That item no
    longer exists."). `proposal-cards.js` uses `openLink` / `labels.withdrawnGone` (`AGENT_TABS`
    and `openAgentLink` gone; `focusTarget` reads the link's testid; `appliedByApproval` passes
    `target_id`). `approvals.js` records any registered kind through `recordKey`, adds
    `byTarget` and `forTarget(kind, id)`, invalidates the kind's `store`.
  - `apply.py`: `config_changed` carries `target_id`; the one frame pin
    (`test_gleepglorp_proposals_apply.py`) updated to `None`.
  - New `tests/browser/test_flow_gleepglorp_kinds.py` (3 tests), added to the `gleepglorp` lane
    in `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py`; `the_one/agents.md` section
    "GleepGlorp client kinds registry (M36 F4 L2)".
- **Notes**:
  - Lanes (reference only): `gleepglorp` 125 passed, 293 s; `agent-tabs` (holds the follow
    test) 221 passed, 458 s; `THE_ONE_TEST_NETNS=1 make test-unit` 11431 passed, 15 skipped,
    384 s (static guards included). Ruff check and format clean.
  - Greps for AC3/AC4 return nothing. No existing browser assertion was edited.
  - Dropped the flight's "one card and receipt folding rule" as the leg planned (card and
    receipt states do not share one).
  - Falsification: registry duplicate-throw and approvals/stub test: yes (guard removed, failed);
    no-fill-spec drawer test: yes (guard removed, failed); script-order/names test: no.

### 03-outside-value-guard

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - `agent/taint.py`: `find_anchor(messages, tool_call_id)` extracted; `compute_taint` uses it,
    behaviour unchanged (taint, routine-tools and notes tests pass unedited).
  - New `the_one/gleepglorp/outside.py`: `fold`, `normalize_url`, `extract_addresses`,
    `deescape`, `token_match`, `is_loader_key` (+ `LOADER_KEY_GLOBS`, `TLD_ALLOWLIST`),
    `collect` (tier 1 and tier 2), `plan`, `check`.
  - `FieldSpec.rows` added (default false); docstring updated.
  - `propose_change` and `fill_form`: after `guard.check` and `compute_taint`, when untrusted,
    `outside.check(kinds.get(norm.kind), norm.changes, outside.collect(...))`; a refusal returns
    before the insert (nothing recorded, no frame). Neither tool's description or parameters
    changed; no `evals/` file edited.
  - New `tests/test_gleepglorp_outside.py` (118 tests). `SECURITY-MODEL.md` (residual paragraph
    keeps 2026-11-20, adds the 2026-11-21 update and a guard section); `the_one/agents.md`
    "Outside-value guard (M36 F4)".
- **Notes**:
  - Gates: `THE_ONE_TEST_NETNS=1 make test-unit` 11549 passed, 15 skipped; ruff check and format
    clean. AC9: no existing test tripped the guard (no `[BLOCKED]`).
  - Falsification (fix removed by editing, test run, fix restored by editing), all yes:
    marked-USER exclusion; untyped-fetch exclusion; free-text email refusal; loader-key-from-
    linked refusal; no-anchor refusal; token boundary (`good.com` in `good.com.evil.test`);
    bare-domain extraction (`garden-stats.example.test`); stitched-args refusal; per-message
    call map (repeated id). The nine mutations were applied together and every target test
    failed; they were then reverted.
  - Design calls beyond the leg text, all fail-closed or defence in depth:
    - `collect` takes an optional `turn`; on a peer or routine turn the last USER message is
      dropped from tier 1, because the app binds a turn's marks only after the step.
    - A stored key that no spec names is scanned as free text.
    - A loader key is still checked when its value is empty (key must be typed).
    - A declared list's single-source rule uses the declared field named `command` as companion;
      Leg 4 must name its command field `command` (or this rule needs a marker).
    - A bare domain, host:port or IP as a whole declared value passes by normalised equality with
      a typed or linked URL, else by token match.
    - Scheme URLs are extracted before emails, so `ssh://git@host` is one URL.
    - The bare-domain, host:port and www. lookbehinds exclude only word characters and `@`, so
      `*.evil.com`, `--host=evil.com` and `x:evil.com` are still found; the trailing boundary is
      `(?!\w|\.\w)` so a sentence-final period does not hide an address.
    - The stub-kind tool test reaches `propose_change` by monkeypatching `kinds.normalize` and
      `kinds.get`; the allowed side asserts only "not refused" (the real store has no stub kind).
  - Accepted residuals (documented): instruction text in free text; defanged forms and
    unlisted-TLD domains; redirects off-site; truncated pages; typed-only args stitched across two
    operator messages are refused (fails closed); common-TLD false positives in agent free text
    after a fetch (for example `socket.io`) are refused until the operator types them.
  - No AC9 trip. Eval rates (`fill_made`, `propose-*`) may move; Legs 6 and 7 re-baseline.

## Decisions

## Deviations

## Anomalies

## Session Notes
