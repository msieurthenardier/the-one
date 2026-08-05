# Flight Log: Authenticated Local API End-to-End

**Flight**: [Authenticated Local API End-to-End](flight.md)
**Mission**: [Local API Authentication](../../mission.md)
**Started**: 2026-08-05

## Summary

Execution began 2026-08-05 on branch `flight/01-authenticated-local-api`.
Flight transitioned `planning` → `in-flight` on operator approval via
`/agentic-workflow`.

## Leg Progress

{Appended per leg during execution.}

## Decisions

{Runtime decisions not anticipated in the flight spec's Design Decisions.}

## Deviations

{Departures from the planned approach, with rationale.}

## Anomalies

{Unexpected behaviour observed during execution.}

## Session Notes

{Freeform notes.}

---

## Flight Director Notes

### Flight start — 2026-08-05

- Phase file loaded: `.flightops/agent-crews/leg-execution.md` — structure valid
  (`## Crew`, `## Interaction Protocol`, `## Prompts` all present with fenced
  blocks). Crew: Developer (Sonnet), Reviewer (Haiku), optional Accessibility
  Reviewer (Sonnet, not applicable to this flight — no user-facing UI changes).
- Git strategy `branch` per ARTIFACTS.md. Branch `flight/01-authenticated-local-api`
  created off `main` at `5df53b2`-equivalent tip; planning artifacts committed as
  the flight baseline so the flight-end Reviewer's "changes since last commit"
  scopes to implementation, not planning.
- Flight status advanced `planning` → `in-flight` directly. The intermediate
  `ready` state was not separately recorded because operator approval and
  execution start were the same act.
- Prerequisite "dedicated dev instance on a non-default port" deliberately left
  open at flight start. It gates `operational-callers` and the behavior test,
  not `credential-foundation` or `gate-middleware`, both of which are pure unit
  work. Recorded here so it is not mistaken for an unnoticed gap.
- Review cadence per the current methodology: design review is risk-tiered
  per leg; code review and commit are deferred until after the last autonomous
  leg. Legs 1–6 are therefore implemented uncommitted on top of the baseline.

---

## Reconnaissance Report

Source artifact: GitHub issue #165, which cites specific code locations. Each
cited item verified against current `main` before leg design.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| API fully unauthenticated; F3 Decision 10 is the canonical citation | `confirmed-live` | `SECURITY-MODEL.md:14-16,20-23` | Real work; DD3/DD4 |
| Origin allowlist gates only mutating methods + WS upgrades, so GETs pass | `confirmed-live` | `middleware.py:57` `GATED_METHODS = {"POST","PUT","PATCH","DELETE"}`; `:81` gates only those | Real work; the GET-side rebinding gap is genuine |
| API reaches `shell` / `python_exec` over plain loopback HTTP | `confirmed-live` | `app.py:357-362` — single middleware, then full router | Real work |
| M19 stores plan-provider OAuth tokens in the DB | `confirmed-live` | Mission 19 debrief; encrypted at rest but reachable via the unauthenticated API | Real work; motivates the mission |
| Persist token at `{data_dir}/api-token`, mode `0600`, "same handling as `encryption.key`" | `partially-satisfied` — premise drifted | `encryption.py:78,104` uses write-then-`chmod`; `api.py:4892-4896` uses `os.open(..., O_EXCL, 0o600)` *because* the former "has a brief world-readable window" | **Do not** follow `encryption.key`'s handling as the issue says; follow `api.py`'s. Captured as DD2 |
| Exempt a `/health`-style probe for the launcher port classification | `confirmed-live` but **rejected as specified** | `/api/info` returns `base_prompt` (`app.py:1985-1987`), not just version | Exemption is right; the endpoint named is wrong. Captured as DD5 |
| Browser handoff via `?token=` → cookie → redirect | `confirmed-live` | Pinned webview exposes no cookie-injection method and no header parameter on window creation; shell owns the URL (`shell.py:497,615`) | Real work — and the *only* available mechanism, not merely the chosen one. DD7 |
| `tests/browser/conftest.py` fixtures need the per-instance token | `confirmed-live`, larger than stated | `conftest.py:112-190` spawns uvicorn per test with isolated data dir; 59 files consume `base_url`; ~56 direct `httpx` sites bypass any shared client; no authenticated-client fixture exists in `tests/conftest.py` | Real work; drove DD10 |
| `_select_port`'s connect-probe must work against the authenticated server | `confirmed-live` | `shell.py:223-261` classifies by reading version from `/api/info` | Real work; DD11 — and the change *improves* classification |
| AIAT lane needs a token env var or file lookup | `confirmed-live` | `tests/test_aiat.py:33`; `tests/live/discord_hat/config.py:99` | Real work |
| `the-one doctor` listed as a client needing the token | `already-satisfied` — **not a client at all** | `the_one/diagnostics.py` contains no HTTP client; its only `subprocess` use (`:69`) is a child-spawn check | Retire from the client inventory |
| *(not in issue)* `make verify-serving` | `confirmed-live` — **missed by the issue** | `Makefile:112-140` curls `/api/info` and loops 18 `/static/js/areas/*.js` asserting 200 | Add to scope — breaks under DD5 *and* DD6 |
| *(not in issue)* CI packaged-smoke | `confirmed-live` — **missed by the issue** | `.github/workflows/windows-installer.yml` step (b) makes a bare `httpx.get` to `/api/info` with no credential handling | Add to scope. Step (c) calls `_select_port` through the `the_one/interfaces/app.py:7-9` shim and inherits the shell's behaviour |
| Connectors as API clients | `already-satisfied` — not clients | No HTTP client anywhere under `the_one/connectors/*.py`; they run in-process | Retire from the client inventory |
| *(not in issue, missed by mission review)* Existing behavior-test specs | `confirmed-live` — **whole caller category missed** | ≥10 `active` specs under `tests/behavior/` navigate a browser straight to the app root with no credential step — `shell-navigation-smoke.md`, `chat-roundtrip.md`, `agent-history-auto-purge.md`, `agent-purge-now-clears-history.md`, `agent-retention-setting-roundtrip.md`, `connector-inference-provider-config-roundtrip.md`, `discord-approval-flow.md`, `audit-log-inspector-renders-routing-entries.md`, `windows-desktop-presence.md`, `windows-native-frame-splash.md`; several target the default port | Add to scope via a runner-level credential mechanism, not per-spec edits. DD13 |
| *(not in issue)* Desktop window-focus forward | `confirmed-live` | `shell.py:493` `httpx.post(.../api/window/focus)`, fired when `_select_port` finds an existing instance — a third shell call site beyond the readiness poll and classifier | Itemize explicitly in the operational-callers leg |
| *(not in issue)* Stale CI comment | `drifted` | `.github/workflows/windows-installer.yml:8` claims unit-test CI "still runs on every PR / main push"; `test.yml:9` is `workflow_dispatch` only — routine CI moved to local Concourse | Pre-existing drift, not caused by this flight; correct opportunistically in the docs leg |
| *(not in issue)* Docs describing the unauthenticated probe | `confirmed-live` | `docs/windows-install.md:89`, `packaging/windows/README.md:202-204` describe the same unauthenticated `/api/info` check | Correct in the docs leg so documentation does not describe retired behaviour |
