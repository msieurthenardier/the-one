# Squawk 0068: Architect prompt: pin environment-derived library defaults before probing; per-leg external-session re-verify

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

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

*(written at completion)*

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition

*(only for deferred or escalated squawks)*
