# Leg Execution — Project Crew

Crew definitions and interaction protocol for implementing flight legs.
The Flight Director (Mission Control) orchestrates this phase using the
/mission-control:agentic-workflow skill.

## Crew

### Developer
- **Context**: project root (current working directory)
- **Model**: Sonnet
- **Role**: Implements code changes. Also performs design reviews against real
  codebase to validate leg specs before implementation.
- **Actions**: implement, fix-review-issues, commit, review-leg-design

### Reviewer
- **Context**: project root (current working directory)
- **Model**: Sonnet when the diff touches a security-sensitive surface (credentials, key
  material, the credential gate or middleware exemptions, sandboxing, self-configuration
  identity); Haiku otherwise. The Flight Director records which tier applied in the flight
  log (or squawk sign-off).
- **Role**: Reviews code changes for quality, correctness, and criteria compliance.
  Has NO knowledge of Developer's reasoning — only sees resulting changes.
- **Actions**: code review

### Accessibility Reviewer (required for UI flights)
- **Context**: project root (current working directory)
- **Model**: Sonnet
- **Role**: Reviews UI changes for accessibility compliance. Evaluates against
  WCAG 2.1 AA standards, screen reader compatibility, keyboard navigation,
  color contrast, ARIA usage, and semantic HTML. Always spawned when any leg
  (or a HAT feature promoted through the fix-vs-feature gate) changes a
  user-facing interface; skipped only for flights with no UI change. (Mission 31:
  in Flight 1 it found the only blocking issue, and a Flight 3 HAT feature that
  skipped it shipped without an a11y pass.)
- **Actions**: review-accessibility

## Separation Rules

- Developer and Reviewer load the target project's CLAUDE.md and conventions
- Reviewer has NO knowledge of Developer's reasoning — only resulting changes
- Each agent instance gets fresh context (no carryover between legs)

**Note:** Handoff signals (`[HANDOFF:review-needed]`, `[HANDOFF:confirmed]`, `[BLOCKED:reason]`, `[LAND:leg]`) are defined by the Flight Control methodology in the agentic-workflow skill, not in this file. Do not modify signal names here — they must match what the Flight Director expects.

## Interaction Protocol

### Design Review
1. Flight Director spawns **Developer** for design review
2. Developer reviews leg against codebase, provides structured assessment
3. Flight Director incorporates feedback
4. Max 2 review cycles — escalate to human if unresolved

### Implementation
1. Flight Director spawns **Developer** to implement
2. Developer implements to acceptance criteria, marks the leg `landed`, updates flight log
3. Developer signals [LAND:leg]; the Flight Director proceeds to the next leg

### Code Review (once per flight)
1. After the last autonomous leg lands, Flight Director spawns **Reviewer** to
   evaluate all uncommitted changes from every leg
2. If any leg (or HAT feature) involves UI changes, spawn the **Accessibility
   Reviewer** in parallel with the Reviewer
3. If issues: Flight Director spawns new **Developer** to fix
4. Loop until all reviewers signal [HANDOFF:confirmed] — max 3 cycles

### Commit (once per flight)
1. Flight Director spawns **Developer** to commit the whole flight
2. Developer commits code + artifacts in one commit, reports the commit ref

### Outward steps (workflow dispatch, tag push, release)
Project rule (squawk 0268). This is project configuration, not a plugin file; if
`/mission-control:init-project` ever resets this file, re-apply it.
1. An outward step runs as its own command, never chained after a commit or a push
   with `;` or `&&` (a failed commit must not still dispatch on the old head).
2. Before it runs, check the pushed head equals the intended commit
   (`git rev-parse HEAD origin/<branch>`).
3. Record its run id and head SHA right after it runs.

### Batch mode (default for UI migration flights)
The operator's standing preference (Mission 31, Flights 4-6): the autonomous legs
run in planned batches with a checkpoint commit at each batch end, and one HAT
closes the flight.
1. Each leg runs its own lanes plus the unit-tier static guards before signalling.
2. At each batch end, grep `tests/`, `scripts/`, `docs/` and `tests/behavior/` for every
   deleted selector, class, testid and moved path, and for exact pins of any response
   shape the batch changed, then run the owning lane of each hit.
3. At each batch end, check every touched lane's wall time against its budget.
4. Lane budget readings count only from a quiet-host `--parallel 3` run (CLAUDE.md
   "Quiet-host rule"), never from a solo `--lane` run or a loaded host.

## Template Variables

The Flight Director substitutes these variables in prompts at runtime:

| Variable | Description | Available In |
|----------|-------------|-------------|
| `{project-slug}` | Project identifier — the repository directory name, or the name from the git remote | All prompts |
| `{flight-number}` | Current flight number | All prompts |
| `{leg-number}` | Current leg number | review-leg-design, implement |
| `{leg-artifact-path}` | Path to the leg artifact file | review-leg-design |
| `{working-directory}` | Resolved working directory for the agent (project root for branch strategy, worktree path for worktree strategy) | All prompts |
| `{reviewer-issues}` | Full text of reviewer feedback (dynamic) | fix-review-issues |

## Prompts

### Developer: Review Leg Design

```
role: developer
phase: leg-design-review
project: {project-slug}
flight: {flight-number}
leg: {leg-number}
action: review-leg-design

Read the leg artifact at {leg-artifact-path}. Cross-reference its acceptance
criteria, implementation guidance, and file references against the actual codebase.

**Read in Developer order first.** Before evaluating rationale in Context, read
the numbered Acceptance Criteria and the Implementation Guidance steps top to
bottom, implementing each mentally as you go — the order a Developer would
encounter them. This is what surfaces a criterion or step that a later one
silently superseded but whose stale text is still sitting upstream: it reads
fine in isolation and is invisible to a review that jumps straight to rationale.

Evaluate:
1. Acceptance criteria — specific, verifiable, complete?
2. Implementation guidance — complete and correctly ordered?
3. Edge cases — missing scenarios?
4. Codebase state — account for working tree, existing tooling, uncommitted changes?
5. File/line references — accurate against current codebase?
6. Dependencies — prerequisite legs completed? Outputs available?

Provide structured output:

**Overall assessment**: approve | approve with changes | needs rework

**Issues** (ranked by severity):
- [high/medium/low] Description — recommended fix

**Suggestions** (non-blocking):
- Description

**Questions** (for the designer):
- Question
```

### Developer: Implement

```
role: developer
phase: leg-implementation
project: {project-slug}
flight: {flight-number}
leg: {leg-number}
action: implement

Read leg artifact. Update leg status to in-flight. Implement to acceptance criteria.

Run tests host-native via the repo venv: `PYTHON=.venv/bin/python bash
scripts/run-tests.sh <files> -x --timeout 30` (or `make test-unit` for the whole
unit suite). Always pass `-x --timeout 30` (or higher per-test timeout) for
autonomous runs: `-x` exits on first failure before pytest-asyncio's loop
teardown can wedge on orphaned tasks; `--timeout` prevents single-test hangs
from eating the whole budget. Scope iterations to the test file(s) you're
changing; run the broader suite once at leg-end.

A bare browser test file path (`tests/browser/<file>`) needs `-m browser` passed
through to `scripts/run-tests.sh`; without it the `addopts` marker filter deselects
every test and nothing is verified. On this WSL host every browser run and gate also
needs `THE_ONE_TEST_NETNS=1` (Mission 28 finding: without it the gate shows scattered
`wait_settled` timeouts).

Gate-flake triage: re-run any failure in isolation; a known squawk flake that passes
in isolation is recorded and accepted; anything else is a regression until an
isolated re-run clears it.

A change under `the_one/interfaces/web/static/` must also run the static JS/CSS
guards — `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and
`tests/test_design_tokens_a11y.py` — not only a browser lane (squawk 0106).

Process hygiene: kill only PIDs or PGIDs you recorded yourself (or the `.pgids`
files `scripts/run-tests.sh --parallel` writes), never by name or pattern —
no `pkill`, `killall` or `kill $(pgrep ...)`. A pattern can hit the operator's own
processes (a `make up` server, another session's tests) (squawk 0160).

When a change renames or deletes a selector, class, testid, symbol or path, or adds
or removes fields in a response shape, grep the tests (every lane, plus `scripts/` and
`tests/behavior/`) for its pins, including exact-dict assertions on that shape, and
update them in this leg.

Shared working tree: other crew and the Flight Director may have uncommitted edits
in this tree. Never run `git stash`, `git checkout -- <path>`, `git restore`,
`git reset` or `git clean`; to compare against the base, use `git diff` or
`git show <ref>:<path>`.

Never write or run a helper script (Python, sed, shell redirection, a heredoc or
the like) that writes a source or test file; edit source and test files only
through the edit tool (squawk 0286). A project `PreToolUse` hook
(`.claude/settings.json` -> `.claude/hooks/block_shell_writes.py`, squawk 0292) now refuses
such shell writes into `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/` and `evals/`
with exit 2; it fails open on anything it cannot parse. When a new test must be shown to fail without
its fix (falsified), remove the fix by editing, run the test, then put the fix back
by editing; never restore a whole file or put back a backup copy (squawk 0284). A
file that had to be rebuilt is reported with a diff against HEAD
(`git diff HEAD -- <path>`). Where the leg asks for falsification, report for each
new test whether it was falsified (yes or no).

If a test hangs, isolate and fix it — do not paper over with `xfail` or skips
unless the leg artifact explicitly authorizes that. Update flight log with
outcomes. Propagate changes to artifacts (flight, mission, leg), CLAUDE.md,
README, and other project documentation as needed. When done, update leg status
to landed and report what you implemented and how you verified it. Do not commit.
Signal [LAND:leg].
```

### Reviewer: Review

```
role: reviewer
phase: flight-review
project: {project-slug}
flight: {flight-number}
action: review

Review all changes on the flight branch relative to its base — they span every leg
implemented in this flight. Evaluate against:
1. Acceptance criteria — are all criteria of every landed leg met?
2. Code quality — style, clarity, maintainability
3. Correctness — edge cases, error handling, security
4. Tests — coverage, meaningful assertions, no regressions. If the diff touches
   `the_one/interfaces/web/static/`, confirm the static JS/CSS guards
   (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`,
   `tests/test_design_tokens_a11y.py`) were run and pass (squawk 0106).
5. Artifacts — flight log updated for every leg, leg statuses correct

When running browser tests yourself, pass `-m browser` with a bare browser file
path to `scripts/run-tests.sh` (else every test is deselected and nothing is
verified), and on this WSL host set `THE_ONE_TEST_NETNS=1` for every browser run and
gate (Mission 28 finding).

Signal [HANDOFF:confirmed] if all changes are satisfactory.
If issues found, list them with severity (blocking/non-blocking) and specific
file:line references.
```

### Accessibility Reviewer: Review Accessibility

```
role: accessibility-reviewer
phase: flight-review
project: {project-slug}
flight: {flight-number}
action: review-accessibility

Review all UI changes on the flight branch relative to its base for accessibility
compliance.

Evaluate against:
1. WCAG 2.1 AA — do changes meet Level AA success criteria?
2. Semantic HTML — proper heading hierarchy, landmark regions, form labels?
3. Keyboard navigation — all interactive elements reachable and operable?
4. Screen readers — ARIA attributes correct and meaningful? Live regions?
5. Color and contrast — minimum 4.5:1 for text, 3:1 for large text/UI?
6. Focus management — visible focus indicators, logical tab order?

Signal [HANDOFF:confirmed] if all changes are accessible.
If issues found, list them with severity (blocking/non-blocking), WCAG criterion
reference, and specific file:line references.
```

### Developer: Fix Review Issues

```
role: developer
phase: flight-review
project: {project-slug}
flight: {flight-number}
action: fix-review-issues

Address the following review feedback:
{reviewer-issues}

Process hygiene: kill only PIDs or PGIDs you recorded yourself (or the `.pgids`
files `scripts/run-tests.sh --parallel` writes), never by name or pattern —
no `pkill`, `killall` or `kill $(pgrep ...)`. A pattern can hit the operator's own
processes (a `make up` server, another session's tests) (squawk 0160).

Shared working tree: other crew and the Flight Director may have uncommitted edits
in this tree. Never run `git stash`, `git checkout -- <path>`, `git restore`,
`git reset` or `git clean`; to compare against the base, use `git diff` or
`git show <ref>:<path>`.

Fix all blocking issues. Non-blocking issues: fix if straightforward, otherwise
note as accepted. When a new test must be shown to fail without its fix (falsified),
remove the fix by editing, run the test and see it fail, then put the fix back by
editing; never restore a whole file or put back a backup copy (squawk 0284).
Never write or run a helper script (Python, sed, shell redirection, a heredoc or
the like) that writes a source or test file; edit source and test files only
through the edit tool (squawk 0286). A file that had to be rebuilt is reported
with a diff against HEAD (`git diff HEAD -- <path>`). For each new test, report
whether it was falsified (yes or no).
Before signalling, run `THE_ONE_TEST_NETNS=1 make test-unit` and
the owning browser lane of every file you touched, and report both results. This
applies to every fix pass: review fixes, HAT fixes and post-gate changes (Mission 31:
in Flights 4, 5 and 6 an untested late change failed the next gate). Signal
[HANDOFF:review-needed] when fixes are complete.
```

### Developer: Commit

```
role: developer
phase: flight-commit
project: {project-slug}
flight: {flight-number}
action: commit

Review has passed for the whole flight. Commit all uncommitted changes (code +
artifacts) in a single commit, following the Git Conventions in .flightops/ARTIFACTS.md.
Include the artifact updates the Flight Director listed when spawning you.
Report the commit ref.
```
