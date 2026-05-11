# Leg: 05-snapshot-rebaseline-and-alignment

**Status**: completed
**Flight**: [Brand Foundation](../flight.md)

## Objective

Bake the four autonomous legs' changes into the running container, regenerate the 12 visual-snapshot baselines so they reflect the rebranded GleepGlorp AI identity, and walk the operator through a structured Human Acceptance Test (HAT) covering brand identity, palette, page-by-page visual sanity, brand-text surfaces, and accessibility in both light and dark themes. Capture any visual issues inline (tactical fixes during HAT, structural issues logged as Known Issues for downstream flights), then complete the flight.

## Context

- Leg 5 of 5. Legs 01-04 are committed as `flight/01: GleepGlorp AI rebrand` (commit `6745363`). The flight is `in-flight`.
- This leg is operator-driven; no autonomous implementation agents are spawned. The Flight Director (orchestrator) presents one verification step at a time and waits for the operator to perform it and report results before moving on.
- The narrow test gate (palette + token-def + oauth-factory + tempdirs) already passed during the flight review. This leg adds the visual-snapshot pixel suite and full-app visual confirmation.
- Container rebuild is required before any visual verification — the Dockerfile bakes `the_one/` at build time. Visual snapshot tests run against a fresh app subprocess (not the container at port 8484), so they need `make rebuild` only to confirm the host-side served app matches; the snapshot tests use `tests/browser/seeders.py` to spawn isolated app instances.

## HAT Step Plan

The orchestrator walks the operator through these in order, one at a time:

1. **`make rebuild`** — bake all 4-leg changes into the container at `localhost:8484`. Verify with `curl /` that the served `index.html` carries the favicon `<link>` tags and the `GleepGlorp AI` title.
2. **Brand identity check (light theme)** — load `http://localhost:8484/` in a private window with light theme forced; confirm: browser tab favicon shows mascot; tab title reads `GleepGlorp AI`; topbar shows mascot icon + `GleepGlorp AI` wordmark; primary buttons render purple; focus rings render purple.
3. **Brand identity check (dark theme)** — toggle theme via Admin → System → Appearance; same checks; confirm purple palette holds across the theme switch.
4. **Page-by-page sanity (light + dark)** — walk through Chat, Studio (Agents grid + an agent editor + MCP Sources), Admin (System + LLM Providers + Built-in Tools). Look for: unstyled elements, contrast issues, layout breaks, anything that reads visually broken.
5. **CLI brand check** — `docker exec the-one the-one version` prints `GleepGlorp AI v0.2.0`.
6. **`/docs` Swagger UI** — load `http://localhost:8484/docs`, confirm title reads `GleepGlorp AI`.
7. **Visual snapshot baseline regeneration** — `UPDATE_SNAPSHOTS=1 docker exec the-one pytest -m pixel tests/browser/test_visual_snapshots.py --timeout 60`. Confirm 12 baselines regenerated.
8. **Snapshot rerun without `UPDATE_SNAPSHOTS`** — confirms the new baselines are stable; should pass clean.
9. **Tactical-fix loop** — for any visual issues the operator surfaces during steps 2-8, diagnose and fix inline. Re-verify the affected step before moving on. Structural issues that can't be fixed in this leg get logged as Known Issues for downstream flights.
10. **Flight close** — update flight.md status `in-flight` → `landed`, tick this leg's checkbox in flight.md, tick the flight checkbox in mission.md, commit the leg-05 artifacts + any tactical fixes, push the branch, open the draft PR.

## Acceptance Criteria

- [x] `make rebuild` completes; `make verify-serving` exits 0
- [x] Light-theme HAT passes operator inspection (no blocking visual issues after tactical fixes)
- [x] Dark-theme HAT passes operator inspection (no blocking visual issues after tactical fixes)
- [x] CLI `the-one version` prints `GleepGlorp AI v0.2.0` (dynamic-version piggyback from Leg 04 working)
- [x] `/docs` Swagger UI title reads `GleepGlorp AI - Swagger UI`
- [~] 10 of 12 visual snapshot baselines regenerated and pass on rerun; 2 (`chat_with_messages` × dark + light) blocked by pre-existing seeder issue logged as Known Issue
- [x] Tactical fixes applied are documented in flight log (icon source-PNG switch, MCP-tab checkbox styling, snapshot-test stale selector)
- [x] Structural issues logged as Known Issue in mission.md (`.session-agent-badge` empty in `app_with_agent` fixture auto-session flow)
- [x] flight.md status updated to `landed`; mission flight checkbox ticked
- [x] Leg 05 + tactical fixes committed and branch pushed
- [x] Draft PR opened with all 5 legs checked off

## Files Affected

- `tests/browser/__snapshots__/` — 12 PNG baselines regenerated locally (gitignored per user-global convention)
- `missions/08-gleepglorp-rebrand/flights/01-brand-foundation/flight.md` — status update
- `missions/08-gleepglorp-rebrand/flights/01-brand-foundation/flight-log.md` — leg progress + any tactical-fix notes
- `missions/08-gleepglorp-rebrand/flights/01-brand-foundation/legs/05-snapshot-rebaseline-and-alignment.md` — this artifact, status updates
- `missions/08-gleepglorp-rebrand/mission.md` — flight checkbox tick
- (Variable) any source files touched by tactical HAT fixes
