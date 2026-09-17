# Squawk 0068: Architect prompt: pin environment-derived library defaults before probing; per-leg external-session re-verify

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-17

## Report

Flight 4's planning probes ran `watchfiles` with its defaults and measured
the polling backend on this WSL host without knowing it (the library picks
a backend from the kernel release and from env vars); three review cycles
were spent unwinding it. Separately, the Concourse token expired between
planning and Leg 4 and was caught reactively. Both belong in the flight
design review as standing checks: `.flightops/agent-crews/flight-design.md`'s
"Review Flight Design" prompt should ask the Architect to (a) check every
planning probe against the library's environment- or platform-derived
defaults and require them pinned, and (b) require that a prerequisite
depending on an external session (Concourse login, a worker, a token) names
a per-leg re-verify rather than a one-time planning check.

## Evidence

- `.flightops/agent-crews/flight-design.md:38` — `### Architect: Review Flight Design`, the `Evaluate:` list (six items, none about environment-derived defaults or session TTLs)
- Flight 4 flight log, "Correction after Architect cycle 1" and probes P13–P18; Flight Director Notes "Leg 3 landed" (Concourse re-login)
- Flight 4 debrief, Recommendations 1 and 6

## Corrective Action

Added two items to the `Evaluate:` list in `.flightops/agent-crews/flight-design.md`'s
"Architect: Review Flight Design" prompt, as items 7 and 8 after the existing six
(unrenumbered, unreworded):

- **7. Environment-derived defaults** — asks the Architect, for each planning premise
  probe against a library or tool, whether its behavior depends on something the
  environment or platform supplies (kernel release, env var, OS check), and if so
  whether the spec shows that default pinned explicitly before the probe's result is
  trusted — rather than measured under whatever backend the probing host happened to
  select. Phrased generally (any environment-sensitive dependency, not `watchfiles`
  specifically) per the squawk's instruction, since the failure mode — a library
  silently picking a backend from the host — applies to any such dependency.
- **8. External-session prerequisites** — asks the Architect, for each prerequisite
  that depends on a session external to the planning pass (a login, a worker, a
  token), whether the spec calls for a per-leg re-verify at implementation time
  rather than relying on a one-time planning-time check. Phrased generally (any
  external session, not Concourse specifically) for the same reason.

Both items match the density and question-form voice of the existing six ("are they
accurate? Is anything missing...", "does the approach maintain...") and were placed
after item 6 (Architecture) rather than folded into item 2 (Prerequisites), since
item 7 is about probe methodology rather than prerequisites and both are general
standing checks distinct enough to warrant their own numbered items, matching the
squawk's "numbered items 7 and 8" framing.

## Verification

- `.flightops/agent-crews/flight-design.md` still has its `## Crew`,
  `## Interaction Protocol`, and `## Prompts` sections (confirmed via
  `grep -n '^## '`).
- The prompt's fenced code block is still well-formed: exactly 2 fence markers
  (opening/closing), confirmed via `awk '/^```/{c++} END{print c}'`.
- Items 1-6 in the `Evaluate:` list are byte-identical to before the edit (confirmed
  via `git diff`, which shows only two added lines, no modifications to existing
  lines).
- The `Provide structured output:` contract block (Overall assessment / Issues /
  Suggestions / Questions) is unchanged (confirmed via `git diff`, no changes below
  the inserted lines).
- No design decisions, shared-interface, or schema changes were involved — a
  two-item addition to one project-modifiable prompt file plus this artifact's own
  status/sections, matching the squawk gate.

## Sign-Off

**Reviewer**: batch Reviewer agent (Haiku tier — the diff is documentation, crew prompts and a test comment; no security-sensitive surface, per `.flightops/agent-crews/leg-execution.md`)
**Verdict**: confirmed
**Commit**: (recorded in the follow-up commit on `squawk/turnaround-2026-09-17`)

## Disposition

*(only for deferred or escalated squawks)*
