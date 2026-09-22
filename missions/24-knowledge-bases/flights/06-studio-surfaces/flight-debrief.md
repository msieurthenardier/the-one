# Flight Debrief: Studio Surfaces

**Date**: 2026-09-19
**Flight**: [Studio Surfaces](flight.md)
**Status**: completed
**Duration**: 2026-09-17 - 2026-09-19
**Legs Completed**: 6 of 6, plus an operator-driven HAT

## Outcome Assessment

### Objectives Achieved

Mission 24's operator-facing surfaces exist and were seen by the operator. Studio's
Knowledge section replaced its stub with a real inventory (create, rename, describe,
delete; register and inspect folders; read items, chunks and source; preview search
through the new `GET /api/knowledge-bases/{kb_id}/search`). The agent editor's
Knowledge tab replaced its stub with an attach-only surface that renders each
knowledge base's derived `kb__…__search` name **served by the backend** rather than
recomputed in JavaScript. Administration gained a Knowledge panel for the app-wide
`chunking` and `monitoring` settings, with `embedding` and `vector_store` read-only
and each carrying its reason on screen.

Underneath the surfaces, the flight closed a class of silent tool re-enablement.
DD-17 made `sha256(kb_id)[:8]` unconditional, turning a derived tool name from a
function of an agent's whole attached set into a function of `(kb.name, kb.id)`.
DD-5 rewrites `disabled_tools` across attached agents on rename. DD-13 re-emits
ungated-prefix entries client-side so an unrelated Studio save cannot erase them.

### Mission Criteria Advanced

No criterion was ticked. Four are materially advanced — register-a-folder-and-see-
status, inspect-contents-and-retrieve-source, attach/detach-in-Studio, and
automatic reflection of on-disk changes — but two of those are marked
*behavior-test-backed* and `kb-studio-round-trip` remains `draft` with five recorded
structural defects. Ticking them on the strength of a draft spec would be the kind
of bookkeeping this debrief exists to catch. The flight's contribution is real; the
criteria stay open until the spec is re-authored (see Action Items).

## What Went Well

**Adversarial design review paid for itself repeatedly, and the best decision came
out of it.** The flight drafted DD-1..DD-12; six more were created by review. DD-13
exists only because Architect cycle 1 found DD-5 was resting on a defect
(`collectFormData` erasing `kb__` entries) that would have made its whole leg
pointless. DD-13's *client-side* placement exists only because cycle 2 found the
obvious server-side preserve would be a one-way ratchet with no un-disable path.
And DD-17 — cycle 3 — is the flight's best decision: making the discriminator
unconditional **deleted** three of four fail-open paths (delete, attach, detach)
rather than defending them, collapsed DD-5 to a single-entry rewrite, and made
DD-14's delete-strip unnecessary. Cost: nine characters of tool name, permanently.
*Fix the key, not the call sites* is the reusable move.

**The behavior test earned its place by failing.** 18/19, with step 8's real failure
surfacing only because the Flight Director mandated the step run as one continuous
process. Run the ordinary way it would have mounted fresh, found the new file
already listed, and passed a false claim. Three of eighteen steps carry that
vacuity. The generalizable finding: **a step whose precondition a fresh mount
silently satisfies is vacuous unless the apparatus is mandated continuous.**

**The failure paths are tested, not merely asserted in prose.** `test_kb_rename.py`
pins the AC-12 fail-open discipline directly — one agent's failure not blocking the
rest, enumeration failure warning rather than raising, `enabled_tools` never
touched. `test_db_api.py` pins the full preserve/clear matrix and the Phase 2d
store-acquisition fix. `test_kb_tool_provider.py` states DD-17's invariant *as a
test* (`test_derived_name_is_invariant_to_set_composition`) and inverts the two
tests that pinned the old behaviour rather than deleting and re-adding them.

**Unticked boxes with reasons beat ticked boxes.** `pip-audit` ran, failed, was
filed as squawk 0083 and left honestly unticked. That is the pattern the rest of
the Completion Checklist should have followed and did not.

## What Could Be Improved

### Process

- **The landing commit flipped two status strings and left the Completion Checklist
  0-of-10 ticked**, while the log recorded several of those gates green repeatedly.
  Caught by the Architect at debrief, reconciled in `flight.md` after the fact.
  Marking a flight landed must include reconciling its own checklist.
- **Two checklist items were owned by no leg and therefore never executed**: the
  full `make test-browser` run and the frozen Windows installer build. The lanes are
  basename globs, so a full-suite run is not implied by running them. `pip-audit`
  is the counter-example — a leg owned it, so it ran. **An unowned checklist item
  does not get an honest "unticked, because…"; it gets forgotten.**
- **The HAT's yield was documented; the HAT's walk was not.** Three log sections
  recorded fixes arising from the walk; none recorded which of DD-18's required
  states were exercised or what was observed for the cross-surface one. Reconstructed
  at debrief while still recoverable and labelled as a reconstruction. DD-18
  mandated named state transitions with negative assertions per state; that structure
  should be written *as the walk proceeds*, not recovered afterwards.
- **`mission.md` went stale against DD-1.** With Flight 6 ticked, its bullet still
  claimed the Windows 1M `usearch` re-measure and two other entries still named
  Flight 6 as their resolution point — all deferred at Flight 6 planning. A ticked
  flight implied three deliveries that did not happen. Corrected at debrief.
- **A "variation" that names a specific seam is a leg-sizing error.** Leg 2's split
  into server/client halves was authorised by the flight spec's own Acceptable
  Variations — but that clause *named the exact seam*. The split then happened
  before a Developer was ever spawned, at zero cost. If you can name the seam at
  planning, you have made the decision; writing it as one leg defers only paperwork.
  The genuine variation in that same list ("split *if* it proves larger in
  implementation") was correctly not exercised.
- **The verification lane list was derived from intended surfaces, not from the
  diff.** `flight.md` names the `studio` and `system` lanes; the flight also modified
  two `shared`-lane files. Both pass, but the plan did not cover work the flight did.

### Technical

- **One correctness defect found at debrief** (squawk 0090): the agent editor's
  fresh-agent `GET` has a `.catch` returning the stale cached agent, which is then
  seated as `self._selectedAgent` and read by the ungated-prefix union — so a single
  failed fetch re-emits a pre-rename `kb__` entry and silently re-enables a
  deliberately disabled tool. The flight argued the *opposite* position for the
  sibling field at length (DD-4's marker discipline, implemented and tested for
  `kb_ids`); the identical reasoning was never applied to `disabled_tools`.
- **The borrowed-class contract is documented in one direction only.** The knowledge
  folder panels wear `.mcp-tool-item` / `-summary` / `-body`, owned by
  `mcp-server-editor.js` — which builds them by string concatenation into a
  grandfathered `innerHTML` sink, while the new consumer builds them with
  `createElement`. One shared contract, two construction idioms, no link. The
  owner's CSS rule at `studio.css:178` still says "Tools list on the MCP
  source-editor page" and has no back-reference, so a maintainer restyling the MCP
  page has no signal they are restyling the knowledge-base page too, and no test
  catches it (pixel snapshots are gitignored; CI never runs `-m pixel`).
- **The dynamic-sink guard is keyed on an 80-character prefix that can absorb
  growth.** This flight moved a baseline entry from a 3-statement, 17-line stub to a
  ~180-line interpolated template in a different area of the app. Same first 80
  characters, same "one entry", ~10x the sink surface, no signal beyond a human
  reading the diff. The values interpolated are module constants so the outcome is
  fine — but the guard's model permitted it silently.
- **The guard is manufacturing the duplication issue #207 names.** It pushes new
  files toward `createElement` + a local `_el` helper, which is the *right* shape —
  and because there is no shared `_el` to import, every file that obeys the guard
  writes its own. `_el` is now defined three times, `_fieldGroup`/`_section` twice.
  That turns #207 from a style preference into a consequence of an enforced invariant.
- **A documented return contract with no consumer**: `rename_kb_tool_references`
  returns the names of agents whose rewrite failed and spends a docstring paragraph
  on interpreting it; the caller discards it, and the docstring itself concedes
  "check the WARNING, not this return value."
- **A dead branch**: after DD-17, `_build_name`'s `hash_len is None` path is
  unreachable — both call sites pass an explicit length.

### Documentation

- CLAUDE.md's mock-provider option list presents itself as complete and omits
  `response["tool_calls"]` — the apparatus two behavior specs depend on, and the one
  DD-18's cross-surface state turned out to require (squawk 0089).
- CLAUDE.md claims a restart is required for JS/CSS changes; `StaticFiles` reads
  from disk per request. The wrong claim cost two unnecessary restarts during the
  HAT and was then repeated back by a Developer agent that had no other source of
  truth (squawk 0086).
- Two frontend patterns shipped with no home in `agents.md`, which gained only
  *backend* contracts this flight: the **load-success marker** (`data-kb-list-loaded`)
  and the **ungated-prefix union**. The next tab listing server-owned entities will
  otherwise copy the MCP swallow-and-continue idiom and reintroduce squawk 0050's shape.
- `kb-studio-round-trip`'s defect inventory lived inside its `**Status**` field
  (~200 words where every other spec has one token) and undercounted its own list as
  four when it enumerates five. Count corrected at debrief; the field still wants a
  `## Known Defects` section.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 2 split into server/client halves | Two risk domains, three kinds of evidence in one review gate | No — the seam was knowable at planning; it should have been two legs |
| Behavior test run inside Leg 2 rather than the optional HAT leg | It is Leg 2's own regression evidence for DD-4/5/13/14; an optional leg could have skipped it | **Yes** |
| DD-18 added at cycle 3 without re-running DD-11's observability audit | The table belonged to an earlier decision and was treated as settled | No — the re-run should be mandatory |
| Stranded-index state constructed rather than observed (HAT) | Six files under 500 bytes give an `indexing` window milliseconds wide | Acceptable, if labelled — it was |
| `pip-audit` left unticked with its blocker named | Squawk 0083 | **Yes** — this is the model for every checklist item |

## Key Learnings

**1. An observability audit must distinguish configured state from runtime state.**
DD-11 premise-audited its apparatus on both axes and caught a missing read path at
cycle 2 — good work. But every read path it enumerated observes *configured* state,
and DD-18 (added later) required a cross-surface assertion over *runtime* state: a
live session's effective tool set. **No surface in the product can observe that** —
not `GET /tools` (built-ins only), not `_resolve_kb_tool_names` (which reads stored
`kb_ids`), not any chat-session route. The contract only became observable during
the walk by scripting the mock provider's `tool_calls` so the agent loop's
acceptance or refusal became the signal. A config read can never satisfy a runtime
assertion, and nothing in the audit's shape forced that distinction to surface.

**2. A negative result from an instrument that cannot express the thing is not
evidence of absence.** Two instances this flight, both the Flight Director's:
squawk 0084's data-directory check against a path that never existed (so "production
untouched" passed unconditionally — and a production credential was rotated behind
it; **operator-confirmed 2026-09-19 as zero impact, fixed by relaunching the app**,
which closes this debrief's one outstanding human-interview question and replaces
the Flight Director's inferred containment claim with the operator's own report),
and a `ps` filter that structurally could not match a
`bash scripts/run-tests.sh` command line, used to assert a violation that had not
happened. Two instances is a pattern.

**3. A browser fixture that cannot produce the structure the code branches on is a
coverage illusion.** Every browser fixture was one flat directory with one short
file, so 15 green inventory tests ran over a degenerate shape: L6-D2's deliberate
flattening and the relative-path branch were both entirely unpinned. The unit layer
was strong throughout (200-level nesting, chunk boundaries, seq ordering, the
`MAX_FILE_BYTES` boundary) — the asymmetry was in fixture *realism*, not test
*count*. A leg spec introducing a structural rendering rule should state the minimum
fixture shape that can falsify it.

**4. Ambiguity in a leg spec is indistinguishable from a decision.** Three defects
traced to Flight Director wording, none of them errors of fact: AC-13 contradicted
itself ("refreshes its **status**" / "a **file** becomes visible") and was the root
cause of the behavior test's only failure, surviving two review cycles that each
read it as one claim. A step-14 instruction asked for a fresh-load reading *and* for
watching a staleness theme that a reload hides. And L6-D3's "matching the Custom
Headers row pattern" licensed dropping a confirm step from an irreversible
cascading delete — the implementing Developer flagged it rather than shipping it.
Each read fine alone.

**5. `[HANDOFF:confirmed]` must mean the reviewer's own delegated work has
returned.** Phase 2d's Reviewer confirmed with six sub-reviews outstanding, one of
which then found two real issues including the `kb_rename.py` guard gap that
contradicted the flight's own AC-12.

## Recommendations

1. **Make the observability audit a table keyed by assertion with a `state kind`
   column** — `configured` | `runtime` | `on-disk` — and forbid a `runtime` row from
   citing a config endpoint as its read path. Re-running the table must be a gate on
   any review cycle that adds a decision asserting an observable. DD-18's row would
   have read "a live session's effective tool set → *runtime* → ???" and failed loudly
   at cycle 3.
2. **Ship the missing item-row observable.** `KBItem` already carries
   `content_hash`, `size_bytes` and `mtime`, and the items route returns them
   verbatim — the client receives and discards them. Rendering `mtime` (or a hash
   prefix) closes three things at once: the behaviour spec's step-8 clause that has
   no browser observable today, the `knowledgeItemsSignature` blind spot (counts-only,
   so an edited file that stays `indexed` with the same chunk count never triggers a
   re-fetch and the inventory goes silently stale), and part of the HAT's
   fixture-realism gap. This is a render gap, not a data gap.
3. **Reconcile every Completion Checklist item to a leg owner at planning.** Two
   unowned items went unexecuted this flight. Carry the frozen Windows build, the full
   browser suite and `pip-audit` into the closing flight with owners named.
4. **Take the free fix DD-17 created for the detach→rename→reattach hole.** The
   derived name embeds a fingerprint of the knowledge base's *identity*. At agent
   build time `KBToolProvider` holds both the `kb_id` and the current derived name —
   so a reconcile (*if a `kb__…__search` entry's discriminator matches this `kb_id`
   but its slug does not match the current name, rewrite it*) is exact, needs **no
   cross-entity write**, no forced ordering and no partial-failure discipline. That is
   strictly better than DD-5's rewrite or the `kb_id`-keyed flag previously
   recommended, and it closes the hole `list_by_kb` leaves (it returns only
   *currently attached* agents, so detach → rename → reattach never rewrites).
5. **Treat DD-13 as a correct stopgap with an undocumented scope condition, and make
   the PUT/PATCH question a named design decision.** `update_agent` now carries three
   preserve-on-omit special cases, each argued locally — and squawk 0080
   (`mcp_source_ids`) is the fourth, missed. The invariant "a form must not erase
   fields it does not render" cannot live in the client (a second client
   re-implements it) or in a per-field preserve list (it needs a decision per field,
   forever, and one has already been missed). It belongs in the request protocol.
6. **Propose the component layer (issue #207) as the next mission, not a Flight 7
   leg.** The cost is no longer hypothetical: Leg 6 took four post-landing passes on
   one file, three of them closing defects of exactly one class — a page hand-assembled
   from another page's class names inheriting that page's assumptions invisibly. That
   cost used to be paid in developer passes; this flight paid it in **operator HAT
   walks**, the scarcest resource in the methodology. The Mission 11 Flight 5 debrief
   recorded the operator raising this in almost the same words; Mission 17 delivered
   the CSS half only. The issue's own risk note settles the vehicle: a layer adopted
   halfway leaves three idioms where there are two, so a stalled migration is a net
   loss. **Cheap interim step that does not wait**: rename the disclosure-tile trio to
   a neutral vocabulary and add a "consumers:" note at `studio.css:178`.

## Action Items

- [ ] Re-author `kb-studio-round-trip` to `active` — six of eighteen steps touched
      (9↔10 ordering, the fresh-mount preconditions on 5/8/10, step 6's fixture
      mandate, step 2's misplaced action), plus step 8 which needs Recommendation 2
      shipped first. It is Mission 24's only non-`active` behaviour spec, so the
      mission's closing regression net is currently not re-runnable. **Owned by the
      closing flight; appears in no Deferred Scope entry today.**
- [ ] Reconcile the remaining four Completion Checklist items with leg owners in the
      closing flight: merge PR #206, full `make test-browser`, frozen Windows build,
      `pip-audit` (squawk 0083).
- [ ] Close squawk 0050 with a reviewer sign-off — its regression net held in both
      the behavior test and the HAT, but it was never formally closed.
- [ ] One coupled leg on `knowledge-section.js` and its repository queries: squawk
      0087 (no `ORDER BY` tiebreak), squawk 0088 (unpinned armed-confirm invariant),
      and the per-item freshness field + signature widening from Recommendation 2.
      These are one leg's work, not three items.
- [ ] Carry the `App.confirmDelete` `revertMs` question to the closing flight — it
      was qualified against the squawk gate and **rejected** (fails "no design
      decisions" and "bounded blast radius": six call sites on a shared helper). The
      real question is not the duration but that a timed-out confirm silently re-arms
      with no feedback distinguishing that from having committed.
- [ ] Do not let squawk 0080 (`mcp_source_ids`) be filed a third time in a third
      form — it is live data loss today.

## Squawks Logged

Filed during the flight: **0080** (`mcp_source_ids` load gate), **0081** (create
routes 500 not 422), **0082** (router `replaceSub` stale `currentSub`), **0083**
(anyio CVEs), **0084** (CLAUDE.md's wrong default data directory — grounding),
**0085** (asset cache-busting keyed to app version).

Filed at close: **0086** (CLAUDE.md's restart guidance), **0087** (no `ORDER BY`
tiebreak), **0088** (unpinned armed-confirm invariant), **0089** (undocumented mock
`tool_calls`), **0090** (stale-agent union re-emits a pre-rename disable).

## Metrics

`make test-unit`: **4,769 passed, 10 skipped, 593 deselected, 17 warnings, 651.78s**,
exit 0, no flakes. Mission 24 series — F1 3,950 / 466.75s; F2 4,370 / 499.22s;
F3 4,547 / 638.25s; F4 4,649 / 636.62s; F5 4,732 / 606.19s; **F6 4,769 / 651.78s**.

Net **+37 tests**, the mission's smallest per-flight add — and *grounded*, unlike the
unexplained drift M23 F3's debrief recorded. The diff adds 76 test functions, 36 of
them browser; two existing unit tests were **inverted** rather than added as DD-17
made the discriminator unconditional, which accounts for the shortfall exactly.

Per-test 128 → 137 ms is **not** a regression from this flight: 137 ms is exactly
F4's figure and the series oscillates 137/128/137 with no monotone trend. CPU
utilisation 24%, so the lane is dominated by async waits, not compute.

Browser lanes — `studio` **176 passed / 3 skipped, 370.38s**; `system` **119 / 0,
197.44s**; `shared` **174 / 3, 98.44s**. Total **469 passed, 6 skipped, 0 failed,
666s**, no flakes, no reruns. Three lanes rather than one, because the flight's 11
Administration tests live in `system` and two modified files live in `shared` —
running `studio` alone would have left 13 touched browser tests unexercised.

`system` and `shared` had **no prior recorded baseline in any debrief**; these
figures establish one. `shared` is the complement lane, so it silently absorbs every
new browser test file until someone gives it an area glob — worth a trend line.

The studio-lane flake M23 F3 recorded (squawk 0035's standing disposition) did not
appear here or in M23 F4. Two consecutive clean runs is not closure, but it gives
the next debrief a third data point rather than a re-discovered question.

Lint: `ruff check` clean, `ruff format --check` 449 files already formatted.
