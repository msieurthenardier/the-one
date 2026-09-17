# Flight Design — Project Crew

Crew definitions for flight specification. The Flight Director designs the
technical spec and uses project-side agents to validate against the real codebase.

## Crew

### Architect
- **Context**: project root (current working directory)
- **Model**: Opus
- **Role**: Reviews flight specs for technical soundness. Validates design
  decisions, prerequisites, technical approach, and leg breakdown against
  architecture best practices and actual codebase state. Ensures the flight
  is buildable and well-structured.
- **Actions**: review-flight-design

## Interaction Protocol

### Design Review
1. Flight Director creates flight spec and interviews human
2. Flight Director spawns **Architect** to review against codebase
3. Architect evaluates design decisions, prerequisites, approach, leg breakdown
4. Flight Director incorporates feedback
5. Max 2 review cycles — escalate to human if unresolved

## Template Variables

The Flight Director substitutes these variables in prompts at runtime:

| Variable | Description |
|----------|-------------|
| `{project-slug}` | Project identifier — the repository directory name, or the name from the git remote |
| `{flight-number}` | Current flight number |
| `{flight-artifact-path}` | Path to the flight artifact file |

## Prompts

### Architect: Review Flight Design

```
role: architect
phase: flight-design-review
project: {project-slug}
flight: {flight-number}
action: review-flight-design

Read the flight artifact at {flight-artifact-path}. Cross-reference its design
decisions, prerequisites, technical approach, and leg breakdown against the actual
codebase state and architecture best practices.

Evaluate:
1. Design decisions — are they sound given the real codebase and architecture?
2. Prerequisites — are they accurate? Is anything missing or already done?
3. Technical approach — is it feasible? Does it follow existing patterns?
4. Leg breakdown — are legs well-scoped, properly ordered, with correct dependencies?
5. Codebase state — does the spec account for current working tree, existing tooling,
   and conventions that might affect implementation?
6. Architecture — does the approach maintain or improve system structure?
7. Environment-derived defaults — for each planning premise probe against a library or tool, does its behavior depend on something the environment or platform supplies (a kernel release, an env var, an OS check)? If so, does the spec show that default pinned explicitly before the probe's result is trusted, rather than measured under whatever backend the probing host happened to select?
8. External-session prerequisites — for each prerequisite that depends on a session external to this planning pass (a login, a worker, a token), does the spec call for a per-leg re-verify at implementation time rather than relying on a one-time check made during planning?

Provide structured output:

**Overall assessment**: approve | approve with changes | needs rework

**Issues** (ranked by severity):
- [high/medium/low] Description — recommended fix

**Suggestions** (non-blocking improvements):
- Description

**Questions** (for the designer to clarify):
- Question
```
