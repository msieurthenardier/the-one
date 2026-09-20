# Leg: confirm-lapse

**Status**: landed
**Flight**: [Mission Close](../flight.md)

## Objective

Decide and implement what `App.confirmDelete` should do when its arm window
lapses, across all 13 call sites, and mechanically pin the third armed-confirm
invariant that squawk 0088 records as holding today with nothing enforcing it.

## Context

**DD-8 is deliberately undecided.** The operator's instruction was to
investigate before deciding, and the flight records that rather than
manufacturing a decision to look complete. This leg's *first output is a
finding*, not a patch.

The defect, stated precisely: **a confirm that times out re-arms with no
feedback, so the operator cannot distinguish "I let it lapse" from "I
committed."** The 3-second `revertMs` default is a symptom surface, not the
defect. The question failed the squawk qualification gate on two counts — "no
design decisions" and "bounded blast radius" — which is why it is a leg.

**The surface is 13 call sites across 8 files, not six.** The Flight 6 debrief
said six; the Citation Audit copied it and stamped it `verified` without
re-counting. Among the 13 is `areas/admin/system-page.js:81` — the
**API-credential rotation** confirm, the highest-consequence confirm in the
app. Any change here must not make that one easier to fire accidentally.

**Squawk 0088** rides along because it is the same helper's reliability: the
folder-delete confirm arms on a `<summary>` for 3 seconds while the page polls
every 5, so it only works because no render path rebuilds or rewrites an armed
folder's `<summary>`. Three behaviours hold that up; **only two have tests**.

Legs 1 and 2a have landed but are **not committed** — this flight defers commit
to the flight-end review. The working tree carries both. Do not revert or
re-stage them.

## Inputs

- `the_one/interfaces/web/static/js/confirm.js` — the whole helper (77 lines);
  `revert()`, the arm branch, the commit branch, `_confirmOriginalTitle`
- The 13 call sites:
  - `areas/studio/knowledge-section.js:979` (folder delete, armed on
    `<summary>`), `:1443` (knowledge-base delete)
  - `areas/studio/connector-editor.js:599`
  - `areas/studio/mcp-server-editor.js:1270`, `:1321`
  - `areas/studio/self-configuration-tab.js:1294`
  - `areas/studio.js:2080`, `:2116`
  - `areas/admin/system-page.js:81` — **API-credential rotation**
  - `areas/admin/provider-editor.js:509`, `:946`, `:951`
  - `areas/chat.js:1140`
- `squawks/0088-armed-confirm-summary-invariant-unpinned.md` — the three
  invariants and which two are tested
- **Line numbers above are WORKING-TREE relative**, re-enumerated after Legs 1
  and 2a landed uncommitted. Four of them shifted from the values an earlier
  draft carried (`knowledge-section.js` 962→979, 1412→1443; `studio.js`
  2066→2080, 2102→2116) because Leg 2a inserted lines above them. Re-run
  `grep -rn "confirmDelete(" the_one/interfaces/web/static/js/` before using
  any of them as a jump target — in a deferred-commit flight the tree moves
  under the citations between legs.
- `knowledge-section.js:1111` — `renderFolderFiles` writes `panel.filesEl` only;
  `:1128`, `:1153` — `renderAllItems` reaches panels solely through it
- `docs/ui-testid-registry.md`; `tests/test_ui_guards.py`

## Outputs

- A written finding covering all 13 call sites
- Either an implemented feedback change, or an escalation (see AC-3)
- A test pinning squawk 0088's third invariant
- Tests across `studio` (8 sites), `system` (4), `chat` (1), plus one
  lane-agnostic `confirm.js` contract test in `shared`
- Squawk 0088 closed; flight log updated

## Acceptance Criteria

**Investigation first (DD-8)**

- [x] AC-1 — A written finding in the flight log covering **all 13 call sites**,
      recording for each: what is armed, what the `[data-confirm-title]` target
      is, what the consequence of committing is, and whether a lapse there is
      currently distinguishable from a commit. This is a deliverable in its own
      right — it is what the operator asked for.
- [x] AC-2 — The finding states plainly whether the defect is uniform across
      the 13 or concentrated in some. A fix justified for one shape and applied
      to all 13 is how this helper accumulated its risk.
- [x] AC-3 — **Escalation gate, applied mechanically.** A change is
      **feedback-only** iff all three hold:
      1. the number of clicks needed to commit is unchanged;
      2. a click's effect (arm / commit) still depends **only** on today's
         binary `.confirm-delete` class — never on a new state the handler must
         branch on;
      3. `revertMs`'s role is unchanged — same thing starts it, same thing
         clears it.
      If the design needs the click handler to branch on anything beyond that
      class, it is an **interaction** change: **stop and report**, per the
      flight's Adaptation Criteria. Implementing it anyway is out of bounds.
      *(The prose test this replaced — "feedback vs interaction" — was not
      crisp enough to act on. The natural fix shape, a lapsed indicator that
      lingers until the next interaction, introduces a tri-state and would have
      been reasonable to call "just visual" while actually changing click
      semantics at 13 sites.)*
- [x] AC-3a — **If AC-3 fires, the leg does not freeze whole.** Squawk 0088's
      work (AC-10 … AC-12) is independent of DD-8's outcome and still lands.
      Report the escalation, land the invariant test, and mark the leg
      `landed` with DD-8 recorded as escalated.

**The fix, if it is a feedback change**

- [x] AC-4 — A lapsed confirm is distinguishable on screen from one that was
      never armed, and from one that committed.
- [x] AC-5 — The change lives in `confirm.js` and reaches all 13 sites through
      the shared helper. **No call site is special-cased.**
- [x] AC-6 — `areas/admin/system-page.js:81` (credential rotation) is not made
      easier to fire accidentally. State explicitly in the flight log how the
      change was evaluated against that site.
- [x] AC-6a — **`revert()` has THREE callers, not two, and a lapse marker must
      distinguish them.** It runs on (a) timer expiry — a true lapse; (b) a
      caller's transport-failure `.catch`; and (c) **the success path** —
      `system-page.js:87-91` calls `revertFn()` after a *successful* rotation,
      with a comment saying so, conveying success through a separate flash.
      A marker applied by simply decorating `revert()` would label a
      **successful credential rotation as "lapsed"** — contradicting AC-4 at
      precisely the site AC-6 exists to protect. The timer's callback must mark
      lapse distinctly from the `revertFn` handed to callers. This remains
      feedback-only under AC-3's test.
- [x] AC-7 — The capture discipline survives: `_confirmOriginalTitle` is still
      captured **only** in the first-click branch. Capturing on every call
      records the placeholder and a later revert overwrites the operator's
      data — `confirm.js`'s own header comment calls this out.
- [x] AC-8 — `revert()` remains idempotent and safe to call from a
      transport-failure path, since callers invoke `revertFn` from `.catch`.
- [x] AC-9 — Tests covering every call site across its real lane. Measured
      against `scripts/run-tests.sh`'s globs: **`studio` covers 8 of 13**
      (knowledge-section ×2, connector-editor, mcp-server-editor ×2,
      self-configuration-tab, studio.js ×2), **`system` covers 4**
      (system-page, provider-editor ×3), **`chat` covers 1**. That is 13/13 —
      **no call site's tests land in `shared`** today.
      *(An earlier draft said "the studio glob alone covers fewer than half",
      which is false — 8 of 13 is a majority. The substantive point stands:
      5 sites live outside `studio`, so `studio` alone is insufficient.)*
- [x] AC-9a — **One lane-agnostic contract test of `confirm.js` itself**,
      named so it falls to the `shared` complement lane. The helper has no
      "area"; its arm/commit/lapse/revert contract deserves a test that is not
      tied to any call site. This is what puts `shared` in scope — not an
      existing test that was miscategorised.

**Squawk 0088**

- [x] AC-10 — A test mechanically pins the third invariant: **an items-signature
      tick must not rebuild or rewrite an armed folder's `<summary>`.** It must
      fail if `renderAllItems` is changed to rebuild summaries — observe that,
      do not assume it.
- [x] AC-10a — **The tick must land inside the 3-second arm window.** A naive
      test that arms a confirm and then waits on the real pipeline (walk → hash
      → chunk → embed → 5s poll) will see the confirm auto-lapse before the
      tick arrives — failing or passing for reasons unrelated to the invariant,
      via the very mechanism this leg is redesigning. Drive the re-index and
      the `/items` refetch directly and assert on the response rather than
      sleeping. Leg 2a's `content_freshness` aggregate makes a content-only
      edit a real, triggerable signature change — use it rather than
      synthesising a tick.
- [x] AC-11 — The test pins the *invariant*, not the current implementation's
      call graph. A future refactor that keeps summaries intact by a different
      route should still pass.
- [x] AC-12 — Squawk 0088 updated to `completed` with Corrective Action and
      Verification filled in. **Do not write the Sign-Off** — the Flight
      Director writes it after the flight-end review.

**Gates**

- [x] AC-13 — New `data-testid`s registered in `docs/ui-testid-registry.md`;
      `tests/test_ui_guards.py` passes.
- [x] AC-14 — `make test-unit` green; the `studio`, `system`, `chat` and
      `shared` browser lanes green; `ruff check` and `ruff format --check` clean.
- [x] AC-15 — Flight log updated with AC-1's finding, AC-6's evaluation, and
      AC-10's observed falsification.

## Verification Steps

- AC-1/2 — read all 13 sites; the finding is prose in the flight log.
- AC-4 — a browser test that arms a confirm, waits past `revertMs`, and asserts
  the lapsed state is visually distinct from the never-armed state.
- AC-7 — a test that arms, lapses, re-arms, and asserts the title is the
  original — not `'Confirm delete?'`.
- AC-9 — `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio -x`,
  then `--lane system`, `--lane chat`, `--lane shared`.
- AC-10 — write the test, then temporarily make `renderAllItems` rebuild a
  folder summary and confirm the test fails. Revert and re-verify.
- AC-14 — `make test-unit` verbatim, alone, foreground.

## Implementation Guidance

1. **Read all 13 call sites before writing any code.** AC-1's finding is the
   leg's first deliverable and the operator's actual request. Do not start from
   a fix you already have in mind.

2. **Note what the helper already does on lapse.** `revert()` removes
   `.confirm-delete` and restores the title text, so the control *does* return
   to its resting appearance. The defect is not that nothing happens — it is
   that the resting appearance after a lapse is **identical to the resting
   appearance before any click**, so a returning operator cannot tell whether
   their click registered at all, or whether the lapse or a commit is what they
   are looking at.

3. **Watch for call sites where the title target is not a label.**
   `knowledge-section.js:962` arms on a `<summary>` with the folder-path span
   as the title target — the text being swapped is *the operator's own data*
   (a filesystem path), not a button label. `chat.js:1140` is similar (a
   session title). That asymmetry across the 13 is exactly what AC-2 asks you
   to characterize.

4. **The credential-rotation site deserves its own paragraph** in the finding.
   It is the only confirm whose commit has no undo and no visible row to
   disappear afterwards — **and it calls `revertFn()` on SUCCESS**
   (`system-page.js:87-91`), which is the trap AC-6a exists for. Read that
   handler before designing anything.

4a. **Record each site's reconciliation behaviour in AC-1's finding.** Squawk
   0088's invariant is specific to `renderFolders`' keyed move-don't-recreate.
   Nothing establishes whether `chat.js`'s session list, `studio.js`'s agent
   tiles, or `provider-editor.js`'s provider list rebuild wholesale on a
   background tick. If any do, a lapse cue applied by the now-detached old
   node's timer never renders on the live replacement — silently failing AC-4
   at the sites that are *not* knowledge-section.js.

4b. **Note the purge-history quirk at `studio.js:2116`.** Its `.then` never
   calls `revertFn()`, so after a successful purge the button reads
   "Confirm Purge?" until the editor re-renders. Not this leg's to fix, but it
   changes what "distinguishable from committed" means at that one site:
   stuck-armed-forever, not reverted.

4c. **Say whether the lapse cue is announced to screen readers.**
   `self-configuration-tab.js:1294` already carries a `role=status` live-region
   announcement for the *arm* transition (added for WCAG 4.1.2, because the
   accessible name overrides the swapped title text). Whether the lapse signal
   reuses that idiom or is purely visual is a decision, not an omission — make
   it explicitly.

5. **For squawk 0088, pin the invariant, not the call graph.** A test that
   asserts `renderAllItems` calls `renderFolderFiles` pins today's
   implementation and will fail on a harmless refactor. A test that arms a
   confirm on a folder summary, drives an items-signature tick, and asserts the
   summary node is the *same node* with the *same armed state* pins the
   property that actually matters.

6. **Do not change `revertMs`'s default as the fix.** The operator's
   instruction and the debrief both say the duration is not the defect. If the
   finding concludes otherwise, that is AC-3's escalation, not a quiet default
   change.

## Edge Cases

- **Two confirms armed simultaneously** on the same page (e.g. two folder
  rows). State in the finding whether that is reachable and whether the fix
  behaves.
- **A confirm armed on a node the page then removes** (poll tick deletes the
  row) — the timer holds a reference; check it cannot resurrect text onto a
  detached node.
- **`titleEl` missing** — the helper already guards `if (titleEl)`; a feedback
  change must guard the same way rather than assuming the element exists.
- **A lapse while the tab is backgrounded** — `setTimeout` throttling means the
  revert may fire late. The operator returns to an armed control that looks
  live but may be past its intended window.
- **Commit path calls `revertFn` on transport failure** — the control returns
  to resting, which after this change must not be mistaken for a lapse.

## Files Affected

- `the_one/interfaces/web/static/js/confirm.js` — the helper
- `the_one/interfaces/web/static/css/*.css` — a lapsed-state style, if the fix
  is visual
- `tests/browser/` — tests across four lanes
- `docs/ui-testid-registry.md`
- `squawks/0088-armed-confirm-summary-invariant-unpinned.md`
- `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`

## Citation Audit

Verified against the working tree on `flight/07-mission-close` (2026-09-19),
carrying Legs 1 and 2a uncommitted:

| Citation | Status |
|---|---|
| `confirm.js` — `revertMs` default 3000; `revert()` clears the timer, removes `.confirm-delete`, restores `_confirmOriginalTitle`; capture only in the first-click branch | verified |
| The 13 call sites listed in Inputs — enumerated by `grep -rn "confirmDelete(" the_one/interfaces/web/static/js/` excluding the docstring at `confirm.js:8` | **count and file set verified**; four LINE NUMBERS were stale and are corrected — see the row below |
| `knowledge-section.js:979`/`:1443` and `studio.js:2080`/`:2116` — working-tree values | **corrected at design review.** The first draft carried `962`/`1412`/`2066`/`2102`, which were correct at `HEAD` and wrong in the tree the leg is built on: Leg 2a's uncommitted edits inserted lines above them. The audit header said "carrying Legs 1 and 2a uncommitted" and the numbers were still gathered pre-Leg-2a. **In a deferred-commit flight, citations drift within the flight** — a form of staleness the audit has no way to catch by construction, since each leg's own verification is true when written |
| `system-page.js:87-91` — `revertFn()` called on the credential rotation's **SUCCESS** path, with a comment saying so (AC-6a) | verified — **added at design review**; the first draft treated `revert()` as having two callers |
| Lane coverage: `studio` 8/13, `system` 4/13, `chat` 1/13, `shared` 0/13 (AC-9) | verified — **corrected**; the first draft claimed `studio` covers "fewer than half", which is false |
| `areas/admin/system-page.js:81` — the API-credential rotate confirm | verified |
| `studio.js:2116` — purge-history confirm whose `.then` never calls `revertFn()` (guidance 4b) | verified |
| `knowledge-section.js:979` — armed on `<summary>`, folder-path span as `[data-confirm-title]` | verified |
| `knowledge-section.js:1111` — `renderFolderFiles` writes `panel.filesEl`; `:1128`/`:1153` — `renderAllItems` reaches panels only through it (squawk 0088's third invariant) | verified |
| `squawks/0088-…md` — names three invariants, records that only the first two have tests | verified |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do **NOT** commit — the Flight Director commits after the flight-end review
- [x] Signal `[HANDOFF:review-needed]`
