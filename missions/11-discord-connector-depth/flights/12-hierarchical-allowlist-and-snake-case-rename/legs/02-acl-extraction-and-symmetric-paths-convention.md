# Leg: acl-extraction-and-symmetric-paths-convention

**Status**: completed
**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](../flight.md)

## Objective

Extract `the_one/connectors/_acl.py:admits_inbound`'s DM-vs-guild decision tree into two private helpers (`_admits_inbound_dm` + `_admits_inbound_guild`), with `admits_inbound` becoming the thin dispatcher that consults `is_dm` and delegates. Semantically a no-op — all 63 existing ACL test sites pass unchanged against the same inputs and outputs. Also: codify `two-symmetric-paths-in-acl` as a named M11 convention in `the_one/agents.md` so future ACL-touching legs default to enumerating both `admits_inbound` AND `admits_outbound` at recon (F11 debrief recommendation #5 pulled forward).

## Context

This is the second of four legs in F12. L1 (snake_case identifier rename) landed cleanly — `_acl.py` was untouched by L1 (484 LOC, 5 functions: `_default_not_dm`, `_default_no_mention`, `admits_outbound`, `admits_dm_peer`, `admits_inbound`).

**Per the flight spec's L2 design decision (`_acl.py:admits_inbound` Extraction):**
- The extraction is done BEFORE L3's storage-shape changes so L3 lands ACL semantic changes against clean structure (the F10 debrief flagged `_acl.py` at edge-of-readable with 5 axes; L3 adds structured-tuple consumption + the per-peer DM-allow check).
- This is a **structurally no-op refactor**: same inputs, same outputs, same flat-axis shape. All 58+ existing `test_connectors_acl.py` test sites + 5+ test sites in `test_connectors_routing.py` / `test_connectors_inbound.py` (63 total per L2 design-time grep) pass unchanged.
- File size after extraction: ~520 LOC (current 484 + ~36 for dispatcher + helper signatures + duplicated peers-axis preludes if developer opts to duplicate vs factor out).

**Per F11 debrief recommendation #5 ("two-symmetric-paths-in-acl convention"):** the project's `_acl.py` has two parallel paths (`admits_outbound` + `admits_inbound`) that have repeatedly needed lockstep updates — F8 L8 (per-agent guilds/roles axes), F10 L1 (dm_admission), F11 L3 (deny-message retirement). Codifying as a named convention in agents.md M11 section makes the recon discipline part of the substrate's documented shape so future ACL-touching legs default to enumerating both directions at recon.

## Inputs

- F12 L1 landed (status: landed, uncommitted on branch `flight/12-hierarchical-allowlist-and-snake-case-rename`)
- L1 baseline (re-verified): backend `pytest --ignore=tests/browser -x --timeout 60` at 2749 passed / 4 skipped / 0 errors / ~262s wall
- `_acl.py` current state (post-L1, untouched): 484 LOC; `admits_inbound` at `:248-484`; `is_dm` branches at `:333` (account-scope) and `:411` (per-agent)
- `agents.md` M11 section currently has 3 conventions: `dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `studio-event-bus` (post-F11 L3 + F9 L6). L2 adds `two-symmetric-paths-in-acl` as a 4th sibling.
- 63 test sites exercising `admits_inbound` across 3 test files: `tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_inbound.py`. All must pass unchanged.
- Uncommitted operator dev state: `docker-compose.yml` (unchanged from L1; stays unstaged).

## Outputs

- `admits_inbound` becomes a thin dispatcher consulting `is_dm` and delegating to one of two new private helpers
- `_admits_inbound_dm` private helper handles the `is_dm=True` branches at account-scope AND per-agent (current code at `_acl.py:333-354` + `:411-424`)
- `_admits_inbound_guild` private helper handles the `is_dm=False` branches at account-scope AND per-agent (current code at `_acl.py:357-389` + `:425-483`)
- The 63 existing test sites pass unchanged (extraction is a structural no-op)
- `the_one/agents.md` Mission-specific (M11) section gains a new `### \`two-symmetric-paths-in-acl\`` convention block
- Flight log L2 progress entry appended
- Leg status `landed` (NOT committed — Phase 2d batches commits)

## Acceptance Criteria

- [x] `admits_inbound` function (`the_one/connectors/_acl.py:248`) is shortened: contains only the dispatcher branching (`if is_dm: return _admits_inbound_dm(...) else: return _admits_inbound_guild(...)`). Per-call input prep (`account_id` derivation, `allowlist` lookup, `member_roles_set` computation) lives INSIDE each helper that needs it — the dispatcher itself does no pre-computation. The current 240-line body is replaced; full body content moves into the two helpers.
- [x] `_admits_inbound_dm` private helper exists in `_acl.py` (defined before `admits_inbound` per Python convention, OR after — implementer's call; both are conventional). Signature accepts the full input set that the DM branches consume: `account`, `agent_acl`, `peer_id`, `account_id`, `allowlist` (passed-in OR re-looked-up). Returns `tuple[bool, str]`. Body contains: account-scope peers axis check + dm_admission check + per-agent peers axis check + admit_dms check.
- [x] `_admits_inbound_guild` private helper exists in `_acl.py`. Signature accepts: `account`, `agent_acl`, `peer_id`, `channel_id`, `account_id`, `allowlist`, `guild_id`, `member_roles_set` (passed-in OR re-looked-up). Returns `tuple[bool, str]`. Body contains: account-scope peers axis check + channels + guilds + roles checks + per-agent peers axis check + per-agent channels + guilds + roles checks.
- [x] **Behavior is byte-identical pre-vs-post extraction**: all 63 existing test sites exercising `admits_inbound` pass without modification. No test fixture or assertion changes in this leg.
- [x] `the_one/agents.md` Mission-specific (M11) section gains a new `### \`two-symmetric-paths-in-acl\`` convention block (added as a sibling to `dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `studio-event-bus` — insertion point per implementer's call, but inside the `## Mission-specific (M11)` section).
- [x] The new convention block cites: (a) the substrate shape (`admits_inbound` + `admits_outbound` as mirror images at the per-agent block); (b) the historical pattern instances (F8 L8 per-agent guilds/roles axes, F10 L1 dm_admission, F11 L3 deny-message retirement); (c) the prescriptive rule ("recon for any ACL-touching leg defaults to enumerating both directions"); (d) source attribution (F11 debrief recommendation #5, F12 L2 codification).
- [x] **No semantic regression**: `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30` is green at the same pass count as L1 baseline (no test additions or skips in L2).
- [x] **Broader backend regression**: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` is green at 2749+ passing / 4 skipped (no test additions in L2; same baseline as L1).
- [x] Browser baseline preserved (no L2 changes to UI — `tests/browser/` should be untouched).
- [x] Flight log `Leg Progress` section has an L2 entry summarizing the extraction shape + agents.md addition + test results.
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d batches commits.

## Verification Steps

1. **Focused ACL test suite** (the regression net for the extraction):
   - `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30`
   - Must show all 63+ admits_inbound-touching tests pass; same pass count as L1 baseline for these 3 files.

2. **Full backend suite** (no regressions outside ACL):
   - `docker exec the-one pytest --ignore=tests/browser -x --timeout 60`
   - Must show 2749+ passed / 4 skipped / 0 errors / 0 failures. Same baseline as L1.

3. **`_acl.py` structure verification**:
   - `grep -nE "^(async )?def " the_one/connectors/_acl.py` should show 7 functions (was 5; added `_admits_inbound_dm` + `_admits_inbound_guild`): `_default_not_dm`, `_default_no_mention`, `admits_outbound`, `admits_dm_peer`, `_admits_inbound_dm` (new), `_admits_inbound_guild` (new), `admits_inbound`. Order is implementer's call.
   - `wc -l the_one/connectors/_acl.py` should show ~510-525 LOC (current 484 + ~30-40 for extraction overhead). Substantial growth flags a non-structural change; warn.

4. **`admits_inbound` body verification** (mechanical):
   - The function body should contain a clear dispatcher pattern. Spot-check: `grep -A 30 "^def admits_inbound" the_one/connectors/_acl.py` should show ≤ ~30 lines of body, with explicit `if is_dm:` branching delegating to the two helpers.

5. **agents.md verification** (visual):
   - Read the M11 section. The new `### \`two-symmetric-paths-in-acl\`` block exists between `### \`backend-merged-replay\`` and `### \`studio-event-bus\`` (or wherever the implementer placed it, as long as it's inside the M11 section).
   - The block describes the substrate shape, historical instances, prescriptive rule, and source attribution per AC #6.

## Implementation Guidance

**Order matters**: do the agents.md convention block first (easier; touches only one file) so the developer cycles through the simpler edit before the substantive extraction. Then do the extraction; then run tests; then update flight log.

### Step 1 — Add `two-symmetric-paths-in-acl` convention to `the_one/agents.md` M11 section

Locate the M11 section in `the_one/agents.md` (currently has 3 conventions: `dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `studio-event-bus` — line numbers post-F11 L3 + F9 L6; grep `grep -n "^### \`" the_one/agents.md | grep -A 5 "Mission-specific (M11)"` to find the section).

Add a new `### \`two-symmetric-paths-in-acl\`` block as a sibling to the existing 3 M11 conventions. Suggested content (implementer can rephrase for style consistency with siblings):

```markdown
### `two-symmetric-paths-in-acl`

`the_one/connectors/_acl.py` has two parallel admission paths — `admits_outbound` (used by the F4 platform-send tool, no envelope context) and `admits_inbound` (used by the F7 L5 dispatcher post-routing, full envelope context including `is_dm` + `guild_id` + `member_roles`). The two share the same shape at the per-agent block — peers axis + channels axis + (M10 F8 L8) guilds axis + (M10 F8 L8) roles axis — and have repeatedly required lockstep changes:

- M10 F8 L8 added per-agent `guilds` + `roles` axes to BOTH paths
- M11 F10 L1 added the `dm_admission` axis (consumed only by `admits_inbound` because outbound has no envelope, but the symmetric path's stub-update was the deferred half — outbound silently ignores the new kwargs)
- M11 F11 L3 retired the anachronistic "DMs-only override" deny string in BOTH paths (the inbound's `:437-454` had a 9-line back-compat comment; outbound's `:163-179` had a 4-line comment; both retired in lockstep)

Recon for any ACL-touching leg defaults to enumerating both directions. The recon question "does this change touch `admits_inbound` only, or `admits_outbound` too?" must be answered explicitly at leg planning; the default-yes-to-both case is the common one. The L3 of F12 (storage-shape + ACL semantics update) is the next concrete instance — structured-tuple channel + role lookups need to land in BOTH paths.

Source: F11 debrief recommendation #5; codified at F12 L2.
```

### Step 2 — Extract `admits_inbound` into dispatcher + two helpers

Read `the_one/connectors/_acl.py:248-484` (current `admits_inbound`). The extraction produces 3 functions where there's currently 1:

**`admits_inbound` (dispatcher)** — keeps the existing signature, body is just the dispatch (helpers receive RAW `member_roles` and recompute the set internally):
```python
def admits_inbound(
    account: Connector,
    agent_acl: dict[str, list[str] | bool | None] | None,
    peer_id: str,
    channel_id: str,
    *,
    is_dm: bool = False,
    guild_id: str | None = None,
    member_roles: list[str] | None = None,
) -> tuple[bool, str]:
    """[docstring preserved verbatim — describes the public contract]"""
    if is_dm:
        return _admits_inbound_dm(
            account, agent_acl, peer_id, channel_id
        )
    return _admits_inbound_guild(
        account, agent_acl, peer_id, channel_id,
        guild_id=guild_id,
        member_roles=member_roles,  # raw list; _admits_inbound_guild recomputes the set internally
    )
```

**`_admits_inbound_dm`** (handles the `is_dm=True` branches at account-scope AND per-agent — currently `_acl.py:316-356` + `:391-424`):
```python
def _admits_inbound_dm(
    account: Connector,
    agent_acl: dict[str, list[str] | bool | None] | None,
    peer_id: str,
    channel_id: str,
) -> tuple[bool, str]:
    """Handles the DM-context branches of admits_inbound (is_dm=True path).
    
    Per the dms-orthogonal-to-guild-restriction convention (agents.md),
    DMs consult only the peers axis (account-scope + per-agent), the
    account-scope dm_admission axis, and the per-agent admit_dms axis.
    Channels/guilds/roles axes are intentionally skipped.
    """
    account_id = account.id
    # Account-scope: peers axis + dm_admission check
    # [body extracted verbatim from _acl.py:317-356]
    # Per-agent: peers axis + admit_dms check  
    # [body extracted verbatim from _acl.py:391-424]
    return True, ""
```

**`_admits_inbound_guild`** (handles the `is_dm=False` branches at account-scope AND per-agent — currently `_acl.py:316-327` + `:357-389` + `:391-408` + `:425-483`):
```python
def _admits_inbound_guild(
    account: Connector,
    agent_acl: dict[str, list[str] | bool | None] | None,
    peer_id: str,
    channel_id: str,
    *,
    guild_id: str | None,
    member_roles: list[str] | None,
) -> tuple[bool, str]:
    """Handles the guild-context branches of admits_inbound (is_dm=False path).
    
    Consults the 4-axis ACL semantics (peers / channels / guilds / roles)
    per M10 F8 L8.
    """
    account_id = account.id
    member_roles_set = set(member_roles or [])
    # Account-scope: peers axis + channels + guilds + roles
    # [body extracted verbatim from _acl.py:317-327 + :357-389]
    # Per-agent: peers axis + channels + guilds + roles
    # [body extracted verbatim from _acl.py:391-408 + :425-483]
    return True, ""
```

**Peers-axis duplication**: each helper checks the peers axis (account-scope + per-agent). The duplication is small (~7 lines × 2 instances × 2 helpers = ~28 duplicated lines). The implementer MAY factor the peers checks out into a third helper `_check_peers` if it improves readability, OR keep them duplicated — both are acceptable. Duplication is preferable IF future per-axis changes (e.g. L3's per-peer `dm_allowed` is a per-peer-axis sub-field that only the DM path consults) would diverge the two paths. Implementer's judgment.

**Docstring preservation**: the existing 50-line `admits_inbound` docstring (lines 258-313) describes the public contract. It stays attached to `admits_inbound` (the dispatcher). The helpers get short docstrings describing their narrower contract (just the branch they own).

### Step 3 — Run tests

```bash
# Focused ACL suite (the regression net for the extraction):
docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30
# Expect: ~63+ admits_inbound-touching tests pass.

# Broad backend (must remain at L1 baseline):
docker exec the-one pytest --ignore=tests/browser -x --timeout 60
# Expect: 2749+ passed / 4 skipped / 0 errors.
```

If a test fails: the extraction is not byte-identical. Compare the extracted helper body line-by-line against the original `admits_inbound` body to find the divergence. Common pitfalls:
- Forgetting to compute `member_roles_set = set(member_roles or [])` in `_admits_inbound_guild`
- Forgetting the account-scope peers check in either helper
- Reordering branches such that an early `return` skips a later check

### Step 4 — Verify structure

```bash
# Function count (should be 7 now):
grep -cE "^(async )?def " the_one/connectors/_acl.py
# Expected: 7 (was 5; added _admits_inbound_dm + _admits_inbound_guild)

# admits_inbound body length (should be ~10-15 lines, was ~240):
awk '/^def admits_inbound\(/,/^def [^_]/{print}' the_one/connectors/_acl.py | wc -l
# Expected: ~30-50 (includes 50-line docstring + small dispatcher body)
```

### Step 5 — Update flight log and leg status

- Append entry to `../flight-log.md` under `## Leg Progress` summarizing: extraction shape (1 → 3 functions), agents.md convention added, test results (focused + broad counts).
- Update this leg artifact's header `**Status**: in-flight` → `**Status**: landed`.
- Do NOT update the flight-spec leg checkbox (commit leg does that).
- Do NOT commit. Do NOT `git add`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Helper visibility**: both helpers are private (underscore-prefixed) per Python convention. They're not exported via `__all__` (the module doesn't have one); callers outside `_acl.py` should not import them directly. Tests exercise only the public `admits_inbound` dispatcher.
- **`admits_outbound` parallel update**: L2 does NOT extract `admits_outbound` (that function is shorter at ~80 LOC; the symmetric-paths convention applies but the extraction symmetry isn't required for L2's scope). `admits_outbound` stays as a single function. The codified `two-symmetric-paths-in-acl` convention applies to FUTURE changes (notably L3 of this same flight, which updates BOTH paths for structured-tuple channel lookups).
- **Branch ordering**: the original `admits_inbound` runs account-scope checks BEFORE per-agent checks. The extracted helpers preserve this ordering. Re-ordering would change the deny-reason message returned (since the first failing check returns) — tests would surface this.
- **Type annotation drift**: the dispatcher signature stays exactly the same (public contract). Helper signatures may use Optional or `| None` per project style; check `_acl.py:248-257` for the project's annotation pattern and match it.
- **Existing test imports**: tests import `admits_inbound` (the dispatcher) directly. They do NOT import the helpers. Verify with `grep -rn "from the_one.connectors._acl import" tests/`. If any test imports an internal helper (unlikely), update accordingly.

## Files Affected

**Production code (1 file)**:
- `the_one/connectors/_acl.py` — 1 function extracted into 3 functions; net LOC change ~+30-40

**Documentation (1 file)**:
- `the_one/agents.md` — 1 new convention block added to Mission-specific (M11) section

**Flight artifacts** (mandatory updates per leg-execution protocol):
- `missions/11-discord-connector-depth/flights/12-hierarchical-allowlist-and-snake-case-rename/flight-log.md` — append L2 progress entry
- This file (`legs/02-acl-extraction-and-symmetric-paths-convention.md`) — status → `landed`

**Explicitly NOT affected in L2**:
- `admits_outbound` (parallel path; convention applies to FUTURE changes per the convention's prescriptive rule; not extracted in this leg)
- Any test file (extraction is a structural no-op)
- Schema, API routes, frontend, browser tests
- `docker-compose.yml` (operator's local dev state)
- L1 residue items (3 historical-narration sites in `_stub.py:23`, `_connector_types.py:24`, `models.py:120` — Phase 2d reviewer judgment; not L2 scope)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (extraction shape, agents.md convention, tests green)
- [x] L2 atomicity boundary verified (no tests modified, no schema/UI changes, only `_acl.py` + `agents.md` touched)
- [x] Backend suite green at 2749+ passing
- [x] Focused ACL suite green at L1 baseline pass count
- [x] Flight-log L2 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all 4 legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-29, leg-design time):

| Citation | Classification | Resolution |
|----------|---------------|------------|
| `the_one/connectors/_acl.py` total LOC 484 | OK | Verified via `wc -l` |
| `the_one/connectors/_acl.py:248` `def admits_inbound(` | OK | Verified via `grep -nE "^def admits_inbound"` |
| `the_one/connectors/_acl.py:333` `if is_dm:` (account-scope DM branch) | OK | Verified by reading lines 318-356; account-scope is_dm branch starts at :333 with `dm_admission` lookup at :334 |
| `the_one/connectors/_acl.py:411` `if is_dm:` (per-agent DM branch) | OK | Verified by reading lines 410-424; per-agent is_dm branch starts at :411 with `admit_dms` lookup at :412 |
| `the_one/connectors/_acl.py:316-356` account-scope block | OK | Verified by reading; structure matches DD: peers axis :318-327 + is_dm branch :333-356 |
| `the_one/connectors/_acl.py:391-484` per-agent block | OK | Verified by reading; structure matches DD: peers axis :393-408 + is_dm branch :411-424 + else branch :425-483 |
| 63 test sites exercising `admits_inbound` across 3 test files | OK | Verified via `grep -rn "admits_inbound" tests/ --include='*.py' \| wc -l` returns 63 |
| `the_one/agents.md` Mission-specific (M11) section with 3 existing conventions | OK | Verified by reading; existing conventions: `dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `studio-event-bus` |
| `_acl.py:163-179` (outbound deny block referenced in convention text) | OK | Verified at F11 L3 land time; convention text cites historical instance accurately |
| `_acl.py:437-454` (inbound deny block referenced in convention text) | OK | Verified at F11 L3 land time; convention text cites historical instance accurately |

10 citations verified clean against current code at leg design time. All references match live state. The extraction is a structural no-op against the current `admits_inbound` body; no drift between leg-design and implementation is expected.
