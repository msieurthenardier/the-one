# Flight Debrief: Ollama Pull shows the download size first

**Date**: 2026-10-07
**Flight**: [Ollama Pull shows the download size first](flight.md) (sortie 01)
**Status**: completed (landed, then marked completed at this debrief)
**Duration**: 2026-10-07 (charter, design, both legs, merge as `2cb1456` via PR #235, release v0.10.3)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
- **The Pull Model control is rebuilt around exact download sizes:**
  - `the_one/llm/ollama_library.py` lists every pullable `name:tag` (448 at the HAT) with its registry-manifest size, cached on disk;
  - two thin routes;
  - one flat list such as `llama3.2:3b (2.0 GB)` with cloud and missing entries greyed out;
  - a size re-check and a confirmation naming the size on every pull.
- **Shipped as v0.10.3**, with the Windows installer built and attached.
- **Defects fixed along the way:** v0.10.2's undownloadable "1.5 TB" cloud entries, double-escaped progress text, Pull re-enabled after Cancel, and Refresh during a pull orphaning it.

### Charter Criteria (the sortie's success criteria)

| Criterion | Result | Evidence |
|---|---|---|
| The exact download size, from the registry manifest, is shown before Pull is enabled | **Met** | HAT steps 2 and 3: every entry carries a size or a reason, and Pull reads "Pull · {size}". The `qwen3:0.6b` install was 522,653,767 B, matching the confirmed "523 MB". |
| Every pull needs an explicit confirmation naming its size | **Met** | HAT steps 3 and 4: the modal names the size; Cancel sent no pull request (server log). |
| If the size can't be determined you're told, and nothing downloads unless you agree | **Met** | Browser tests cover the "Pull anyway" path and the 4xx re-check. The HAT had no registry outage, so this path was not seen live. |
| You can choose a variant, not only `:latest` | **Met** | HAT step 2: `llama3.2:1b` sits before `llama3.2:3b`, and so on. Reaching a variant is by first-letter jump plus arrow keys or scrolling, which the operator accepted at step 3b. |

All four checkpoints were met. The flight spec's checkboxes are ticked.

## What Went Well
- **A cheap Divert check before building.** A throwaway scratch script fetched all 445 manifests live: 8.0 s, no 403/429. It confirmed DD4 and showed the cold fill (about 10 s) would overrun the 8 s wait, so the `loading` path was known to be real before any code.
- **Design reviews caught real defects on paper.** The two Architect cycles found two:
  - a `typing.TypedDict` route annotation would crash `api.py` at import on Python 3.11 (CI and the Windows build), though it passes on the 3.12 dev venv;
  - the lifespan cancel ran after uvicorn's request drain, so it could not unblock `make down`.

  The per-leg Developer review found eight smaller ones, including the wrong seeder and the missing CSS step.
- **The HAT was the most valuable leg.** Run on a scratch instance against the operator's real Ollama in seven state-transition steps:
  - it proved the disk cache across a restart (one search request, no loading loop);
  - a real 523 MB pull matched its confirmed size;
  - it found the one real design miss (DD1, below).
- **The stateless, dev-mode-gated test seam**, set by default in the browser conftest, kept every browser test off the network. It was proven by running the lanes inside the `THE_ONE_TEST_NETNS=1` namespace, which has no internet.
- **Debrief test run (WSL2, netns, locked venv) was clean:**
  - unit: 5600 passed, 10 skipped, 0 failed, 724 s;
  - chats: 168, 4:36;
  - agents: 153 passed / 2 skipped, 6:12;
  - library: 153 passed / 1 skipped, 9:19;
  - settings: 214, 7:36;
  - no flakes, and neither squawk 0134 nor 0136 recurred.

## What Could Be Improved

### Process
- **(Critical) A cross-version check destroyed the dev venv.** Leg 1 mandated `uv run --python 3.11 --with-editable .` inside the project, and uv rebuilt the repo `.venv` as 3.11.
  - The Developer then tested in an *unlocked* scratch venv and reported "11 pre-existing failures". They were dependency drift (`openai` 3.26 against the lock's 2.32).
  - Recovery took an operator decision, a rebuild, `uv sync --frozen`, and two full unit runs to disprove the false failures.
  - Rule for future legs: a cross-version check uses `uv run --no-project` or a scratch `UV_PROJECT_ENVIRONMENT`, and any rebuilt venv is synced `--frozen` before its results are trusted.
- **(Important) DD1 rested on an untested platform claim.** "Type-to-jump still works" over about 448 native-`<select>` entries is true only for the first letter on Windows (WebView2), the app's main runtime.
  - Neither Architect cycle questioned it; the operator found it at HAT step 3.
  - A two-minute check in the real shell would have settled it. A design decision that depends on native-widget behaviour should name that dependency and verify it on the target platform at design time.
- **(Important) The fallback, DD12 (a filter box), was built in full before anyone tried it.** It went through a design, a Developer review (3 medium issues), an implementation (6 tests, CSS, registry rows) and a code review. The operator rejected it on first touch ("this is not right, revert, lets go with the previous version of the first letter"), and it never shipped.
  - A hot-edited prototype on the running 8486 instance would have tested the idea for a fraction of the cost.
  - The design also missed the existing `App.ui.searchList` (`docs/ui-control-inventory.md`), the library's own "find one in many" control.
  - Lesson: a mid-HAT feature gets a throwaway prototype in the operator's hands before the design-review, implement and review cycle.
- **(Important) Review of cache-file robustness ran three cycles.** Cycle 1's nits became cycle 2's blocking finding (a 400-digit timestamp and a `RecursionError` path through `size()`), and cycle 3 accepted a list of remaining hand-edit cases.
  - Validating names that flow into a URL was right.
  - The timestamp edge cases guard only against hand-editing the app's own file.
  - DD4 said "a corrupt file never causes a 500" but not which loaded values may be trusted. A one-line rule would have bounded it: "validate at load only what flows into a URL or into arithmetic; the rest is trusted local state".
- **(Minor) A HAT step prescribed a path the interaction couldn't reach.** Step 3 named `deepseek-r1:671b`, which type-to-find couldn't reach; the operator used `deepseek-coder-v2:236b`. The Flight Director caught the mismatch from the server log. HAT steps should name a goal ("a model over 100 GB"), not a path through an unverified interaction.

### Technical
- **(Important) A fill in progress hides the cached list.** `_needs_fill` starts a fill whenever the *listing* is older than 300 s (`_LISTING_TTL`), even when every size is fresh, which they are for 7 days.
  - The panel then renders the loading copy and ignores the `models` snapshot the same response carries.
  - With ollama.com slow or blackholed (two 10 s timeouts), a user with a full disk cache waits about 20 s on "Loading…". That contradicts DD4's intent that an outage "still shows the full list".
  - No test pairs `loading: true` with a non-empty `models`. Squawk candidate.
- **(Important) The parser depends on Tailwind class names** (`items-baseline`, `text-blue-600`, `text-cyan-500`). A restyle of ollama.com makes the parse return `[]`, and the code falls back silently to the stale listing with only a "page fetch failed" style warning. Add a distinct "parsed zero entries" warning. Squawk candidate.
- **(Minor) Coverage gaps:**
  - no test asserts that `app.py`'s lifespan actually calls `shutdown_drain()`;
  - no browser assertion covers DD8's decimal sizes on the installed-model and VRAM lines (the VRAM line was rebuilt from `innerHTML` to DOM APIs without one);
  - the "panel refreshed; choose the model again" guard is untested in the browser.
- **(Minor) Other debt:**
  - **Disabled state:** `pullNameInput.disabled` has five writers; `renderPullButton` owns only the button. DD12's review proposed one owner, and that idea is worth keeping without the filter box.
  - **Sync write:** `size()` writes the whole map synchronously after every Pull click (about 50 KB).
  - **Rounding:** `formatSize` can print "1000 MB" just under 1e9.
  - **Two formatters:** `App.formatBytes` and `formatSize` disagree (squawk 0137).
- **Architecture: a net improvement.** `api.py` lost a module-global cache and inline fetchers, dead parser code was deleted, two `innerHTML` sinks left the baseline, and the new lifespan drain follows the existing convention. The roughly 8 module-level globals copy `model_catalog`'s pattern; a third instance would justify a small catalog class.

### Test suite runtime (operator-raised during this debrief)
- **The finding, from the debriefs.** The operator asked why the suite is so slow and suspected Mission 25. The debriefs bear that out:
  - the browser suite held at about 4.5–5 min through Missions 8–10 and rose slowly to 15.7 min at the end of Mission 24;
  - Mission 25 took it to 39.2 min (Flight 4), flight by flight: 16.9 → 25.7 → 33.0 → 39.2.
  - Chart: https://claude.ai/artifact/QcknEj5Pa2zmDgiuy3Qp7v (private).
- **The cause.** Every browser test using `app_clean` (and the seeded variants) starts its own uvicorn server.
  - The decision dates from Mission 4 Flight 1 (2026-04-26), when the suite had 3 flows: "Strongest isolation."
  - It was centralised in Mission 20 (`_spawn_app`) but never re-scoped.
  - `pytest --setup-plan`: before Mission 25 (`3121c2d^`), 533 items with about 407 server starts; now 1,828 items with **936 server starts**.
  - Five measured starts averaged **about 1.6 s** each (start to ready, then stop), so about 25 of the roughly 38–41 minutes is server churn.
  - Mission 25's 694 two-engine contract items load a blank page and start no server.
- **The unit suite.** It grew steadily rather than in one jump: 1.3 min at Mission 7 (1,344 tests) to 12 min today (5,600). Its cost per test **doubled** (about 0.06 s → about 0.13 s), which more tests alone don't explain.
- **Why it went unnoticed.** No Mission 25 debrief flagged the tripling. Each recorded the lane times and compared them only with the flight before. Recorded below as a methodology observation.

### Documentation
- **Missing patterns in `the_one/agents.md`:**
  - the detached single-flight fill (a module task, a shielded bounded wait, a `loading` answer, a lifespan drain, per-fill loop-bound primitives, `_reset_for_tests`);
  - the cross-version-check rule;
  - the accepted first-letter limitation of the Pull list, so a future "can't find deepseek-r1:671b" report is recognised as known.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| A 300 s cooldown after an early stop, during which `search` starts no new fill | DD4 left "re-fill after an early stop" unspecified; without it every panel render re-hammered a failing registry (reviewed sound) | Yes: any early-stop rule needs a stated re-try policy |
| The size route returns the shared map's entry after recording (DD6's cached `ok` with no new field) | A simpler way to meet DD6, settled at leg design | No (local) |
| The repo `.venv` rebuilt as 3.11, then unlocked, then synced `--frozen` | The leg's `uv run --python 3.11` inside the project | **Yes, as a prohibition:** cross-version checks never touch the project env |
| DD12 filter box designed, built, reviewed, reverted | The operator rejected it on first touch | Yes: prototype mid-HAT features before building |
| Debrief test run skipped the contracts and shared lanes | The operator: the suite is too slow; shared ran in leg 1 (465 passed) | No: a one-off, recorded here |

## Key Learnings
- **Measured before designed.** The live Divert probe and the manifest measurements made DD2, DD3 and DD4 hold up exactly; the estimate was 445 entries and the HAT saw 448. Probing an external dependency for a few minutes before design is cheap and worth repeating.
- **Platform claims belong in the citation audit.** The audit verified every code citation and none of the browser-behaviour claims, and the browser claim was the one that failed.
- **Hands-on use catches what review misses.** DD12 passed two reviews and failed in the operator's hands in seconds.
- **A per-test cost that was fine at 3 tests compounds silently.** The browser fixture's isolation choice was never revisited as the suite grew 600-fold. Debriefs that compare only with the previous flight can't see that kind of drift.

## Methodology Observations
Plugin version: mission-control 1.2.0, for every entry below.

1. **agentic-workflow, Phase 2a (leg design): the "Python 3.11 import check" was specified as a project-env command.**
   - **What happened:** the Flight Director wrote the AC7 verification as `uv run --python 3.11 --with-editable .`. Nothing in the leg template or the crew prompt warns that `uv run` in a project directory rebuilds that project's `.venv`.
   - **Expected:** a leg design guideline that cross-interpreter checks use an isolated environment.
   - **Cost:**
     - the operator's dev venv was destroyed;
     - the operator was escalated to, because the subagent's `rm -rf` was denied and the Flight Director correctly refused to retry it;
     - one rebuild, then a second fix (`uv sync --frozen`) after the first rebuild was unlocked;
     - two extra full unit runs (about 12 min each);
     - a false "11 pre-existing failures" report the Flight Director had to disprove.
2. **sortie, flight design (Architect review): design-review cycles audit code citations but not platform or UX claims.**
   - **What happened:** DD1's "type-to-jump still works" passed two Architect cycles unexamined, then failed at HAT on Windows.
   - **Expected:** the Citation Audit, or the Architect prompt, covers runtime-behaviour claims the design depends on, such as native widget behaviour, browser engine or OS, alongside code citations.
   - **Cost:** the DD12 detour below.
3. **agentic-workflow, Phase 2b (HAT fix-versus-feature gate): the gate routed a mid-HAT feature straight into the full design-review, implement and review cycle.**
   - **What happened:** the operator rejected the result on first touch.
   - **Expected:** for a mid-HAT UI feature, a step before the design review: put a throwaway prototype (hot-edited JS/CSS on the running HAT instance) in the operator's hands, and only then design, review and build it.
   - **Cost:** one Developer design review, one Developer implementation (about 12 min plus a settings-lane run), one Reviewer, one revert, and the operator's time on a step 3b that ended in "revert".
4. **agentic-workflow, Phase 2d (flight review): the review and fix loop has no guidance on proportionality for trusted local state.**
   - **What happened:** three cycles were spent on hand-edited-cache-file shapes. The Reviewer was told "any path that still raises is blocking", and correctly enumerated more paths each cycle.
   - **Expected:** a review-brief rule for app-written state, saying what must be validated and what is trusted.
   - **Cost:** two extra Developer and Reviewer cycles, about 15 minutes of wall time.
5. **flight-debrief, Phase 3 (test metrics): debriefs compare only with "earlier numbers they find", in practice the previous flight.**
   - **What happened:** Mission 25's browser suite went from 15.7 min (Mission 24 close) to 39.2 min, a factor of 2.5, over one mission. Each Mission 25 flight debrief recorded its lane times and judged the change from the flight before (+19% to +29% per flight) without escalating it.
   - **Expected:** the metrics phase compares against the previous *mission's* close as well, and flags a growth threshold, for example more than 50% per mission.
   - **Cost:** the operator found the suite "way too slow" before the methodology flagged it. One debrief session went into reconstructing the history from 154 debrief files.
6. **flight-debrief, Phase 2 (Developer interview): "run the full test suite once" costs about 50 minutes here.**
   - **What happened:** the instruction ran unit plus six sequential browser lanes. The operator stopped it partway ("this is way too slow"), and contracts and shared were skipped.
   - **Expected:** a scoped default (unit plus the lanes the flight touched) with a full run as an option, or reuse of the flight's own gate runs.
   - **Cost:** about 40 minutes of the operator waiting before the cut.
7. **sortie (vehicle check):** a sortie was the right vehicle. It had one outcome, one cluster of decisions (list shape, size source, confirm policy, cache) and two legs. The DD12 detour was a HAT finding, not a second decision cluster, and it was reverted rather than grown. The charter's four criteria were clear and binary, and all were observed at the HAT.

## Recommendations
1. **Plan a sortie to cut browser-suite server churn** (936 per-test uvicorn starts, about 25 of about 40 min). Start by measuring, then decide the isolation trade-off: one app per file with a data reset, a session pool with fresh databases, or parallel workers. Include why the unit suite's per-test cost doubled.
2. **Show the cached list while a fill runs.**
   - Render `models` whenever the response carries them, even with `loading: true`, and refresh the listing in the background, stale-while-revalidate, with a TTL in hours.
   - Add the missing test.
   - Squawk 0139.
3. **Add a leg-design rule:** cross-version checks use `uv run --no-project` or a scratch `UV_PROJECT_ENVIRONMENT`, and any rebuilt venv is synced `--frozen` before its results count. Put it in the leg-execution crew prompt and in CLAUDE.md's Testing section.
4. **Prototype mid-HAT UI features in the operator's hands before the design and build cycle.** If the Pull list is revisited, start from `App.ui.searchList`.
5. **Compare test metrics against the previous mission's close in every debrief**, not just the last flight, with a growth flag.

## Action Items
- [x] Logged as squawks (operator-confirmed in Phase 6):
  - 0139: the cached list is hidden while a fill runs;
  - 0140: a "parsed zero entries" warning;
  - 0141: pins for the shutdown-drain wiring and the decimal sizes;
  - 0142: the `agents.md` and CLAUDE.md patterns note.
- [ ] Plan the browser-suite runtime sortie (recommendation 1).
- [ ] Open squawks from this sortie: 0135 (Python 3.12), 0136 (KB-watcher timing flake), 0137 (`App.formatBytes` units), 0138 (Playwright and Chromium 11 versions behind). 0135 and 0138 can share a turnaround.
- [ ] A later sortie: cloud-model support. Keep `status` as the registry fact and add a separate capability field, rather than overloading `cloud`.
