# Leg: browser-ci-path-filter-and-dedup

**Status**: completed
**Flight**: [Native Application Window](../flight.md)

## Objective

Cut the browser-CI cost (the ~15-min long pole) by **path-filtering** the
`browser` job so it only runs its expensive steps when UI-touching files change,
plus a **conservative, optional dedup** of any clearly-redundant browser tests.
No coupling to the launcher (Legs 1-2).

## Context

- **DD7 (operator-directed):** most PRs (connectors/DB/MCP/agent) don't touch the
  UI and pay ~15 min for ~zero browser signal. Path-filter the `browser` job to
  UI changes only. The **Windows** half of DD7 already landed in `test.yml` (the
  F3 "DD7 revised — 2026-06-13" curated-subset block) — this leg is the
  **`browser` job only**; do not touch the Windows job.
- **Mechanism (architect-validated):** GitHub Actions `paths:` filters are
  workflow/trigger-level, NOT per-job — so use a **`dorny/paths-filter` step**
  first, then gate the expensive steps (setup-python, pip install, Chromium
  provision, the pytest run) on its output. The job still runs (checkout +
  filter) but **completes green** when those steps skip — so a future required
  check stays satisfied (no neutral-emit shim needed). `main` has no branch
  protection today anyway (F3).
- **Dedup is light/transitional (re-scoped after recon):** `test_markdown.py` is
  **7 functions** (the "91" was parametrized cases — legitimate markdown
  scenarios, NOT redundant). So the path-filter is the real win; dedup is a
  **conservative, optional audit** — trim only *clearly-redundant* tests (genuine
  duplicate functions, not parametrized scenarios), coverage-guided; **if nothing
  is clearly redundant, skip it** — the suite is transitional (the next mission's
  gated-MCP apparatus supersedes Playwright-Chromium; don't manufacture dedup or
  risk coverage loss).

## Inputs

- `.github/workflows/test.yml` — the `browser` job (`ubuntu-latest`: checkout@v5
  → setup-python@v6 → `pip install -e ".[all-llms,dev]"` → Provision Chromium →
  `pytest -m browser tests/browser/`). Triggers: `pull_request` + `push`
  (the workflow header has no `paths:`).
- The UI source surface: `the_one/interfaces/web/**` (api.py, app.py,
  middleware.py, static/{index.html,js,css,brand,fonts}), `tests/browser/**`, and
  `pyproject.toml` (the Playwright pin — a bump there must re-run the suite).

## Outputs

- `.github/workflows/test.yml` — the `browser` job gains a `dorny/paths-filter`
  step and `if:` gates on the expensive steps.
- *(optional)* a small number of clearly-redundant browser tests removed, with
  the removal + coverage rationale recorded — OR a note that the audit found
  nothing clearly redundant (path-filter is the win).

## Acceptance Criteria

- [ ] The `browser` job runs a `dorny/paths-filter` step (after checkout) with a
      `ui` filter on `the_one/interfaces/web/**`, `tests/browser/**`, and
      `pyproject.toml` (the Playwright pin); the
      setup-python, `pip install`, Chromium-provision, and pytest steps are gated
      `if: steps.<id>.outputs.ui == 'true'`.
- [ ] On a non-UI change the job **completes successfully (green)** with the
      expensive steps skipped (no Chromium install, no browser run); on a
      UI-touching change it runs the full browser suite as before.
- [ ] The push-to-main lane works (dorny/paths-filter diffs against the
      before-SHA on push; base-ref on PR) — the filter is configured so both
      trigger lanes classify correctly.
- [ ] The Windows job and all other jobs (test/bwrap/lint) are **untouched**.
- [ ] *(dedup, optional)* any removed browser tests are genuine duplicates (not
      parametrized scenarios); coverage of the affected UI surface is unchanged;
      the removal is recorded. If nothing clearly redundant, the flight log notes
      that and no tests are removed.
- [ ] **This flight does NOT touch the web UI** (the launcher legs touch
      `interfaces/app.py` + `tests/test_app_launcher.py`, neither under the
      filter), so on flight/04's own PR the browser job **correctly SKIPS and
      goes green-fast** — that skip IS the path-filter working, and is the FD's
      primary verification at 2d. The gated *run* path (browser tests still pass
      when triggered) is architecturally sound (valid YAML + the well-established
      `dorny/paths-filter`); if the FD wants positive confirmation, force one run
      via a no-op touch to a `web/**` file or `workflow_dispatch` — optional, not
      a landing blocker.

## Verification Steps

- Local: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"` — the workflow is valid YAML after the edit.
- Local: re-read the `browser` job and confirm every expensive step carries the `if: steps.<id>.outputs.ui == 'true'` gate and the filter paths are correct.
- *(dedup, if any)* `.venv/bin/python -m pytest tests/browser/<touched_file> --collect-only -q` to confirm the remaining cases still cover the surface; do NOT run the full browser suite locally (Chromium/long).
- CI (FD, at 2d push): the `browser` job goes green-fast on this PR if it's
  non-UI, OR runs the suite if UI files changed; other jobs unaffected.

## Implementation Guidance

1. **`.github/workflows/test.yml` — gate the `browser` job:**
   ```yaml
     browser:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v5
         # Path-filter: the browser suite (~15 min) only needs to run when the
         # web UI changes. Most PRs (connectors/DB/MCP/agent) don't touch it.
         # ADD any new UI surface to the `ui` filter below, or the browser
         # suite won't run on PRs that change it. First push to a new branch →
         # before-SHA is all-zeros → the action treats everything as changed →
         # the suite RUNS (conservative-safe, intentional).
         - name: Detect UI changes
           uses: dorny/paths-filter@v3
           id: changes
           with:
             filters: |
               ui:
                 - 'the_one/interfaces/web/**'
                 - 'tests/browser/**'
                 - 'pyproject.toml'   # covers Playwright pin bumps
         - uses: actions/setup-python@v6
           if: steps.changes.outputs.ui == 'true'
           with:
             python-version: "3.11"
             cache: pip
         - name: Install dependencies
           if: steps.changes.outputs.ui == 'true'
           run: pip install -e ".[all-llms,dev]"
         - name: Provision Chromium
           if: steps.changes.outputs.ui == 'true'
           run: python -m playwright install --with-deps chromium
         - name: Run browser tests (host-native)
           if: steps.changes.outputs.ui == 'true'
           env:
             THE_ONE_DEV_MODE: "true"
           run: python -m pytest -m browser tests/browser/ --timeout=300 --tb=short
   ```
   - Pin `dorny/paths-filter` to a major (`@v3`). It diffs the base ref on
     `pull_request` and the before-SHA on `push` automatically — both this
     workflow's triggers are supported.
   - Add a one-line comment above the filter explaining the cost intent and that
     a new UI surface must be added to the `ui` filter (mirrors the Windows
     curated-list maintenance note's spirit).

2. **Dedup (optional, conservative):** quickly audit `tests/browser/` for
   *genuinely duplicate* test functions (NOT parametrized cases — those are
   distinct scenarios). The big files are interaction flows
   (`test_flow_studio_*`, editor save/dirty-confirm). Trim only high-confidence
   duplicates where another test already asserts the same behavior; record each
   removal + why coverage is preserved. **If nothing is clearly redundant, remove
   nothing** and **record "audit performed, nothing clearly redundant"** in the
   flight log (confirms the audit happened) — the path-filter is the deliverable.

3. **Do NOT** touch the `windows`/`test`/`bwrap`/`lint` jobs, the launcher
   (Legs 1-2), or the workflow's top-level triggers.

## Citation Audit

Citations verified at leg-design time: `.github/workflows/test.yml` `browser`
job (checkout@v5/setup-python@v6/pip/Provision Chromium/`pytest -m browser`) OK;
the UI source surface `the_one/interfaces/web/**` (api.py/app.py/middleware.py/
static) OK; `tests/browser/**` OK; `test_markdown.py` = 7 functions (the 91 are
parametrized) — corrected the earlier "91 redundant tests" framing. No source
`file:line` citations beyond the workflow; all verified.
