# Behavior Test: Knowledge Base Studio Round Trip

**Slug**: `kb-studio-round-trip`
**Status**: active *(re-authored five times; reverted to `draft` on 2026-09-21 to repair defects #7-#11, all of which held on the 2026-09-22 run. Returned to `active` on 2026-09-22 after that run scored **17 pass / 1 inconclusive / 0 fail** and the single inconclusive — a step 12->13 sequencing gap, **defect #15** — was fixed below. That fix's corrected sequence was itself executed during the run as step 13-bis and passed, so it ships verified rather than merely reasoned. See `runs/2026-09-22-01-05-35.md`.)*
**Created**: 2026-09-17
**Updated**: 2026-10-02 (M25 F3: "inventory" mapped onto the Library list and detail shell; see the note under Preconditions)
**Last Run**: 2026-09-22-01-05-35 — **17 pass / 1 inconclusive / 0 fail** across all 18 checkpoints, run strictly one-at-a-time in live two-agent mode. Step 5's `[continuous-session]` clause and step 9's full step-2-to-9 continuity span were **exercised for the first time** rather than recorded UNEXERCISED. The sole inconclusive (step 13) was a spec-sequencing gap, now fixed as defect #15. See `kb-studio-round-trip/runs/2026-09-22-01-05-35.md`.

## Intent

Mission 24's operator story is "point the app at a folder and your agents can
search it." Every part of that story below the screen is already covered —
Flight 3's `kb-folder-index-round-trip`, Flight 4's `kb-folder-watch-round-trip`
and Flight 5's `kb-agent-query-round-trip` each proved their slice against a
real instance through the API. This test is the first that drives the operator's
actual surfaces, and it exists for the things only a screen can falsify: that
the status a folder reports is the status the inventory renders, that an
attachment made in Studio is the attachment the agent gets, and — the reason
this spec exists — that **state the operator did not touch does not change
underneath them**.

Most of its assertions are *negative*: about state that must not move. That is
the class Flight 5's behavior test was found to be missing entirely, and each
one here exists because a specific defect was found, not because a happy path
suggested it. Squawk 0050 is a live data-loss path (a Studio save wipes
`kb_ids`); an unrelated Studio save also erases a `kb__` entry from
`disabled_tools`; and a knowledge base's derived tool name used to move when its
name changed *or* when the agent's attached set changed, silently re-enabling a
deliberately disabled tool. None is visible in a happy-path walk, and all are
invisible to unit tests of either surface alone, because each needs a real save
of one surface observed through a different one.

One assertion is deliberately *positive* (step 15): that an explicit API removal
still removes. Without it, a preserve rule that had quietly become a one-way
ratchet would pass every other step in this table.

## Preconditions

- A dedicated dev instance is running on a **non-default port with a scratch
  data directory** — never port 8484 and never the operator's default data dir.
  See CLAUDE.md, "SAFETY RULE — never target the operator's production
  instance".
- Credential mechanics follow CLAUDE.md's "Behavior-test credential convention"
  by reference. No step below encodes them.
- A fixture folder exists **outside the repository**, containing at least:
  - three small text or markdown files with distinct, greppable prose;
  - one further text or markdown file comfortably exceeding the chunk size —
    at least 3 KB of distinct prose, so it yields **at least three chunks**
    (chunk size 1000 characters). Needed so step 6's chunk-ordering clause has
    something to fail against: every file under ~1000 characters is
    single-chunk, and a one-element list is sorted vacuously (the defect named
    in the 2026-09-18-13-14-52 run log's FINDING 5). This makes the fixture's
    **good**-file count **four**, not three — steps 3 and 5 below are written
    against four.
  - one file that will fail indexing — **it must carry a supported extension
    (`.txt` or `.md`)** and be over `MAX_FILE_BYTES` (10 MiB) or contain a null
    byte in its first 8 KiB. A `.bin` or other unsupported suffix is filtered out
    by the walk and never becomes an item at all, so step 5's "failed, with its
    error legible in the UI" would be unobservable.
- **Sizing the restart fixture is necessary but NOT sufficient — the pre-stop
  poll must be a tight loop.** *(Defect #9, added 2026-09-21.)* The 2026-09-21
  run proved this by counterexample: a correctly-sized 400-file fixture **still
  failed** to catch an in-flight item on the first attempt, because
  registration and the first poll were issued as two separate tool
  invocations and the ordinary inter-call latency (~5 s) was longer than the
  entire index pass (~3 s). The second attempt caught it at **+0.0291 s** by
  issuing the registration and the whole polling loop from **one uninterrupted
  process**. So: **step 10's trigger and its polling loop must run in a single
  script with no tool-call boundary between them.** Fixture size buys margin;
  the tight loop is what makes the race winnable. An executor following the
  sizing guidance alone will reproduce the first attempt's failure.
- **A second, disposable fixture folder for step 10's restart-resume check
  only**: `<fixture-restart>`, outside the repository and distinct from the
  fixture above, sized so a full index pass takes on the order of several
  seconds to low tens of seconds — long enough for an operator (or the
  Executor) to issue a stop command while at least one item is still
  `indexing`. Reuse `kb-folder-index-round-trip.md`'s `live-kill` variant's
  generator pattern (many small text files) at a scale that keeps this
  spec's own runtime reasonable — for example 300-500 files of a few KB each
  — rather than authoring a second generator. It is registered on its own
  disposable knowledge base, created and deleted entirely within step 10, so
  it never affects steps 3, 5 or 8's item counts on the main fixture. This is
  the fix for the sixth defect named in the 2026-09-18-13-14-52 run log's
  Orchestrator Notes (`:735-742`): on a 3-4 file fixture an index pass
  completes faster than a stop command can land, so "stop it mid-pass" was
  previously unwinnable and the crash-recovery assertion was never actually
  exercised. Size it **at authoring time here**, never by growing it mid-run —
  growing it mid-run is exactly what would perturb steps 5/8's counts on the
  *other* fixture if this bullet were skipped and the main fixture reused
  instead.
- At least one agent exists with a configured provider, so the attach tab has
  something to attach to and the agent can be saved.
- **Steps marked `[continuous-session]` must run inside one uninterrupted
  browser page/process, from the step's trigger action through its
  observation** — no reload, no re-navigation to the app root, and no fresh
  Executor process boundary in between. This project's default apparatus
  re-mounts fresh at every step boundary (`storage_state` persists the session
  cookie, but not the page), which silently satisfies any "without operator
  action" or "same session" wording the moment the apparatus re-mounts — the
  gap the 2026-09-18-13-14-52 run log's FINDING 3 names. A step so marked is
  not judged PASS on a reading obtained by a fresh mount inside its span: the
  Executor states, for that step, which process/page continuity it actually
  achieved, and the Validator records the marked clause **UNEXERCISED** rather
  than PASS if a fresh mount occurred anywhere in the marked span — it does
  not fail the step outright. **Step 5 is a deliberate partial exception**: a
  genuinely continuous reading would need a second, throwaway registration
  event this spec does not budget for without risking steps 6-18's counts, so
  the Executor should still avoid navigating away where practical, but a fresh
  mount there records only that step's timing clause UNEXERCISED, per the run
  log's own disposition (FINDING 3).
- **Where a step requires a fresh client load, prove it — do not assert it.** *(Added 2026-09-22.)* Use
  `performance.getEntriesByType('navigation')[0].type === 'reload'`: it is set by the browser engine and
  cannot be fabricated by page script, unlike a self-reported "I reloaded". Before the continuity span
  ends, `window.__continuityMarker` going from its value to `null` serves the same purpose from the other
  direction (it proves a reload DID occur). After the span, the marker is permanently `null` and carries no
  information, so the navigation-timing signal is the only one left — the 2026-09-22 run had to improvise
  this mid-run at step 14 and it should not have had to.
- **The instance must be verified to be running the CODE UNDER TEST, not merely
  the right instance with the right data directory.** *(Defect #10, added
  2026-09-21 — its absence voided an entire eight-checkpoint run.)* `the-one
  serve` has no `--reload`, so Python changes need `make restart`; **static JS
  and CSS are served from disk per request and are always current**, which is
  precisely what makes a stale backend invisible — the rendered half of every
  observation looks correct while the API half is a previous build. Before
  step 1: read the server process's start time (`ps -o lstart -p <pid>`) and
  compare it against the last commit touching the features under test, **and**
  positively confirm a field that build introduced is present in a live
  response (absent, not null, is the signature of a stale build). Record both.
  This is a read-and-confirm bullet in the same spirit as the monitoring one
  below — the spec's own silence on it, not merely an operator's oversight, is
  what let a full run be judged against the wrong build.
- **Monitoring settings are read and pinned before the run, not assumed.**
  `monitoring.watch_enabled` defaults `true` and `reconcile_interval_seconds`
  defaults **300**; the reconciliation walk — not the watcher — is the source of
  truth, and on WSL2 a native notifier does not fire for Windows-side edits. So:
  read `GET /api/knowledge-settings` and record both values; read
  `GET /api/knowledge-bases/{kb_id}/status`'s `folders[].watch` and record it;
  and `PUT` a short `reconcile_interval_seconds` (for example 15) for the run.
  Every settle window below is expressed as a multiple of the **configured**
  interval, never as a bare "reasonable window" — otherwise a step that is
  really waiting 5 minutes on the walk reads as a watcher failure.

> **Since Mission 25 Flight 3: what "the inventory" means in this shell.** Knowledge bases
> are rows in the **"Knowledge bases" group of the Library list** (the aside). An open
> knowledge base's items, chunks, source text and search are in the **detail pane** beside
> it.
>
> - **Creating** (step 2) is **Add → Knowledge base**. It opens a create form at
>   `#library/knowledge/~new`, and **Create opens the new knowledge base's detail view**
>   (squawk 0101), so the next action starts there.
> - **Closing a knowledge base** uses the breadcrumb link "Knowledge bases" in its header.
>   There is no Back button.
> - **"Appears in the inventory"** means a row in that group, and "the inventory shows
>   only …" means that group's rows.
>
> The step table's assertions are unchanged.

## Observables Required

- **browser** (rendered Studio surfaces — measured via chrome-devtools,
  playwright, or similar). Rendered state is primary: screenshot plus
  accessibility snapshot. DOM evals are supplementary diagnostics only. An
  apparatus driving a `[continuous-session]` step must be capable of keeping
  one page/process alive across that step's whole span (e.g. Playwright driven
  from one script, not one Executor process per step) — a spec depending on
  session continuity should fail at READY if the apparatus cannot do this, not
  discover it mid-step.
- **http** (API read-back for state the UI collapses or cannot show — measured
  via curl through Bash or a dedicated MCP):
  - `GET /api/knowledge-bases/{kb_id}/status` — per-folder `status`, `watch`,
    `watch_error`; `chunks`; `content_freshness`; `indexer`
  - `GET /api/agents/{name}` — `kb_ids`, `disabled_tools`
  - `GET /api/knowledge-bases/{kb_id}/search` — `hits`, `degraded`, `indexer`
- **filesystem** (fixture creation, edit and deletion — measured via Bash /
  Write), to trigger real indexing and real watcher activity.
- **shell** (instance stop/start for the restart-resume step — measured via
  Bash).

## Steps

**Row 9 (attach) runs before Row 10 (restart-resume) — a deliberate local
swap from this spec's original step order, not a bug.** Row 10 restarts the
instance, which ends any browser session; Row 9 requires attaching within the
same session as step 2's create, which a restart would foreclose. Swapping them
satisfies both with **no coverage loss**: nothing in steps 11-18 needs
continuous-session state (they read fresh per step), and Row 10's restart
threatens nothing downstream once it runs after Row 9's attach. (AC-1,
2026-09-18-13-14-52 run log's Orchestrator Notes and Executor closing.)

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open the Library destination's Knowledge section in the browser (rail "Library" → `#library/knowledge`). | The section renders a real inventory surface — a create affordance and either a list of knowledge bases or an empty state. The Flight 5 stub text ("Knowledge bases will be created and managed here in a future mission") is **absent**. |
| 2 | Create a knowledge base with a short name. Then attempt to create one with a name longer than 43 characters. After observing the length-hint behaviour, delete the over-long knowledge base. | The first is created and appears in the inventory. The second surfaces a length hint naming the limit — and, per DD-16, the hint is **advisory**: the second knowledge base **is** created and stays in the inventory until deleted. Assert both, so the decided behaviour is judged rather than the intuitive one. After the deletion action, the inventory shows only the first knowledge base — the cleanup actually removed it rather than merely being instructed to. |
| 3 | Register the fixture folder on the new knowledge base. | The folder appears with a walk status. No error is shown. |
| 4 | **SAFETY: name the instance's own scratch data directory itself — never `$HOME`, and not its parent.** Attempt to register that path as a second source. | Refused, and the message **says why** — that the application's own database and index live there. A bare "422" or "invalid path" is a fail. *(The data dir itself is the deterministic case: a parent that happens to be the filesystem root trips a different, earlier guard with different wording.)* |
| 5 | (Wait point, no actions.) *(Step 3's registration kicks an index pass immediately, so this wait does not depend on the reconcile interval — step 8's does.)* | Within two configured reconcile intervals, the inventory shows the **four** good fixture files as indexed and the deliberately-bad file as **failed, with its error legible in the UI**. `GET /status` agrees: `items` counts match what is rendered, and `chunks` is greater than zero. This clause is `[continuous-session]` on a best-effort basis only (see Preconditions) — a fresh mount during this step's span records it **UNEXERCISED**, not a fail. `[mixed-frame]` |
| 6 | Open the multi-chunk fixture item — the file mandated in Preconditions to exceed the chunk size — and read its chunks, then its source text. | Chunks render in sequence order, and the clause is falsifiable here: the mandated file yields at least three chunks, so an out-of-order render has something to show against. Source text renders and matches the fixture file's prose. |
| 7 | Run a search from the inventory for an exact, rare term that appears in exactly one fixture file. | The hit set contains that file's chunk, with its score rendered. If a degrade line is shown, it names a cause and is accompanied by the indexer state; if no degrade line is shown, `GET /search` reports `degraded: null`. `[mixed-frame]` |
| 8 | Before editing, read and record: (a) `GET /status`'s `content_freshness`; (b) the **per-item** `Indexed:` timestamp (`data-testid="kb-item-indexed-at"`) off the row of the file you are about to edit, scoped to that file's own DOM group; (c) `folders[].watch`. Then add a new file to the fixture folder on disk AND edit that existing file — the edit must change the file's **size**, since `plan_reconcile` keys change-detection on `size_bytes`/`mtime` and a same-size same-mtime edit is not detected as changed at all. Wait two configured reconcile intervals. Take no action in the UI during the wait. `[continuous-session]` | Both changes are reflected in the inventory **without any operator action in the UI and without restarting the app**: the new file's row appears, and the edited file's row shows an `Indexed:` timestamp **later than the one recorded before editing**. **On `content_freshness`** *(clause rewritten 2026-09-21, defect #8)*: it must have advanced past its pre-edit value, and must **equal `MAX(indexed_at)` across all file items**, and that maximum must belong to **one of the items changed in this pass**. **Do NOT assert that `content_freshness` equals the edited file's own timestamp** — this step's own Actions change *two* items in one reconcile pass, so the aggregate legitimately takes whichever indexed last, and an equality assertion would pass or fail on unordered race timing rather than on behaviour. (The 2026-09-21 run measured a 1.868 ms divergence for exactly this reason: `content_freshness` equalled the *new* file's timestamp, not the *edited* file's. The feature was correct; the clause was not.) The point of the clause is to rule out a **spurious** freshness signal, which is why a **folder-level** `indexed_at` is **not** evidence here — it advances on every walk, changed content or not. Record whether `folders[].watch` was active, so a pass carried by the reconcile walk alone is not mistaken for a working watcher. `[mixed-frame]` |
| 9 | Open an agent (rail "Agents"), go to its Knowledge tab, attach the knowledge base **created in step 2**, and save. **CONTINUITY SPAN — read this carefully** *(clarified 2026-09-21, defect #11)*: this step requires **one unbroken page, never reloaded or re-navigated to the app root, reaching all the way back to step 2's create** — spanning steps 3, 4, 5, 6, 7 and 8. It is **not** continuity within step 9 alone. A fresh mount anywhere in that span re-fetches the tab's list, which would then contain the knowledge base **regardless of the behaviour under test**, and the step would pass while testing nothing. Use a marker that a reload would destroy (e.g. `window.__continuityMarker`, set at step 1 and re-read at every step) so continuity is **falsifiable evidence**, not self-report. `[continuous-session]` | The knowledge base is **present in the tab's list at all** (the create-then-attach path — this presence, not the successful save, is the load-bearing observation), renders as attached after save, and `GET /api/agents/{name}` reports its id in `kb_ids`. An absent entry means the tab's list is stale. |
| 10 | Create a fresh, disposable knowledge base and register `<fixture-restart>` on it (Preconditions) — registration kicks off an index pass immediately. **Issue the registration and the entire polling loop from ONE uninterrupted process** (see Preconditions — a tool-call boundary here loses the race). Poll `GET .../status` until at least one item reports `indexing`, then stop the instance immediately. Start it again. Poll `GET .../status` until the indexer reports idle — a bare two-interval wait is not sufficient, since this fixture's pass duration is not bounded by the reconcile interval. **Then delete this disposable knowledge base** *(moved here from Expected Results, 2026-09-21, defect #7 — it is an action, and an action in the results column cannot be judged)*; it plays no further role in the spec. | The pre-stop poll shows at least one item in `indexing` before the stop — a stop that never observes an in-flight item is not evidence for anything and must be re-attempted, not recorded as a pass. After restart, indexing **resumes rather than restarts**: no item is stranded in `indexing` once the indexer reports idle, and `<fixture-restart>`'s files reach a terminal status (`indexed` or `failed`) with none left at `pending`/`indexing`. `GET /status` shows no `indexing` item once the indexer reports idle. **Known limitation of this evidence** *(recorded 2026-09-21)*: if the stop is caught at `indexed:0`, a terminal post-restart state cannot distinguish genuine resume from a wipe-and-reindex — both produce identical aggregates. To assert resume **literally**, snapshot which item ids and `content_hash`es were already `indexed` before the stop and assert those exact records survive untouched afterwards, with only the `pending`/`indexing` items showing fresh `indexed_at`. |
| 11 | **Squawk 0050's regression net.** Go to that agent's **General** tab, change an unrelated field (for example the description), and save. Do not touch the Knowledge tab. | `GET /api/agents/{name}` still reports the knowledge base in `kb_ids` — **unchanged**. The Knowledge tab still renders it as attached. A wiped `kb_ids` is the exact defect this step exists to catch. |
| 12 | **Read the derived tool name off the attach-tab row** (do not compute it — the collision-discriminator logic is exactly what must not be reimplemented here). Then disable it for that agent via `PUT /api/agents/{name}`, adding that name to `disabled_tools`. *(There is deliberately no UI for disabling — see Out of Scope.)* | The row displays a `kb__…__search` name, and `GET /api/agents/{name}` then lists that exact name in `disabled_tools`. |
| 13 | **DD-13's regression net.** **FIRST, force a fresh client load** (full reload; confirm it genuinely happened via `performance.getEntriesByType('navigation')[0].type === 'reload'`, which in-page script cannot fabricate). *(Defect #15, added 2026-09-22 — this beat is load-bearing, not hygiene.* Step 9 mandates one unbroken page back to step 2, and step 12 sets `disabled_tools` through the **only** path that exists — a direct API `PUT`, since Out of Scope states there is no UI for it. Those two individually-correct requirements collide: by the time this step runs, the page's in-memory config necessarily predates step 12's `PUT`, so an unrelated save from it drops the entry and this step reads as a DD-13 failure when DD-13 is fine. Without this fresh load the step tests client staleness, not the union logic its Expected Results describe. The 2026-09-22 run hit exactly this and had to resolve it with an out-of-band experiment.)* **Then** make another unrelated Studio save from the agent's **General** tab. Do not touch any tool or knowledge-base control. | `GET /api/agents/{name}` still lists the `kb__…__search` name in `disabled_tools` — **unchanged**. An erased entry means a deliberately disabled tool has silently re-enabled, and is a fail. |
| 14 | **DD-5's regression net.** Rename the knowledge base from the inventory, then reopen the agent's Knowledge tab. | The row's displayed tool name reflects the new name, and `GET /api/agents/{name}` shows `disabled_tools` containing **that same name** — i.e. the entry was rewritten, not left stale. Comparing the two is the assertion; a `disabled_tools` entry that no longer matches the displayed name means the tool has silently re-enabled, and is a fail. |
| 15 | **DD-13's inverse — the un-disable path.** Via `PUT /api/agents/{name}`, send a `disabled_tools` list that omits the `kb__…__search` name. *(`AgentConfig` validates the whole object, so GET-then-PUT; the GET returns `__MASKED__` credential values, which the server preserves.)* | `GET /api/agents/{name}` shows the entry **gone**. This step is why DD-13 is a client-side union and not a server-side preserve: a server-side "always re-add" would make this impossible, and steps 12–14 alone would pass against that ratchet. A surviving entry here is a fail. |
| 16 | **DD-17's net — set membership must not move a derived name.** Re-add the `disabled_tools` entry removed in step 15. Then create a *second* knowledge base with **the same name** as the first and attach it to the same agent. | Both rows render distinct `kb__…__search` names. The **first** knowledge base's displayed tool name is **unchanged** from step 14, and `disabled_tools` still matches it — so its disabled tool did not silently re-enable when a same-named sibling joined the set. A changed name here means DD-17 was not applied. |
| 17 | Delete the second knowledge base, then reopen the agent's Knowledge tab. | The first knowledge base's displayed tool name is **still unchanged**, and `disabled_tools` still matches it — detaching/deleting a colliding sibling does not move it either. |
| 18 | Delete the first knowledge base from the inventory while its folder is registered. Then reopen the agent and save it once from the General tab. | Per DD-14: it disappears from the inventory; `kb_ids` **still** carries the now-dangling id immediately after delete with no error anywhere, and after the subsequent save the id is **gone**. Its `disabled_tools` entry remains — inert by DD-17, since any future knowledge base has a different `kb_id` and therefore a different derived name. All three are asserted. |

## Out of Scope

- Agent-side query behaviour end to end — covered by
  `kb-agent-query-round-trip` (Flight 5), including the unattached-agent
  isolation assertion.
- **A UI for `disabled_tools` on a `kb__` tool.** None exists: the Tools tab
  renders built-in tools only, and MCP per-tool disables live in
  `mcp_overrides`. Step 12 therefore uses the API deliberately, not as a
  shortcut. If a later flight adds such a surface, steps 12–14 should be
  re-authored to drive it.
- Watcher mechanics under load and the `starting`/`idle`/`running` tolerance —
  covered by `kb-folder-watch-round-trip` (Flight 4) and the `large-folder
  settle` variant on `kb-folder-index-round-trip` (Flight 7).
- Indexing pipeline internals (chunking boundaries, embedding correctness) —
  covered by `kb-folder-index-round-trip` (Flight 3) and unit tests.
- The Settings destination's Knowledge panel (`#settings/knowledge-indexing`) — a separate surface; covered by browser-lane
  tests rather than here, since nothing about it needs real-environment
  observation.

## Variants (optional)

None yet. A "large fixture folder" variant would duplicate
`kb-folder-index-round-trip`'s "large-folder settle" work and should be
authored there, not here.
