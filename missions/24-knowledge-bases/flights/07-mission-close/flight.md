# Flight: Mission Close

**Status**: in-flight
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [ ] Operator can inspect a knowledge base's contents and metadata, and
      retrieve the source material behind any indexed item *(the item row
      gains the freshness field its own behaviour spec asserts against)*
- [ ] A knowledge base can be attached to and detached from any agent in
      Studio *(behavior-test-backed — this flight re-authors
      `kb-studio-round-trip` to `active`, which is what makes the criterion
      honestly tickable; it is Mission 24's only non-`active` spec)*
- [ ] Existing installs upgrade with no data loss, the unit gate stays green,
      and the frozen Windows installer still builds and runs
- [ ] Retrieval combines semantic and keyword matching *(already ticked by
      Flight 5; this flight measures whether the constants behind it are
      load-bearing or arbitrary — it does not re-open the criterion)*

Also closes two mission **open questions** (the Windows 1M `usearch`
re-measure; whether the fusion balance is operator-tunable or fixed) and one
mission **Known Issue** (`get_vector_store()` has no shutdown hook).

---

## Pre-Flight

### Objective

Make Mission 24 closable. Four recorded obligations have outlived the flights
that were meant to carry them: a process-lifecycle hole that loses vector
writes at shutdown, a naming hole that silently drops an operator's disable
across detach → rename → reattach, an inventory row that renders nothing a
content change would alter (and a signature that therefore never re-fetches),
and a set of release gates — the full browser suite, `pip-audit`, the frozen
Windows build — that Flight 6 listed and left unowned. Alongside them, two
measurements the mission asked for and never took: whether Flight 2's Windows
1M `usearch` figures (extrapolated from 200k) survive contact with a real 1M
corpus, and whether `RRF_K` / `candidate_k` / the DD-3 reserved slot are
load-bearing constants or arbitrary ones. The flight ends with
`kb-studio-round-trip` re-authored to `active`, so the mission's closing
regression net is re-runnable rather than nominally present.

### Open Questions

- [x] Does one closing flight carry all four risk domains, or does the pile
      split? → **DD-1** (one flight; operator's call, 2026-09-19)
- [x] Is a Windows worker actually reachable for the 1M re-measure? →
      **DD-5** (yes, Concourse `fly execute`; staged ladder, not one run)
- [x] Where does R20's relevance ground truth come from? → **DD-4** (it does
      not; the flight runs a sensitivity sweep and says what that can and
      cannot conclude)
- [x] Does R8 (walk skip counters) come in, now that Flight 6's deferral
      premise turns out to be false? → **DD-7** (yes)
- [x] Is `the_one/tools/naming.py` (R15) carried? → **DD-2** (no, with a
      stated trigger)
- [x] Where does the component-layer work land? → **DD-11** (comment-only;
      re-decided by the operator after the Architect found the vocabulary is
      **24** class names, not three — the original call was made against a
      number that turned out to be wrong)
- [ ] **What is the right fix for `App.confirmDelete`'s silent re-arm?** →
      **DD-8** makes this a leg-level open question, decided in-flight after
      reading **all 13** call sites. Deliberately NOT pre-decided here: the
      operator's instruction was to investigate first, and the flight should
      not pretend to know the shape before the read.
- [x] Do the skip counters live in `app_metadata` or on `kb_items` with a v42
      migration? → **DD-7** (`app_metadata` kv, no migration; the leg owns
      explicit cleanup on both delete paths, since the kv is outside the
      cascade)

### Design Decisions

**DD-1 — One closing flight carries all four risk domains**: performance
measurement (R12, R13, R20), process lifecycle (R14), the coupled UI surface
(Rec 2, squawks 0087/0088, R8, the confirm question), and the release gates.
- Rationale: they do not share a surface, but they share a vehicle question —
  *what must be true for Mission 24 to close*. Every item here is either a
  mission criterion, a mission open question, or a mission Known Issue. Split
  across two flights, the gates cannot run until the second one, which means
  the mission's release readiness stays unmeasured for an extra planning cycle.
- Trade-off: one review gate over four domains, which Flight 6's own DD-1
  called "the worst place to do it." The mitigation is leg boundaries drawn on
  the domain lines, so the Reviewer reads four coherent diffs rather than one
  mixed one — not a single end-of-flight review over the union.
- Operator decision, 2026-09-19.

**DD-2 — R15 (`the_one/tools/naming.py`) is NOT carried**: the duplicated
`_TOOL_NAME_MAX_LEN = 64` (`mcp/_tool.py:39`, `knowledge/tool_provider.py:61`)
and the behaviourally-identical `_normalize_source_name` /
`_normalize_kb_name` stay as they are.
- Rationale: no mission criterion rests on it, and the F5 debrief's own
  trigger — *"before a third prefixed namespace"* — has not fired. There are
  two prefixes (`mcp__`, `kb__`), the same two as when the item was filed.
  Extracting a shared module now is a shared-interface change bought with the
  mission's last review gate and no forcing function.
- Trade-off: the duplication survives the mission, and the next namespace pays
  the extraction cost under time pressure rather than now.
- **Trigger, recorded so this is a deferral and not a drop**: the first change
  that adds a third prefixed tool namespace, or the first bug caused by the
  two `_normalize_*` implementations diverging.

**DD-3 — `close_vector_store()` closes if built, never builds to close**: the
shutdown hook is a new public function in `the_one/vectors/__init__.py` that
inspects the module-private `_store`, closes it when non-`None`, and clears
the cache. The lifespan calls that function; it never calls
`get_vector_store()`.
- Rationale: `get_vector_store()` (`vectors/__init__.py:70`) *builds and
  opens* on first call. Calling it from the shutdown path would construct a
  `UsearchStore`, open its sidecars, and immediately close them — on an
  instance that never used a knowledge base at all. The hook must be able to
  answer "nothing to do" without touching disk.
- **Two ordering bounds, not one** (Architect cycle 1): after
  `_indexing_manager.drain()` (`app.py:421-427`) **and before**
  `close_connection()` (`app.py:537`). The second bound is load-bearing —
  `UsearchStore.flush()` calls `_upsert_registry_row()`, which writes through
  `self.conn`; a hook placed after the DB close would raise on every dirty
  knowledge base. The file's own house style pins both sides (see the MCP-pool
  comment at `app.py:451-454`, "AFTER PTY drain … and BEFORE DB close"), and
  the existing drain-order spy test at `app.py:456` gains an assertion for the
  new position.
- **The hook is load-bearing, not defensive** — the original rationale here
  ("knowledge bases that have no worker") was true but weak. `IndexingManager.stop()`
  (`manager.py:224-254`) leaves the store dirty on **two** paths: the cancel
  fallback *never flushes at all* (`manager.py:240-243`), and a flush that
  times out or raises is logged with `entry.dirty` still `True`
  (`manager.py:246-251`). The hook's real job includes the drain's own
  leftovers.
- `UsearchStore.close` (`usearch_store.py:486`) already iterates
  `self._kbs` and flushes each under its own `try/except`, so one failing
  knowledge base cannot abort the rest — the same discipline the watch-manager
  and indexing-manager drains already use, and the hook inherits it rather
  than re-implementing it.
- **Idempotency is an acceptance criterion, not an assumption**: `close()`
  does not clear `self._kbs` or mark the store closed. A second call is
  nonetheless a *no-op* in the normal case, because `flush()` early-returns on
  `if entry is None or not entry.dirty` (`usearch_store.py:424-426`) — it
  re-flushes only when the first flush **failed**, which is the documented
  desired behaviour (`:417-422`). The criterion stands; the reason stated in an
  earlier draft of this decision (that a second call always re-flushes) was
  wrong and is corrected here.

**DD-3a — the cancel-fallback torn-save hazard is closed by surfacing state,
not by skipping blindly** (Architect cycle 1, a genuine hazard this flight
would otherwise have shipped): `UsearchStore.upsert` holds `entry.lock` across
`await asyncio.to_thread(_do_upsert, entry.index)` (`usearch_store.py:275-296`).
Cancelling that task unwinds the `async with` and **releases the lock while the
worker thread is still mutating the index** — `manager.py:242-243` says so in
its own words. A `close_vector_store()` running immediately afterwards would
acquire that now-free lock and `index.save` concurrently with a live mutation:
a torn save, on precisely the path the hook exists to cover.
- **Resolution**: `IndexingManager.stop()` already computes `cancelled`; it
  records which knowledge bases took the cancel fallback, and the hook reads
  that and **skips exactly those**, logging each as *not flushed — a cancelled
  mutation may still be running*.
- Rationale for this shape over the alternatives: skipping nothing corrupts the
  index; skipping everything (not running the hook after a cancel) loses the
  clean knowledge bases' writes too; a bounded settle guesses at a duration the
  code cannot bound. Surfacing the state the manager already has is the only
  option that is both safe and precise, and it makes the lost write **visible
  in the log** rather than silent.
- The write on a cancel-fallback knowledge base **is** lost. That is the
  correct trade — a lost write is recoverable by re-indexing; a torn index is
  not — and it is recorded here so it is a decision rather than an accident.

**DD-4 — R20 is a sensitivity sweep, not a relevance benchmark**: the flight
sweeps `RRF_K` and `candidate_k` across a real corpus and reports how much the
returned top-`limit` set *changes* — rank churn against the shipped constants,
reserved-slot fire rate, and the overlap curve — with no query→document
relevance judgments.
- Rationale: the F5 debrief asked for "recall/precision," which needs ground
  truth that does not exist. `bench_vector_store.py`'s existing `recall@k` is
  **vector** recall against an exact float32 brute-force neighbour set — it
  measures whether HNSW found the right vectors, and says nothing about
  whether the fused result is useful. Manufacturing labels would produce a
  precision number defensible only against the labeller.
- **What the sweep can conclude**: whether the constants are load-bearing
  (the result set moves materially when they move) or arbitrary (it does
  not), and whether the DD-3 reserved slot ever fires outside its
  constructed test cases. Both are real answers to the mission's open
  question "is the balance operator-tunable or fixed."
- **What it cannot conclude**: that any particular value is *better*. The
  flight must not report a "recommended" `RRF_K`, and the mission open
  question closes as *"fixed, and here is the evidence the fixing is not
  arbitrary"* — not as *"tuned."*
- Trade-off: a genuine quality regression in fusion would not be caught. Named
  so a future mission that wants one knows exactly what it is buying.
- Operator decision, 2026-09-19.

**DD-5 — R12 runs as a staged ladder (200k → 500k → 1M) with an early-stop
checkpoint**, as a new `ci/tasks/windows-vector-bench.yml` invoked by
`fly -t the-one execute -c ci/tasks/windows-vector-bench.yml -i repo=.`.
- **The claim under test is narrowed, deliberately** (Architect cycle 1):
  three Windows points test whether **Windows build and save cost are linear
  in N**, which is not the same as testing an N-independent Windows/Linux
  *ratio* — that would need matching Linux rungs at 500k and 1M. The flight
  does **not** re-measure Linux, because nothing downstream depends on the
  ratio: Flight 3's flush cadence was sized against **absolute Windows
  figures**, and the ratio was only ever the means of extrapolating them. Per
  `mission.md:255`'s standing rule, the Linux numbers are discounted
  explicitly rather than quietly compared against.
- Rationale: Flight 2's 1M/3M Windows figures are 200k measurements scaled by
  an assumption nobody re-checked, and Flight 3's flush cadence rests on them.
  Three points test that assumption; one point only confirms or denies a single
  extrapolated number. If 500k already falsifies linearity, the flight has its
  answer without holding a shared worker for two hours.
- **The tolerance is stated before the first run, not after the second**: the
  leg fixes a numeric band for "within tolerance of the extrapolation" as its
  first act and records it in the flight log before any measurement. Deciding
  it after seeing 500k is how a checkpoint becomes a rationalization.
- The Concourse Windows worker is **shared and uncontainerised**, and the
  `build-windows-installer` job auto-triggers after `ci` passes — a multi-hour
  hold on it is real contention, not a theoretical cost.
- **Early-stop checkpoint** (operator decision point inside the leg): after
  500k, if the measured per-vector build cost is within tolerance of the
  extrapolation, the 1M run proceeds; if the curve has already diverged, the
  leg stops and reports the divergence, because the extrapolation is falsified
  either way and the remaining hours buy precision on a number already known
  to be wrong.
- Trade-off: three runs of setup overhead instead of one.

**DD-6 — Rec 2's two halves land in the same commit, never separately**: the
per-item freshness field on the inventory row and the widening of
`studio.js::knowledgeItemsSignature` (`studio.js:480`) ship together.
- Rationale: Flight 6 recorded that they *mask each other*. The signature is
  counts-only (`JSON.stringify(status.items) + '|' + status.chunks`), so a
  content-only edit triggers no `/items` re-fetch — harmless today only
  because the row renders nothing a content-only change would alter.
  **Shipping the freshness field alone converts an invisible blind spot into a
  visible staleness bug.**
- **This is not a render-only change** — an earlier draft of this decision
  called it "a render + signature change, not a data change," which is false
  and is corrected here (Architect cycle 1). The render half is free: `GET
  /items` already returns `indexed_at`, `content_hash`, `size_bytes` and
  `mtime` per item and the client discards them. The **signature** half is
  not: `knowledgeItemsSignature` is computed from `/status`
  (`studio.js:589`, `:694`), and `get_kb_status` (`api.py:1805-1841`) carries
  **no per-item content signal at all** — only `items` status counts,
  per-folder walk state, `chunks` and `indexer`. The signature cannot be
  widened client-side to see a content-only edit, because the data it would
  need is not in the payload it reads.
- **Resolution — a freshness aggregate on `get_kb_status`**, so Leg 2a does
  touch Python. The rejected alternative was folding `status.folders` into the
  signature (client-only, since folder `indexed_at` is already in the payload
  and `manager.py:409` sets it on every completed walk): it works, but Flight 6
  *measured* that a folder's `indexed_at` advances on every reconcile walk
  whether or not anything changed — so the signature would fire every walk
  forever on a quiet corpus, and would be structurally unable to answer "did
  anything change." An aggregate over file items that moves iff an item
  re-indexed is one query and is precise.
- This is also what unblocks `kb-studio-round-trip` step 8, whose second
  clause was written against a browser observable that does not exist.

**DD-7 — R8 (walk skip counters) is in scope; Flight 6's deferral premise was
false**: Flight 6 deferred it saying "nothing in the pipeline accumulates them
today, so the walk would have to count and persist per-pass skip totals."
- The walk **already counts them**: `WalkResult` carries `skipped_dirs` and
  `skipped_entries` (`knowledge/walk.py:58-59`), incremented at nine sites
  through `walk.py:106-152`, and `knowledge/manager.py:412` already logs both
  per pass. The missing work is persistence and projection, not instrumentation.
- Recorded as a **reconnaissance correction**, not a scope change of opinion —
  the earlier decision rested on a fact that is not true, and is being revisited
  for that reason rather than because the flight wants the work.
- **RESOLVED — `app_metadata` kv, no migration** (operator, 2026-09-19).
  `kb_items` has no
  spare column (`db/models.py:108-129`), but `AppMetadataRepository`
  (`db/repositories.py:1851-1876`, schema v31) is a generic string kv with
  `get`/`set`, already carrying `last_purge_at` and `VECTOR_STORE_KEY`. A key
  per folder item holding JSON persists across restarts with **zero schema
  change**. The in-memory current-pass-only fallback in Adaptation Criteria
  stays as the fallback it was always meant to be.
- **The kv's one cost is an acceptance criterion, not a footnote**: a key in
  `app_metadata` is *not* reached by `kb_items`' cascade delete, so deleting a
  folder or a knowledge base would orphan its skip-count keys forever. The leg
  owns explicit cleanup on both delete paths, and a test that proves a deleted
  folder leaves no key behind. This is the whole price of avoiding the
  migration, and it is paid in the leg rather than discovered later.
- Scope stays bounded to what the mission criterion asks: the counts of files
  that never became items, beside the folder's existing walk status. Files that
  *did* become `failed` items are already legible and are not touched.

**DD-8 — `App.confirmDelete`'s silent re-arm is a leg-level open question, not
a pre-decided fix**: the leg reads all 13 call sites, then decides.
- Rationale: the question failed the squawk gate on exactly two counts — "no
  design decisions" and "bounded blast radius" — and pre-deciding the fix here
  would re-fail the first one at flight level instead. The defect is stated;
  the shape of the fix is not.
- **The defect, stated precisely**: a confirm that times out re-arms with no
  feedback, so the operator cannot distinguish *"I let it lapse"* from *"I
  committed."* The 3-second `revertMs` default is a symptom surface, not the
  defect.
- **Constraint the leg inherits: whatever it decides applies to all 13 call
  sites** across 8 files, through the shared helper. A fix that special-cases
  the knowledge-base call site is out of bounds — that is how the helper
  acquired 13 divergent behaviours' worth of risk in the first place.
- **The surface is larger than this flight first recorded.** An earlier draft
  of this decision said "six call sites," copied from the Flight 6 debrief and
  stamped `verified` in the Citation Audit without being re-counted. The real
  count is **13**, and the difference is not cosmetic: it pulls in
  `areas/admin/system-page.js:81` — the **API-credential rotation** confirm,
  the highest-consequence confirm in the app — plus `areas/chat.js:1140` and
  three sites in `areas/admin/provider-editor.js`. The fix therefore crosses
  the `chat`, `system` and `shared` browser lanes as well as `studio`.
- Operator decision (investigate first), 2026-09-19.

**DD-9 — Squawks 0083 and 0050 clear on the squawk path as prerequisites, not
as legs**:
- **0083** (`anyio` 4.13.0 → 4.14.2, two CVEs) must land *before* the gates
  leg runs, because `pip-audit` cannot be green while it stands and the frozen
  Windows build must be verified *after* the bump — `anyio` is inside the
  PyInstaller closure.
- **0050** (`kb_ids` clobber) is `already-satisfied in code` — fixed and
  regression-netted in Flight 6 — but its artifact carries an **empty
  Corrective Action** and status `open`. It needs a write-up and an independent
  sign-off, which is the squawk path's job, not a leg's.
- Rationale: both are single coherent items with no design decisions. Routing
  them through legs would inflate the flight and produce worse records — a
  squawk's sign-off is what closes a squawk.

**DD-10 — the Windows bench task provisions a fresh per-run venv**: like
`ci/tasks/windows-installer-build.yml`, never the persistent `C:\Python311`
base interpreter.
- Rationale: the Concourse Windows worker runs tasks **uncontainerised**, so
  that interpreter's `site-packages` survives across builds. Build 606657
  shipped a stale `hf_xet` exactly this way (recorded in `ci/README.md:95-99`).
  A benchmark is more sensitive to this than a build: a stale `usearch` or
  `numpy` would silently produce numbers for a version the product does not
  ship, and nothing in the output would say so.
- ⚠️ **CORRECTED 2026-09-19 at Leg 3 design review — this decision's premise
  was FALSE.** `scripts/bench_vector_store.py:102` has imported
  `_usearch_acceleration` from `the_one.diagnostics` since Flight 2 Leg 5
  (commit `c315cf5`), and `host_facts()` (`:210-225`) has emitted
  `"usearch_acceleration": _usearch_acceleration()` all along — the **same
  function** the `doctor` probe uses, reporting `numkong=yes, simd=haswell`,
  documented as "never raises" and already degrading gracefully when numkong
  is missing or unlinked.
- **The evidence behind the false claim was a grep that could not match.**
  This decision cited `grep 'simd\|simsimd\|numkong'` over the script
  returning nothing. That is true, and meaningless: the identifier is
  `usearch_acceleration`, which contains none of those substrings. **A negative
  result from an instrument that cannot express the thing is not evidence of
  absence** — the Flight 6 debrief's own Key Learning #2, recorded after two
  instances, both the Flight Director's. This is the third.
- **What survives**: the *hazard* is real and correctly stated — `usearch`
  swallows its own numkong `ImportError`, so an unrecorded backend is a genuine
  risk, and `_usearch_acceleration`'s docstring says it exists for exactly that
  reason. **What was wrong**: the claim that the bench script lacked it. The
  remaining gap is narrower and real — see the leg's AC-3: `host_facts()` is
  printed once by the parent and never called in a `--child` invocation, whose
  entire stdout contract is one rendered markdown row. So a per-cell subprocess
  still cannot report its own backend.
- *(Original text, preserved: "A version string does not determine the backend.
  `bench_vector_store.py:215-218` records `platform`, `python`,
  `sqlite_version` and `usearch_version` — and nothing about SIMD or numkong
  linkage.")* Flight 1 established that every
  published `usearch` Windows wheel is `simd=serial` with zero `nk_*` symbol
  refs (`mission.md:249-252`) and, worse, that **`usearch` swallows its own
  numkong `ImportError`** (Flight 1 log, `:93-95`) — a bundle missing
  `numkong._numkong` still imports, still answers searches by dynamic dispatch,
  and still prints a clean `OK`. So a fresh per-run venv — DD-10's own remedy —
  is exactly where a silent backend difference could enter, one layer below
  where DD-10 was looking.
- **Therefore**: the host-level field already exists and is reused, not
  rebuilt. The leg's work is threading it to **per-cell** visibility through
  `render_row`/`_TABLE_HEADERS`, so a forked child's row carries the backend
  it actually ran under. Numbers measured under an unrecorded backend are not
  measurements — and a parent-only record does not cover a per-cell fork.

**DD-11 — the disclosure-tile rename rides the UI leg; issue #207 stays a
future mission**: rename the trio to a neutral vocabulary and add the
`consumers:` note at `studio.css:178`.
- Rationale: the F6 debrief's Recommendation 6 argues the component layer is a
  mission, not a leg — "a layer adopted halfway leaves three idioms where there
  are two." The rename is the part that does not wait: it is the same file's
  neighbourhood the UI leg already opens, and it removes the specific trap that
  cost Flight 6 three of its four post-landing passes (a page hand-assembled
  from another page's class names, inheriting that page's assumptions
  invisibly).
- **The premise the operator decided on was wrong, and this needs re-deciding**
  (Architect cycle 1). "The trio" implied three class names. The actual
  vocabulary is **24 distinct `mcp-tool-*` class names** across 6 source files
  (`css/studio.css`, `areas/studio.js`, `studio/tools-tab.js`,
  `studio/mcps-tab.js`, `studio/knowledge-section.js`,
  `studio/mcp-server-editor.js`) and referenced by **4 browser test files**
  spanning the `studio` and `shared` lanes.
- Renaming 3 of 24 leaves 21 siblings carrying the old vocabulary beside 3 new
  ones — which is verbatim the "a layer adopted halfway leaves three idioms
  where there are two" failure that DD-11's own rationale cites as the reason
  issue #207 is a mission and not a leg. **A 3-of-24 rename is the one option
  this decision's own argument forbids.**
- **RESOLVED — comment-only** (operator, 2026-09-19, re-decided against the
  corrected number). Add the `consumers:` note
  at `studio.css:178` naming every reader of the vocabulary, and leave the
  rename whole to the component mission. The trap Flight 6 actually hit was
  *invisibility* — a page hand-assembled from another page's class names,
  inheriting that page's assumptions with nothing on screen or in the source
  saying so. A comment closes the invisibility at a fraction of the blast
  radius; the rename closes it again, more expensively, and only if it is
  complete.
- The rename itself — whole, all 24 — belongs to the component-layer mission.
  Recorded as a re-decision rather than silently changed, because the original
  was a real operator call made against a number that turned out to be wrong.
- **Scope bound for the leg**: no class name changes. If the note cannot be
  written without renaming something, that is the signal the work is the
  mission's, not this leg's — stop and say so.

**DD-12 — Rec 5 (the PUT/PATCH preserve-on-omit protocol question) is OUT of
scope and escalates**: `update_agent` now carries three preserve-on-omit
special cases (`mcp_overrides`, `self_revision_requires_approval`, `kb_ids`)
and squawk 0080 (`mcp_source_ids`) is the fourth, missed and still live data
loss.
- Rationale: the invariant "a form must not erase fields it does not render"
  belongs in the request protocol, which means every form in the app, not the
  knowledge-base surface. It fails flight sizing on its own — a different
  mission's worth of blast radius.
- **This flight does not fix squawk 0080 and does not pretend to.** The
  debrief's instruction — *"do not let squawk 0080 be filed a third time in a
  third form"* — is honoured by naming it here as an escalation with a vehicle,
  not by folding it in.
- Recommended vehicle: its own mission, alongside or after the component-layer
  mission (issue #207), since both are cross-cutting protocol/vocabulary work
  on the same surfaces.

**DD-13 — Flight 6's DD-17 makes a reconcile exact, closing the detach →
rename → reattach hole**: at agent build time both the `kb_id` and the current
derived name are in hand, so the rule is *if a `kb__…__search` entry in
`disabled_tools` carries a discriminator derived from this `kb_id` but a slug
that does not match the current name, rewrite it.*
- Rationale: **Flight 6's DD-17 made this free.** `compute_tool_names`
  (`knowledge/tool_provider.py:117`) applies the `sha256(kb_id)` discriminator
  **unconditionally**, so the discriminator is a stable fingerprint of identity
  that survives a rename. Matching on it needs **no cross-entity write**, no
  forced ordering and no partial-failure discipline.
- **The discriminator's WIDTH is not fixed** (Architect cycle 1 — this
  falsified the matching rule as first written, though not the decision).
  `_HASH_LENGTHS = (8, 12, 16)` (`tool_provider.py:72`) and the widening loop
  at `:181-200` promote a knowledge base to 12 then 16 characters when derived
  names collide **across the set being computed** — which is exactly the
  set-composition dependence that `compute_tool_names`' own docstring claims
  the name does not have. The docstring is an approximation with its exception
  documented 60 lines below it, and an earlier draft of this decision cited
  that docstring as if it were the control flow.
- **Therefore the rule is**: strip `kb__` and `__search`, then test whether the
  remainder ends with `_` + `_discriminator(kb_id, L)` for **each** `L in
  _HASH_LENGTHS`. It cannot match a fixed width, and it cannot split on
  position either — a slug may itself contain `_` and `__`
  (`tool_provider.py:82-86`). In practice only the 8-character path is
  reachable (widening requires a sha256 prefix collision), so the reconcile
  stays exact; `_HASH_LENGTHS` becomes a named coupling point.
- **The seam is `agent/factory.py`, not `KBToolProvider`** (Architect cycle 1).
  `KBToolProvider.get_tools_for_agent` (`tool_provider.py:215-262`) returns
  `list[Tool]` and never consults `disabled_tools`; the per-agent disable is
  applied at `factory.py:423` via `config.is_tool_enabled`, where both the
  derived names and the config are in hand. An earlier draft placed the
  reconcile where the data is not.
- **`knowledge/kb_rename.py` stays, and the two do not conflict**: it performs
  an *exact full-name* replacement (old derived name → new, both computed by
  the caller) and never parses a discriminator, so there is no second matching
  rule to keep in agreement. Division of labour: `kb_rename` is the write-side
  converger for the common case (rename while attached); the reconcile is the
  read-side backstop for the case `kb_rename` structurally cannot see, because
  `SQLiteAgentStore.list_by_kb` returns only *currently attached* agents.
- **Stated cost**: the reconcile writes nothing, so a stale entry corrected at
  read time stays stale on disk until the next rename or an explicit `PUT` —
  and `studio.js:2394-2419` re-unions every `kb__`-prefixed stored entry on
  every Studio save while no Studio surface renders a `kb__` toggle. The
  reconcile is therefore **permanent** code with no convergence path of its
  own. That is accepted deliberately: writing to agent rows from a read path is
  a worse trade than carrying a cheap normalization forever.

### Citation Audit

Verified against the working tree at **`7965246`** (2026-09-19). Every design
decision above that asserts a code mechanism appears here.

**Architect cycle 1 re-checked 15 of 19 rows independently and found one
failure, one verified-but-misleading row, and one drifted line number.** All
three are corrected below and marked. The failure — "six call sites" — is
exactly the defect class this audit exists to catch: a figure copied from a
source artifact and stamped `verified` without being re-counted. It is left
visible here rather than quietly fixed, because an audit that hides its own
misses is worth less than no audit.

| Citation | Status |
|---|---|
| `the_one/vectors/__init__.py:70 — async def get_vector_store()` — builds + `open()`s on first call, caches in module-global `_store`; no public accessor returns the cache without building (DD-3) | verified |
| `the_one/interfaces/web/app.py` — `grep get_vector_store` returns **zero hits** in the whole file; the lifespan drains watch manager, indexing manager, reaper, PTY registry and MCP pool (DD-3, R14) | verified |
| `the_one/vectors/usearch_store.py:486 — async def close()` — iterates `self._kbs`, flushes each under its own `try/except`; does **not** clear `_kbs` or mark closed, so a second call re-flushes (DD-3 idempotency AC) | verified |
| `the_one/vectors/usearch_store.py:407 — async def flush(kb_id)` — the per-KB flush `close()` calls (DD-3) | verified |
| `the_one/knowledge/walk.py:58-59 — WalkResult.skipped_dirs / .skipped_entries` — counted at nine sites through `:106-152` (DD-7) | verified |
| `the_one/knowledge/manager.py:412 — "(skipped_dirs=%d, skipped_entries=%d)"` — already logged per pass, never persisted (DD-7) | verified |
| `the_one/interfaces/web/static/js/areas/studio.js:480 — knowledgeItemsSignature(status)` — counts-only; read at `:589` and `:694` (DD-6) | verified |
| `the_one/db/repositories.py:527,632,640 — "ORDER BY created_at"` with no tiebreak; `:1569` and `:2431` in the same file already carry `, id DESC` / `, identifier DESC` tiebreaks as in-file precedent (squawk 0087) | verified |
| `the_one/knowledge/retrieval.py:93 — RRF_K = 60`; `:112 — SEMANTIC_QUERY_TIMEOUT = 2.0`; `:160 — _candidate_k(limit)`; the DD-3 reserved slot at `:220-233` (DD-4) | verified |
| `the_one/knowledge/tool_provider.py:117 — compute_tool_names` — the discriminator IS applied unconditionally (verified in control flow, not just docstring) (DD-13) | verified |
| `the_one/knowledge/tool_provider.py:72 — _HASH_LENGTHS = (8, 12, 16)` + the widening loop at `:181-200` — the discriminator's **width** is set-composition-dependent, contradicting the docstring's "independent of the composition of the set" (DD-13) | verified — **corrected**; an earlier row quoted the docstring as if it were the control flow |
| `the_one/agent/factory.py:423 — "if tool.name not in disabled_names and config.is_tool_enabled(tool.name)"` — the per-agent disable is applied here, NOT in `KBToolProvider.get_tools_for_agent` (`tool_provider.py:215-262`, which never consults `disabled_tools`) (DD-13 seam) | verified |
| `the_one/knowledge/kb_rename.py::rename_kb_tool_references` — exact full-name replacement computed by the caller; never parses a discriminator, so no second matching rule (DD-13) | verified |
| `the_one/interfaces/web/api.py:1805-1841 — get_kb_status` — returns `items` (status counts), `folders[]`, `chunks`, `indexer`; **no per-item content signal** (DD-6) | verified |
| `the_one/knowledge/manager.py:224-254 — IndexingManager.stop` — cancel fallback never flushes (`:240-243`); a failed/timed-out flush leaves `dirty` True (`:246-251`) (DD-3, DD-3a) | verified |
| `the_one/vectors/usearch_store.py:275-296 — upsert` holds `entry.lock` across `await asyncio.to_thread(...)`; cancellation releases the lock with the worker thread still mutating (DD-3a torn-save hazard) | verified |
| `the_one/vectors/usearch_store.py:424-426 — flush` early-returns on `not entry.dirty`, so a second `close()` is a no-op unless the first flush failed (DD-3 idempotency) | verified |
| `the_one/db/repositories.py:1851-1876 — AppMetadataRepository.get/set` — generic string kv, schema v31, already holds `last_purge_at` and `VECTOR_STORE_KEY` (DD-7 persistence without migration) | verified |
| `the_one/db/schema.py:14 — CURRENT_VERSION = 41` — so a new migration would be **v42**, not v41 (Adaptation Criteria) | verified |
| `scripts/bench_vector_store.py:102` imports `_usearch_acceleration`; `host_facts()` (`:210-225`) already emits `"usearch_acceleration"` — present since Flight 2 Leg 5 (`c315cf5`) | **FALSIFIED at Leg 3 design review.** This row previously read "records … **nothing** about SIMD or numkong linkage — verified", on the strength of a grep for `simd\|simsimd\|numkong` that cannot match the identifier `usearch_acceleration`. Third instance in Mission 24 of asserting absence with an instrument that cannot express presence |
| `usearch` swallows its own numkong `ImportError` (Flight 1 log `:93-95`); `the_one/diagnostics.py:378-415 — _usearch_acceleration` exists precisely to surface it | verified — the hazard is real; only the claim that the bench lacked coverage was false |
| 24 distinct `mcp-tool-*` class names across 6 source files, referenced by 4 browser test files in the `studio` and `shared` lanes (DD-11) | verified — **corrected** from "the trio" |
| `the_one/knowledge/tool_provider.py:61` and `the_one/mcp/_tool.py:39` — `_TOOL_NAME_MAX_LEN = 64` duplicated; `the_one/tools/naming.py` does not exist (DD-2) | verified |
| `scripts/bench_vector_store.py:837-861 — _build_arg_parser` — `--corpus`, `--cells`, `--k`, `--seed`, `--child`; per-cell child processes for clean `peak_rss_MB` (DD-5) | verified |
| `ci/tasks/windows-installer-build.yml` + `ci/README.md:95-99` — fresh per-build venv because the uncontainerised worker's `C:\Python311` site-packages survive; build 606657 shipped a stale `hf_xet` (DD-10) | verified |
| `ci/README.md:78 — fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.` — the ad-hoc task-invocation pattern the bench task follows (DD-5) | verified |
| `tests/behavior/kb-folder-index-round-trip.md:99 — "## Variants (optional)"` — the `live-kill` variant already generates 2,000 × 50 KB files; R13 reuses that fixture generator | verified |
| `uv.lock:66-67 — anyio 4.13.0` still pinned (DD-9, squawk 0083) | verified — line corrected from `:73` |
| `squawks/0050-studio-save-clobbers-kb-ids.md` — status `open`, **Corrective Action section empty** (DD-9) | verified |
| `the_one/interfaces/web/api.py::update_agent` — three preserve-on-omit special cases, no `disabled_tools` clause, no `mcp_source_ids` clause (DD-12, squawk 0080) | verified |
| `the_one/interfaces/web/static/js/confirm.js — App.confirmDelete(itemEl, onConfirm, opts)` — `revertMs` default 3000, **13 call sites across 8 files**: `studio/knowledge-section.js:962,:1412` · `studio/connector-editor.js:599` · `studio/mcp-server-editor.js:1270,:1321` · `studio/self-configuration-tab.js:1294` · `studio.js:2066,:2102` · `admin/system-page.js:81` · `admin/provider-editor.js:509,:946,:951` · `chat.js:1140` (DD-8) | **CORRECTED** — an earlier row read "six call sites", copied from the Flight 6 debrief and stamped `verified` without re-counting. Caught by the Architect. Re-counted independently by the Flight Director |

### Prerequisites

- [ ] **PR #208 merged into `mission/24-knowledge-bases`** — the squawk
      turnaround (0084, 0086, 0089, 0090). The flight branch cuts from the
      mission branch; branching before this merges puts the flight behind its
      own corrected documentation.
- [ ] **Squawk 0083 completed** (`anyio` → 4.14.2) — DD-9. Blocks the gates
      leg; the frozen Windows build must be verified after the bump.
- [ ] **Squawk 0050 completed** (write-up + sign-off) — DD-9. Artifact work,
      no code change.
- [ ] **Concourse Windows worker reachable** — operator confirmed the path is
      available, 2026-09-19. **This is a planning-time confirmation and is not
      sufficient on its own**: the `fly -t the-one` login expires, and the
      worker is shared and uncontainerised with `build-windows-installer`
      auto-triggering onto it (`ci/README.md:92-93`). Leg 3's **first step** is
      to re-run `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.`
      and confirm green, so a worker or auth problem surfaces as itself rather
      than as a bench-task bug days later.
- [ ] **A 1M-chunk corpus is generatable** — `bench_vector_store.py`'s
      synthetic generator is seeded and parameterised; confirm it reaches 1M
      within the worker's disk budget before the ladder leg runs.
- [ ] **`make test-unit` green on the mission branch** at flight start, so the
      gates leg measures this flight's effect and not inherited drift.

### Pre-Flight Checklist

- [x] All open questions resolved *(DD-8's remains open by decision — a
      leg-level question the operator instructed be investigated first, not a
      flight-level one left unanswered)*
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
      at `7965246`
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Four leg boundaries drawn on the domain lines, so the flight-end Reviewer reads
four coherent diffs rather than one mixed one — which is the mitigation DD-1
owes for putting four domains behind one review gate.

**Non-UI correctness** (Leg 1) closes two recorded holes that share one
property: no operator surface can reveal either of them. The shutdown hook adds
`close_vector_store()` beside `get_vector_store()` and calls it from the
lifespan after the indexing-manager drain; the reconcile adds a read-side rule
at `factory.py:423` keyed on Flight 6 DD-17's identity fingerprint. Both are pinned by
unit tests, neither touches a schema.

**The UI surface** splits into **two** legs on a hard boundary. **2a** is
decided work on one lane: the freshness field with its `get_kb_status`
aggregate and the signature widening together (DD-6), the skip-counter
persistence and projection (DD-7), the `ORDER BY` tiebreaks (0087), and
DD-11's note. **2b** is the confirm helper (DD-8) and its invariant test
(0088) — the only piece carrying an undecided design, and the only one
crossing four browser lanes. Splitting them lets 2a land while DD-8's
investigation runs, instead of holding decided work behind an open question.

**Measurement** (Leg 3) produces numbers and a recorded interpretation, and
changes product code only where the numbers demand it. The Windows ladder runs
through a new CI task; the fusion sweep runs on Linux, because it measures
fusion arithmetic and not a platform.

**Gates and the regression net** (Leg 4) re-authors `kb-studio-round-trip` —
which depends on Leg 2a having shipped step 8's observable — adds R13's
large-folder settle variant, then runs every release gate by hand and records
the results, because this mission branch has no CI lane.

### Checkpoints

- [ ] A process that used a knowledge base and shut down cleanly has no
      unflushed vector writes, **and the hook never builds a store**. *(The
      second clause is deliberately about the hook, not the process:
      `IndexingManager.start_all` (`manager.py:268-284`) already calls the
      store factory on first launch with zero knowledge bases, so "a process
      that never touched one builds no store" is unreachable and an earlier
      draft asserted it anyway.)*
- [ ] A knowledge base whose worker took the cancel fallback is **skipped, and
      logged as skipped** — never saved concurrently with a live mutation
- [ ] An operator's disabled knowledge-base tool survives detach → rename →
      reattach
- [ ] A content-only edit to an indexed file produces a visible change on the
      inventory row **and** triggers the re-fetch that renders it
- [ ] A confirm that lapses is distinguishable on screen from one that
      committed, at **all 13** call sites — including the API-credential
      rotation confirm in Administration
- [ ] The Windows ladder either confirms that Windows build/save cost is
      linear in N or falsifies it, with Flight 3's flush constants re-checked
      against the result either way, and the **SIMD/numkong backend recorded**
      alongside every measurement
- [ ] The fusion sweep answers whether `RRF_K` and `candidate_k` are
      load-bearing, without claiming a better value
- [ ] `kb-studio-round-trip` is `active` and passes
- [ ] `make lint`, `make test-unit`, full `make test-browser`, `pip-audit`
      against the release closure, and a frozen Windows build all run by hand
      and recorded — **each with a named leg owner** (F6 debrief Rec. 3)

### Adaptation Criteria

**Divert if**:
- R8's skip counters turn out to need a schema migration to persist.
  **`AppMetadataRepository` is the default and needs none** (DD-7); if that
  route proves unworkable, a **v42** migration (`CURRENT_VERSION` is already
  41) in the mission's closing flight is out of scope — fall back to reporting
  the current pass only, from memory, and record the limitation
- Closing the DD-3a cancel-fallback hazard turns out to need a change to
  `IndexingManager`'s stop/drain contract rather than a reported flag — that
  is a lifecycle interface with its own consumers and belongs in its own leg
- The Windows ladder diverges from the extrapolation badly enough that
  Flight 3's flush cadence is *wrong* rather than *imprecise* — that is a
  correctness change to the indexing pipeline, which is a different risk
  domain and gets its own leg or flight
- DD-8's investigation concludes the right fix is a change to the confirm
  *interaction* rather than its feedback — a **13**-call-site interaction
  change is a design decision that escalates to the operator before
  implementation. *(This trigger said "six" until the count was corrected;
  among the 13 is the API-credential rotation confirm, which is why an
  interaction change here is escalated rather than decided in-leg.)*

**Acceptable variations**:
- Further splitting **2b** if DD-8's chosen fix turns out to want a per-lane
  rollout. *(The 2a/2b boundary itself is NOT a variation — it is mandatory;
  see Legs. An earlier draft made it optional and grouped DD-8 with DD-11 as
  "shared-helper work", which they are not: DD-11 is a comment with no
  behaviour change, DD-8 is a behaviour change with an open design.)*
- Stopping the Windows ladder at 500k when the curve has already answered the
  question (DD-5's early-stop checkpoint) — this is the design, not a deviation
- The sweep's parameter grid and corpus choice settled by the implementing
  agent, provided DD-4's "cannot conclude" boundary is preserved in the write-up
- Rendering decisions within the inventory row settled against existing Studio
  patterns

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> one at a time as the flight progresses.

- [ ] `non-ui-defect-closure` **(high-risk — lifecycle)** — `close_vector_store()`
      and its lifespan wiring (DD-3, R14, a mission Known Issue deferred four
      times), plus DD-13's detach → rename → reattach reconcile (F6 debrief
      Rec. 4). Two independent defects in one leg because they share the
      property that made both survivable: **no operator surface reveals
      either**, so each is pinned by a unit test or it is not pinned at all.
      No UI, no schema, no migration.
- [ ] `inventory-freshness` **(2a — render, projection, all decided)** —
      DD-6's freshness field with its `get_kb_status` aggregate and the
      signature widening, **in one commit**; DD-7's skip-counter persistence
      via `AppMetadataRepository` and its projection; squawk 0087's three
      `ORDER BY` tiebreaks (matching the in-file `, id DESC` precedent at
      `repositories.py:1569`); and DD-11's `consumers:` note. Browser tests land
      as `test_flow_studio_knowledge_*.py` for the `studio` lane glob.
- [ ] `confirm-lapse` **(2b — high-risk, shared helper, undecided design)** —
      DD-8's investigation across all **13** `App.confirmDelete` call sites and
      the fix it selects, plus squawk 0088's armed-confirm invariant test.
      **Crosses four browser lanes**: `studio`, `system`
      (`admin/system-page.js`, `admin/provider-editor.js`), `chat`
      (`chat.js`), and `shared`. Test coverage must name all four — the
      `studio` glob alone covers fewer than half the call sites.
      *Split from 2a as a hard boundary, not an option (Architect cycle 1):
      2a is decided work and 2b is not, and holding decided work behind an open
      design question is the one sequencing error this flight can cheaply
      avoid.*
- [ ] `measurement` — **first step: re-verify the Concourse worker** (see
      Prerequisites). Then DD-5's staged Windows ladder as a new
      `ci/tasks/windows-vector-bench.yml` (DD-10's fresh venv, recorded
      dependency versions **and the SIMD/numkong backend**), with its tolerance
      band fixed and logged before the first run; and DD-4's fusion sensitivity
      sweep, which runs on Linux because it measures fusion arithmetic and not
      a platform. Re-checks Flight 3's flush constants against the measured
      curve. Closes two mission open questions. Product code changes only where
      the numbers demand it, and the write-up states DD-4's boundary explicitly.
      **The early-stop decision at 500k is the operator's**, escalated by the
      Flight Director with the measured curve in hand; the Developer does not
      make that call and does not idle waiting for it — it hands back and the
      leg resumes on the answer.
- [ ] `regression-net-and-gates` — re-author `kb-studio-round-trip` to `active`
      (six steps: the 9↔10 ordering, fresh-mount preconditions on 5/8/10,
      step 6's fixture mandate, step 2's misplaced action, and step 8 once
      Leg 2a has shipped its observable), add R13's large-folder settle variant
      to `kb-folder-index-round-trip`, then run and record `make lint`,
      `make test-unit`, full `make test-browser` (`TEST_TIMEOUT=3600`),
      `pip-audit` against the release closure, and a frozen Windows build.
      **This leg owns every Completion Checklist gate** — the reconciliation
      F6 Rec. 3 asked for. **Depends on Leg 2a** (step 8's observable must
      exist before the spec can assert against it) **and on Leg 3** (its
      numbers feed the flight log's metrics section). Runs last, and cannot be
      pulled forward.
- [ ] `hat-and-alignment` *(optional, interactive)* — a short walk over only
      what this flight makes operator-visible: the freshness field, the skip
      counters, and the confirm-lapse feedback. Deliberately small — Flight 6
      carried the mission-closing HAT, and re-walking it would spend the
      operator's scarcest resource on surfaces already aligned.

---

## Post-Flight

### Completion Checklist

Every item carries a leg owner, per F6 debrief Recommendation 3 — two unowned
items went unexecuted last flight.

- [ ] All legs completed — *Flight Director*
- [ ] `make lint` clean — *Leg 4*
- [ ] `make test-unit` green, with the count recorded against the F1–F6 series
      — *Leg 4*
- [ ] Full `make test-browser` green (`TEST_TIMEOUT=3600`, all four lanes) —
      *Leg 4*
- [ ] `pip-audit` clean against the release closure — *Leg 4* (needs squawk
      0083 landed first; see Prerequisites)
- [ ] Frozen Windows build succeeds and the built app runs — *Leg 4*
- [~] `kb-studio-round-trip` status `active` — **DONE**; **passing — NOT YET
      RUN** — *Leg 05 (spec), Flight Director (run)*. **Deliberately deferred,
      operator decision 2026-09-20**: the spec is re-authored and `active`, and
      the 18-step walk is scheduled before the flight's PR merges rather than
      before its commit. Recorded as **not-run, never as passed** — which is
      AC-17's own rule applied to this flight's own checklist. The mission
      criterion it backs ("a knowledge base can be attached to and detached
      from any agent in Studio, behavior-test-backed") therefore stays
      **unticked** until the run is green.
- [ ] Documentation updated: CLAUDE.md and `the_one/agents.md` for the shutdown
      hook, the skip-counter projection, the `get_kb_status` freshness
      aggregate and the new CI task — *Leg 4*
- [ ] Code merged to `mission/24-knowledge-bases` — *Flight Director*
- [ ] Mission open questions closed: Windows 1M re-measure, fusion balance —
      *Leg 3*
- [ ] Mission Known Issue closed: `get_vector_store()` shutdown hook — *Leg 1*
- [ ] Squawks 0087 and 0088 closed with sign-offs — *Leg 2a / Leg 2b*

**Leg map**: Leg 1 `non-ui-defect-closure` · Leg 2a `inventory-freshness` ·
Leg 2b `confirm-lapse` · Leg 3 `measurement` · Leg 4
`regression-net-and-gates` · optional `hat-and-alignment`.

**Not this flight's checklist**: the `mission/24-knowledge-bases` → `main` PR,
which gets the full CI lane, belongs to mission close and the mission debrief.

### Verification

The flight achieved its objective when Mission 24 can be closed without a
caveat: every success criterion either ticked or explicitly and honestly
deferred, every open question answered or re-assigned with a named vehicle,
the Known Issues list free of items whose resolution point has passed, and
`kb-studio-round-trip` re-runnable so the closing regression net is real rather
than nominal.

Three specific falsifiable checks, since "the mission can close" is not one:

1. `grep -c 'Resolution point: Flight 6' missions/24-knowledge-bases/mission.md`
   returns 0 — no Known Issue still names a flight that has landed.
2. Every unchecked mission success criterion has either a `[x]` with evidence
   or a recorded deferral naming its vehicle.
3. `tests/behavior/kb-studio-round-trip.md` reads `**Status**: active` with a
   `**Last Run**` timestamp from this flight.
