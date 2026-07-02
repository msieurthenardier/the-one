# Flight Debrief: Human Acceptance Testing — Provider Chat Sweep

**Date**: 2026-07-02
**Flight**: [HAT — Provider Chat Sweep](flight.md)
**Status**: landed
**Duration**: 2026-06-26 – 2026-07-02
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved
The operator drove live chat on the installed app and 7 findings (F09-01…07) were logged,
triaged, fixed, and shipped across five patch releases (0.2.10, 0.2.12, 0.2.13, 0.2.14; a
0.2.11 batch was planned then folded forward). Every finding is resolved or dispositioned;
legs 01–05 all `completed`. The flight lands on operator judgment (DD1) with the chat
experience materially improved: reachable MCP tools, a coherent send-while-thinking queue,
a tunable Ollama context window, a relocated routing-audit inspector, and — critically —
static-asset cache-busting so future UI updates actually appear after an upgrade.

### Mission Criteria Advanced
No *named* provider-layer success criterion (like F07, this is a QA/hardening flight). It
provided **empirical confidence for the Ollama-native chat path** and produced one genuine
agent-tooling fix (F09-01, tool-search truncation) and one provider-config mitigation
(F09-05, num_ctx). It also surfaced field evidence for the mission's **deferred compaction
Known Issue** (F09-05) and a per-model-config design note now recorded there.

## What Went Well
- **The accretive HAT model (DD1) is validated.** Started with an empty leg list; each leg
  was a real repro→fix→verify unit, none speculative. This is the clean proof case for the
  pattern — it belongs in the methodology.
- **DD2 (test on the installed app) earned its keep.** F09-07 (stale WebView cache after an
  in-place upgrade) exists *only* on the installed path — a dev-only sweep would never have
  found it. That single finding retroactively justifies the DD2 rebuild cost.
- **DD4 triage was correct on every finding.** F09-05's real fix (compaction) went to the
  mission Known Issue with the num_ctx field as an explicit stop-gap; the F09-02/03/04
  cluster became one redesign leg. Every finding carries a one-line disposition.
- **The diagnose→leg→fix→dev-verify→release loop ran cleanly** and is worth codifying as the
  standard HAT execution loop (see Recommendations). Dev-instance verification bridged DD2's
  rebuild cost; the GitHub-Actions tag-release path (adopted mid-flight, 0.2.13/0.2.14)
  delivered official installers as GitHub Releases.
- **Client-hold queue redesign is architecturally cleaner than what it replaced.** Holding
  the message client-side until turn `done` makes cancel trivially correct and structurally
  eliminates the F09-03 race rather than patching it.
- **The "config migration → run browser suite" discipline held.** F06/F08 broke the browser
  suite 3×; the config-touching leg 03 (num_ctx admin field) shipped with a green
  `test_flow_provider_editor.py`. Pattern is working.
- **Test health is stable:** 3609 passing (+35 since F08), skips rock-stable at 10, full
  default suite 329s (inside the historical 296–346s band) despite the additions.

## What Could Be Improved

### Process
- **The accretive model has no forcing-function for *breadth*.** The flight was scoped
  across three providers (DD3) but substantively exercised **one** (Ollama-native); the
  Anthropic and OpenRouter checkpoints landed unchecked (`flight.md` Checkpoints). It drilled
  deep on the first fruitful provider and landed before sweeping the others. *(Operator, this
  debrief: Ollama was the intended priority — accepted, not a defect. Recorded so future
  multi-provider HAT sweeps add per-provider gates or re-scope the title when they become a
  single-provider deep-dive.)*
- **Cache-busting should have been a preflight prerequisite, not a mid-sweep finding.** F09-07
  caused a whole release (0.2.13) to ship an *invisible* UI change, which then induced the
  next finding. Any HAT sweep that ships UI mid-flight should confirm the in-place-upgrade
  path surfaces new assets *before* trusting "operator didn't see it" as signal.
- **Release cadence was right for HAT** (per-fix live re-verify keeps the signal honest —
  operator confirmed "right rhythm"), but note one thrash artifact: 0.2.13 shipped an
  invisible change because the cache bug hid it.

### Technical
- **`_session_inflight` set is now over-general.** The `dict[str, set[Task]]` correctly fixed
  F09-03, but the F09-04 client-hold redesign means a session can again only hold one live
  task (nothing is queued backend-side mid-turn). Retained deliberately as a backstop — but a
  future reader will assume concurrent backend turns are supported. **Add a comment pinning
  the invariant.**
- **Cache-busting is a runtime HTML rewrite** (`index()` regex-appends `?v=` to 61 refs,
  memoized via `lru_cache`). Works and is dev/PyInstaller-agnostic, but the architecturally
  cleaner long-term home is build-time asset fingerprinting (hashed filenames) — note it for
  whenever a frontend build pipeline is introduced.
- **num_ctx is per-provider, but the correct shape is per-model** (one provider serves many
  models; the window/speed trade-off is per-model). Honestly labeled a stop-gap and routed to
  the compaction mission Known Issue — exemplary governance — but do not build more
  per-provider window logic on top of it.
- **⚠️ aiosqlite `Event loop is closed` teardown has escalated from noise to a red run.**
  F08 recorded 18 warnings ("carrying cost now exceeds the fix," open since F05); this run
  showed **19 warnings AND an intermittent full-suite failure**
  (`test_lifespan.py::test_lifespan_drains_session_registry`, which passes 3/3 in isolation —
  cross-test event-loop teardown pollution, not an F09 regression). **This debt has crossed
  from warning into an actual flaky failure and should be fixed at mission-debrief, not
  deferred a fifth time.**

### Documentation
- The **cache-busting invariant** (`_cache_busted_index_html`, `no-store` on `/`) is a new
  app-wide rule — document it (web-interface README/CLAUDE.md) so a future dev doesn't add an
  un-versioned static ref or re-enable HTML caching and silently reintroduce the stale-UI bug.
- The **search_tools prefixed-name quirk** (a server-name query returns the whole catalog;
  operator accepted "leave it as is") lives only in the flight log — add a code comment so it
  isn't "fixed" by someone reading the code cold.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 02 reworked mid-leg: F09-02/03 done-handler+immediate-send (`37f012f`) → client-hold (`5599047`) | F09-04 (pin+cancel) reframed the queue; client-hold is simpler and subsumes F09-02. All unreleased, so zero user impact | Yes — a later HAT finding reframing an earlier *unreleased* fix into a cleaner design is the accretive model working; rework-before-release is correct |
| Adopted GitHub-Actions `v*`-tag release path mid-flight (0.2.13/0.2.14) | Operator's GH Actions credits restored; official installers publish as GitHub Releases | Yes — document as the HAT/official release path alongside local Concourse |
| Dev-instance (port 8485) verification instead of reinstall-per-leg | DD2's installed-app target has a rebuild cost; verify the branch on a dev run, confirm on next installed build | Yes — "dev-instance verify is the gate; installed re-verify closes the leg" |
| F09-05 kept OUT of a deep fix (stop-gap field + Known Issue) | Root cause is hardware (partial VRAM offload) + already-deferred compaction, not a flight-sized bug | Yes — model for "real finding, wrong flight to fix it in" |

## Key Learnings
- **HAT is a *surface* sweep, not a *layer* sweep.** ~2 of 7 findings touched the provider
  layer the flight was named for; the rest were chat-UI/web-infra. That's expected — the chat
  UI and delivery pipeline are *on the path* to exercising providers, so defects there block
  the testing itself (F09-07 literally hid a fix). "Provider chat" names the driving activity,
  not a scope contract on where fixes land. *(Operator concurred: expected for HAT.)*
- **The accretive model trades breadth for depth.** It self-selects the first provider that
  yields findings and can land on operator judgment before the planned surface is swept. Great
  for depth; needs an explicit gate for breadth.
- **Latent whole-app debt surfaces through whichever flight happens to trip it.** Cache-busting
  affected *every* prior frontend change silently; F09-06 just made it visible. Preflight
  checks for cross-cutting infra (asset freshness, teardown hygiene) pay off.
- **Recording debt where the future owner will find it works.** Per-model num_ctx is now a
  design note *on the compaction mission*, not orphaned in a flight log.

## Recommendations
1. **Fix the aiosqlite `Event loop is closed` teardown at `/mission-debrief`.** It has crossed
   from a 4-debrief-old warning into a real intermittent suite failure. Likely an
   `asyncio_mode`/fixture-scope fix in `pyproject.toml`/conftest. Highest-value cleanup.
2. **Graduate context compaction from Known Issue to a planned mission.** F09-05 is the first
   *live field* confirmation (not F8's synthetic warn-signal) that a long conversation becomes
   unusable near the window limit. It inherits: per-model num_ctx config, the F8 per-result
   governor as prerequisite, and the tool_use↔tool_result pairing constraint on eviction.
3. **Codify the HAT execution loop + preflight.** Standardize diagnose→leg→fix→dev-verify→
   tagged-release→installed-re-verify; and for any HAT that ships UI, add **asset-freshness /
   cache-busting** and **per-in-scope-provider coverage gates** as preflight prerequisites.
4. **Author cross-upgrade behavior tests** for the classes unit tests can't see by
   construction: stale-cache-after-upgrade (F09-07), num_ctx→decode-speed (F09-05), and the
   telemetry-overlay denominator tracking the effective window (leg 03). See
   `.claude/skills/behavior-test/AUTHORING.md`.
5. **Two small doc/comment fixes:** the cache-busting invariant (README/CLAUDE.md) and the
   search_tools prefixed-name quirk (code comment); add the `_session_inflight`-is-single-task
   invariant comment.

## Action Items
- [ ] **Fix aiosqlite `Event loop is closed` teardown** (now a flaky suite failure, not just
      warnings) — carry to `/mission-debrief`; `asyncio_mode`/fixture-scope fix.
- [ ] **Graduate context compaction to a planned mission** (F09-05 is the trigger; inherits
      per-model num_ctx + F8 governor prerequisite + pairing constraint).
- [ ] Add a code comment pinning the `_session_inflight`-holds-one-live-task invariant
      (over-general set retained as backstop).
- [ ] Document the cache-busting invariant (`?v=` + `no-store`) in the web-interface
      README/CLAUDE.md; add a code comment on the search_tools prefixed-name catalog behavior.
- [ ] Note per-model num_ctx as a required surface for the compaction mission (do not extend
      per-provider window logic).
- [ ] *(Optional, operator-deferred)* A focused Anthropic + OpenRouter chat HAT before mission
      close — Ollama-native is well-covered; the cloud paths are thin. Operator deemed the
      Ollama focus acceptable this sweep.
- [ ] *(Carried)* Decide whether to re-enable GitHub-Actions `lint.yml`/`test.yml` auto-run
      now that Actions credits are restored (currently `workflow_dispatch`-only).
