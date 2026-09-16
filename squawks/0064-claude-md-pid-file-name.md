# Squawk 0064: `CLAUDE.md` names the wrong `make up` PID/log files

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-16

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

Fixed `CLAUDE.md`'s "Local dev (host-native)" section (previously line
44, now expanded): it names the port-scoped PID/log files
(`.the-one.$(THE_ONE_PORT).pid` / `.the-one.$(THE_ONE_PORT).log`, e.g.
`.the-one.8484.pid` / `.the-one.8484.log` for the default port) instead
of the stale unscoped `.the-one.pid` / `.the-one.log`, and adds a
sentence that a dev instance on another port keeps its own PID/log
files — which is what makes `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch>
make down` safe against the default instance. Also fixed the `make logs`
comment in the same section's command block (was `.the-one.log`, now
`.the-one.$(THE_ONE_PORT).log, e.g. .the-one.8484.log`).

Checked the rest of `CLAUDE.md`, `README.md`, and `docs/*.md` for the
same stale names (`grep -rn "\.the-one\.pid\|\.the-one\.log"`) — no
other mentions found; only the two spots above needed fixing. No
Makefile changes made (out of scope; it already uses the correct
port-scoped scheme).

## Verification

`grep -n "\.the-one\.pid\|\.the-one\.log" CLAUDE.md` → no matches (exit
1), confirming the stale unscoped names are gone; the section now names
`.the-one.$(THE_ONE_PORT).pid` / `.the-one.$(THE_ONE_PORT).log` and the
per-port isolation sentence.

`git check-ignore -v .the-one.8484.pid .the-one.8484.log` confirms
`.gitignore`'s existing glob patterns (`.the-one*.pid` line 40,
`.the-one*.log` line 42) already cover the port-scoped names — no
`.gitignore` change needed.

## Sign-Off
**Reviewer**: Sonnet (batch review, squawk turnaround 2026-09-16; Sonnet tier — 0063 touches the route reading operator-registered paths)
**Verdict**: confirmed
**Commit**: (recorded in the follow-up commit)
