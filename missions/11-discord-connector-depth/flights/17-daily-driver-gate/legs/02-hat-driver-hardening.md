# Leg: hat-driver-hardening

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)

## Objective

Harden the committed live-traffic HAT driver suite (`tests/live/discord_hat/`) into a maintainable, documented, CI-net-covered regression gate — so the F17 full-day run can lean on it and future Discord-touching flights can re-run it without reconstructing tribal knowledge.

## Context

- This bundles the carried HAT-driver debt the F15 + F16 debriefs aimed squarely at F17 (the named forcing function). All of it shares one surface (`tests/live/discord_hat/`), matching the project's `touched-surface-debt-folding` convention.
- **No README exists** for the HAT suite today — the provisioning + run procedure + timing gotchas live only in the F15 flight log and will be lost.
- The HAT tests **SKIP cleanly without `.env.hat`** (`skip_if_unconfigured()`), so they're deselected from the default backend suite — meaning the driver's *pure helpers* have **zero CI regression coverage**; a refactor that breaks `inbound_peer_names` / `latest_routing_entry` / the routing-length logic would only surface on the next operator live run.
- `_BOT_IDS` is hardcoded in `test_multi_user.py` (~`:53`) — the one HAT test that doesn't take its ids from the env contract, so re-provisioning burner bots silently breaks just that file.
- A doc-lag from F15 L3: the leg spec + flight-log note still say the burner bots need a `message_content` intent; the actual fix was `Intents.default()` (burners only POST — Message Content is NOT needed on them; only the-one's own bot needs it).
- This leg is **docs + tests + a small env-contract move** — lower-risk than L1, no production-code behavior change.

## Inputs

- `tests/live/discord_hat/` — `driver.py` (`BotDriver` + the pure helpers `inbound_peer_names`, `latest_routing_entry`, `post_and_wait_new_routing`, `wait_for_session`), `config.py` (env contract: `THE_ONE_HAT_BOT_TOKENS`/`_BOT_TOKEN_{1,2,3}`, `_GUILD_ID`, `_CHANNEL_IDS`, `_CONNECTOR_ID`, `_BOT_USER_ID`), the scenario files (`test_smoke.py`, `test_multi_user.py`, `test_multi_channel.py`, `test_multi_agent.py`, `test_pairing_peers_decoupling.py`), `.env.hat` (gitignored, present).
- `tests/live/discord_hat/test_multi_user.py` (~`:53`) — the hardcoded `_BOT_IDS`.
- The F15 L3 leg spec (`missions/11-discord-connector-depth/flights/15-live-traffic-hat/legs/03-multi-bot-hat-driver-foundation.md`) + the F15 flight-log note — the `message_content`→`Intents.default()` doc-lag.
- The `Makefile` HAT target (confirm exact name — `test-discord-hat` per F15 debrief).

## Outputs

- `tests/live/discord_hat/README.md` — provisioning + run + constraints + timing rationale + scenario catalogue.
- `_BOT_IDS` sourced from the env contract (`config.py`), no longer hardcoded in `test_multi_user.py`.
- A hermetic unit-test file in the DEFAULT (no-creds) backend suite exercising the pure driver helpers against fixture dicts.
- The `message_content` doc-lag scrubbed in the F15 artifacts.
- Default backend suite green (now including the new hermetic helper tests).

## Acceptance Criteria

- [x] `tests/live/discord_hat/README.md` exists and covers, at minimum: **burner-bot provisioning** (created in a *normal* browser — captcha/MFA block automation; **Message Content intent is NOT needed on the burners**, they only post; only the-one's own bot needs it); **how to find the-one's gateway-assigned bot user id**; that the suite **SKIPs without `.env.hat`** and how to populate it (the full env-var contract); the **`_BOT_IDS` re-provisioning gotcha** (now resolved — point at the env var); the **`wait_for_session(until=…)` timing rationale** (poll the session *detail* until the expected state lands, not just session existence — messages + peer_name + the engaged routing entry persist only after `agent.step()`); the **connect-time-closure restart requirement** (`ingest_bots` is read at connect time → reconfigure + container restart before a HAT run); the **bot-can't-DM-bot** constraint (REST 50007 — DM/pairing surfaces need a human pass); and a **catalogue of the committed scenario files** with one line each. No operator machine username or absolute home path appears anywhere in the README (repo-relative paths / `<placeholders>` only).
- [x] The hardcoded bot *user* id tuple (`_BOT_IDS`) — present in **BOTH** `test_multi_user.py:53-57` **and** `test_pairing_peers_decoupling.py:55-59` (identical real Discord snowflakes currently committed to this public repo) — is sourced from the env contract in `config.py` via a new `THE_ONE_HAT_BOT_USER_IDS` comma-separated var (mirror `_read_tokens`/`_read_channel_ids`), added as an **OPTIONAL** `bot_user_ids: list[str]` field on `HatConfig` (default `[]`, **NOT** added to `load()`'s required-fields gate). Both consumer tests read `cfg.bot_user_ids` and locally `pytest.skip` when it's empty — so `test_smoke`/`test_multi_channel`/`test_multi_agent` (which don't use bot ids) are NOT made to skip by the new var. **No hardcoded snowflakes remain in either source file.** Add the new var (placeholder values) to `.env.hat.example`.
- [x] A **hermetic unit-test file in the default backend suite** (`tests/test_discord_hat_helpers.py`, NOT under `tests/live/discord_hat/` and NOT marked `discord_hat`/`live`) imports the pure helpers via the established absolute path `from tests.live.discord_hat.driver import latest_routing_entry, inbound_peer_names, routing_len` (the same `from tests.…` mechanism used by `tests/test_connectors_commands.py:44`; `--import-mode=importlib` + `pythonpath=["tests"]` per `pyproject.toml:65-66` make this work) and exercises them against fixture dicts (no Discord, no creds, no network): `inbound_peer_names` extracts F6 peer_names from an inbound-message fixture; `latest_routing_entry` returns the most-recent routing entry (and `None` on empty); `routing_len` returns the routing-array length (the before/after count `post_and_wait_new_routing` keys on). These pass in the default selection (which already excludes `discord_hat`/`live` via `addopts` — no `-m` flag needed).
- [x] **`routing_len(detail: dict) -> int`** is exported from `driver.py` (extracting the inline `_routing_len` closure at `:500-503`) so the hermetic test covers the real before/after logic rather than a re-inlined copy. No behavior change to the live `post_and_wait_new_routing` (it calls the extracted function).
- [x] Module import of `driver.py` is confirmed side-effect-free w.r.t. creds (verified: top-level imports are `discord`/`httpx`/`HatConfig` only, no `load()`/connection at import) — no refactor of existing helpers needed beyond the `routing_len` extraction.
- [x] The `message_content` doc-lag is scrubbed at the live stale-instruction sites in the F15 L3 leg spec (`legs/03-multi-bot-hat-driver-foundation.md:60`, `:80`, `:95`) → `Intents.default()`. The flight-log correction note (`flight-log.md:63`) is already authoritative and stays; the historical implementation-log line (`:176`) is low-priority history (optionally annotated, not required). `driver.py:68` already uses `Intents.default()` — docs-only, no code change.
- [x] Default backend suite green including the new hermetic tests; the `discord_hat` live tests still SKIP cleanly without creds (no regression to their gating). No production (`the_one/`) source changed by this leg.

## Verification Steps

- README: render-read it; confirm every F15-flagged item is present and that it contains no leaked username/home path (`grep -nE '/home/|/Users/|C:\\\\Users' tests/live/discord_hat/README.md` returns nothing).
- Env-contract move: both `test_multi_user.py` and `test_pairing_peers_decoupling.py` read `cfg.bot_user_ids`; `grep -rnE '\b15111925[0-9]{10}\b' tests/live/discord_hat/*.py` (the real snowflake prefix) returns **nothing** — no hardcoded ids remain in committed source; the config var is documented in the README + `.env.hat.example`.
- Hermetic tests: `docker exec the-one pytest tests/test_discord_hat_helpers.py -x --timeout 30 -q` passes WITHOUT `.env.hat`.
- Live-gate intact: `docker exec the-one pytest tests/live/discord_hat/ -x --timeout 30 -q` still SKIPs cleanly without creds.
- Full default suite once at leg end: `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' --timeout 30 -q` — green, count = L1's 2861 + the new hermetic tests.
- Doc-lag: `grep -rn "message_content" missions/11-discord-connector-depth/flights/15-live-traffic-hat/` shows only historical-narration (if any), not a live "burners need message_content intent" instruction.

## Implementation Guidance

1. **Write the README** from the F15 flight log + debrief (the source of truth for the provisioning procedure). Keep it operator-facing and anonymized (no machine username, no absolute home paths). Include the env-var contract table and the scenario catalogue.
2. **Move `_BOT_IDS`** into `config.py`: add `_read_bot_user_ids()` (mirror `_read_tokens`/`_read_channel_ids`, comma-split `THE_ONE_HAT_BOT_USER_IDS`) + an **optional** `bot_user_ids: list[str]` field on `HatConfig` (default `[]`; do NOT add it to `load()`'s required gate). Update BOTH `test_multi_user.py` and `test_pairing_peers_decoupling.py` to read `cfg.bot_user_ids` and `pytest.skip(...)` locally when empty; remove the hardcoded snowflake tuples from both. Add the var (placeholders) to `.env.hat.example`.
3. **Export `routing_len(detail)`** from `driver.py` (extract the inline `:500-503` closure; have `post_and_wait_new_routing` call it — no behavior change). **Add the hermetic tests** at `tests/test_discord_hat_helpers.py` (default suite, no marker), importing `latest_routing_entry`/`inbound_peer_names`/`routing_len` via `from tests.live.discord_hat.driver import …`. Build fixture dicts shaped like the real session-detail / inbound-message payloads (copy shapes from the F15 scenario assertions). No creds/network.
4. **Scrub the doc-lag**: fix the stale `message_content`-intent instructions in `legs/03-multi-bot-hat-driver-foundation.md:60`/`:80`/`:95` → `Intents.default()` (burners only post). Leave `flight-log.md:63` (already correct); optionally annotate `:176` as history. Do not touch `driver.py` (already correct).
5. Run the hermetic file, the live-gate SKIP check, then the full default suite once at the end.

## Edge Cases

- **Don't un-skip the live tests**: the hermetic tests must live OUTSIDE `tests/live/discord_hat/` and carry no `discord_hat`/`live` marker, or they'd be deselected (defeating the CI-net purpose) or, worse, try to run live.
- **Skip-scope**: `THE_ONE_HAT_BOT_USER_IDS` must NOT join `load()`'s required-fields gate — otherwise the three scenarios that don't use bot ids (`test_smoke`/`test_multi_channel`/`test_multi_agent`) would start skipping when an operator has the other five vars set. Optional field + per-consumer local skip only.
- **Helper importability**: if making a helper importable without creds requires moving it, keep the live tests' import paths working (re-export if needed) so the scenario files don't break.
- **Anonymization**: the README is committed to a public repo — no real Discord ids that deanonymize the operator's server, no machine paths. Use placeholders for ids; describe how to obtain them.
- **`.env.hat` is gitignored** — the README documents its shape but the file itself is never committed (and the hermetic tests must not depend on it).
- **Doc-lag scrub is historical**: the F15 leg spec is a landed-flight artifact; correct the misleading instruction but don't rewrite its history — a light touch (fix the wrong intent claim, note the correction) is enough.

## Files Affected

- `tests/live/discord_hat/README.md` *(new)* — provisioning + run + constraints + timing + scenario catalogue.
- `tests/live/discord_hat/config.py` — add `_read_bot_user_ids()` + optional `bot_user_ids` field (`THE_ONE_HAT_BOT_USER_IDS`).
- `tests/live/discord_hat/test_multi_user.py` — read bot ids from config + local skip; remove hardcoded tuple.
- `tests/live/discord_hat/test_pairing_peers_decoupling.py` — same (the second hardcoded-`_BOT_IDS` site).
- `tests/live/discord_hat/.env.hat.example` — add the new var with placeholders.
- `tests/live/discord_hat/driver.py` — extract `routing_len(detail)` as an exported function (no behavior change).
- `tests/test_discord_hat_helpers.py` *(new)* — hermetic unit tests for the pure helpers in the default suite.
- `missions/11-discord-connector-depth/flights/15-live-traffic-hat/legs/03-multi-bot-hat-driver-foundation.md` (`:60`/`:80`/`:95`) — `message_content`→`Intents.default()` doc scrub.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(commit deferred to flight-end batch per /agentic-workflow)*

- [x] All acceptance criteria verified
- [x] Tests passing (hermetic file + full default suite green; live-gate still SKIPs)
- [x] Update flight-log.md with leg progress entry
- [x] Leg status set to `landed` (→ `completed` at flight-end commit)
- [ ] Check off this leg in flight.md (deferred to flight-end commit)
- [x] If final autonomous leg: hold for flight-end batch review (L3 is interactive, held for operator)
- [x] Commit deferred to flight-end review (per /agentic-workflow batch model)
