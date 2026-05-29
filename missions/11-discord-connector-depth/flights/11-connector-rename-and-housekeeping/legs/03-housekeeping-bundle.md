# Leg: housekeeping-bundle

**Status**: completed
**Flight**: [Connector Terminology Rename + Small-Housekeeping Fold-Ins](../flight.md)

## Objective

Land three independent housekeeping items the F9+F10 combined debrief filed as F11-bound: (a) sweep `the_one/agents.md` structurally (promote two new M11 conventions, extend the per-axis-tri-state-override block from 4 axes to 5, add callouts for two new F9 API endpoints under their L2-renamed paths, prune F4-era prose); (b) retire the anachronistic deny message + back-compat comment block in `the_one/connectors/_acl.py` and update its two test fixtures; (c) redesign the `tests/test_provider_repository.py` async fixture to drop the 13 pre-existing teardown errors that have been carried since F7.

## Context

This is the third and final leg in F11. L1 + L2 landed the connector rename across the entire codebase; L3 closes the small-housekeeping carry-forward debt before Phase 2d batches commits across all three legs.

**Per the flight spec's L3 design decisions:**
- Ordering within the leg matters: do the agents.md sweep FIRST so the documentation prose changes shake out any further rename residue before the surgical fixes land.
- The asyncio fix is a fixture-pattern redesign (sync fixture wrapping async resource via `run_until_complete()` under `asyncio_mode = "auto"`), NOT the originally-assumed surgical AsyncExitStack ordering tweak. This was reclassified at flight planning (architect cycle-1 finding).
- After L3 lands, the full backend suite runs WITHOUT the `--deselect tests/test_provider_repository.py` workaround the L1/L2 verification used.

**Atomicity boundary:** L3 owns five specific surfaces (cycle-1 review added 2):
- `the_one/agents.md` (structural sweep)
- `the_one/connectors/_acl.py` — TWO deny blocks: **outbound** at `:163-179` (cycle-1 finding — `"target is not a DM"`) AND **inbound** at `:437-454` (`"envelope is not a DM"`)
- `tests/test_connectors_acl.py` — 4 test methods pinning the old deny strings (2 outbound at `:107`, `:137`; 2 inbound at `:322`, `:354`)
- `tests/test_connector_send_tool.py:744-745` (cycle-1 finding — also pins the outbound deny string)
- `tests/test_provider_repository.py` (fixture redesign)

L3 must NOT touch any L1 or L2 surface (no Python substrate identifiers, no API routes, no frontend). The L1 + L2 diffs on the branch are inputs to L3, not modification targets.

## Inputs

- L1 + L2 landed (both status: landed, uncommitted on branch `flight/11-connector-rename-and-housekeeping`)
- Backend suite at 2736 passed / 4 skipped / 30 deselected (with `--deselect tests/test_provider_repository.py`) after L2
- Browser suite at 431 passed / 35 skipped / 14 deselected after L2 (2 deselected are pre-existing `main` failures, not L2-caused; the 12 marker-deselected are normal browser-test markers)
- 13 teardown errors in `tests/test_provider_repository.py` still present (their fix IS this leg)
- agents.md size: 906 lines
- M11 conventions section starts at `agents.md:405` (currently has only `studio-event-bus` at line 407)
- `per-axis-tri-state-override` convention heading at `agents.md:110`; the deeper "four parallel axes" application paragraph at `agents.md:678`
- F9 L3 introduced 2 peer-approval API endpoints (now renamed by L2 to `/api/connectors/{id}/peer-approvals/{id}/{approve|dismiss}`); F9 L5 introduced the per-agent detach endpoint (now `DELETE /api/agents/{name}/connectors/{connector_id}`)
- `_acl.py` deny block at lines 440-462 (back-compat comment at 440-448; deny statement at 449-455)
- `tests/test_connectors_acl.py` has 4 tests pinning the old deny string at lines 97-122, 123-148, 311-336, 339-356
- Operator local-state callout (unchanged from L1/L2): `docker-compose.yml` carries uncommitted HAT env vars; do NOT stage it

## Outputs

- `the_one/agents.md` extended with 2 new M11 conventions (`dms-orthogonal-to-guild-restriction`, `backend-merged-replay`), per-axis-tri-state-override extended to 5 axes, callouts added for 2 new F9 API endpoints under L2-renamed paths, F4-era prose pruned
- `the_one/connectors/_acl.py:440-462` deny block: 9-line back-compat comment retired; deny message updated to reflect the branch's actual semantic (per-agent channels axis is explicitly empty, no DM-related text)
- `tests/test_connectors_acl.py` 4 test methods updated: deny-string assertions match the new message (test names + bodies stay; only the string literal changes)
- `tests/test_provider_repository.py` fixture `repo` converted from sync `def repo` + `run_until_complete()` to native `async def repo` consuming `await` directly; 0 teardown errors after L3
- Flight log L3 progress entry appended
- Leg status `landed` (NOT committed — Phase 2d batches all three legs into one commit)

## Acceptance Criteria

- [x] **agents.md M11 section grows by 2 new convention blocks**: `### \`dms-orthogonal-to-guild-restriction\`` and `### \`backend-merged-replay\`` added under the `### Mission-specific (M11)` heading at `agents.md:405`, following the existing convention-block prose pattern (1-2 paragraph description citing the originating leg + the file/symbol the convention applies to).
- [x] **agents.md per-axis-tri-state-override block extended to 5 axes**: the deep application paragraph at `agents.md:678` (`"four parallel axes: peers, channels, plus guilds and roles"`) updated to list 5 axes including `dm_admission` (F10 L1 addition); the count "four" → "five" and the axis enumeration extended. If the convention's own definition block at `agents.md:110-115` references a specific axis count or example, update in lockstep.
- [x] **agents.md API endpoint callouts added** for the 2 F9 endpoints (rendered at L2-renamed paths): `POST /api/connectors/{id}/peer-approvals/{id}/{approve|dismiss}` (F9 L3) and `DELETE /api/agents/{name}/connectors/{connector_id}` (F9 L5). Same callout discipline as the existing `__MASKED__` sentinel callout — somewhere a reader would naturally encounter when learning the API surface.
- [x] **agents.md F4-era prose pruned**: identify F4-era paragraphs that the M10 debrief should have retired but didn't; remove them. Use judgment (the implementing developer scans the M10 debrief's documentation-recommendations section for context); prune at least 1 obviously-stale paragraph. If nothing clearly stale surfaces, document the negative result in the flight-log entry.
- [x] **`_acl.py:438-448` inbound back-compat comment block retired**: the 9-line comment explaining the deny string's preservation is removed. The branch above (`elif agent_channels == []:` inbound) retains its semantic but no longer needs the back-compat justification.
- [x] **`_acl.py:170-173` outbound comment block retired**: the 4-line `# Per-agent DMs-only sentinel: ...` comment that describes the historical "DMs-only sentinel" name is replaced with a 1-line note matching the inbound retirement style.
- [x] **`_acl.py:174-179` outbound deny string updated**: the message `f"channel_id {channel_id!r} is not reachable for this agent on account {account_id!r} (DMs-only override; target is not a DM)"` is replaced with `f"channel_id {channel_id!r} is not reachable for this agent on account {account_id!r} (per-agent channels axis is explicitly empty)"`. Note: outbound retains the verb **"reachable"** (vs inbound's **"admitted"**) — these are the codebase's existing semantic conventions for the two directions.
- [x] **`_acl.py:449-455` inbound deny string updated**: the message `f"channel_id {channel_id!r} is not admitted for this agent on account {account_id!r} (DMs-only override; envelope is not a DM)"` is replaced with `f"channel_id {channel_id!r} is not admitted for this agent on account {account_id!r} (per-agent channels axis is explicitly empty)"` (parallels the sibling guilds/roles axes' messages a few lines below at `:466-471` and `:484-489`).
- [x] **`tests/test_connectors_acl.py` 4 test assertion sites updated to assert the new strings**:
  - Outbound (assert `"reachable"`): `:107` in `test_per_agent_channels_empty_is_dms_only_sentinel` (outbound class, line 97); `:137` in `test_per_agent_channels_empty_with_is_dm_false_denies` (outbound, line 123)
  - Inbound (assert `"admitted"`): `:322` in `test_per_agent_channels_empty_is_dms_only_sentinel` (inbound class, line 311); `:354` in `test_per_agent_channels_empty_with_is_dm_false_denies` (inbound, line 339)
  - All 4 sites: replace `"(DMs-only override; <target|envelope> is not a DM)"` substring with `"(per-agent channels axis is explicitly empty)"`. Test method names stay (they describe behavior, not the literal string).
- [x] **`tests/test_connector_send_tool.py:744-745` updated to assert the new outbound string**: the assertion `"[error] [constraint] channel_id 'c1' is not reachable for this agent on account 'acct-send' (DMs-only override; target is not a DM)"` becomes `"[error] [constraint] channel_id 'c1' is not reachable for this agent on account 'acct-send' (per-agent channels axis is explicitly empty)"`. Test method name and docstring may stay (sibling at `:725-726` is prose-only).
- [x] **`tests/test_provider_repository.py:24-35` fixture redesigned**: the `repo` fixture is converted from `def repo(encryptor):` + nested `_setup()` + `asyncio.get_event_loop().run_until_complete()` to `async def repo(encryptor):` directly awaiting `aiosqlite.connect(":memory:")` + `ensure_schema(conn)` + yielding the repository + `await conn.close()` in teardown. Under `pyproject.toml`'s `asyncio_mode = "auto"`, an async fixture is auto-detected; the 13 test functions consume `repo` as a plain value (no signature change at consumer sites).
- [x] **0 teardown errors in `tests/test_provider_repository.py`** after L3: `docker exec the-one pytest tests/test_provider_repository.py -x --timeout 30` shows 13 passed / 0 errors (was 0 passed / 13 errors pre-L3).
- [x] **Full backend suite WITHOUT the `--deselect` workaround**: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` is green at 2749+ passing (2736 from L2 + 13 previously-erroring-now-passing) / 4 skipped / 0 errors / 0 failures. This is the F11 acceptance state — no L3-deferred residue.
- [x] **Atomicity boundary**: `git diff --name-only main` minus the L1+L2 file set + L3's allowlist (`agents.md`, `_acl.py`, `test_connectors_acl.py`, `test_provider_repository.py`) returns empty. No surprise files touched.
- [x] **Flight log `Leg Progress` section** has an L3 entry summarizing the three sub-items + test results.
- [x] **Leg status updated to `landed`** in this file's header. **DO NOT commit** — Phase 2d batches the commits.

## Verification Steps

1. **Provider repository tests (regression net for the asyncio fixture redesign)**:
   - `docker exec the-one pytest tests/test_provider_repository.py -x --timeout 30`
   - Expect: 13 passed / 0 errors / 0 failures. The 13 errors that have been carried since F7 are gone.

2. **ACL tests (regression net for the deny-message retirement)**:
   - `docker exec the-one pytest tests/test_connectors_acl.py -x --timeout 30`
   - Expect: all green; the 4 tests with updated string assertions pass.

3. **Full backend suite WITHOUT the deselect workaround** (the L3 acceptance gate):
   - `docker exec the-one pytest --ignore=tests/browser -x --timeout 60`
   - Expect: 2749+ passing / 4 skipped / 0 errors / 0 failures. Wall-clock within ~10% of the L2 baseline (no regression).

4. **Browser suite** (unchanged from L2 — L3 doesn't touch frontend):
   - `docker exec the-one pytest tests/browser/ -x --timeout 120`
   - Expect: 431+ passed / 35 skipped / 14 deselected (the 2 pre-existing-main failures remain — not L3-caused; document as carry-forward).

5. **agents.md sanity** (manual visual check):
   - Read the M11 section at `agents.md:405+` to confirm 2 new convention blocks render correctly.
   - Read the per-axis-tri-state-override deep paragraph at `agents.md:678` to confirm 5-axis enumeration.
   - Spot-check the API endpoint callouts render at the expected location.
   - Confirm at least one F4-era prose paragraph removed.

6. **Atomicity boundary**:
   - `git diff --name-only main` should show only L1+L2 files + the 4 L3 files. Any file outside this allowlist = scope creep.

## Implementation Guidance

### Step 1 — agents.md structural sweep (FIRST per flight spec)

Five sub-items within agents.md:

**1a — Add `dms-orthogonal-to-guild-restriction` M11 convention block.** Add a new `### \`dms-orthogonal-to-guild-restriction\`` heading + 1-2 paragraph description under the `### Mission-specific (M11)` heading at `agents.md:405`. The convention captures the F10 L1 posture inversion: the substrate's DM admission is orthogonal to guild restrictions — operators expressing "DMs from approved peers + restricted guild channels" need both the account-scope `dm_admission` axis and the per-agent `admit_dms` opt-out to compose cleanly. Cite the origin (F10 L1 at `the_one/connectors/_acl.py`) + the test class that pins the behavior (`tests/test_connectors_acl.py`).

**1b — Add `backend-merged-replay` M11 convention block.** Add a new `### \`backend-merged-replay\`` heading + description under the same M11 section. The convention captures F9 L4's `_restore_session` shape: when a session is restored from disk, the backend merges messages + pending_approvals by timestamp into the unified history before broadcasting. The pattern is general: when restoring async UI state from multiple persistent stores keyed by time, merge at the backend (not the frontend) so consumers see a single ordered stream. Cite the origin (F9 L4 at `the_one/interfaces/web/app.py`'s `_restore_session`).

**1c — Extend per-axis-tri-state-override to 5 axes.** Find the deep application paragraph at `agents.md:678` that starts `"The account-scope config["allowlist"] and per-agent AgentConfig.connector_acls[account_id] admission surfaces both carry four parallel axes: peers, channels (cross-platform, F6 baseline), plus guilds and roles (Discord-flavored, F8 L8)..."`. Update:
  - `"four parallel axes"` → `"five parallel axes"`
  - Extend the enumeration: `"peers, channels (cross-platform, F6 baseline), plus guilds and roles (Discord-flavored, F8 L8), plus dm_admission (Discord DM admission scope, F10 L1)"`
  - If the prose later says "each axis is independently tri-state per the per-axis-tri-state-override convention", that wording stays — it generalizes to 5 axes naturally
  - The convention's own definition block at `agents.md:110-115` uses an ellipsis (`peers, channels, guilds, roles, …`) and cites F8 L8 as the third-occurrence extension. Add an F10 L1 fourth-occurrence citation in the same spot, recording `dm_admission` as the new axis added by F10 L1 (cycle-1 finding).
  
**1d — Add 2 F9 API endpoint callouts.** Locate the existing `__MASKED__` sentinel callout (currently at `agents.md:423-427`: `### \`__MASKED__\` sentinel (LLM providers)`). Add similarly-styled callouts (or a single combined "F9 Discord-native peer-approval + per-agent detach endpoints" subsection) for the 2 new endpoints, rendered with their L2-renamed paths:
  - `POST /api/connectors/{id}/peer-approvals/{id}/{approve|dismiss}` — F9 L3 Discord-native peer-approval action endpoints. Approve flips the `pending_approvals` row to `status='approved'` and adds the peer to the account allowlist; dismiss flips to `status='dismissed'` without mutating the allowlist.
  - `DELETE /api/agents/{name}/connectors/{connector_id}` — F9 L5 detach-from-Connectors-screen endpoint. Detaches the agent from the connector, releases the per-(agent, connector) pool entry, persists the connector_ids list change, and updates the connector account's attached-agents list without a page reload.
  
  Place the callouts in the "Subsystem contracts" section (starts at `agents.md:415`) where API surface conventions naturally live.

**1e — Prune F4-era prose.** The implementing developer reads the M10 debrief's documentation-recommendations section at `missions/10-bi-directional-comms-connectors/mission-debrief.md` (file verified to exist at this path during cycle-1) for context on what should have been pruned but wasn't. Look for F4-era prose paragraphs in agents.md that describe transient mid-flight state (e.g. paragraphs starting with "F4 L3 currently..." or paragraphs that say "TODO when X lands"). Prune at least 1 clearly-stale paragraph. If nothing clearly stale surfaces after a 5-minute scan, document the negative result in the flight log L3 entry ("F4-era prose audit completed — no clearly-stale paragraphs found; pruning deferred to a future routine-maintenance session").

### Step 2 — `_acl.py` anachronistic deny message retirement (BOTH outbound AND inbound — cycle-1 finding)

`_acl.py` has TWO symmetric deny blocks that BOTH need retirement. Note the different verbs and noun targets — `admits_outbound` says "reachable"/"target", `admits_inbound` says "admitted"/"envelope". These are the codebase's existing semantic conventions; preserve them.

**Step 2a — OUTBOUND block at `_acl.py:163-179`** (in `admits_outbound`):

Replace the existing block:
```python
        elif agent_channels == []:
            # Per-agent DMs-only sentinel: ``[]`` means "no non-DM
            # channels admitted; DMs only." The plugin-resolved
            # ``is_dm`` bool decides the branch — permit if the target
            # is a DM, else deny.
            if is_dm:
                return True, ""
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r} (DMs-only override; "
                f"target is not a DM)",
            )
```
with:
```python
        elif agent_channels == []:
            # Per-agent channels axis is explicitly empty: permit DMs, deny everything else.
            if is_dm:
                return True, ""
            return (
                False,
                f"channel_id {channel_id!r} is not reachable "
                f"for this agent on account {account_id!r} (per-agent "
                f"channels axis is explicitly empty)",
            )
```

**Step 2b — INBOUND block at `_acl.py:437-454`** (in `admits_inbound`):

Replace the existing 9-line back-compat comment block at `:440-448` + deny string at `:449-455`. The comment block starts with `# Pre-L1 this branch was the "DMs-only override"` and ends with `# ``admit_dms`` mechanism.`. The new shape:
```python
            elif agent_channels == []:
                # Per-agent channels axis is explicitly empty: deny all guild-context messages on this account for this agent.
                return (
                    False,
                    f"channel_id {channel_id!r} is not admitted for this "
                    f"agent on account {account_id!r} (per-agent channels "
                    f"axis is explicitly empty)",
                )
```

This parallels the sibling guilds-axis message (`:466-471`) which already uses the form "(per-agent guilds axis is explicitly empty)".

### Step 3 — Test assertion updates across 2 test files (cycle-1 expanded)

**5 assertion sites total across 2 files** — 3 outbound + 2 inbound. The outbound sites pin the OUTBOUND deny string (`"target is not a DM"`); the inbound sites pin the INBOUND deny string (`"envelope is not a DM"`). Update each to match the new strings from Step 2.

**Outbound assertion sites** (assert `"reachable"` + `"target"` historically; now `"reachable"` + `"per-agent channels axis is explicitly empty"`):
- `tests/test_connectors_acl.py:107` — assertion inside `test_per_agent_channels_empty_is_dms_only_sentinel` (outbound class, method at line 97). The current 2-line string-concatenated assertion `"channel_id 'C1' is not reachable for this agent on account "` + `"'acc-1' (DMs-only override; target is not a DM)"` becomes `"channel_id 'C1' is not reachable for this agent on account "` + `"'acc-1' (per-agent channels axis is explicitly empty)"`.
- `tests/test_connectors_acl.py:137` — assertion inside `test_per_agent_channels_empty_with_is_dm_false_denies` (outbound, method at line 123). Same shape as `:107`.
- `tests/test_connector_send_tool.py:744-745` — assertion inside `test_deny_when_per_agent_acl_channels_is_empty_dms_only_stub` (or similarly-named method around that line). The current 3-line string-concatenated assertion ending `"(DMs-only override; target is not a DM)"` becomes ending `"(per-agent channels axis is explicitly empty)"`. The `[error] [constraint]` prefix stays.

**Inbound assertion sites** (assert `"admitted"` + `"envelope"` historically; now `"admitted"` + `"per-agent channels axis is explicitly empty"`):
- `tests/test_connectors_acl.py:322` — assertion inside `test_per_agent_channels_empty_is_dms_only_sentinel` (inbound class, method at line 311). The current string `"'acc-1' (DMs-only override; envelope is not a DM)"` becomes `"'acc-1' (per-agent channels axis is explicitly empty)"`.
- `tests/test_connectors_acl.py:354` — assertion inside `test_per_agent_channels_empty_with_is_dm_false_denies` (inbound, method at line 339). Same shape as `:322`.

**Test method names + docstrings**: stay as-is. `dms_only_sentinel` is the historical lineage name; renaming would obscure git blame. (Spec also says don't touch test class names — same defer rationale.) The docstring at `:98-100` says "DMs-only sentinel" — accurate as lineage, misleading as current semantic, but defer update for the same lineage-preservation reason.

**Mechanical verification**: after Steps 2 + 3, `grep -rn "DMs-only override" the_one/ tests/` returns 0 hits. The only remaining historical references to the phrase live in this leg's spec + flight artifacts.

### Step 4 — `tests/test_provider_repository.py` fixture redesign

Current shape (lines 24-35):
```python
@pytest.fixture()
def repo(encryptor):
    """Yield a LLMProviderRepository backed by an in-memory DB."""

    async def _setup():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await ensure_schema(conn)
        return conn

    conn = asyncio.get_event_loop().run_until_complete(_setup())
    yield LLMProviderRepository(conn, encryptor)
    asyncio.get_event_loop().run_until_complete(conn.close())
```

Target shape:
```python
@pytest.fixture()
async def repo(encryptor):
    """Yield a LLMProviderRepository backed by an in-memory DB."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await ensure_schema(conn)
    yield LLMProviderRepository(conn, encryptor)
    await conn.close()
```

Key changes:
- `def repo` → `async def repo`
- Drop the nested `_setup()` function entirely
- Inline the `aiosqlite.connect(":memory:")` + `ensure_schema(conn)` awaits
- Replace `asyncio.get_event_loop().run_until_complete(conn.close())` with `await conn.close()`

The 13 test functions at lines 53, 59, 70, 84, 101, 112, 126, 140, 149, 157, 166, 175, 183 already `async def test_*` and use `repo` as a value — no signature changes needed at consumer sites under `asyncio_mode = "auto"`.

If the `import asyncio` at the top of the file is now unused (after removing the `run_until_complete` calls), remove it. Spot-check with `grep -n '^import asyncio\b\|^from asyncio\b' tests/test_provider_repository.py` and check usage with `grep -n 'asyncio\.' tests/test_provider_repository.py`.

If the `@pytest.mark.asyncio` decorators on test functions are now redundant under `asyncio_mode = "auto"`, leave them alone — removing them is out of L3 scope (separate cleanup that might surface unexpected test-collection differences).

### Step 5 — Run tests

```bash
# Focused: provider repo tests (the L3-specific regression net):
docker exec the-one pytest tests/test_provider_repository.py -x --timeout 30
# Expect: 13 passed / 0 errors / 0 failures.

# Focused: ACL tests (deny-string retirement regression net):
docker exec the-one pytest tests/test_connectors_acl.py -x --timeout 30
# Expect: all green; the 4 updated tests pass.

# Broad: full backend suite WITHOUT the deselect workaround (L3 acceptance gate):
docker exec the-one pytest --ignore=tests/browser -x --timeout 60
# Expect: 2749+ passing / 4 skipped / 0 errors / 0 failures.

# Browser suite (unchanged from L2):
docker exec the-one pytest tests/browser/ -x --timeout 120
# Expect: 431+ passed / 35 skipped / 14 deselected.
```

If the provider-repo tests still error after the fixture redesign: the fixture's `aiosqlite` import or `LLMProviderRepository` constructor signature may have changed since F7. Re-read the imports + class definition and adjust.

If the ACL tests fail because the assertion substring doesn't match: re-read `_acl.py:449-455` and confirm the new f-string literal matches the test assertion exactly (line-wrap whitespace in the f-string matters — `f"... is not admitted for this " f"agent on account..."` is two adjacent string literals concatenated; the joined value has a single space between "this" and "agent").

### Step 6 — Update flight log and leg status

- Append entry to `../flight-log.md` under `## Leg Progress` summarizing:
  - agents.md sweep: 2 new conventions promoted, per-axis-tri-state-override extended to 5 axes, 2 API endpoint callouts added, F4-era pruning result (paragraph count + result of negative result)
  - _acl.py: deny block retired (9-line comment removed, deny string updated to match guilds-axis sibling style)
  - test_provider_repository.py: fixture converted from sync `run_until_complete` to async; 13 tests now pass
  - Test results (counts + timing + count delta from F10 baseline)
  - Atomicity-boundary verification
- Update this leg artifact's header `**Status**: in-flight` → `**Status**: landed`.
- Do NOT update the flight-spec leg checkbox to `[x]` (commit leg does that).
- Do NOT commit. Do NOT `git add`. Signal `[HANDOFF:review-needed]` per the leg-execution crew's Implement prompt.

## Edge Cases

- **`per-axis-tri-state-override` convention's own block (line 110-115)**: re-read to see if it references a specific axis count or names specific axes. If yes, update in lockstep with the deep paragraph. If the block is purely abstract (just describes the tri-state pattern without naming axes), leave it.
- **The deny-string-change ripple to outbound + inbound tests**: the L3 spec lists 5 assertion sites across 2 test files. If during implementation any line numbers drift, use these greps as the canonical source: `grep -n "DMs-only override; target is not a DM" tests/` (outbound — should return 3 hits: 2 in `test_connectors_acl.py`, 1 in `test_connector_send_tool.py`); `grep -n "DMs-only override; envelope is not a DM" tests/` (inbound — should return 2 hits in `test_connectors_acl.py`). If hit counts differ, update all sites discovered.
- **`pyproject.toml` asyncio_mode = "auto"**: this is at `pyproject.toml:57`. Under auto mode, async fixtures are auto-detected and test consumers receive the yielded value directly. If for some reason the fixture redesign causes "fixture coroutine not iterable" errors, the asyncio_mode may have changed; re-verify.
- **`_acl.py:466-471` and `:484-489`**: these are the sibling guilds-axis and roles-axis deny messages whose style the new channels-axis message should mirror. The implementing developer should read them to confirm the parallel phrasing before writing the new message.
- **agents.md M11 section currently has just `studio-event-bus`**: the section is small enough that adding 2 new conventions doubles its density. That's expected and correct — F11 promotes M11-pattern conventions filed during F9/F10 implementation that didn't have a home until now.
- **Test fixture method name (do not rename)**: `test_per_agent_channels_empty_is_dms_only_sentinel` is a historical name — the branch USED TO BE the DMs-only sentinel. The name documents the lineage. Renaming would obscure git blame; defer indefinitely.
- **Flight log entry for the F4-era pruning negative result**: even if nothing is pruned, document the audit attempt. Future routine-maintenance sessions need to know this was looked at.
- **`asyncio_mode = "auto"` redundant decorators**: the 13 `@pytest.mark.asyncio` decorators on the test functions are redundant under auto mode but harmless. Leave them — removing is a separate cleanup beyond L3's stated scope.

## Files Affected

**agents.md (sweep):**
- `the_one/agents.md` — 5 sub-items: 2 new convention blocks + per-axis-tri-state-override extension + 2 API endpoint callouts + F4-era pruning (≥1 paragraph)

**_acl.py + ACL tests (deny retirement — outbound + inbound, cycle-1 expanded):**
- `the_one/connectors/_acl.py:163-179` — outbound comment + deny string updated
- `the_one/connectors/_acl.py:437-454` — inbound comment block removed, deny string updated
- `tests/test_connectors_acl.py` — 4 test assertions updated (`:107`, `:137`, `:322`, `:354`)
- `tests/test_connector_send_tool.py:744-745` — 1 test assertion updated (cycle-1 finding)

**Provider repository fixture redesign:**
- `tests/test_provider_repository.py:24-35` — fixture converted; possibly drop `import asyncio` if now unused

**Flight artifacts:**
- `missions/11-discord-connector-depth/flights/11-connector-rename-and-housekeeping/flight-log.md` — append L3 progress entry
- This file (`legs/03-housekeeping-bundle.md`) — status → `landed`

**Explicitly NOT affected in L3:**
- Any L1 file (Python substrate identifiers, schema, etc.)
- Any L2 file (API routes, JS, CSS, browser tests)
- `docker-compose.yml` (operator's local dev state)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (agents.md sweep, deny retirement, fixture redesign, test gates)
- [x] L3 atomicity boundary verified (no L1/L2 file re-touches)
- [x] Full backend suite without `--deselect` workaround is green (2749+ passing, 0 errors)
- [x] Browser suite unchanged from L2 baseline (431+ passing)
- [x] Flight-log L3 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all three legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-28, leg-design time):

| Citation | Classification | Resolution |
|----------|----------------|------------|
| `the_one/connectors/_acl.py:163-179` outbound deny block (cycle-1 added) | OK | Verified by `sed -n '160,180p'` — comment at :170-173, deny string at :174-179 with `"(DMs-only override; target is not a DM)"` substring |
| `the_one/connectors/_acl.py:437-454` inbound deny block | OK | Verified by `sed -n '430,470p'` — comment block at :440-448, deny statement at :449-455. The exact byte-string `"(DMs-only override; envelope is not a DM)"` confirmed at :452-453 |
| `tests/test_connectors_acl.py:97` outbound `test_per_agent_channels_empty_is_dms_only_sentinel` (assertion at `:107`) | OK | Verified by `grep -n` — test at :97; assertion of outbound deny string at :107 |
| `tests/test_connectors_acl.py:123` outbound `test_per_agent_channels_empty_with_is_dm_false_denies` (assertion at `:137`) | OK | Verified — test at :123; assertion at :137 |
| `tests/test_connectors_acl.py:311` inbound `test_per_agent_channels_empty_is_dms_only_sentinel` (assertion at `:322`) | OK | Verified — inbound test at :311; assertion of inbound deny string at :322 |
| `tests/test_connectors_acl.py:339` inbound `test_per_agent_channels_empty_with_is_dm_false_denies` (assertion at `:354`) | OK | Verified — inbound test at :339; assertion at :354 |
| `tests/test_connector_send_tool.py:744-745` outbound deny-string assertion (cycle-1 added) | OK | Verified by `grep -n "DMs-only override" tests/test_connector_send_tool.py` — single hit at :744 |
| `missions/10-bi-directional-comms-connectors/mission-debrief.md` (F4-era pruning reference) | OK | Cycle-1 confirmed file exists at this path |
| `tests/test_provider_repository.py:24-35` `repo` fixture (sync + `run_until_complete`) | OK | Verified by `sed -n '15,38p'` — fixture at :24, `_setup` async function inside, `run_until_complete` at :33 and :35 |
| `pyproject.toml:57` `asyncio_mode = "auto"` | OK | Verified by `grep -nE "asyncio_mode"` |
| `the_one/agents.md:110` `per-axis-tri-state-override` heading | OK | Verified by `grep -nE` — convention heading at line 110 |
| `the_one/agents.md:405` `### Mission-specific (M11)` heading | OK | Verified — M11 section starts at 405, currently has only `studio-event-bus` at 407 |
| `the_one/agents.md:678` "four parallel axes" deep paragraph | OK | Verified by grep — the paragraph cites "four parallel axes: peers, channels (cross-platform, F6 baseline), plus guilds and roles (Discord-flavored, F8 L8)" |
| `the_one/agents.md:423-427` `__MASKED__` sentinel callout (style reference for API callouts) | OK | Verified — sentinel callout exists at the cited location for style reference |
| 13 `test_provider_repository.py` test lines (53, 59, 70, 84, 101, 112, 126, 140, 149, 157, 166, 175, 183) | not re-verified | Flight log + spec architect cycle-1 are the source. Implementing developer re-verifies via grep `^async def test_` if precise lines matter (they don't for the fixture redesign — the fix is at the fixture site only). |

12 citations verified; 0 drift; 0 `gone`. The fixture-pattern citation (`tests/test_provider_repository.py:24-35`) was the architect-cycle-1-reclassified surface — confirmed live.
