# Sortie: Local-command MCP servers: newest protocol and Forget

**Status**: landed

## Charter

### Outcome
A local-command MCP server that is slow to start still connects on the newest protocol it supports, and the operator can make the app forget what it remembers about a local-command server, as they can for an HTTP one.

### Why Now
The operator's `mcp-everything` server (local command, `npx`) shows protocol 2025-11-25 after moving to a release that speaks 2026-07-28, and Test takes more than 10 seconds on it. Squawk 0372 reproduced the cause on a scratch instance: a server that starts 12 s late is connected on the older protocol with no error, and with 16 tools where the same server offers 22. The operator also asked for "Forget tools list" on local-command servers (squawk 0373), which have never had it.

### Success Criteria
- [ ] A local-command server that takes 12 seconds to start connects on 2026-07-28 with its full tool list, from Test and from a chat.
- [ ] An older-protocol server still connects, and a server that starts promptly connects no slower than today.
- [ ] "Forget tools list" is shown on a local-command server that has a stored tools list; pressing it clears the list, the per-agent tool lists and the remembered protocol, and it returns after the next Test that connects.
- [ ] When a local-command connection does fall back to the older protocol because the newer-protocol check got no answer in time, the MCP editor's Server section says so in plain words.

### Constraints
- No use of private SDK modules in `the_one/mcp/` (the existing rule of `_negotiate.py`), and the `mcp==2.3.0` pin stays.
- HTTP servers' negotiation and sign-in behaviour is unchanged.
- A connect stays bounded by today's overall limit (`MCP_DEFAULT_TIMEOUT_SECONDS`, 30 s).
- Out of scope (operator, 2026-11-18): the fact that a bare `npx -y <package>` reuses a cached version.

---

## Pre-Flight

### Objective
On the connect path shared by Test and chats, give a local-command (stdio) server's `server/discover` probe the server's start-up time: when the probe times out with no answer, send it again, inside a window that leaves time for the older handshake, and only then fall back. Record on the client when a connection fell back for that reason; Test stores the fact beside the protocol, and the editor's Server section shows one warning line under the facts. In the editor, show "Forget tools list" on a local-command server that has a stored tools list.

### Open Questions
- [x] Does the editor say when a connection fell back? → Yes (operator, 2026-11-18), see DD4 and the Mockup.
- [x] Where does the note sit? → A line under the facts in the Server section (operator, 2026-11-18), see Mockup.
- [x] "Forget tools list" on local-command servers? → Yes (operator, 2026-11-17), see DD5.
- [x] The npx cache behaviour? → Left out (operator, 2026-11-18).
- [x] A closing HAT? → Yes, a short one (operator, 2026-11-18).
- [x] After a no-answer fallback, is the older revision remembered for the source? → Not the first time; only when it happens twice in a row (Flight Director, on the Architect's finding that remembering it at once pins a one-off slow start to the older protocol for the whole run, and that never remembering it costs a server that ignores the probe the full window on every connect). See DD3.
- [x] Who writes `protocol_version` into a source's stored `_cache`? → Three writers in `api.py` (Architect, 2026-11-18): `_build_and_test_stdio_mcp` (also the agent Test route's shared mode), `_build_and_test_no_auth_mcp` and `_connect_with_tokens` (both HTTP). The pool never writes `_cache`, and the per-agent tool cache holds no protocol. See DD4.
- [x] Is `REQUEST_TIMEOUT` importable from a public SDK name? → Yes: `from mcp.types import REQUEST_TIMEOUT` (-32001), which the public-names guard allows (Architect, checked by import). But the code alone does not identify a timeout: a server may send -32001 itself. See DD1.
- [x] Is a second `server/discover` on one session safe? → Yes (Architect, by reading the SDK): each probe gets a new id, the abandoned waiter is removed, and a late answer is dropped with a debug log. See DD1.

### Design Decisions

**DD1. The probe is patient for local-command servers only**
- Choice: `negotiate` keeps its return type (`-> str`; the tests call it 28 times and compare the result with a string) and gains keywords, all optional: `patient_until` (a loop-clock deadline or `None`), `outcome` (a small mutable object the policy fills in, DD4) and `clock` (default: the running loop's `time`, injectable for the scripted tests). `MCPClient._connect_once` passes a deadline only when `self.source.type == "stdio"`; for every other transport it is `None` and the policy is byte-for-byte today's. That covers the pool's clients (chats) and the agent Test route; the self-configuration loopback is HTTP and is unchanged.
  - **What counts as "no answer".** A probe got no answer when `send_discover` raised `MCPError` with code `REQUEST_TIMEOUT` **and** the probe had been outstanding for at least a floor (a named constant, 1 s), or when the probe was cut off by the deadline (next point). The code alone is not enough: -32001 is a legal code for a server to send (two of this repo's own fixtures send it), and a server that answers the probe at once with it must fall back at once, not be asked hundreds of times.
  - **The re-send.** While a deadline is given and has not passed, a probe that got no answer is sent again at the same version. Each re-sent probe is bounded by the deadline (`asyncio.timeout_at(patient_until)`); that expiry is also "no answer". Cancelling a probe is safe: the SDK sends no cancel notification for discover and removes the waiter.
  - **The re-send is an inner loop.** It does not use up the policy's `attempt` counter. A Python-SDK dual-era server commits to the modern era on the first request it reads and then refuses `initialize` with -32022; today's policy recovers from that by probing once more, but only on attempt 0. So a server that starts after the window is still connected on the modern era by the existing recovery, provided the re-sends left `attempt` alone. With no deadline the loop runs once and the SDK parity test is unchanged.
  - Any other error, and a no-answer after the deadline, takes today's path (the 401 check, the -32022 branches, then `session.initialize()`).
- Rationale: a local-command server is spawned by the connect, so "no answer yet" usually means "still starting": the request sits in the pipe and is answered when the server comes up. An HTTP server is already running; ten seconds of silence there is a real no-answer, and its behaviour is under a constraint. Re-sending is the only way to wait longer on the public API: the probe's timeout is a module constant inside `ClientSession.send_discover`, and the alternatives need the private dispatcher or private session fields (Architect).
- Trade-off: the server receives several probes and answers each when it starts; the late answers are dropped. A local server that never answers an unknown method (it must answer with an error, but one that does not exists as the `--drop-discover` fixture) now takes the whole window before the fallback, where it took 10 s. DD3 bounds how often.

**DD2. The window is the connect limit less a reserve for the handshake**
- Choice: the deadline is the loop time at the entry of `_connect_once`'s existing `asyncio.timeout(self.timeout_seconds)` block, plus `timeout_seconds - HANDSHAKE_RESERVE_SECONDS`. The reserve is a named constant of 10 s in `the_one/mcp/__init__.py`, read at connect time through the same lazy import as `_HANDSHAKE_OFFER_VERSION`, so tests can patch it. The spawn of the server (the sandbox included) is inside that block, so the window counts from before the spawn. With the default 30 s limit the probe is patient until 20 s, and because every re-sent probe is cut at the deadline (DD1) the handshake keeps the full reserve. A `timeout_seconds` at or below the reserve gives no patience (one probe, as today). The whole connect is still under the existing outer timeout; `initialize()` has no timeout of its own.
- Rationale: the operator's case (a start of more than 10 s) and the reproduction (12 s) both sit inside 20 s. The overall limit is a constraint.
- Trade-off: a server that needs more than 20 s to start still falls back unless it is a server that the -32022 recovery of DD1 brings back to the modern era, and one that needs more than 30 s still fails, as today. DD4 tells the operator when a fallback happened.

**DD3. A no-answer fallback is remembered only the second time in a row**
- Choice: `the_one/mcp/_era.py` keeps, beside the revision map, a per-source count of consecutive no-answer fallbacks. When a connect ends on a handshake revision because the probe got no answer (DD4's fact) and `record_era` is true, the count goes up; the revision is remembered (so later connects call `initialize()` directly, as today) only when the count reaches 2. Until then the memory for the source is left empty, so the next connect probes again. Any connect that ends another way resets the count, and `forget_era` clears it (a source edit, a delete, Reset connection, Forget tools list, a failed connect). Every other negotiation result is remembered exactly as today. `record_era=False` and `fresh_negotiation` keep their meaning (a Test always negotiates from scratch).
- Rationale: remembering the first no-answer fallback would pin a one-off slow start (a package runner's first download) to the older protocol for the whole run, silently, on every pooled connect, while the agent's cached tool list may hold the newer protocol's tools. Never remembering it would cost a server that ignores the probe the full 20 s on every connect, and pooled connections are rebuilt after 300 idle seconds. Twice in a row separates the two cases: a slow start gets a second chance, and a server that never answers pays the window twice per run, then connects fast.
- Trade-off: one more piece of in-memory state. A server that never answers the probe costs two patient connects per run (about 20 s each) where it cost one 10 s wait. A server that is slow on every start and is not rescued by the -32022 recovery ends on the older protocol either way.

**DD4. The fallback is a recorded fact, stored by Test and shown under the facts**
- Choice:
  - **On the client.** The policy fills the `outcome` object of DD1; `MCPClient` exposes it as a read-only property `negotiation_fallback`, reset at the start of every connect: `"no_answer"` only when the last probe got no answer **and** the connection's final revision is a handshake revision (a recovery that ends on the modern era leaves it `None`), else `None`.
  - **In the stored cache.** `api.py::_build_and_test_stdio_mcp` writes `protocol_fallback: "no_answer"` in the same `merge_cache` as `protocol_version`, or deletes the key when there was no such fallback. It reads the property through one small helper that defaults to `None` for an object without it, because the unit tests patch about a dozen fake clients into that route and they define no such property; the real client's property is pinned by the integration test. The two HTTP writers (`_build_and_test_no_auth_mcp`, `_connect_with_tokens`) delete the key unconditionally, with no client read. `update_mcp_source`'s server-changed rule, which already drops `last_check` and `auth_posture`, drops `protocol_fallback` too, so a type change cannot leave a local-command note on an HTTP server.
  - **In the editor.** `mcp-server-info.js` shows one warning line under the facts when `cache.protocol_fallback === 'no_answer'` and the Protocol row is shown: "This server did not answer the newer-protocol check in time, so this connection uses an older protocol and may offer fewer tools. Press Test again once the server has started." It is an `App.ui.banner` (tone `warning`, role `note`, testid `mcp-server-protocol-fallback`), built once with the section and toggled with `hidden` on every `update`, as the section's other optional parts are. No new control and no owned class outside `js/ui/`.
- Rationale: the operator chose a visible note. One stored key keeps the Version, the Protocol and the note painted from the same cache object in one call, which is how the section already works. The banner is the catalogue's in-section warning with a `note` role (precedents: the Date and time page, the self-configuration revisions); `App.ui.notice` has no warning tone.
- Trade-off: one more key in `_cache`. A connection that fell back in a chat shows no note until the next Test (nothing but Test writes `_cache`). The agent Test route with per-agent credentials can store a fallback's shorter tool list for that agent with no note anywhere (it writes no shared cache). Both accepted and written into `the_one/agents.md`.

**DD5. "Forget tools list" on a local-command server**
- Choice: the rule in `mcp-connection-status.js::updateButtons` becomes: an HTTP server as today (`type === 'streamable-http' && oauth_active !== true && cache && (cache.auth_posture || cache.tools)`), or a local-command server whose cache holds a tools list (`type === 'stdio' && cache && Array.isArray(cache.tools)`, the test `App.usage.mcpState` already uses; the one writer for a local-command server stores the tools and the protocol together, and a failed Test stores only `last_check`, which leaves nothing to forget). Same button, same place beside the status line, same armed label and same "Tools list forgotten" message. The route `DELETE /api/mcp-sources/{id}/connection` is unchanged: it already accepts a stdio source, drops `_cache`, the per-agent tool cache and the remembered revision, and closes pooled connections. Reset connection stays HTTP-only (it is the sign-in's button).
- Rationale: the operator asked for it; it is also the way to clear a remembered older revision (DD3) without restarting. Nothing else on the page assumes a local-command server has no such button, and `runDelete`'s success path is correct for one (Architect).
- Trade-off: this reverses Mission 31 Flight 5's DD6 ("stdio gets neither"). That artifact is not rewritten; this decision supersedes it and the leg updates the live documents. A local-command server with a remembered revision but no stored tools list (it fell back twice in chats and was never tested) has no button; a Test gives it one. Accepted.

**DD6. Verification apparatus**
- Choice: no behavior test.
  - **The policy** is pinned in `tests/test_mcp_negotiate.py` with scripted sessions and the injected clock: no answer then an answer inside the window; no answers until the deadline, then the handshake; an instant -32001 with a deadline falls back with one probe; a no-answer window followed by `initialize` refused with -32022 recovers to the modern era and reports no fallback; no deadline sends one probe. The SDK parity test keeps running with no deadline, the -32001 scenario included.
  - **The client and the route** are pinned with the real stdio fixture (`tests/fixtures/mcp/hello_server.py` gains a start-delay option). Two things make these tests fast and true (Architect): the window is `timeout_seconds` less the reserve, so a test passes a small `timeout_seconds` (or patches `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS` and the reserve) as well as patching `mcp.client.session.DISCOVER_TIMEOUT_SECONDS`; and the fixture is a Python dual-era server, which the -32022 recovery brings back to the modern era, so a **real** fallback needs the delay together with `--legacy-only`. The cases: a delayed dual-era server ends modern with the full tool list; a delayed `--legacy-only` server ends on the handshake with `negotiation_fallback == "no_answer"`, and the Test route stores the key; a prompt server stores no key and deletes a stale one; two no-answer fallbacks in a row are needed before a connect skips the probe.
  - **A test that changes meaning** is rewritten in the leg, not deleted: `tests/test_mcp_negotiation_fallback.py::test_stdio_silent_drop_falls_back_and_second_connect_skips_discover` (`--legacy-only --drop-discover`, one probe expected, the second connect skipping it). Under DD1 and DD3 it would run about 20 s, send about 40 probes and fail both assertions.
  - **The editor** is pinned in the `mcp-connection` lane with seeded caches: `test_flow_studio_mcp_editor_status.py` for the button (the predicate test is rewritten in place and gains a cached local-command case and a local-command case holding only `last_check`), `test_flow_studio_mcp_editor_server_info.py` for the note. The browser tests never need a slow real server.
  - **The HAT** walks one real slow server on a scratch instance.
- Rationale: every criterion is a deterministic fact about a stored record or the DOM; the one thing only a real run shows (a real 12 s start) is the HAT's first step and was already reproduced by hand.
- Trade-off: the browser tier proves the note from a seeded key, not from a real fallback; the unit tier proves the key from a real fallback. The join is the route's cache write, which the route test covers.

### Mockup (operator-approved, 2026-11-18)

The operator chose "Line under Protocol" over "Beside the status line" and "On the Protocol row itself".

```
CONNECTION ---------------------------------
 ...
 [ Test ]  * Connected - checked 3:42 PM
           [ Forget tools list ]

SERVER -------------------------------------
 Everything Reference Server
 Version    2.3.0
 Protocol   2025-11-25
 Offers     Tools, Resources, Prompts

 ! This server did not answer the newer-protocol
   check in time, so this connection uses an
   older protocol and may offer fewer tools.
   Press Test again once the server has started.

 > Tools (16)
```

"Forget tools list" on a local-command server sits beside the status line, where it is for an HTTP server. The mockup is a reference for placement and wording, not a pixel contract.

### Citation Audit

Verified against the working tree at `c317c878`.

| Citation | Status |
|---|---|
| `the_one/mcp/_negotiate.py::_full_policy` — any `MCPError` from `session.send_discover(version)` that is not a recorded 401 and not an actionable -32022 falls through to `await session.initialize()` and returns | verified |
| `the_one/mcp/_negotiate.py::negotiate` — signature `(session, *, remembered)`; a remembered handshake revision calls `initialize()` directly with no probe | verified |
| `mcp/client/session.py` (mcp 2.3.0) — `DISCOVER_TIMEOUT_SECONDS = 10.0`; `send_discover` builds `opts = {"timeout": DISCOVER_TIMEOUT_SECONDS, "cancel_on_abandon": False, ...}` and takes no timeout argument | verified |
| `mcp/shared/jsonrpc_dispatcher.py::send_raw_request` — raises `MCPError` with `REQUEST_TIMEOUT` when `opts["timeout"]` elapsed (imported there from `mcp_types`) | verified (the public import path is an open question) |
| `the_one/mcp/client.py::_connect_once` — the transport enter and `negotiate(session, remembered=…)` run inside `async with asyncio.timeout(self.timeout_seconds)`; `remembered` is `None` when `fresh_negotiation`; `_era.remember_era(self.source.id, negotiated)` runs when `record_era` | verified |
| `the_one/mcp/__init__.py` — `MCP_DEFAULT_TIMEOUT_SECONDS = 30` | verified |
| `the_one/mcp/_era.py` — a process-wide in-memory `source_id -> revision` map; `forget_era` | verified |
| `the_one/interfaces/web/api.py::_build_and_test_stdio_mcp` — `MCPClient(source=…, auth_provider=None, fresh_negotiation=True, record_era=record_era)`; one `repo.merge_cache` writes `tools`, `capabilities`, `server_info`, `instructions`, `meta`, `protocol_version`, `last_updated` | verified |
| `api.py::reset_mcp_connection` — no type check; pops `_cache`, strips sign-in keys, `_evict_all_for_source`, `_drop_source_agent_tool_cache`, `forget_era`; docstring: "calling on a stdio source is harmless … but UI hides the affordance" | verified |
| `the_one/interfaces/web/static/js/areas/studio/mcp-connection-status.js::updateButtons` — Forget requires `source.type === 'streamable-http'` | verified |
| `mcp-connection-status.js::runDelete` — on success sets `oauth_active` and `has_access_token` false, deletes `config._cache`, repaints; no type-specific step | verified |
| `the_one/interfaces/web/static/js/areas/studio/mcp-server-info.js::update` — builds the Version, Protocol, Offers and Website rows from one cache object and calls `facts.set(rows)` | verified |
| `tests/browser/test_flow_studio_mcp_editor_status.py::test_reset_and_forget_predicates` — docstring "neither for stdio"; pins the current rule | verified |
| `tests/test_mcp_negotiate.py::test_parity_with_sdk_negotiate_auto` — runs the-one's policy and the SDK's private `negotiate_auto` against the same scripted sessions | verified |
| `tests/fixtures/mcp/hello_server.py` — `--stdio`, `--legacy-only[=<revision>]`, `--drop-discover` ("never answers `server/discover`"); no start-delay option | verified |
| Reproduction (squawk 0372, Evidence): the published 2.3.0 server as a local command gives `2026-07-28` and 22 tools at once or 4 s late, `2025-11-25` and 16 tools 12 s late | verified (run on 2026-11-17, scratch instance on Linux; its log names the sandbox backend, bubblewrap. The operator's app runs unsandboxed on Windows; the spawn is inside the window either way) |
| `mcp/shared/jsonrpc_dispatcher.py` — each request takes a new id (`_allocate_id`); the waiter is removed in `finally`; a late answer is dropped ("dropping response for unknown/late request id"); `mcp.types.REQUEST_TIMEOUT == -32001` | verified by the Architect (reading, and an import check) |
| `mcp/server/runner.py::serve_dual_era_loop` — "The client's first request decides the connection's protocol era, once"; a modern connection refuses `initialize` with -32022; `_negotiate.py::_full_policy` re-probes after that only when `attempt == 0` | verified by the Architect |
| `tests/fixtures/mcp/asgi_401.py`, `tests/fixtures/oauth/__init__.py` — fixtures that answer with code -32001 themselves | verified by the Architect |
| `the_one/interfaces/web/api.py` — the three writers of `_cache.protocol_version`: `_build_and_test_stdio_mcp` (gated by `cache_write != "none"`), `_build_and_test_no_auth_mcp`, `_connect_with_tokens`; `the_one/mcp/_pool.py` writes no `_cache`; `agent_mcp_tool_cache` rows hold `(agent_name, source_id, tools, fetched_at)` | verified by the Architect |
| `tests/test_mcp_negotiation_fallback.py::test_stdio_silent_drop_falls_back_and_second_connect_skips_discover` — the only user of `--drop-discover`; `DISCOVER_TIMEOUT_SECONDS` is patched only in that file | verified by the Architect |
| `docs/ui-control-inventory.md` — `App.ui.banner` takes tone `warning`, role `note`, `testid`, `hidden`; `App.ui.notice` has tones `muted` and `danger` only | verified by the Architect |

### Prerequisites
- [x] No active mission, and the one open sortie (12, claimed actions) does not touch `the_one/mcp/` or the MCP editor.
- [x] PR #378 (the sortie 18 debrief, with squawks 0372 and 0373's evidence) is merged (`032f27cc`, 2026-11-18), and the sortie branch is cut from that `main`. The merge was made before the last commit on that branch was pushed (`c317c878`, the operator's answers in squawk 0373), so that commit rides on this sortie's branch.
- [x] Sortie 18's changes to the MCP editor are on `main` (v0.16.5); this flight's editor files (`mcp-connection-status.js`, `mcp-server-info.js`) were not touched by it apart from squawk 0371's one line.
- [x] Consumer search for the Forget rule, run by the Architect on 2026-11-18 (`grep -rn -F` over `tests/` (with `tests/behavior/`), `scripts/`, `docs/`, `evals/`, `the_one/`). The editor leg runs it again before it starts. Hits, by pattern:
  - `forget-mcp-connection-btn`: `tests/browser/test_flow_studio_mcp_editor_server_info.py`, `test_flow_studio_mcp_editor_status.py` (three sites), `docs/ui-testid-registry.md`, `mcp-connection-status.js`.
  - `Forget tools list`: `scripts/ui_capture.py` (two sites; the `mcp-edit-stdio` capture will now show the button), `docs/releases/v0.16.5.md` (history, left as is), `test_flow_studio_mcp_editor_status.py` (three sites), `the_one/agents.md` (two sites), `mcp-connection-status.js` (two sites), `css/studio.css`.
  - `neither for stdio`: the docstring of `test_flow_studio_mcp_editor_status.py::test_reset_and_forget_predicates`. Its local-command case seeds no cache, so it would still pass unchanged; the rewrite adds the cached cases (DD6).
  - `stdio gets neither`: none outside `missions/`. `Tools list forgotten`: `mcp-connection-status.js`.
  - `reset_mcp_connection` and callers of `DELETE …/connection`: `api.py`, `the_one/agents.md`, `mcp-connection-status.js`, `tests/test_store_static.py` (pins the fetch literal), `tests/test_mcp_test_connection_negotiation.py`, `tests/test_mcp_last_check.py`, `tests/test_agent_mcp_tool_cache.py`, `tests/test_mcp_connection_reset.py` (HTTP sources only).
- [x] Consumer search for the probe's timing, run by the Architect on 2026-11-18: `negotiate(` is called from `client.py` and 28 times in `tests/test_mcp_negotiate.py` (no test patches it); `DISCOVER_TIMEOUT_SECONDS` is patched only in `tests/test_mcp_negotiation_fallback.py` (three tests); `--drop-discover` has one user, the test DD6 rewrites; `--close-on-discover` and the HTTP fallback tests are unaffected (a closed pipe is not a timeout, and HTTP gets no deadline).
- [x] The HAT's real server comes from the npm registry: reachability is checked again on the day, before the HAT starts. (Checked on 2026-11-18; the published version was 2.3.1.)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (the registry check is the HAT's, on the day)
- [x] Validation approach defined
- [x] Legs defined
- [x] Operator-approved mockup recorded

---

## In-Flight

### Technical Approach
1. **The connect path first.** `_negotiate.py`: the `patient_until`, `outcome` and `clock` keywords, the inner re-send loop and its "no answer" rule (DD1); the module's branch map gains one row for the re-send and one for the attempt-0 recovery after a no-answer window. `the_one/mcp/__init__.py`: the reserve and the floor as named constants. `client.py`: the deadline for stdio sources, the `negotiation_fallback` property, reset on every connect. `_era.py`: the consecutive no-answer count (DD3). `api.py`: the fallback key written or deleted by the local-command writer, deleted by the two HTTP writers and by `update_mcp_source`'s server-changed rule (DD4). The stdio fixture gains a start-delay option and its docstring says so. Tests per DD6, the rewritten silent-drop test included. Docs: `the_one/agents.md` "MCP F2 Client Foundation" (its sentence on the cost of a server that ignores the probe changes), `the_one/mcp/README.md`'s negotiation section, and the "Automatic protocol negotiation" paragraph of `CLAUDE.md`.
2. **Then the editor.** `mcp-connection-status.js`: the rule of DD5. `mcp-server-info.js`: the banner of DD4, its visibility set on every `update`. The pinned predicate test is rewritten in place (renamed, not deleted and re-added), and new tests cover Forget on a local-command server (shown, armed, pressed, hidden, back after a Test) and the note (shown with the key, hidden without, gone after a Forget). `scripts/ui_capture.py`'s `mcp-edit-stdio` surface is re-captured as a visual check (it now shows the button). Docs: `docs/ui-testid-registry.md` (the Forget row's wording and a new row for `mcp-server-protocol-fallback`), `the_one/agents.md`'s MCP editor notes (the Forget rule and the two accepted gaps of DD4), the route's docstring.
3. **Both legs** run `ruff check` and `ruff format --check` on the files they touch before landing (sortie 18 debrief, recommendation 2).
4. **HAT** on a scratch instance (never port 8484 or the default data directory), started only after the closing gate has finished: a real slow-starting local server, the Forget button on it, the note on a server that starts later than the window, and one HTTP server unchanged.

### Checkpoints
- [x] Unit tier green with the negotiation and client tests (`THE_ONE_TEST_NETNS=1 make test-unit`), the SDK parity test included
- [x] `mcp-connection` lane green with the button and note tests; `mcp`, `library`, `agents` and `agent-tabs` lanes green (other readers of the MCP source cache: `test_mcp_test_connection_button.py` runs a real local-command Test, `test_studio_mcps_tab.py` reads the cache)
- [x] Full local gate on the final tree, on a host with no other test run, finished before the HAT instance starts; a HAT fix re-runs the lanes above and the unit tier, and a fix wider than the editor re-runs the full gate (sortie 18 debrief, recommendation 4)
- [x] HAT walked with the operator

### Adaptation Criteria

**Divert if**:
- The patient probe cannot be built on the public `ClientSession` API (for example, a second `send_discover` on the same session is refused or corrupts the session).
- Re-sending the probe to a real dual-era server changes what it negotiates (for example, the late answers to the abandoned probes confuse the session).
- Keeping HTTP behaviour unchanged turns out to need a change to the shared policy's structure.

**Acceptable variations**:
- A different reserve than 10 s, if the integration tests show the handshake needs more or less.
- The wording of the note, within the meaning the operator approved.
- Never remembering a no-answer fallback (dropping DD3's count), if the count proves awkward to keep correct; the cost is the full window on every connect to a server that ignores the probe.

### HAT list
- A real local-command server that starts 12 s late: Protocol 2026-07-28, the full tool list, no note.
- The same server started later than the window (a total start of about 22 to 24 s; the package runner adds 3 to 5 s to the delay, and 30 s is the limit): connects, older protocol, the note is shown; a Test after a normal start removes it.
- "Forget tools list" on a local-command server: shown after a Test, arms, clears the Server section and the tools, comes back after the next Test.
- An HTTP server: Test, Forget and Test behave as before.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `patient-discover` - the patient probe for local-command servers, the fallback fact on the client and in the stored cache, fixture option, unit and integration tests, docs
- [x] `editor-forget-and-note` - "Forget tools list" on local-command servers, the fallback note in the Server section, flow tests, docs
- [x] `hat-and-alignment` *(optional)* - Guided HAT session with iterative fixes

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- `THE_ONE_TEST_NETNS=1 make test-unit` green, with `tests/test_mcp_negotiate.py` and the new client and route tests.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp-connection` green, plus the lanes of the checkpoints.
- The lint pair clean on every file touched (`ruff check`, `ruff format --check`).
- On a scratch instance: the published "everything" server as a local command started 12 s late shows Protocol 2026-07-28 and 22 tools after a Test.
