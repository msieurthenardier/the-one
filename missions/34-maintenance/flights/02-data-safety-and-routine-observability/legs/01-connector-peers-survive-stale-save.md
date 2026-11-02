# Leg: connector-peers-survive-stale-save

**Status**: completed
**Flight**: [Data safety and routine observability](../flight.md)

## Objective
A peer paired while a connector editor is open is still stored after that editor's Save, and a peer the operator deliberately removes in the editor is still removed.

## Context
- Flight Technical Approach step 1; mission criterion "A stale connector save keeps a paired peer" (#4, squawk 0288, escalated into this leg).
- **The defect.** `the_one/connectors/inbound.py::_pair_peer` appends a peer to `config.allowlist.peers` server-side when a DM carries a valid pairing code (`dispatch_inbound`: `if envelope.is_dm and manager.consume_pairing_code(...)`: `await _pair_peer(connector, envelope.peer_id, conn_repo)`). `the_one/interfaces/web/api.py::update_connector` does `merged = existing.model_dump(); merged.update(data)`, a shallow merge, so an incoming `config` replaces the stored one whole. The editor (`static/js/areas/studio/connector-editor.js::buildPayload`) sends `allowlist.peers` from its textarea as it was when the editor loaded (or after its last Save). A Save from an editor opened before the pairing therefore drops the paired peer.
- **Mechanism chosen by the Flight Director (design decision, recorded in the flight log):** a **three-way merge of `allowlist.peers` using a base the editor sends**, not a server-side union and not a stale-save 409.
  - A plain union (stored ∪ incoming) cannot express "remove a peer" — rejected.
  - A 409 needs a conflict UI in the editor (reload or "save anyway"), which is new operator-visible behaviour the mission constraint forbids — rejected.
  - Three-way merge: the editor adds one top-level payload key, `allowlist_peers_base`, the `allowlist.peers` list of the record it last loaded or saved (`stored`). The server computes `added_since_base = [p for p in stored_peers if p not in base]` and the result `incoming_peers + [p for p in added_since_base if p not in incoming_peers]` (order: the operator's list first, then the preserved peers in stored order). A peer in the base that the operator removed stays removed. A peer someone else removed meanwhile (in base, gone from stored, absent from incoming) is not re-added.
  - The only visible effect is the one the mission allows: after Save the editor shows the preserved peer (the edit-mode Save already re-applies the server's response through `applyRecord(stored)`).
- **Backward compatibility.** `Connector` is a plain `BaseModel` (no `extra="forbid"`), so an unknown key is ignored today. The server must `pop` `allowlist_peers_base` from `data` before the merge in every case. A PUT without the key (API callers, tests) keeps today's replace semantics exactly. A PUT with the key but with no `config` in the body leaves `config` untouched (nothing to merge).
- **Validation of the base.** `allowlist_peers_base` must be a list of strings; anything else is a 422 with `loc` naming the key (match the existing `secrets must be a dict.` style: `HTTPException(422, detail=...)`). `null` is treated as absent.
- **Only peers.** Pairing writes nothing else; channels, always-listen and the channel map keep replace semantics.
- **Sortie 07 constraint:** this leg edits `update_connector` only in `api.py` (not `create_agent`/`update_agent`/`_agent_response`), and does not touch `inbound.py:480-483`. Prerequisite re-check: sortie 07 (`ae2296f1`) did not change `update_connector` (verified at leg design, body read at HEAD `b497312f`).
- **Not in scope:** `_pair_peer`'s own read-modify-write (it re-reads the row per inbound in `dispatch_inbound`, so two pairings in sequence do not lose each other); optimistic concurrency for other editors (waits for the agent write-safety block).

## Inputs
- HEAD `b497312f` on branch `flight/02-data-safety-and-routine-observability`.
- Squawk 0288 (`escalated`).

## Outputs
- `the_one/interfaces/web/api.py::update_connector`: pops and validates `allowlist_peers_base`; merges peers as above.
- `static/js/areas/studio/connector-editor.js::buildPayload`: sends `allowlist_peers_base` from `stored` in edit mode only (create mode omits it).
- Unit tests (in `tests/test_connector_routes.py`, or a new `tests/test_connector_stale_save.py` if that file's fixtures fit poorly), a browser test in the `library` lane's `test_studio_connector_editor.py`.
- `the_one/agents.md` Connectors section: one short paragraph on the merge rule. Flight log entry; squawk 0288 Disposition gains a link to the outcome.

## Acceptance Criteria
- [ ] **AC1 — red first.** A unit test performs: create a connector with peers `["a"]`; GET it (the editor's view); pair peer `"b"` through the real `_pair_peer` (with the real `ConnectorRepository`); PUT the GET's `config` back with an unrelated change (e.g. `default_agent`) **and** `allowlist_peers_base: ["a"]`; assert stored peers are `["a", "b"]`. Run it before the fix and record in the flight log that it fails at HEAD (0288 proven), then make it pass.
- [ ] **AC2 — deliberate removal.** Base `["a", "b"]`, stored `["a", "b", "c"]` (c paired after load), incoming `["a"]` → stored `["a", "c"]`. And base `["a", "b"]`, stored `["a"]` (b removed elsewhere), incoming `["a", "b"]` → `["a", "b"]` (the operator's explicit list wins for a peer it names).
- [ ] **AC3 — compatibility.** A PUT without `allowlist_peers_base` replaces `config` exactly as before (an existing route test keeps passing unmodified, plus one new assertion that a no-base PUT dropping a peer drops it). The key is never stored: after any PUT, `config` and the response contain no `allowlist_peers_base`. A base that is not a list of strings is a 422 and nothing is written.
- [ ] **AC3b — malformed shapes keep today's errors.** With a valid base present, an incoming `config.allowlist` that is not a dict (e.g. `"x"`), or `peers` that is not a list of strings, still gives the same 422 the validator gives today (not a 500), and the stored row is unchanged after the 422 (re-read and compare). A base that fails validation is refused before `repo.update`, with the stored row unchanged.
- [ ] **AC4 — empty incoming allowlist.** Incoming `config` with no `allowlist` key (the editor's sparse config when both textareas are empty), base `[]`, stored `["p"]` (paired after load) → stored `config.allowlist.peers == ["p"]`, other stored allowlist keys follow the incoming config (channels absent → absent).
- [ ] **AC5 — secrets unchanged.** The `__MASKED__` per-key handling still keeps the stored token on a PUT that carries a base (one assertion in the AC1 test or its own).
- [ ] **AC6 — editor sends the base.** A browser test in `tests/browser/test_studio_connector_editor.py` opens an existing connector with peers, edits an unrelated field, saves, and asserts the captured PUT body's `allowlist_peers_base` equals the peers the editor loaded; and that a create (POST) body has no such key. After the editor is open, add a peer server-side through the test file's `_api(base)` client (a PUT with the new peer, standing in for a pairing), then edit an unrelated field and Save: the peers textarea shows the extra peer afterwards. Then edit another field and Save again: the second PUT's `allowlist_peers_base` equals the first response's peers (pins the `stored = updated` reassignment). Capture bodies with `page.expect_request(lambda r: r.method == "PUT" and ...)` and `request.post_data_json`. If `seeders.seed_connector` cannot seed peers, seed with `_api(base).post` and `config.allowlist.peers`.
- [ ] **AC7 — suites green.** `make test-unit` passes; `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane library` passes; the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`) pass; ruff clean.
- [ ] **AC8 — records.** agents.md Connectors section states the merge rule; flight log records the red result and the outcome; squawk 0288's Disposition links the leg.

## Verification Steps
- AC1: run the new test with the merge code removed (by editing) and paste the failure into the flight log; restore by editing; run again.
- AC2–AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/<file> -x --timeout 30`.
- AC6: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_studio_connector_editor.py -x`, then the `library` lane.
- AC7/AC8: commands above; read agents.md, the flight log and squawk 0288.

## Implementation Guidance
1. Write the AC1 test first against HEAD (it fails), then implement in `update_connector`, right after the secrets block and before `merged = existing.model_dump()`: pop the base, validate, and if both the base and `data.get("config")` (a dict) are present compute the merged peer list against `existing.config` and write it into `data["config"]["allowlist"]["peers"]` (creating `allowlist` when the result is non-empty; never write an empty `peers` key where the editor's sparse config would have omitted it). Keep it a small helper (e.g. `_merge_paired_peers(stored_config, incoming_config, base)`) beside the route, pure, with its own unit tests for AC2/AC3b/AC4. **Return contract:** it returns a copy of the incoming config with `allowlist.peers` merged, or the incoming config unchanged (the same object) when the incoming `config` is not a dict, its `allowlist` is present but not a dict, or its `peers` is present but not a list of strings, so the model validator still raises the 422 it raises today. It reads `existing.config` read-only and never mutates the request's dicts or `existing.model_dump()` in place (copy `config` and `allowlist` before writing). Deduplicate first-occurrence across the incoming list and the preserved peers. Pop and validate the base before anything can reach `repo.update`.
2. In `buildPayload`, add `allowlist_peers_base` in edit mode from `(stored.config && stored.config.allowlist && stored.config.allowlist.peers) || []`. `buildPayload` is a closure over `stored`; `stored` is reassigned on a successful Save, so the next Save's base is the saved row. Keep the comment style of the surrounding code (one short comment saying why).
3. Browser test per AC6; use the file's existing seeding and request-capture patterns (read the file first).
4. agents.md: extend "Connector subsystem contract" (around L964) with the rule in two or three sentences, and add one clause to the connector editor paragraph (around L2309) that Save sends `allowlist_peers_base`.

## Design Review
2026-11-02, Developer (Sonnet), cycle 1: **approve with changes**. Merge rule verified for every interleaving (pairing after load, operator removal, removal elsewhere, re-add of a peer removed elsewhere, duplicates, no allowlist key; residual ambiguity accepted: a peer removed elsewhere and re-paired after load is kept). `stored` changes only at mount and edit Save; the editor is the only web PUT client. Applied: AC3b (malformed shapes keep the 422, row unchanged), the helper's return contract and no-mutation rule, base validated before `repo.update`, the second-Save assertion and seeding approach in AC6, the agents.md section names. No second cycle: the changes tighten the spec without changing the design.

## Edge Cases
- Duplicate ids in incoming or base: the result has each peer once, first occurrence wins.
- `existing.config` has no `allowlist` or no `peers`: nothing added since base.
- A non-dict `config` in the body: leave it to the existing model validation (422 as today); do not crash in the helper.
- The base is sent but the operator renamed the connector or changed type: the merge still applies; only peers are touched.

## Files Affected
- `the_one/interfaces/web/api.py` (`update_connector` and a helper beside it)
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (`buildPayload`)
- `tests/test_connector_routes.py` or a new `tests/test_connector_stale_save.py`; `tests/browser/test_studio_connector_editor.py`
- `the_one/agents.md`; the flight log; `squawks/0288-*.md`

## Citation Audit
Checked at `b497312f` (Flight Director, 2026-11-02): `api.py::update_connector` at :4519, secrets block :4531-4544, `merged = existing.model_dump(); merged.update(data)` at :4551-4552 — verified (flight citation said L4366/L4398; drifted). `inbound.py::_pair_peer` at :129 and its call `await _pair_peer(connector, envelope.peer_id, conn_repo)` inside `dispatch_inbound` after `conn_repo.get(connector_id)` — verified. `connector-editor.js`: `var stored = cfg;` :163, `buildPayload` :356, edit Save `cfg = config = stored = updated; applyRecord(stored);` :693-694 — verified. `db/models.py::Connector` has no `model_config` (extra keys ignored) — verified.
