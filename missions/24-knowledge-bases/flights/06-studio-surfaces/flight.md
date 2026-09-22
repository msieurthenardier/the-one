# Flight: Studio Surfaces

**Status**: completed
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [ ] Operator can register a folder on disk as a knowledge base source, and see each discovered item's index status including failures
- [ ] Operator can inspect a knowledge base's contents and metadata, and retrieve the source material behind any indexed item
- [ ] A knowledge base can be attached to and detached from any agent in Studio *(behavior-test-backed)*
- [ ] Files in a registered folder index automatically, and additions, modifications, and deletions are reflected without operator action or an app restart *(behavior-test-backed — this flight observes it through a screen for the first time)*

---

## Pre-Flight

### Objective

Replace both knowledge-base stubs with the real operator surfaces: a global
Knowledge inventory in Studio where a knowledge base is created, renamed,
deleted, pointed at a folder, and inspected down to individual chunks and
source text; a per-agent Knowledge tab where a knowledge base is attached and
detached; and one Administration panel for the app-wide chunking and monitoring
settings whose API shipped in Flights 2 and 4 with no screen. Every backend
route these surfaces consume already exists and is tested, with one exception:
retrieval has no HTTP entry point, so this flight adds the operator-facing
search route that makes the inventory a proving surface for Flight 5's hybrid
fusion. The flight closes with a broad guided HAT that carries Flight 3's seven
waived steps and walks the whole mission's operator story end to end.

### Open Questions

- [x] Does Flight 6 carry the non-UI carry-forward cluster? → **DD-1** (no; a
      closing flight does)
- [x] How does the inventory reach `retrieval.search`, which no route exposes? →
      **DD-6**
- [x] Does this flight add a rename affordance, given rename dangles name-keyed
      `disabled_tools` entries? → **DD-5** (yes, and it owns the consequence)
- [x] Chip area or row toggles for the attach control? → **DD-3**
- [x] Client-side or server-side fix for squawk 0050? → **DD-4** (both)
- [x] What happens to a `kb__` entry in `disabled_tools` when the operator
      saves the agent for an unrelated reason? → **DD-13**: today it is erased.
      Surfaced by Architect cycle 1; it is the defect DD-5 was resting on.
- [x] What happens to an agent's stored state when a knowledge base is deleted?
      → **DD-14**: `kb_ids` dangles and is dropped at the next save; the
      `disabled_tools` entry is left because **DD-17** makes it inert. Delete
      writes nothing to any agent.
- [x] A knowledge base's derived tool name changes with the agent's whole
      attached set, so rename, delete, attach and detach each dangle a
      name-keyed `disabled_tools` entry → **DD-17** (operator decision at
      Architect cycle 3: fix the naming, not the four call sites)
- [x] Is the attach tab's knowledge-base list fresh enough to attach something
      just created? → **DD-15** (no, today; it is currently dead state)
- [x] How does an operator *un*-disable a knowledge-base tool they disabled? →
      **DD-13**: `PUT /api/agents/{name}` with an explicit list stays
      authoritative. This is why DD-13 is client-side; a server-side preserve
      would have removed the capability silently.
- [x] Does the name-length hint refuse an over-length name? → **DD-16** (no —
      it is advisory; over-length names are truncated, never refused)
- [x] Is the embedding model operator-changeable, and if so how is the
      whole-corpus re-index surfaced? *(mission open question)* → **DD-7**: it is
      not changeable at all; the mission's own description of the guard was
      wrong. Answered, not carried.
- [ ] **Walk skip counters on `/status`** (F3 debrief action item, recon R8) —
      deferred with reason, see Deferred Scope below. Rolled to the closing
      flight's planning as an open question, not silently dropped.

### Design Decisions

**DD-1 — Flight 6 is Studio surfaces only; a closing Flight 7 carries the
non-UI cluster**: Flight 6 = the two stub replacements, the settings panel, the
search route, squawk 0050, the rename-integrity fix, and the mission-closing
HAT. Flight 7 = the Windows 1M `usearch` re-measure (recon R12), the
"Large-folder settle" behavior-test variant (R13), `get_vector_store()`'s
missing shutdown hook (R14), the shared `the_one/tools/naming.py` (R15), and the
recall/precision benchmark that evaluates `RRF_K`, `candidate_k` and DD-12
together (R20).
- Rationale: the two clusters share a vehicle question, not a surface. The UI
  cluster is additive work over shipped, tested routes; the other is a
  performance measurement, a process-lifecycle hook, and a shared-interface
  refactor — three risk domains that each want their own planning conversation
  and review gate. Folding them together would put one review gate over four
  domains in the mission's last flight, which is the worst place to do it.
- Trade-off: the mission takes one more flight than its plan listed. R14 in
  particular has now been deferred three times and the mission's Known Issues
  says "not deferred again" — this decision honours that by naming a flight that
  exists to carry it, rather than by cramming it behind a UI review.

**DD-2 — Two surfaces, one inventory model**: Studio's **Knowledge section** is
the global inventory — create, rename, delete a knowledge base; register and
inspect folders; read items, chunks and source. The agent editor's **Knowledge
tab** is attach-only: it lists existing knowledge bases with a toggle each and
creates nothing.
- Rationale: exactly the split the MCP surfaces already use (the MCP Servers
  section owns the source; the MCPs tab attaches it), so the operator meets one
  mental model twice rather than two. It also keeps creation out of a surface
  whose save is an agent PUT.
- Trade-off: attaching a not-yet-created knowledge base is a two-stop journey.

**DD-3 — The attach control is a per-knowledge-base row toggle, not a chip
area**: the tab renders one row per knowledge base carrying
`data-kb-toggle` + `data-kb-id`, and `collectFormData` collects
`[data-kb-toggle][data-kb-id]:checked`.
- Rationale: mirrors what the MCPs tab already does
  (`mcps-tab.js:142` sets `data-mcp-source-toggle`; `studio.js` collects
  `[data-mcp-source-toggle][data-mcp-source-id]`), which itself replaced the
  chip-area pattern. The dead `.chip-area[data-type="kb"] .chip` selector is
  removed in the same change — it is the mechanism of squawk 0050.
- **Each row also renders that knowledge base's derived tool name**
  (`kb__…__search`), **served by the backend — never recomputed in JavaScript**.
  Verified at Architect cycle 2 that nothing exposes it today (`GET /tools` is
  built-ins, there is no `/agents/{name}/tools`, and the self-configuration
  projection returns knowledge-base *names*), so this flight adds the read path:
  `_compute_tool_names` is promoted to a public `compute_tool_names` and the
  agent response carries `{kb_id: tool_name}` for the agent's stored `kb_ids`.
  A JavaScript reimplementation was the implied alternative and is rejected —
  it would mean reproducing the sha256 discriminator, the 8→12→16 widening and
  the budget-before-truncation rule in the browser, which is exactly the logic
  DD-5 and DD-17 argue is subtle enough to get wrong.
- Under **DD-17** a name depends only on `(kb.name, kb.id)`, so the value is
  stable per knowledge base and does **not** need recomputing as the operator
  toggles rows — which is what makes serving it from the stored set correct
  rather than merely convenient. An unattached knowledge base's row therefore
  shows its name normally; there is no "depends what it joins" case left.
- This is also the only way a rename's effect (DD-5) is visible to the operator
  at all, and it is the behavior test's read path for steps 12 and 14.
- Trade-off: a long knowledge-base list is a long list of rows; the MCPs tab has
  the same property and has not needed paging.

**DD-4 — `kb_ids` is preserved on omit server-side *and* omitted client-side
unless the knowledge-base list is known to have loaded**: both sides change.
- Server: `update_agent` gains `if "kb_ids" not in data: data["kb_ids"] =
  existing.kb_ids`, exactly mirroring the `self_revision_requires_approval`
  preserve already in that function.
- Client: the attach surface's container carries `data-kb-list-loaded="true"`
  **set on the success branch only — the `catch` branch must leave the marker
  unset and render the load-failure state**, and `collectFormData` sets
  `data.kb_ids` only when that marker is present. The wording matters: the
  pattern this mirrors (`refreshMcpSourcesCache`) *always resolves*, because its
  `.catch` swallows and returns, so "set it when the promise resolves" would set
  the marker on the failure path and reproduce the very defect this closes
  (Architect cycle 2). The failure path carries its own assertion. A loaded surface with zero toggles checked still
  sends `[]` — a legitimate "detach everything".
- **The discriminator is an explicit load-success marker, not container
  presence** (Architect cycle 1, high). Container presence cannot distinguish
  "no knowledge bases exist" from "the fetch failed", and the natural
  implementation makes the failure reachable: `refreshMcpSourcesCache`
  (`studio.js`) swallows a fetch error in `.catch` and keeps an empty cache. A
  Knowledge tab mirroring it would render with zero rows, container present, and
  PUT `kb_ids: []` — squawk 0050 reproduced through the fix meant to close it.
  The server-side preserve does not help there, because the key is present.
- When the fetch fails the tab renders an explicit "couldn't load knowledge
  bases" state rather than an empty list, so the operator is not shown a false
  "nothing attached".
- Rationale: either half alone leaves the path open. The client fix alone
  leaves the API undefended against any other caller that omits the key; the
  server fix alone does nothing about squawk 0050's actual bug, which sends the
  key *present and empty*.
- Trade-off: two changes plus a marker to defend one field. Accepted: this is a
  live data-loss path since Flight 5 made `kb_ids` functional.

**DD-13 — `disabled_tools` entries for ungated-prefix tools survive a Studio
save, fixed client-side**: `collectFormData` computes the built-in disabled
names from the tool checkboxes as it does today, then **unions in the stored
entries whose names start with an `UNGATED_TOOL_PREFIXES` prefix** (`mcp__`,
`kb__`) from the loaded agent object. Symmetric with DD-4's client half.
- **This is the defect DD-5 was quietly resting on** (Architect cycle 1, high).
  `collectFormData` derives `disabled_tools` from
  `input[type="checkbox"][data-tool]` — built-in tools only — and sets it in
  **all three** of its branches (`[]`, `[]`, or the built-in disabled names).
  The Tools tab renders built-in categories only, and MCP per-tool disables live
  in `mcp_overrides`. So a `kb__…__search` entry set through the API is erased
  by the next unrelated Studio save: fail-open, the same shape as squawk 0050,
  in the same code block.
- Without this, DD-5 spends the flight's highest-risk leg preserving a value
  across a rename that the UI deletes on the next save. **DD-13 is the more
  load-bearing of the two**; DD-5 only matters once entries survive at all.
- **Client-side, NOT a server-side preserve in `update_agent`** (Architect cycle
  2, high). A server-side "always re-add every stored ungated entry" is a one-way
  ratchet: Studio always sends the key, an API caller wanting removal sends a
  list without the name, and the two payloads are indistinguishable — so once an
  entry existed, **no PUT could ever remove it** and a deliberately disabled tool
  would become permanently un-re-enableable, with no UI to undo it. That trades
  one fail-open for an invisible permanent fail-closed, which is worse.
- An earlier draft justified the server side with "the client cannot re-add a
  name it never rendered." That was **wrong**: `_agent_response` returns
  `disabled_tools` byte-identical (only MCP credential keys are masked), so the
  editor already holds every stored ungated entry and can re-emit it — exactly
  as DD-4 has the client do for `kb_ids`.
- **The un-disable path stays open and is stated**: `PUT /api/agents/{name}`
  with an explicit `disabled_tools` list is authoritative, because an API caller
  sends the list it wants. Only the Studio form unions, and only because the
  Studio form cannot render these names. The behavior test proves **removal
  still works**, not merely that the entry survives — a survival-only net would
  pass against the ratchet this decision exists to avoid.
- **The union must read a freshly fetched agent, not the Studio cache**
  (Architect cycle 3, high). Verified: `loadAll()` is not re-run on a Studio
  section switch — it runs at area mount and after a save or delete only — so
  after a rename performed in the Knowledge section, the cached agent object
  still holds the pre-rewrite entry and the next save would put it straight
  back, silently undoing DD-5. Refresh the agent on agent-editor mount alongside
  DD-15's knowledge-base refresh; there is an exact in-file precedent that pairs
  `refreshMcpSourcesCache()` with a `fetch('/api/agents/' + name)` and re-selects.
- **Create mode contributes nothing**: `_selectedAgent` is `null` there, so the
  union must be guarded. A new agent has no stored entries, so this is
  semantically a no-op — but an unguarded read crashes the Save path.
- Append the stored ungated entries **after** the built-in names in a stable
  order. The collected value also feeds dirty-tracking, so nondeterministic
  ordering (a `Set` iteration, say) would make the Save button flicker.
- Trade-off: the rule lives in the client, so a future non-Studio UI would need
  it too. Accepted — the alternative removes a capability silently.
- Note the symmetry: top-level `disabled_tools` can also hold `mcp__` names set
  through the API, and the union preserves those too. That is correct and not a
  new coupling — the MCPs tab writes per-tool disables to
  `mcp_overrides[source].disabled_tools`, a disjoint field, so the union cannot
  resurrect anything that tab controls.

**DD-17 — The tool-name discriminator is applied ALWAYS, not only on collision,
so a derived tool name no longer depends on the agent's attached set**:
`_compute_tool_names` drops its `over_length or colliding` condition and gives
every knowledge base the `sha256(kb_id)[:8]` discriminator unconditionally.
- **This is the root-cause fix, chosen over patching four call sites**
  (operator decision at Architect cycle 3). Verified: the discriminator is
  currently conditional — `hash_len_by_id[kb.id] = None` when a slug neither
  collides nor overflows — and it is applied to *every* member of a colliding
  group. That makes the derived name a function of the **whole attached set**,
  so a name-keyed `disabled_tools` entry goes stale and its tool silently
  re-enables on **four** distinct events: rename, a delete that resolves a
  collision, an **attach** that creates one, and a **detach** that resolves one.
  Cases 3 and 4 arrive through the attach tab this flight introduces.
- After this change the name is `f(kb.name, kb.id)`. Delete, attach and detach
  cannot move it, so three of the four cases stop existing rather than being
  defended. Only rename remains, because the name is an input to it — that is
  DD-5, and it collapses to a single-entry rewrite.
- **It also collapses DD-14.** A deleted knowledge base's stale entry becomes
  permanently inert: a later knowledge base with the same *name* has a different
  `kb_id`, therefore a different hash, therefore a different tool name. The
  silent-pre-disable trap that justified a delete strip cannot occur.
- **Residual, stated rather than hidden**: the uniqueness-assertion loop that
  widens 8→12→16 on a genuine sha256 prefix collision is still set-scoped, so in
  that astronomically unlikely case a sibling's name can still move. Kept —
  removing the assertion would be worse than the residue it leaves — and
  recorded as a known, unhandled case rather than papered over.
- Costs, accepted: every tool name grows by 9 characters, so **DD-16's slug
  budget falls from 52 to 43**; and every derived name shifts once. Nothing real
  is affected — Flight 5 shipped a day ago onto a mission branch not yet merged
  to `main`, so no install holds a name-keyed entry. Flight 5's naming tests
  must be **updated in place rather than deleted and re-added**, so `git blame`
  records the intent shift.
- Trade-off: uglier tool names, permanently. Worth it — the alternative was
  three cross-entity writes with three different orderings in a mission's last
  flight.

**DD-5 — A rename rewrites name-keyed `disabled_tools` entries across every
attached agent**: when `update_knowledge_base` changes `name`, then for each
agent whose `kb_ids` contains that knowledge base, recompute the agent's whole
`{kb_id: tool_name}` map before and after the rename and rewrite any
`disabled_tools` entry matching an old name to its new name. Entries that match
nothing are left untouched.
- Rationale: the derived tool name is `kb__{slug}__search` where the slug comes
  from the knowledge base's **name**, and `disabled_tools` is an exact-name
  blacklist applied universally, `kb__` prefix included
  (`AgentConfig.is_tool_enabled`). So today a rename silently **re-enables** a
  tool the operator deliberately disabled — it fails *open*, which is the wrong
  direction to fail. Flight 6 is the flight that adds the rename affordance, so
  Flight 6 owns the consequence.
- **Under DD-17 this is a single-entry rewrite**: compute the knowledge base's
  old derived name from `existing.name` (already in hand) and its new one from
  the incoming name, both in memory, then replace that one entry per agent.
  *(An earlier draft required recomputing the agent's whole map, because a
  rename could move a sibling's name by creating or resolving a slug collision.
  DD-17 removes that coupling — the only residue is the pathological
  hash-collision widening case DD-17 records.)*
- Rejected — clear the entry instead of rewriting it: turns one fail-open into
  another. Rejected — refuse the rename while any agent disables the tool:
  rename is the affordance this flight exists to add.
- Precedent: the v7 schema migration already rewrites tool names across every
  agent's `enabled_tools`/`disabled_tools` columns (`db/schema.py`, v7 block),
  including its rule that `enabled_tools = NULL` is preserved as `NULL` and
  never coerced to `[]`.
- **Scope is `disabled_tools` only, deliberately** — narrower than the cited v7
  precedent, which also rewrites `enabled_tools`. Reason: `kb__` is in
  `UNGATED_TOOL_PREFIXES`, so `is_tool_enabled` never consults `enabled_tools`
  for a `kb__` name and an entry there is inert. A Developer following the v7
  precedent would widen this incorrectly; the reason is stated so they don't.
- **Ordering and partial failure**: `write_transaction` raises on re-entry by
  the same task, so the rename and the agent saves are **sequential
  transactions, not one atomic unit**. Compute both names in memory **first**
  (they depend only on `existing.name`, the incoming name and `kb_id` — never on
  when the row is written), then rename the knowledge base, then rewrite each
  agent. The reverse mutation order would leave rewritten entries behind a
  rename that never happened. A failure part-way leaves later agents
  unrewritten, which fails open, so each such agent is named in a WARNING log.
  This is a stated limitation, not an oversight.
- Prefer adding `SQLiteAgentStore.list_by_kb(kb_id)` — `list_by_provider` is
  the structural precedent — over scanning every agent; it also gives the
  rewrite a natural unit-test seam. **The precedent does not transfer
  verbatim**: `list_by_provider` is plain column equality, while `kb_ids` is a
  JSON TEXT column, so this needs `json_each` (JSON1 is already relied on
  elsewhere in `schema.py`). A `LIKE '%<id>%'` would match substrings of other
  ids and is wrong.
- The rewrite goes through `SQLiteAgentStore.load`/`save`, which decrypt and
  re-encrypt `mcp_overrides` credentials on the round trip. Do **not** "optimise"
  it into a targeted `UPDATE agents SET disabled_tools = ?` that bypasses the
  store and its encryptor.
- **Rename inherits the session-bound attachment contract**: a live agent holds
  its old tool name until the next agent build, exactly as detach does. A
  rename is not retroactive to an open session, and the flight does not try to
  make it one.
- Trade-off: `update_knowledge_base` becomes a cross-entity write, loading and
  potentially saving agent rows. This is the flight's one shared-interface
  change and its highest-risk leg.

**DD-14 — Delete writes nothing to any agent: `kb_ids` self-heals at the next
save, and the `disabled_tools` entry is inert under DD-17.** Neither dangling
value needs defending, for different reasons.
- **`kb_ids`: left dangling, dropped at the next save.** Already the system's
  behaviour and it already degrades safely — `delete_knowledge_base` cascades to
  `kb_items` and `kb_chunks` only; nothing writes `agents.kb_ids`;
  `KBToolProvider` logs a WARNING and skips an id that no longer resolves, and
  the self-configuration projection skips it too. Once the attach tab renders
  only existing knowledge bases, the operator's next save drops it naturally.
  The change here is that the save-time drop becomes a **stated decision rather
  than an emergent behaviour** — documented, and pinned by the behavior test.
- **`disabled_tools`: left alone. Delete is NOT a cross-entity write.** Under
  DD-17 the stale entry is permanently **inert**, not a trap: the derived name
  includes `sha256(kb_id)[:8]`, so a later knowledge base created with the same
  *name* gets a different id, a different hash and a different tool name. It can
  never match the stale entry, so it can never be silently pre-disabled.
- *(Architect cycle 2 established that a dangling blacklist entry was a real
  trap and required a delete strip; cycle 3 showed the strip would also have had
  to recompute sibling names, with an ordering rule that could not transfer from
  DD-5. DD-17 removes the trap at its source, so the strip is deleted rather
  than fixed — the hazard no longer exists to defend against.)*
- The entry does remain as dead text in an agent's `disabled_tools`, re-emitted
  by DD-13's union. Cosmetic, bounded, and documented; removing it is exactly
  the kind of cleanup the next mission's `kb_id`-keyed rework subsumes.
- Trade-off: between delete and the next save, an agent's stored `kb_ids` names
  something that no longer exists. Harmless by construction, and now written
  down.

**DD-15 — The knowledge-base list is refreshed on agent-editor mount, not only
at Studio mount**: add `refreshKnowledgeBasesCache()` mirroring
`refreshMcpSourcesCache`, and extend the tab signature to
`renderKnowledgeTab(panel, agent, allKnowledgeBases, callbacks)` the way
`renderMcpsTab` was extended.
- Rationale (Architect cycle 1, medium): `self._allKnowledgeBases` is populated
  once inside `loadAll()`'s `Promise.all` and **read nowhere in the file** — it
  is currently dead. The MCP list gained a per-edit-mount refresh precisely
  because a source created in the inventory was otherwise invisible until a hard
  reload. Create-then-attach is the flight's own primary journey and the
  behavior test walks it directly, so the same fix is needed here.
- The refresh must set DD-4's load marker only on success, which is why DD-4 and
  DD-15 land in the same leg.
- Mirror `refreshMcpSourcesCache`'s failure behaviour exactly: its `.catch`
  keeps the **prior** cache (`self._allMcpSources || []`), it does not blank it.
  A refresh that blanked a populated cache on a transient error would be a new
  defect.
- **But the attach tab renders the load-failure state anyway, even when the
  prior cache is populated** (Architect cycle 3, medium). Otherwise DD-4's
  marker and DD-15's keep-prior rule contradict each other on the second mount
  after a transient failure: rows would render from stale data while the marker
  stayed unset, so the operator could toggle an attachment, save, see "Saved",
  and have nothing change. Keeping the cache serves its other consumers; this
  surface refuses to render stale attachment state as if it were current.

**DD-6 — New operator-facing route `GET /api/knowledge-bases/{kb_id}/search`**:
read-only, wrapping `retrieval.search`, returning `{hits: [...], degraded: str |
null, indexer: str}`.
- Rationale: Flight 5's debrief records as a follow-up that "Flight 6's
  inventory should call `search()` directly and render `SearchResult.degraded`
  — the stated justifications for DD-1's module shape and result object", and
  says that if neither happens both decisions should be revisited. **Verified
  during reconnaissance: it cannot be done as written.** `retrieval.search`
  takes `chunk_repo`, `item_repo`, `store` and `backend` as keyword-only
  arguments — an in-process call — and no HTTP route exposes it. The route is
  the missing piece; with it, the inventory genuinely is the non-agent consumer
  those two decisions were justified by.
- The `indexer` field is the mitigation Flight 5's debrief asks for (follow-up
  12: correlate the degrade line with indexer state). It reuses
  `get_indexing_manager().state(kb_id)` — the same call `get_kb_status` already
  makes — so it adds a field, not machinery.
- **Route shape, specified rather than left to the implementer**: query
  parameter `q` (required, non-empty); `limit: int = Query(10, ge=1, le=20)`,
  because `KBSearchTool` enforces the same 1–20 bound itself — the agent loop
  applies no schema validation, so a route-side `Query` bound is the equivalent
  guard; 404 on an unknown `kb_id`, as every sibling knowledge-base route does.
  Each hit renders its `SearchHit.score` alongside its path and text.
- **The route does NOT render per-hit provenance (which list a hit came from),
  and `SearchHit` is not widened** (Architect cycle 2, high). An earlier draft
  asserted each hit "carries which list(s) it came from". Verified false:
  `SearchHit` carries `chunk_id, item_id, path, seq, char_start, char_end, text,
  score` and nothing more; the membership flags live on `_FusedCandidate`, whose
  docstring states it "never crosses out of this module". Rendering provenance
  would mean widening the public result dataclass of the module Flight 5 landed
  a day ago — a shared-interface change, which contradicts this decision's own
  "additive and read-only" framing and would re-tier Leg 1. Score plus the
  `degraded` line is what Flight 5's follow-up 11 actually asked for, and it is
  enough to make the inventory a genuine non-agent consumer of `SearchResult`.
- **`get_embedding_backend()` is synchronous and lock-taking and must be
  resolved under `asyncio.to_thread`**, exactly as `knowledge/tool.py:212` does.
  `api.py` has no such call today, so a Developer has no in-file pattern to copy
  and would plausibly call it inline; it is named here for that reason. The
  repositories and store come from the existing `_kb_chunk_repo()`,
  `_kb_item_repo()` and `_vector_store()` helpers already in `api.py`.
- The route is operator-facing and sits behind the same credential gate as every
  other route, which means an agent holding an external credential can reach it.
  That is the existing trust model, not a new hole — but it is stated in
  `SECURITY-MODEL.md` rather than left implicit.
- Trade-off: a new public route in the mission's last flight. Bounded: read-only,
  no new state, no new dependency, behind the same credential gate as every
  other route.

**DD-7 — One Administration Knowledge panel, honest about what is fixed**:
`chunking.size_chars` and `chunking.overlap_chars` and
`monitoring.watch_enabled` and `monitoring.reconcile_interval_seconds` are
editable; `embedding` and `vector_store` render read-only.
- **This corrects a stale mission claim.** The mission's open question records
  that "Flight 2's settings API refuses a `model_id`/`dim` change while any
  chunk exists (409)". Verified false: `EmbeddingSettings` validates `dim`
  against `EMBEDDING_DIM` and `backend` against the single allowed value
  unconditionally — a 422, not a 409, and not conditional on chunk count. The
  embedding model is **pinned**, not conditionally locked, and there is no
  operator path to change it at all. The panel therefore displays it and does
  not offer to change it, and the mission open question is answered rather than
  carried into the next mission.
- The panel states the two settings' different application semantics, because
  they genuinely differ: monitoring changes apply live through an awaited hook
  on the same request; chunking changes apply to **future indexing only** and
  never re-chunk existing content.
- Trade-off: a read-only block invites "why can't I change this?" The panel
  answers it in place rather than leaving the operator to find out by trying.

**DD-8 — Source text is fetched on demand, never per row render**: the item list
renders from `GET /items` alone; `GET /items/{id}/source` fires only when the
operator opens a specific item's source view.
- Rationale: Flight 3's debrief action item ("do not call `/source` per click")
  understates it — the route re-reads and re-extracts the file from disk on
  every call, so a list that prefetched source would re-extract every file in
  the folder on every render.
- Trade-off: opening source costs a round trip. Correct: it is the read the
  operator explicitly asked for.

**DD-9 — A standalone file item whose path lies inside a registered folder is
badged with the containing folder**: the item list marks it rather than
silently showing what looks like a duplicate.
- Rationale: Flight 3's debrief asks for this to be "legible". `GET /items`
  returns each item's full model dump, `parent_id` included, so a standalone
  item (null `parent_id`) whose path is under a folder item's path is
  identifiable client-side with no API change.
- Trade-off: a client-side path comparison. Acceptable — it is presentation,
  and the authoritative relationship stays `parent_id`.

**DD-10 — The folder-registration form renders the route's refusal reasons in
its own words**: including Flight 4's DD-6 case, where a folder that equals,
contains, or lies inside the application data directory is refused 422 — the
form says *why* (the app's own database and index live there), not just that it
failed.
- Rationale: F4's debrief asks for this explicitly. A bare 422 on the operator's
  home directory reads as a bug.

**DD-11 — HAT apparatus: browser-driving Executor, with every assertion's read
path named** *(premise-audited on both axes)*.
- **Act**: a browser apparatus (Playwright or chrome-devtools MCP) drives the
  Studio UI; Bash creates, edits and deletes fixture files on disk to trigger
  real indexing and real watcher activity.
- **Observe**: rendered state (screenshot + accessibility snapshot) for every
  UI assertion; and for the assertions the UI collapses or cannot show —
  - index/watch/indexer state → `GET /api/knowledge-bases/{kb_id}/status`
    (returns per-folder `status`, `watch`, `watch_error`, plus `chunks` and
    `indexer`);
  - **`kb_ids` and `disabled_tools` survive an unrelated save** → `GET
    /api/agents/{name}`, whose response routes through `_agent_response` and
    carries both as stored;
  - **an agent's derived `kb__…__search` name** → the attach-tab row renders it
    (DD-3). Nothing else exposes it — no `/agents/{name}/tools` route exists and
    the self-configuration projection returns knowledge-base *names*;
  - degrade behaviour → the DD-6 route's `degraded` and `indexer` fields.
- Both axes are static facts checked at planning against current code, not
  assumed. **Two** read paths did not exist and are added by this flight rather
  than discovered mid-HAT: DD-6's search route, and DD-3's rendered tool name.
  The second was missed on the first pass — this decision claimed every read
  path was named while one assertion had none, which is exactly the failure the
  observability audit exists to prevent, caught at Architect cycle 2 rather than
  at HAT time.
- Instance: a dedicated dev instance (`THE_ONE_PORT=8485` + scratch data dir),
  never port 8484 or the default data dir. Credential mechanics follow CLAUDE.md's
  "Behavior-test credential convention" by reference; no step table encodes them.

**DD-16 — The name-length hint is advisory, and the number is 43**: the create
and rename forms warn when a name exceeds 43 characters; they do not refuse it.
An empty name is refused (it yields the slug `""` and the tool name
`kb____<hash>__search`) — `KnowledgeBase.name` has no minimum either.
- Rationale: verified at Architect cycle 2 that `KnowledgeBase` constrains `id`
  only — `name` carries no length bound, and an over-length name is **truncated
  and discriminated** by `_compute_tool_names`, never rejected. So a hint that
  implied refusal would be lying about the system. 52 is the real budget:
  64 (the LLM tool-name ceiling) − `len("kb__")` − `len("__search")`. A raw
  character count is accurate because `_normalize_kb_name` is a strict 1:1
  character map — but count **code points** (`[...name].length`), not UTF-16
  units, or an astral character counts double in the browser and single on the
  server.
- 43, not 52: **DD-17** makes the discriminator unconditional, so its 9
  characters come out of the slug budget on every name rather than only on
  colliding ones.
- Trade-off: a warning the operator can ignore. Correct — the system does accept
  the name; the consequence is a truncated tool name, not a failure.

**DD-12 — Behavior test `kb-studio-round-trip`**: authored in this flight, and
it carries four assertions that exist because of specific prior findings, each
about state that must **not** change —
- `kb_ids` survives a save made from an unrelated tab (squawk 0050's net);
- a `kb__` entry in `disabled_tools` survives a save made from an unrelated tab
  (DD-13's net);
- that entry still names the agent's current tool after a rename (DD-5's net);
- a deleted knowledge base's id dangles until the next save and is gone after it,
  while its `disabled_tools` entry is stripped at delete (DD-14's net — every
  half asserted, so the decided behaviour is pinned rather than inferred);

and one that must **change**, because its absence is how a preserve rule turns
into a ratchet:

- an explicit `PUT` removing a `kb__` entry from `disabled_tools` still removes
  it (DD-13's inverse). A survival-only net would pass against exactly the
  failure mode DD-13 rejects.

**Negative** assertions about unchanged state are the class Flight 5's behavior
test was found to be missing entirely, and three of these four exist because a
review found the corresponding defect rather than because a happy path suggested
them.

**DD-18 — The HAT is required, and structured as named state transitions**:
this flight does not land without it.
- **Why required**: the operator's standing criterion, set at Flight 3's debrief
  (Rec. 5), is to plan HAT legs *only* for flights with an operator-visible
  surface — and to fold an API-only flight's walk into the next UI flight's HAT.
  Flight 6 is that UI flight, and it is carrying Flight 3's deferred walk. Making
  it optional here would waive the same walk a second time and leave the
  mission's entire operator-facing surface never seen by the operator before
  close. An earlier draft of this spec marked the leg optional and waivable;
  that was wrong on the operator's own rule.
- **Structure**: state transition sequences, per CLAUDE.md's HAT Design
  Guidance — each transition named, several assertions per state (UI elements,
  error area, button states), and **negative assertions** ("no error messages",
  "nothing else changed") alongside the positive ones. That format is what
  caught three bugs in Flight 04's HAT that an end-state-only walk missed, and
  it matches this flight's dominant defect class, which is state changing when
  it should not.
- **At least one state must be shared with a surface the operator is not looking
  at.** The obvious one here is the **session-bound attachment contract**: an
  agent conversation open in another window keeps its existing tool set, so a
  knowledge base attached, detached or renamed mid-session is not visible to it
  until the next agent build. That is correct behaviour and it will look like a
  bug in a HAT unless it is walked deliberately.
- **Findings route through the fix-vs-feature gate.** Look-and-feel fixes ride
  the inline protocol; anything that adds or alters behaviour is promoted to a
  scoped design review first, and a change touching more than one surface gets a
  lightweight design-review pass before implementation. A HAT finding that
  changes a contract the behavior spec pins (route shapes, `data-testid`s, the
  derived tool name) is a spec re-author, handled deliberately — not an inline
  edit.
- Trade-off: the flight cannot land without operator time. That is the point of
  the leg; a mission whose whole deliverable is two screens should not close on
  agent sign-off alone.

### Citation Audit

Required before the first Architect cycle (squawk 0075). Every design decision
above that asserts a code mechanism, verified against the working tree at
`d3c122b`:

| Citation | Status |
|---|---|
| `static/js/areas/studio/stub-knowledge.js::renderKnowledgeStub` — renders a `.page-header` + `h1` and one `.empty-canvas` one-liner; no data is fetched or rendered | verified |
| `static/js/areas/studio.js::collectFormData` — `disabled_tools` derived from `input[type="checkbox"][data-tool]` (built-ins only) and set in **all three** branches, so an ungated-prefix entry is erased by any save (DD-13's premise) | verified |
| `static/js/areas/studio.js` — `self._allKnowledgeBases` written once in `loadAll()`'s `Promise.all`, read nowhere in the file; no refresh path exists (DD-15) | verified |
| `static/js/areas/studio.js::refreshMcpSourcesCache` — `.catch` swallows the error and keeps an empty cache (DD-4's reachable-failure premise; DD-15's precedent) | verified |
| `interfaces/web/api.py` — folder-registration guard is `is_within(settings.data_dir, canonical) or is_within(canonical, settings.data_dir)`: a folder is refused **only** for overlap with the data dir, so `$HOME` is not refused when the data dir is elsewhere (DD-10; behavior-test step 4) | verified |
| `knowledge/tool.py` — `backend = await asyncio.to_thread(get_embedding_backend)`; repositories built on the request connection; `store = await get_vector_store()` (DD-6's feasibility and its `to_thread` requirement) | verified |
| `interfaces/web/api.py` — `_kb_chunk_repo()`, `_kb_item_repo()`, `_vector_store()` helpers already exist in this module (DD-6's wiring) | verified |
| `db/repositories.py::SQLiteAgentStore` — offers `list_agents()` (names), `load(name)`, and `list_by_provider(provider_config_id)`; **no** kb-scoped query (DD-5's `list_by_kb` precedent) | verified |
| `db/_write_lock.py::write_transaction` — raises on re-entry by the same task, so DD-5's rename and agent saves cannot be one atomic unit (DD-5's ordering rule) | verified |
| `interfaces/web/api.py::delete_knowledge_base` — cascades to `kb_items`/`kb_chunks` and the vector store; nothing writes `agents.kb_ids` (DD-14) | verified |
| `knowledge/retrieval.py::SearchHit` — fields are `chunk_id, item_id, path, seq, char_start, char_end, text, score`; **no list-membership fields**. `_FusedCandidate` holds `in_keyword_list`/`in_semantic_list` and its docstring states it "never crosses out of this module" (DD-6's dropped provenance claim) | verified |
| `interfaces/web/api.py::_agent_response` — returns `disabled_tools` byte-identical; only MCP credential keys are masked, so the Studio editor already holds stored ungated-prefix entries (DD-13's client-side feasibility) | verified |
| `knowledge/walk.py` — a file whose lower-cased suffix is outside the extractor allowlist is skipped with `continue` and **never becomes an item** ("by-design filter — never counted"); the size and null-byte rejections that DO produce a `failed` item live downstream in `knowledge/indexer.py` (behavior-test fixture must be `.txt`/`.md`) | verified |
| `db/models.py::KnowledgeBase` — constrains `id` only; `name` carries no length bound, and an over-length name is truncated + discriminated by `_compute_tool_names`, never refused (DD-16's advisory semantics and its 52-character budget) | verified |
| No read path for an agent's derived `kb__…__search` name — `GET /tools` returns built-ins, no `/agents/{name}/tools` route exists, and `self_configuration/projection.py` returns knowledge-base *names*, not tool names (DD-3's row rendering is the read path) | verified |
| `static/js/areas/studio.js::refreshMcpSourcesCache` — the `.catch` keeps the **prior** cache (`self._allMcpSources || []`), it does not blank it; and the promise always resolves (DD-4's marker wording, DD-15's failure behaviour) | verified |
| `static/js/areas/studio/knowledge-tab.js::renderKnowledgeTab` — renders one `.empty-state`; takes `panel` only, no agent, no knowledge-base list | verified |
| `static/js/areas/studio.js::collectFormData` — `querySelectorAll('.chip-area[data-type="kb"] .chip')`, then `data.kb_ids` built from it; the selector matches nothing, so `[]` is PUT on every save (DD-3, DD-4) | verified |
| `static/js/areas/studio/mcps-tab.js` — `checkbox.setAttribute('data-mcp-source-toggle', '')`; `studio.js` collects `[data-mcp-source-toggle][data-mcp-source-id]` (DD-3's precedent) | verified |
| `static/js/areas/studio/agent-editor.js::renderAgentEditor` — all five tab panels mounted unconditionally before return; `renderKnowledgeTab(knowledgePanel)` is not deferred to tab activation (DD-4) | verified |
| `interfaces/web/api.py::update_agent` — `if "self_revision_requires_approval" not in data: data[...] = existing...` — the keep-on-omit precedent DD-4 mirrors | verified |
| `interfaces/web/api.py::update_knowledge_base` — `merged = existing.model_dump(); merged.update(data)` — accepts and applies `name` (DD-5's premise) | verified |
| `agent/config.py::AgentConfig.is_tool_enabled` — `disabled_tools` is a universal exact-name blacklist checked after the ungated-prefix gate, so a `kb__` name in it is still disabled (DD-5's fail-open premise) | verified |
| `knowledge/tool_provider.py::_compute_tool_names` — the discriminator is **conditional**: `hash_len_by_id[kb.id] = None` when a slug neither collides nor overflows, and it is applied to *every* member of a colliding group. So a derived name is order-independent but **set-dependent** — the premise DD-17 removes | verified |
| `knowledge/tool_provider.py::_compute_tool_names` — the trailing uniqueness-assertion loop widens 8→12→16 across the set, so it stays set-scoped even under DD-17 (DD-17's recorded residual) | verified |
| `static/js/areas/studio.js` — `loadAll()` runs at area mount and after a save or delete, **not** on section switch; `selectAgent` re-renders from the cached agent object (DD-13's fresh-fetch requirement) | verified |
| `db/schema.py` v7 migration — rewrites tool names across every agent's `enabled_tools`/`disabled_tools`, preserving `NULL` as `NULL` (DD-5's precedent) | verified |
| `knowledge/retrieval.py::search` — keyword-only `chunk_repo`, `item_repo`, `store`, `backend`; returns `SearchResult(hits, degraded)`; **no HTTP route exposes it** (DD-6's premise) | verified |
| `interfaces/web/api.py::get_kb_status` — returns `items`, `folders[]` with `status`/`watch`/`watch_error`, `chunks`, `indexer`; **no walk skip counters** (DD-11's read path; R8's deferral) | verified |
| `knowledge/settings.py::EmbeddingSettings` — `backend`, `model_id` and `dim` each validated against a single allowed value unconditionally, no chunk-count condition, raising `ValueError` → 422 (DD-7's correction of the mission) | verified |
| `knowledge/settings.py::ChunkingSettings` / `MonitoringSettings` — `size_chars` (200–2000), `overlap_chars` (≤ 50% of size), `watch_enabled`, `reconcile_interval_seconds` (10–86400) (DD-7's editable set) | verified |
| `interfaces/web/api.py::update_knowledge_settings` — accepts only `embedding`/`chunking`/`monitoring`; monitoring applied live via `_after_monitoring_settings_changed` (DD-7's semantics) | verified |
| `interfaces/web/api.py::list_kb_items` — returns each item's full `model_dump()`, `parent_id` included (DD-9) | verified |
| `interfaces/web/api.py::get_kb_item_source` — re-reads and re-extracts from disk per call (DD-8) | verified |
| `interfaces/web/api.py::_agent_response` — `cfg.model_dump()` with only credential keys masked, so `kb_ids` is returned as stored (DD-11's read path for the squawk-0050 assertion) | verified |
| `interfaces/web/app.py` lifespan — drains watch manager, indexing manager, web-session reaper, PTY registry, MCP pool; `get_vector_store` appears nowhere (DD-1's R14, out of scope here) | verified |

### Prerequisites

- [x] Mission branch `mission/24-knowledge-bases` current at `d3c122b`; working tree clean apart from planning artifacts; `ruff check the_one/ tests/ scripts/` passes; `pip-audit` clean as of the squawk turnaround (PR #205) *(verified at Architect cycle 1)*
- [ ] Browser apparatus available for the HAT and for `make test-browser` (Playwright + Chromium installed)
- [ ] A fixture folder of small text/markdown files outside the repo, including at least one deliberately failing file (over `MAX_FILE_BYTES` or containing a null byte) so the failure path is observable
- [ ] No CI lane runs on this branch — `make lint`, `make test-unit`, the release-closure `pip-audit`, and the frozen Windows build are all run by hand and recorded in the flight log

**Session-external — re-verify at the leg that needs them, never once at
planning** (F4 debrief Rec. 6):

- [ ] Dedicated dev instance reachable on `THE_ONE_PORT=8485` with a scratch
      data dir — **never** 8484 or the default data dir. The instance can be
      down and its credential can have been rotated since planning; re-verify
      both at the leg that drives it, not here.
- [ ] Concourse Windows worker reachable on the day of the frozen build.
- [ ] **Monitoring settings read and pinned before any watcher-dependent
      step.** `monitoring.watch_enabled` defaults `true` and
      `reconcile_interval_seconds` defaults **300** — and this host is WSL2,
      where a native notifier does not fire for Windows-side edits. A step that
      asserts "reflected without operator action" silently depends on all three.
      Read `GET /api/knowledge-settings` and `GET .../status`'s
      `folders[].watch`, record them, and express every settle window in terms
      of the configured interval rather than a bare "reasonable window".

### Pre-Flight Checklist

- [x] All open questions resolved *(one deferred with a stated reason and a named vehicle)*
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified — session-external ones re-verified per leg
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Every surface is built over routes that already exist and are covered by tests,
with one addition (DD-6). The work is therefore mostly front-end: three new
render modules under `static/js/areas/`, two of which replace a stub file
outright, plus browser-lane coverage in the existing `studio` and `system`
lanes.

The backend surface is five changes: DD-6's search route; DD-4's keep-on-omit
guard in `update_agent`; DD-17's unconditional discriminator in
`knowledge/tool_provider.py`, which also promotes `_compute_tool_names` to a
public `compute_tool_names`; DD-3's `{kb_id: tool_name}` field on the agent
response; and DD-5's rename rewrite plus its `SQLiteAgentStore.list_by_kb`.
**Two carry the flight's real risk** — DD-17, because it changes naming code
Flight 5 landed a day ago and every derived name with it, and DD-5, the flight's
one cross-entity write. The leg carrying them is tiered high and gets its own
design review before implementation.

The rename helper and the promoted name computation both live in
`the_one/knowledge/` — the web layer calls the public
`compute_tool_names`, never an underscore-private symbol across a package
boundary. That also gives Flight 7's `the_one/tools/naming.py` refactor a known
caller set. (DD-13's fix is client-side and so is not in this list.)

**A note for whoever plans the next mission.** DD-5 and DD-13 both exist because
`disabled_tools` is keyed by a *derived* name — one that changes with the
knowledge base's name and with the composition of the agent's attached set. A
per-attachment disabled flag keyed by `kb_id` would be immune to rename, to
collision-discriminator changes, and to the Studio-save wipe in one move. That
is out of scope here and is deliberately not attempted in a mission's last
flight, but it is the shape to reach for rather than letting DD-5's rewrite
become permanently load-bearing.

*(Amended at Phase 2d, 2026-09-18, with a trigger this note did not originally
name: **detach → rename → reattach**. `SQLiteAgentStore.list_by_kb` returns only
**currently attached** agents, so a rename performed while a knowledge base is
detached never rewrites the entry of an agent that later reattaches — and on
reattachment the stale name matches nothing, silently re-enabling a tool the
operator disabled. DD-5/DD-17's framing that "only rename can still move a name"
implicitly assumed the agent stays attached throughout. A `kb_id`-keyed flag is
immune to this too, which strengthens rather than changes the recommendation.)*

The search route (DD-6) is additive and read-only; it reuses the dependency
wiring the agent-side tool already uses to obtain a chunk repository, item
repository, vector store and embedding backend.

### Deferred Scope — recorded, not dropped

- **Walk skip counters on `/status`** (F3 debrief; recon R8). Exposing them is
  not a rendering change: nothing in the pipeline accumulates them today, so the
  walk would have to count and persist per-pass skip totals. That is a change
  inside the indexing pipeline, which is neither this flight's surface nor the
  closing flight's. Carried as an open question into the closing flight's
  planning. What this flight *does* surface is every file that became a
  `failed` item with its error — which is what the mission criterion asks for;
  skip counters are about files that never became items at all.
- **The five non-UI carry-forward items** — see DD-1.

- **Per-item freshness on the inventory row, and the invalidation signature that
  must widen with it** *(found by the behavior test's re-verification,
  2026-09-18; see `tests/behavior/kb-studio-round-trip/runs/2026-09-18-reverify.md`)*.
  Two coupled gaps, deferred together **as one leg, deliberately not as two
  squawks**:
  1. An item row renders only path and status, so **a re-indexed file shows no
     on-screen change at all**. The folder's `indexed:` timestamp is not a
     substitute — it advances on every reconcile walk whether or not anything
     changed, which was measured rather than assumed.
  2. `studio.js::knowledgeItemsSignature` is **counts-only**
     (`JSON.stringify(status.items) + '|' + status.chunks`), so a content-only
     edit changes neither term and triggers **no** `/items` re-fetch.
  **They currently mask each other**: the blind spot is harmless only because the
  row shows nothing a content-only change would alter. **Shipping the freshness
  field alone would convert an invisible blind spot into a visible staleness
  bug**, which is why they must land together. `GET /items` already returns
  `indexed_at`, `content_hash`, `size_bytes` and `mtime` per item, so the data
  exists; the work is rendering it and widening the signature to something that
  moves on content change.

### Checkpoints

- [ ] Knowledge inventory renders a real knowledge base end to end: created,
      folder registered, items indexed, chunks and source readable, re-index
      runs, a failure is legible
- [ ] Search preview returns fused hits and renders a degrade line correlated
      with indexer state
- [ ] An agent's attachments survive a save made from an unrelated tab; a
      disabled knowledge-base tool survives an unrelated save **and** a rename
      **and an attach of a same-named knowledge base**; and an explicit API
      removal of that entry still works
- [ ] `kb-studio-round-trip` run and green (Leg 2's regression evidence)
- [ ] Administration exposes chunking and monitoring, and says plainly what is
      fixed
- [ ] `make lint`, `make test-unit`, `make test-browser`, `pip-audit`, and a
      frozen Windows build all run by hand and recorded
- [ ] Mission-closing HAT walked with the operator and its findings resolved
      (required — see DD-18)

### Adaptation Criteria

**Divert if**:
- DD-5's cross-agent rewrite turns out to need a schema change or a migration —
  that is a different risk domain and belongs in its own leg or flight
- DD-17's unconditional discriminator turns out to need a data migration of
  existing `disabled_tools` entries (it should not — no install holds one), or
  breaks a Flight 5 naming invariant that cannot simply be re-pinned

*(An earlier trigger here — "the search route cannot obtain a vector store and
embedding backend from a request context" — was removed: Architect cycle 1
verified `_kb_chunk_repo()`, `_kb_item_repo()` and `_vector_store()` already
exist in `api.py` and that `knowledge/tool.py` shows the exact pattern. The
trigger cannot fire, and leaving it would imply an unresolved risk.)*

**Acceptable variations**:
- Splitting the inventory leg if it proves larger in implementation than in
  design — it is the flight's biggest single surface
- **Splitting Leg 2**, which is the high-risk one and carries the most: a
  natural seam runs UI + client fixes | server-side name integrity (DD-17, DD-3,
  DD-5) | the behavior-test run
- Rendering decisions within the inventory (layout, where status lives) settled
  by the implementing agent against existing Studio patterns

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> one at a time as the flight progresses.
>
> **Amended during execution (2026-09-17):** the planned
> `attach-tab-and-name-integrity` leg was split into `tool-name-integrity`
> (server) and `attach-tab` (client) under this flight's own "Acceptable
> variations", which pre-authorises exactly that seam. Rationale in the flight
> log under "Scope decision — Leg 2 is split in two". Content is unchanged; the
> later legs renumber.

- [ ] `knowledge-inventory` *(ready — see `legs/01-knowledge-inventory.md`)* — Studio's Knowledge section: knowledge-base create
      and delete, folder registration with DD-10's error taxonomy, the
      per-knowledge-base detail view (items with status and errors, per-folder
      walk status + watch state + `watch_error`, chunk count, indexer state,
      re-index changed/all, chunk list, source read-back), DD-8's on-demand
      source fetch, DD-9's duplication badge, and the name-length hint. Includes
      DD-6's search route and the degrade/indexer line it renders. Browser tests
      land as `test_flow_studio_knowledge_*.py` so they fall in the existing
      `studio` lane glob. **Rename is NOT in this leg** — see below.
- [ ] `tool-name-integrity` **(high-risk, server only)** — DD-17's
      unconditional discriminator, `_compute_tool_names` promoted to a public
      `compute_tool_names`, Flight 5's naming tests **updated in place** (not
      deleted and re-added, so `git blame` records the intent shift), the
      `{kb_id: tool_name}` field on the agent response (DD-3's read path),
      DD-4's server-side `kb_ids` keep-on-omit, and DD-5's rename rewrite with
      `SQLiteAgentStore.list_by_kb`. No UI.
- [ ] `attach-tab` — the per-agent Knowledge tab (DD-2, DD-3's row rendering
      consuming Leg 2's field, DD-15's per-edit-mount refresh), squawk 0050's
      client half and its load marker (DD-4), the ungated-prefix
      `disabled_tools` union (DD-13), **the rename affordance itself** in the
      inventory, and **the `kb-studio-round-trip` run** as the combined
      regression evidence for DD-4, DD-13, DD-5, DD-14 and DD-17.
      *Rename ships in this flight, beside DD-5, because DD-5's argument is that
      the flight adding rename owns the consequence — the split above is within
      the flight, so that argument is untouched.*
- [ ] `knowledge-settings-panel` — one Administration panel for chunking and
      monitoring, with embedding and vector store read-only (DD-7). Browser tests
      land as `test_flow_admin_knowledge_settings.py` for the `system` lane glob.
      **This leg also owns the documentation**: CLAUDE.md and `the_one/agents.md`
      for the new route and both surfaces, DD-14's save-time-drop rule, and
      DD-6's credential-reach note in `SECURITY-MODEL.md`.
- [ ] `hat-and-alignment` **(required, interactive)** — the mission-closing HAT,
      structured per DD-18: Flight 3's seven waived steps (register a folder,
      watch status, read chunks/source, re-index, read a failure, concurrent
      delete, restart-resume) plus this flight's own surfaces, walked as named
      state transitions rather than isolated checks. Sized to what has
      accumulated behind it, planned for flexibility rather than a fixed
      checklist. **Not optional**: this is the mission's only flight with an
      operator-visible surface, which is the operator's own standing criterion
      for when a HAT is planned (Flight 3 debrief, Rec. 5).

---

## Post-Flight

### Completion Checklist

*(Reconciled at the Flight 6 debrief, 2026-09-19. The landing commit `7208327`
flipped two status strings and left this section entirely unticked — 0 of 10 —
while the log recorded several of these green repeatedly. The Architect's debrief
review caught it. Each box below is now either ticked with its evidence or left
unticked **with the reason stated**, on the `pip-audit` pattern: an item that
failed honestly and said why is worth more than one silently carried.)*

- [x] All legs completed, `hat-and-alignment` included — six legs landed; the HAT
      was walked with the operator on 2026-09-19 (flight log, "The HAT walk
      itself")
- [x] Code merged to `mission/24-knowledge-bases` — PR #206 merged 2026-09-19 at
      `c44e782`
- [x] `make lint` clean — `ruff check` + `ruff format --check` clean on every leg
      and on the final tree (449 files formatted)
- [x] `make test-unit` green — **4769 passed, 10 skipped, 593 deselected,
      17 warnings, 595.22s** on the final tree
- [ ] `make test-browser` green (`TEST_TIMEOUT=3600`) — **not run.** Only the
      `studio` and `system` lanes were run (studio: 176 passed, 3 skipped, on the
      final tree). The lanes are basename globs, so a full-suite run is **not**
      implied by them. No leg owned this item, which is why it was never scheduled.
- [ ] `pip-audit` clean against the release closure — **blocked by squawk 0083**
      (anyio CVE bump). Ran, failed, filed, left honestly unticked.
- [ ] Frozen Windows installer builds and runs — **not attempted.** Needs the
      Concourse Windows worker, named in Prerequisites as a session-external
      precondition and never re-verified because no leg owned the build. Carries
      to the closing flight.
- [x] `kb-studio-round-trip` run and green, run log committed (Leg 2) — 18/19 on
      `2026-09-18-13-14-52` with one real failure (step 8), remediated and
      re-verified green on `2026-09-18-reverify`; both run logs committed.
      **Caveat**: the spec itself remains `**Status**: draft` with five recorded
      structural defects. It ran and it is green; it is not yet a regression net.
- [ ] Squawk 0050 marked completed with its sign-off — **still `open`.** Its
      regression net (a General-tab save not wiping `kb_ids`) was exercised in the
      behavior test *and* in the HAT and held both times, but the squawk was never
      formally closed with a reviewer sign-off.
- [x] CLAUDE.md, `the_one/agents.md` and `SECURITY-MODEL.md` updated for the new
      route, both surfaces, and DD-14's delete semantics (Leg 3 owns this) —
      +40/-2 across the three files

**Four items remain open and every one has a named owner or blocker.** Three
(browser suite, frozen build, `pip-audit`) carry to the closing flight; the fourth
(merge) is the operator's. Two of them — the full browser run and the frozen build
— were unowned by any leg, which is the structural reason they went unexecuted
rather than unticked-with-a-reason. See the debrief's recommendation on giving
every Completion Checklist item a leg owner.

### Verification

- **Behavior test**: `kb-studio-round-trip` (DD-12) — authored in this flight and
  **run as part of Leg 2**, not deferred to the optional HAT leg: it is Leg 2's
  own regression evidence for DD-4, DD-13, DD-5 and DD-14, and leaving it to an
  optional leg would let the flight complete with none of those nets ever run.
  Run via `/mission-control:behavior-test kb-studio-round-trip` against a
  dedicated dev instance. Carries the five assertions in DD-12 — four about
  state that must not change, one about state that must.
- **Browser lanes**: `studio` (inventory, attach tab) and `system` (settings
  panel), via `scripts/run-tests.sh --lane …`, never bare `pytest -m browser`.
- **Unit**: `make test-unit` verbatim, for the search route, the `kb_ids`
  preserve, and the rename rewrite.
- **HAT**: the `hat-and-alignment` leg, walked with the operator — required, not
  waivable. See DD-18 for its structure and the cross-surface state it must
  include.
