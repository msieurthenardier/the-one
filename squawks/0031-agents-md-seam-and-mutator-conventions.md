# Squawk 0031: agents.md convention entries for the dual-gate seam and disjoint post-step mutator patterns

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: 2026-09-01

## Report

Two patterns from Mission 23 Flight 2 deserve `the_one/agents.md` convention entries so they're
pattern-matched instead of re-derived (the seam risk-tiering was re-argued from scratch for the
second flight running):

1. **Dual-gate test seams with risk tiering** — inert-metadata seams may gate on `dev_mode` alone
   (oauth/pending precedent); seams that mutate real state or inject into a live agent loop gate on
   `dev_mode` AND a seam-specific env var (purge-sweep, `THE_ONE_STUB_TEST_ENDPOINT` precedents).
2. **Composition-disjoint post-step mutators** — `_bind_peer_name` (touches only `Role.USER`) and
   `tag_post_step_visibility` (skips `Role.USER`) are non-conflicting by construction; the pattern
   for composing independent post-step concerns without one function growing multiple jobs.

## Evidence

- Flight 2 debrief, What Could Be Improved / Documentation
- `the_one/connectors/inbound.py::_bind_peer_name`, `the_one/llm/base.py::tag_post_step_visibility`
- Seam gates: `api.py` `/_test/stub/*`, `/_test/purge-sweep`; `tests/test_seam_routes_403_sweep.py`

## Corrective Action

Added two `### Project-wide` convention entries to `the_one/agents.md`, in the "Project
Conventions" section, immediately before "### Mission-specific (M16)":

1. **`risk-tiered-test-seam-gating`** — states the tiering rule (inert-metadata seams gate on
   `settings.dev_mode` alone; live-state-mutating or agent-loop-injecting seams gate on
   `settings.dev_mode` AND a seam-specific env var) and cites the three precedents: single-gate
   `POST /_test/oauth/pending`; dual-gate `POST /_test/purge-sweep`
   (`THE_ONE_PURGE_SWEEP_TEST_ENDPOINT`); dual-gate `POST /_test/stub/inbound` /
   `GET /_test/stub/outbound` (`THE_ONE_STUB_TEST_ENDPOINT`, Mission 23 Flight 2 DD-10), all in
   `the_one/interfaces/web/api.py`.
2. **`composition-disjoint-post-step-mutators`** — states the pattern (two post-step mutators
   over the same `messages[pre_step_len:]` slice touch disjoint `Role` subsets so they compose in
   either order) and cites `the_one/connectors/inbound.py::_bind_peer_name` (touches only
   `Role.USER`) and `the_one/llm/base.py::tag_post_step_visibility` (skips `Role.USER`), called
   back-to-back in `dispatch_inbound`.

Both entries follow the existing convention-entry shape (kebab-case `###` slug, prose statement
of the rule, an applicability boundary, and citations to real code/tests). Docs only — no
`the_one/` source files outside `agents.md` were touched.

## Verification

- Confirmed every cited file/symbol exists and matches the claims: `grep` for
  `_creatable_connector_types`, `POST /_test/oauth/pending` (`seed_pending_oauth_flow`),
  `POST /_test/purge-sweep` (`trigger_purge_sweep`, `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT`),
  `/_test/stub/inbound` / `/_test/stub/outbound` (`THE_ONE_STUB_TEST_ENDPOINT`) all resolve in
  `the_one/interfaces/web/api.py`; `_bind_peer_name` in `the_one/connectors/inbound.py` and
  `tag_post_step_visibility` in `the_one/llm/base.py` resolve, and `dispatch_inbound` calls them
  in the stated order (`_bind_peer_name(...)` then `tag_post_step_visibility(...)`).
- `git diff --stat` shows only `the_one/agents.md` and this squawk artifact changed — scope gate
  held.
- No forbidden terms (operator username, absolute home path) introduced.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)
