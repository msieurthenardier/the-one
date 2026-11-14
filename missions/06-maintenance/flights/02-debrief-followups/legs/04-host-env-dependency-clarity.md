# Leg: 04-host-env-dependency-clarity

**Status**: completed
**Flight**: [Debrief Follow-ups](../flight.md)

## Objective

Close the host-environment dependency gap surfaced during Flight 01 Leg 01 by adding a guardrail comment in `pyproject.toml`. Design review discovered the gap is **already closed**: `markdownify` and `readability-lxml` were moved from `[project.optional-dependencies].dev` into base `[project.dependencies]` in commit `e65077e` (Flight 05 web expansion, 2026-04-30), and `CLAUDE.md:13` already documents the canonical install (`pip install -e ".[all-llms,dev]"`). The remaining work is a small guardrail: an inline `#` comment in `pyproject.toml` immediately above the two deps noting they are runtime feature deps consumed by `FetchUrlTool`, so a future maintainer doesn't accidentally move them back to `[dev]` and re-open the gap.

## Context

Flight 01 Leg 01 flight-log entry (line 56 of that flight's `flight-log.md`):

> Pre-existing host-env dependency gap (NOT introduced by this leg, but discovered during verification): `markdownify` and `readability-lxml` were missing from the host's `~/.local` Python env, causing 3 test failures in `test_web_tools.py` and `test_api_tool_configs.py`. CI runs `pip install '.[dev]'` in a fresh container so they are present there.

This was accurate as of Flight 01 (the deps were in `[dev]` at the time). Commit `e65077e` (Flight 05, 2026-04-30) moved the deps into base `[project.dependencies]`, which closed the host-env gap automatically — any operator who runs `pip install -e .` (with or without extras) now gets these deps.

The actual consumer is **`FetchUrlTool`** (`the_one/tools/web.py:202-203`), where `markdownify` and `readability` are lazily imported inside `_call` only when `text/html` content is encountered. (Note: the original Flight 01 flight-log mentioned `WebSearchTool` as a likely consumer — that was incorrect; `WebSearchTool` at `web.py:331` does not import either dep.)

The leg's purpose is therefore reduced to a **guardrail comment** preventing future regression:
- A maintainer doing dependency hygiene might see two test-named-sounding deps and move them back to `[dev]`. The inline `#` comment makes the runtime-feature attribution explicit at the dep-list site.

## Inputs

- `pyproject.toml` (existing; verified base `[project.dependencies]` at L6-20 includes `"readability-lxml>=0.8"` at L8 and `"markdownify>=0.13"` at L9; `[dev]` group at L26 contains only test/lint tooling, NOT these two deps)
- `CLAUDE.md` (existing; `## Commands` section at L9; install command at L12-13 already says `pip install -e ".[all-llms,dev]"` — no edit needed)
- `the_one/tools/web.py` (existing; `FetchUrlTool` consumer at L142-208 with lazy imports at L202-203)

## Outputs

- `pyproject.toml` has a `#` comment immediately above the `"readability-lxml>=0.8"` line (L8) noting both deps are runtime feature deps consumed by `FetchUrlTool` and explaining why they MUST stay in base — preventing a future maintainer from moving them back to `[dev]`.

## Acceptance Criteria

- [x] `grep -B 3 '"readability-lxml' pyproject.toml` shows a `#` comment line referencing `FetchUrlTool` (or `the_one/tools/web.py`) and explaining "MUST stay in base" or equivalent guardrail wording immediately above the dep
- [x] `pyproject.toml` line ordering preserved: comment above `readability-lxml>=0.8`, which stays above `markdownify>=0.13`, which stays inside the base `dependencies = [...]` array (L6-20)
- [x] No actual dep-tier change — `readability-lxml` and `markdownify` remain in base `dependencies`, NOT moved to or from `[dev]`
- [x] CLAUDE.md unchanged (already documents the install command at L13)
- [x] `python -c "import markdownify, readability"` succeeds in the host env (verifies the gap is in fact closed for this operator; if it fails, surface in flight-log as a `pip install -e .` re-bootstrap reminder, but do NOT modify `pyproject.toml` further)
- [x] `pytest -q --ignore=tests/browser --timeout=120` green (no regression — the change is a comment-only edit in TOML)
- [x] Ruff lint + format clean: `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` (TOML is not lint-checked, but Python files should remain clean since none are touched)

## Verification Steps

- `cd ~/projects/the-one && grep -B 3 -A 1 '"readability-lxml' pyproject.toml` — confirm guardrail comment present immediately above
- `cd ~/projects/the-one && grep -A 1 '"markdownify' pyproject.toml` — confirm dep still adjacent in base list
- `cd ~/projects/the-one && python -c "import markdownify, readability; print('OK')"` — confirm host env has both deps
- `cd ~/projects/the-one && pytest -q --ignore=tests/browser --timeout=120 2>&1 | tail -5`
- `cd ~/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/`

## Implementation Guidance

> **Note**: design review verified that the dep-tier gap is already closed (commit `e65077e` moved the deps to base). This leg is a **guardrail comment only** — do NOT change which section the deps live in.

1. **Confirm pre-state with re-grep**:
   - `grep -nE '"(markdownify|readability)' pyproject.toml` — confirms both deps are in base `[project.dependencies]` (was L8-9). Re-grep right before the edit since concurrent flight branches could shift line numbers.
   - `grep -nE '\[project.optional-dependencies\]|\bdev = ' pyproject.toml` — confirms `[dev]` contains only test/lint tooling (was L22-26).

2. **Add the guardrail comment**:
   - Insert a `#` comment immediately above the `"readability-lxml>=0.8"` line. TOML supports `#` comments anywhere, including inside multi-line arrays. Suggested wording (compact, pinned to the consumer):
     ```toml
     dependencies = [
         "httpx>=0.27",
         # readability-lxml + markdownify: runtime feature deps consumed by
         # FetchUrlTool (the_one/tools/web.py) when fetching text/html. Keep
         # in base dependencies — moving to [dev] would re-open the host-env
         # gap that Flight 01 Leg 01 surfaced (and commit e65077e closed).
         "readability-lxml>=0.8",
         "markdownify>=0.13",
         ...
     ]
     ```
   - 4 lines of comment is fine — the file uses sparse comments elsewhere and the rationale is non-obvious enough to merit the explicit warning.

3. **Verify**:
   - Run `python -c "import markdownify, readability"` to confirm the host env is healthy.
   - Run the full test suite for regression check (the change is a TOML comment so should be a no-op for tests).
   - Run ruff (Python files — no TOML changes ever affect Python ruff output).

## Edge Cases

- **Host env may have lost the deps since Flight 01 Leg 01's manual `--user --break-system-packages` install**: if `python -c "import markdownify, readability"` fails, the operator needs to run `pip install -e .` (no extras needed since the deps are now in base). Surface this in flight-log as a "re-bootstrap reminder" but do NOT add a CLAUDE.md doc — the install command at `CLAUDE.md:13` already covers it.
- **Flight 01 historical "3 host-only failures" count is stale**: the count came from the Flight 01 era when deps were in `[dev]`. Since deps are now in base, the count today is presumably 0 (the manual `--break-system-packages` install + the e65077e commit both closed it for different consumers). Do NOT re-verify the historical count — only the current host env's import status matters.
- **TOML comment placement**: keep the comment INSIDE the `dependencies = [...]` array (above the deps it documents). A comment outside the array would read as a top-of-section header and lose its proximity-pinning to the relevant deps.

## Files Affected

- `pyproject.toml` — 4-line `#` guardrail comment above the `"readability-lxml>=0.8"` entry in base `[project.dependencies]` (no actual dep movement)
- *(no `CLAUDE.md` change — install command at L13 already documents the canonical bootstrap)*
- *(no `the_one/tools/web.py` change — `FetchUrlTool` consumer is correct as-is)*

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] `pyproject.toml` guardrail comment in place immediately above `"readability-lxml>=0.8"`
- [x] `python -c "import markdownify, readability"` succeeds (host env healthy; if fails, log in flight-log)
- [x] Full pytest suite green
- [x] Ruff lint + format clean
- [x] Update flight-log.md with leg progress entry — record:
  - Original premise was obsolete (gap already closed by commit `e65077e`)
  - Leg pivoted to a guardrail-comment-only scope
  - The actual consumer is `FetchUrlTool` (not `WebSearchTool` as the original leg said)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md (Checkpoints AND Legs lists; ALSO check off the Contributing-to-Criteria item: "Host-env dependency gap closed (either `pyproject.toml` shift OR CLAUDE.md `pip install '.[dev]'` bootstrap)")
- [ ] DO NOT commit — deferred to flight close
