# Leg: 04-remove-concourse-and-self-modification

**Status**: completed
**Flight**: [Code Hygiene + Concourse Removal](../flight.md)

## Objective

Remove Concourse CI infrastructure and self-modification framing from the project. The Concourse pipeline drifted from being a tool the agent uses to being maybe-CI-someday infrastructure that nobody invokes; the self-modification narrative is largely vestigial after M08's product-shaped README. This leg deletes the dead infrastructure and revises the few live narrative refs that still carry the framing.

## Context

**Recon findings (2026-05-15)**:
- `ci/` directory has exactly 2 files: `pipeline.yml` (Concourse pipeline def) and `deploy.sh` (rollback helper). Both delete cleanly — no Python imports reference them.
- `Dockerfile` and `docker-compose.yml` have ZERO Concourse references. Nothing to clean there.
- `Makefile` has no `deploy` / `rollback` / `ci-*` targets. Nothing to clean there.
- `README.md` (M08 F8) has ZERO self-modification or Concourse references. M08 already moved past that framing — README reads as a product description, not a self-modifying-agent manifesto. Nothing to revise.
- `the_one/agents.md` (187 KB internal architecture reference) has ZERO self-modification or Concourse references in a quick scan. Likely also clean — verify during implementation.
- `CLAUDE.md` has ONE Concourse reference at line 56: `"mirrors the Concourse CI/prod path"`. Single-line edit.
- `SECURITY-MODEL.md` has FIVE relevant lines (recon corrected during design review): lines 45 ("Any deployment exposing..."), 96 (`THE_ONE_CONCOURSE_PASS` rotation), 99 (`"or \`ci/pipeline.yml\`."` — points at a file this leg deletes), 107 ("Multi-user / multi-tenant deployments"), 118 ("Secrets manager: would replace `THE_ONE_CONCOURSE_PASS`-style env"). The `THE_ONE_CONCOURSE_PASS` refs (96, 118) and the `ci/pipeline.yml` ref (99) are real and need edits. The "deployment" / "multi-user deployments" refs (45, 107) are general and stay (they refer to hypothetical not-this-project deployments).
- `.env` has `THE_ONE_CONCOURSE_PASS=<value>` (one line).
- `.env.example` has ZERO `THE_ONE_CONCOURSE_PASS` reference (the example never had it — it's been local-only since M06).
- `projects.md` (in mission-control) line 184 has the canonical self-modification framing: `"Self-modifying, LLM-powered personal agent. Hand-rolled agent loop, tool registry, LLM abstraction, and message protocol — no frameworks. Can edit its own source, run tests, deploy via Concourse CI, and roll back if things break."` and line 191 lists `Concourse CI` in the stack. Both need revision.
- Historical maintenance reports (`maintenance/2026-05-04.md` and `maintenance/2026-05-15.md`) reference Concourse in their findings. **Leave them intact** — they're the inspection record at the time. The 2026-05-15 report can get a one-paragraph header note acknowledging the post-write pivot.

**What stays — explicitly NOT removed**:
- Repo name `the-one` (GitHub repo)
- Python module name `the_one`
- The agent's runtime ability to use `Write` / `Edit` / shell tools (general tools, not a Concourse-coupled "self-modification feature")
- M01-M08 mission/flight/leg artifacts (historical record)
- The `concourse-local` repo itself (separate project; its existence is not affected by this leg)
- SECURITY-MODEL.md lines 45 + 107 (general "deployment" / "multi-user deployments" refs — they don't name Concourse, just discuss hypothetical posture)

## Inputs

- `the-one/ci/pipeline.yml` and `the-one/ci/deploy.sh` (to be deleted)
- `the-one/.env` (`THE_ONE_CONCOURSE_PASS` line to be removed)
- `the-one/CLAUDE.md` line 56 (single Concourse ref)
- `the-one/SECURITY-MODEL.md` lines 96, 118 (`THE_ONE_CONCOURSE_PASS` refs)
- `the-one/agents.md` — to be verified clean, no edit expected
- `the-one/README.md` — verified clean (no edit)
- `the-one/Dockerfile`, `docker-compose.yml`, `Makefile` — verified clean (no edit)
- `mission-control/projects.md` line 184 (description) and 191 (stack) for `the-one` entry
- `the-one/maintenance/2026-05-15.md` (header annotation only)

## Outputs

- `the-one/ci/` directory deleted (`ci/pipeline.yml`, `ci/deploy.sh` both gone)
- `the-one/.env` no longer contains `THE_ONE_CONCOURSE_PASS`
- `the-one/CLAUDE.md` line 56 revised to drop the Concourse-CI reference (the surrounding sentence about `make rebuild` requirements stays; just trim the parenthetical)
- `the-one/SECURITY-MODEL.md` `THE_ONE_CONCOURSE_PASS` refs revised — the section about `THE_ONE_CONCOURSE_PASS` (line 96 area) either deleted or rewritten to reference a more general "local-only secret"; "Future Work" Secrets Manager note (line 118 area) revised similarly
- `mission-control/projects.md` `the-one` entry: description rewritten to drop self-modification + Concourse framing; stack line drops Concourse CI
- `the-one/maintenance/2026-05-15.md` gets a 2-3 line header note acknowledging the mid-mission pivot (so future readers don't take the CI/CD findings at face value)
- `the-one/agents.md`, `README.md`, `Dockerfile`, `docker-compose.yml`, `Makefile` — verified clean, no edit
- Single commit on the flight branch with everything

## Acceptance Criteria

- [ ] `cd /home/cprch/projects/the-one && test ! -d ci` — `ci/` directory is gone
- [ ] `cd /home/cprch/projects/the-one && grep -i concourse .env || true` — no match
- [ ] `cd /home/cprch/projects/the-one && grep -i "concourse" CLAUDE.md README.md Dockerfile docker-compose.yml Makefile pyproject.toml 2>/dev/null || true` — no matches in any live file
- [ ] `cd /home/cprch/projects/the-one && grep -in "concourse\|THE_ONE_CONCOURSE_PASS" SECURITY-MODEL.md || true` — no `THE_ONE_CONCOURSE_PASS` matches; the word "Concourse" itself may persist only in historical/comment contexts and only with operator concurrence
- [ ] `cd /home/cprch/projects/the-one && grep -in "self.modif\|self.improv\|deploy via" CLAUDE.md README.md SECURITY-MODEL.md the_one/agents.md || true` — no live-narrative self-modification refs (historical mission docs are exempt)
- [ ] `cd /home/cprch/projects/mission-control && sed -n '/^## the-one$/,/^## /p' projects.md | grep -i "concourse\|self.modif"` — no match (the entry's description + stack lines no longer name Concourse or self-modification; `sed` extracts the whole `## the-one` section regardless of length)
- [ ] `cd /home/cprch/projects/the-one && pytest --tb=no -q --collect-only` — collection still works (no test imports `ci/` paths)
- [ ] `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — Leg 1's zero-baseline preserved (this leg's removal doesn't introduce ruff violations)
- [ ] `the-one/maintenance/2026-05-15.md` has a clearly-marked header annotation acknowledging the post-write pivot (CI/CD findings superseded)

## Verification Steps

- `cd /home/cprch/projects/the-one && ls ci/ 2>&1` — should report "No such file or directory"
- `cd /home/cprch/projects/the-one && grep -rn "concourse\|fly trigger-job\|pipeline\.yml" --include="*.py" --include="*.md" --include="*.sh" --include="Makefile" --include="*.toml" --include="*.yml" . 2>/dev/null | grep -v -E "^./missions/|^./maintenance/|^./.git/|^./.venv/"` — only allowed remaining matches should be in historical artifacts under `missions/` and `maintenance/`. Inspect each remaining hit for legitimacy.
- `cd /home/cprch/projects/the-one && grep -in "self.modif\|self.improv" the_one/agents.md` — no matches
- `cd /home/cprch/projects/the-one && pytest --tb=no -q 2>&1 | tail -10` — no NEW failures vs Leg 2's post-leg baseline
- `cd /home/cprch/projects/mission-control && cat projects.md | sed -n '/^## the-one$/,/^---$/p'` — the entry no longer reads "Self-modifying, LLM-powered personal agent..."
- (manual) Re-read the revised CLAUDE.md and SECURITY-MODEL.md to verify the edits read naturally and don't leave orphaned phrasing

## Implementation Guidance

0. **Re-verify recon at implementation time** (added per design review — Legs 1-3 may have shifted the recon surface)
   - Re-run the recon grep set BEFORE applying edits:
     - `grep -rn "concourse\|Concourse\|THE_ONE_CONCOURSE_PASS" --include="*.md" --include="*.py" --include="*.yml" --include="*.toml" --include="*.sh" --include="Makefile" the_one/ tests/ CLAUDE.md README.md SECURITY-MODEL.md Dockerfile docker-compose.yml Makefile pyproject.toml .env.example 2>/dev/null`
   - Confirm `.env` is gitignored: `grep -E "^\.env$|^\.env\b" .gitignore` — must match
   - Confirm no in-flight Concourse builds: if `fly -t local status` succeeds, `fly -t local builds -p the-one --count 5` and confirm no `started` builds before proceeding. (If `fly` auth is still broken — as it was at Leg 1 — skip this; broken auth implies no live builds.)
   - If new Concourse refs surfaced beyond the leg's stated edit set, surface in flight log Decisions before proceeding

1. **Delete `ci/` directory**
   - `cd /home/cprch/projects/the-one && git rm -r ci/`
   - This removes `pipeline.yml` and `deploy.sh` in one go; tracked by git so the deletion is in the commit

2. **Remove `THE_ONE_CONCOURSE_PASS` from `.env`**
   - `.env` is gitignored (verified in step 0) — this is a local-file edit only, no commit impact
   - Edit `.env` to remove the `THE_ONE_CONCOURSE_PASS=...` line
   - Do NOT log the credential value in flight-log.md or commit messages
   - Verify `.env.example` does not have the line (it doesn't, per recon) — no edit needed

3. **Edit `CLAUDE.md` line 56 area**
   - Read the section around line 56 (the `## When to rebuild` or similar section about `make rebuild`)
   - The current text is: `"**When \`make rebuild\` is required**: any change under \`the_one/\` — JS, CSS, HTML, Python. The Dockerfile copies these at build time; live-reload is intentionally NOT enabled (mirrors the Concourse CI/prod path)."`
   - Revise to drop the Concourse parenthetical. New text: `"**When \`make rebuild\` is required**: any change under \`the_one/\` — JS, CSS, HTML, Python. The Dockerfile copies these at build time; live-reload is intentionally NOT enabled so dev exercises the same image-build path as a real deploy."`
   - Verify no other Concourse refs in CLAUDE.md after the edit: `grep -in "concourse" CLAUDE.md` returns empty

4. **Edit `SECURITY-MODEL.md`** — revise the Concourse-bearing lines
   - **4a. Line 96 area (Secrets section)**: the bullet about `THE_ONE_CONCOURSE_PASS` rotation can be DELETED outright. The surrounding bullets about `.env` and encryption-at-rest stay.
   - **4b. Line 99 area** (recon correction added during design review): the line reads `"or \`ci/pipeline.yml\`."` as part of a bullet listing files no secrets land in (`.env.example`, `Dockerfile`, `docker-compose.yml`, `ci/pipeline.yml`). Remove the `ci/pipeline.yml` enumeration item; the surrounding bullet stays valid (other files still have no secrets in them).
   - **4c. Line 118 area (Future Work — Secrets manager)**: rewrite to a generic example. Change `"would replace \`THE_ONE_CONCOURSE_PASS\`-style env"` to `"would replace local-only `.env`-style secret storage"` (or similar generic wording). The intent of the Future Work bullet (replacing env-file secrets with a vault) stays meaningful even without Concourse.
   - Verify line 45 and 107 don't need edits — they reference "deployment" generically, not Concourse specifically. Confirm during read.

5. **Verify `the_one/agents.md` is clean**
   - `grep -inE "self.modif|self.improv|concourse|deploy.*pipeline|rollback.*image" the_one/agents.md`
   - Expected: empty. If matches surface, surface them in flight log and decide per-match whether to revise or accept (some matches may be in code-tool documentation about the agent's runtime `Edit` tool — those are fine; the runtime ability to edit files is not "self-modification framing" in the marketing sense)

6. **Update `mission-control/projects.md`** — ONLY the `## the-one` entry (NOT the `## concourse-local` entry directly below it at lines ~195-204; that's a separate project)
   - Read lines around `## the-one` (around line 182)
   - Current description (line 184): `"Self-modifying, LLM-powered personal agent. Hand-rolled agent loop, tool registry, LLM abstraction, and message protocol — no frameworks. Can edit its own source, run tests, deploy via Concourse CI, and roll back if things break."`
   - Replace with something product-shaped (matching the README's voice). Suggested: `"LLM-powered personal agent platform. Hand-rolled agent loop, tool registry, LLM abstraction, and message protocol — no frameworks. Talk to agents in Chat, configure them in Studio, manage providers and built-in tools in Administration."`
   - Stack line (191): drop `Concourse CI`. New stack: `Python, FastAPI, WebSocket, Docker`

7. **Annotate `the-one/maintenance/2026-05-15.md`** with a header note
   - At the top of the report (after the date/triggered-by/assessment header block), add a new section titled `## Note: Post-Report Pivot (2026-05-15)`
   - Content (suggested): `"This report was written 2026-05-15 BEFORE the operator decided (same day, during M09 Flight 1 execution) to remove Concourse CI infrastructure and self-modification framing from the project. As a result, the Category 8 CI/CD findings (C1 Concourse 8.1 upgrade cadence, C2 pip-audit in CI, C3 cp -r waste, C4 git-revision binding, C5 auto-rollback selftest, C6 AIAT gating, C7 password rotation cadence) and Finding 1.4 (pip-audit in CI) are superseded — the underlying infrastructure is removed in F1 Leg 4. The lint/format gate-evasion concern (Finding 8.1) is also moot, though the lint+format zero-baseline restoration in F1 Leg 1 still happens (it has value independent of any CI substrate). Other findings (lint+format, asgi-lifespan, sandbox skip predicate, OAuth XSS, _clean_npx allowlist, doc carry-forwards, accessibility) are unaffected by the pivot and proceed as planned."`
   - This is the maintenance report's record of the strategic shift — it stays a snapshot of what was found, but with the right caveat

8. **Verify nothing in the source tree imports or shells out to anything Concourse-coupled**
   - `cd /home/cprch/projects/the-one && grep -rn "concourse\|fly trigger\|deploy\.sh" --include="*.py" the_one/ tests/ 2>/dev/null` — should be empty
   - `cd /home/cprch/projects/the-one && grep -rn "ci/pipeline\|ci/deploy" --include="*.py" the_one/ tests/ 2>/dev/null` — should be empty
   - If anything surfaces, investigate per-finding; either dead code (delete) or genuinely needs revision

9. **Run the test suite to confirm nothing breaks from the removals**
   - `cd /home/cprch/projects/the-one && pytest --tb=no -q --collect-only | tail -5` — collection still works
   - `docker exec the-one pytest -x --timeout 30 tests/ 2>&1 | tail -20` — broad pytest at Leg 2's post-leg baseline (no NEW failures)

10. **Commit**
    - In `the-one`: enumerate the paths explicitly (NOT `git add -A`, per design-review fix — `-A` could sweep in scratch files):
      ```
      cd /home/cprch/projects/the-one
      git add CLAUDE.md SECURITY-MODEL.md maintenance/2026-05-15.md
      # ci/ is already staged from the `git rm -r ci/` in step 1
      git status  # inspect — should be clean except for the intended changes
      ```
    - Commit with a heredoc (NOT `-m "...\n\n..."` — `-m` does not interpret escape sequences):
      ```bash
      git commit -m "$(cat <<'EOF'
      flight/01: remove Concourse CI infrastructure + self-modification framing

      Mission: 09
      EOF
      )"
      ```
    - Do NOT push the the-one flight branch — the operator decides push cadence at flight close.
    - In `mission-control` (SEPARATE REPO with its own commit cadence): stage the `projects.md` change but **DO NOT auto-commit or auto-push** unless the operator explicitly says to. Surface the staged change in the flight log so the operator can commit at their preferred time:
      ```
      cd /home/cprch/projects/mission-control
      git add projects.md
      git status  # show operator the staged change
      ```
      Operator commit message (when they're ready): `docs(projects): drop Concourse/self-modification framing from the-one entry`
    - Per crew protocol: signal `[HANDOFF:review-needed]` at leg end, NOT `[COMPLETE:leg]` (flight uses end-of-flight commit pattern for the the-one repo; mission-control commits are independent of that workflow)
    - Update leg status from `in-flight` to `landed`
    - Update flight-log.md with a Leg Progress entry

## Edge Cases

- **`the_one/agents.md` actually has self-modification refs**: if recon was wrong and the file references the framing, scope this leg to also revise agents.md. agents.md is 187 KB — a wholesale rewrite is out of scope; aim for targeted edits at the few sites that name self-modification or Concourse.
- **A test imports from `ci/`**: surface the test, decide whether to delete the test (if Concourse-specific) or de-couple it (if testing something else that happened to reference `ci/`).
- **`THE_ONE_CONCOURSE_PASS` is referenced from Python code**: `grep -rn "THE_ONE_CONCOURSE_PASS" the_one/` — if anything turns up (it shouldn't, this env var is just for `fly login`), surface and decide.
- **mission-control commit timing**: the operator may not want to commit `projects.md` until after the maintenance flight is fully landed. If so, stage the change locally; the operator commits on their own cadence. Don't push the mission-control change.
- **The maintenance report annotation conflicts with the operator's preferred phrasing**: surface the suggested wording in the flight log Decisions section and let the operator confirm before the commit goes through.

## Files Affected

**Deleted**:
- `the-one/ci/pipeline.yml`
- `the-one/ci/deploy.sh`
- `the-one/ci/` (directory, removed when contents are gone)

**Modified** (the-one repo):
- `the-one/.env` (local-only, gitignored — no commit; just remove the line)
- `the-one/CLAUDE.md` (one parenthetical removed at line ~56)
- `the-one/SECURITY-MODEL.md` (2-3 lines revised around `THE_ONE_CONCOURSE_PASS` refs)
- `the-one/maintenance/2026-05-15.md` (one header annotation paragraph added)

**Modified** (mission-control repo — separate commit):
- `mission-control/projects.md` (the-one entry description + stack lines)

**NOT modified** (verified clean during recon):
- `the-one/README.md`
- `the-one/the_one/agents.md` (re-verify during step 5)
- `the-one/Dockerfile`
- `the-one/docker-compose.yml`
- `the-one/Makefile`
- `the-one/.env.example`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest at Leg 2's post-leg baseline; ruff baselines preserved from Leg 1)
- [ ] No stranded Concourse references in live narrative docs
- [ ] Mission-control `projects.md` change staged (and either committed-in-place or surfaced for operator-cadenced commit)
- [ ] Maintenance report header annotation lands
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Commit the cleanup (the-one repo) and the projects.md change (mission-control repo, separately)
