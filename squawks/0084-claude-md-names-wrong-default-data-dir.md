# Squawk 0084: CLAUDE.md's safety rule names a default data directory that does not exist

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-09-18
**Completed**: 2026-09-19

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

`grep -rn '~/.the-one' CLAUDE.md .flightops/` returns **exactly one** hit —
`CLAUDE.md:326`, inside the paragraph that explains this incident ("an earlier
version of this section named `~/.the-one`, which does not exist..."). That is a
deliberate historical reference, not a live instruction.

*(Verification corrected 2026-09-19 during the turnaround batch. As first written
it said the grep "returns nothing", which is false and always was: the corrective
action itself introduced the explanatory sentence. A verification that fails
against its own fix is not a verification — and a reviewer running it verbatim
would have read the hit as an incomplete correction. The check that actually
matters is that no line **instructs** the reader to use `~/.the-one`, which
holds.)*

## Sign-Off

*Independent verification confirms the safety-rule correction is accurate and complete — no line instructs a literal default path, the printed one-liner returns the real platformdirs-derived directory, and the sole remaining `~/.the-one` string is the deliberate historical-incident reference the Verification section describes. Approved.*

**Reviewer**: independent Reviewer agent, turnaround batch 2026-09-19.

> Prior pending note, kept for the record:
>
> *(pending — routed into the 2026-09-19 turnaround batch for the independent
> sign-off it never received.)*
> 
> **Why this squawk is in a turnaround batch with no code change.** The corrective
> action was applied during Mission 24 Flight 6, directly by the Flight Director
> rather than through the Developer/Reviewer pair, on the grounds that it was a
> one-line safety-doc fix. That reasoning was wrong in a specific way worth naming:
> the fix was small, but the squawk is `grounding` severity and documents an incident
> in which the operator's **production API credential was rotated** behind a check
> that could not fail. A fix whose whole purpose is to make a safety check capable of
> failing is exactly the kind that should not be self-certified.
> 
> Nothing is being re-implemented here. The batch Reviewer verifies the landed
> correction and supplies the sign-off, closing the separation gap rather than
> leaving it recorded-and-accepted.
