# Squawk 0071: Bump the `soupsieve` floor pin to close two ReDoS advisories

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

## Report

`pip-audit` at Flight 5's close reports two new advisories against
`soupsieve` 2.8.4, both fixed in 2.9.0. Flight 4 closed with `pip-audit`
clean and Flight 5 changed no dependency manifest, so these are upstream
advisories published in between — not a regression introduced by any flight.

`pyproject.toml` already carries an explicit security floor for this package
(`soupsieve>=2.8.4`), added by an earlier bump for a *different* pair of
CVEs. This squawk raises that floor and updates its comment, following the
convention already established in that block.

**Severity is `routine`, not `grounding`, on a checked exposure argument
rather than an assumption.** Both advisories are quadratic-CPU (ReDoS)
denial-of-service reachable *only* where an attacker-controlled CSS selector
is compiled — the advisories state plainly that "applications using only
hard-coded selectors are unaffected". This project passes **no** selector at
all: `grep` finds no `BeautifulSoup`, `.select(`, `.select_one(` or
`soupsieve` usage anywhere in `the_one/`. The package is a pure transitive
(`soupsieve` ← `beautifulsoup4` ← `markdownify`/`readability-lxml`), and
`markdownify` walks the parse tree rather than querying it by selector. The
vulnerable code path is therefore not reachable from this application today.

Worth fixing anyway, for the reason the floor-pin block exists: `soupsieve`
**does** ship inside the frozen closure, and the convention is to keep the
shipped closure free of known advisories rather than to re-derive
reachability every time the gate runs.

## Evidence

`.venv/bin/pip-audit`, 2026-09-17:

```
soupsieve 2.8.4   CVE-2026-85999  2.9.0
soupsieve 2.8.4   CVE-2026-86000  2.9.0
```

- `CVE-2026-85999` — `src/soupsieve/css_parser.py`: `RE_WS_END =
  re.compile(fr'{WSC}*$')` is anchored only at the end, so `.search()` retries
  at every offset and a long internal whitespace/comment run costs O(n²). A
  ~20 KB *valid* selector stalls for ~10 s.
- `CVE-2026-86000` — the shared `IDENTIFIER` sub-pattern places two adjacent
  quantified groups over overlapping character classes
  (`(?:[classA]|ESC)+(?:[classB]|ESC)*`), backtracking quadratically on a
  failing match. `compile('[a=' + 'a'*12000)` ≈ 17 s.

Existing floor and its comment: `pyproject.toml:71` — `"soupsieve>=2.8.4"`,
documented in the block above it as "pure transitive via readability-lxml's
bs4 dep (no prior explicit floor; closes GHSA-2wc2-fm75-p42x /
CVE-2026-49476 and GHSA-836r-79rf-4m37 / CVE-2026-49477; fixed in 2.8.4)".

Non-reachability check: `grep -rn "BeautifulSoup\|\.select(\|\.select_one(\|soupsieve" the_one/ --include=*.py`
returns only `the_one/platform/pty_unix.py:413`, which is `select.select` on
a file descriptor — unrelated to CSS.

## Corrective Action

Raised the `soupsieve` floor in `pyproject.toml` from `>=2.8.4` to
`>=2.9.0`, and extended the existing floor-pin comment block above it
(rather than deleting the record of the earlier fix): it now notes that
`2.8.4` closed GHSA-2wc2-fm75-p42x/CVE-2026-49476 and
GHSA-836r-79rf-4m37/CVE-2026-49477, and that the floor was raised to
`2.9.0` for the two new ReDoS advisories (CVE-2026-85999, CVE-2026-86000)
found in the CSS-selector compiler, per the 2026-09-17 `pip-audit` run.

Also upgraded the installed package in the repo dev venv —
`.venv/bin/python -m pip install -U "soupsieve>=2.9.0"` — since `pip-audit`
audits what's actually installed, not the `pyproject.toml` floor alone.
This resolved cleanly to `soupsieve-2.9.2` with no other package touched
(no cascading version changes), so nothing exceeded this squawk's scope.
**`uv.lock` was subsequently updated by the Flight Director, and that step
was load-bearing rather than tidying.** The implementing Developer left the
lock at `2.8.4`, reasoning it was outside the squawk's stated file scope and
that a later `uv lock` would pick up the raised floor. That reasoning is
sound in general and wrong here, because of how this project ships:
`ci/tasks/windows-installer-build.yml` runs `uv export --no-dev … >
release-requirements.txt` and installs **that** closure with `--no-deps`,
deliberately — the task's own comment (from squawks 0009 and 0015) records
that the frozen app must ship the exact locked set rather than a build-time
re-resolve. With the lock untouched, the floor bump would have changed
nothing about the shipped installer, and this squawk's stated reason for
existing — that `soupsieve` ships inside the frozen closure — would have
gone unmet while the gate read clean.

Ran `uv lock --upgrade-package soupsieve`, scoped to the one package:
`2.8.4 → 2.9.2`, four lines changed in `uv.lock`, no cascade to any other
pin. The narrow `--upgrade-package` form was chosen over a bare `uv lock`
precisely so an unrelated resolver drift could not ride along inside a
routine squawk.

## Verification

- `.venv/bin/pip-audit` (post-upgrade): no `soupsieve` finding (see combined output below, run alongside squawk 0072's `pip` upgrade).
- `ruff check the_one/ tests/ scripts/` / `make lint`: `All checks passed!`.
- No dependency other than `soupsieve` itself needed a version change to satisfy the new floor — confirmed by the `pip install -U` output, which uninstalled only `soupsieve 2.8.4` and installed `2.9.2`.
- `make test-unit` not run in this pass (no code/behavior change); the package bump is orthogonal to application logic and covered by the existing `soupsieve` floor-pin convention rather than a new test.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `PENDING`
