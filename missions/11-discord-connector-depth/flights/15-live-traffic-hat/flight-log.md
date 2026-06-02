# Flight Log: Live-Traffic HAT Capability

**Flight**: [Live-Traffic HAT Capability](flight.md)

## Summary

Planning in progress. Flight scoped to the live-traffic HAT capability (mission criteria #5/#6/#7/#9/#11/#13) plus four carry-forward fold-ins. Rate-limiting (#17) deferred to the daily-driver flight (F16) per operator decision (discord.py pre-empts per-route limits; no cascade observed). Apparatus resolved to **hybrid** (committed discord.py multi-bot driver + operator Chrome-MCP pass), de-risked by a planning-time premise audit.

---

## Reconnaissance Report

Source artifacts: M11 mission.md success criteria + Known Issues; F14 debrief Action Items; F13 debrief Recommendations/Action Items. Each item F15 sources was walked against current code during planning.

| Item | Classification | Evidence | Recommendation |
|------|---------------|----------|----------------|
| F14: wire connector loggers to stdout | `confirmed-live` | No central logging setup anywhere in `the_one/` or `scripts/` (no `basicConfig`/`dictConfig`/`StreamHandler`); loggers are `getLogger(__name__)` only — not propagated to `docker logs` under uvicorn | L1 — diagnostic prerequisite for the HAT |
| F14: add `tini` as PID 1 | `confirmed-live` | `Dockerfile:37` `ENTRYPOINT ["/entrypoint.sh"]` → `entrypoint.sh` `exec "$@"` → CMD `the-one serve` becomes PID 1; no `tini` referenced in Dockerfile/compose | L1 — bundle with loggers (shared container/startup surface) |
| F14/F13: re-run `audit-log-inspector` behavior test (deferred at F14) | `confirmed-live` | F14 debrief deviation: deferred due to seeding drift + the PUT-drops-metadata bug below | L2 — fix seeding, re-run to PASS |
| F13: `ChatSessionRepository.update` drops `session_metadata` on PUT | `confirmed-live` | `repositories.py:936` UPDATE sets only `title, messages, updated_at`; docstring states the 7 connector-identity columns (incl. `session_metadata`) are intentionally NOT round-tripped | L2 — seed audit entries via test-only session/fixture or direct write (not PUT) |
| F13/F14: 2 pre-existing browser test failures (since pre-F10) | `drifted` | Files exist (`tests/browser/test_flow_agent_tabs.py`, `test_flow_studio_navigation.py`) but the debrief-cited function names (`test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`) did not match a `def` grep — names drifted or parametrized | L2 — re-locate the failing tests first, then fix |
| Mission #9 detach-from-Connectors-screen | `partially-satisfied` | F9 substrate landed (DELETE endpoint, pool release, detail-page button, grid badge per mission.md:33); L8 HAT did NOT exercise the detach step | L7 — close via the hybrid HAT pass |
| Mission #5/#6/#7 live routing | `confirmed-live` (unverified-against-real-traffic) | F6/F7 substrate landed; never exercised against real multi-X Discord traffic (M10 deferrals) | L4/L5/L6 — the core HAT scenarios |
| Mission #11 committed HAT script | `partially-satisfied` | `[~]` — F14 shipped the slash-only `discord-slash-end-to-end` spec; multi-user/channel/agent/pairing/mentions coverage owed | L3–L8 — the committed multi-bot driver closes it |
| Mission #13 peer-name attribution | `confirmed-live` (unverified-against-real-traffic) | F6 substrate landed (6-surface lockstep per mission.md:136); not yet observed end-to-end under real multi-user traffic | L4 — observe in Chat UI under multi-peer load |

**Planning-time premise audits (F14 "verify-before-lock" discipline):**
- ✅ **Multi-bot driver viability** — `ingest_bots` config flag at `_discord.py:935` disables the bot-author inbound filter; `peer_id=str(author.id)` at `_discord_translate.py:124` gives distinct burner bots distinct peers. Apparatus de-risked *before* lock (vs F14 L9 which lost a cycle to an unaudited apparatus premise).
- ⏳ **Bot-peer vs human-peer path equivalence** — deferred to L3 (grep `_routing.py`/`_acl.py` for author-type branches + live smoke assert) before L4 relies on it. Pre-authorized as a Divert trigger.
- ⏳ **Author-agnostic mention detection** — deferred to L7; fallback to human-sender Chrome-MCP pass if bot mentions don't register.

**Operator-confirmed planning decisions:** apparatus = hybrid; fold-ins = all four (loggers, tini, audit-log re-run, 2 browser fails); #17 deferred to F16.

---

## Flight Director Notes

### 2026-06-01 — Flight start (`/agentic-workflow`)
- Phase file loaded: `.flightops/agent-crews/leg-execution.md` (valid: Crew / Interaction Protocol / Prompts present).
- Flight status `ready` → `in-flight`. Branch `flight/15-live-traffic-hat` created off `main`.
- Planning artifacts committed (`536a5fe`), source untouched.
- **Pre-existing uncommitted change flagged & excluded from F15:** `docker-compose.yml` adds `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` env vars (commented "M11 F7 L12 HAT"). F13 L3 removed `Settings.inference_*` in favor of per-connector storage, so this env config is likely vestigial. Left uncommitted in the working tree; NOT part of any F15 commit. Operator to discard or confirm.
- Execution order: deferred-commit model — L1–L6 autonomous (single review + commit at Phase 2d); L7 (pairing/mentions/detach) + L8 (UAT) are interactive HAT legs the FD guides directly. Behavior-test legs run via `/behavior-test` and commit per-run.

### 2026-06-02 — Apparatus confirmed: bot-token driver (FD decision)
- Operator provisioned test-channel-1/2/3, test-role1/2, agents "Connector agent 1/2", and 3 real user accounts (operator drives 2, agent 1). Operator open to creating bot tokens ("if I can create tokens, I will do that") and deferred the apparatus choice to the FD.
- **FD decision: 3 bot-application tokens (autonomous discord.py driver), per the planned HAT Apparatus DD** — NOT human user accounts. Rationale: a user account can't be code-driven ToS-compliantly (self-bot), one Chrome-MCP browser = one account, so the human-account route can't be an autonomous re-runnable gate (the core of criterion #11). Bots are the sanctioned automation path; premise already audited (`ingest_bots` + author-id peers); routing/session/ACL/attribution path is identical for a bot peer.
- Operator to create 3 bot apps (Message Content intent, invited to the test guild, test-role1/2 assigned) + hand over 3 tokens (gitignored env). The 3 human accounts repurpose to the L7 real-human pairing-approval pass. L3 skeleton proceeds now; live smoke runs when tokens land.

### L3 — multi-bot-hat-driver-foundation
**Status**: landed — skeleton complete + **live smoke PASS 3/3 (+1 deferred)** on 2026-06-02.

#### Provisioning (operator + FD, 2026-06-02)
- **Bots:** operator created 3 bot apps (HAT Test Bot 1/2/3 — ids `1511192509483843604`/`1511192652140249168`/`1511192722252234812`) in a normal browser (the MCP-automated browser loops hCaptcha; token reset is MFA-gated — both hard blockers for automation). Operator reset+pasted the 3 tokens and authorized all 3 into the test guild. Tokens live in gitignored `tests/live/discord_hat/.env.hat`.
- **the-one bot user id** = `1506767486002135280` (GleepGlorp app id == bot user id).
- **Connector `58f1fe5a833f` ("Discord Constellation", guild `1447766672441348150`) reconfigured by FD via API** (operator-confirmed): `ingest_bots=true`, `always_listen=false`, `dm_admission=all` (token + allowlist preserved); **Connector Agent 1 + 2 attached**. Channel ids wired: test-channel-1/2/3 = `1511160772305092827`/`1511160809391128728`/`1511160859622379591`.
- **Finding (L1 observability earned its keep):** the connector was being SKIPPED at startup ("has no attached agents; skipping startup acquire") until the agents were attached — visible only because L1 wired connector logs to `docker logs`. After attaching + container restart: "Warm-acquired connector account … (2 attached agent(s))".
- **Finding (config freshness):** `on_message`'s `ingest_bots` gate reads `account.config` from the **connect-time closure** (`_discord.py:935`), so the `ingest_bots` change required a container **restart** to go live (`always_listen`/`dm_admission` are read fresh per-dispatch and don't).

#### Inline live-run fixes (FD, F14-style HAT fixes — to be reviewed at Phase 2d)
- **Driver intents:** dropped `message_content` → `Intents.default()`. The sender bots only POST; requesting a privileged intent the bot apps don't have enabled raises `PrivilegedIntentsRequired` on connect. (`driver.py`)
- **`wait_for_session` timing:** added an optional `until(detail)` predicate that polls the session *detail* (not just the lookup). The session row is created early in dispatch, but the inbound message + `peer_name` + the engaged routing entry persist only after `agent.step()` finishes the LLM call (seconds later). Without it the smoke raced the dispatch and read an empty `messages` array. **This fix is load-bearing for L4–L6.**
- **DM-isolation deferred to L7:** a Discord **bot cannot DM another bot** (REST `50007 Cannot send messages to this user`). The DM "channel of 1" premise is verified live in L7 with a real human DM. (Platform constraint, analogous to F14's bot-can't-invoke-bot-slash finding.)

#### Live smoke result (`make`-equivalent `pytest -m discord_hat … test_smoke.py`) — PASS
| Premise | Status |
|---|---|
| author-agnostic `@mention` engages (`stepped`) | PASS |
| bot-peer equivalence (F6 `peer_name` on inbound = "HAT Test Bot 1") | PASS |
| negative control (non-mention → `policy-silent`/`always-listen-off`) | PASS |
| channel-shared-vs-DM-isolated topology | DEFERRED → L7 (human DM) |

The committed multi-bot driver works end-to-end against real Discord. Apparatus fully validated for L4–L6. ruff clean; backend suite unaffected (HAT excluded by default marker).

#### Design review (Developer, 2 cycles) — historical
- **Cycle 2 → approve.** Reviewer verified all three resolutions against real code: `find_most_recent_by_external_key(*, platform, connector_id, channel_id, thread_id) -> ChatSession|None` (`repositories.py:872`) matches the lookup endpoint spec (COALESCE thread_id handling, platform="discord"); `always_listen=FALSE` short-circuits at `_inbound.py:235-240` BEFORE `run_engagement_inference` → `policy-silent`/`outcome="always-listen-off"`; `peer_name` emitted by `codec.py:89-90` on user-role messages, exposed via detail `messages`; `<@id>` mention + `get_user(bot_user_id).create_dm()` correct; second `_test` seam consistent with L2, no route conflict. Non-blocking: `inbound_peer_names` should filter role=="user".

#### Design review (Developer, cycle 1 → needs rework)
Two HIGH blockers in the smoke's ASSERTION path (skeleton/marker/secrets sound):
- **HTTP session API exposes no connector-keying fields** — `_session_summary` (`api.py:3271`) returns only id/agent/title/timestamps; detail adds only messages+session_metadata. Driver can't locate the connector-attached session. **Fix:** add a dev-mode-gated test-seam LOOKUP endpoint (sibling to L2's seed) resolving `(connector_id, channel_id)` → session id via `find_most_recent_by_external_key` (`repositories.py:872`). Isolated; no production shape change.
- **`stepped` routing entries omit `policy.outcome` and `peer_id`** (`_inbound.py:773-776`; `policy` attaches only on `policy-silent`). Smoke's `outcome=="mention"`/`peer_id` assertions can't pass. **Fix:** re-authored the smoke against real shapes + **flipped the test connector to `always_listen=FALSE`** so `@mention→stepped` and `non-mention→policy-silent(always-listen-off)` — deterministic, inference fully out; bot-peer ingestion verified via F6 `peer_name` in the session `messages` (also criterion #13's observable), NOT via a routing-entry peer_id.
- **(Med)** driver had no source for the-one's bot user id (needed for @mention + DM target; `is_mention` matches `guild.me.id`, not persisted). **Fix:** added `THE_ONE_HAT_BOT_USER_ID` to the env/config contract.
- Sound/verified: marker+addopts change is correct & complete; no `__init__.py` needed under importlib; skip-if-absent safe; `.env` gitignore does NOT match `.env.hat` (explicit pattern required — captured); BotDriver lifecycle pattern fine; no working-tree conflict.
- **`always_listen=FALSE` supersedes the flight DD's "always_listen=true fallback" for routing legs L3–L6** (flight prereq updated); L7 mentions-aware re-verify flips it on. Recorded here per the in-flight-modification discipline.

## Leg Progress

### L1 — connector-observability-and-reaper
**Status**: ready (design finalized) → handed to Developer for implementation

#### Design review (Developer, 2 cycles)
- **Cycle 1 → needs rework.** One HIGH: the draft set `propagate=False` on the `the_one` logger, which the reviewer EMPIRICALLY showed breaks `tests/test_lifespan.py::test_lifespan_warns_on_deprecated_inference_env_vars` + `::test_lifespan_does_not_warn_when_inference_env_vars_unset` (caplog captures via root → needs propagation; 0 vs 1 records). Also confirmed: tini installs at `/usr/bin/tini` (correct as written); `settings` already imported at `app.py:39`; no conflicting logging config exists; launch-path analysis correct.
- **Resolution:** dropped `propagate=False` (it was both harmful AND unnecessary — uvicorn installs handlers only on `uvicorn*` loggers, not root, so a single `the_one` handler emits each record once; `lastResort` is suppressed once handled). Added Test 4 (caplog-still-captures regression) to pin the contract. Fixed low-sev Inputs wording + added the uvicorn-no-log_config note.
- **Cycle 2 → approve.** Reviewer ran the two lifespan tests (2 passed), simulated production single-emission (count=1, stderr empty → no double-emit), confirmed Test 4 pins the contract. No new issues.

### L2 — test-baseline-hygiene
**Status**: ready (design finalized) → handed to Developer for the autonomous portion

#### Recon re-scoped L2 (operator-confirmed: "Lean L2 — build clean seed + re-run")
- **Browser-fails fold-in → `already-satisfied`.** Ran both cited files: **22 passed, 1 skipped**. F14 debrief metrics already say "0 (L5 resolved both)". Debrief-cited names had drifted (`..._three_tabs` → `..._five_tabs`; `..._preserves_agent_selection` → `test_studio_section_round_trip_returns_to_agent_listing` @ `test_flow_studio_navigation.py:253`). Retired with evidence; no code.
- **Audit-log-inspector → already passed 7/7 at F13** (run `2026-05-31-23-56-31`); the earlier same-day FAIL was transient cache-stale CSS (no code fix). F14 re-run was deferred only because the spec's PUT seed silently drops `session_metadata` (`repositories.py:936` by design). L2 builds a clean seed so it's a sustainable regression gate.
- **Op note (carry to Phase 2d + HAT):** `make rebuild` (L1) wipes the Playwright browser cache + system deps (`libglib-2.0.so.0` missing → chromium launch fails). Remedy: `make _ensure-playwright` (auto-run by `make test-browser`). ALWAYS use `make test-browser`, never raw `docker exec … pytest -m browser`. Restored at L2 design time.

#### Design (the live work)
- Dev-mode-gated test-seam endpoint `POST /api/_test/chat/sessions/{id}/routing-audit` → sets `session_metadata["routing"]` via `set_session_metadata_key` (NOT the dropping `update`); 403 when not dev-mode; 404 on missing session. + unit tests in `tests/test_db_api.py`. + behavior-spec seed precondition rewritten to the new endpoint. FD re-runs `/behavior-test` cache-cold to confirm PASS.

#### Design review (Developer, 1 cycle)
- **approve with changes** — all LOW (doc-accuracy): repo via `_chat_repo()` (not inline get_connection); test toggle = `patch("…api.settings")` + `mock_settings.dev_mode` in `tests/test_db_api.py`; gate status 403 (endpoint-level) decided over the mock-provider's field-level 400, "mirror exactly" wording removed. Citations all verified accurate. Applied; no design change → no re-review.

#### Implementation (Developer) — 2026-06-02

**Status**: ready → in-flight → landed.

**Changes (5 files, source untouched outside these):**
- `the_one/config.py` — added `log_level: str = "INFO"` under a new `# Logging` group (rides existing `THE_ONE_` env_prefix → `THE_ONE_LOG_LEVEL`).
- `the_one/logging_config.py` (NEW) — `configure_logging()`: resolves `logging.getLogger("the_one")`, sets level case-insensitively from `settings.log_level` with `getattr(logging, name, logging.INFO)` fallback, attaches exactly one `StreamHandler(sys.stdout)` with formatter `%(asctime)s %(levelname)s %(name)s: %(message)s`. Idempotent via a `_the_one_stdout_handler` sentinel attr on the handler. `propagate` LEFT at default True (not set) — per the leg's Edge Cases this is what keeps `test_lifespan.py`'s caplog deprecation-warning tests passing.
- `the_one/interfaces/web/app.py` — `configure_logging()` is the FIRST statement in `lifespan` (before `await init_db()`), followed by `logger.info("the-one starting; log_level=%s", settings.log_level)`. Reused the module-level `settings` import (app.py:39) — no new import.
- `Dockerfile` — added `tini` to the apt-get install list; `ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]` (entrypoint.sh `exec "$@"` unchanged).
- `tests/test_logging_config.py` (NEW) — 5 tests: handler-attach+level+propagate-True; idempotency (no duplicate handler); root/uvicorn loggers untouched; caplog-still-captures regression (the cycle-1 hazard contract); bogus-level → INFO fallback. Hermetic autouse fixture removes the sentinel handler and restores level/propagate after each test.

**Test results (all via `docker exec the-one pytest … -x --timeout 30`):**
- `tests/test_logging_config.py` — **5 passed**.
- `tests/test_lifespan.py` (cycle-1 regression hazard) — **6 passed** (both deprecation-warning caplog tests green → propagation contract holds).
- Full backend suite (`-m 'not browser and not live and not pixel and not requires_bwrap'`) — **2823 passed, 4 skipped, 524 deselected** in 266s. (Pre-existing aiosqlite "Event loop is closed" teardown warning observed — unrelated to this leg.)
- Re-ran logging+lifespan post-rebuild — **11 passed**.

**Rebuild verification (NOT deferred — `make rebuild` succeeded in-environment):**
- `docker compose build the-one` succeeded; container recreated and reached healthy.
- `docker exec the-one cat /proc/1/comm` → **`tini`** (acceptance criterion met).
- `docker logs the-one 2>&1 | grep "the-one starting"` → `2026-06-02 ... INFO the_one.interfaces.web.app: the-one starting; log_level=INFO` (acceptance criterion met — `the_one.*` INFO now reaches `docker logs`).

**All acceptance criteria verified at runtime — no pending-rebuild caveat.** Commit deferred to Phase 2d (deferred-commit model). Pre-existing uncommitted `docker-compose.yml` change left untouched.

> **Note:** the Implementation block immediately above (logging_config / Dockerfile / tini) records the **L1** observability-and-reaper work; it landed under this L2 heading in the working tree. The L2 test-baseline-hygiene implementation is recorded below. L1's files were left untouched.

#### Implementation — test-baseline-hygiene (Developer) — 2026-06-02

**Status**: ready → in-flight → landed (FD-performed `/behavior-test` re-run pending — see below).

**Changes (3 files, source untouched outside these):**
- `the_one/interfaces/web/api.py` — NEW dev-mode-gated test-seam endpoint `POST /api/_test/chat/sessions/{session_id}/routing-audit` (placed right after `purge_chat_messages`, the sibling session-scoped POST). Gates FIRST on `settings.dev_mode` → **403** ("test-seam endpoint requires THE_ONE_DEV_MODE=true") when off; parses the body, pulls `routing = data.get("routing")`, returns **400** if it's not a list; `repo = await _chat_repo()` then `set_session_metadata_key(session_id, "routing", routing)` (NOT the `session_metadata`-dropping `update`); `KeyError` → **404**; returns `{"count": len(routing)}`. Commented as an M11 F15 L2 dev-mode test seam citing the `app.py:118` / `api.py:3378` precedents.
- `tests/test_db_api.py` — NEW `TestRoutingAuditSeedEndpoint` (6 tests, using the existing `client` fixture + the `patch("…api.settings"); mock_settings.dev_mode = …` toggle from `test_provider_api.py:1998+`): dev-mode happy path (count matches); round-trip visible via `GET /api/chat/sessions/{id}` (`session_metadata.routing` length); overwrite semantic (re-POST full 5 replaces); non-dev → 403; missing session → 404; non-list body → 400.
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — Preconditions seed bullet rewritten: primary seed is now the new endpoint via one `curl -X POST … /routing-audit -d '{"routing":[…]}'` (the broken `PUT` removed as primary; old PUT-drops-metadata caveat noted; direct `aiosqlite UPDATE` kept as documented fallback; `jq` length probe kept). Step 6's "append 5th entry" now re-POSTs the **full 5-entry array** to the same endpoint (overwrite semantic spelled out). Intent + Steps 1-5/7 assertions untouched.

**Test results (all via `docker exec the-one pytest … -x --timeout 30`):**
- `tests/test_db_api.py::TestRoutingAuditSeedEndpoint` — **6 passed**.
- `tests/test_db_api.py` (full module) — **102 passed**.
- Full backend suite (`-m 'not browser and not live and not pixel and not requires_bwrap'`) — **2829 passed, 4 skipped, 524 deselected** in 266s. (Pre-existing aiosqlite "Event loop is closed" teardown warning observed — unrelated to this leg.)
- **Browser baseline (the retirement criterion)** — `tests/browser/test_flow_agent_tabs.py` + `tests/browser/test_flow_studio_navigation.py` (`-m browser --timeout 90`): **22 passed, 1 skipped** in 32s. Chromium launched cleanly — no `_ensure-playwright` / `install-deps` needed (L1 rebuild's deps still restored). Confirms the F13/F14 "2 pre-existing browser fails" fold-in is **`already-satisfied`** (F14 L5 resolved both; the 22-passed count matches L2 recon exactly).

**Manual smoke (dev container, dev-mode on):**
```
SID=8ec02a404b58   # picked via GET /api/chat/sessions
POST /api/_test/chat/sessions/$SID/routing-audit  -d '{"routing":[{…stepped entry…}]}'  → {"count":1}
GET  /api/chat/sessions/$SID  → session_metadata.routing length = 1
```
Confirms the live round-trip: POST seeds, detail endpoint surfaces it. (POST returning 200 — not 403 — also confirms the dev container runs `THE_ONE_DEV_MODE=true`, so the behavior-test seed will work.)

**Pending FD:** the **`/behavior-test audit-log-inspector-renders-routing-entries` re-run** (cache-cold: fresh tab + `ignoreCache=true`, per the F13 transient-cache lesson) is FD-performed and NOT yet run — the corresponding acceptance criterion stays unchecked in the leg artifact. The autonomous portion (endpoint + unit tests + spec update + retirement evidence + backend/browser baselines) is complete.

**Commit deferred to Phase 2d** (deferred-commit model). Pre-existing uncommitted `docker-compose.yml` change + L1's uncommitted files left untouched.

---

### L3 — multi-bot-hat-driver-foundation

#### Implementation (Developer) — 2026-06-01

**Status**: ready → in-flight → landed (skeleton complete; **live smoke PENDING operator tokens**).

**What was built (8 files):**
- `the_one/interfaces/web/api.py` — NEW dev-mode-gated test-seam LOOKUP endpoint `GET /api/_test/chat/sessions/lookup` (placed right after the L2 `routing-audit` seed). Gates FIRST on `settings.dev_mode` → **403** when off; query params `connector_id`, `channel_id`, optional `thread_id`; `repo = await _chat_repo()` → `find_most_recent_by_external_key(platform="discord", connector_id=…, channel_id=…, thread_id=…)`; returns `{"session_id": <id or None>}` (null — not 404 — on no-match, so the driver can poll a stable shape). No production API shape change.
- `tests/test_db_api.py` — NEW `TestSessionLookupSeamEndpoint` (3 tests, same `patch("…api.settings"); mock_settings.dev_mode=…` toggle as L2): match-found returns the session id (seeds a connector-keyed session via `POST /api/chat/sessions` with `platform/connector_id/channel_id`), no-match returns `{"session_id": null}`, non-dev → 403.
- `tests/live/discord_hat/__init__.py`, `config.py`, `driver.py`, `report.py`, `test_smoke.py` — NEW driver package. `config.py`: frozen `HatConfig` + `load()` (None if env absent) + `skip_if_unconfigured()`; reads `THE_ONE_HAT_BOT_TOKENS` (comma-split) or `THE_ONE_HAT_BOT_TOKEN_{1,2,3}`, `_GUILD_ID`, `_CHANNEL_IDS`, `_CONNECTOR_ID`, `_BOT_USER_ID`, `THE_ONE_TEST_URL` (default `http://localhost:8484`). `driver.py`: `BotDriver` async ctx-mgr (N `discord.Client`s, `message_content` intent, `client.start()` as tasks, per-client `on_ready` await w/ 30s bound, clean shutdown cancelling tasks + closing clients), `mention()`/`post()`/`dm()`, plus HTTP-API assertion helpers `wait_for_session` (polls the lookup seam then GETs the detail), `latest_routing_entry`, `inbound_peer_names` (filters `role=="user"` per the cycle-2 non-blocking note). `report.py`: `HatReport` accumulating `{criterion,status,evidence}` rows + markdown `render()`. `test_smoke.py`: one `@pytest.mark.discord_hat` smoke per leg step 6 (engage via mention→`stepped`; F6 `peer_name` attribution; negative control non-mention→`policy-silent`/`always-listen-off`; DM→separate session); all gated by `skip_if_unconfigured()`. Driver bots are posting-only (M2 feedback-loop guard).
- `tests/live/discord_hat/.env.hat.example` — NEW committed template (placeholders only, incl. `THE_ONE_HAT_BOT_USER_ID`).
- `pyproject.toml` — `discord_hat` marker registered; `addopts` deselect extended `… and not discord_hat`.
- `Makefile` — `test-discord-hat` target mirroring `test-live`.
- `.gitignore` — `tests/live/discord_hat/.env.hat` + `*.env.hat` (the existing `.env` rule does NOT match `.env.hat`).

**Test results (all `docker exec the-one …`):**
- `ruff check tests/live/discord_hat/ the_one/interfaces/web/api.py` — **clean**.
- `python -c "import tests.live.discord_hat.driver, …config, …report"` — **imports OK**.
- `pytest -m discord_hat tests/live/discord_hat/ -q` (no hat env) — **1 skipped, 0 errors** (suite-safety gate holds; marker registered, no unknown-mark warning).
- `pytest tests/test_db_api.py::TestSessionLookupSeamEndpoint` — **3 passed**.
- `pytest tests/test_db_api.py` (full module) — **105 passed**.
- Full backend suite (`-m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat'`) — **2832 passed, 4 skipped, 525 deselected** in 268s; HAT NOT collected. (Pre-existing aiosqlite "Event loop is closed" teardown warning — unrelated.)
- Token-leak grep (Discord token shape) over `tests/live/discord_hat/` — **clean**.
- Gitignore: `.env.hat` ignored, `.env.hat.example` tracked — confirmed.

**Manual lookup smoke (dev container, dev-mode on):** `GET /api/_test/chat/sessions/lookup?connector_id=bogus-xyz&channel_id=nope-123` → **HTTP 200 `{"session_id":null}`** (confirms gate-open path + null-on-no-match; no connector-attached session existed in the dev DB to positive-match, but the unit test covers match-found). 403 path covered by unit test.

**Live smoke PENDING operator tokens.** The `@pytest.mark.discord_hat` smoke is built and skips cleanly without env. The FD runs `make test-discord-hat` once the operator provisions the 3 bot tokens + test-guild ids + the-one's bot user id (the leg's PENDING-provisioning acceptance criterion). Everything else is complete so the live smoke runs the moment tokens land.

**Note on container config:** the running `the-one` container bind-mounts `the_one/`, `tests/`, `scripts/` but bakes `pyproject.toml` into the image. The api.py endpoint + tests are live immediately (bind-mounted); the new marker/addopts in `pyproject.toml` were validated by `docker cp pyproject.toml the-one:/app/pyproject.toml` for this run — a normal `make rebuild` will bake them in.

**Commit deferred to Phase 2d** (deferred-commit model). Pre-existing uncommitted `docker-compose.yml` change + prior legs' uncommitted files left untouched.

---

### L4 — multi-user-routing-hat

#### Implementation (Developer) — 2026-06-01

**Status**: ready → in-flight → landed (BUILD complete; **live run PENDING FD**).

**What was built (3 files):**
- `tests/live/discord_hat/driver.py` — three small additions: `set_agent_connector_acl(base_url, agent_name, account_id, acl)` (GET full agent body → merge `{account_id: acl}` into `connector_acls` → PUT the whole body; returns the PRIOR `connector_acls` dict-or-None for exact restore), `restore_agent_connector_acls(base_url, agent_name, prior)` (GET → set `connector_acls = prior` → PUT; restores to the captured value, None included), and `post_and_wait_new_routing(base_url, connector_id, channel_id, bots, sender_idx, content, *, timeout=90)` (snapshots routing length, posts from `bots[sender_idx]`, polls the session detail until a NEW entry lands with a terminal disposition `stepped`/`no-eligible`, returns that latest entry — the isolated-posting correlation helper, since routing entries carry no `peer_id`). Agent names are URL-encoded (`Connector Agent 1` has a space). `PUT /agents/{name}` is a full-config replace (`AgentConfig.model_validate` at `api.py:490`), so the helpers GET-mutate-PUT the whole body.
- `tests/live/discord_hat/test_multi_user.py` (NEW) — one `@pytest.mark.discord_hat` test (`skip_if_unconfigured`), three phases with generous timeouts (each engaged post drives one `agent.step` under a per-session lock): **Phase A** posts an `@mention` from bots 0/1/2 into channel_ids[0], `wait_for_session(..., until=≥3 distinct inbound peer_names, timeout=180)`, asserts ONE stable session id + all 3 display names present (#5 topology + #13 attribution). **Phase B** sets Connector Agent 1 overlay `{"peers":[{"id":bot0},{"id":bot1}],"channels":None}`, isolated-posts bot0 → new stepped entry `agent=="Connector Agent 1"`, isolated-posts bot2 → new stepped entry `agent=="Connector Agent 2"` (#5 per-user ACL differentiation via first-eligible fall-through). **Phase C** sets BOTH agents' overlays excluding bot2, isolated-posts bot2 → `disposition=="no-eligible"` (#5 hard-deny). A `finally` RESTORES both agents' `connector_acls` to the captured prior (None-safe via an `_UNSET` sentinel — Agent 2 is only restored if Phase C mutated it). Builds a `HatReport` and `print(report.render())` under `-s`. **CRITICAL** per-agent `channels` is `None` (inherit), never `[]` (the DMs-only trap that denies guild messages).
- `tests/behavior/discord-multi-user-routing.md` — Steps table + disposition note rewritten to the L3-proven shapes: ONE shared session; routing `disposition: stepped` carries NO `policy.outcome`; routing entries lack `peer_id` so peer→agent correlation needs isolated one-at-a-time posting; the ACL step is now routing-differentiation (Agent 1 overlay → bot C routes to Agent 2) plus a hard-deny → no-eligible; DM-isolation reframed as the human pass (bot-to-bot DM is blocked by Discord 50007). Added a "Committed counterpart" callout referencing `test_multi_user.py`; the two-agents precondition updated to the L4 set/restore model. Intent + format preserved.

**Non-live validation (all `docker exec the-one …`):**
- `ruff check tests/live/discord_hat/` — **clean** (All checks passed).
- `python -c "import tests.live.discord_hat.test_multi_user, tests.live.discord_hat.driver"` — **imports OK**.
- `pytest -m discord_hat tests/live/discord_hat/test_multi_user.py -q` with NO env (`.env.hat` NOT sourced) — **1 skipped, 0 errors** (suite-safety gate holds).
- Full backend suite (`-m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat'`) — **2832 passed, 4 skipped, 526 deselected** in 266s; HAT NOT collected. (Pre-existing aiosqlite "Event loop is closed" teardown warning — unrelated, noted in prior leg entries.)

**Live run PENDING FD.** The test posts real messages into the test guild and mutates the operator's live Connector Agent 1/2 `connector_acls` (restored in a `finally`), so the Developer does NOT run it. The FD runs (env sourced):
`docker exec the-one bash -lc 'set -a; source /app/tests/live/discord_hat/.env.hat; set +a; cd /app && pytest -m discord_hat tests/live/discord_hat/test_multi_user.py -v -s --timeout 300'` → capture the HatReport table; then confirm both agents' `connector_acls` restored to their pre-test value.

**Commit deferred to Phase 2d** (deferred-commit model). `docker-compose.yml` + prior legs' uncommitted files left untouched. Did not run the live test.

#### Live run (FD) — 2026-06-02 — **PASS 4/4**
`pytest -m discord_hat test_multi_user.py` against the real guild (20.5s):

| Criterion | Status | Evidence |
|---|---|---|
| #5 topology — 3 bots → ONE channel-scoped session | PASS | single session `57df1bd3fda8431188227ae015ffb9cf`; 3 distinct inbound peer_names |
| #13 attribution — F6 peer_name per bot | PASS | inbound peer_names ⊇ ['HAT Test Bot 1','HAT Test Bot 2','HAT Test Bot 3'] |
| #5 per-user ACL differentiation (same channel, 2 agents) | PASS | bot0 → 'Connector Agent 1' (admitted); bot2 → 'Connector Agent 2' (Agent-1-denied → fell through, first-eligible) |
| #5 hard-deny — bot2 excluded by both agents → no-eligible | PASS | disposition='no-eligible' (every agent denied) |

**Cleanup verified:** both Connector Agent 1/2 `connector_acls` restored to `None` (pre-test value) post-run — the self-contained set/restore works; re-runnable.

**L4 closes mission criteria #5 (multi-user routing) and #13 (peer-name attribution) against real traffic.** Status → completed.

---

### L5 — multi-channel-routing-hat

#### Implementation (Developer) — 2026-06-01

**Status**: ready → in-flight → landed (BUILD complete; **live run PENDING FD**).

**What was built (3 files):**
- `tests/live/discord_hat/driver.py` — two additions mirroring the L4 ACL-helper style: `set_connector_routing(base_url, connector_id, routing)` (GET the full connector → take `config = body["config"]` → record `prior = config.get("routing")` → `config["routing"] = routing` → PUT `{"config": config}` with NO `secrets` key so the token is preserved; returns the PRIOR routing dict-or-None for exact restore) and `restore_connector_routing(base_url, connector_id, prior)` (GET → `config["routing"] = prior` (None-safe) → PUT `{"config": config}`). Both typed + commented; routing dict shape `{"rules": list, "default": ...}` (BOTH keys), `RoutingRule.match` is a LIST.
- `tests/live/discord_hat/test_multi_channel.py` (NEW) — one `@pytest.mark.discord_hat` test (`skip_if_unconfigured`), unique nonce. Captures `prior = set_connector_routing(base, CID, {"rules":[ch1→Agent1, ch2→Agent2], "default":Agent1})`, wraps the rest in try/finally. **Per-channel default**: PRIMES each cold channel with a direct `bots.post(0, channel_id, …@mention…)` + `wait_for_session(..., until=disposition=="stepped", timeout=120)` (NOT `post_and_wait_new_routing` — it requires a pre-existing session and would block on a cold channel); asserts ch1→Agent 1/scope=channel, ch2→Agent 2/scope=channel, ch3→Agent 1/scope=default; collects each `detail["id"]`. Asserts `len(set(ids))==3` (distinct channel-keyed sessions). **Channel-scoped override** (ch3's session now exists): sets routing with an added ch3→Agent 2 channel rule, then `post_and_wait_new_routing(..., ch3, …, timeout=120)`; asserts the new entry `agent=="Connector Agent 2"`, `scope=="channel"`, `reason=="rule-match"`. `finally: restore_connector_routing(base, CID, prior)`. Builds a `HatReport`, `print(report.render())` under `-s`.
- `tests/behavior/discord-multi-channel-routing.md` (NEW) — Witnessed spec mirroring `discord-multi-user-routing.md`: preconditions (connector + Agent 1/2 + 3 channels, `channel_id:"*"` allowlist, `@mention` engagement), steps driving per-channel `@mention` posts asserting the per-channel routed agent (`[mixed-frame]` session-detail routing entry `agent`/`scope`/`reason`) + the channel-scoped override; restore-in-`finally` precondition; "Committed counterpart" callout → `test_multi_channel.py`. Status `draft`.

**Non-live validation (all `docker exec the-one …`):**
- `ruff check tests/live/discord_hat/` — **clean** (All checks passed).
- `python -c "import tests.live.discord_hat.test_multi_channel, tests.live.discord_hat.driver"` — **imports OK**.
- `pytest -m discord_hat tests/live/discord_hat/test_multi_channel.py -q` with NO env (`.env.hat` NOT sourced) — **1 skipped, 0 errors** (suite-safety gate holds).
- Full backend suite (`-m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat'`) — **2832 passed, 4 skipped, 527 deselected** in 267s; HAT NOT collected (the +1 deselected vs L4's 526 is the new `test_multi_channel.py`). (Pre-existing aiosqlite "Event loop is closed" teardown warning — unrelated, noted in prior leg entries.)

**Live run PENDING FD.** The test posts real messages into the test guild AND mutates the operator's live connector `config.routing` (restored in a `finally`), so the Developer does NOT run it. The FD runs (env sourced):
`docker exec the-one bash -lc 'set -a; source /app/tests/live/discord_hat/.env.hat; set +a; cd /app && pytest -m discord_hat tests/live/discord_hat/test_multi_channel.py -v -s --timeout 300'` → capture the HatReport table; then confirm `config.routing` restored to its pre-test value (`curl -s "$URL/api/connectors/58f1fe5a833f" | jq '.config.routing'` → pre-test value, currently `null`).

**Commit deferred to Phase 2d** (deferred-commit model). `docker-compose.yml` + prior legs' uncommitted files left untouched. Did not run the live test.

#### Live run (FD) — 2026-06-02 — **PASS 4/4**
`pytest -m discord_hat test_multi_channel.py` against the real guild (5.5s):

| Criterion | Status | Evidence |
|---|---|---|
| #6 per-channel routing — ch1→Agent 1, ch2→Agent 2 (channel rules) | PASS | ch1→'Connector Agent 1' scope=channel; ch2→'Connector Agent 2' scope=channel |
| #6 default fall-through — ch3 (no rule) → per-account default | PASS | ch3→'Connector Agent 1' scope=default |
| #6 separate sessions — ch1/ch2/ch3 → 3 distinct session ids | PASS | 3 distinct ids (ch1 reuses the L3/L4 channel session; ch2/ch3 fresh) |
| #6 channel-scoped override — ch3 rule re-routes away from default | PASS | ch3→'Connector Agent 2' scope=channel reason=rule-match (was default→Agent 1) |

**Cleanup verified:** connector `config.routing` restored to `None` (pre-test) post-run. Design-review caught a real blocker pre-implementation (don't call `post_and_wait_new_routing` on a cold channel — prime with `wait_for_session(until=stepped)` first); fix applied, live run clean first try.

**L5 closes mission criterion #6 (multi-channel routing) against real traffic.** Status → completed.

---

### L6 — multi-agent-routing-hat

#### Implementation (Developer) — 2026-06-01

**Status**: ready → in-flight → landed (BUILD complete; **live run PENDING FD**).

**What was built (3 files):**
- `tests/live/discord_hat/driver.py` — generalized `post_and_wait_new_routing` with an optional `until_entry: Callable[[dict], bool] | None = None`. When `None` (the L4/L5 default), it keeps the EXACT prior behavior — waits until `len(routing) > before` AND the latest entry's `disposition in {"stepped","no-eligible"}` (the default is now a local `until_entry` closure with that predicate, so L4/L5 call sites are behavior-unchanged). When provided, it waits until `len(routing) > before` AND `until_entry(latest)`. `/talk-to`/`/new` callers pass `until_entry=lambda e: e.get("disposition") == "command-intercepted"` (fast intercept at dispatch step 11, no LLM). Backward-compatible signature (new keyword-only param); ruff clean.
- `tests/live/discord_hat/test_multi_agent.py` (NEW) — one `@pytest.mark.discord_hat` test (`skip_if_unconfigured`), unique nonce, channel = `cfg.channel_ids[1]` (test-channel-2), `CID = cfg.connector_id`. Captures `prior_routing` via a small `_get_connector_routing` GET helper (Phase A runs with no routing change, so the restore value is captured up front rather than from `set_connector_routing`'s return). try/finally. **Phase A — override:** posts `/talk-to Connector Agent 2` (`until_entry=command-intercepted`) → asserts `disposition=="command-intercepted"` AND `intercept_source=="builtin"` (cheap extra signal the built-in handler fired); then an `@mention` (default `until_entry`) → asserts `scope=="override"`, `agent=="Connector Agent 2"`, `reason=="override"`. **Phase B — override beats rule:** `set_connector_routing` to `{"rules":[ch2→Agent 1], "default":Agent 1}`; re-issues `/talk-to Connector Agent 2` (command-intercepted) + `@mention` → asserts `scope=="override"`, `agent=="Connector Agent 2"` (step-1 override beat the step-2 rule). **Phase C — dynamic re-override:** `/talk-to Connector Agent 1` (command-intercepted) + `@mention` → asserts `agent=="Connector Agent 1"`, `scope=="override"`. **finally:** best-effort `bots.post(0, ch2, "/new")` (rotate session → clear override) guarded so a post failure can't mask the restore, then `restore_connector_routing(base, CID, prior_routing)`. Builds a `HatReport`, `print(report.render())` under `-s`. A comment notes all phases must complete within `session_continuation_seconds` (interactive HAT speed is fine) so a slow run doesn't rotate the session mid-phase.
- `tests/behavior/discord-multi-agent-routing.md` (NEW) — Witnessed spec mirroring `discord-multi-channel-routing.md`: preconditions (connector + Agent 1/2 + test-channel-2, both agents ACL-admitting so both are valid `/talk-to` targets, `@mention` engagement, timing-within-continuation-window note); steps driving `/talk-to` → `@mention` asserting `disposition=command-intercepted`/`intercept_source=builtin` then `scope=override`/`agent`/`reason=override` via the `[mixed-frame]` session-detail routing entry, plus override-beats-rule (Phase B) and dynamic re-override (Phase C); restore + `/new` in `finally`; "Committed counterpart" callout → `test_multi_agent.py`. Notes #7's multi-agent/multi-peer/per-(agent,peer)-ACL facets are L4-covered. Status `draft`.

**Non-live validation (all `docker exec the-one …`):**
- `ruff check tests/live/discord_hat/` — **clean** (All checks passed).
- `python -c "import tests.live.discord_hat.test_multi_agent, tests.live.discord_hat.driver"` — **imports OK**.
- `pytest -m discord_hat tests/live/discord_hat/ -q` with NO env — **4 skipped, 0 errors** (test_multi_user/test_multi_channel/test_multi_agent + smoke all collect+skip; the helper generalization didn't break L4/L5 collection).
- Full backend suite (`-m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat'`) — **2832 passed, 4 skipped, 528 deselected** in 267s; HAT NOT collected (the +1 deselected vs L5's 527 is the new `test_multi_agent.py`). (Pre-existing aiosqlite "Event loop is closed" teardown warning — unrelated, noted in prior leg entries.)

**Live run PENDING FD.** The test posts real messages into the test guild AND mutates the operator's live connector `config.routing` (restored in a `finally`), so the Developer does NOT run it. The FD runs (env sourced):
`docker exec the-one bash -lc 'set -a; source /app/tests/live/discord_hat/.env.hat; set +a; cd /app && pytest -m discord_hat tests/live/discord_hat/test_multi_agent.py -v -s --timeout 300'` → capture the HatReport table; then confirm `config.routing` restored to its pre-test value (`curl -s "$URL/api/connectors/58f1fe5a833f" | jq '.config.routing'` → pre-test value, currently `null`).

**Commit deferred to Phase 2d** (deferred-commit model). `docker-compose.yml` + prior legs' uncommitted files left untouched. Did not run the live test.

#### Live run (FD) — 2026-06-02 — **PASS 3/3**
`pytest -m discord_hat test_multi_agent.py` against the real guild (11.3s):

| Criterion | Status | Evidence |
|---|---|---|
| #7 /talk-to override — intercept + next @mention routes to target | PASS | /talk-to 'Connector Agent 2' → command-intercepted (intercept_source=builtin); next @mention → 'Connector Agent 2' scope=override reason=override |
| #7 override beats channel rule | PASS | with ch2→'Connector Agent 1' rule set, /talk-to Agent 2 + @mention → 'Connector Agent 2' scope=override (step-1 override > step-2 rule) |
| #7 dynamic re-override | PASS | /talk-to 'Connector Agent 1' + @mention → 'Connector Agent 1' scope=override (re-pointed mid-session) |

**Cleanup verified:** connector `config.routing` restored to `None` post-run; the `post_and_wait_new_routing` generalization (optional `until_entry`) left L4/L5 byte-unchanged (re-run no-env SKIP confirmed 4 tests collect+skip).

**L4 + L6 together CLOSE mission criterion #7** (L4: multi-agent + multi-peer + per-(agent,peer) ACL; L6: the peer-issued `/talk-to` override). L6 status → completed.

---

## Decisions

_Runtime decisions will be recorded here during execution._

---

## Deviations

_None yet._

---

## Anomalies

_None yet._

---

## Session Notes

### 2026-06-01 — Planning
- Context gathered: M11 mission, F13/F14 debriefs, existing Discord behavior-test specs (`discord-slash-end-to-end`, `discord-engagement`), full codebase interrogation of the connector subsystem.
- Scope debated: operator pushed back on rate-limiting necessity → resolved to defer #17 to the daily-driver flight.
- Premise audit surfaced `ingest_bots` + author-id peers → unlocked the fully-automatable multi-bot driver apparatus.
- Draft behavior-test spec authored: `tests/behavior/discord-multi-user-routing.md` (status `draft`).

### 2026-06-01 — Design Review (Architect, 2 cycles)

**Cycle 1 → needs rework.** Apparatus premise verified (ingest_bots + author-id peers; no author-type branch in routing/ACL). Two HIGH issues:
- **H1 — session keying excludes `peer_id`** (`_session.py:123`): ≥3 senders in one channel share ONE session, contradicting the spec's "3 distinct sessions" and mission #5's "peer-scoped session." Escalated to operator → resolved: shared-channel = one session (attribution + ACL + routing carry per-peer-ness); DM = its own session ("channel of 1"). mission.md #5 reworded; "Shared-channel session semantics" DD added; spec steps reframed + DM-isolation step added. No substrate change.
- **H2 — channel messages silent by default** (policy gate): plain non-mention posts need `always_listen` or `@mention`. Resolved.
- M1 (disposition vocab → `no-eligible` for ACL-deny), M2 (`ingest_bots` feedback-loop guard: burner bots posting-only + isolated guild), L1 (`make test-live` is hardcoded to `test_aiat.py`; added dedicated `discord_hat` marker + `make test-discord-hat`). All incorporated.

**Cycle 2 → approve with changes.** All five resolutions verified against code. One residual (N1): the `always_listen` path STILL runs the engagement inference, which is strongly biased to silence (`_inference.py:73,81`) — so `always_listen=true` alone doesn't deterministically engage; plain messages could land `policy-silent` and read as false routing failures. **Resolution (better than the suggested wording fix):** switch the routing-leg engagement to `@mention`, which engages via the mention path with NO inference. Verified `is_mention` (`_discord.py:1825`) checks the bot's id in `message.mentions` independent of author → a burner-bot mention registers. DD reframed (`@mention` primary, `always_listen`+substantive fallback); L3 smoke now also verifies bot-mention registration; spec updated. N2 (cosmetic disposition wording) tightened.

**Design review complete (2/2 cycles).** No open blocking issues.
