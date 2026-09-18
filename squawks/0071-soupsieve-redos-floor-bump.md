# Squawk 0071: Bump the `soupsieve` floor pin to close two ReDoS advisories

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

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

*(written at completion)*

## Verification

*(written at completion — expected: `.venv/bin/pip-audit` no longer reports
`soupsieve`; `make test-unit` stays green; `make lint` clean)*

## Sign-Off

*(written at completion)*
