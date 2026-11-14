# Leg: 08-integration-verification

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Final autonomous leg before the batch commit. Run the full unit + browser + AIAT suites, execute F5-specific regression sweeps, refresh `agents.md` and `CLAUDE.md` to reflect the F5 surface (19 tools, 6 active constraint types now including URL/host scope + SSRF, `WebConfig` shape, `SearchBackend` protocol pattern, mission-Constraint preservation note for SSRF-no-disable), close mission Open Questions, and append the F4-debrief-deferred `python_exec` exit-suffix behavior change to mission Known Issues.

## Context

- L0–L7 landed (uncommitted). HAT cleared all 9 scenarios with one inline fix (IP-literal SSRF bypass — already covered by 5 new regression tests).
- **No new code in this leg** — verification, doc refresh, mission-level housekeeping.
- **Mission Open Questions assigned to F5** (per `mission.md`): "Search backend extensibility shape" — RESOLVED via Decision 2 (SearchBackend Protocol with DDG impl).
- **F1 known issue** (DDG returns no results) — RESOLVED via L5 (browser User-Agent) + L6 (WebSearchTool wired to DDGSearchBackend).
- **F4 debrief action item** — append `python_exec` exit-code-suffix behavior change to mission Known Issues (deferred from F4 L8).

## Acceptance Criteria

- [x] **Full unit suite green** (modulo CSS-token red): exits 0 with ≥ 991 tests passing (post-L7 baseline). *(991 passed, 1 skipped, 239 deselected.)*
- [x] **F5 regression sweeps return expected counts**:
  - `grep -rn 'class WebConfig' the_one/` → exactly 1 (`_web_config.py`). *(1 hit at `_web_config.py:110`.)*
  - `grep -rn 'SSRFGuardedTransport' the_one/` → ≥ 5 (definition + 3 tools using it via `_build_transport` + 1 in tests-helper if any). *(8 source-line hits.)*
  - `grep -rn '_TOOL_CLASSES' the_one/tools/builtins.py` should show 19 tool entries. *(19 confirmed.)*
  - `grep -rn 'class SearchBackend' the_one/tools/` → exactly 1 (`_search_backends.py`). *(1 hit.)*
  - `grep -rn 'class DDGSearchBackend' the_one/tools/` → exactly 1. *(1 hit.)*
  - `grep -rn 'CheckMode\.' the_one/tools/` → multiple (post-L0 unification consumers). *(consumers in `filesystem.py` + `execution.py`.)*
  - `grep -rn 'disable_ssrf\|ssrf_disabled' the_one/` → 0 (mission invariant). *(0 source-code hits; only docstring/comment lines describing the invariant itself.)*
- [x] **Browser test attempt** — run `make test-browser`. Document if Playwright env gap persists. *(Env gap confirmed: 216 errors on Playwright Chromium launch — pre-existing F1 Known Issue F1-2.)*
- [x] **AIAT live smoke attempt** — document if env gap persists. *(Env gap confirmed: default agent has `provider_config_id=None`; `test_basic_chat` fails on empty response.)*
- [x] `agents.md` reflects F5: 19 tools, 6 active constraint types (path scope, read-size cap, output cap, timeout caps, command denylist, **URL/host scope + SSRF** new in F5), `WebConfig` shape, `SearchBackend` protocol, SSRF "no full-disable" invariant, IP-literal-also-blocked correction.
- [x] `CLAUDE.md` reflects F5: `WebConfig` shape + `SSRFGuardedTransport` pattern + `SearchBackend` Protocol pattern.
- [x] `mission.md`:
  - Mark "Search backend extensibility shape" Open Question resolved (Decision 2).
  - Mark F1 known issue resolved (`[x]` with reference to F5 L5+L6).
  - Append `python_exec` exit-code-suffix behavior change to Known Issues (per F4 debrief).
- [x] Flight log: L8 entry appended summarizing verification results.

## Verification Steps

```bash
# Full unit suite
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined 2>&1 | tail -3

# F5 regression sweeps
echo "=== WebConfig defined sites ==="
docker exec the-one grep -rn 'class WebConfig' the_one/

echo "=== SSRFGuardedTransport refs ==="
docker exec the-one grep -rn 'SSRFGuardedTransport' the_one/ | wc -l

echo "=== SearchBackend Protocol ==="
docker exec the-one grep -rn 'class SearchBackend\|class DDGSearchBackend' the_one/tools/

echo "=== _TOOL_CLASSES count ==="
docker exec the-one python -c "from the_one.tools.builtins import _TOOL_CLASSES; print(len(_TOOL_CLASSES), 'tools'); print(list(_TOOL_CLASSES))"

echo "=== Mission invariant: no disable_ssrf ==="
docker exec the-one grep -rn 'disable_ssrf\|ssrf_disabled\|disable_ssrf_protection' the_one/ || echo "(none)"

# Browser tests + AIAT (best-effort)
cd ~/projects/the-one && make test-browser 2>&1 | tail -10 || echo "browser test failed (env)"
docker exec the-one pytest -m live tests/test_aiat.py -x -q 2>&1 | tail -5 || echo "aiat live not available (env)"
```

## Implementation Guidance

1. Run verification suite first.
2. Update `agents.md` (project root) — reflect F5 surface (19 tools, 6 active constraint types).
3. Update `CLAUDE.md` (project root) — `WebConfig` shape + `SearchBackend` Protocol.
4. Update `mission.md`:
   - Mark "Search backend extensibility shape" Open Question resolved.
   - Mark F1 known issue resolved.
   - Append `python_exec` exit-code-suffix to Known Issues (per F4 debrief).
5. Append L8 entry to flight log.
6. Mark this leg `landed`; mark FLIGHT status `landed` in flight.md; check off this leg in flight.md.

## Files Affected

- `agents.md` — F5 surface refresh.
- `CLAUDE.md` — `WebConfig` + SearchBackend Protocol additions.
- `missions/05-built-in-tool-system/mission.md` — close F5 Open Question; close F1 known issue; append python_exec exit-suffix item.
- `missions/05-built-in-tool-system/flights/05-web-expansion-and-constraints/flight-log.md` — L8 entry.
- `missions/05-built-in-tool-system/flights/05-web-expansion-and-constraints/flight.md` — status `in-flight` → `landed`; check off L8.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests run (results documented even if some fail for env reasons)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Set FLIGHT status to `landed` in flight.md (this is the final leg)
- [x] Check off this leg in flight.md
- [x] Mark mission-level Open Questions resolved
- [ ] (Flight Director will commit + open PR after Reviewer pass)
