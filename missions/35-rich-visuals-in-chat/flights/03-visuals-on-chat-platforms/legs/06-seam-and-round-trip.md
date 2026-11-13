# Leg: seam-and-round-trip

**Status**: completed
**Flight**: [Visuals on Chat Platforms](../flight.md)

## Objective
A dev instance started with `THE_ONE_FAKE_PLATFORMS_URL` points its Discord and Telegram connectors at the local fake platforms, and only at a loopback IP. The seam is gated and documented, and the `charts-reach-platforms` behavior test is finalized and passes against the fakes for both platforms.

## Context
- **Flight design decisions:**
  - DD2: the app-side seam. It sits in the lifespan beside the stub gate, reads the process environment only, needs `dev_mode`, takes a loopback IP literal only, and passes keyword URLs to both `register()` functions with an explicit `gateway_url`. The residual goes into SECURITY-MODEL.md and the connectors README.
  - DD3: what converts. The behavior test covers the automatic reply, the tool send and the step-limit line.
  - DD7: the 413 fallback, with one warning.
- **What earlier legs give:**
  - Leg 3: conversion through `send_reply`.
  - Leg 4: `send_visual` and `send_visual_fallback` on both clients.
  - Leg 5: `scripts/fake_platforms.py`, with its control routes, which this leg's behavior test uses: `/_control/health`, `discord/inject`, `telegram/inject`, `received`, `fail-next`, `reset`, and `--save-dir`.
- **The registration today** (`the_one/interfaces/web/app.py` lifespan):
  - The stub's dual gate (`if settings.dev_mode and os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") == "1":`).
  - Then unconditional `register()` blocks, each in its own `try/except`, for Discord (`from the_one.connectors.discord import register as _register_discord`) and Telegram, with symmetric `unregister` at shutdown (`:751`, `:755`).
  - `discord.register()` and `telegram.register()` take no arguments and build `DiscordPlugin()` and `TelegramPlugin()`.
  - The constructors already accept `gateway_url=` and `rest_base_url=` (Discord) and `base_url=` (Telegram).
- **The seam's security posture:**
  - A bot token typed into a dev instance must never leave the machine through this seam. So the URL's host must be a loopback **IP literal** (`127.0.0.1`, or `::1` in brackets), with no host names (no `localhost`; DNS is not trusted). The scheme must be `http`, and a port must be given.
  - Anything else is refused with one logged error, and the real URLs are used.
  - Production (`dev_mode` off) never reads the variable.
  - The gateway URL is built from the checked base (`ws://<host>:<port>/discord/gateway`) and passed explicitly, so the client never follows a gateway URL the fake returns. The fake's READY has no `resume_gateway_url` (Leg 5), so a reconnect also stays on the checked URL.
- **The start-of-leg check (from flight planning) was answered at design review: there is no cache, and step 9 needs no restart.**
  - `dispatch_inbound` calls `factory.create(agent_name)` per inbound message (`inbound.py:418`).
  - `AgentFactory.create` (`factory.py:365-`) loads the config through `_load_config` and `store.load` (`:741-747`, the DB-backed `SQLiteAgentStore`, `db/repositories.py:159`) on every call.
  - It reads the provider row from the DB (`:386-400`) and passes `provider_config.config` (`:407-412`) to `get_provider` (`:437`). `llm/registry.py:41-48` builds a **new provider instance per call**.
  - `max_iterations` comes from the freshly loaded config (`:716`).
- **Behaviour at `max_iterations: 1`** (design review):
  - The single iteration runs the scripted tool call, then the loop ends at its limit (`core.py:298-299`, `:412`).
  - `deliver_final_reply` sees the `[platform-send-ok]` tool result and sends no automatic reply (`delivery.py` skip rule).
  - After the persist, the step-limit line is sent (`inbound.py:454`, `:469-470`).
  - A tool call that fails (for example an allowlist miss) lacks the prefix, so an extra automatic reply goes out. That makes a wrong script a visible failure, not a silent one.
- **High risk:** a security-sensitive surface (where bot tokens are sent). It gets a leg design review, and the Reviewer at flight end runs as Sonnet.
- **Running the behavior test is the Flight Director's step,** through `/mission-control:behavior-test charts-reach-platforms`, after the Developer lands the code and the finalized spec. A failing run means the leg does not land (the agentic-workflow rule).

## Inputs
- Legs 3-5 landed (uncommitted) in the working tree; Leg 1 committed.
- `tests/behavior/charts-reach-platforms.md`, the draft from flight planning: 10 steps, `Status: draft`.
- CLAUDE.md "Behavior-test credential convention" and "SAFETY RULE": scratch cwd, scratch data dir, a port that is neither 8484 nor 8485, a shell-only credential.

## Outputs
- **`the_one/connectors/discord/__init__.py`:** `register(*, rest_base_url: str = DEFAULT_BASE_URL, gateway_url: str | None = None)` passes only those two to `DiscordPlugin`; its other constructor keywords are left at their defaults.
- **`the_one/connectors/telegram/__init__.py`:** `register(*, base_url: str = DEFAULT_BASE_URL)`. Neither package reads the environment.
- **`the_one/connectors/fake_platforms_seam.py`** (new, pure). `fake_platform_urls(raw: str | None, *, dev_mode: bool) -> FakeUrls | None | Refused`, where `FakeUrls(discord_rest, discord_gateway, telegram_base)`. It parses with `urllib.parse.urlsplit` and checks with `ipaddress.ip_address(host).is_loopback`, and needs scheme `http`, an explicit port, and no userinfo, query or fragment. The path must be empty or `/`.
- **`the_one/interfaces/web/app.py`:** the lifespan reads `os.environ.get("THE_ONE_FAKE_PLATFORMS_URL")` (never `settings` or `.env`) when `settings.dev_mode`, calls the pure function, and then:
  - with URLs: passes them to the two `register()` calls and logs one warning, "connectors use the fake platforms at http://127.0.0.1:P";
  - when refused: logs one error with the reason and registers with the real defaults. The log line carries only the reason plus `urlsplit(…).scheme` and `.hostname`, and never the raw value, its userinfo, its path or its query;
  - when the variable is unset, or `dev_mode` is off: registers exactly as today.
- **Tests:**
  - `tests/test_fake_platforms_seam.py` (new): a table test of the pure function.
  - A lifespan test, with an app built through the project's existing lifespan-test pattern, asserting the registered plugins' URLs for set, refused and unset (with `dev_mode` on and off).
- **Docs:**
  - CLAUDE.md: a row in the "Test seams at a glance" table (an environment seam, not an `/api/_test` route: `THE_ONE_FAKE_PLATFORMS_URL` with `THE_ONE_DEV_MODE=true`, pointing Discord and Telegram at `scripts/fake_platforms.py`), plus a sentence on the stub route's `images` key. Leg 3 documented that key in the connectors README only, and CLAUDE.md does not mention it yet.
  - SECURITY-MODEL.md: the seam's gate and loopback rule, and the residual that the fakes prove what the app sends, not what the platforms show.
  - `the_one/connectors/README.md`: the seam in "Test seams", beside Leg 5's paragraph.
- **`tests/behavior/charts-reach-platforms.md`:** finalized, with real control-route names, exact commands, the seeding requests and `Status: active`. It is then run by the Flight Director.

## Acceptance Criteria
- [ ] **AC1, start check (answered at design: no cache).** The flight log records the citations in Context. Step 9 of the spec has no restart. The Developer re-checks that `factory.py` and `llm/registry.py` have not changed since then.
- [ ] **AC2.** `fake_platform_urls`:
  - **Accepts** `http://127.0.0.1:8490`, `http://127.0.0.1:8490/` and `http://[::1]:8490`, giving `http://127.0.0.1:8490/discord/api/v10`, `ws://127.0.0.1:8490/discord/gateway` and `http://127.0.0.1:8490/telegram`, with brackets kept for IPv6.
  - **Refuses** each of these, each with a reason:
    - `http://localhost:8490`;
    - `http://10.0.0.1:8490`;
    - `http://example.com:8490`;
    - `https://127.0.0.1:8490`;
    - `http://127.0.0.1` (no port);
    - `http://user@127.0.0.1:8490`;
    - `http://127.0.0.1:8490/x`;
    - `http://127.0.0.1:8490?q=1`;
    - `ftp://…`;
    - `http://[::1` (`urlsplit` raises `ValueError`);
    - `http://[::ffff:127.0.0.1]:8490` (IPv4-mapped, so `is_loopback` is False on this Python);
    - a 10 000-character garbage string;
    - non-string input.
  - **Never raises:** every refusal is a `Refused(reason)` value.
  - **Returns `None`** when the value is unset, empty or only whitespace, or when `dev_mode` is false, whatever the value. An empty variable (`THE_ONE_FAKE_PLATFORMS_URL= cmd`) is treated as unset, silently.
- [ ] **AC3, lifespan.** The registered plugins are read back through `the_one.connectors.registry.get_plugin("discord" | "telegram")` and their attributes: Discord's `_rest_base_url` and `_gateway_url_override`, Telegram's `_base_url`.
  - With `dev_mode` on and a valid value, the `discord` plugin has the fake REST base and the explicit gateway URL, and `telegram` has the fake base, with one warning logged.
  - With a refused value, both plugins have the real defaults and one error is logged. A test with `http://user:secret@127.0.0.1:8490` asserts that `user`, `secret` and the raw value appear in no log record.
  - With `dev_mode` off and the value set, both have the defaults and nothing about the seam is logged.
  - Unset: the defaults.
  - **No `.env`:** the variable is not a `Settings` field. A test asserts `"fake_platforms_url"` is not in `Settings.model_fields`, and that the lifespan source reads it through `os.environ.get("THE_ONE_FAKE_PLATFORMS_URL")`. pydantic-settings never exports `.env` values into `os.environ`, so a `.env` entry cannot reach the seam.
  - The lifespan tests reuse the skeleton in `tests/_routine_app.py:114-150`:
    - `monkeypatch.setattr(settings, "data_dir", tmp_path)` and `monkeypatch.setattr(settings, "dev_mode", …)`;
    - `copy_template(settings.db_path)`;
    - the DB connection singleton reset, `plugin_registry.clear_for_test()` and `_write_lock.reset_for_test()`;
    - `async with lifespan(app)` in one task.
- [ ] **AC4.** Neither connector package reads `os.environ`, guarded by a grep-style test over `the_one/connectors/discord/` and `the_one/connectors/telegram/`. `register()` with no arguments behaves exactly as today, and the existing registration tests pass.
- [ ] **AC5.** The docs are updated as listed in Outputs: CLAUDE.md seam row and stub `images` sentence, SECURITY-MODEL.md, and the connectors README.
- [ ] **AC6.** `tests/behavior/charts-reach-platforms.md` is finalized against the real fake and app:
  - the fake's start command (port ≥ 8490, `--save-dir` under the scratch dir);
  - the dev instance with `THE_ONE_FAKE_PLATFORMS_URL`;
  - the credential creation;
  - the seeding requests, as exact `curl` commands with the bearer credential and JSON bodies. Every nested JSON body (the chart inside `config.response.content`, and step 9's tool-call arguments) is built with `.venv/bin/python -c 'import json; …'`, never hand-escaped. The requests create:
    - the mock provider, with a `name` and `config.response.content` holding text, a chart titled "Revenue by region", a widget and closing text;
    - the agent;
    - the Discord connector, with the fixed `"id": "disc1"`, `secrets.token` set to a fake token, and `config` `{"default_agent": <agent>, "allowlist": {"peers": [<the Discord inject author id>]}}`;
    - the Telegram connector, with the fixed `"id": "tg1"` and the same shape, its allowlist holding the Telegram inject `from_id`, which is also the DM chat id.
    
    The sender ids are exactly the values the steps' inject calls use.
  - **A start-up check in the Preconditions:** after seeding, `serve.log` holds one "connectors use the fake platforms at http://127.0.0.1:P" warning, and `POST /api/connectors/disc1/test` and `…/tg1/test` succeed against the fake. A seam failure is then caught before step 1.
  - each step's real control call. Step 7 uses `fail-next {count: 1, status: 413, kind: "upload"}`, so the later JSON fallback is not failed.
  - step 9's tool-call scripting through `config.response.tool_calls`:
    - the call is `{"id": "tc1", "name": "send_to_platform_channel", "arguments": {"content": <reply with a chart>, "target": {"connector_id": "tg1", "peer_id": <chat id>}}}`;
    - `config.response.content` is short plain text;
    - the agent's `max_iterations` is 1.
  
  `Status: active`. A dry check by the Developer confirms each `curl` in the Preconditions works on a scratch instance (port ≥ 8490, scratch data dir and cwd under `$HOME`), and the instance and the fake are stopped by their recorded PIDs afterwards.
- [ ] **AC7.** `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected skip count, and `ruff check` and `ruff format --check` are clean.
- [ ] **AC8 (Flight Director, after landing).** `/mission-control:behavior-test charts-reach-platforms` passes, and its run log is committed under the configured run-log location. A failure blocks landing; fix it in a new pass and re-run.

## Verification Steps
- AC1: read `the_one/agent/factory.py` (`create`) and the provider construction it calls.
- AC2-AC4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_fake_platforms_seam.py <lifespan test> -x --timeout 60`.
- AC6: the Developer's dry check of the Preconditions on a scratch instance, recorded in the flight log. Run log paths go to scratch, outside the repo.
- AC7: `THE_ONE_TEST_NETNS=1 make test-unit` (in the background).
- AC8: the Flight Director runs the behavior test.

## Implementation Guidance
1. **Start check (AC1) first.** Re-check the Context citations against `factory.py` and `llm/registry.py`, and record the result in the flight log.
2. **The pure function and its table test (AC2).** Keep the result types small, for example a `Refused(reason)` dataclass.
3. **`register()` keywords (AC4).** Change only the signatures and the constructor calls. Grep for `register()` callers in tests (`tests/test_discord_plugin.py`, `tests/test_telegram_plugin.py`, any lifespan test) and leave them passing.
4. **The lifespan (AC3).**
   - Compute the seam result once, before the Discord block, beside the stub gate.
   - Pass keywords only when the result is `FakeUrls`.
   - Keep each `try/except` and the shutdown `unregister` unchanged.
   - For the lifespan test, find the existing lifespan-test pattern (`grep -rn "lifespan" tests/ | head`; `asgi-lifespan` is a dev dependency) and use a scratch data dir.
5. **Docs (AC5).**
6. **The behavior spec (AC6).**
   - Keep the draft's 10 steps and observables, and fill in the real names.
   - The Validator opens the saved PNG by path (step 3).
   - Fallback warnings appear in `serve.log` (step 8).
   - Do the dry check of the Preconditions only, not the steps; the steps are the Flight Director's run.
7. **Gates (AC7).**

## Edge Cases
- **`THE_ONE_FAKE_PLATFORMS_URL` set on a prod-like instance with `dev_mode` off:** ignored silently. That is the intent, so that a stray variable cannot redirect tokens.
- **IPv4-mapped IPv6** (`http://[::ffff:127.0.0.1]:8490`): `is_loopback` is False on this Python (verified at design review), so it is refused (AC2).
- **Connector creation never calls the platform** (`api.py:4936-4971` writes the row and calls `manager.start`). Connect, the doctor (`POST /connectors/{id}/test`, `api.py:5142`) and the gateway fetch all go through the registered plugin's URL attributes (`discord/plugin.py:340`, `:360`; `telegram/plugin.py:335`). The only hard-coded URLs are the two defaults, so the seam covers every path.
- **A refused value is visible only in the log.** That is enough for a dev-only seam: the spec's start-up check catches it. Nothing is exposed in `/api/info`.
- **A fake that is not running when the instance starts:** the connectors' connect fails and the manager backs off as for any unreachable platform. No special handling is needed. The spec starts the fake first.
- **The Telegram token in fake URLs:** the fake redacts it in `received` (Leg 5). The app's own logs follow existing behaviour; the transport mapping raises `from None` (Leg 4).

## Files Affected
- `the_one/connectors/discord/__init__.py`, `the_one/connectors/telegram/__init__.py`, `the_one/connectors/fake_platforms_seam.py` (new), `the_one/interfaces/web/app.py`
- `tests/test_fake_platforms_seam.py` (new), a lifespan test (new or extended)
- `CLAUDE.md`, `SECURITY-MODEL.md`, `the_one/connectors/README.md`
- `tests/behavior/charts-reach-platforms.md`

## Citation Audit
Checked 2026-11-12 (Leg 1 committed; Legs 3-4 uncommitted, which leave these lines alone).
- `the_one/interfaces/web/app.py:450-456` — the stub dual gate `if settings.dev_mode and os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") == "1":` then `register_for_test("stub", …)`; `:458-483` — the Discord and Telegram `register()` blocks, each in its own `try/except`; `:751`, `:755` — shutdown `unregister` — verified
- `the_one/connectors/discord/__init__.py` `register()` → `registry.register("discord", DiscordPlugin())`; `telegram/__init__.py` `register()` → `registry.register("telegram", TelegramPlugin())` — verified
- `DiscordPlugin(…, gateway_url=None, rest_base_url=DEFAULT_BASE_URL, …)`; `TelegramPlugin(*, base_url=DEFAULT_BASE_URL, api_transport=None)` — verified
- `the_one/connectors/inbound.py:418` — `agent = await factory.create(agent_name)` per inbound message — verified (caching behind it is AC1's check)
- `the_one/agent/config.py:142` — `max_iterations: int = 20` — verified
- `tests/behavior/charts-reach-platforms.md` — draft, 10 steps — verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
