# Leg: schema-and-shared

**Status**: completed
**Flight**: [Telegram and the Name Directory](../flight.md)

## Objective

Execute the v39 migration (connector-type CHECK admitting `'telegram'` + the `connector_directory` table), land the lockstep type set, the directory repository with its passive-population hooks and named consumers (session titles, delete cleanup), and the `keying_to_target` extraction — the flight's entire shared-code surface in one high-risk leg, per the DD-1 enumeration.

## Context

- Flight DD-3 (v39, mission RQ10's exact scope), DD-4 (directory schema + population incl. the channel-ungated cycle-2 decision), DD-7 (session titles), DD-8 (extraction), DD-1a-g (the named shared touches — this leg delivers a, b, c-partial (Discord channel capture; Telegram's is leg 2), d-partial (hooks; the tool is leg 3), f, g).
- Mission constraint: v39 is the LAST authorized migration step. Its scope is exact — the CHECK change (via the established ceremony) and the `connector_directory` table. Anything more is a `[BLOCKED]` stop, not an improvisation.
- The migration ledger's house pattern: version-gated blocks appended after `if version < 38:` (ends `schema.py:2265`, `INSERT OR IGNORE ... VALUES (38)` last); v19 (`schema.py:~745-825`) is the documented CHECK-change ceremony to follow — a NEW constraint via table-rewrite, never editing frozen history. Mind v38's own rewind-re-run commentary (`schema.py:1064+`): the v39 block must be idempotent and tolerant of the rewind-re-run test pattern (`tests/test_db_migration.py` deletes schema_version rows and re-runs).
- Lockstep type set (all four in ONE change): `db/models.py` `Connector.type` Literal + `_CONNECTOR_TYPES` + the import-time assert; `api.py::_creatable_connector_types` (gate-aware — `'telegram'` joins `'discord'` as unconditional).
- Repository pattern: `ConnectorRepository` (`db/repositories.py:600`) is the shape reference — but `connector_directory` holds NO secrets: no encryptor, plain rows (DD-4). Two named methods: `search(agent_name, query, connector_id=None)` and `get(connector_id, kind, platform_id)`. **Search scoping is CONNECTOR-LEVEL by design** (designer ruling, 2026-09-02, resolving the review's question): a connector is in scope when the caller appears anywhere in its binding (`default_agent` or any `channel_map` value) — a deliberate simplification, NOT per-target precision. Rationale: send-time authorization remains the real per-target gate (unchanged); the lookup exposes only names within one connector, which is one operator trust domain; per-target search filtering would duplicate the send matrix for marginal privacy inside a domain the operator already configured. AC-3 tests the connector-level behavior deliberately. **Return-shape boundary** (second ruling): the repository returns RAW rows (`kind`, `platform_id`, `thread_id`, names) — leg 3's tool performs the DD-5 literal-key translation (`peer_id`/`channel_id`); the boundary is pinned here so leg 3 doesn't guess.
- Population hooks:
  - Peers: `dispatch_inbound` (`connectors/inbound.py`) — upsert IMMEDIATELY after `is_admitted` passes and BEFORE the `/new` and `should_reply` early returns (DD-4's pinned placement; the silence guarantee holds because unadmitted returns happen first). `InboundEnvelope` (`connectors/base.py:20-38`) gains OPTIONAL `peer_username: str | None = None` (frozen dataclass — additive field with default; grep ALL construction sites: discord plugin, stub seam `stub_test_inbound` in api.py (DD-1f passthrough), tests).
  - Discord channels: where `_resolve_channel_type` already fetches channel metadata (`discord/plugin.py`), capture `name` → directory upsert (channel entries deliberately NOT admission-gated — DD-4 cycle-2 decision, quote it in the code comment). Threads: when the resolved channel is a thread type, store per DD-4's rule (`platform_id` = send-addressable id, `thread_id` alongside).
  - Upsert-on-change only (skip identical name+username) — the write-per-message guard.
- DD-7: `resolve_session` (`inbound.py:132`) / `_session_title` (`inbound.py:128`) — channel sessions title from `directory.get(...)` `display_name` when present, else the raw id as today. Creation-time only.
- DD-8: `connector_send._resolve_default_target` (`tools/connector_send.py:89`) currently mirrors `resolve_session`'s keying by comment — extract the shared `keying_to_target(session) -> SendTarget | None` helper (home: `connectors/base.py` or a small `connectors/_keying.py`); returns **None for a non-connector-bound session** so `_resolve_default_target`'s existing "not bound to a platform conversation" error string stays reachable through the extraction (design review: the error-path handoff pinned); `_resolve_default_target` consumes it; existing DD-11 tests keep passing unmodified (behavior-preserving; the dataclass field names already match the dict shapes it builds today).
- DD-1g: `delete_connector` (`api.py:2882`) gains one deterministic `connector_directory` DELETE for the connector's rows.
- Budget: this leg + leg 3's tool share the ≤350 non-Telegram bucket; report counts. **FD budget ruling recorded up front** (design review projected this leg alone at ~380-450 against house doc density): the DD-11 sub-buckets and flight total (≤700) are TARGETS; the stop-and-split TRIGGER remains the mission ceiling (3,000 — 1,218 slack at branch cut). A doc-density-driven overrun of a target is reported in the flight log, not silently absorbed and not grounds to trim the DD-citing comment pattern; if actual counts project beyond the MISSION slack, stop the leg. (Cycle-2 correction: no leg-level flight-ceiling number — DD-11 stays the flight's single budget authority.)

## Inputs
- Clean tree on `flight/04-telegram-and-directory` cut from `ec2a0e0` (Flights 1-3 + turnaround merged); suite baseline 3,758.
- `CURRENT_VERSION = 38` (`schema.py:14`).

## Outputs
- `db/schema.py`: v39 block + `CURRENT_VERSION = 39`.
- `db/models.py`: lockstep type set.
- `db/repositories.py`: `ConnectorDirectoryRepository` (+ wiring where repositories are constructed, mirroring siblings).
- `connectors/base.py`: `peer_username` field; `keying_to_target` (or `_keying.py`).
- `connectors/inbound.py`: peer upsert hook; DD-7 titles; extraction consumption alignment.
- `connectors/discord/plugin.py`: channel-name capture (+ username into envelopes).
- `the_one/interfaces/web/api.py`: stub-seam `peer_username` passthrough; delete-route cleanup.
- `the_one/tools/connector_send.py`: `_resolve_default_target` consumes the shared helper.
- Tests: migration (v39 applies + idempotent + rewind-re-run tolerant + CHECK accepts telegram/rejects unknown), repository (search scoping incl. agent-authorization, get, upsert-on-change), hooks (admitted peer recorded pre-early-return incl. on `/new` and non-replying channels; unadmitted NOT recorded; channel capture incl. thread shape; username passthrough all three construction sites), DD-7 titles (named when known, raw id else), DD-8 extraction (existing tests unmodified + helper unit tests).

## Acceptance Criteria

- [x] **AC-1 v39 applies live**: against a fresh scratch DB and against a v38 DB, `ensure_schema` lands v39; `connectors.type` accepts `'telegram'` and still rejects an unknown type (CHECK asserted both ways); `connector_directory` exists with the DD-4 columns incl. `thread_id`; idempotent on re-run and tolerant of the rewind-re-run pattern; `CURRENT_VERSION = 39`. Unit-asserted in the migration test file's house style.
- [x] **AC-2 Lockstep set**: Literal + `_CONNECTOR_TYPES` + assert + `_creatable_connector_types` all gain `'telegram'` in one change; the assert passes; a Studio-bound `GET /api/connectors/types` (route test) lists telegram unconditionally.
- [x] **AC-3 Repository**: `search` returns only candidates from connectors where the caller matches `default_agent` OR appears in any `channel_map` value (positive + negative test), AND — the connector-LEVEL breadth the ruling means — a connector bound to the caller only via ONE `channel_map` entry (different `default_agent`) still surfaces directory rows from that connector's OTHER channels and peers (explicit test; an accidental per-target filter must fail it); substring match on display_name OR username, case-insensitive, ≤10 newest-first; `get` exact-match; upsert-on-change skips identical writes (asserted via row `last_seen` or write-count seam).
- [x] **AC-4 Peer hook placement**: an admitted peer's `/new` message AND an admitted peer's message in a non-replying channel BOTH record directory entries; an unadmitted peer's message records NOTHING (the silence guarantee's directory extension); `peer_username` flows from all three construction sites (discord author.username, stub seam body field, direct construction default None).
- [x] **AC-5 Discord channel capture**: the existing channel-resolution path upserts `(channel id, name)`, with the name cached alongside the type in `channel_type_cache` — so a channel's name is captured once per PROCESS LIFETIME and a RENAME is observed only after a process restart clears the cache (cycle-2 correction: the cache deliberately survives reconnects — `_AccountState`'s documented contract; the honest trade-off, stated — live rename-tracking would need a fetch cadence this leg deliberately doesn't add; the upsert-on-change guard applies at each capture, it does not imply live tracking). Thread-typed channels store the DD-4 thread shape. A code comment notes that a channel whose only pre-human traffic is dropped bot/self messages gets its entry on the first qualifying message.
- [x] **AC-6 Session titles**: a channel session created AFTER its directory entry exists is titled with `display_name`; before, the raw id (both asserted); DM titles unchanged.
- [x] **AC-7 Extraction**: `keying_to_target` exists in its named home; `_resolve_default_target` consumes it; ALL existing DD-11 default-target tests pass UNMODIFIED; helper unit tests cover peer-keyed, channel-keyed (+thread), and non-connector rows; the degenerate connector-bound-but-keyless branch (`connector_send.py:126-133`) MOVES into `keying_to_target` (returning None) so the helper is the single keying authority.
- [x] **AC-8 Delete cleanup**: deleting a connector removes its directory rows (asserted); other connectors' rows untouched.
- [x] **AC-9 Budget + suite**: non-Telegram bucket count reported (this leg's share of ≤350); `make test-unit` green; no new deps.

## Verification Steps
- Scoped foreground runs per touched test file (`PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x --timeout 30`); migration tests against real temp DBs.
- AC-1 live-DB half: a throwaway scratch data dir boot (`THE_ONE_DATA_DIR=$(mktemp -d) THE_ONE_PORT=8485 ...`) reaching v39, then teardown — no reuse of the standing behavior-test scratch (its DB is wanted for leg 3/4 continuity; it upgrades then too, note in the log).
- `make test-unit` once at leg end, foreground, 600000 ms timeout.

## Implementation Guidance
1. v39 first (ceremony per v19's documented pattern; read v38's rewind commentary before writing a line). 2. Lockstep set + route test. 3. Repository + tests. 4. `peer_username` field + all construction sites in one pass (grep `InboundEnvelope(` project-wide). 5. Hooks (peer placement exact; discord capture). 6. DD-7 titles. 7. DD-8 extraction LAST (behavior-preserving refactor over a green base). 8. Foreground-only test discipline (explicit timeouts up to 600000 ms; never background; never end a turn with a command pending); `uv sync` always with `--extra dev`.

## Edge Cases
- **Rewind-re-run**: v39 needs LESS machinery than v19/v23 (design review clarification — don't over-build): the CHECK ceremony rewrites `connectors` into the same name with no later rename, so an unconditional CREATE-new/INSERT/DROP/RENAME is naturally idempotent on a stamp-only rewind (the v38 "unconditional step, safe to repeat" precedent); `connector_directory` is a brand-new table — `CREATE TABLE IF NOT EXISTS` per the v21 precedent, never the rewrite ceremony.
- **Directory upsert during a turn that later fails**: the peer entry stays (observation is observation) — assert the upsert isn't rolled back with agent errors.
- **Same platform_id as peer AND channel** (Telegram DMs use chat ids): the `kind` column separates them; PK covers it — test it.
- **Empty display_name** (platform sends none): fall back to username, else the raw id — never an empty-string name in the directory.
- **`search` with an unbound agent** (no connector names it): empty result, not an error.

## Files Affected
(see Outputs)

## Citation Audit (2026-09-02)
Verified on the branch at `ec2a0e0`: `schema.py:14` CURRENT_VERSION=38, `:2214-2265` v38 block tail, `:1064+` rewind commentary, v19 ceremony `~:745-825`; `models.py` Connector Literal/`_CONNECTOR_TYPES`/assert (Flight 3 shape unchanged); `repositories.py:600` ConnectorRepository, `:1105` ChatSessionRepository; `inbound.py:128` `_session_title`, `:132` resolve_session, admission/early-return ordering at `:360-373` (cycle-1 flight review's reading, re-confirmed); `connector_send.py:89` `_resolve_default_target`; `api.py:2882` delete_connector; `base.py:20-38` InboundEnvelope. All live.

---

## Post-Completion Checklist
**Flight-end commit model — do NOT commit and do NOT signal `[COMPLETE:leg]`:**
- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` foreground)
- [x] Flight log updated (counts, migration verification detail, deviations/anomalies)
- [x] Leg status set to `landed`
- [x] Signal `[HANDOFF:review-needed]`
