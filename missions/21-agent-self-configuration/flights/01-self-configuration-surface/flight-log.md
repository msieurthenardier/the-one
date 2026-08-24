# Flight Log: Self-Configuration Surface

**Flight**: [Self-Configuration Surface](flight.md)

## Summary

Planning complete; execution not started.

---

## Reconnaissance Report

Mission 21 pre-enumerated findings with specific code citations, so each was
walked against current code before the leg breakdown was set. No commits landed
between the mission's authoring and this survey, so drift was expected to be
nil — the value here is in the **counts**, which the Mission 20 debrief named as
the recurring reconnaissance weakness ("strong at finding categories and weak at
counting within them").

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `MCPSource.type` is a closed two-value literal guarded by a CHECK constraint | `confirmed-live` | `db/models.py:106`; `db/schema.py:400` | Avoided entirely by DD1 |
| "~14 production call sites switch on source type" | `confirmed-live` — count exact | `mcp/client.py:110,118,130`; `mcp/_tool_provider.py:88,90,93,157,168,181`; `api.py:985,1052,1081,1238,1730,1764,1766,1769` | 14 confirmed; untouched under DD1 |
| Transport rename precedent for a table-rebuild migration | `confirmed-live` | `db/schema.py:377-418` | Not needed under DD1 |
| Agent override columns are unencrypted JSON | `confirmed-live` | `db/schema.py:347-348,437-438` (plain `TEXT` via `ALTER`) | Leg 1 |
| Agent read endpoints return overrides unmasked | `confirmed-live` | `api.py:439-447,450-457` — both return bare `cfg.model_dump()` | Leg 1 |
| Substitutable override keys carry credentials | `confirmed-live` | `mcp/_overrides.py:60,89,90` — `env`, `headers`, `bearer_token` | Leg 1 |
| Per-agent tool provision runs in-process for every transport | `confirmed-live` | `mcp/_tool_provider.py:219-390` | Informs DD1 |
| System prompt baked once at construction; step loop never re-reads | `confirmed-live` — **but understated** | `agent/core.py:176-178`; loop re-binds `self.messages` per iteration at `:276-289` | See A1 below |
| Rejoin already rebuilds from the current agent row | `confirmed-live` | `app.py:1103-1111`, `:975` | `next_session` is free |
| Mission 20's three unspent seams | `confirmed-live` | Gate resolves identity; credential id distinct from secret; second-source registration | DD2 spends the first |
| M20 debrief action items (4 open) | `confirmed-live`, **out of scope** | Squawks 0001 and 0002 both still `open` | Flight 3 / squawk queue; none touch this surface |

### Items the mission did not enumerate, found during this survey

| Finding | Evidence | Disposition |
|---|---|---|
| **A1 — the propagation risk runs opposite to the mission's framing.** `_run_iterations` re-binds `request_messages = self.messages` *inside* its while loop, and tool dispatch happens in that same loop. A naive in-place mutation lands **mid-turn**, not next-turn. | `agent/core.py:276-289`, `:588` | DD7 — deferral required, not coordination |
| **A2 — no read path exposes a running agent's system prompt.** `session_joined` carries history, title, agent name, routing metadata; not the prompt. Propagation cannot be asserted by state inspection. | `app.py:1199-1220` | DD8 — behavioral assertion |
| **A3 — the type fall-throughs are silent.** `filter_mcp_tools_by_override` and `_apply_override` return input *unchanged* for an unrecognized type rather than raising. An unrecognized source type would have silently disabled the operator's per-tool control — mission criterion 8 failing with no error anywhere. | `mcp/_tool_provider.py:92-93`, `:181-185` | DD1's strongest argument |
| **A4 — ~26 further type-conditional sites in JavaScript**, uncounted by the mission. 22 in `mcp-server-editor.js`, plus `mcps-tab.js:148`, `studio.js:567-587`, `mcp-servers-grid.js:31`. | as cited | Untouched under DD1 |
| **A5 — `mcp/_pool.py` has zero `source.type` dispatch.** It delegates to `mcp/client.py`. | `mcp/_pool.py` (no matches) | Pre-declared split point does not fire |
| **A6 — agent credential overrides are already silently wiped by Studio.** `collectFormData` rebuilds `mcp_overrides` from the DOM while the MCPs tab renders no credential fields, so an API-set override does not survive the next save. | `studio.js:2064-2132`; `mcps-tab.js:21-26` | DD5 — preserve must be server-side |
| **A7 — `SQLiteAgentStore` carries no encryptor** and is constructed at 7 production + 30 test sites. | `db/repositories.py:74`; construction sites in `retention.py:58`, `connectors/_inbound.py:328`, `connectors/_pool.py:578`, `interfaces/cli.py:31`, `app.py:140,1283`, `api.py:68` | DD5 — defaulted parameter avoids the ripple |
| **A8 — `Encryptor.rotate_key` has no production caller.** Adding an encrypted column does not break an existing rotation path. | `encryption.py:53` | Recorded so the absence is not mistaken for a coupling |
| **A9 — the plaintext fallback removes the need for a data migration.** `_decrypt_secrets_blob` treats undecryptable input as plaintext. | `db/repositories.py:40-59` | DD5 — lazy re-encrypt on write |

**Retirements**: none. Every mission-cited item is live.

---

## Leg Progress

*(none yet)*

---

## Decisions

*(runtime decisions not in the original plan)*

---

## Deviations

*(departures from the planned approach)*

---

## Anomalies

*(unexpected issues encountered)*

---

## Session Notes

**Flight design** — Design decisions DD1–DD9 recorded in the flight spec. The
mission's pre-declared split point was evaluated against a counted survey and
**does not fire**: it required the transport enum to widen *and* the widening to
ripple into transport dispatch, the pool and the sandbox. DD1 avoids the widening
altogether, and A5 shows the pool carries no type dispatch regardless.

One scope shift from the mission's plan: DD1 makes a credential unavoidable on
the agent's own path, so credential minting moves from Flight 3 into Flight 1
(self-only, no operator UI). Flight 3 is correspondingly smaller but remains a
genuine boundary — it introduces the credential store as a secrets-bearing table
and settles the rotation semantics Mission 20 deferred.
