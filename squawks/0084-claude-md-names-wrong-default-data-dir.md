# Squawk 0084: CLAUDE.md's safety rule names a default data directory that does not exist

**Status**: open
**Type**: defect
**Severity**: grounding
**Reported**: 2026-09-18
**Completed**: —

## Report

`CLAUDE.md:317`, inside the **"SAFETY RULE — never target the operator's
production instance"** section, calls the operator's default data directory
**`~/.the-one`**.

That path does not exist and never has. The real default is
`platformdirs.user_data_dir("the-one", appauthor=False)`
(`the_one/config.py::_default_data_dir`), which on Linux resolves to
**`~/.local/share/the-one`**.

**The consequence is a safety check that cannot fail.** An agent reading the
safety rule and then verifying "is the production data directory untouched?" by
testing `~/.the-one` gets a clean result **unconditionally** — whether or not it
has just written to the real one. The documentation hands the reader an
instrument that cannot detect the thing it exists to detect.

**This is not hypothetical.** It happened during Mission 24 Flight 6's HAT setup:
a `rotate-api-credential` was run without `THE_ONE_DATA_DIR` set and rotated the
operator's **production** credential. Every "production untouched" verification in
that session had checked `~/.the-one` and returned a false all-clear. The port
rule (never 8484) was followed scrupruously throughout; the directory half of the
same rule was checked against the wrong path. Impact was contained — the installed
app reads the credential at startup and was unaffected, and `encryption.key` and
the database were never touched — but the check that should have caught it was
structurally incapable of doing so.

## Evidence

- `CLAUDE.md:317` — "operator's default `~/.the-one` data directory"
- `the_one/config.py::_default_data_dir` — `platformdirs.user_data_dir("the-one", appauthor=False)`
- `ls ~/.the-one` → no such directory; `ls ~/.local/share/the-one` → the real one,
  holding `api-credential`, `encryption.key`, the database and `boxes/`.

## Corrective Action

Corrected `CLAUDE.md` to stop naming a literal path. The safety rule now says the
default is **platformdirs-derived**, gives the one-liner that prints it
(`python -c "from the_one.config import settings; print(settings.data_dir)"`), and
says plainly that **a check against a hardcoded guess is not a check** — the
directory must be read from the config, or from the target process's own
`/proc/<pid>/environ`, which is the technique that did work correctly elsewhere in
the same session.

## Verification

`grep -rn '~/.the-one' CLAUDE.md .flightops/` returns nothing.

## Sign-Off

*(pending — this was a documentation correction made directly by the Flight
Director rather than through the Developer/Reviewer pair, on the grounds that it
is a one-line safety-doc fix with no code change. Flagged here so the deviation
from the crew separation is on the record rather than assumed.)*
