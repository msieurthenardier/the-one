# Leg: multi-bot-hat-driver-foundation

**Status**: completed — skeleton + live smoke PASS 3/3 (DM premise deferred to L7; bot-to-bot DM blocked by Discord). See flight log L3 entry (2026-06-02).
**Flight**: [Live-Traffic HAT Capability](../flight.md)

## Objective

Build the committed, re-runnable foundation of the live-traffic HAT: a `discord.py` multi-bot driver under `tests/live/discord_hat/` (bot lifecycle, env-based config with skip-if-absent, a scenario API, and a per-criterion report structure), gated behind a new `discord_hat` pytest marker + `make test-discord-hat` target, plus a smoke scenario that — when bot tokens are present — confirms the three load-bearing premises live (bot-peer equivalence, author-agnostic `@mention`, and channel-shared-vs-DM-isolated session topology) before L4–L6 assert against them. This is the criterion-#11 artifact's skeleton.

## Context

- **Apparatus (FD-confirmed, see flight log 2026-06-02):** 3 Discord **bot-application tokens** drive the senders from code (`ingest_bots=true` on the test connector → distinct bot author ids → distinct peers). Human user accounts are reserved for L7's pairing-approval pass. Chosen over human/Chrome-MCP because only a code-driven bot driver is an autonomous, re-runnable regression gate — the core of criterion #11.
- **Premises this leg confirms live** (all statically audited; the smoke makes them empirical before L4 relies on them):
  - **Bot-peer equivalence** — `ingest_bots` gate at `_discord.py:933-937`; `peer_id = str(message.author.id)` at `_discord_translate.py:124`; no author-type branch in `_routing.py`/`_acl.py`/`_inbound.py`/`_session.py` (Architect grep).
  - **Author-agnostic `@mention`** — `is_mention` (`_discord.py:1825`) checks the bot's id in `message.mentions`, independent of author → a bot-authored mention engages via the `mention` policy outcome with NO inference. The routing legs use `@mention` for deterministic, inference-free engagement.
  - **Session topology** — sessions key on `(platform, connector_id, channel_id, thread_id)` (`_session.py:123`), `peer_id` excluded → a shared channel = ONE session; a DM = its own session (`channel_id = message.channel.id`, `_discord_translate.py:99`).
- **Two observability gaps this leg closes (design-review HIGH findings), and the assert-against-real-shapes discipline they enforce:**
  - **The REST session API does not expose connector-keying fields.** `_session_summary` (`api.py:3271`) returns only `{id, agent_name, title, created_at, updated_at}`; the detail endpoint (`api.py:3167`) adds only `messages` + `session_metadata`. Neither carries `connector_id`/`channel_id`, so the driver cannot locate the connector-attached session by (connector, channel). This leg adds a **dev-mode-gated test-seam LOOKUP endpoint** (sibling to L2's seed) that resolves `(connector_id, channel_id[, thread_id])` → session id via `ChatSessionRepository.find_most_recent_by_external_key` (`repositories.py:872`). Isolated/test-only; no production API shape change.
  - **The engaged-path routing entry is intentionally minimal.** A `stepped` audit entry is `{ts, agent, rule_index, scope, match, reason, disposition}` — NO `policy.outcome`, NO `peer_id` (`_inbound.py:773-776` comment; `policy` attaches only on the `policy-silent` path at `:800`). So the smoke must NOT assert `outcome=="mention"` or `peer_id` on the routing entry. Instead: **the test connector runs `always_listen=FALSE`** so the policy gate has exactly two channel outcomes — `@mention → stepped`, and `non-mention → policy-silent` with `policy.outcome == "always-listen-off"` (no inference call at all). A `stepped` entry after an `@mention` therefore unambiguously means the mention engaged; the non-mention → `policy-silent` contrast is the negative control. Bot-peer ingestion is verified via the **F6 `peer_name` on the inbound message** in the session's `messages` (the detail endpoint exposes `messages`), which is also criterion #13's observable — NOT via a peer_id on the routing entry. (This supersedes the flight DD's "always_listen=true fallback" for the routing legs L3–L6; L7's mentions-aware re-verify flips `always_listen` on to exercise the inference path. Recorded in the flight log.)
- **Existing conventions to mirror:**
  - Live tests hit the-one over HTTP via `httpx` against `THE_ONE_TEST_URL` (default `http://localhost:8484`), session-scoped `base_url` fixture — see `tests/test_aiat.py:1-45`.
  - `discord.py` client + intents construction — `_discord.py:769-800` (`discord.Intents.default()` then `message_content`/`members`/`guilds`). `discord.py>=2.4,<2.5` is pinned (`pyproject.toml:28`).
  - Multiple concurrent `discord.Client`s on one event loop is the standard pattern (Architect-confirmed; the-one itself runs its client as a background task).
- **Marker discipline:** the existing `live` marker means "real LLM APIs" and `make test-live` is hardcoded to `test_aiat.py` — do NOT reuse it. Add a dedicated `discord_hat` marker and extend the default deselect so the HAT never runs in the normal suite (it needs tokens + a live guild).
- **Secrets:** bot tokens are injected via env and are **gitignored, never committed** (mission constraint). The driver reads env only; a committed `.env.hat.example` documents the variable names.

## Inputs

- `pyproject.toml:56-72` — `[tool.pytest.ini_options]`: `markers` list + `addopts` deselect string (`-m 'not live and not browser and not pixel and not requires_bwrap'`).
- `Makefile` — `test-live` target (`Makefile:128-130`) as the shape to mirror for `test-discord-hat`; `_ensure-playwright` as the optional-setup-target precedent.
- `tests/test_aiat.py:1-45` — live-test httpx/base_url/session-id conventions.
- `the_one/connectors/_discord.py:769-800` — intents construction; `:1825` — `is_mention`.
- The-one HTTP API for assertions: `GET /api/chat/sessions/{id}` (`api.py:3167`) exposes `session_metadata` (incl. `routing`) AND `messages` (incl. F6 `peer_name`). The list/summary (`_session_summary`, `api.py:3271`) does NOT carry connector-keying fields — hence the new lookup seam below.
- `ChatSessionRepository.find_most_recent_by_external_key` (`repositories.py:872`) — resolves a session by `(platform, connector_id, channel_id, thread_id)`; the lookup endpoint wraps this.
- `the_one/interfaces/web/api.py` — the L2 dev-mode seed endpoint `POST /api/_test/chat/sessions/{id}/routing-audit` is the sibling pattern for the new dev-mode-gated lookup seam (gate, `_chat_repo()`, 403/404). The L2 seed is NOT used for seeding here (the HAT seeds via real bot traffic), but its endpoint shape is the template.
- The test connector account id, guild id, 3 channel ids, AND **the-one's Discord bot user id** (`THE_ONE_HAT_BOT_USER_ID` — needed for the `@mention` and DM target; `is_mention` matches `message.guild.me.id`, the gateway-assigned bot user id, which the-one does NOT persist to the API) — all operator-provided via env (see config).
- The L2 dev-mode seed endpoint exists but is NOT used here (the HAT seeds via real bot traffic, not the test seam).

## Outputs

- `the_one/interfaces/web/api.py` — NEW dev-mode-gated test-seam LOOKUP endpoint (sibling to L2's seed) resolving `(connector_id, channel_id[, thread_id])` → session id via `find_most_recent_by_external_key`. + unit tests.
- `tests/live/discord_hat/__init__.py` + modules:
  - `config.py` — env loader (`hat_config()` returning tokens, guild id, channel ids, connector id, **the-one bot user id**, base url) with a `skip_if_unconfigured()` helper that calls `pytest.skip(...)` when required env is absent.
  - `driver.py` — `BotDriver`: async context manager that logs in N `discord.Client`s, waits ready, exposes `post(bot_idx, channel_id, content)`, `dm(bot_idx, content)`, and clean shutdown.
  - `assertions.py` (or in `driver.py`) — helpers that poll the-one's HTTP API for the connector-attached session + its `routing` entries, with a bounded poll/timeout.
  - `report.py` — a per-criterion pass/fail report structure (criterion id → status + evidence) the later legs append to.
  - `test_smoke.py` — the `discord_hat`-marked smoke scenario (skips if unconfigured).
- `pyproject.toml` — `discord_hat` marker added; default `addopts` deselect extended with `and not discord_hat`.
- `Makefile` — `test-discord-hat` target.
- `tests/live/discord_hat/.env.hat.example` — committed template of the env var names (NO real values).
- `.gitignore` — ignore any local `tests/live/discord_hat/.env.hat` (or equivalent) holding real tokens.

## Acceptance Criteria

- [ ] `tests/live/discord_hat/` package exists with `config.py`, `driver.py`, `report.py`, and `test_smoke.py` (assertions helper may live in `driver.py`). All modules import cleanly (`docker exec the-one python -c "import tests.live.discord_hat.driver"` or equivalent) and pass `ruff check`.
- [ ] A `discord_hat` pytest marker is registered in `pyproject.toml` `markers`, and the default `addopts` deselect is extended to `... and not discord_hat` so the HAT is excluded from the normal backend suite.
- [ ] A `make test-discord-hat` target runs `pytest -m discord_hat tests/live/discord_hat/` (mirroring `test-live`'s shape).
- [ ] A dev-mode-gated lookup endpoint exists (suggested: `GET /api/_test/chat/sessions/lookup?connector_id=&channel_id=&thread_id=`) that returns the matching session id (or null/404 if none) via `find_most_recent_by_external_key`; **403** when not dev-mode (mirror L2's seed gate). Unit tests cover: match found, no-match, 403 non-dev-mode.
- [ ] `config.py` reads the required env (suggested names: `THE_ONE_HAT_BOT_TOKENS` comma-separated OR `THE_ONE_HAT_BOT_TOKEN_{1,2,3}`; `THE_ONE_HAT_GUILD_ID`; `THE_ONE_HAT_CHANNEL_IDS`; `THE_ONE_HAT_CONNECTOR_ID`; `THE_ONE_HAT_BOT_USER_ID`; `THE_ONE_TEST_URL` default `http://localhost:8484`) and `skip_if_unconfigured()` cleanly `pytest.skip`s when tokens/ids are absent — so `make test-discord-hat` with no env SKIPS (does not error), and the normal suite is unaffected.
- [ ] `BotDriver` brings up N concurrent `discord.Client`s (`Intents.default()` — burner bots only POST; Message Content is a receive capability the-one's own bot carries, NOT the senders), awaits each `on_ready`, exposes `post`/`dm`/shutdown, and tears all clients down cleanly (no leaked tasks/sessions).
- [ ] Bot tokens are sourced ONLY from env; a committed `.env.hat.example` documents the variable names with placeholder values; `.gitignore` excludes any real local env file. No token value appears in any committed file (grep-clean).
- [ ] **(FD-performed once tokens land — PENDING until provisioning)** The smoke scenario PASSES against the real test guild (test connector configured `ingest_bots=true`, **`always_listen=FALSE`**): bot[0] posts a message `@`-mentioning the-one's bot to a test channel → the lookup seam finds the connector-attached session; its latest `routing` entry is `disposition: stepped` (mention engaged, inference fully out of path); the session's `messages` show the inbound attributed with `peer_name` == bot[0]'s display name (bot ingested as a peer; F6 attribution). **Negative control:** bot[0] posts a NON-mention message → its routing entry is `disposition: policy-silent` with `policy.outcome == "always-listen-off"` (confirms the mention is what engaged). **Topology:** bot[0] DMs the-one's bot → a SEPARATE session (distinct `channel_id`) exists. The smoke writes each result into the report structure.
- [ ] The leg lands with the skeleton committed and the smoke either PASSED (if tokens were available) or marked clearly PENDING-provisioning in the flight log (skeleton imports + skips cleanly without tokens).

## Verification Steps

- `docker exec the-one ruff check tests/live/discord_hat/` — clean.
- `docker exec the-one python -c "import tests.live.discord_hat.driver, tests.live.discord_hat.config, tests.live.discord_hat.report"` — imports OK.
- `docker exec the-one pytest -m discord_hat tests/live/discord_hat/ -q` with NO hat env set → all SKIP (0 errors). Confirms the suite-safety gate.
- `grep -rn "discord_hat" pyproject.toml Makefile` — marker + deselect + target present.
- `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' -x --timeout 30 -q` — full backend suite still green and does NOT collect the HAT.
- Token-leak check: `git grep -nE "[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}" -- tests/live/discord_hat/ || echo "no token-shaped strings"` (Discord token shape) — no real tokens committed.
- **(FD, once tokens land)** `make test-discord-hat` with env set → smoke PASS; record in flight log.

## Implementation Guidance

1. **Marker + target first** — add `"discord_hat: live multi-bot Discord HAT (needs bot tokens + a test guild; deselect by default)"` to `pyproject.toml` `markers`; extend `addopts` to `-m 'not live and not browser and not pixel and not requires_bwrap and not discord_hat' --import-mode=importlib`. Add a `test-discord-hat` Makefile target mirroring `test-live` (`docker exec the-one pytest -m discord_hat tests/live/discord_hat/ -v --tb=short`).
1b. **Lookup seam endpoint** (`the_one/interfaces/web/api.py`, beside the L2 seed endpoint) — `GET /api/_test/chat/sessions/lookup`, dev-mode-gated (`if not settings.dev_mode: raise HTTPException(403, …)`, mirroring L2). Query params `connector_id`, `channel_id`, optional `thread_id`. Acquire `repo = await _chat_repo()`, call `find_most_recent_by_external_key(platform="discord", connector_id=…, channel_id=…, thread_id=…)` (read its exact signature at `repositories.py:872`), return `{"session_id": <id or None>}` (or 404 if you prefer not-found semantics — pick one and unit-test it). Unit tests in `tests/test_db_api.py`: match, no-match, 403 non-dev.
2. **`config.py`** — a small frozen dataclass `HatConfig(tokens: list[str], guild_id: str, channel_ids: list[str], connector_id: str, bot_user_id: str, base_url: str)` + `load() -> HatConfig | None` (None if required env absent) + `skip_if_unconfigured() -> HatConfig` that `pytest.skip("discord_hat env not configured")`s when `load()` is None. Read tokens from `THE_ONE_HAT_BOT_TOKENS` (comma-split) or the numbered fallback; read `bot_user_id` from `THE_ONE_HAT_BOT_USER_ID`.
3. **`driver.py`** — `class BotDriver`: `async def __aenter__` logs in each token as a `discord.Client(intents=discord.Intents.default())` (NOT `message_content=True` — the sender bots only POST; requesting a privileged intent the bot apps don't have enabled raises `PrivilegedIntentsRequired` on connect; F15 L3 inline fix confirmed this), starts each `client.start(token)` as a task, awaits a per-client `ready` event (bounded timeout, e.g. 30s). `mention(content)` helper prefixes `f"<@{cfg.bot_user_id}> {content}"` so the post engages the-one via the mention path. `post(bot_idx, channel_id, content)` resolves the channel via `client.get_channel(int(channel_id))` (fetch if not cached) and `await channel.send(content)`. `dm(bot_idx, content)` opens a DM to the-one's bot user (`await client.get_user(int(cfg.bot_user_id)).create_dm()` / `fetch_user`) and sends. `__aexit__` closes all clients and cancels tasks. Keep it minimal and well-commented; this is committed production-grade code.
4. **Assertions helper** — `async def wait_for_session(base_url, connector_id, channel_id, *, thread_id=None, timeout=30) -> dict` polls the lookup seam `GET /api/_test/chat/sessions/lookup?connector_id=&channel_id=` until it returns a non-null `session_id` (or timeout), then `GET /api/chat/sessions/{session_id}` (httpx) and returns the detail dict (incl. `session_metadata.routing` AND `messages`). Siblings: `latest_routing_entry(detail)` returns the last `routing` entry; `inbound_peer_names(detail)` extracts `peer_name` from the inbound `messages`. The lookup seam is the supported way to match connector+channel — do NOT try to match via the connector-field-less `_session_summary` list.
5. **`report.py`** — a simple `HatReport` accumulating `{criterion: str, status: "PASS"|"FAIL"|"PENDING", evidence: str}` rows with a `render()` method (markdown table). Later legs import and extend it.
6. **`test_smoke.py`** — one `@pytest.mark.discord_hat` async test asserting ONLY against fields that exist (see Context): `cfg = skip_if_unconfigured()`; `async with BotDriver(cfg) as bots:`
   - **(engage)** bot[0] posts `bots.mention("smoke ping")` to `cfg.channel_ids[0]`; `detail = await wait_for_session(base_url, cfg.connector_id, cfg.channel_ids[0])`; assert `latest_routing_entry(detail)["disposition"] == "stepped"`.
   - **(attribution / bot-peer ingestion)** assert bot[0]'s display name appears in `inbound_peer_names(detail)` (F6 `peer_name` on the inbound message — confirms the bot was ingested as a peer; this is also criterion #13's observable).
   - **(negative control)** bot[0] posts a NON-mention message to the same channel; the new routing entry has `disposition == "policy-silent"` and `entry["policy"]["outcome"] == "always-listen-off"` (confirms `always_listen=FALSE` and that the mention — not blanket-listen — drove engagement).
   - **(topology)** `await bots.dm(0, "smoke dm")`; `dm_detail = await wait_for_session(base_url, cfg.connector_id, <dm_channel_id>)` resolves a SEPARATE session whose `channel_id` differs from the guild channel (the DM channel id may be discovered from the driver's DM send result). Assert it's a distinct session id.
   - Record each into a `HatReport`. Do NOT assert `policy.outcome` or `peer_id` on a `stepped` entry — they aren't there.
7. **Secrets hygiene** — `.env.hat.example` lists the var names with placeholders; add `tests/live/discord_hat/.env.hat` (and `*.env.hat`) to `.gitignore`. The driver does NOT read a dotenv file unless one is explicitly loaded; env vars are the contract. Never echo tokens in logs.

## Edge Cases

- **No tokens present** → every `discord_hat` test SKIPS (never errors); the normal suite never collects them. This is the default CI/dev state and must stay green.
- **Concurrent clients / event loop** — all `discord.Client`s share the test's running loop; ensure clean shutdown so no "Task was destroyed but it is pending" / unclosed-session warnings leak into other tests (they won't run in the same session as unit tests, but keep teardown clean).
- **Burner bots use `Intents.default()`, NOT `message_content`** — the sender bots only POST; `message_content` is a privileged receive capability that the-one's own bot carries (it reads inbound messages). Requesting a privileged intent the bot apps don't have enabled raises `PrivilegedIntentsRequired` on connect. The bots must be invited with Send Messages permission. (F15 L3 inline fix — confirmed in flight log and `driver.py:68`.)
- **the-one ignores bot authors unless `ingest_bots=true`** — the test connector MUST have `ingest_bots=true` (operator-provisioned). If the smoke sees no session after timeout, the first suspect is `ingest_bots` not set / the bot not on the allowlist / wrong connector id — surface a clear diagnostic (now visible in `docker logs` thanks to L1).
- **Feedback-loop guard (M2 from planning)** — the driver bots are posting-only and never auto-reply; the test connector targets the isolated test guild only. Do not add any auto-reply behavior to the driver bots.
- **Token leakage** — never commit a real token; never log one. The `.env.hat.example` holds placeholders only.
- **discord.py 2.4 API** — use the pinned API surface; `client.start()` vs `client.run()` (use `start` for async-managed lifecycle inside the loop).

## Files Affected

- `the_one/interfaces/web/api.py` — NEW dev-mode-gated lookup seam endpoint.
- `tests/test_db_api.py` — lookup endpoint unit tests (beside L2's seed tests).
- `tests/live/discord_hat/__init__.py`, `config.py`, `driver.py`, `report.py`, `test_smoke.py` — NEW.
- `tests/live/discord_hat/.env.hat.example` — NEW (committed template; includes `THE_ONE_HAT_BOT_USER_ID`).
- `pyproject.toml` — `discord_hat` marker + addopts deselect.
- `Makefile` — `test-discord-hat` target.
- `.gitignore` — ignore local `.env.hat` (the existing `.env` rule does NOT match `.env.hat`; add an explicit pattern).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (the live smoke may be PENDING provisioning — mark clearly)
- [ ] Tests passing (skeleton imports; `discord_hat` tests skip cleanly without env; full backend suite green and excludes the HAT)
- [ ] `ruff check` clean on the new package
- [ ] Update flight-log.md with the L3 entry (skeleton complete; smoke PASS or PENDING-provisioning)
- [ ] Set this leg's status to `completed` (or leave `landed` with smoke PENDING) in this file's header
- [ ] Check off this leg in flight.md
- [ ] Not the final leg — commit handled at flight-level Phase 2d (deferred-commit model)

## Citation Audit

Citations verified/corrected against current code at L3 design time + design review: `pyproject.toml:65` (addopts), `:67-72` (markers), `:28` (discord.py pin) OK; `Makefile:128-130` (test-live) OK; `tests/test_aiat.py:1-45` (live-test conventions) OK; `_discord.py:769-800` (intents) OK; `_discord.py:1825` (is_mention matches `guild.me.id`) OK; `_discord.py:933-937` (ingest_bots gate) OK; `_discord_translate.py:124` (peer_id) + `:99` (DM channel_id) OK; `api.py:3167` (session detail exposes messages+session_metadata) OK; **`api.py:3271` (`_session_summary` — corrected from the draft's `:3232`; it returns only id/agent/title/timestamps, the gap the lookup seam closes)**; `_inbound.py:773-776` (stepped entry omits policy/peer_id) OK; `_inbound.py:800` (policy attaches on policy-silent) OK; `repositories.py:872` (`find_most_recent_by_external_key`) OK; `_session.py:123` (4-tuple keying) OK. All resolved.
