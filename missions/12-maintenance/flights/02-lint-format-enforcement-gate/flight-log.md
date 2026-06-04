# Flight Log: Lint/Format Enforcement Gate

**Flight**: [Lint/Format Enforcement Gate](flight.md)

## Summary
In progress. Two legs: (1) bring the tree to a zero ruff baseline + remove dead `noqa: BLE001`; (2) install the enforcement gate (pre-commit hook + GitHub Actions CI) that fails on violations. The gate is the deliverable; the cleanup is a one-time side effect (third recurrence of drift — Q1).

---

## Leg Progress

### 2026-06-04 — Leg 01 implementation (Developer agent, Sonnet)

**Before → after ruff state** (in-container ruff 0.15.15):
- `ruff check`: **78 errors → 0** ("All checks passed!").
- `ruff format --check`: **97 of 322 would reformat → 0** (322 already formatted; re-run stable).
- `grep noqa: BLE001` (`.py`): **12 → 0**.

**Residual resolution breakdown** (35 manual, after the 43 auto-fixed):
- **Auto-fix (43):** `ruff check --fix` cleared 33 I001 + 10 F401. Diff eyeballed — all F401 removals were in `tests/` files (no `the_one/` source import removed, no `__init__.py`, no `__all__` surface). The one `the_one/` change (`interfaces/web/app.py`) was pure I001 reordering.
- **N818 (5) → noqa:** `_Stub*` classes in `test_connectors_discord.py` got `# noqa: N818  # mirrors discord.py exception name`. No rename (preserves the discord.py correspondence).
- **N802 (6) → noqa:** test methods/functions across `test_connector_form_registry.py`, `test_flow_studio_connector_allowlist_dropdown.py`, `test_flow_studio_connector_discoverable_dropdown.py` (×2), `test_flow_studio_connector_routing_dropdown.py`, `test_connectors_inbound.py` got `# noqa: N802` with a one-line justification (name mirrors JS `onChange`/`optionalFns` handler, or the L6 step label). No rename.
- **E402 (2) → moved:** `test_connectors_pool.py` (merged `DiscoverableEntities`/`DiscoverableEntity` into the existing top `from the_one.connectors.base import (...)`) and `test_lifespan.py` (`import logging as _logging` moved into the stdlib top block). No noqa.
- **N806 (1) → rename:** `_FRONTEND_FIELDS` → `_frontend_fields` in `api.py` (function-local; both the definition and the single in-function reference updated).
- **E501 (21) → wrap:** comments wrapped in place (`_acl.py`, the 283-char NOTE in `_inbound.py`); docstring line wrapped (`db/models.py`); code wrapped via parens (`db/repositories.py`); JS expression wrapped (`test_connector_form_registry.py`); assertion/f-string messages split (`test_flow_chat_peer_attribution.py`, `test_flow_studio_connector_inference_provider_row.py`); JSON content string split via adjacent literals (`test_llm_provider_cross_provider_history.py`). **Migration SQL (`schema.py`, 6 lines) and prompt strings (`_inference.py`, 4 lines)** wrapped via `\` line-continuation inside the existing triple-quoted blocks — verified **byte-identical to HEAD** by AST string-constant set comparison (equal before AND after `ruff format`).

**BLE001 removals (12):** stripped from `connector_history.py` (7), `api.py` (3), `test_connectors_discord.py` (1), `mcp/cache_cleanup.py` (1). The dead `noqa` text was removed; where the trailing comment carried real rationale ("plugin error surface", "best-effort warmup per F4 L2", "architect: swallow everything", "pin no-exception", etc.) the rationale was **retained as a plain inline comment** — only the dead `noqa: BLE001` token was dropped. At `api.py:2463` only the noqa was removed; the `except (ConnectorClientError, Exception)` clause is left exactly as-is (Flight 03 T1/T2's). README example untouched; `BLE`/`B` NOT added to `select`.

**Suite:** `docker exec the-one pytest tests/ -q -x --timeout 60` → **2935 passed, 4 skipped, 538 deselected** in ~289s. Green. The 3 warnings are pre-existing aiosqlite event-loop-teardown ResourceWarnings, unrelated to this leg.

**Deviation (noted):** The leg enumerated 3 long `async def test_resolve_inference_provider_...` names under E501 expecting a "wrap". They could not be wrapped: the function name alone makes `async def <name>() -> None:` exceed 100, and `ruff format` actively re-wraps the `-> None` return annotation onto its own line — which pushes any `# noqa: E501` off the offending name line, leaving E501 unsuppressed (format vs noqa fight). Resolved by a **minimal rename** (`_returns_none_` → `_none_`, trimming redundant words), which the names tolerated (descriptive intent preserved) and which have **no external callers** (verified by grep — pytest-discovered test functions only). This is consistent with the leg's stance that rename is acceptable where a name has no external references. No other residual required a non-mechanical decision.

### 2026-06-04 — Leg 02 implementation (Developer agent, Opus)

**Files created:**
- `.pre-commit-config.yaml` — `repo: astral-sh/ruff-pre-commit`, `rev: v0.15.15`; hooks `id: ruff` (`args: [--fix]`) + `id: ruff-format`. No custom file args (honors `[tool.ruff]`).
- `.github/workflows/lint.yml` — GitHub Actions, triggers `pull_request` + `push:{branches:[main]}`, `concurrency: {group: lint-${{ github.ref }}, cancel-in-progress: true}`; one `ubuntu-latest` job: `actions/checkout@v4`, `actions/setup-python@v5` (python 3.11), `pip install ruff==0.15.15`, then **separate** steps `ruff check the_one/ tests/` and `ruff format --check the_one/ tests/`. Check-only (no `--fix`); ruff-only (no pytest/playwright/snapshots).

**Files changed:**
- `pyproject.toml` `[dev]` extra: `ruff>=0.6` → `ruff==0.15.15`; added `pre-commit>=3`. No other dep touched.
- `Makefile`: added `format-check: ## Ruff format check (read-only)` → `docker exec the-one ruff format --check the_one/ tests/` (mirrors `make lint`/`make format`).
- `CLAUDE.md` `## Commands`: note after the Lint & format block — `pre-commit install` once to activate (+`pipx install pre-commit` if needed), same checks run in CI on PRs/pushes-to-main, gate exists to stop ruff-baseline drift.

**pre-commit exercisable in this environment? YES.** Not pre-installed; installed via `pipx install pre-commit` → pre-commit 4.6.0. (pip pre-commit also in `[dev]` now.)

**Gate proof (exact commands + observed output):**
- *Clean tree, pre-commit's own run:* `pre-commit run --all-files` → `ruff (legacy alias)...Passed`, `ruff format...Passed`, **exit 0**. Confirmed no source mutation after: `docker exec the-one ruff check the_one/ tests/` → "All checks passed!" exit 0; `ruff format --check` → "322 files already formatted".
- *Deliberate violation (real source file `the_one/sessions/_locks.py`):* appended `import os, sys` + an over-long unformatted line, `git add`ed it.
  - `docker exec the-one ruff check the_one/sessions/_locks.py` → **exit 1** (E401, E402, I001, F401×2 — 5 errors).
  - `docker exec the-one ruff format --check the_one/sessions/_locks.py` → **exit 1** ("1 file would be reformatted").
  - `pre-commit run --files the_one/sessions/_locks.py` → `ruff...Failed` + `ruff format...Failed`, **exit 1** (hook blocks the commit; `--fix`/`ruff-format` modified the working file as expected).
- *Revert:* `git restore --staged` + restored the file to its Leg-1 compliant content. (Note: a plain `git checkout -- ` reverted to HEAD, which is *pre-Leg-1* since Leg-1 is uncommitted — it dropped Leg-1's one blank-line fix to this file. Caught immediately and restored from a pre-violation backup; `_locks.py` now matches its Leg-1 state: ruff check 0, format-check clean, back to ` M` in git status, nothing left staged.)
- `make format-check` → **exit 0** ("322 files already formatted").

**Post-gate sanity (no drift from Leg-1 baseline):** `docker exec the-one ruff check the_one/ tests/` → 0 ("All checks passed!"); `ruff format --check the_one/ tests/` → "322 files already formatted". Stray-`.py`-mutation audit: 102 modified `.py` (the Leg-1 set), no extras; new files only `.github/` + `.pre-commit-config.yaml`; other changes only `CLAUDE.md`, `Makefile`, `pyproject.toml`. Both new YAML files parse (`yaml.safe_load`). Full pytest suite not re-run (Leg-1 verified green; this leg adds no source-behavior change).

---

## Flight Director Notes

### 2026-06-04 — Flight start
- Invoked via `/agentic-workflow` for `the-one` mission 12, flight 02 (Lint/Format Enforcement Gate). Branched `flight/02-lint-format-enforcement-gate` off `main` (Flight 01 / mission scaffold now merged via PR #88, commit 8e260c2).
- Loaded phase file `.flightops/agent-crews/leg-execution.md` (Developer=Sonnet, Reviewer=Haiku) — structure valid.
- **Prerequisite resolved — CI host:** repo has no pipeline today (no `.github/workflows`, no `.pre-commit-config.yaml`). **Operator chose GitHub Actions** (natural fit, repo is GitHub-hosted). Leg 2 will add `.github/workflows/lint.yml`.
- **Ground-truth state confirmed (in-container ruff 0.15.15):** 78 lint errors (43 auto-fixable), 97 of 322 files would reformat — matches the leg specs exactly. **Pin ruff 0.15.15** across the container, the pre-commit rev, and the CI install to avoid passes-locally-fails-in-CI skew.
- Both legs authored during planning (status `ready`); per-leg design review then implementation. Flight `ready` → `in-flight`.

### 2026-06-04 — Leg 01 design review (Developer agent, Sonnet) + revisions
Design review enumerated all 35 manual residuals against the live tree and caught several inaccuracies; revisions applied (corrections + per-leg decision resolutions, no new scope → no second cycle):
- **[high] Stale edge case fixed:** the leg warned about renaming `ConnectorAuthRequired` (N818) and coordinating with Flight 03. But it is *already* `# noqa: N818`-suppressed at `errors.py:36` and is NOT among the 5 current N818 violations (those are all `_Stub*` test classes mirroring discord.py names). Edge case rewritten: leave `ConnectorAuthRequired` + its noqa untouched (Flight 03 Q2 may delete it).
- **[medium] BLE001 count corrected:** 12 in `.py` (not 10) — added `the_one/mcp/cache_cleanup.py`. Full file list now in Context. Removal confirmed lowest-risk (BLE not in `select`); ruleset left unchanged. The README example (1) is out of scope → Flight 06 doc scrub.
- **[medium] api.py:2463 guardrail:** the dead noqa there sits on a redundant `except (ConnectorClientError, Exception)` tuple — a real bug, but Flight 03 T1/T2's. Leg now says strip only the noqa, leave the clause untouched, so we don't collide with Flight 03.
- **[low] Format-stability criterion added:** E501 wrapping of migration SQL (`schema.py`) and prompt literals (`_inference.py`) must keep the string byte-identical.
- **Decision resolutions (Flight Director, per project's "noted inline in leg files"):** N818 → targeted `# noqa: N818` (mirror discord.py names); N802 → targeted `# noqa: N802` (mirror JS handler names); E402 → move imports to top; N806 → rename `_FRONTEND_FIELDS` → `_frontend_fields`. F401 auto-fix verified safe (all in test files, no `__all__`/`__init__` re-exports).
- Leg remains `ready`. Proceeding to implementation.

### 2026-06-04 — Leg 02 design review (Developer agent, Sonnet) + revisions
Design review verified the gate's invocations against the live Makefile/pyproject and surfaced a live skew proof; revisions applied (corrections + decision resolutions, no new scope → no second cycle):
- **[high] Version-skew root cause:** `[dev]` declares `ruff>=0.6` (unpinned) and the **host venv is already drifted to 0.15.11** vs container 0.15.15 — the very drift this gate must stop. Resolution: pin all enforcement points to **0.15.15** — pre-commit `rev: v0.15.15`; CI installs `ruff==0.15.15` *directly* (not `pip install ".[dev]"`, which re-resolves ruff to latest + drags the heavy dev tree into a lint-only job); and tighten `[dev]` to `ruff==0.15.15`.
- **[medium] pre-commit launcher undeclared:** added `pre-commit>=3` to `[dev]` + documented `pipx install pre-commit` fallback.
- **[medium] fix-vs-check pinned:** CI is check/fail-only (no `--fix`); local hook is `ruff --fix` + `ruff-format` (ergonomics, still blocks on violations).
- **[medium] CI triggers/concurrency:** `pull_request` + `push:{branches:[main]}` (the latter makes "green on main" demonstrable) + `concurrency` cancel-in-progress; action versions pinned `@v4`/`@v5`.
- **[low] "one source of truth" reframed:** `make lint` is check-only, `make format` write-only, and `ruff format --check` had no make target — so truth = shared `[tool.ruff]` config + path args `the_one/ tests/`. Added a `make format-check` target to give the format-gate invocation a make home.
- **[low] gate-proof clarified:** `pre-commit run` only sees *staged* files → "stage, run, revert."
- **[low] docs:** no CONTRIBUTING.md exists; note lands in CLAUDE.md `## Commands` after the Lint & format block.
- Leg remains `ready`. Proceeding to implementation.

---

### 2026-06-04 — Flight 02 code review (Reviewer agent, Haiku) → confirmed
- Reviewer evaluated ALL uncommitted changes (both legs) with no knowledge of developer reasoning. Verdict: **[HANDOFF:confirmed]** — zero-baseline outcome verified (ruff check 0, 322 formatted, no `.py` BLE001), byte-identical SQL/prompt wrapping confirmed via AST comparison, `_locks.py` integrity confirmed (single blank-line change, no corruption from the gate-proof hiccup), gate config correct (pre-commit `v0.15.15`, CI check-only ruff-only `ruff==0.15.15`, pyproject pin, Makefile target, CLAUDE.md note), no stray changes.
- Single review cycle, no fixes required. Proceeding to commit.

---

## Decisions

### Pin the whole toolchain to ruff 0.15.15 (Flight Director)
**Context**: `[dev]` declared `ruff>=0.6`; host venv had already drifted to 0.15.11 vs container 0.15.15 — an unpinned floor is itself a drift vector, which is the root cause Q1 keeps recurring.
**Decision**: Pin pre-commit `rev: v0.15.15`, CI `ruff==0.15.15`, and `[dev]` `ruff==0.15.15`. Future ruff bumps become one deliberate edit that flows to all enforcement points.
**Impact**: Eliminates the version-skew failure mode for the gate. A deliberate future-bump cost (one line) replaces silent drift.

---

## Deviations

### Leg 02 Developer ran on Opus, not the phase file's Sonnet
**Planned**: `leg-execution.md` specifies Developer = Sonnet.
**Actual**: The Leg 02 implementation agent inherited the session's Opus model (no explicit `model` override was passed on spawn).
**Reason**: Oversight in the spawn call. Harmless — Opus is more capable, only costlier; output was reviewed independently (Haiku) and confirmed. The "never Opus for the Reviewer" rule was honored (Reviewer = Haiku). Future spawns should pass `model: sonnet` explicitly for Developer agents.

---

## Anomalies

---

## Session Notes
