# Flight Debrief: Mission Close

**Date**: 2026-09-20
**Flight**: [Mission Close](flight.md)
**Status**: completed *(the contested label is resolved — see "Addendum, 2026-09-22" at the end)*
**Duration**: 2026-09-19 planning → 2026-09-20 landed
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

Four recorded obligations that had outlived the flights meant to carry them are
closed: `get_vector_store()`'s missing shutdown hook (a mission Known Issue
deferred four times), the detach → rename → reattach hole that silently dropped
an operator's disable, an inventory row that rendered nothing a content change
would alter, and the release gates Flight 6 listed and left unowned. Both
mission open questions are answered. Squawks 0087 and 0088 are closed with
sign-offs.

### Mission Criteria Advanced

- **Existing installs upgrade, unit gate green, frozen Windows installer builds
  and runs** — advanced substantially. 4,810 unit tests pass; the frozen build
  produced `the-one-setup-0.8.1.exe` with all nine doctor gates OK.
- **Operator can inspect a knowledge base's contents and metadata** — the item
  row now renders freshness, so a content-only edit is visible.
- **A knowledge base can be attached to and detached from any agent in Studio
  (behavior-test-backed)** — **NOT advanced to tickable.** The spec is
  re-authored and `active`; the 18-step walk has not run. This is the criterion
  named *first* in this flight's own Contributing to Criteria.

### Checkpoints

Six of seven met. The unmet one is the behaviour test.

## What Went Well

**Falsification over assertion, paid for repeatedly.** Legs 01 and 03 both
contain cases where the implementer deliberately broke its own fix to watch the
guarding test fail, then reverted (AC-4c, AC-7a, AC-16, AC-10a). This is more
expensive than "the test is green" and it was paid anyway. It earned its keep
once, sharply: falsifying squawk 0088's invariant revealed the failure mode is
worse than the squawk described — a rebuild doesn't fail to arm the confirm, it
arms an **invisible detached node** while the displayed summary shows nothing.
A green suite would never have surfaced that.

**The band-before-the-data discipline held.** DD-5's tolerance band was written
into the flight log before the 500k rung ran, derived from two calibration runs
rather than assumed. When the result came back inside the band, the `i8`
`build_s` deviation of +8.18% was still recorded as **larger than run-to-run
noise (≤2.0%) and therefore unexplained**, rather than waved through on a
technically-passing verdict.

**One shared helper genuinely eliminated a drift class.** The Developer grepped
the tree for the raw literal `"knowledge.walk_skips."` and found it in exactly
one place — `walk_skip_counters_key`'s own body. All four call sites import it;
the cleanup tests read back through the same helper the write site used, so a
drifted cleanup key would be caught rather than masked. This is elimination by
construction, not by convention.

**DD-8's prose gate became a mechanical test, and that generalizes.** "Is this
a feedback change or an interaction change?" is the kind of question that
produces disputes. The three conditions that replaced it — click count
unchanged, arm/commit decision still governed by one class, `revertMs`'s role
unchanged — are checkable by anyone with no context. Exportable to any future
decision hinging on a fuzzy distinction.

**The squawk/flight separation held under pressure.** Squawks 0083 and 0050
were deliberately not cleared in parallel with the legs, because mixing squawk
edits into an uncommitted flight tree would contaminate both records. Squawks
0091 and 0092 were found mid-flight and deferred rather than folded in.

## What Could Be Improved

### One failure mode, four costumes

This is the flight's dominant finding, and it is the Flight Director's.

| # | Incident | The instrument | The truth |
|---|---|---|---|
| 1 | **DD-10** | `grep 'simd\|simsimd\|numkong'` returned nothing | The identifier is `usearch_acceleration`. The field had existed since Flight 2 Leg 5 |
| 2 | **DD-13** | A docstring saying the derived name is "independent of the composition of the set" | `_HASH_LENGTHS` widens 8→12→16 sixty lines below |
| 3 | **"six call sites"** | Copied from the Flight 6 debrief's prose, stamped `verified` | 13, across 8 files — including the credential-rotation confirm |
| 4 | **"three list queries"** | Squawk 0087's own Report | Four (squawk 0091) |

The Architect's verdict: *"These four incidents are one failure mode, not
four — verifying that a secondary description says what the decision needs,
instead of re-deriving the fact from the primary source."*

Two aggravating facts:

- **Flight 6's debrief already named this**, as Key Learning #2, after two
  prior instances, both the Flight Director's. DD-10 is the third. **A written
  lesson failed to intercept its own next recurrence.**
- **A review praised the false claim.** DD-10 was called "the sharpest finding
  of the review" by the Architect at flight design. Two review passes accepted
  a confidently-stated grep with visible zero output; a third falsified it. The
  review layer was fooled by the *shape* of evidence rather than asking whether
  the instrument could express the thing.

The log records this pattern — twice, explicitly — **and changed nothing about
the process that produces it.** That is the gap. Recommendation 1 closes it
mechanically, because vigilance has now failed three times.

### The flight ran past its own stated blocker

The Prerequisites section says verbatim: *"Squawk 0083 completed (`anyio` →
4.14.2) — **Blocks the gates leg**; the frozen Windows build must be verified
after the bump."*

The gates leg ran with 0083 still `open`, and the frozen build was verified
**before** the bump — the reverse of what that line requires. `pip-audit` was
recorded as failing with an owner instead of the leg being held.

That may have been the right call. **It was not a call anyone made.** The
prerequisite was never revisited; a stated hard gate became a soft owned gap by
default. Found by the Architect at debrief, not during execution.

Worse: **the entire Prerequisites checklist was never reconciled** — all four
items still unticked at landing, including PR #208, which the Flight Director
merged personally. The Completion Checklist was reconciled with care. The
checklist directly above it was not looked at. *The instrument beside the one
being checked.*

### A sixth instance, found by running the behaviour test — and a new shape

*Added 2026-09-21, during the `kb-studio-round-trip` run this debrief's first
action item called for.*

**Instance five — citing the wrong system's documentation.** Judging step 7's
degrade-line clause, the Flight Director told the Validator that
`[hidden]{display:none!important}` is "this project's own documented reset
(CLAUDE.md)". It is not. That line appears nowhere in this project's
`CLAUDE.md` or `agents.md`; the project CSS carries only scoped rules
(`.tabpanel[hidden]`, `.banner[hidden]`). The text came from the Flight
Director's **own operating environment's tooling documentation** and was passed
downstream as project evidence. The Validator checked the source, found it
absent, and noted its conclusion did not depend on the citation — native HTML
`hidden` is UA-default `display:none` by standard. The verdict survived; the
citation trail would have been poisoned.

This is a **worse shape** than instances 1-4. Those substituted a description
of the code for the code. This substituted *a different system entirely* for
the project — which Recommendation 1 as written does not catch, because the
source was not weak, it was foreign.

**Instance six — verifying the environment but not the build.** The Flight
Director prepared the run's preconditions and verified, carefully, that the dev
instance owned a scratch data directory (`/proc/<pid>/environ`, per squawk
0084's lesson), was not port 8484, and held clean state. It never checked
whether the instance was running **the code under test**.

The **Executor** caught it at step 8: `GET /status` returned no
`content_freshness` key at all — not null, absent. It traced the field to
commit `e7fea7e` (2026-09-20 18:50) against a server process started
**2026-09-19 14:11**, and cited this project's own rule that `the-one serve`
has no `--reload`. Seven checkpoints had been judged against the *previous
flight's backend*.

**Why it stayed invisible is the generalizable part.** Static JS and CSS are
served from disk per request, so Leg 2b's `.confirm-lapsed` cue and Leg 2a's
rendered `kb-item-indexed-at` field were genuinely live and genuinely correct.
Only the Python was stale. **The run looked healthy because the half being
observed was the fresh half.** A partially-stale environment produces evidence
that is locally valid and globally meaningless — and nothing in the apparatus
scan was looking for it.

Operator decision: restart and re-run all eighteen steps from scratch. The
seven passes became evidence about a build nobody ships. Confirmed by the
restart itself: `content_freshness` and `folders[].skipped_dirs` /
`skipped_entries` were absent thirty seconds before and present thirty seconds
after — the restart was necessary, not precautionary.

**This vindicates running the behaviour test rather than deferring it again.**
Had the flight been marked `completed` on the strength of a re-authored spec
that was never executed, none of this would have surfaced. The spec was
repaired correctly; the *environment* was wrong, and only running it could show
that.

### The label

The Architect's finding, recorded here rather than argued away:

> *Both `git log` and `flight.md` call this **"landed"** while the PR is still
> draft and the criterion the flight exists to satisfy is unticked — a reader
> skimming the Status line, rather than the ~350-line Post-Flight section,
> would reasonably conclude more is done than is. This is the one place I'd
> call over-claiming rather than honest deferral: not in the substance, but in
> the label.*

And on the comparison this flight drew with Flight 6:

> *The comparison ("this is not the Flight 6 failure repeating") is asserted by
> the Flight Director about the Flight Director's own work, with no independent
> reviewer checking whether "owned" is actually sufficient. It reads as true on
> the evidence, but nothing in the process forced that check the way the
> Citation Audit forces evidence-checking elsewhere.*

Both stand. "Recorded and owned" is a real improvement on Flight 6's *unowned
and silently dropped* — but it is not the same as the mission being closable,
and the status word should not imply that it is.

### Latent trap in the test suite — the code-level analog

`the_one/vectors/_store.py:142` widened `close()` to take `skip_kb_ids`. Three
test stubs still declare the old shape:

- `tests/test_db_api.py:1575` (`_RecordingStore`)
- `tests/test_db_api.py:1703` (`_BoomStore`)
- `tests/test_db_api.py:2545` (`_StubStore`)

Dormant today — that fixture builds a bare `FastAPI()` that never enters
`lifespan`, so `close_vector_store()` never reaches them. But the Developer
traced the failure mode if it ever does, and it is exactly this flight's theme:

> *`app.py:553-558` wraps the real `close_vector_store()` call in a bare
> `try/except Exception: logger.exception(...)`. If any future refactor moves
> these tests onto the real app+lifespan, the resulting `TypeError` would be
> silently swallowed by production's own defensive handling — the route
> assertions would still pass, hiding both the stub's protocol drift and the
> fact that a real flush was silently skipped. An instrument that structurally
> cannot detect the condition it would need to detect, protected by the exact
> error-handling discipline meant to make shutdown robust.*

Notably, the Developer **did not find a newly-introduced assertion that cannot
fail**. The two "assertion that cannot detect what it claims" defects it did
find (squawks 0091, 0092) are pre-existing and were *found by* this flight.

### Structural

**Deferred commit cost more than it bought.** Four line citations in Leg 03
drifted *within the flight*, because Leg 02's uncommitted edits shifted them —
a Citation Audit true at authoring and false at execution. The Architect's
point is sharp: the convention exists to avoid mixing squawk work into flight
commits, but that is a **branch hygiene** problem, solved by keeping squawks on
their own branch, not by refusing to commit within the flight branch.

**Idling agents on multi-hour jobs was a structural mistake.** Two Developers
burned ~50 tool calls between them waiting on Concourse rungs and re-verifying
finished work. The Flight Director eventually moved to `setsid nohup … &
disown` plus backgrounded watchers, spawning agents only when interpretive work
existed — by Legs 04 and 05 that was the standing pattern. The fix arrived; the
cost was paid first.

**The methodology has no mid-leg escalation signal.** AC-9 asked a Developer to
pause, hand a decision to a human, and resume the same leg. None of
`[HANDOFF:review-needed]`, `[HANDOFF:confirmed]`, `[BLOCKED:reason]`,
`[COMPLETE:leg]` means that, and `[BLOCKED:…]` means *revert* — which would
have discarded hours of measurement. Caught at design review and resolved by
pre-splitting the leg, which only works because that pause point was known at
design time. An unforeseeable one still has nowhere to land.

### Smaller

- **A watcher keyed to the wrong PID.** `setsid` forks, so `$!` named the bash
  wrapper, not the `fly` client. It would have reported a rung complete while
  it ran. Replaced with a build-state watcher that reports on *every* terminal
  state — because a filter that only matches success is silent on a crash.
- **A commit sha written into two squawk sign-offs, then amended**, invalidating
  both references. Fixed with a follow-up rather than a third amend.
- **"Four of four legs done"** when there were five — caught by the operator.
  The same enumeration failure, applied to the flight's own leg list, in a
  sentence that contradicted itself one line later.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 2 split into 2a/2b as mandatory, not optional | Decided work should not be held behind an undecided design | **Yes** — split on decidedness, not size |
| Operator overrode DD-5's letter to stop at 500k | The extrapolation *confirmed*; DD-5 only modelled divergence | **Yes** — give ladders a two-sided checkpoint |
| Gates leg ran past its stated blocker | Nobody revisited the prerequisite | **No** — this is the defect |
| Developers spawned to wait on multi-hour jobs | Early legs; corrected by Leg 04 | **No** — detach and poll |

## Key Learnings

1. **A written lesson does not intercept its own recurrence.** Flight 6's Key
   Learning #2 named this exact failure and the Flight Director wrote it. DD-10
   is its third instance. Lessons need mechanical enforcement, not restatement.
2. **A negative result is only evidence if the instrument can express the
   positive.** Three greps, one `ps` filter, one PID watcher, one `head -3` —
   all of them "found nothing" about things that were there.
3. **An enumeration in a source artifact is a claim, not a count.** Three
   separate under-counts this flight, each copied forward from prose.
4. **Check the instrument beside the one you are checking.** The Completion
   Checklist was reconciled meticulously; the Prerequisites checklist directly
   above it was never looked at.
5. **Documenting an error is not the same as not making it.** This flight's log
   is unusually self-critical, and the Architect was asked directly whether
   that substitutes for rigor. Its answer: mostly no — the falsification tests
   are real rigor, not decoration — *except* where the flight graded its own
   comparison to Flight 6 with nothing forcing the check.

## Recommendations

1. **Make the Citation Audit resistant to the failure that has now beaten it
   five times.** *(Widened 2026-09-21 after instance five.)* The original
   primary/secondary distinction does not catch citing **another system's**
   documentation as the project's — that source was not weak, it was foreign.
   Add: **a citation to project documentation must be verified against the
   project tree at audit time** (`grep` the repo), never recalled. And: Any row whose evidence is *"a search returned nothing"* must carry
   a **positive control**: proof the same pattern matches a known-present
   instance, or the actual identifier read from the code. And mark each row
   `primary` (read the control flow) or `secondary` (docstring, prior debrief,
   someone else's count) — a `secondary` row requires **re-derivation**, not a
   match-check, before it can be stamped verified. Matching a description to a
   description is not verification.
2. **Fix the status vocabulary.** Do not call a flight `landed` while a
   Completion Checklist item blocks the flight's own headline mission
   criterion. Either withhold `landed` or introduce a status that names the gap
   at the same visibility as the headline.
3. **Switch to per-leg commits on the flight branch.** Real history, no
   cross-leg citation drift, bisectable; flight-end review becomes
   `git diff <flight-start>..HEAD`. Keep squawks off the flight branch by
   branch discipline, which is what that problem actually is.
4. **Name the detached-launch pattern in the leg-execution crew file.** Launch
   long external jobs detached, record the handle, don't hold an agent blocked
   on one; spawn or resume only when there is interpretive work.
5. **Add a mid-leg operator-decision signal** (e.g.
   `[HANDOFF:operator-decision]`) with a defined resume contract, so a
   foreseeable pause point doesn't require pre-splitting a leg and an
   unforeseeable one has somewhere to land.
6. **Re-verify a prerequisite at the leg that depends on it**, not only at
   planning. Leg 04 did this for the Concourse worker and caught nothing;
   Leg 05 did not do it for squawk 0083 and ran past a stated blocker.

## Action Items

- [~] Run `kb-studio-round-trip` — **started 2026-09-21.** First attempt void:
      seven checkpoints passed against a stale backend before the Executor
      caught it (see "A sixth instance" above). Re-running all 18 steps on the
      restarted instance. The criterion stays unticked until it is green.
- [ ] **Add a build-freshness check to the standing apparatus scan** — a
      behaviour test must confirm the instance is serving the *code under
      test*, not merely that it is the right instance with the right data
      directory. This run had no such check and it cost seven checkpoints.
- [ ] Clear squawk 0083 so `pip-audit` can go green, then re-verify the frozen
      Windows build **after** the bump, as the prerequisite requires
- [ ] Close squawk 0050 (write-up + sign-off; fixed in Flight 6, never closed —
      now carried across two flights)
- [ ] Squawk candidates from this debrief: the `VectorStore.close()` stub drift
      (`test_db_api.py:1575,1703,2545`); `sweep_fusion_constants.py` unwired to
      any test or CI lane while monkeypatching private `retrieval.py` internals
- [ ] Investigate the unverified residual: `asyncio.to_thread`'s non-daemon
      executor may delay process teardown if a cancelled worker thread is still
      running at exit
- [ ] Carry Recommendations 1-6 into the mission debrief — 1, 3, 4 and 5 are
      methodology changes, not project work

## Metrics

`make test-unit` (debrief run, verbatim, alone, foreground): **4,810 passed,
10 skipped, 616 deselected, 694.75s**, exit 0, **zero failures, zero flakes**.

Mission 24 series: F1 3,950/466.75s · F2 4,370/499.22s · F3 4,547/638.25s ·
F4 4,649/636.62s · F5 4,732/606.19s · F6 4,769/651.78s · **F7 4,810/694.75s**.
Net **+41**, comparable to F6's +37 — consistent with a defect-closure flight.

This run is a **second clean data point on the identical collected count
(4,810)**: the Leg 04 gate run collected 4,810 with one failure
(`test_kb_watcher.py::test_drain_three_live_entries_under_a_second`); here that
same test passes. Deselected count identical at 616, so no marker drift. The
flake diagnosis is confirmed rather than assumed.

Per-test cost 140ms (gate) → 144ms (debrief), at or just above the F1-F6 band
of 114-141ms. Plausibly host-load noise — the host carried intermittent memory
pressure from unrelated processes throughout, which is independently
attributed as the cause of the gate run's flake.

Browser lanes (cited, not re-run): **530 passed / 6 skipped / 2 failed** in
940.50s against F6's 469/6. Both failures matched the standing squawk-0035
full-lane timing-flake signature and passed in isolation; the one in a file
this flight modified was additionally run as its whole file (29/29).

Lint: `ruff check` clean, `ruff format --check` 452 files.

`pip-audit`: **NOT clean** — `anyio` 4.13.0, CVE-2026-63374 and CVE-2026-64847.

Frozen Windows build: **PASS** — `the-one-setup-0.8.1.exe`, 135,040,950 bytes,
nine of nine doctor gates OK.


## Addendum — 2026-09-22: the contested label, resolved

This debrief was written on 2026-09-20 with the flight's own first-named
criterion unticked and its PR in draft. The Architect's finding was recorded
rather than argued away:

> *Both `git log` and `flight.md` call this "landed" while the PR is still draft
> and the criterion the flight exists to satisfy is unticked … not in the
> substance, but in the label.*

**That finding was correct, and it has now been closed by doing the work rather
than by relabelling it.** `kb-studio-round-trip` ran on 2026-09-22:
**17 pass / 1 inconclusive / 0 fail** across all 18 checkpoints, strict
one-checkpoint-at-a-time. The spec is `active`, the criterion is ticked, the
`pip-audit` item is closed by squawk 0083, and PR #209 is out of draft. The
Completion Checklist now carries one unticked item — the merge itself, which is
the operator's call.

**What the run added that the debrief could not have known.** All five repairs
from the 2026-09-21 revert held. Two clauses that had never actually been tested
— step 5's `[continuous-session]` and step 9's full step-2-to-9 span — were
exercised for the first time rather than recorded UNEXERCISED, the latter
verified by two independent outside readers via read-only calls neither agent
could have coordinated to fake. Step 8's rewritten `content_freshness` clause
reproduced the exact ~1 ms divergence that forced its rewrite and **passed**,
where the old equality clause would have failed correct behaviour — which is the
strongest available evidence that the rewrite fixed the clause rather than
merely loosening it.

**One new spec defect (#15) was found, fixed, and its fix verified in-run.** Step
9's mandated page continuity collides with step 12's out-of-band `PUT` — the only
way to set `disabled_tools`, since there is deliberately no UI — leaving the
client stale by step 13, which then reads as a DD-13 failure when DD-13 is fine.
Ruled inconclusive: *the test failed, not the system.* The fix (an explicit
fresh-load beat) was executed during the run as step 13-bis and passed.

**This is the second time in this flight that the same defect class produced a
false positive against correct code** — first DD-10's grep that could not match
the identifier it searched for, now step 13's clause that could not distinguish
the behaviour it claimed to test. The flight's own Key Learning #2 named the
class; it recurred anyway, which suggests naming it is not sufficient
prophylaxis. What actually caught it this time was procedural, not analytical:
an independent judge who **held a verdict and demanded a discriminating
experiment** instead of ruling on the available evidence.

**On the second Architect finding** — that the flight's comparison with Flight 6
was "asserted by the Flight Director about the Flight Director's own work, with
no independent reviewer checking whether 'owned' is actually sufficient" — that
one **also stands, and is now partly answered by outcome**: the owned gaps were
in fact closed (`pip-audit` by the squawk that owned it, the behaviour test by
this run), which is what "owned" was supposed to mean. But the finding's
procedural point is untouched: nothing in the process forced that check, and it
was closed by follow-through rather than by any mechanism.

### Carried out of the run, not swept

- **Studio's agent-editor save is last-writer-wins with no staleness detection.**
  Raised as a **flight candidate, not a squawk** — it fails the squawk
  qualification gate on two of four criteria (needs a design decision; touches a
  shared interface). Logging it as a squawk would have been using the squawk
  path as a workaround for scope, which the methodology explicitly warns against.
- **Literal restart-resume remains unproven.** Step 10 won its race first try
  (+0.0424 s, bracketed 9.6 ms on the other side) but caught the snapshot at
  `indexed: 0` — the spec's own named evidence ceiling. Aggregate resume is well
  evidenced; the `content_hash`-survival mechanism was never exercised.
- **Apparatus: untracked pages spawn during error recovery.** *"Exactly one page"
  is an invariant nobody enforces; it was discovered by accident.* Must be
  enforced before this apparatus runs unattended.
- **Three weakly-falsifiable clauses named** for a future spec revision (steps 3,
  5 and 7), each with the reason it cannot currently fail.

Run log: `tests/behavior/kb-studio-round-trip/runs/2026-09-22-01-05-35.md`.
