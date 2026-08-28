# Squawk 0016: README quickstart points at removed `THE_ONE_LLM_*` env vars, names UI areas that no longer match the nav, and six tunables are undocumented

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

Three README/`.env.example` accuracy gaps, one doc pass (2026-08-27 maintenance
findings B4, E7, B6):

1. The quickstart says `cp .env.example .env  # edit THE_ONE_LLM_* for your provider
   of choice`, but those variables were removed in Mission 12 when provider config
   moved to the database; `.env.example` itself opens by saying providers are
   configured in the admin UI. A new operator following the README edits variables
   that do nothing.
2. The README refers to the areas as **Administration** and **Studio**; the live nav
   labels are **System** and **Agent Studio**.
3. Six `THE_ONE_*` tunables read by the code are absent from `.env.example`:
   `THE_ONE_ANTHROPIC_EXTENDED_THINKING`, `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`,
   `THE_ONE_OPENROUTER_TEST_MODELS_JSON`, `THE_ONE_REASONING_EFFORT`,
   `THE_ONE_RESPONSE_FORMAT`, `THE_ONE_STOP`.

Fix: rewrite the quickstart line to point at the admin UI provider setup; reconcile
the area names (either direction — pick one and apply consistently, including the
screenshot captions); add an "advanced LLM tuning" block to `.env.example` mirroring
its existing operational-tunables section.

## Evidence

- `README.md:49` — `cp .env.example .env  # edit THE_ONE_LLM_* for your provider of choice`;
  `.env.example:1-2` — "LLM provider selection and model are configured via the admin UI, not env vars"
- `README.md:13,24,26,30,32,107` — "Studio" / "Administration";
  `the_one/interfaces/web/static/js/areas/admin.js:3` — `label: 'System'`;
  `the_one/interfaces/web/static/js/areas/studio.js:3` — `label: 'Agent Studio'`
- `the_one/llm/anthropic_provider.py:94`, `the_one/agent/core.py:24`,
  `the_one/llm/openrouter_api.py:94`, `the_one/llm/_request_params.py:34-36` — the
  six env reads; none appear in `.env.example`

## Corrective Action

Documentation-only pass, three parts:

1. **README quickstart** (`README.md:49`): replaced
   `cp .env.example .env  # edit THE_ONE_LLM_* for your provider of choice` with
   `cp .env.example .env  # optional — only needed to change operational tunables;
   see "Supported LLMs" below to configure a provider`, pointing at the existing
   "configure each provider in **System → LLM Providers**" paragraph instead of
   env vars that no longer exist. Left the Jinja2 web-stack mention (`README.md:13`)
   untouched — its removal is maintenance finding D2 / a separate squawk.
2. **Area names reconciled to match the live nav** (`admin.js:3` → `System`,
   `studio.js:3` → `Agent Studio`; no JS changed). Updated every README prose
   mention, both screenshot alt/caption pairs, and the `Admin`/`Administration`
   → `System` and `Studio` → `Agent Studio` references at `README.md:13,24,26,30,
   32,35,107,123` (line 35's "Admin → General → Appearance" caption was an
   additional instance found beyond the cited evidence lines). Checked `docs/`:
   the only "Studio"/"Administration" hits are in dated internal design specs
   under `docs/superpowers/` (historical design history, not current operator
   docs) — left alone. The three operator-facing docs (`windows-install.md`,
   `kb-architecture.md`, `ui-testid-registry.md`) had no matches.
3. **`.env.example` "Advanced LLM tuning" block** added before the existing
   "Dev / test seams" section, documenting the six previously-undocumented vars,
   derived from their read sites: `THE_ONE_ANTHROPIC_EXTENDED_THINKING` (bool,
   default false; `anthropic_provider.py:94,117-123`), `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`
   (seconds, default 120, floor 1; `agent/core.py:24-45`),
   `THE_ONE_OPENROUTER_TEST_MODELS_JSON` (dev-mode-gated JSON array test seam;
   `openrouter_api.py:94-104`), `THE_ONE_REASONING_EFFORT` (free-form string,
   provider-specific accepted values, default unset; `_request_params.py:34,141-152`),
   `THE_ONE_RESPONSE_FORMAT` ("json"/"json_object" or a JSON object, default
   unset; `_request_params.py:35,60-105`), `THE_ONE_STOP` (bare string or JSON
   array of strings, default unset; `_request_params.py:36,111-134`). All three
   named "canonical resolvers" precedence per-provider config → env → default,
   noted in each block's intro line.

## Verification

- `grep -n THE_ONE_LLM_ README.md` → empty (exit 1). PASS.
- Each of the six vars present in `.env.example` (`THE_ONE_ANTHROPIC_EXTENDED_THINKING`,
  `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`, `THE_ONE_OPENROUTER_TEST_MODELS_JSON`,
  `THE_ONE_REASONING_EFFORT`, `THE_ONE_RESPONSE_FORMAT`, `THE_ONE_STOP`). PASS.
- `grep -nE '\bAdministration\b|\bStudio\b' README.md` → 5 remaining lines, every
  one an "Agent Studio" occurrence (no bare "Administration", no bare "Studio"
  outside "Agent Studio"). PASS.
- No test under `tests/` reads `.env.example` (grep for `env.example` / `env\.example`
  returned nothing) — no test to run.
- `make lint` → "All checks passed!" (no-op). `make format-check` → "443 files
  already formatted" (no-op). Both PASS, as expected for a docs-only change.
- `git status --short` confirms only `.env.example`, `README.md`, and this
  squawk file were touched — the pre-existing uncommitted work from squawks
  0010-0015 (`the_one/`, `ci/`, `SECURITY-MODEL.md`, tests) is untouched.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `5cf3cac` on `squawk/turnaround-2026-08-27` — PR #178
