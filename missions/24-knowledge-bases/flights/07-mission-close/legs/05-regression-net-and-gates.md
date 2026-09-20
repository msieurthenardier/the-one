# Leg: regression-net-and-gates

**Status**: landed
**Flight**: [Mission Close](../flight.md)

## Objective

Re-author `kb-studio-round-trip` so Mission 24's closing regression net is
re-runnable rather than nominally present, add the large-folder settle variant,
and run every release gate by hand — each with this leg as its named owner.

## Context

**`kb-studio-round-trip` is Mission 24's only non-`active` behaviour spec.**
Its status line records five structural defects; **the run logs carry six** —
step 9's vacuous-pass problem (AC-1a) is diagnosed in
`runs/2026-09-18-13-14-52.md:735-742` and never made it into the status line.
**Read the logs, not the status line.** The Flight 6 debrief lists this
re-author as an action item owned by this flight.
Until it is `active`, the mission criterion *"a knowledge base can be attached
to and detached from any agent in Studio (behavior-test-backed)"* cannot be
honestly ticked — the backing is a spec that cannot be re-run.

**Step 8's defect is already fixed by Leg 2a.** Its second clause ("the edited
file re-indexes") had no browser observable at all, because the item row
rendered only path and status. Leg 2a shipped the freshness field and the
`content_freshness` aggregate, so that clause now has a surface. This leg is
the one that can finally write it.

**This mission branch has no CI lane.** Concourse tracks `main`, and
`pr-lint.yml` triggers only on PRs into `main`, so every gate runs by hand and
is recorded. That is why this leg exists as a leg rather than as a checklist.

**`pip-audit` cannot go green.** Squawk 0083 (`anyio` 4.13.0, two CVEs, fixed
in 4.14.2) is still `open`. This leg **records the known finding against that
squawk** rather than faking a pass or bumping the dependency inline —
dependency work on an uncommitted flight branch would mix a squawk's record
into a flight commit. Flight 6 handled it the same way.

Legs 1, 2a and 2b have landed but are **not committed**. Leg 3's measurement
runs may still be in flight; its numbers feed this leg's flight-log metrics
section but nothing else here depends on them.

## Inputs

- `tests/behavior/kb-studio-round-trip.md` — 18 steps; its `**Status**: draft`
  line enumerates **five** defects. The run logs carry a **sixth** (AC-1a)
- `tests/behavior/kb-studio-round-trip/runs/2026-09-18-13-14-52.md` and
  `.../2026-09-18-reverify.md` — the run logs whose closing summaries diagnose
  them
- `tests/behavior/kb-folder-index-round-trip.md:99` — the `Variants` section;
  its `live-kill` variant already generates 2,000 × 50 KB files, which R13's
  settle variant reuses
- `.flightops/ARTIFACTS.md` — the canonical "Behavior Test — Spec" format the
  re-authored spec is validated against
- `squawks/0083-anyio-cve-bump.md` — the known `pip-audit` finding
- `ci/README.md` — the by-hand gate commands and the `fly execute` shapes

## Outputs

- `kb-studio-round-trip` at `**Status**: active`, re-runnable
- A `large-folder settle` variant on `kb-folder-index-round-trip`
- Every gate run and recorded, with outcomes including the known failure
- Flight log carrying the full metrics section

## Acceptance Criteria

**Spec re-author**

- [x] AC-1 — **Steps 9 and 10 are no longer mutually unsatisfiable.** Step 9
      stops and restarts the instance; step 10 requires attaching "during this
      same browser session — do not reload the page first". A restart ends the
      session.
      **Default resolution: a LOCAL SWAP — run step 10 first, then step 9
      (…8, 10, 9, 11…).** This satisfies both assertions with **no coverage
      loss**: nothing in steps 11-18 needs continuous-session state (they use
      fresh-load reads per the run log's FINDING 7), and step 9's restart
      threatens nothing downstream once it runs after step 10.
      **Do NOT move step 9 to the end of the spec.** By step 18 both knowledge
      bases have been deleted (steps 17-18), so step 9 would have nothing to
      index and would need a fresh throwaway knowledge base and folder — setup
      this leg does not budget for.
      *(An earlier draft of this criterion said "state what is consequently no
      longer covered", which presupposes a trade-off the local swap does not
      require. Only state a coverage loss if you deviate from the local swap —
      and say why you deviated.)*
- [x] AC-1a — **Step 9's assertion must be WINNABLE, not vacuous.** This is a
      **sixth** defect, named in the run log (`runs/2026-09-18-13-14-52.md:735-742`)
      but **not** in the spec's status line, which lists five. The log's ruling:
      *"Step 9 may pass vacuously… a spec follow-up to size the fixture so the
      assertion is winnable. It is not to be faked by enlarging the fixture
      mid-run, which would perturb steps 5 and 8's counts."* On a 3-4 file
      fixture an index pass completes faster than an operator can stop the
      instance, so "stop it mid-pass" catches nothing and the crash-recovery
      assertion is never exercised.
      Size the spec's mandated fixture so a pass is long enough to interrupt —
      **at authoring time, in the Preconditions**, never by growing it mid-run.
      If the fixture that makes step 9 winnable would perturb steps 5/8's
      counts, say so and resolve it deliberately (a second folder registered
      only for step 9 is one option).
      *(This leg was drafted from the spec's status line. The run log carries
      one more defect than the status line does — which is why Implementation
      Guidance 1 says to read the logs first, and why this criterion exists
      only because the design review did.)*
- [x] AC-2 — **Steps 5, 8 and 10's fresh-mount preconditions are made real.**
      Each carries a precondition that a fresh mount silently satisfies, so the
      step passes without testing what it claims. Either make the precondition
      falsifiable or delete it and say what is actually being asserted.
- [x] AC-3 — **Step 6's ordering clause becomes falsifiable.** "Chunks render
      in sequence order" is unfalsifiable against the mandated fixture (a
      single-chunk file cannot exhibit an order). Mandate a fixture that can
      fail it, or drop the clause.
- [x] AC-4 — **Step 2's action moves out of the Expected Results column.** Per
      `.flightops/ARTIFACTS.md`'s spec format, Actions and Expected Results are
      distinct columns; an action in the results column cannot be judged.
- [x] AC-5 — **Step 8's second clause gets its observable.** Leg 2a shipped the
      per-item freshness field and `get_kb_status`'s `content_freshness`
      aggregate. Write the clause against the field the operator can actually
      see, and mark the row's cross-frame clause `[mixed-frame]` only if a
      supplementary observable is genuinely needed.
- [x] AC-6 — The spec validates against `.flightops/ARTIFACTS.md`'s required
      sections: Intent, Preconditions, Observables Required, Steps, Out of
      Scope. Status becomes `active`. **`Last Run` is NOT edited** — the Flight
      Director runs the test and the run skill writes that.
- [x] AC-7 — The spec's Preconditions still name a **non-default port and a
      scratch data directory**, and still reference CLAUDE.md's safety rule by
      name rather than restating credential mechanics.

**R13 — large-folder settle variant**

- [x] AC-8 — A `large-folder settle` variant added to
      `kb-folder-index-round-trip.md`'s Variants section, exercising the
      `starting` allowance and the `idle`/`running` tolerance (F4 debrief
      Rec. 3). It reuses the `live-kill` variant's existing 2,000 × 50 KB
      fixture generator rather than authoring a second one.
- [x] AC-9 — The variant states its own flake profile honestly, as `live-kill`
      does ("higher fidelity, flake-prone by construction — run only when the
      seeded variant passes").

**Gates — this leg is the named owner of every one**

- [x] AC-10 — `make lint` clean (`ruff check` + `ruff format --check`).
- [x] AC-11 — `make test-unit` green, run **verbatim, alone, foreground**.
      Record the count against the mission series (F1 3,950 → F2 4,370 →
      F3 4,547 → F4 4,649 → F5 4,732 → F6 4,769 → F7 …).
- [x] AC-12 — **Full** `make test-browser` with `TEST_TIMEOUT=3600` — all four
      lanes, not a selection. Record per-lane counts. **Note the standing
      full-lane flake** (`conftest.py`'s "Standing pattern — full-lane timing
      flakes (squawk 0035)"): a test that fails only under a full-lane run and
      passes in isolation is that known pattern, not a regression — but it must
      be named, isolated, and re-run, never waved through.
- [x] AC-13 — `pip-audit` run against the **release closure** (the `uv export`
      the pr-lint workflow audits, fed to `pip-audit --disable-pip -r`, per
      `ci/README.md`). **It will report `anyio` 4.13.0's two CVEs.** Record the
      finding against squawk 0083 and state plainly that this gate is **not
      green** and cannot be until that squawk lands. Do not bump the dependency
      here.
- [x] AC-14 — A **frozen Windows build** via
      `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out`,
      recorded as pass or fail. Launch it detached and poll with `fly watch`
      (Flight 2 build 59's client-death lesson). **Do not run concurrently with
      Leg 3's ladder** — same shared worker.
- [x] AC-15 — Documentation reconciled: CLAUDE.md and `the_one/agents.md`
      reflect this flight's new surfaces (the shutdown hook, the
      `get_kb_status` additive keys, the skip-counter projection, the
      `.confirm-lapsed` cue, the new CI task). Legs 1/2a/2b each updated docs;
      this is the reconciliation pass that checks they agree.

**Recording**

- [x] AC-16 — Flight log carries the full metrics section: unit count and
      delta, per-lane browser counts, lint, `pip-audit`'s known failure, the
      frozen build's outcome, and any flakes with their disposition.
- [x] AC-17 — Every gate's outcome is recorded **as observed**, including
      failures. A gate that did not run is recorded as not-run, never as
      passed. *(Flight 6 left two Completion Checklist items unowned and
      unexecuted; this leg exists so that cannot recur.)*

## Verification Steps

- AC-1…AC-7 — read the re-authored spec against `.flightops/ARTIFACTS.md`'s
  format section. The Flight Director runs the test afterwards via
  `/mission-control:behavior-test kb-studio-round-trip`; **the Developer does
  not run it** (the run skill orchestrates its own Executor/Validator crew).
- AC-10 — `make lint`
- AC-11 — `make test-unit`
- AC-12 — `TEST_TIMEOUT=3600 make test-browser`
- AC-13 — per `ci/README.md`'s pip-audit recipe
- AC-14 — `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out`

## Implementation Guidance

1. **Read both run logs before touching the spec.** The five defects are
   diagnosed in their closing summaries with more precision than the status
   line carries. Re-authoring from the status line alone will reproduce the
   ambiguity that caused them.

2. **AC-1 is the hard one.** Steps 9 and 10 conflict because one restarts the
   instance and the other forbids a page reload. Resolving it is a real
   authoring decision — say in the spec which way you resolved it and what is
   consequently no longer covered, rather than quietly reordering.

3. **Do not weaken an assertion to make it pass.** This spec's value is that
   most of its assertions are *negative* — about state that must not move —
   and each exists because a specific defect was found. A re-author that turns
   a negative assertion into a happy-path check has destroyed the thing being
   re-authored.

4. **`pip-audit` will fail and that is the correct outcome.** Record it. A
   green gate here would be a false record, and the mission's own dependency
   stakeholder is the reason the audit exists.

5. **Sequence AC-14 against Leg 3.** Both want the Concourse Windows worker.
   Check whether a Leg 3 rung is in flight (`fly -t the-one builds`) before
   launching, and wait rather than contend.

6. **AC-12 takes ~13 minutes plus load.** `TEST_TIMEOUT=3600` is not optional —
   the default 1200s is tighter than the suite's own runtime and will kill a
   healthy run.

## Edge Cases

- **A full-lane flake that is NOT squawk 0035's pattern** — if a failing test
  also fails in isolation, it is a regression and this leg does not land until
  it is understood.
- **The frozen build fails for a reason this flight introduced** — that is a
  mission-criterion failure ("the frozen Windows installer still builds and
  runs") and must be reported, not recorded as a known issue.
- **The re-authored spec changes an id, route or shape another artifact
  depends on** — the flight's own DD guidance says a contract change is a
  deliberate re-author, not an inline fix. Say so if it happens.
- **Leg 3's 1M rung still running at AC-14 time** — wait. Two multi-hour jobs
  on one uncontainerised worker is how build 59 died.

## Files Affected

- `tests/behavior/kb-studio-round-trip.md`
- `tests/behavior/kb-folder-index-round-trip.md`
- `CLAUDE.md`, `the_one/agents.md` — reconciliation only
- `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`

## Citation Audit

Verified against the working tree on `flight/07-mission-close` (2026-09-20),
carrying Legs 1, 2a, 2b uncommitted:

| Citation | Status |
|---|---|
| `tests/behavior/kb-studio-round-trip.md` — `**Status**: draft` enumerating five defects; 18 step rows at `:86-103` | verified |
| Step 9 (`:94`) stops and restarts the instance; step 10 (`:95`) requires attaching "during this same browser session — do not reload the page first" (AC-1) | verified |
| Step 2 (`:87`) — "The second is refused…" carries the creation action in the results column (AC-4) | verified |
| Step 8 (`:93`) — "Both changes are reflected in the inventory without any operator action" (AC-5) | verified |
| `tests/behavior/kb-folder-index-round-trip.md:99` — `## Variants (optional)`, `live-kill` generating 2,000 × 50 KB files (AC-8) | verified |
| `squawks/0083-anyio-cve-bump.md` — status `open`; `uv.lock` still pins `anyio` 4.13.0 (AC-13) | verified |
| Mission unit-test series F1 3,950 → F6 4,769, from the Flight 6 debrief's Metrics section (AC-11) | verified |
| `tests/browser/conftest.py` — "Standing pattern — full-lane timing flakes (squawk 0035)" (AC-12) | verified — cited by Leg 2b's own report |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (or failures recorded as observed, per AC-17)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do **NOT** commit — the Flight Director commits after the flight-end review
- [x] Signal `[HANDOFF:review-needed]`
