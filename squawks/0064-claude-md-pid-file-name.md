# Squawk 0064: `CLAUDE.md` names the wrong `make up` PID/log files

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

## Report

`CLAUDE.md`'s "Local dev (host-native)" section says `make up` "writes
`.the-one.pid` + `.the-one.log`". The Makefile scopes both by port —
`.the-one.$(THE_ONE_PORT).pid` / `.the-one.$(THE_ONE_PORT).log` (so the
default instance writes `.the-one.8484.pid`). Surfaced twice during Flight
3 (design review, then the behavior test's live-kill variant). One-line
doc fix; also worth a sentence that a dev instance on another port keeps
its own PID file, which is what makes `THE_ONE_PORT=8485 make down` safe.

## Evidence

- `CLAUDE.md:44` — "(writes `.the-one.pid` + `.the-one.log`, both gitignored)"
- `Makefile:37-38` — `THE_ONE_PIDFILE ?= .the-one.$(THE_ONE_PORT).pid`, `THE_ONE_LOGFILE ?= .the-one.$(THE_ONE_PORT).log`

## Corrective Action
*(written at completion)*

## Verification
`grep -n "\.the-one\.pid" CLAUDE.md` → 0; the section names the port-scoped files and the per-port isolation.

## Sign-Off
*(written at completion)*
