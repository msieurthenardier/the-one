# Behavior Test: Audit Log Inspector Renders Routing Entries (F13 L5)

**Slug**: `audit-log-inspector-renders-routing-entries`
**Status**: active
**Created**: 2026-05-31
**Last Run**: 2026-05-31-23-56-31 (PASS 7/7)

## Intent

Verify that the Chat UI per-session "Routing audit" panel renders entries from `session_metadata["routing"]` — exercising the L5 backend exposure (detail-endpoint composition + WS join-payload extension), the new `App.chat.routingAuditPanel` module (`create` / `render` / `wireRefresh`), and the CSS disposition badges as a single end-to-end flow. The unit browser tests in `tests/browser/test_flow_chat_routing_audit_panel.py` hit the surfaces in isolation (one fixture, one assertion per test); this behavior test hits them as a real operator does — open the Chat UI, navigate to a session seeded with multi-disposition routing entries, expand the panel, expand a row, expand the policy-silent row's nested policy dict, click Refresh, and confirm rendered state at each checkpoint. The Witnessed pattern (Validator independent of Executor) catches false-positive scenarios where DOM internals report success but no human can see the panel (broken CSS, off-screen overflow, hidden ancestor).

## Preconditions

- The-one is running host-native on `http://localhost:8484` and the Chat UI loads at that URL (verified by an active probe: the operator opens the URL in a browser and sees Chat render OR the welcome screen).
- The operator has the chrome-devtools MCP browser session attached to that URL.
- The build under test includes F13 L1+L2+L3+L4+L5 commits (verified by running `git grep -nE 'routing-audit|routingAudit' the_one/interfaces/web/static/js/areas/` directly in the repo — returns at least 6 hits AND `git grep -n 'session_metadata' the_one/interfaces/web/api.py` returns the detail-endpoint composition site).
- A test chat session exists with **multi-disposition routing entries** seeded in `session_metadata["routing"]`. The seed should include at least 4 entries — one each for the four canonical dispositions:
  - `stepped` — the engaged path (`{"ts": "...", "agent": "<name>", "rule_index": 0, "scope": "channel", "match": null, "reason": "matched", "disposition": "stepped"}`)
  - `command-intercepted` — built-in command short-circuit (add `"intercept_source": "builtin"`)
  - `no-eligible` — no agent could handle the inbound (`"agent": null`, `"disposition": "no-eligible"`)
  - `policy-silent` — gate decided silent with `policy` dict (`"policy": {"outcome": "inference-no", "account_always_listen": true, "agent_always_listen": true, "inference_provider_id": "<prov-id>", "inference_model": "<model-name>"}`)
  - **Operator seeds via the dev-mode test-seam endpoint** (M11 F15 L2): POST the routing entries to `POST /api/_test/chat/sessions/<sid>/routing-audit`, which sets `session_metadata["routing"]` via the repository's `set_session_metadata_key` (overwrite semantic). Example:
    ```
    curl -X POST http://localhost:8484/api/_test/chat/sessions/<sid>/routing-audit \
      -H 'Content-Type: application/json' \
      -d '{"routing": [ {...stepped entry...}, {...command-intercepted entry...}, {...no-eligible entry...}, {...policy-silent entry...} ]}'
    ```
    (The endpoint returns `{"count": N}` and 403s unless the container runs with `THE_ONE_DEV_MODE=true` — the dev container does. Note: the old `PUT /api/chat/sessions/<sid>` seed does NOT work — `update` drops `session_metadata` by design.) **Fallback**: direct SQLite `UPDATE chat_sessions SET session_metadata = '{...}' WHERE id = ...` against the data-dir `the-one.db`. The seed is operator-checkable via `curl -s http://localhost:8484/api/chat/sessions/<sid> | jq '.session_metadata.routing | length'` returning `>= 4`.
- The operator knows the target session's id (passed in as a parameter or recorded during the precondition seed).
- The session belongs to a configured agent (any agent — the panel test does not assert on agent topology, only on the routing entries rendered).
- **Decay-prone preconditions probed actively**: the seed data is recent (just-written before the test); the container is fresh enough that the agent name in the seed still resolves (the panel renders whatever string is in the entry, so even a deleted agent renders as a string — but the join handler requires the agent to exist to broadcast `session_joined`).

## Observables Required

- browser (rendered state of the Chat UI panel, measured via chrome-devtools MCP — screenshot + a11y snapshot are the primary evidence; structured DOM evals are supplementary, used only to confirm collapsed/expanded state or class membership where the visual evidence is ambiguous)
- http (the `GET /api/chat/sessions/{id}` response read out-of-band by the operator after the Refresh click in step 6, used to confirm the panel's contents reflect the substrate state — `[mixed-frame]` justification given at that step)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open Chat at `http://localhost:8484/#chat/sessions/<target_session_id>` (substitute the seeded session id from preconditions). Wait briefly for the chat area to load (the agent name renders in the header). | The Chat area is visible — the message list renders (possibly empty) and the input area is at the bottom of the chrome. Above the input area and below the message list, a "Routing audit" disclosure / summary element is visible. The disclosure is **collapsed by default** (no inner content visible yet — only the toggle label). |
| 2 | Click the "Routing audit" summary to expand the panel. | The disclosure expands. Inside, a "Refresh" button is visible and enabled. Below the Refresh button, a list of routing-entry rows is visible — four rows, one per seeded disposition. Each row's summary line shows: a timestamp (ISO 8601 form is acceptable), an agent identifier or `—` (for the no-eligible row), a scope label, a reason (truncated if long), and a disposition badge with visible text matching one of `stepped`, `command-intercepted`, `no-eligible`, `policy-silent`. **Rendered state**: the four badges have visually distinct colors (screenshot evidence — for example, the `stepped` badge appears green-ish, `no-eligible` orange/yellow-ish, `policy-silent` muted/grey, `command-intercepted` violet/accent-ish — exact hex values vary by light/dark theme; the test asserts visual distinction, not specific hex values). |
| 3 | Click the row whose disposition badge reads `stepped` to expand its summary disclosure. | The row expands. Inside the expansion, a key-value list is visible. Visible keys include `disposition` (value `stepped`), `ts` (the entry's timestamp), `agent` (the entry's agent name), `scope` (the entry's scope value), and `rule_index` (the entry's rule index integer — e.g., `0`). The `match` and `reason` keys are also visible with their respective values. |
| 4 | Collapse the `stepped` row (click its summary again). Click the row whose disposition badge reads `command-intercepted` to expand it. | The `stepped` row collapses; the `command-intercepted` row expands. Inside its expansion, the same base key-value list is visible PLUS an `intercept_source` key whose value is `builtin` (or `plugin` if the seed used that variant). |
| 5 | Collapse the `command-intercepted` row. Click the row whose disposition badge reads `policy-silent` to expand it. | The `policy-silent` row expands. Inside the expansion, the base key-value list is visible PLUS a `policy` key whose value is rendered as a **nested key-value list** (visually distinct — indented, bordered, or otherwise set off from the parent list). Inside that nested list, the following keys + values are visible: `outcome` (value `inference-no`), `account_always_listen` (value `true`), `agent_always_listen` (value `true`), `inference_provider_id` (the seeded provider id string), `inference_model` (the seeded model name string). |
| 6 | Open a terminal (the operator runs this out-of-band, not the Executor inside the browser) and run `curl -s http://localhost:8484/api/chat/sessions/<target_session_id> \| jq '.session_metadata.routing \| length'`. Note the value (should be `4` after the precondition seed). Then re-seed the routing list with a 5th entry by re-POSTing the **full 5-entry array** (the original 4 plus 1 new) to the dev-mode test-seam endpoint — `set_session_metadata_key` has overwrite semantic, so you post the whole list, not a delta: `curl -X POST http://localhost:8484/api/_test/chat/sessions/<target_session_id>/routing-audit -H 'Content-Type: application/json' -d '{"routing": [<the original 4 entries plus 1 new>]}'` (fallback: direct SQLite `UPDATE`). Verify the count is now `5` via the same `jq` curl probe. Then return to the browser and click the "Refresh" button inside the routing-audit panel. | **(setup-then-observe row.)** Before the Refresh click: the panel still shows 4 rows (the just-appended 5th entry is not yet reflected — the panel hadn't re-fetched). After the Refresh click: within 3 seconds the panel re-renders and shows **5 rows** (the 4 originals plus the new one). The Refresh button briefly disables during the in-flight fetch (visible at the moment of click) then re-enables. `[mixed-frame]` HTTP probe: `curl -s http://localhost:8484/api/chat/sessions/<target_session_id> \| jq '.session_metadata.routing \| length'` returns `5`, confirming the substrate state matches what the panel renders. Justification: cross-frame here because the panel's correctness is a function of "did it re-fetch and re-render" AND "is the substrate the source of truth" — confirming the substrate count directly distinguishes "panel re-rendered against a phantom cache" from "panel re-rendered against the real data". The substrate observable is the only one that distinguishes those cases. |
| 7 | Cache-defeat: hard-reload the browser page (Ctrl+Shift+R or equivalent). Wait for Chat to re-load. Verify the URL is still `#chat/sessions/<target_session_id>`. Observe the routing-audit panel WITHOUT clicking Refresh. | The Chat UI loads. The routing-audit panel is visible, collapsed by default. Click its summary to expand. **Rendered state**: **5 rows** are visible (matching the post-step-6 count). This confirms the WebSocket `session_joined` payload includes `session_metadata` — the panel was populated at join time, not via a separate REST round-trip. If only 4 rows are visible (the pre-step-6 count), the L5 server-side `session_joined` payload extension (AC-14) regressed and the test fails here. |

## Out of Scope

- The dispatcher actually WRITING routing entries during a live inbound (covered by the existing `discord-engagement.md` behavior test and by `tests/test_connectors_inbound.py` unit tests; this test consumes pre-seeded entries).
- The connector-editor inference Provider + Model UI (covered by `connector-inference-provider-config-roundtrip.md` from L4).
- Rendering `session_metadata["audit"]` (F6 ACL deny/permit decisions) — explicitly out of F13 scope per Phase 5b DD "Audit-Log Inspector Renders Only `routing`".
- Pagination / time-range filtering on the routing entries (deferred per flight Adaptation Criteria; future flight).
- WebSocket-pushed real-time updates (deferred per architect cycle-1; future flight).
- Slash-command verification against the real Discord bot (covered by L6 HAT).
- Performance / accessibility audits — separate concerns. (The panel uses native `<details>`/`<summary>` for keyboard support, but no formal a11y audit runs in this spec.)
- Visual snapshot baselines — per the user-global "Test snapshots are not committed" rule, this spec does not capture or assert on snapshot baselines; rendered-state assertions describe what the operator and Validator see, not pixel diffs.

## Variants (optional)

None for this initial round. Future variants could:

- Parametrize the connector type (Discord vs Stub) for the seeded session — confirm the panel renders uniformly regardless of connector source.
- Test the panel against a session with `session_metadata = {"audit": [...]}` only (no `routing`) — confirm the empty-state renders ("No routing decisions yet") even though `session_metadata` is non-null.
- Test the panel against a session with a forward-compat `disposition="pool-failure"` entry — confirm the row renders without crashing even though no CSS class matches the badge.
- Test the Refresh button under network failure (e.g., kill the container between fetch initiation and response) — confirm the button re-enables and the prior render stays in place.
