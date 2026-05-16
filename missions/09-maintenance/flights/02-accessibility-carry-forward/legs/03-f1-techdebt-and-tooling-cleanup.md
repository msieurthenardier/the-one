# Leg: 03-f1-techdebt-and-tooling-cleanup

**Status**: landed
**Flight**: [Accessibility Carry-forward + F1 Tech-Debt Cleanup](../flight.md)

## Objective

Land the six non-methodology recommendations from the F1 debrief as a bundled atomic-sub-commits leg, before they decay into the next maintenance pass.

## Context

F1's debrief (`missions/09-maintenance/flights/01-integrity-gate-restoration/flight-debrief.md`) surfaced 10 forward-looking recommendations. Four are methodology updates (covered by `/flight`, `/flight-debrief`, `/mission-debrief`, `/routine-maintenance` skill prompts — they live in the mission-control repo and don't ship with the-one). The remaining SIX are concrete technical fixes for the-one's Makefile + agents.md surfaces. They share a common touch surface (~1 Makefile + ~3 agents.md/SECURITY-MODEL.md edits), are small (~1-5 line edits each), and bundle cleanly into one leg.

The unifying thread: **don't let F1's tail-end tech-debt rot for a maintenance cycle**. Each item is small enough to be opportunistically pulled forward without expanding the leg beyond ~1-2 hours of work.

**Pre-existing state (verified during F2 design recon, 2026-05-16)**:
- `agents.md:233` cites `test_max_context_tokens_live_read_across_resolver` in `tests/test_agent_core.py` — neither name nor file exists. Actual test: `test_usage_event_reflects_live_max_context_tokens_at_emission` at `tests/test_process_and_broadcast_live_read.py:98`.
- `Makefile doctor` target (around L148) uses bare `python -c "..."` — sub-shell fails when `python` isn't on PATH (only `python3` + `.venv/bin/python` present).
- `Makefile audit` target (around L154) already carries the `## Run pip-audit against host venv (non-blocking; surfaces advisories)` help-string — provides the rationale; an inline comment block above the target would only reinforce. Treat the F1 "Non-blocking by design" recommendation as already-satisfied via the existing help-string.
- `Makefile` has no `rebuild-browsers` target.
- `Makefile` has no `audit-bytes` target.
- `agents.md ## Project Conventions` (around L171) has `### gated-debug-instrumentation` (M08 F7) and `### live-read-across-lazy-resolver-boundary` (F1 Leg 3) — no `### host-side-bench-drift-detection` entry yet.
- `SECURITY-MODEL.md` has no entry on the npm-spec regex as a security primitive.

## Inputs

- `Makefile` — current targets include `doctor` (L147-149) and `audit` (L151-154); no `rebuild-browsers`, no `audit-bytes`. The `rebuild` target (where? — need to grep) is the base for `rebuild-browsers`.
- `the_one/agents.md`:
  - `## Project Conventions` heading (~L171) — destination for `### host-side-bench-drift-detection`
  - `### live-read-across-lazy-resolver-boundary` entry (~L229-238) — destination for the citation fix
  - Possibly `## Security` section or similar (locate by reading top headings) — destination for npm-spec regex doc
- `SECURITY-MODEL.md` — alternative destination for the npm-spec regex doc (decide during implementation based on file structure fit)
- `the_one/mcp/cache_cleanup.py:71-83` — the `_VALID_NPX_PKG_RE` exemplar to reference in the new doc
- `tests/test_process_and_broadcast_live_read.py:98` — the actual test name that should replace the broken citation
- F1 debrief at `missions/09-maintenance/flights/01-integrity-gate-restoration/flight-debrief.md` — source of truth for the bundled recommendations

## Outputs

- `Makefile`:
  - New `rebuild-browsers` target
  - `doctor` target uses `.venv/bin/python -c ...`
  - New `audit-bytes` target
- `the_one/agents.md`:
  - `### live-read-across-lazy-resolver-boundary` citation corrected (2-line fix at L233)
  - New `### host-side-bench-drift-detection` entry in `## Project Conventions`
  - New entry documenting npm-spec regex (placement TBD during implementation — Project Conventions or a Security section)
- Six atomic sub-commits inside this leg, each independently revertable

## Acceptance Criteria

- [ ] `cd /home/cprch/projects/the-one && make help | grep "rebuild-browsers"` matches (target exists)
- [ ] `cd /home/cprch/projects/the-one && grep -E "^rebuild-browsers: rebuild _ensure-playwright" Makefile` matches — target has both prereqs in order (uses existing `_ensure-playwright` machinery at `Makefile:39-46`, not raw `playwright install chromium`)
- [ ] `cd /home/cprch/projects/the-one && grep -A2 "^doctor:" Makefile` shows `.venv/bin/python3 -c ...` (NOT bare `python -c ...`; matches `.venv/bin/pip-audit` shape in `audit` target)
- [ ] `cd /home/cprch/projects/the-one && make audit-bytes` exits 0 (no raw U+2028/U+2029 chars in `the_one/` or `tests/`)
- [ ] `cd /home/cprch/projects/the-one && grep -A2 "^audit-bytes:" Makefile` shows the target invokes `git grep -lP "[\x{2028}\x{2029}]"` against the appropriate paths
- [ ] `cd /home/cprch/projects/the-one && grep -n "test_usage_event_reflects_live_max_context_tokens_at_emission" the_one/agents.md` matches inside the `### live-read-across-lazy-resolver-boundary` entry
- [ ] `cd /home/cprch/projects/the-one && grep -n "test_max_context_tokens_live_read_across_resolver" the_one/agents.md` returns empty (broken citation gone)
- [ ] `cd /home/cprch/projects/the-one && grep -n "^### \`host-side-bench-drift-detection\`" the_one/agents.md` matches (new convention landed — note the **backtick wrapping** per the section's convention; all five existing entries at L175, 185, 195, 205, 219, 229 use `` ### `slug` `` form)
- [ ] `cd /home/cprch/projects/the-one && grep -n "_VALID_NPX_PKG_RE\|npm.spec" SECURITY-MODEL.md` matches in `## Tool Execution Boundary` section (security-primitive doc landed in SECURITY-MODEL per Architect F2 review)
- [ ] `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both exit 0 (F1 baseline preserved)
- [ ] Container pytest unchanged (1700 passed). Host pytest unchanged **relative to Leg 2's landed state** (host has a pre-existing `mcp.client.auth.exceptions` import failure unrelated to F2 — documented in Leg 1's flight-log entry; M10-candidate)

## Verification Steps

- `cd /home/cprch/projects/the-one && make help` — full help listing; `rebuild-browsers`, `audit-bytes` visible
- `cd /home/cprch/projects/the-one && make doctor` — exit 0 (host); should work even from a sub-shell that lacks bare `python` on PATH
- `cd /home/cprch/projects/the-one && make audit-bytes` — exit 0 (no LSEP/PSEP source bytes)
- **Probe `audit-bytes` correctness**: deliberately write a temporary file with a raw U+2028 byte (`printf 'x\xe2\x80\xa8y' > /tmp/test-lsep.py`) under `the_one/` (or as a probe in `tests/`), run `make audit-bytes`, confirm non-zero exit, delete the probe. Documents the target detects its target class.
- `cd /home/cprch/projects/the-one && make rebuild-browsers` — runs `make rebuild` then `playwright install chromium`; exit 0 (or surfaces clear error if image missing)
- `cd /home/cprch/projects/the-one && sed -n '/^### live-read-across-lazy-resolver-boundary/,/^### /p' the_one/agents.md` — shows the entry with the corrected test citation (no `test_max_context_tokens_live_read_across_resolver`; no `tests/test_agent_core.py`)
- `cd /home/cprch/projects/the-one && sed -n '/^### host-side-bench-drift-detection/,/^### /p' the_one/agents.md` — shows the new convention entry
- `cd /home/cprch/projects/the-one && pytest --tb=no -q` (host) — 1700 passed unchanged
- `cd /home/cprch/projects/the-one && docker exec the-one pytest --tb=no -q --ignore=tests/browser` — 1700 passed unchanged

## Implementation Guidance

Six sub-fixes, each its own sub-commit. Order them roughly by isolation (Makefile-only first, then agents.md). Run `ruff check + ruff format --check` between sub-commits if any agents.md edits introduce trailing whitespace (unlikely, but cheap to check).

1. **(a) Add `make rebuild-browsers` target** — use existing `_ensure-playwright` machinery, don't duplicate it
   - **Important context (Architect spot-check during F2 design review)**: `Makefile:39-46` already defines a `_ensure-playwright` internal target that conditionally installs Chromium (with `install-deps`) when the binary is absent. `make test-browser` and `make test-pixel` already chain it. The F1 debrief's "312 ERRORS at setup" came from bypassing `make` and calling raw `docker exec the-one pytest -m browser` directly. The "rebuild wipes Chromium" foot-gun is **already mitigated for the canonical entry points** — the new `rebuild-browsers` target is a convenience alias for operators who run `make rebuild` standalone and then expect tests to work without an intermediate `make test-browser` call.
   - Locate the existing `rebuild` target (`Makefile:22` area) and `_ensure-playwright` target (`Makefile:39-46`). Read both to understand the existing pattern.
   - Add a new target chaining the existing primitives — DO NOT re-implement the install logic:
     ```make
     .PHONY: rebuild-browsers
     rebuild-browsers: rebuild _ensure-playwright  ## Rebuild dev container + ensure Playwright Chromium present
     ```
     The `_ensure-playwright` dependency gives us the conditional + `install-deps` logic for free.
   - Test: run `make rebuild-browsers`; confirm rebuild completes + chromium check passes. Then deliberately remove `~/.cache/ms-playwright/` from the container (`docker exec the-one rm -rf /root/.cache/ms-playwright/chromium_headless_shell-1208`) and re-run `make rebuild-browsers`; confirm the missing-Chromium case triggers a fresh install via `_ensure-playwright`'s conditional.
   - Sub-commit: `flight/02: add make rebuild-browsers target chaining _ensure-playwright (F1 debrief carry-forward)`

2. **(b) Fix `make doctor` python resolution**
   - Edit the `doctor` target (around `Makefile:148`) to change `python -c "..."` → `.venv/bin/python3 -c "..."`.
   - Architect note (F2 design review): `.venv/bin/python` is actually a symlink chain → `python3` → `/bin/python3` (the venv is mostly a directory of site-packages + `pyvenv.cfg`; the interpreter itself is system Python). Use `.venv/bin/python3` directly for explicitness; matches `.venv/bin/pip-audit`'s shape in the `audit` target.
   - The probe content stays identical — same import list (`asgi_lifespan, pytest_asyncio, pytest_timeout, pytest_playwright, pixelmatch, pip_audit`, `from PIL import Image`, `find_spec('playwright')`, `import ruff`).
   - Test: run `make doctor` from a sub-shell that lacks bare `python` (e.g., `bash -c "cd /home/cprch/projects/the-one && make doctor"`); confirm exit 0. Then deliberately uninstall something (`.venv/bin/pip uninstall -y pixelmatch && make doctor` should exit non-zero; `.venv/bin/pip install pixelmatch` to restore).
   - Sub-commit: `flight/02: make doctor uses .venv/bin/python3 (F1 debrief carry-forward)`

3. **(c) Add `make audit-bytes` target**
   - Add under the existing `# ── Drift detection (host-side) ──` section header (alongside `doctor` and `audit`):
     ```make
     .PHONY: audit-bytes
     audit-bytes:  ## Detect raw U+2028/U+2029 (LSEP/PSEP) characters in tracked source — must be empty
     	@! git grep -lP "[\x{2028}\x{2029}]" -- 'the_one/**/*.py' 'tests/**/*.py'
     ```
     The leading `!` inverts the exit code — `git grep -l` returns 0 when files match (bad) and 1 when nothing matches (good); we want the inverse. **Pathspec `**` covers recursive sub-directories** (`the_one/*.py` alone would miss nested modules).
   - **Important contract** (Architect note from F2 design review): `git grep` scans the git INDEX, not the working tree. Files newly added but unstaged won't be scanned. The target's purpose is "ensure committed content is clean" — run it AS PART of pre-commit or after staging. A developer who Edits a file containing raw LSEP/PSEP but doesn't `git add` it will get a misleading clean result. Document this contract in the help-string or an inline Makefile comment.
   - **Scope rationale**: pathspec is `.py`-only because F1's foot-gun class was "JS string literals inside Python source" (Python's `Edit` tool can inject raw LSEP bytes silently; vanilla `.js` source goes through a different review path). If a future incident class surfaces in `.js`/`.html`/`.css` template content, broaden the pathspec.
   - **Verify `git grep -P` support**: requires PCRE-enabled git. Architect F2 review verified on this project's git 2.43.0 — PCRE present, probe confirmed working. If a future operator's git lacks PCRE, fall back to a Python-based scanner.
   - Test: run `make audit-bytes` — should exit 0 today (F1's byte-level grep at flight-review confirmed zero raw LSEP/PSEP). Then deliberately introduce a raw byte (see Verification Steps probe — note that the probe file must be `git add -N`'d to be visible to `git grep`); confirm non-zero exit; remove.
   - Sub-commit: `flight/02: add make audit-bytes target (F1 debrief carry-forward)`

4. **(d) Fix `agents.md` live-read entry citation**
   - Open `the_one/agents.md` and locate the `### live-read-across-lazy-resolver-boundary` entry (around L229-238).
   - Find the sentence ending: `"...M07 F7 L05 pins the contract with `test_max_context_tokens_live_read_across_resolver` (in `tests/test_agent_core.py`)."`
   - Replace with: `"...M07 F7 L05 pins the contract with `test_usage_event_reflects_live_max_context_tokens_at_emission` (in `tests/test_process_and_broadcast_live_read.py`)."`
   - Verify by `grep -n "test_usage_event_reflects" the_one/agents.md` — should match exactly once now.
   - Sub-commit: `flight/02: agents.md live-read citation correction (F1 debrief carry-forward)`

5. **(e) Add `` ### `host-side-bench-drift-detection` `` convention** (backtick the slug — section convention)
   - Open `the_one/agents.md` and locate `## Project Conventions` (L171); find the existing entries (all wrap their slug in backticks):
     - `` ### `trust-the-runtime` `` (L175)
     - `` ### `gated-debug-instrumentation` `` (L185 area)
     - `` ### `confirm-delete-pattern` `` (L195 area, if present)
     - `` ### `live-read-across-lazy-resolver-boundary` `` (L229)
   - Verify the existing backtick form via `grep -nE '^### \`' the_one/agents.md` before adding.
   - Add a new entry AFTER `` ### `gated-debug-instrumentation` `` AND BEFORE `` ### `live-read-across-lazy-resolver-boundary` `` (chronological: gated-debug landed M08 F7, host-side-bench-drift-detection codifies F1 M09 Leg 2 work, live-read-across-lazy-resolver-boundary codifies F1 M09 Leg 3 work).
     ```markdown
     ### `host-side-bench-drift-detection`

     Targets whose purpose is to detect drift between the developer's HOST bench and the canonical container should run on the host (not `docker exec`), surface a clean diagnostic on failure, and be invoked manually (not on every dev iteration).

     **Why**: F1 (M09 Leg 2) introduced `make doctor` to catch the `asgi-lifespan`-declared-but-uninstalled drift that wasn't catchable in container-first `make lint` / `make format` / `make test` (which run via `docker exec` against the container's own venv where `pip install -e .[dev]` ran at image-build time). The host venv is where the operator runs ad-hoc `pytest` and where dev-extras drift surfaces; container-first tooling can't see it.

     **Pattern**: a host-side drift target lives under a `# ── Drift detection (host-side) ──` section header in the `Makefile`, deliberately separate from container-first targets. It uses `.venv/bin/python3 -c "..."` (NOT bare `python -c "..."` — avoids the sub-shell PATH-resolution foot-gun where bare `python` may be absent and `python3` is the live interpreter). Exit code carries the contract: 0 if clean, non-zero with a clear `ModuleNotFoundError` / `AssertionError` if drift detected.

     **Live examples**: `make doctor` (probes declared dev extras from `pyproject.toml`'s `[project.optional-dependencies].dev`); `make audit` (runs `.venv/bin/pip-audit --skip-editable || true`, non-blocking); `make audit-bytes` (detects raw U+2028/U+2029 LSEP/PSEP characters in source — defends against the F1 Leg 3 implementation anomaly class).
     ```
   - Verify by `grep -n "^### host-side-bench-drift-detection" the_one/agents.md` — match.
   - Sub-commit: `flight/02: agents.md ### host-side-bench-drift-detection convention (F1 debrief carry-forward)`

6. **(f) Document npm-spec regex as a security primitive** — `SECURITY-MODEL.md ## Tool Execution Boundary` BULLET form (Architect-corrected + Leg-3-cycle-1 corrected)
   - **Placement (revised per cycle-1 Leg 3 design review)**: `SECURITY-MODEL.md ## Tool Execution Boundary` (L49-82) is the structurally-correct home. **HOWEVER**, that section is a **flat bullet list** (existing entries are `- **Filesystem (M05 F3)**: ...`, `- **Execution (M05 F4)**: ...`, etc.) — NOT nested H3 headings. The original draft proposed `### npm-spec-allowlist-for-operator-supplied-paths` which would break the section's voice. **Correct shape**: add as a new top-level bullet, peer of the existing four. Inline the regex as an indented code block under the bullet.
   - Add as a new peer bullet under `## Tool Execution Boundary`:
     ```markdown
     - **Operator-supplied identifier allowlists**: any operator-config-derived string that flows into `Path()` joins, `subprocess.run()` argv elements, or filesystem operations MUST be validated against a spec-grounded allowlist regex, NOT a permissive character class. The character class `[A-Za-z0-9._@/-]` is NOT an allowlist for paths — every character is permitted individually, so `../etc/passwd` passes. The spec-grounded form is anchored, structure-aware, and rejects path-traversal patterns by construction.

       Exemplar regex (npm package-name spec — covers `lodash`, `@scope/pkg`, `pkg-with-dashes`, `pkg_with_underscores`; rejects `../etc/passwd`, `a/b/c`, `.hidden`, uppercase, shell metacharacters):

       ```python
       _VALID_NPX_PKG_RE = re.compile(r'^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$')
       ```

       Implementation: `the_one/mcp/cache_cleanup.py:71-83` defines `_VALID_NPX_PKG_RE` module-level, validates at function entry of `_clean_npx`, raises `ValueError` before any path operation. Established in F1 M09 Leg 3 after a design-review catch (the original draft used the broken char-class allowlist).
     ```
   - Verify with the AC's grep.
   - Sub-commit: `flight/02: document npm-spec regex security primitive (F1 debrief carry-forward)`

7. **Verify F1 baselines unchanged**
   - `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both exit 0
   - `pytest --tb=no -q` host AND `docker exec the-one pytest --tb=no -q --ignore=tests/browser` — both at 1700 passed

## Edge Cases

- **`make rebuild-browsers` target dependency**: if the project's `rebuild` target has side effects that shouldn't be reproduced (rare), drop the `rebuild-browsers: rebuild` dependency and require `make rebuild && make rebuild-browsers` instead. Decide during implementation.
- **`git grep -P` unavailable**: fall back to scanning via Python (`.venv/bin/python -c "import pathlib, sys; bad = [p for p in pathlib.Path('the_one').rglob('*.py') if any(c in p.read_text() for c in '  ')]; sys.exit(0 if not bad else 1)"`). Implementer's choice based on portability needs.
- **agents.md ordering**: if the existing `## Project Conventions` ordering is opaque, place the new entries alphabetically OR at the end. Don't restructure unrelated entries.
- **npm-spec doc placement**: if the implementer feels strongly the doc belongs in `SECURITY-MODEL.md`, that's also valid — the AC only requires it land in ONE of the two files.
- **`make rebuild-browsers` runtime cost**: `make rebuild` is non-trivial (~30s typical). The composite target may take 30-60s. Document the expected timing if surprising.

## Files Affected

- `Makefile` — 2 new targets (`rebuild-browsers` chaining `_ensure-playwright`; `audit-bytes`) + 1 fix (`doctor` uses `.venv/bin/python3`); the `audit` target stays as-is (its help-string already carries the non-blocking-by-design rationale)
- `the_one/agents.md` — 1 citation fix (~2 lines in `### live-read-across-lazy-resolver-boundary`), 1 new entry (`### host-side-bench-drift-detection` in `## Project Conventions`)
- `SECURITY-MODEL.md` — 1 new entry under `## Tool Execution Boundary` documenting the npm-spec regex security primitive
- `flight-log.md` — Leg Progress entry on completion

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All 6 sub-commits landed atomically
- [ ] Each new Makefile target verified (positive + negative case where applicable)
- [ ] F1 baselines preserved (ruff 0/0, broad pytest 1700)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] (Flight-close commit later checks off this leg in `flight.md` and transitions to `completed`)
