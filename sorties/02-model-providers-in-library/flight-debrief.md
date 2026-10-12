# Flight Debrief: Model providers in Library

**Date**: 2026-10-12
**Flight**: [Model providers in Library](flight.md) (sortie 02)
**Status**: completed (merged as `298f857`, PR #269; released as v0.11.3)
**Duration**: 2026-10-11 (charter) to 2026-10-12 (merge and release)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
- **Model providers live in Library.** They are the first group, "Model providers", listed and edited like knowledge bases, MCP servers and connectors. The provider editor opens in the detail pane at `#library/providers[/~new|/{id}]`.
- **Library has a real front door.** `#library` is the start page's own route. Bare section URLs (`#library/knowledge|mcp|connectors|providers`) are silent aliases for it. Breadcrumbs read `Library / {Group}`, with "Library" the link. A static check forbids any code that produces a bare section URL.
- **Settings has no Models section.** `#settings/providers…` and `#admin/providers…` are unknown routes: a cold load lands on `#chats`, and an in-app go is refused.
- **Code structure.**
  - All provider code moved out of the admin area: `admin.js` −509 lines and 0 `provider` mentions, and `providers-list.js` deleted.
  - It now lives in `areas/studio/` behind a new `providers-section.js` (256 lines) with an explicit ctx/handle contract. `studio.js` grew only 86 lines.
- **Tests.**
  - A ninth browser lane, `providers`, holds 102 tests.
  - 28 browser files and helpers were migrated, and the retired testids are fenced.
  - A new guard rejects any `settings/providers` route literal.

### Charter Success Criteria
| Criterion | Result | Note |
|---|---|---|
| Library shows a "Model providers" group first, rows with type badge and "used by", editor at `#library/providers[/~new\|/{id}]` | **Met** | `test_flow_provider_library.py::test_model_providers_is_the_first_group_with_badge_and_used_by` and 15 sibling tests, plus `test_flow_provider_items.py` |
| `#library` is Library's own route with a first Model providers card; nothing presents the root as the knowledge section; the Add menu and Jump to reach providers | **Met** | `test_router_core.py::test_library_root_is_a_route_of_its_own`; the four-card start-page test; `library_add(page, "providers")`; Jump to `data-kind="provider"`; router comments, `agents.md` and `CLAUDE.md` rewritten |
| No Settings Models group; `#settings/providers…` is no longer a route (dropped, not redirected) | **Met** | `test_settings_pages_static.py` (seven pages); the routing pins for six old hashes resolve to unknown |
| Unit and every browser lane pass; provider tests use Library routes; no `settings/providers` route remains in tests | **Met** | Debrief run on merged main: unit 5953 passed / 12 skipped; browser `PARALLEL_RESULT rc=0 total=939s lanes=9 failed=-`. The remaining literals are the guard and the unknown-route pins |

All four criteria are met, and all checkpoints are met, including leg 1's in-leg Part A checkpoint.

## What Went Well
- **Two Architect design reviews caught real problems before any code was written.**
  - The retired-testid plan would have failed the registry coverage pin, because `library-empty-` and `settings-nav-` stay live.
  - The `#library` root was unspecified in studio's state model.
  - A route-keyed label collision with the still-live Settings "Providers" page would have broken `test_router_announce.py` mid-flight.
  - Each of these would have cost a fix loop.
- **The additive-then-subtractive leg split.** It was suggested by Architect cycle 1, and the operator chose to merge the root work into the additive leg. Leg 1 proved the moved editor in both hosts at once: the unmodified Settings tests plus the new Library tests. Leg 2 then deleted a path already known to work, and the routing and studio changes never broke both hosts together.
- **The in-leg checkpoint isolated the root churn.** It came from running each leg as two Developer spawns (Part A, then Part B). Three lanes' stale expectations were fixed before any provider code existed.
- **The DD4 module contract held.** The Divert criterion never fired, because `providers-section.js` needed no studio state beyond `ctx`. The interface was, if anything, over-specified: `getDirty` and `bumpEditorGen` are wired but unused.
- **Out-of-scope finds stayed out.** Squawks 0187 (an agent-rules focus flake) and 0188 (plan re-auth copy says "Administration") were logged, not folded in.
- **The Flight Director rejected a skimmed review.** Review cycle 1's Reviewer confirmed while saying it had only skimmed the two highest-risk surfaces. Treating that as partial led to cycle 2, which found a real race (below).
- **Gate time improved.** The browser gate went from 1055 s (M28) to 939 s, back under Mission 26's ~20-minute target, because provider tests left the settings lane (477 s → 227 s) for a parallel lane.

## What Could Be Improved

### Process
- **The race reached the end-of-flight review.** A provider save or delete resolving after the user switched items could re-sync the URL to the old item, clear the shared `dirty`, or discard the newly opened editor. Review cycle 2 found it, and fix round 2 closed it with a module-local `mountToken` and three held-request tests falsified against the old guard.
  - **Root cause:** DD4 named `ctx.editorGen()` as the staleness signal. But `editorGen` is bumped only by `closeOpenItem` (`studio.js` ~l.1773), not by an intent switch between items or sections. Nobody asked at design time "what invalidates an in-flight save?" beyond discard and breadcrumb.
- **One reviewer for a 105-file diff.** The two-leg soft limit was honoured by splitting each leg into two Developer spawns. That kept each spawn small, but concentrated the whole flight (105 files, +3606/−3027) into a single end-of-flight review, where cycle 1 skimmed.
- **Stale expectations not enumerated.** Leg specs did not list the existing tests their route and copy changes would break:
  - Part A: three lanes, about 460 s of re-runs;
  - leg 2: the Jump-to page count;
  - DD6: the create title, caught only at review.
- **The full gate predated the review fixes.** The nine-lane gate ran before fix rounds 1 and 2, and only unit plus three lanes ran after. The debrief's full run on merged main closes that gap (green), but the commit went in on a partial post-fix gate.

### Technical
- **The same stale-callback race likely exists in the other three Library editors.** This is the Architect's debrief reading and is unconfirmed by a test. It predates this sortie.
  - **Connectors** (`studio.js` ~1595-1614): the same shape as the pre-fix provider code, with a hard-coded `sync('studio', 'connectors/' + id)`.
  - **MCP** (~1397-1469): it re-serializes, but `editingMcpSource = updated` is assigned first, and `dirty = false` clobbers.
  - **Knowledge bases** (~1238-1258): `mountKnowledgeDetail` wipes the pane before its own stale guard.
  - **All three:** `onDeleteSuccess` and `onDirtyChange` are unguarded.
  - Review cycle 2's "unaffected because they re-serialize" covered only part of the MCP case.
  - **Needs a sortie** (lifecycle change across three orchestrators; see Recommendations).
- **Hand-maintained section lists.** `studio.js` has two lists duplicating `LIBRARY_GROUPS`: `hydrateState`'s root list (~l.187) and `isLibrarySection` (~l.628). A fifth group needs both edited.
- **Per-section `if` chains.** The `library` and `providers` pseudo-sections add special-case branches (about 30 delegate sites). A handle registry keyed by `LIBRARY_GROUPS` would remove them, and should come before extracting the next section.
- **Two views of providers in studio.** `providersCache` and `_allProviders` are both fed by `App.store`. This was a deliberate DD to avoid changing the Agents-list gating, but it is a drift risk.
- **Small leftovers.**
  - The `admin-pf-*` class names now live in `studio.css` (accepted naming debt).
  - `.cap-chip*` lives in `components.css`.
  - The provider tests in `test_flow_settings_focus_after.py` still run in the settings lane.
  - The unused ctx members `getDirty` and `bumpEditorGen` remain.
- **Retired with no ported test.** These Settings provider checks were deleted rather than ported: tile layout and ellipsis, the tab-order walk, the store-notification focus test and the forced-colours tile. The Library row gets those properties from `App.ui.listPane`, but no provider-specific test pins them.

### Documentation
- `agents.md` "Providers section" states the stale-callback rule for providers only. The general rule belongs beside "The save-create staleness guard" (`agents.md` ~2050) once the other sections adopt it.
- The router announces the knowledge section as "Knowledge" (`router.js` ~446), while the group label is "Knowledge bases". This predates the sortie and should be confirmed as intended.
- The re-authored behavior specs (9) were not re-run. They are operator-run, and there was no HAT.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Each leg ran as two Developer spawns with an in-leg checkpoint, instead of splitting legs | Honour the operator's two-leg choice while limiting each Developer's blast radius | **Yes**, for large legs, with the review-depth caveat below |
| The operator folded the `#library` root cleanup into the sortie mid-planning | The operator flagged stale "root = knowledge section" context, which sat in the same decision cluster (how Library is addressed) | Yes: same-cluster cleanup belongs with the work, and charter criteria were consolidated to stay at four |
| `LISTS["settings/providers"]` scoped by link class, not an `.area-admin` ancestor (DD10) | A `has=` locator cannot match an ancestor-first selector | No (interim only); check `_lists` locator mechanics when specifying helpers |
| `editorGen` replaced as the staleness signal by `editorGen` + `mountToken` + `isActive()` | `editorGen` only means "discarded", not "the mounted item changed" | **Yes**: a mount-token rule for any orchestrator callback that outlives its mount |
| The Flight Director rejected review cycle 1's confirmation as partial | The Reviewer stated it had skimmed the highest-risk surfaces | **Yes**: a Reviewer must list the surfaces it deep-read |
| Committed on unit plus three lanes after the fix rounds, not a full gate | The fixes touched only surfaces those lanes cover; saved about 16 min | Acceptable, but the debrief run was the first full post-fix proof |

## Key Learnings
- **Ask the lifetime question at design time.** For any design that moves or adds an editor, list its callback-invalidation events: discard, an intent switch within a group, a switch across groups, and leaving the destination. Give each a held-request test, falsified against the old guard.
- **Held-request staleness tests must leave the editor clean.** A dirty editor makes the leave guard discard, which bumps `editorGen` and masks the bug. The first draft of the race tests passed against the buggy code for exactly this reason.
- **Fence before you retire, and remove live registry rows in the same edit.** The coverage pin fails on a retired id while it is still registered live, or when it is a prefix of a live one.
- **Destination-keyed labels.** A route-segment-keyed label table collides once two destinations share a segment (`providers`). Key by destination.
- **Stale context propagates.** A misleading code comment and one `agents.md` line (`#library` → `#library/knowledge`) made planning describe the Library root wrongly to the operator. Code comments are context and need the same upkeep as docs.

## Methodology Observations
All of these were observed with mission-control **1.2.0**.

1. **The sortie two-leg soft limit vs a design reviewer's split.**
   - **Skill and phase:** `/mission-control:sortie` Plan step 5, and `/mission-control:agentic-workflow` 2a.
   - **What happened:** Architect cycle 1 recommended splitting leg 2. That made three legs, so the soft limit forced an operator choice, and they merged the root work into the additive leg. The leg-1 Developer design review then recommended splitting leg 1 into 1a/1b. The Flight Director kept the leg count and ran each leg as two Developer spawns, which neither skill describes.
   - **Expected instead:** guidance on whether a split within a leg (sequential spawns with a checkpoint) is an accepted way to honour the limit.
   - **Cost:** two extra operator and Flight Director decisions, and a single review absorbing a 105-file diff.
2. **The flight review has no depth contract.**
   - **Skill and phase:** `/mission-control:agentic-workflow` 2d, "Reviewer: Review" prompt.
   - **What happened:** the cycle-1 Reviewer signalled `[HANDOFF:confirmed]` while stating it had only skimmed the two surfaces the flight design marked highest-risk. The skill treats `[HANDOFF:confirmed]` as passing, and nothing asks the Reviewer which surfaces it deep-read, or assigns deep focus areas by risk tier.
   - **Expected instead:** a required "surfaces traced" list, and risk-ranked focus areas carried from the flight design into the Review prompt.
   - **Cost:** the Flight Director caught it manually. That took one extra fix round and two extra review cycles, and the blocking race would otherwise have shipped.
3. **Reviewer claims outside scope are taken as findings.**
   - **Skill and phase:** `/mission-control:agentic-workflow` 2d.
   - **What happened:** review cycle 2 asserted, outside its assigned scope, that the MCP, connector and KB editors were unaffected by the race. The Flight Director recorded that in the flight log. The debrief Architect's reading contradicts it.
   - **Expected instead:** a convention that out-of-scope assurances are labelled unverified.
   - **Cost:** a likely pre-existing defect class went unflagged until the debrief.
4. **Planning relied on stale in-repo context.**
   - **Skill and phase:** `/mission-control:sortie` Plan step 1, the qualification read.
   - **What happened:** the Flight Director's quick read took the router's `root: 'library/knowledge'` and its comment at face value, and told the operator that `#library` lands on the knowledge section. The operator corrected it and asked for the source to be cleaned up.
   - **Cost:** one correction round and a charter amendment (benign). Recorded because code comments are not in any skill's freshness checks.
5. **The debrief's full-suite run is affordable again.**
   - **Skill and phase:** `/mission-control:flight-debrief` Phase 2.
   - **What happened:** sortie 01's debrief recorded the operator stopping a slow sequential debrief run. Here the instructed full run (unit plus `--parallel 3`) took about 19 minutes and served as the first full gate after the review fixes.
   - No cost. Recorded as context for that earlier observation.

## Human Interview
Two questions were asked and not yet answered at writing:
- Has the operator used Model providers in the released app, given there was no HAT?
- Was folding the `#library` root cleanup into this sortie the right scope call?

Fold the answers in here if given.

## Recommendations
1. **Plan a sortie for the stale-callback race in the connector, MCP and knowledge-base orchestrators.**
   - First, write held-request tests that confirm or refute each case. Make the switch while clean, and falsify against the current guard.
   - Then apply the mount-token rule: act only if `gen === editorGen && token === mountToken && isActive()`. Guard delete and dirty callbacks too, and serialize the current state rather than a closure-derived sub.
   - Move the rule into `agents.md` beside the save-create staleness guard.
   - This is a lifecycle change across three orchestrators, so it fails the squawk gate.
2. **Before extracting the next Library section, introduce a section-handle registry keyed by `LIBRARY_GROUPS`.** Derive `hydrateState`'s root list and `isLibrarySection` from it. Then extract connectors first (smallest), then MCP, then knowledge bases, using `providers-section.js` amended with the mount-token rule as the template.
3. **Give the flight Review prompt a depth contract.** Require a list of the surfaces traced, and carry the flight design's highest-risk surfaces into the prompt as mandatory deep-read areas. This would have caught the race in cycle 1.
4. **Make leg specs enumerate expected-breaking tests** for route, copy and label moves (a grep of the old literal across `tests/`). This would have saved about one lane re-run per leg and the DD6 title miss.
5. **Small follow-ups, logged as squawks (2026-10-12):**
   - **0189:** move the provider focus-after tests to the providers lane.
   - **0190:** drop the unused ctx members `getDirty` and `bumpEditorGen`.
   - **0191:** derive or pin studio's Library section lists from `LIBRARY_GROUPS`.
   - **0192:** the "Knowledge" vs "Knowledge bases" router label.

   Earlier in the flight: 0187 (agent-rules focus flake, deferred) and 0188 (plan re-auth copy says "Administration").
