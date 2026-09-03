# Flight Log: Telegram and the Name Directory

**Flight**: [Telegram and the Name Directory](flight.md)

## Summary
Landed 2026-09-02. Four legs: v39 + directory + shared surface; the Telegram long-poll client; the lookup tool + a PASSED stub gate (3/3); and a guided HAT that verified Telegram live from the operator's own account, cross-connector name sends on both platforms, and shipped a HAT-promoted formatted-rendering feature. Two review-corrected budget facts: shared bucket 607, Telegram subpackage 575 post-feature.

## Flight Design Notes (planning, 2026-09-02)

- Planning surfaced a genuine mission-constraint collision before any spec text existed: `'telegram'` requires a CHECK-change migration and v38 was spent. Escalated to the mission owner → RQ10 (v39 authorized narrowly: type CHECK + `connector_directory`, one step). Mission criterion for the additive seam reworded per the Flight 3 debrief recommendation (owner-approved), and the name directory joined the mission as a new criterion (RQ11) — operator's rationale: "a good opportunity to validate our architecture and ensure it's multi-connector."
- Operator design inputs recorded verbatim in the DDs: directory schema carries display name AND username (nullable) because bare names collide; resolution is a SEPARATE lookup tool (not a send-tool name form); the two-call chain is gated by a stub behavior test before the HAT; the lookup tool is carve-out-seeded; session-title ride-along included.
- Flight 3 lessons applied at planning: the three review-time questions are named in the Technical Approach for every leg design; the DD-10 apparatus is audited on all three axes including ADMIT (the stub gate's seeding envelope is allowlisted); the model floor (gpt-oss:20b) is a stated prerequisite before the gate; no automated Telegram live gate is pretended (bots cannot see other bots' messages on Telegram — the HAT is the honest instrument).

- Architect design review cycle 1 (2026-09-02, with the Flight 3 debrief's three review-time questions as a mandatory charter): approve with changes; ZERO DD-to-DD contradictions (vs. Flight 3's three) and both happy paths traced clean — the reply hop correctly rides Flight 3's DD-10 unmodified. HIGH: the lookup tool's generic `platform_id` broke literal copy-the-ids (model-performed rename at the floor) → candidates now emit `peer_id`/`channel_id`+`thread_id` keyed exactly as the send target expects. Mediums applied: population hook pinned BEFORE the `/new`/`should_reply` early returns; `thread_id` column added while v39 is open; shared bucket loosened to ≤350 (doc-density realism); Telegram `chat.title` capture named in leg 2; `connector_id` filter guidance moved into the tool description; DD-1 enumeration gains the stub-seam `peer_username` passthrough (f) and delete-route cleanup (g). Lows: cross-flight DD-4 citation disambiguated; DD-5/DD-7 repository methods named; wording nits. Cycle 2 re-review spawned. Operator sign-off is standing ("approved, mark it ready and kick off /agentic-workflow") contingent on a clean cycle 2.

- Cycle 2 (2026-09-02): approve with changes, all applied at the cap. Budget line reconciled (≤700/≤350); DD-5 repository method literally named (`search(agent_name, query, connector_id=None)`); and the one substantive gap DECIDED at flight level rather than deferred: channel directory entries are deliberately NOT admission-gated (stated asymmetry — channel names are operator-domain metadata and the bound agent already holds send authority to any visible channel; peers remain strictly gated). Operator's standing sign-off executed → flight `ready`, /agentic-workflow begins.

### Flight Director Notes

- 2026-09-02 — Flight `ready` → `in-flight`; branch `flight/04-telegram-and-directory` cut from `ec2a0e0` (clean main incl. PR #188). Crew file re-validated in-session.
- 2026-09-02 — Leg 1 `schema-and-shared` designed. **Risk tier: HIGH, no deliberation needed** — it IS the schema/migration leg plus every shared-code touch the flight makes. Design review mandatory; the review charter carries the three Flight 3 questions plus the v38 rewind-re-run commentary as required reading.

- 2026-09-02 — Leg 1 design review cycle 1 (Sonnet Developer): approve with changes; citations verified exact, envelope-field addition proven safe (three construction sites counted, slots+frozen additive-default OK). Fixed: AC-5's rename claim was FALSE as written (channel cache = one fetch per process) → restated as the honest trade-off (renames observed post-reconnect). Designer rulings recorded in the leg: `search()` scoping is deliberately CONNECTOR-LEVEL (send-time auth stays the per-target gate; one connector = one operator trust domain); repository returns RAW rows, leg 3's tool owns the literal-key translation; `keying_to_target` returns None for unbound sessions (error-path handoff pinned); v39 needs LESS rewind machinery than v19/v23 (unconditional-idempotent + CREATE IF NOT EXISTS, don't over-build); FD budget ruling — sub-buckets are targets, mission ceiling is the trigger, doc density is not trimmed to fit. Cycle 2 spawned (substantive rulings).

- 2026-09-02 — Leg 1 design review cycle 2: approve with changes, all applied at the cap. Cycle 2's sharpest catch: my cycle-1 "fix" for AC-5 reintroduced the same error class it was fixing — the channel cache survives RECONNECTS by documented contract; only a process restart clears it (AC-5 corrected). Also: the leg-level "~900" flight-ceiling figure contradicted DD-11 and was removed (DD-11 stays the single budget authority; targets reported-not-absorbed, mission ceiling is the trigger); AC-3 gained the explicit connector-breadth test an accidental per-target filter must fail; keying degenerate branch moves into the helper. Leg 1 `ready`, Developer spawned.

- 2026-09-02 — Environment note for leg 4 (operator): a dedicated test/"robot" Telegram USER account is logged in via the operator's goldfinch browser (web.telegram.org). The FD can drive that peer side during the HAT (browser-assisted), speeding the walk; it is deliberately NOT promoted to an automated acceptance apparatus (web-client automation is too fragile for a gate; the stub behavior test remains the mechanical gate and the HAT the live instrument).

- 2026-09-02 — Leg 1 landed (one spawn, NO stall): all 9 ACs, v39 live-verified + rewind-tolerant, 3,803 passing (+45), 450 net lines reported against the 350 shared target per the standing budget ruling (mission slack ~768). `legs_completed = 1`.
- 2026-09-02 — Leg 2 `telegram-client` designed. **Risk tier: LOW — recorded rationale**: purely additive subpackage + one lifespan registration block inside a twice-proven pattern (Discord is the direct structural template); ZERO shared-code touches (leg 1 delivered the flight's entire shared surface); DD-2's Bot API protocol facts were explicitly fact-checked at flight design review cycle 1 ("all check out"); the flight-end Reviewer covers the resulting code. Skipping per-leg design review per the tiering rule; the leg artifact bakes DD-2's normative specifics in verbatim so the implementer isn't re-deriving protocol.
- 2026-09-02 — Leg 2 landed (one spawn, NO stall): all 12 ACs, subpackage lands at EXACTLY the DD-11 ≤350 ceiling (see Leg Progress), 3,852 passing (+49, baseline 3,803), help file drafted with both platform walkthroughs. `legs_completed = 2`.

- 2026-09-02 — Leg 3 `directory-tool-and-gate` designed. **Risk tier: HIGH** — three criteria hit: frozen-adjacent factory seed-block touch (DD-6), a new tool on the read-authorization surface (DD-5), and finalization of an external contract (the behavior spec other readers depend on). Tool name PINNED in the leg: `find_platform_destination`. Design review spawned (focused — DD-5's contract was already litigated through two flight cycles + leg-1 rulings; the review targets the leg-specific surface).

- 2026-09-02 — Leg 3 design review cycle 1: NEEDS REWORK — the tier-high call earned out. HIGH×2: (1) `tools/builtins.py::_TOOL_CLASSES` was absent from the leg entirely — the sole registration seam; without it the tool is inert and every pin test fails (now in Outputs/guidance/citations); (2) no path to the connector `name` AC-1 requires — designer ruling: `search`'s SQL gains a plain JOIN returning `connector_name` as a raw column (no encryptor, no per-candidate get; a permitted amendment to leg-1-landed code, noted for the flight-end reviewer). MEDIUM-HIGH: two landed exact-shape carve-out assertions break in the two-tool world — designer ruling: extend fixtures (disabled-agent disables both names), rewrite the two assertions in place with a citing comment. MEDIUM: behavior-spec step 1 was not row-judgeable — designer ruling: step 1 narrows to the browser-observable claim; step 2's Expected Result carries the directory-population proof (the candidate itself is the evidence). LOW-MED: candidate serialization pinned to one compact JSON array. Cycle 2 re-review spawned (cap).

- 2026-09-02 — Leg 3 design review cycle 2: approve with changes, applied at the cap. Must-fix: `ConnectorDirectoryEntry` needed the `connector_name: str | None = None` field — pydantic's default `extra="ignore"` would have silently dropped the JOIN column (the enrichment a no-op behind green SQL); docstring boundary sentence added ("RAW" = key-translation status, not single-table provenance — the exact loose end that forced leg 1's own ruling, closed at the source this time). Citations re-verified exact; the behavior-spec judgeability ruling and `peer_username` passthrough confirmed real. Leg 3 `ready`, Developer spawned.

- 2026-09-02 — Leg 3 implemented (one stall, resumed — eleventh mission-wide): 3,871 passing (+19), agent/ diff exactly the sanctioned 16 lines, bucket 762 vs 350 target reported per ruling. **MISSION BUDGET FLAG (corrected at flight-end review): 2,739/3,000 — ~261 slack.** My leg-summed arithmetic (2,894/106) double-counted the leg-1/leg-3 overlap on shared files (`db/repositories.py`, `db/models.py`); the Reviewer re-derived from `git diff --numstat`: shared bucket 607 net + Telegram 350 exact. The conservative error hid slack rather than a breach; corrected before leg 4 planning per the review.
- 2026-09-02 — **Stub gate PASSED 3/3** (`directory-lookup-send` run 2026-09-02-20-22-46, run log committed). Checkpoint 2 attempt 1 FAIL → operator-sanctioned row re-author (300s window for floor-model recovery loops; final-state outbound with a TIGHTER zero-wrong-target guarantee; the top-level-promotion clause removed as an FD spec-authoring error — unbound sessions don't promote, by Flight 2 design) → rerun PASS (~166s, exactly one record, exact content). Checkpoint 3: no-match surfaced honestly; the model's one invented-target attempt rejected by the allowlist BEFORE any platform effect (authorization proven live again). Model-floor patterns recorded for the debrief: repeatable connector_id-vs-type confusion on first attempts (squawk candidate: sharpen the tool description — "connector_id is an opaque id, never the platform type"); truncation-on-first-send seen once. **Leg 3 AC-7 met → leg 3 `landed`; dev instance torn down. Phase 2d: flight-end review spawned.**

- 2026-09-02 — **Leg 4 HAT, steps 1–7 all verified live.** CORRECTION to the earlier environment note: the goldfinch-logged-in Telegram account is the operator's PERSONAL account, not a dedicated test account — the FD drove it briefly under the mistaken premise, stopped on the operator's correction, and continued only with explicit permission ("you're ok to drive it"). Silver lining: personal-account pairing is the true daily-driver scenario. Steps: (1) doctor ok on the new telegram connector (getMe + poll loop; BotFather privacy mode confirmed disabled); (2) unadmitted-DM silence (/start + text, nothing persisted); (3) pairing code → allowlist gains the operator's Telegram id, silently; (4) DM round-trip — reply delivered via DD-10's Telegram PeerTarget, session + directory entry (display name + username) created; cosmetic note: replies render raw markdown in Telegram (no parse_mode — DD-2's stated trade-off, step-8 candidate); (5) group created (FD-assisted via the profile add-member flow — the web client's group-creation picker can't find bots, a docs candidate), first message captured `chat.title` into the directory BEFORE any session existed, `always_listen` wired by chat id read FROM the directory, unprompted group reply ~30s, and the group session titled "the-one HAT" — DD-7's directory-named titles live; (6) `/new` → fresh session, memory probe proves reset; (7) **cross-connector name sends from one unbound console chat**: "to C on telegram" and "to Chuck R on discord" both resolved via `find_platform_destination` and delivered (Discord half verified via bot REST read) — mission criterion RQ11 observed live, multi-connector. Step 8 (open alignment) in progress.

- 2026-09-02 — HAT step 8 outcomes: (a) **FEATURE, operator-approved for immediate scoped execution**: Telegram formatted rendering — plugin-side deterministic markdown→Telegram-HTML conversion at the `send()` boundary (`parse_mode=HTML`, the robust mode; MarkdownV2's escaping rejected as hostile), subset bold/italic/inline-code/code-block/link, degrade tables/headings, escape `< > &`, MECHANICAL FALLBACK: one plain-text resend on API rejection — delivery never lost; Discord/stub untouched (Discord renders markdown natively — the per-platform adaptation belongs at each plugin's send boundary, the contract's canonical text unchanged). In-house converter, no new deps, ~100-150 lines INSIDE the telegram subpackage — a reported overrun of the 350 target per the standing budget ruling (mission ceiling comfortably clear). Leg 2's exact sendMessage payload assertions will need updating (named, not incidental). Scoped design review spawned per the HAT fix-vs-feature gate. (b) **DOCS FIX (inline)**: connector-setup.md gains the group-creation quirk (bots can't be added in the web client's creation picker — create empty, then Group Info → Add Members → full @username).

---

## Leg Progress

### 2026-09-02 — Leg 1 `schema-and-shared` landed

**v39 migration** — `the_one/db/schema.py`: `CURRENT_VERSION` 38 → 39. One
`if version < 39:` block, two segments per DD-3/RQ10's exact scope:
Segment 1 rewrites `connectors` (table-rewrite ceremony following v19's
documented pattern) so `type` CHECK admits `'discord', 'stub', 'telegram'`
— guarded on `connectors` table presence (mirrors v38 step 2/3's
hand-built-partial-fixture tolerance; needed for real — see Deviations).
Segment 2: `CREATE TABLE IF NOT EXISTS connector_directory` (v21
precedent) — `connector_id`, `kind CHECK IN ('peer','channel')`,
`platform_id`, `thread_id NULL`, `display_name`, `username NULL`,
`last_seen`, `PRIMARY KEY (connector_id, kind, platform_id)`. No further
migration step was needed or attempted — RQ10's scope held exactly.

**Migration verification**:
- Unit (`tests/test_db_migration.py::TestSchemaV39`, 4 tests): fresh-DB
  upgrade (CHECK admits telegram + rejects unknown type, both asserted;
  `connector_directory` columns incl. `thread_id` verified via
  `PRAGMA table_info`); v38-DB upgrade preserving an existing `discord`
  row's other columns verbatim; idempotent on double-`ensure_schema`
  (v39 stamped exactly once); tolerant of the full `TestSchemaV7`-style
  rewind-rerun (`schema_version >= 7` deleted, entire v13→v39 chain
  re-fires without raising; CHECK/table shape intact post-rerun).
- Live: booted `the-one serve` against a **throwaway `mktemp -d`** data
  dir on port 8485 (never 8484, never the operator's default dir).
  Confirmed via direct `sqlite3` inspection: `schema_version` MAX = 39;
  `connector_directory` has all 7 DD-4 columns; `connectors`' CHECK SQL
  reads `CHECK (type IN ('discord', 'stub', 'telegram'))` verbatim.
  Process killed and scratch dir removed after verification (teardown
  confirmed — directory no longer exists).

**Lockstep type set** (`the_one/db/models.py`, `the_one/interfaces/web/api.py`)
— one change: `Connector.type` Literal, `_CONNECTOR_TYPES`, the
import-time assert (passes — exercised at module import in every test
run), and `_creatable_connector_types()` all gained `'telegram'`;
`'telegram'` joins `'discord'` unconditionally (mirrors how `'discord'`
itself became unconditional in Flight 3), `'stub'` stays dual-gated.
Route test updated: `GET /api/connectors/types` lists
`["discord", "telegram"]` ungated, adds `"stub"` under the gate.

**Repository** (`the_one/db/repositories.py`) — new `ConnectorDirectoryRepository`
(no encryptor — DD-4, no secrets) sibling to `ConnectorRepository`:
`upsert` (upsert-on-change, skips the write incl. `last_seen` when
display_name+username are unchanged), `get` (exact-match,
`(connector_id, kind, platform_id)`), `search` (connector-level scoping
— agent_name matches `default_agent` OR appears in any `channel_map`
value; case-insensitive substring over display_name/username; ≤10
newest-first; `connector_id` filter intersects with, never bypasses,
the authorization scope), `delete_for_connector`. New
`ConnectorDirectoryEntry` Pydantic model in `db/models.py`. Wired into
`api.py` (`_connector_directory_repo()` helper, mirroring
`_connector_repo()`) and `delete_connector` (DD-1g: one deterministic
DELETE after the connector row itself is confirmed gone).

**Population hooks**:
- `connectors/base.py`: `InboundEnvelope` gains `peer_username: str | None = None`
  (additive, defaulted — frozen dataclass, no ordering issue since `raw`
  already trailed with a default). All three construction sites verified:
  Discord (`author.username`), the stub test seam (`body.get("peer_username")`
  in `api.py::stub_test_inbound`), and direct construction (default `None`,
  unit-tested).
- `connectors/inbound.py::dispatch_inbound`: peer upsert inserted
  immediately after the `is_admitted` block, before the `/new` and
  `should_reply` early returns — verified by dedicated tests (admitted
  peer's `/new` records; admitted peer in a non-replying channel
  records; unadmitted peer records nothing; upsert survives a later
  `agent.step` failure — it commits independently, before the
  session-locked dispatch even begins).
- `connectors/discord/plugin.py::_resolve_channel_type`: on a
  `channel_type_cache` MISS only, opportunistically upserts a
  channel-kind directory row (name captured once per PROCESS LIFETIME —
  AC-5's honesty contract, verified by a dedicated call-count test).
  Skips the upsert when the platform sends no `"name"` (Discord DMs never
  do) — this both keeps DMs out of the channel-kind directory and avoids
  ever writing an empty-string name, with no separate DM-type check
  needed. Thread-typed channels store `platform_id == thread_id` (the
  send-addressable id, matching `_translate_message_create`'s existing
  shape). Wrapped in try/except-log (best-effort — a directory hiccup
  must never break message translation); needed for real, see
  Deviations.

**DD-7 session titles** (`connectors/inbound.py`): `_session_title` (now
async) and `resolve_session` gained an optional `dir_repo` parameter
(default `None`, so every pre-existing call site — 13 in
`test_connectors_inbound.py` alone — needed no edits). When `dir_repo` is
supplied and a `channel`-kind directory entry exists at session-creation
time, the title is `display_name`; else the raw channel id, unchanged.
DM titles untouched. `dispatch_inbound` passes the real `dir_repo`.
4 new tests: named-when-known, raw-id-before-entry-exists, no
retro-rename after creation, DM unaffected.

**DD-8 `keying_to_target` extraction** (`connectors/base.py`, home
chosen: `base.py` itself — already imports `Connector`/holds
`ChannelTarget`/`PeerTarget`, so no new `_keying.py` module was needed):
single keying authority, `ChatSession -> SendTarget | None`. The
degenerate connector-bound-but-keyless branch moved out of
`connector_send.py::_resolve_default_target` into the helper (returns
`None`, same as the non-connector-bound case — one error string covers
both at the call site, per the pinned error-path handoff).
`_resolve_default_target` now consumes it; **all 11 pre-existing DD-11
tests in `test_connector_send_tool.py` pass completely unmodified** — the
dict-shape construction at the call site is unchanged, only its input
(a `SendTarget` from the helper vs. the row's raw columns inline)
changed. 6 new unit tests on the helper itself (peer-keyed,
channel-keyed +thread, non-connector, degenerate, channel-priority).

**Budget** — `wc -l` deltas (git diff --stat) for the shared bucket
(production code, this leg's share of the ≤350 target):

| File | +/- |
|---|---|
| `the_one/db/schema.py` | +105/-3 |
| `the_one/db/models.py` | +38/-6 |
| `the_one/db/repositories.py` | +138/-0 |
| `the_one/connectors/base.py` | +48/-1 |
| `the_one/connectors/inbound.py` | +59/-7 |
| `the_one/connectors/discord/plugin.py` | +79/-4 |
| `the_one/interfaces/web/api.py` | +26/-5 (incl. one unrelated `ruff format` whitespace normalization, see Deviations) |
| `the_one/tools/connector_send.py` | +61/-51 (net small; a full inline-vs-helper rewrite, so both sides are large) |
| **Total** | **502 insertions / 52 deletions → 450 net** |

This is **leg 1 alone** against the ≤350 *target* for "migration +
directory + tool + extraction + hooks" (leg 1 + leg 3 combined); leg 3's
tool work still to come. Per DD-11's FD budget ruling (recorded in the
leg spec Context and reaffirmed at design review), sub-bucket targets
are reported, not silently absorbed, and are NOT grounds to trim the
DD-citing comment density — the actual stop trigger is the MISSION
ceiling (3,000 connector Python; 1,782 used pre-flight, 1,218 slack at
branch cut). 450 net lines leaves ~768 lines of mission slack even
before leg 3's own count — well within bounds. No stop condition was
approached. Test-file deltas (not counted against the production
budget): +1,072/-6 across the six touched test files.

**Test numbers**: scoped runs all green throughout (migration 88/88,
repositories 153/153, connectors_inbound 47/47, connector_send_tool +
connector_routes 63/63 combined, discord_plugin 24/24, plus a
spot-check of five adjacent connector test files 38/38 — none
regressed). `make test-unit` (foreground, full): **3,803 passed, 10
skipped, 0 failed** (553 deselected — browser/live/pixel markers, as
designed), ~7m14s. No new dependencies (`pyproject.toml`/`uv.lock`
untouched).

**Agent loop**: `the_one/agent/` untouched, confirmed by the diff scope
above (no file under that path appears).

---

### 2026-09-02 — Leg 2 `telegram-client` landed

**Subpackage** — `the_one/connectors/telegram/` (`__init__.py`, `_api.py`,
`plugin.py`), structural template Discord (`connectors/discord/`), zero
shared-code touches (leg 1 delivered the flight's entire shared surface;
confirmed by diff scope — nothing outside the new subpackage, the test
tree, `docs/`, and the one `interfaces/web/app.py` registration block).

- `_api.py`: `TelegramApiClient` — `getMe`/`getUpdates`/`sendMessage` on
  `httpx`, token in the URL path (`/bot<token>/<method>`, not a header,
  unlike Discord). 401/404/409 → `PermanentConnectorFailure` (REUSED
  verbatim from `connectors/base.py`, Flight 3); other 4xx/5xx →
  `TelegramApiError` (ordinary `ConnectorClientError`, manager backoff).
  `sendMessage` 429 gets one bounded retry honoring `retry_after`, then
  surfaces as `TelegramApiError` (Edge Cases' named choice).
- `plugin.py`: `TelegramPlugin`/`TelegramClient`/`_AccountState` — the
  Discord account-id-keyed `_state` dict shape. `connect()` runs `getMe`
  then the FIRST `getUpdates` cycle synchronously (awaited via
  `ready_future`, mirroring Discord's READY wait) so a 401/404/409 from
  either raises `PermanentConnectorFailure` at connect time; a LATER 409
  (a second consumer starting mid-session) is NOT re-raised
  synchronously — same accepted pre-READY-only trade-off Discord's
  close-code policy documents. `is_alive()` = poll task alive AND last
  successful poll within `2*timeout+grace`. Translation: `chat.type ==
  "private"` → `is_dm`; `mentions_bot` from a `mention` entity sliced by
  UTF-16 CODE-UNIT offsets (not native string indexing — Edge Cases'
  named pitfall) or a `text_mention` entity matching the bot id;
  `peer_name` from `first_name [+ last_name]`; channel/group keyed by
  `str(chat.id)`; `message_thread_id` → envelope `thread_id`; bot-authored
  messages drop unless allowlisted (Flight 3 DD-4 parity); text-less
  messages drop. Directory: every group/supergroup message's `chat.title`
  upserts a channel-kind directory row, NOT admission-gated (the DD-4
  cycle-2 ruling quoted at the call site, per AC-6). Outbound `send()`:
  `ChannelTarget` → `chat_id=channel_id` (+ `message_thread_id`);
  `PeerTarget` → `chat_id=peer_id` directly (Telegram's DM chat id IS the
  user id — no Create-DM REST step, unlike Discord). NO `history` method
  on `TelegramClient` at all (the Bot API has no history endpoint) — the
  optional-hook pattern working as designed, `getattr(client, "history",
  None) is None` asserted, `fetch_channel_history`'s existing no-hook
  path covers it with zero new code.
- Registration: `interfaces/web/app.py` gained one guarded
  `_register_telegram()` block immediately after Discord's (same
  unconditional pattern, own try/except), plus symmetric
  `registry.unregister("telegram")` at shutdown.
- `docs/connector-setup.md` (new, DD-9): Discord + Telegram operator
  walkthroughs (bot creation, token handling, the Telegram
  `/setprivacy`-OFF requirement for always-listen groups stated
  prominently, pairing flow, form-field reference table). Linked from
  `the_one/connectors/README.md` (new "Telegram (Flight 4)" contract
  section, mirroring the Discord section) and the top-level `README.md`.
  Placeholder tokens/ids/usernames throughout — no operator-identity
  leaks (swept).

**Fixture** — `tests/_telegram_api_fixture.py`: `FakeTelegramApi`, an
`httpx.MockTransport`-backed double that models Telegram's REAL
`getUpdates` offset semantics (every scheduled update persists in
`self.updates`; each call filters by `update_id >= offset`, or returns
everything when `offset` is omitted) rather than a scripted batch queue —
this is what makes AC-2's redelivery assertion fall out naturally: a
fresh `_AccountState` (offset=None) re-receives every update the fixture
has ever scheduled, exactly like an unclean-restart client hitting the
real Bot API. `error_status` maps a method name to an HTTP status
(permanent: 401/404/409; ordinary: 500; `429` fires once then reverts,
covering the bounded-retry path). Empty-batch polls sleep a small
`empty_poll_delay` (default 20ms) to bound the background loop's
iteration rate during tests without simulating the full 50s long-poll
hold.

**Test numbers**: scoped `tests/test_telegram_*.py` — 49/49 (10 API-layer,
39 plugin-layer), foreground, passed on the first run. Spot-check of four
adjacent connector test files (Discord plugin, connector routes,
connectors_inbound, connector_send_tool) — 134/134, none regressed.
`make test-unit` (foreground, full): **3,852 passed, 10 skipped, 0
failed** (553 deselected), ~7m20s — exactly baseline 3,803 + 49 new, no
new failures or warnings.

**Budget** (AC-11): `wc -l the_one/connectors/telegram/*.py` —

| File | Lines |
|---|---|
| `__init__.py` | 13 |
| `_api.py` | 81 |
| `plugin.py` | 256 |
| **Total** | **350** |

Lands at EXACTLY the DD-11 ≤350 ceiling, zero lines of slack in this
sub-bucket (reached only after several compaction passes — see
Deviations). No `pyproject.toml`/`uv.lock` diff (confirmed via `git diff
--stat`) — `httpx` was already a base dependency, no new one added.
Fixture-only networking throughout the new test files (`httpx.
MockTransport` exclusively; no real host ever addressed).

---

### 2026-09-02 — Leg 3 `directory-tool-and-gate` Developer handoff (AC-1..AC-6 landed; AC-7 pending — FD-run)

**Tool** — new `the_one/tools/connector_lookup.py`: `FindPlatformDestinationTool`
(name `find_platform_destination`, pinned). Read-only; `query` (required,
declared first) + optional `connector_id`, mirroring
`connector_send.py`'s construction/agent_name pattern (per-agent instance,
NO encryptor — the directory repository takes none). Resolves via
`ConnectorDirectoryRepository.search(self._agent_name, query,
connector_id)`, then performs the DD-5 literal-key translation: a `peer`
row emits `peer_id`; a `channel` row emits `channel_id` (+ `thread_id`
when set) — never a generic `platform_id`, never both key shapes on one
candidate (asserted). Zero matches → `[no-match] no directory entry
matches {query!r}` (not an error, not an empty array). Empty/whitespace
query → `[error] [constraint] ...`, no full-table dump. Result is ONE
compact JSON array (`json.dumps(..., separators=(",", ":"))`) — never
prose-with-inline-ids. Description documents `target`-compatibility
(`send_to_platform_channel`'s target) and the connector_id-omission
guidance. Schema `required=["query"]` is a prefix of declared property
order (global `test_tool_base.py` invariant — passes automatically via
`_TOOL_CLASSES` iteration).

**Registration** — `the_one/tools/builtins.py::_TOOL_CLASSES` gains
`"find_platform_destination": FindPlatformDestinationTool` appended after
the existing pair (empty default `Config`, so the `FilesystemConfig`
ordering-is-policy assertion is unaffected). Confirmed this is the sole
seam: before this entry, the pin tests all failed with the tool absent
from every registry.

**Connector-name enrichment** — `ConnectorDirectoryRepository.search`
(`db/repositories.py`) SQL gains a plain `JOIN connectors c ON c.id =
cd.connector_id`, returning `c.name AS connector_name` as one more RAW
column (no encryptor, no per-candidate `ConnectorRepository.get`).
`db/models.py::ConnectorDirectoryEntry` gains `connector_name: str | None
= None` (the cycle-2 must-fix — without it pydantic's `extra="ignore"`
would silently drop the JOIN column and the enrichment would be a no-op
behind green SQL). `get()` is UNCHANGED — it stays a single-table
exact-match read, so `connector_name` is `None` on rows it returns (pinned
by a new test). Repository class docstring gained the boundary sentence:
"RAW" describes key-translation status, not single-table provenance — the
JOIN is a compatible extension of leg 1's boundary, not a breach. Leg 1's
`tests/test_db_repositories.py::TestConnectorDirectoryRepository` gained
two new tests (`test_search_includes_connector_name_via_join`,
`test_get_does_not_enrich_connector_name`); all pre-existing tests in that
class pass unmodified.

**DD-6 pair seeding** — `the_one/agent/factory.py`'s sanctioned seed block:
the `if SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in registry.tool_names:` became
a `for seed_tool_name in (SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
FIND_PLATFORM_DESTINATION_TOOL_NAME):` iteration, same body per name.
`agent/core.py` untouched. **`git diff the_one/agent/` shows ONLY this
file, ONLY the import + the seed-block iteration** (16 insertions / 4
deletions total) — verified directly, quoted in the handoff below.

**Pin tests** (`tests/test_factory.py::TestSendToolCarveOut`) — all five
DD-6 cases: (a) pair seeded when both enabled — `test_no_search_needed_first_llm_call`
and `test_no_duplication_on_search_match` extended to assert both names;
(b) each independently absent when disabled — the shared `disabled-agent`
fixture now disables BOTH names (designer ruling, no fixture split), and a
NEW `test_each_tool_independently_absent_when_disabled` proves the
independence half with two single-tool-disabled agents; (c) reset survival
for both — `test_reset_survival_and_container_identity` rewritten for the
pair; (d) no duplication on search match — covered by (a)'s extension;
(e) baseline otherwise unchanged — `test_baseline_otherwise_unchanged`
REWRITTEN IN PLACE (the two cited exact-shape assertions): disabled case
stays an exact 2-element list (`SEARCH_TOOLS_SCHEMA`, `CONTINUE_SCHEMA` —
unchanged shape since the shared fixture now disables both names);
enabled case is now an exact 4-element list (baseline pair + both
carve-out schemas, order-agnostic via a set comparison on the tail two).
`test_no_duplication_on_search_match`'s `len == 1` also rewritten to
assert `count(...) == 1` for EACH name plus the length-parity check,
unchanged in spirit.

**Unnamed sibling breakage, fixed in-charter** — `tests/test_builtins.py`
(not named in the leg spec, but a direct, mechanical consequence of the
AC-4 registration touch): three hardcoded tool-count assertions
(`len(...) == 21`, twice) and one exact tool-name `set` literal broke the
moment `find_platform_destination` entered `_TOOL_CLASSES`. Rewritten to
`22` with a citing comment, and `"find_platform_destination"` added to
the name set — mechanical, no design decision, same category as the two
`test_factory.py` assertions the leg spec named explicitly. Flagging for
the flight-end reviewer in case a broader sweep for similar magic numbers
is wanted; `tests/test_api_tool_configs.py` was already dynamic
(`len(_TOOL_CLASSES)`) and needed no change.

**Docs** — `the_one/connectors/README.md` gained a new "Lookup tool
(`find_platform_destination`, DD-5, ...)" section quoting the repository's
connector-level scoping ruling verbatim, per AC/Outputs. `the_one/agents.md`'s
connectors index bullet ("Two built-in tools" → "Three built-in tools")
extended with the lookup tool's one-paragraph summary and a pointer to the
README section.

**Behavior spec finalized** — `tests/behavior/directory-lookup-send.md`
`status: draft` → `active`. Tool name pinned throughout. Step 1's Expected
Result narrowed to the browser-observable session claim ONLY (`DM: Marisol
Vega` session + transcript, judgeable at that row); the directory-population
claim moved to step 2, where the lookup tool's own candidate (`display_name`
"Marisol Vega", `peer_id` "peer-7") IS the evidence, per the judgeability
ruling. Exact stub-seam payload pinned for step 1, including
`peer_username` (leg 1's passthrough, the draft's hedge resolved to an
assertion — `"peer_username": "marisolv"`). Shape-valid per ARTIFACTS.md
Phase-1 (Intent/Preconditions/Observables Required/Steps/Out of Scope all
present and non-empty).

**Budget** (production code only, this leg's share of the shared
"migration + directory + tool + extraction + hooks" bucket — `git diff
--numstat` / `wc -l`):

| File | +/- (net) |
|---|---|
| `the_one/tools/connector_lookup.py` (new) | +107 |
| `the_one/db/repositories.py` | +152/-0 |
| `the_one/db/models.py` | +38/-7 (net +31) |
| `the_one/agent/factory.py` | +16/-4 (net +12) |
| `the_one/tools/builtins.py` | +10/-0 |
| **Leg 3 total** | **312 net** |

Per DD-11's standing FD budget ruling (sub-bucket targets are reported,
not silently absorbed; the MISSION ceiling is the trigger, not the
sub-bucket target): leg 1 alone already used 450 of the shared bucket's
≤350 *target*; leg 3 adds 312 more, bringing the combined shared-bucket
total to **762** against the ≤350 target — reported, not a stop condition
per the standing ruling. At the MISSION level: 1,782 (pre-flight) + 450
(leg 1) + 350 (leg 2, exactly at its own ceiling) + 312 (leg 3) = **2,894**
against the 3,000-line ceiling — **106 lines of mission slack remain**
before leg 4. Flagging explicitly for the FD: this is thin. No stop
condition was triggered (DD-11's divert-if is keyed to the mission
ceiling, which was not reached), but leg 4's HAT leg does no further
Python-line work per the flight's own leg breakdown, so this is expected
to be the flight's final production-code total barring HAT-driven fixes.

**Test numbers**: scoped foreground runs all green — lookup tool 16/16;
repositories 155/155 (153 baseline + 2 new); factory 30/30 (29 baseline +
1 new); `test_tool_base.py` + `test_connector_send_tool.py` +
`test_connector_routes.py` 84/84 (unchanged, spot-check); `test_builtins.py`
+ `test_api_tool_configs.py` + `test_cli_sandbox_parity.py` 47/47 (1
deselected, `requires_bwrap`). `make test-unit` (foreground, full,
600000ms timeout): **3,871 passed, 10 skipped, 0 failed** (553 deselected
— browser/live/pixel, as designed), 461.87s (~7m42s). Baseline 3,852 → +19,
exactly matching the new tests added across the three files above (16 + 1
+ 2). No new dependencies (`pyproject.toml`/`uv.lock` untouched, confirmed
via `git diff --stat`). `ruff check` + `ruff format --check` clean on all
touched files after one `ruff format` pass on the new test file.

**Agent loop**: `the_one/agent/` diff scope confirmed — `factory.py` only,
import + seed-loop iteration only (see "DD-6 pair seeding" above).

**AC-7 (gate) is NOT run by this Developer** — per the leg spec and the
flight-end-review precedent, the gate run and leg landing belong to the
FD. Leg status left `in-flight`. See the Developer's `[HANDOFF:review-needed]`
message for the exact gate preconditions (stub connector shape, tools
enabled on test-agent, env vars, model).

---

## Decisions

- Home for `keying_to_target`: `connectors/base.py` (not a new
  `connectors/_keying.py`) — the module already imports `Connector`
  and owns `ChannelTarget`/`PeerTarget`/`SendTarget`, so co-locating the
  one function that maps between them added zero new files and kept the
  touch minimal, per the leg spec's "implementer's within the named
  touch" allowance.
- `resolve_session`/`_session_title` took an **optional** `dir_repo`
  parameter (default `None`, pre-DD-7 fallback behavior) rather than a
  required one — this avoided editing 13 pre-existing call sites in
  `test_connectors_inbound.py` for a leg-1-internal signature change,
  while `dispatch_inbound` (the only production caller) always supplies
  the real repo.
- Discord channel-directory capture uses a truthy-`name` guard
  (`if not name: return`) rather than an explicit `ctype in _DM_TYPES`
  check to exclude DMs — Discord's Get Channel response for a DM/group-DM
  carries no `"name"` key at all, so the truthy check naturally excludes
  DMs while also satisfying the "never an empty-string name" invariant
  in one guard, with no separate type-based branch needed.
- **Leg 2**: `_run` (the `getMe` + poll-loop body) is a CLOSURE nested
  inside `TelegramPlugin.connect()` (capturing `state`/`api`/
  `on_inbound`/`ready_future`) rather than a separate method taking those
  four as parameters — chosen specifically to fit the DD-11 ≤350 budget
  (a 5-parameter method signature costs ~8 wrapped lines at this file's
  100-char line length; the closure needs none). Same reasoning for
  `TelegramClient` being a `@dataclass` (fields `_task`/`_api`/
  `account_id`/`_state`, matching Discord's attribute names including
  the leading underscores on the two internal ones) instead of a
  hand-written `__init__` — Python dataclasses accept
  underscore-prefixed field names without issue; this is a stated,
  deliberate style choice, not an oversight.
- **Leg 2**: `InboundEnvelope.raw` is left at its default `{}` for every
  Telegram-constructed envelope (never populated with the raw Telegram
  `message` dict) — unlike Discord's plugin, which does pass `raw=d` for
  parity/debuggability. Not required by DD-2 or any AC, and every
  additional kwarg has a real line cost under the tight budget; a
  deliberate, budget-driven divergence from the Discord precedent, not
  an oversight.

---

## Deviations

- **`uv sync --extra dev` alone is insufficient for `make test-unit`
  on this branch.** Following the leg instruction literally
  (`uv sync --extra dev`) *uninstalled* `anthropic`/`openai` and the
  `gui` extra's packages that were already present in the venv (from a
  prior `all-llms,gui,dev` install), because `uv sync` reconciles the
  environment to exactly the requested extras. This caused 14 collection
  errors (`ModuleNotFoundError: anthropic` / `openai`) on the first
  `make test-unit` attempt. Fixed by re-running
  `uv sync --extra dev --extra all-llms --extra gui` to restore the
  full previous environment before re-running the suite. Flagging this
  for the flight-end reviewer / future legs: on THIS repo's dev venv,
  `uv sync --extra dev` should be `uv sync --extra dev --extra all-llms
  --extra gui` (or whatever combination the venv was actually seeded
  with) to avoid stripping installed extras mid-leg. No `pyproject.toml`
  or `uv.lock` change was made or needed — this was a local-venv
  package-set issue only.
- **v39's rewrite ceremony needed a table-presence guard the original
  leg-spec text didn't anticipate.** The first version of Segment 1
  (unconditional `PRAGMA foreign_keys=OFF; CREATE TABLE connectors_new...`)
  broke a pre-existing test (`TestSchemaV30::test_v30_migration_on_v29_fixture_adds_column_backfills_rows`)
  that hand-builds a partial schema (only `agents` + `schema_version`,
  seeded at version 29) to test v30 in isolation — that fixture never
  creates a `connectors` table at all, since it starts past v13/v19/v23.
  Added a `SELECT name FROM sqlite_master ...` presence guard around
  Segment 1 (mirroring v38 step 2/3's own documented "hand-built
  partial-schema fixture" tolerance) — a no-op for any real,
  monotonically-migrated database, where `connectors` always exists by
  v39. This is the same category of tolerance the leg spec already
  named for v38; extending it to v39 is a minimal, in-charter fix, not
  a design change.
- **One test's original design was invalid, not v39.** My first draft of
  the rewind-rerun test deleted `schema_version WHERE version >= 7`
  (the full `TestSchemaV7`-style cascade) and asserted a pre-inserted
  connector row survived — but v38's OWN block does an intentionally
  unconditional `DELETE FROM connectors` on every re-run (its docstring
  says so explicitly: "a stamp rewind is a test-only
  structural-idempotency artifact"), so ANY row inserted before a full
  v7+ rewind is wiped by v38 before v39 even runs. Corrected the test to
  assert what's actually true (no crash, CHECK/table shape intact,
  `connector_directory` still writable) rather than asserting row
  survival through a scenario where a documented, pre-existing migration
  step wipes the table. v39's actual stamp-only-rewind row-preservation
  (the real contract) is covered by a separate test that rewinds only
  `version >= 39`.
- Running `ruff format` across the touched files reformatted one
  unrelated, pre-existing line in `the_one/interfaces/web/api.py`
  (`discord_test_sever`'s `HTTPException` call collapsed from two lines
  to one) — a whitespace-only, behavior-preserving normalization, not a
  functional change; left as-is since ruff format is the mandated
  formatter for touched files.
- **Leg 2**: the DD-11 ≤350-line subpackage ceiling needed unusually
  aggressive compaction to land — the first correctness-complete draft
  measured ~500 lines (comment density matching Discord's own house
  style, which carries no comparable per-file budget); repeated
  edit/`ruff format`/`wc -l` cycles trimmed docstrings/comments to their
  AC-mandated minimum (the DD-4 quote for AC-6, the no-`history`
  rationale for AC-8, the UTF-16-offset and offset-redelivery notes for
  AC-5/AC-2) and restructured `connect()`/`_run()` as described in
  Decisions above. Final count landed at EXACTLY 350 — zero lines of
  slack in this specific sub-bucket. Flagging for the flight-end
  reviewer and any future touch to this subpackage: a further change
  here will need a compensating cut elsewhere in the same three files to
  stay in budget, OR a return to the FD for a budget conversation (DD-11
  sub-bucket targets are reported, not silently absorbed, per leg 1's
  own recorded ruling — but this sub-bucket specifically has no more
  room to absorb anything). The MISSION-level ceiling (3,000 connector
  Python) still has substantial slack — only this leg's own sub-target
  is at its limit.
- **Leg 2**: no `uv sync`/environment deviation this time — the venv was
  already correctly seeded from leg 1's fix (`--extra dev --extra
  all-llms --extra gui`), and `make test-unit` passed on the first
  attempt.
- **Leg 3**: the first `make test-unit` invocation exceeded the calling
  tool's own 120s default foreground timeout and was auto-moved to a
  background task (no `run_in_background` flag was set — this is the
  tool's own threshold, not a deliberate choice). Per the leg's test
  discipline (foreground-only, explicit timeouts up to 600000ms), the
  background run and its accompanying monitor were stopped unused and
  `make test-unit` was re-invoked as a genuine foreground call with an
  explicit 600000ms timeout, which completed cleanly (461.87s, well
  under the cap). No test content or result was taken from the aborted
  background run. Flagging for future legs on this project: always pass
  an explicit large timeout on the FIRST `make test-unit` invocation,
  not just as a fallback after the default trips.

---

## Anomalies
*(none for either leg — every item above was resolved within its leg,
not left open)*

- **Leg 3**: none left open — AC-1..AC-6 verified, `make test-unit` green.
  AC-7 (the gate run) is INTENTIONALLY not run by this Developer; it is
  the FD's post-handoff step per the leg spec, not an anomaly.

- 2026-09-02 — Flight-end review (Sonnet, security tier): **[HANDOFF:confirmed]**, no blocking issues. Verified personally: admission boundary structurally unreachable for unadmitted peers (upsert at inbound.py:395-413, strictly post-is_admitted, pre-early-returns, ruling quoted); channel-ungated ruling quoted at both plugin call sites; lookup scoping non-bypassable (connector_id intersects, never widens); keying extraction behavior-preserving; UTF-16 mention slicing genuinely correct; no wrong-target path (send re-checks authorization regardless of target provenance); no leaks. Budget corrected (above). Non-blocking notes for the debrief/squawks: httpx-logger token-in-URL hardening (worth a squawk), LIKE %/_ escaping (cosmetic), unclamped 429 retry_after (trivial), group-DM capture test gap (minor). Leg checkbox drift (legs 2-3) fixed in the commit pass.

- 2026-09-02 — HAT step 8 closed: feature implemented per the scoped review's strengthened design (structural no-raise guard, broad plain-text fallback healing length overflow, fixture one-shot-400, bullet/italic collision test), operator re-verified LIVE in Telegram (bold heading, <pre> table, bold prose, inline code — table-interior markers accepted as the stated degrade); docs fix shipped. Independent Reviewer (Haiku tier) [HANDOFF:confirmed] with an injection spot-check. Telegram subpackage 575 lines post-feature (target overrun by design under the standing ruling); suite 3,910. **Leg 4 `completed`; flight `landed`; PR #190 ready; dev instance torn down. [COMPLETE:flight]**
