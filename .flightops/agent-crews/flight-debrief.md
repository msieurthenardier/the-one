# Flight Debrief — Project Crew

Crew definitions for post-flight analysis. The Flight Director interviews the
human and project-side agents to capture both execution and design perspectives.

## Crew

### Developer
- **Context**: project root (current working directory)
- **Model**: Sonnet
- **Role**: Provides developer perspective on flight execution. Reviews what was
  built, identifies technical debt introduced, evaluates implementation quality,
  and surfaces issues that flight logs may not capture.
- **Actions**: debrief-interview

### Architect
- **Context**: project root (current working directory)
- **Model**: Sonnet
- **Role**: Closes the design feedback loop. Evaluates whether the design decisions
  made during flight planning held up in practice. Reviews architectural impact of
  what was built and whether the approach should be adjusted for future flights.
- **Actions**: debrief-design-review

## Interaction Protocol

### Developer Interview
1. Flight Director loads flight context (mission, flight, legs, log, actual code)
2. Flight Director decides where test metrics come from (see "Test metrics: reuse
   the flight's gate" below): the flight's gate, supplied in the brief, or a fresh
   run the Developer is told to make
3. Flight Director spawns **Developer** with that brief to review implementation
   and provide feedback
4. Developer examines code changes, test coverage, patterns used, debt introduced
5. Developer provides structured debrief input

### Architect Interview
1. Flight Director spawns **Architect** to review whether design decisions held up
2. Architect compares flight-design spec against actual implementation
3. Architect evaluates architectural impact and provides feedback for future flights

### Human Interview
1. Flight Director interviews human with targeted questions based on flight log
2. Keep lightweight — 2-3 questions max

### Synthesis
1. Flight Director synthesizes Developer input + Architect input + human input + document analysis
2. Generates debrief artifact

### Test metrics: reuse the flight's gate

This narrows the flight-debrief skill's "run the full suite once" instruction for
this project (Mission 33 Flight 2 debrief, Methodology Observation 1). Before
briefing the Developer, the Flight Director decides:

- **Reuse** the flight's last full gate (a unit run plus a quiet-host
  `--parallel 3` browser run, both on the same commit) when
  `git diff <gate commit>..HEAD` touches nothing under `the_one/`, `tests/` or
  `scripts/` except the lane-budget table in `scripts/run-tests.sh`. Record the
  gate's commit, its `PARALLEL_RESULT` line, the per-lane times and the unit
  counts, and compare those against prior debriefs.
- **Run fresh** otherwise, including when the gate ran on a loaded host or the
  branch was rebased onto a moved `main`.
- **Either way,** say which run each number came from.

## Template Variables

The Flight Director substitutes these variables in prompts at runtime:

| Variable | Description |
|----------|-------------|
| `{project-slug}` | Project identifier — the repository directory name, or the name from the git remote |
| `{flight-number}` | Current flight number |
| `{flight-artifact-path}` | Path to the flight artifact file |

## Prompts

### Developer: Debrief Interview

```
role: developer
phase: flight-debrief
project: {project-slug}
flight: {flight-number}
action: debrief-interview

Review the implementation produced during this flight. Examine the code changes,
test coverage, and architectural decisions made.

Provide structured input for the debrief:

**Implementation Quality**:
- Does the code follow project conventions?
- Are there patterns that should be documented?
- What technical debt was introduced?

**Leg Spec Accuracy**:
- Were leg specs clear and sufficient for implementation?
- What was missing or misleading?
- Were acceptance criteria verifiable?

**Testing Assessment**:
- Is test coverage adequate?
- Are there untested edge cases?
- Do tests meaningfully validate behavior?

**Test Metrics**:
- Report the metrics the Flight Director supplies from the flight's gate (or from
  your own fresh run when told to run one): gate commit, `PARALLEL_RESULT` line,
  per-lane times, unit counts. Compare them with prior debriefs and name the
  source of each number.

**Recommendations**:
- What should future flights in this area account for?
- Are there refactoring opportunities?
- What documentation is missing?
```

### Architect: Debrief Design Review

```
role: architect
phase: flight-debrief
project: {project-slug}
flight: {flight-number}
action: debrief-design-review

Read the flight artifact at {flight-artifact-path}. Compare the design decisions,
technical approach, and leg breakdown that were planned against what was actually
implemented.

Provide structured input for the debrief:

**Design Decisions Assessment**:
- Which design decisions held up well in practice?
- Which decisions had to be revised during implementation? Why?
- Were there decisions that should have been made differently?

**Architectural Impact**:
- Did the implementation maintain or improve the system's architecture?
- Were there unplanned structural changes? Are they sound?
- Did the approach create any architectural debt?

**Flight Design Accuracy**:
- Was the technical approach feasible as specified?
- Were prerequisites correctly identified?
- Was the leg breakdown appropriate for the actual work?

**Forward-Looking**:
- What should future flight designs in this area account for?
- Are there architectural patterns that emerged worth standardizing?
- What design assumptions should be revisited?
```
