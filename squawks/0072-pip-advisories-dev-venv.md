# Squawk 0072: Upgrade `pip` in the dev venv to clear two advisories from the audit gate

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

## Report

`pip-audit` at Flight 5's close reports two advisories against `pip` 26.1.1.
Logged separately from squawk 0071 deliberately: despite surfacing in the
same audit run, this is a **different kind of item** and the operator may
reasonably schedule it differently.

The distinction that matters: `pip` is **not a dependency of this project**.
It appears in no manifest (`pyproject.toml` declares it nowhere) and is not
part of the frozen closure that ships — it is the installer present in the
development virtualenv. So unlike squawk 0071 there is **no repository change
to make**; the fix is `.venv/bin/python -m pip install -U pip`, and the
artifact of record is this squawk rather than a diff.

The reason to do it at all is gate hygiene: `pip-audit` is a release-closure
gate run by hand at every flight close, and a standing finding that everyone
has learned to skip past is how a real finding gets skipped past too. Clear
it so the gate's output stays meaningful.

Exposure is low on the advisories' own terms — one requires installing from a
malicious package index, and the other concerns entry-point paths at install
time. Neither is reachable by the running application; both concern the act
of installing packages.

## Evidence

`.venv/bin/pip-audit`, 2026-09-17:

```
pip 26.1.1  PYSEC-2026-196   26.1.2
pip 26.1.1  PYSEC-2026-3721  26.2
```

- `PYSEC-2026-196` — `console_scripts`/`gui_scripts` treated as paths rather
  than file names without sanitising the resolved absolute path, so entry
  points can be installed outside the installation directory.
- `PYSEC-2026-3721` — doubly-encoded package URLs from an index mishandled,
  allowing files to be written to arbitrary locations even when installing
  wheels. Requires a malicious *index*; malicious packages alone cannot
  exploit it.

Not declared anywhere in the repo: `grep -n -i "pip" pyproject.toml` returns
no dependency entry for `pip` itself.

## Corrective Action

*(written at completion)*

## Verification

*(written at completion — expected: `.venv/bin/pip-audit` no longer reports
`pip`; `make test-unit` stays green, since nothing the application imports
has changed)*

## Sign-Off

*(written at completion)*
