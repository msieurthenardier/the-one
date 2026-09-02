# Leg: directory-tool-and-gate

**Status**: completed
**Flight**: [Telegram and the Name Directory](../flight.md)

## Objective

Land the `find_platform_destination` lookup tool with its connector-level read authorization and literal-key candidate translation, generalize the DD-6 carve-out to the connector tool pair, finalize the `directory-lookup-send` behavior spec — and hand the Flight Director a runnable mechanical gate (AC-8 equivalent: the FD runs the stub behavior test post-handoff; the leg lands only when it passes).

## Context

- Flight DD-5 (tool contract — read it in full: description-guided `connector_id` omission, ≤10 newest-first, zero-match message, connector-level scoping ruling), DD-6 (pair seeding), DD-10 (the gate), DD-11 (this leg shares the non-Telegram bucket; leg 1 used 450 — report the delta).
- **Tool name PINNED**: `find_platform_destination` (the behavior spec finalization uses it; changing it post-gate is a spec re-author).
- Leg 1's landed surface: `ConnectorDirectoryRepository.search(agent_name, query, connector_id=None)` returns RAW rows — THIS leg owns the DD-5 literal-key translation: `kind=='peer'` → candidate carries `peer_id`; `kind=='channel'` → `channel_id` (+ `thread_id` when set); never a generic `platform_id` in the tool's output. Candidates also carry `connector_id`, connector `name`, `kind`, `display_name`, `username`, `last_seen`.
- Tool construction mirrors `SendToPlatformChannelTool` (`tools/connector_send.py`): per-agent instance receiving `agent_name` at registration (the parameter-source audit's answer — the caller identity is construction-time state, not model input); resolves the running manager/repositories the same way — EXCEPT no encryptor (the directory repository takes none; do not copy `connector_send.py`'s encryptor-construction lines). **Registration (review HIGH — the tool is inert without it)**: add `"find_platform_destination": FindPlatformDestinationTool` to `_TOOL_CLASSES` in `the_one/tools/builtins.py`, mirroring the send tool's entry — the sole seam through which built-ins reach the registry and thus the DD-6 seed check. Read-only: NO authorization error paths beyond scoping — out-of-scope rows are simply absent from results (enumeration reveals nothing).
- **Connector-name enrichment (review HIGH, designer ruling)**: `ConnectorDirectoryRepository.search`'s SQL gains a plain JOIN to `connectors` returning `connector_name` as one more RAW column (plaintext `name` column; no encryptor, no per-candidate `ConnectorRepository.get`). **Cycle-2 must-fix included**: `db/models.py::ConnectorDirectoryEntry` gains `connector_name: str | None = None` — without the field, pydantic's default `extra="ignore"` silently DROPS the JOIN column and the enrichment is a no-op (`get()` never populates it; only `search()`'s enriched rows do). Also update the repository class docstring's raw-row enumeration with one sentence: "RAW" describes key-translation status (platform_id/thread_id untranslated), not single-table provenance — the JOIN is a compatible extension of leg 1's boundary, not a breach. This is a small amendment to leg-1-landed code — permitted (uncommitted tree, flight-end review covers it); update leg 1's repository tests accordingly and note the amendment in the flight log.
- **Candidate serialization PINNED (review — the same literal-copy risk the flight's HIGH fix targeted)**: the tool returns ONE compact JSON array of candidate objects (each with exactly the documented keys), never prose-with-inline-ids; the zero-match case returns the clear message, not an empty array without explanation.
- Tool description (part of the contract — the carve-out seeds `to_schema()`): documents the query semantics, the omit-`connector_id`-unless-you-have-an-id-from-a-prior-result guidance (flight cycle-1 medium), and that returned ids paste directly into `send_to_platform_channel`'s `target`.
- DD-6: `agent/factory.py`'s sanctioned seed block — seed BOTH `send_to_platform_channel` and `find_platform_destination` when each is registry-present (a two-name iteration; `agent/core.py` UNTOUCHED — the seed/reset mechanism already handles N entries). This is the leg's ONLY frozen-loop-adjacent touch and it stays inside the already-sanctioned block.
- Pin tests (extend `tests/test_factory.py::TestSendToolCarveOut` + visibility suites): (a) pair seeded when both enabled; (b) each independently absent when disabled (2 cases); (c) reset survival for both; (d) `search_tools` match on either does not duplicate; (e) baseline otherwise unchanged. **Existing-assertion breakage (review MEDIUM-HIGH — handle explicitly, not incidentally)**: two landed exact-shape assertions break in the two-tool world — `test_baseline_otherwise_unchanged` (exact 2-element list) and `test_no_duplication_on_search_match` (`len == 1`); designer ruling: EXTEND the existing fixtures (`disabled-agent` gains the new tool name in `disabled_tools`) and REWRITE those two assertions in place for the pair-seeded baseline, with a comment citing this leg — no fixture split.
- Behavior spec finalization (`tests/behavior/directory-lookup-send.md` → status `active`): pin the tool name, exact seam payloads (the `peer_username` field landed in leg 1's stub-seam passthrough — the draft's step-1 hedge becomes an assertion), and apply the review's judgeability fix (designer-ruled): **step 1's Expected Result narrows to the browser-observable session claim ONLY** (each row must be judgeable at its own row; no deferred-evidence claims, no unmarked mixed frames); **step 2's Expected Result explicitly gains the directory-population proof** — the lookup candidate's presence with display name "Marisol Vega" IS the evidence the directory was populated. Spec must pass ARTIFACTS.md Phase-1 shape validation.
- The gate RUN is the FD's (per the flight-end-review precedent: the leg's Developer makes it runnable and hands off; the FD runs `/behavior-test directory-lookup-send` and lands the leg on PASS). Environment: the standing scratch dir (`/tmp/the-one-behavior-test-scratch`) upgrades to v39 on next boot; stub gate env `THE_ONE_STUB_TEST_ENDPOINT=1`; `test-agent` on gpt-oss:20b (mission floor) with BOTH tools enabled and the bare prompt; a stub connector with the test peer allowlisted (the draft's ADMIT-audited precondition).
- Docs: `connectors/README.md` gains the lookup tool's contract (scoping ruling quoted); `agents.md` index bullet.

## Inputs
- Legs 1-2 landed (uncommitted): repository + raw search live; suite 3,852.

## Outputs
- `the_one/tools/connector_lookup.py` (suggested) — the tool.
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` entry (the registration seam).
- `agent/factory.py` — the seed `if` becomes a two-name `for` loop over `(SEND_TO_PLATFORM_CHANNEL_TOOL_NAME, FIND_PLATFORM_DESTINATION_TOOL_NAME)` — the leg's only frozen-adjacent touch, inside the sanctioned block.
- `db/repositories.py` — `search`'s JOIN enrichment (`connector_name` raw column) + docstring boundary sentence + leg-1 test updates.
- `db/models.py` — `ConnectorDirectoryEntry.connector_name: str | None = None` (cycle-2 must-fix).
- `tests/test_connector_lookup_tool.py` (+ carve-out pin extensions incl. the two rewritten exact-shape assertions).
- `tests/behavior/directory-lookup-send.md` finalized (`active`).
- README/agents.md doc touches.

## Acceptance Criteria

- [x] **AC-1 Tool contract**: query matching (substring, case-insensitive, display_name OR username), ≤10 newest-first, zero-match message naming the query, literal-key candidates (peer_id vs channel_id+thread_id per kind — a peer candidate NEVER carries channel keys and vice versa, asserted), connector name included; unit tests per behavior.
- [x] **AC-2 Scoping**: connector-level authorization via the leg-1 repository semantics exercised THROUGH the tool (bound-via-channel_map-only caller sees the connector's other rows; unbound agent gets empty results, not an error).
- [x] **AC-3 Schema/description**: `target`-compatibility and the connector_id-omission guidance present in the tool description; schema `required` honors the property-order invariant (`tests/test_tool_base.py` global rule — Flight 3's DD-11 lesson).
- [x] **AC-4 Pair seeding**: the five pin cases above green; `git diff the_one/agent/` shows ONLY the factory seed-block iteration.
- [x] **AC-5 Spec finalized**: `directory-lookup-send.md` `active`, tool name pinned, seam payloads exact (incl. `peer_username`), shape-valid per ARTIFACTS.md; step-1 expected result reads through a surface the spec names.
- [x] **AC-6 Budget + suite**: bucket delta reported (leg 1 used 450 of the 350 target — this leg's addition reported against DD-11's ruling); `make test-unit` green (baseline 3,852); no new deps.
- [x] **AC-7 Gate (FD-run, blocks leg landing)**: `/behavior-test directory-lookup-send` PASSES; run log committed. Verified AFTER the Developer hands off.

## Verification Steps
- Scoped foreground runs (tool + factory + visibility files); `make test-unit` once at leg end (foreground, 600000 ms).
- AC-7: FD boots the dev instance (scratch dir, stub gate env, port 8485), verifies test-agent model + both tools enabled + stub connector/allowlist, runs the behavior test.

## Implementation Guidance
1. Tool first (mirror connector_send's construction/DB-access/registration patterns and its raw-`Request`-free tool shape). 2. Seed iteration + pin tests. 3. Spec finalization LAST (against the real tool's name/schema). 4. Foreground-only test discipline (explicit timeouts to 600000 ms; never background; never end a turn with a command pending); `uv sync` with `--extra dev --extra all-llms --extra gui`.

## Edge Cases
- **Query matching a peer AND a channel** (same connector): both candidates returned with their distinct key shapes — asserted.
- **Duplicate display_name across connectors**: both returned; connector `name` disambiguates (the RQ11 duplicate rationale) — asserted.
- **username-only match** (display name mismatch): returned.
- **Empty query / whitespace**: clear error message, no full-table dump.
- **Directory entry for a connector deleted mid-session**: leg 1's delete-cleanup makes this transient; a stale row surviving a race returns a candidate whose send then fails authorization — acceptable, note in the tool docstring.

## Files Affected
(see Outputs)

## Citation Audit (2026-09-02, amended post-review)
Against the leg-2 tree: `tools/connector_send.py` construction/agent_name pattern + property-order invariant precedent; `tools/builtins.py::_TOOL_CLASSES` (the registration seam — review-added, verified `"send_to_platform_channel"` entry at `builtins.py:66`); `agent/factory.py` seed block at `:401-404`; `db/repositories.py::ConnectorDirectoryRepository.search` at `:781-832` (raw-row contract, JOIN amendment ruled); `api.py` stub seam with `peer_username` passthrough (leg 1); `tests/test_factory.py::TestSendToolCarveOut` at `:753-878` incl. the two exact-shape assertions at `:799`/`:836`. All live on the branch.

---

## Post-Completion Checklist
**Flight-end commit model — do NOT commit and do NOT signal `[COMPLETE:leg]`:**
- [x] AC-1..AC-6 verified (AC-7 is the FD's post-handoff gate)
- [x] Tests passing (`make test-unit` foreground)
- [x] Flight log updated
- [x] Leg status left `in-flight` — the FD sets `landed` after AC-7 passes
- [x] Signal `[HANDOFF:review-needed]`
