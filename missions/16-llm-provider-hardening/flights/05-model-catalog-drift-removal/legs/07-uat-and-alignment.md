# Leg: uat-and-alignment (optional HAT)

**Status**: in-flight
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Guided human acceptance test: the operator confirms, in the real running app, that
context-window reporting is correct per model, survives an offline restart, and
that the daily refresh loop maintains the on-disk cache. The Flight Director walks
the operator through each step, fixing any issue inline before landing the flight.

## Nature

Interactive / human-driven (per the agentic-workflow HAT protocol). No autonomous
Developer/Reviewer agents execute these steps — the operator performs them and
reports results; the FD diagnoses + fixes (spawning a Developer only if a code
change is needed) and re-verifies before moving on.

## Preconditions
- the-one runnable host-native (`make up` / the project's run path).
- At least one of: an OpenAI provider and/or an Anthropic provider configured in
  Administration with a valid key (the context-window resolve itself needs no key,
  but the Studio model-list + a real chat do).
- For the 1M check: an Anthropic provider with a current Claude model
  (`claude-sonnet-4-6`).

## Verification Steps (acceptance)

| # | Step | Expected |
|---|------|----------|
| 1 | Launch the app; confirm it starts cleanly (no traceback from the new refresh loop) and the startup logs show the catalog-refresh loop task started. | App serves; no error from `_model_catalog_refresh_loop`; (optionally) a refresh attempt logged. |
| 2 | Open a chat against an **Anthropic** `claude-sonnet-4-6` agent. Read the telemetry overlay's `max:` value. | Shows **1,000,000** (≈1M), not 200k. |
| 3 | Open a chat against an **OpenAI** `gpt-4o` agent (if configured). | `max:` shows **128,000**. |
| 4 | In Studio / the model picker for the Anthropic provider, view the per-model context-length chips. | `claude-sonnet-4*` shows ~1M; Haiku-class shows 200k; an unknown/未-cataloged model shows **no chip** (not a wrong value). |
| 5 | **Offline-restart survival**: stop the app, optionally disconnect network, restart, and reopen the **same** `claude-sonnet-4-6` chat from history. | `max:` still reads **1,000,000** — resolved from the local cache/seed with no network. |
| 6 | Inspect the on-disk cache after the loop has run (or trigger `make refresh-model-catalog` for the seed): `cat "$(the-one data dir)/model_catalog.json"` — confirm a `fetched_at` (cache) or `generated_at` (seed) stamp and provider sections. | A valid catalog JSON with a date stamp + `providers.openai` / `providers.anthropic`. |

## Out of Scope
- Re-testing unit-level behavior (covered by the committed suites).
- The header-gated 1M path (deferred — mission Open Question).

## Disposition
- All steps pass → check off, land the flight.
- A step fails → FD diagnoses, fixes inline (new commit, no amend), re-verifies that
  step, then continues. Record any fix in the flight log.
- Operator may accept a minor cosmetic gap as a known issue (recorded in the flight
  log) and still land.

---

## Post-Completion Checklist
- [ ] All HAT steps passed (or dispositions recorded)
- [ ] Any inline fixes committed + noted in flight log
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md
- [ ] (Final-leg landing handled by the Flight Director: flight → landed, mission
      flight checked off, PR opened)
