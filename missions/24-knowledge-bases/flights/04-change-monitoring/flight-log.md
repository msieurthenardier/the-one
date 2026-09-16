# Flight Log: Change Monitoring

**Flight**: [Change Monitoring](flight.md)

## Summary

Planning complete (2026-09-16). `flight.md` at `ready` after three Architect cycles (needs rework → needs rework → approve with changes; the third pass at the operator's request past the max-2 rule); operator interview and two checkpoints recorded below; twenty planning premise probes against `watchfiles`, four of them corrected after cycle 1 found the WSL polling default; the behavior-test draft `kb-folder-watch-round-trip` is filed. No code has changed.

---

## Leg Progress

*(none yet)*

---

## Decisions

### Flight Director Notes — flight start (2026-09-16)

- Loaded `.flightops/ARTIFACTS.md`, `FLIGHT_OPERATIONS.md`, `agent-crews/flight-design.md` (structure valid: Crew, Interaction Protocol, Prompts present).
- Sources read: `mission.md` (Flight 4 bullet, Open Questions, Known Issues, Branch Layout), Flight 3 `flight.md` (DD-1, DD-3, DD-5, DD-6, DD-7, DD-8, DD-9), Flight 3 `flight-debrief.md` (Recommendations 2, 3, 6, 7; Technical notes), the four Flight 3 leg artifacts, `tests/behavior/kb-folder-index-round-trip.md`.
- Code read: `the_one/knowledge/manager.py` (whole), `walk.py` (skip rules inline at the dot-prefix, `SKIPPED_DIRS` and suffix checks), `settings.py` (whole), `connectors/manager.py` (`ConnectorManager` supervisor loop), `interfaces/web/app.py` (indexing-manager lifespan block; the purge and catalog-refresh loops), `interfaces/web/api.py` (knowledge-base routes, `_after_folder_registered`, knowledge-settings routes), `diagnostics.py` (`run_doctor` gates, `_vector_probe_outcome`, `_probe_usearch`), `platform/paths.py`, `tests/test_kb_manager.py` (fixtures), `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order`, `tests/conftest.py` (`THE_ONE_DATA_DIR` isolation), `ci/tasks/windows-installer-build.yml` and `.github/workflows/windows-installer.yml` (by-name needles), `the_one/agents.md` (the two conventions named by squawk 0065; the eight-gates table).
- HAT: not planned. The operator's rule at the Flight 3 debrief — HAT legs only where there is a screen — applies; this flight has no UI surface. The walk-through joins Flight 6's HAT.
- Branch: `mission/24-knowledge-bases` at `a657873`, 36 ahead of `main` (`970c5d4`, release 0.8.1), 0 behind. No merge from `main` at this boundary.
- Methodology (Flight 3 debrief Recommendation 4): every number the operator had not given — settle 5 s / hold 60 s, interval 300 s, the 10 s floor, the 5 s drain budget — was put to the operator as a labelled Flight Director proposal or is recorded in the DD as one. The drain budget (5 s) and the interval floor (10 s) were not asked; they are Flight Director proposals recorded as such in DD-4 and DD-7.

### Operator interview (2026-09-16)

| Question | Answer |
|---|---|
| Open-ended input on scope and approach | "no preferences" |
| Where the interval and on/off switch live | **Administration knowledge settings** (over env vars, the recommended option) → DD-5, live application |
| Default reconciliation interval (proposal) | **5 minutes** → DD-4 |
| Refuse registering a folder that contains the data directory | **Yes, 422, plus the filter** → DD-6 |
| Ninth `doctor` gate for the file watcher | **Yes, frozen-only** → DD-9 |
| Settle window / hold cap (proposal) | **5 s settle, 60 s hold cap** (over the recommended 2 s / 30 s) → DD-3 |
| Vehicle for the Windows 1M `usearch` re-measure | **Fold into Flight 6 / mission close** → DD-12 |

### Planning premise probes (2026-09-16, this host: WSL2, kernel 6.18, `watchfiles` 1.1.1, Python 3.12)

| # | Premise | Method | Result |
|---|---|---|---|
| P1 | `watchfiles` is importable and its API matches the plan | `import watchfiles; inspect.signature(awatch)` | 1.1.1; `awatch(*paths, watch_filter, debounce=1600, step=50, stop_event, rust_timeout, yield_on_timeout, force_polling, poll_delay_ms, recursive=True, ignore_permission_denied)`; `Change ∈ {added, modified, deleted}`; a filter is any `(Change, str) -> bool` |
| P2 | A recursive subscription reports files created in brand-new subdirectories | `awatch(tmp)` while creating `sub/a.txt`, `.hidden/b.txt`, `node_modules/c.txt` with `watch_filter=None` | One set at +0.65 s with all six `added` paths — the filter is ours to apply (DD-2) |
| P3 | A missing root fails loudly at subscription | `awatch(tmp / "missing")` | `FileNotFoundError` at construction |
| P4 | Behaviour when the root is removed while subscribed | `shutil.rmtree(root)` under `awatch(root, rust_timeout=500, yield_on_timeout=True)` | **Measured on the polling backend — superseded by P13.** No exception; `deleted root` re-reported every ~300 ms (that is `poll_delay_ms`), not native behaviour |
| P5 | The stop event is honoured promptly | `stop_event.set()` from a task | Generator returned within the next step (~50 ms) in P2 and P4 |
| P6 | Events arrive on a Windows drive mounted under WSL2 | `awatch("/mnt/c/Temp/…")` while writing `p.txt` | **Measured on the polling backend — superseded by P15.** Polling delivers on any mount; the Flight Director's first reading ("drvfs delivers events") was the polling backend, not native notification |
| P7 | The extension is packaged for the operator's platform | `grep watchfiles uv.lock` | cp311 wheels for `win_amd64`, macOS x86_64/arm64, manylinux x86_64/aarch64; `anyio>=3.0.0` dependency already in the closure |
| P8 | The frozen build reaches `watchfiles` today | `grep watchfiles packaging/ ci/ the_one/` | No direct reference anywhere; reached only through `uvicorn.supervisors` (`from watchfiles import watch` under `try`), which `serve` never uses → DD-9's gate and the direct declaration |
| P9 | inotify headroom | `/proc/sys/fs/inotify/max_user_watches`, `max_user_instances` | 1,048,576 / 8,192 |
| P10 | Test data-dir isolation vs DD-6 | `tests/conftest.py:36`, `tests/test_db_api.py::client` | `THE_ONE_DATA_DIR` is a `mkdtemp(prefix="the-one-pytest-")` set once; the API client fixture does not re-point `settings.data_dir`, and every folder test registers under its own `tmp_path` — disjoint from the data dir in both directions |
| P11 | Drain order pin | `tests/test_mcp_pool.py:686-805` | `_FakeIndexingManager` spy and the pinned list exist as Flight 3 left them; DD-7 inserts `watch_start`/`watch_drain` between `indexing_start` and `indexing_drain` |
| P12 | Doctor needles | `ci/tasks/windows-installer-build.yml:110`, `.github/workflows/windows-installer.yml:96-106` | Both lanes grep `usearch: OK`, `fts5: OK`, `embedding model: OK` by name; `file watcher: OK` joins both |

**Correction after Architect cycle 1 (2026-09-16).** `watchfiles.main::_default_force_polling(None)` returns **`True` on this host** (WSL2: `'microsoft-standard'` in the kernel release), so P2, P4, P5 and P6 above measured the *polling* backend, not native notification. The rows are kept with their supersession noted; the pinned-native re-probes follow. Lesson for the log: a library that picks a backend from the environment must have that knob pinned before its behaviour is measured — DD-0 now pins every knob at both call sites.

| # | Premise (native backend pinned: `force_polling=False`, `ignore_permission_denied=True`) | Method | Result |
|---|---|---|---|
| P13 | Root removed while subscribed | `shutil.rmtree(root)` under `awatch(root, …)` | **Exactly one** set at +0.40 s: `deleted <root>`, `deleted <root>/a.txt`; then silence until the stop event — the subscription is dead without saying so (DD-1 leaves it and re-subscribes on the tick; DD-2 lets the root's own path always pass the filter) |
| P14 | Root renamed away | `root.rename(sibling)` | One set: `deleted <root>` — a rename reads as a delete; no `modified <root>` (DD-1's first draft had a `modified`-on-rename clause; removed) |
| P15 | Events on a Windows drive under WSL2 | `awatch("/mnt/c/Temp/…")` while writing `p.txt` | **Nothing delivered** in 1.7 s — native inotify does not see drvfs; the folder would read `watching` and rely on the periodic walk (DD-0 records it; the behavior spec's fixture must be on a native filesystem) |
| P16 | Path shape and new-subdirectory delivery | create `sub/a.txt` and `b.txt` under a watched root | One set: `added <root>/b.txt`, `added <root>/sub`, `modified <root>/sub/a.txt` — paths are the subscribed root plus a relative part (DD-2's pure comparison is exact); a file inside a brand-new subdirectory is reported |
| P17 | Unreadable subdirectory under the root | `chmod 000 <root>/secret`, then write `<root>/c.txt` | With `ignore_permission_denied=True`: subscription established, `added <root>/c.txt` delivered. (Architect, cycle 1: with the default `False` the subscription raises `PermissionError` at construction — a folder the walk indexes fine would read `unavailable` forever) |
| P18 | `anyio` default thread limiter | `anyio.to_thread.current_default_thread_limiter().total_tokens` (Architect) | 40, shared with Starlette's `run_in_threadpool` — the reason DD-1 runs each subscription on a dedicated thread rather than through `awatch` |
| P19 | `ignore_permission_denied` semantics (Architect cycle 2, re-verified by the Flight Director) | sync `watch(root, force_polling=False, ignore_permission_denied=…, rust_timeout=300, yield_on_timeout=True)` on a thread | **`True` swallows every registration error**: a missing root constructs and yields empty sets (`['empty','empty']`); with `False` a missing root raises `FileNotFoundError: No path was found.` and an unreadable subdirectory raises `PermissionError … about ["<root>/secret"]`, which `True` survives. Contrary to the `.pyi`. → DD-0's two-step rule |
| P20 | Stop latency of the dedicated-thread subscription | `stop_event.set()` → generator return, `rust_timeout=1000, step=50` | **0.9 ms** on this host (the Architect measured 16 ms) — the 5 s drain budget is generous by three orders of magnitude |

### Architect design review — cycle 1 (2026-09-16)

**Verdict**: needs rework. The spine (trigger-only watcher, shared predicate, periodic walk as correctness, data-dir refusal, drain ordering, additive `/status`) confirmed against the tree; every `file:symbol` citation checked, two accuracy slips found. Findings and how each was incorporated:

| Severity | Finding | Incorporated as |
|---|---|---|
| high | `watchfiles` force-polls by default on WSL; P2/P4/P5/P6 measured polling; DD-9's "native" claim was unverifiable | **DD-0** (new): every knob pinned at both call sites; probes re-run (P13–P18); operator chose native everywhere at the checkpoint |
| high | DD-1's root-removal rule (`deleted` **or `modified`** on the root) would tear the watch down on every file creation, since a file added inside the root yields `modified <root>` | DD-1: `Change.deleted` on the root only; `modified <root>` pinned as survivable by a unit AC; P14 shows rename also reads as `deleted` |
| high | `ignore_permission_denied` defaults to `False`; one `chmod 000` subdirectory kills the subscription at construction while the walk skips and counts it | DD-0 pins `True`; P17 verifies; AC added |
| medium-high | The filter is applied after the notifier has registered watches for the whole tree, so the inotify-descriptor argument does not hold | DD-2 "Honesty about what the filter does not do"; the ENOSPC degrade is the answer |
| medium | The reconcile tick and a sibling folder's timer can `request_index` inside a delete route's `stop → delete` window, re-opening the Flight 3 AC-10 race | DD-3 `suppress(kb_id)` async context manager; DD-8 both delete routes hold it; AC |
| medium | `is_watch_candidate` would drop `deleted <root>` for a root with a dotted name | DD-2 clause (1): the root's own path always passes; test with a dotted root |
| medium | `Path.relative_to` raises for a path outside the root (macOS `/private/var`, Windows casing); a raise inside `watch_filter` kills the subscription | DD-2 clause (2): never raising, returns False |
| medium | A merged `is_skipped_name` called at the top of the walk loop would change `WalkResult` counter semantics | DD-2: `is_hidden_name` replaces only the dot-prefix check at its existing site; `SKIPPED_DIRS` stays inline and counted |
| medium | Leg 2 was the whole feature | Split: `watch-manager` (module + tests, no wiring) and `wiring-routes-and-docs` |
| medium | DD-9's "first yield non-empty" is a false-FAIL on a loaded frozen runner | DD-9: iterate until non-empty or a 10 s deadline, explicit close, 200 ms debounce; `_vector_probe_outcome` is already name-agnostic |
| medium | `indexer = idle` asserted at a 10 s interval samples mid-pass | Spec: `idle` or `running` wherever the interval is 10 s; counts carry the assertion |
| medium | Step 8's 20 s cold-restart bound is too tight (model load in the first pass) | Spec: 60 s |
| medium | DD-3's `loop.call_later` cannot be driven by a fake clock | DD-3: small real values through constructor keywords; Verification reworded; delay clamped ≥ 0 |
| medium | `awatch` blocks a worker of the shared 40-token `anyio` limiter | DD-1: dedicated daemon thread per subscription; cap 64 (operator's choice at the checkpoint) |
| medium | The live-apply hook's sync/async shape was unpinned | DD-5: `async def`, awaited by the route |
| medium | DD-1's ENOSPC premise had no negative test | DD-1: factory-raised `FileNotFoundError` / `OSError(ENOSPC)` / `RuntimeError` ACs |
| low | "four test modules" → three | DD-5 corrected |
| low | `state()` `"off"` conflated three conditions; `watching` could be reported before the subscription existed | DD-1: entry before task; `starting` state; `watching` only after the first yield |
| low | `excluded_roots` should be a constructor keyword | DD-2 |
| low | Spec's row note claimed the item id changes across root removal and return; the walk leaves children untouched on `OSError`, so it does not | Spec note corrected |
| low | "No `POST …/reindex` was made" is Executor conduct, not an observable | Moved to the Actions column |
| low | Registering the home directory now 422s (data dir is under the profile) | DD-6 detail hint |
| low | The 60 s launcher join also covers other drains | DD-7 margin sentence |

Architect questions answered at the operator checkpoint (2026-09-16): backend → **native everywhere** (DD-0); watched-folder bound → **64, degrade past it** (DD-1); gate shape → **import unconditional, round-trip frozen-only** (DD-9). Question 3 (use `stop_kb` during a folder delete) resolved by design instead: `suppress(kb_id)` closes the window without restarting sibling watches.

Suggestions taken: a Divert criterion for the backend; the one-request-per-window count as a unit AC; DD-4 names the resurrect-a-`stopped`-worker property. Suggestion not taken: a `watch_backend` field on `/status` — with DD-0 pinning native everywhere the field would be constant.

Substantive changes → a second Architect pass.

### Architect design review — cycle 2 (2026-09-16)

**Verdict**: needs rework — one high, ten medium, six low. Cycle-1 incorporation: 19 of 23 findings incorporated in full; the `ignore_permission_denied` fix (cycle 1, high) introduced the new high; two sibling sites were missed (the exact-dict `/status` test; the Flight 3 spec's parent-folder 409); the fake-clock wording survived in the behavior spec's Out of Scope. Findings and how each was incorporated:

| Severity | Finding | Incorporated as |
|---|---|---|
| high | `ignore_permission_denied=True` swallows every registration error — a missing root or an inotify `ENOSPC` reads `watching` for ever; Step 9's `unavailable` could not pass; the factory-driven negative ACs would pass green against a library that can never raise | DD-0 two-step subscribe (`False` first, `True` only on `PermissionError`; P19); DD-1 records it; one AC through the real `watch` on a missing root |
| medium | An empty timeout yield (one per second) re-arming the settle timer would fire a `request_index` per KB every 60 s for ever | DD-1: empty yield marks `watching` once and does nothing else; AC |
| medium | The per-folder task had no termination path — every `stop`/`drain` would burn the full timeout | DD-1: terminal sentinel posted from the thread's `finally`; task returns on it; AC "every `stop` returns without waiting" |
| medium | `call_soon_threadsafe` from an abandoned thread after loop close raises | DD-1: guarded with `try/except RuntimeError` + `is_closed()` |
| medium | Error path covered only construction, not a mid-iteration `WatchfilesRustInternalError` | DD-1: whole `for` body wrapped; AC for a generator raising after a first yield |
| medium | DD-2 clause (5) did not lower-case the suffix (`NOTES.MD` on Windows/macOS) | DD-2 pins `.lower()`; test |
| medium | Raw `path == str(root)` is fragile on Windows (drive-letter case, `\\?\` prefix) | DD-2: `os.path.normcase` on both sides in clauses (1) and (2); Windows premise recorded as a Divert criterion |
| medium | DD-6 makes the Flight 3 spec's Step 6 (parent of fixture → 409) read 422 when `<scratch>` is under `/tmp` | DD-6: Leg 1 amends the Flight 3 spec's Preconditions (nested fixture); re-run is the operator's call |
| medium | `test_reports_folder_projection_and_manager_state` asserts `folders[]` by exact dict equality | DD-8 names it |
| medium | The doctor probe's single early write can be lost (notifier exists only after the first `next()`); a 10 s deadline × ~20 full `run_doctor` tests | DD-9: writer writes on every timeout yield; 2 s unfrozen / 10 s frozen; full-run tests monkeypatch the probe (the embedding-probe precedent) |
| medium | `start`/`stop`/`stop_kb` sync-vs-async shape unpinned | DD-1 surface list pins each |
| low | `raise_interrupt` still inherited | DD-0 pins `False` |
| low | Spec Out of Scope still said "fake clock" | Spec corrected |
| low | Two more gate-count sites (`run_doctor` docstring; `agents.md` "Six of the eight", "separate from the eight gates") | DD-9 sweeps them |
| low | `folders[].status` sampled mid-pass at a 10 s interval | Spec: one re-poll allowed on `pending`/`indexing`; DD-10 |
| low | Suppression: the tick's check must be synchronous next to `request_index`; the context manager must release in `finally` (routes raise 404 inside it) | DD-3 |
| low | inotify *instances* (default 128 on many distros) beside the descriptor note | DD-1 |

Architect questions: Q1 → the two-step subscribe (full fidelity). Q2 → attempt always, 2 s unfrozen deadline, full-`run_doctor` tests monkeypatch the probe. Q3 → amend only in Leg 1; a Leg 4 re-run of the Flight 3 spec is put to the operator. Suggestions taken: measured stop latency recorded (P20); the two new ACs listed explicitly; DD-10 names Step 3 as the clean proof. Not taken: back-off in `_resubscribe_unavailable` (one `FileNotFoundError` per tick per missing root is accepted at the 300 s default).

**Max-2 cycles reached with the second verdict still "needs rework"** — escalated to the operator per the skill: run a third Architect pass on the incorporated spec, or mark it ready on the Flight Director's incorporation.

**Operator checkpoint (2026-09-16)**: a **third Architect pass** on the incorporated spec before it is marked ready (the Flight 3 override, repeated); the Flight 3 behavior spec is **amended only** in Leg 1 — Leg 4 does not re-run it.

### Architect design review — cycle 3 (2026-09-16, operator-authorised)

**Verdict**: approve with changes — one medium, nine low, all text-level; the flight judged buildable as four legs. Cycle-2 incorporation: 16 of 17 in full; one partial (two further gate-count sentences unswept); one self-contradiction (DD-2 clause 1's form). Findings and how each was incorporated:

| Severity | Finding | Incorporated as |
|---|---|---|
| medium | The two-step subscribe retries with `True` on a `PermissionError` caused by the *root itself*, constructing a zero-watch subscription the first empty yield reports as `watching` | DD-0: `os.access(root, R_OK\|X_OK)` before the retry; an unreadable root → `unavailable` with the reason (Flight Director's call: visible); AC |
| low | Two more gate-count sentences (`run_doctor` "The other four … gate unconditionally"; `agents.md:1353`) | DD-9 sweep list |
| low | DD-2 clause (1) showed a raw string compare while forbidding one | Pinned `PurePath(normcase(path)) == PurePath(normcase(root))` |
| low | "helper thread writes on every timeout yield" is unimplementable as written | DD-9: the probe writes in the loop that consumes the yields (measured 0.35 s to first non-empty, 8/8) |
| low | Cap-created entries have no task; `drain` gathers tasks | DD-1: `task: Task \| None`; AC |
| low | Leg 1 checkpoint omitted the Flight 3 spec amendment, the dependency declaration, the CI needles; the parent-folder constraint was prose only | Checkpoint widened; the constraint becomes an explicit Precondition of the Flight 3 spec |
| low | Probe tests vs the autouse stub in `test_doctor.py` | DD-9: the `_probe_usearch` precedent (module-top import), stated |
| low | `except PermissionError` must precede `except OSError` | DD-0 |
| low | DD-3 claimed both delete routes raise 404 inside the guarded region | DD-3 corrected (`delete_kb_item`'s 404s fire before it) |
| low | Two filter/walk divergences: dotted-directory rename yields no trigger; `SKIPPED_DIRS` case-insensitive on Windows | DD-2 records both as latency-only; the `Change`-aware clause (5) suggestion declined (build-tree `.o` churn) |
| low | Recon row said Leg 3 amends the open question; the convention citation over-claims; `SECURITY-MODEL.md` content unnamed | Recon row → Leg 4; DD-1 states what is and is not shared with the convention; Completion Checklist names the bullet's content |

Suggestions taken: one `_schedule` after a successful (re)subscribe (DD-1); deadlines as module constants and the `TMPDIR` note (DD-9); the log-noise note for the Executor (spec row conventions). Declined: passing `Change` to the filter (recorded in DD-2 with the reason). Architect questions: Q1 → `unavailable`; Q2 → explicit Precondition; Q3 → same file, `_probe_usearch` precedent. Verified clean by the Architect and recorded: `is_hidden_name` counter-neutral (one `startswith` site); Step 4's three 422s under pydantic 2.13; drain-steps order vs `app.py`; DD-5's consumer list; DD-11's lock claim; only two `IndexingManager.stop` call sites outside `drain`, both covered by DD-8.

Flight marked **ready** after these edits; no fourth cycle (the Architect's own recommendation, and the operator's override was for one pass).

---

## Reconnaissance Report

The flight sources from the Flight 3 debrief's Recommendations 2 and 7 and two recorded notes, not from a code-cited item list; the recon is correspondingly short.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Rec. 2a — watcher is a trigger only, debounce into one `request_index` per settle window | `confirmed-live` | `manager.py::request_index` is synchronous, coalescing, lock-free; no watcher exists | DD-1, DD-3 |
| Rec. 2b — subscribe with the walk's dot-prefix and `SKIPPED_DIRS` rules | `confirmed-live` | `walk.py::walk_folder` applies both inline (`name.startswith(".")`, `name in SKIPPED_DIRS`); no shared predicate | DD-2 extracts one predicate the walk and the watcher both call |
| Rec. 2c — never classify file state in the watcher | `confirmed-live` | design rule; nothing to verify in code | DD-1 |
| Rec. 2d — respect the lock order | `confirmed-live` | `manager.py` module docstring states the order; the watcher takes no lock | DD-1 |
| Rec. 7 — decide the Windows 1M re-measure vehicle | `needs-human-recheck` → decided | `mission.md` Open Questions, last bullet | Operator: fold into Flight 6 / mission close (DD-12); Leg 4 amends the open question |
| Technical note — `get_vector_store()` has no shutdown hook | `confirmed-live`, out of scope | `the_one/vectors/__init__.py` (no hook); Flight 3 DD-7 | Unchanged by this flight; stays recorded (DD-12) |
| Mission Flight 4 bullet — "modelled on `ConnectorManager`" | `confirmed-live` | `connectors/manager.py::_run` supervisor loop with reconnect; `agents.md` names the convention with the watcher as its expected third instance | DD-1 |

---

## Deviations

*(none yet)*

---

## Anomalies

*(none yet)*

---

## Session Notes

- 2026-09-16 — Planning session. Context gathering, code interrogation, interview, spec draft, premise probes, behavior-test draft. Architect cycle 1 (needs rework: the WSL polling default); native re-probes P13–P18; operator checkpoint on backend, cap and gate shape; spec rewritten (DD-0 added, four legs); Architect cycle 2 (needs rework: the permission flag swallows all registration errors; sentinel; empty yields); fixes applied; escalated to the operator at the max-2 boundary; operator chose a third pass (approve with changes); edits applied; flight `ready`.
