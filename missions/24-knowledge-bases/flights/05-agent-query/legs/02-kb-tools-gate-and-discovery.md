# Leg 2: Knowledge-Base Tools, Wiring and Discovery

**Status**: completed
**Flight**: [Agent Query](../flight.md)
**Risk tier**: high — factory wiring with a strict call ordering that three
review cycles converged on, a new per-agent tool surface, and an edit to
`_search_tools.py`, whose matching rules are already subtle.

## Objective

Make Leg 1's retrieval reachable by an attached agent. One
`kb__{slug}__search` tool per attached knowledge base, built by a per-agent
provider, registered by `AgentFactory` beside the MCP tools, discoverable
through `search_tools` under a `kb:` group, and reachable only by agents the
operator attached it to. Documentation for all of it.

## Dependencies

Leg 1 (`landed`) provides `the_one/knowledge/retrieval.py::search`,
`SearchResult`/`SearchHit`, `SEMANTIC_QUERY_TIMEOUT`, `VectorStoreBusyError`,
and `UNGATED_TOOL_PREFIXES` already containing `"kb__"`. **DD-6 is done** —
this leg adds only the factory-level regression that proves the gate works
end to end with a real `kb__` tool registered.

## Scope

**Creates**
- `the_one/knowledge/tool.py` — `KBSearchTool`
- `the_one/knowledge/tool_provider.py` — `KBToolProvider`
- `tests/test_kb_tool_provider.py`

**Modifies**
- `the_one/agent/factory.py` — provider construction + the four-step ordering
- `the_one/tools/_search_tools.py` — the `kb__` branch in `_format_result` only (no `source_index` change)
- `the_one/agent/config.py` — `BASE_PROMPT` only (the gate itself is Leg 1)
- `tests/test_factory.py`, `tests/test_search_tools.py`
- `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`

**Out of scope**: `retrieval.py` and `the_one/vectors/` (Leg 1, landed); any
Studio/UI surface (Flight 6); squawk 0050.

## Acceptance Criteria

### `KBSearchTool` (DD-4)

- [x] **AC-1** `KBSearchTool(Tool)` sets `name` / `description` / `parameters`
  as **instance** attributes **before** `super().__init__()`, and passes
  `agent_name` through to it. `tests/test_factory.py::TestAgentNamePlumbing::test_agent_name_threads_to_tools`
  iterates every registered tool asserting `tool._agent_name == name`, so
  omitting it fails an existing test.
- [x] **AC-2** The tool **receives** its finished name from the provider; it
  does not compute it (AC-6 explains why).
- [x] **AC-3** Parameters: `query` (string, required) and `limit` (integer,
  optional, default 5, range 1–20). Out-of-range `limit` is **rejected with a
  message, not clamped** — `search_keyword`'s convention. **The tool alone is
  responsible for this**: `Agent._execute_tool` calls `tool.execute(**args)`
  directly with no JSON-Schema validation or coercion of `args` against
  `self.parameters`, and converts a raised exception into
  `[error] Tool execution failed: {e}`. Stated because a reader could
  reasonably assume the schema is enforced upstream.
- [x] **AC-4** `description` names the knowledge base and, when set, its
  description, and **instructs terse, keyword-shaped queries rather than
  sentences**. Not a style preference: FTS5's implicit AND drops the keyword
  side to zero hits on a sentence-shaped query, which is the half the mission's
  exact-term criterion rests on (DD-3).
- [x] **AC-5** The tool holds `kb_id` and `kb_name` and resolves its
  connection, repositories, store and backend **at call time**, then calls
  Leg 1's `search`. `get_embedding_backend()` is resolved under
  `asyncio.to_thread` — it is synchronous and takes a `threading.Lock`, so
  calling it on the event loop before warm-up blocks the loop for the model
  load.

### Naming: collision, length, uniqueness (DD-4)

- [x] **AC-6** `KBToolProvider` computes every name for the agent's whole
  attached set, because group-collision detection needs that set.
  `slug = _normalize_kb_name(kb.name)`, mirroring
  `the_one/mcp/_tool.py::_normalize_source_name` (every character outside
  `[a-zA-Z0-9_-]` → `_`), re-implemented in the knowledge package with a
  docstring note pointing at the sibling.
- [x] **AC-7** **Group-wide collision discriminator**: if a slug has more
  than one claimant among the agent's attached knowledge bases, **every**
  member of that group gets the discriminator — not just the second and
  subsequent. **The discriminator is AC-9's fixed-length hash, never
  `kb_id[:6]` or any other prefix of `kb_id`**; read AC-9 before implementing
  this criterion. A test proves the names are identical under a **reordered**
  `kb_ids`, because `disabled_tools` is name-keyed and an order-dependent
  name would silently re-target a different knowledge base after a reorder.
- [x] **AC-8** **Over-length names truncate and suffix; they are never
  dropped.** Truncate the slug to fit `_TOOL_NAME_MAX_LEN` (64), append a
  single discriminator, log at WARNING. Dropping is the `MCPClientTool`
  precedent and does **not** transfer: there a drop costs one tool of many,
  here it costs the knowledge base's only tool — the whole attachment,
  invisibly.
- [x] **AC-9** **Uniqueness is asserted, not assumed, and the discriminator
  is fixed-length.** `kb_id` is client-supplyable via
  `POST /api/knowledge-bases` and `KnowledgeBase._validate_id` allows up to
  **64 characters** — the same as `_TOOL_NAME_MAX_LEN` — so "widen by taking
  more of `kb_id`" can grow unboundedly and blow the name budget that AC-8
  already truncated against. **The discriminator is therefore always a
  fixed-length hash**: `sha256(kb_id)`'s first 8 hex characters. Its length
  is known before truncation, so AC-8 can reserve for it exactly. If two
  members of a collision group somehow share those 8 characters, the hash
  length steps up by a fixed increment (8 → 12 → 16), each step still a known
  length reserved in the same way — never character-by-character growth of
  `kb_id`.
- [x] **AC-10** Over-length **and** colliding compose to **one** discriminator
  applied once, with its budget reserved **before** the slug is truncated:
  reserve `len(discriminator)`, truncate the slug to what remains under
  `kb__` + `__search` + the reserved discriminator, append once, then assert
  uniqueness across the agent's whole set. Never two suffixes, and never a
  name that exceeds 64 after widening.
- [x] **AC-10b** **The compound test**, which the earlier AC-9 case would not
  have tripped: two knowledge bases whose `name` is long enough to require
  AC-8 truncation **and** whose `kb_id`s share a 6+ character prefix. Assert
  both names are unique, both are ≤ 64 characters, and both are stable under
  a reordered `kb_ids`.

### `KBToolProvider` (DD-5)

- [x] **AC-11** `the_one/knowledge/tool_provider.py::KBToolProvider.get_tools_for_agent(config, *, agent_name) -> list[Tool]`.
  **Not** a `the_one/tools/provider.py::ToolProvider` Protocol implementer —
  that Protocol is synchronous and per-tool-name keyed; this is async and
  per-entity keyed. Sibling shape to `MCPToolProvider`.
- [x] **AC-12** Empty `config.kb_ids` → `[]` with **no database call**
  (verified by a repo stub that raises).
- [x] **AC-13** A `kb_id` that no longer exists → WARNING naming the agent and
  the id, skip that one, keep the rest (the orphan-source precedent).
- [x] **AC-14** Constructor-injected into `AgentFactory` like `mcp_provider`,
  so `tests/test_factory.py` has a seam to substitute at. The import in
  `factory.py` is **lazy** (inside the method), per the cycle
  `agent.__init__ → agent.factory → db.repositories → agent.config → agent.__init__`
  that `_build_source_index`'s docstring records.

### Factory wiring (DD-5)

- [x] **AC-15** `AgentFactory.create` calls
  `kb_tools = await self.kb_provider.get_tools_for_agent(config, agent_name=name)`
  and registers the returned tools **immediately after the MCP block**,
  behind the same filter:
  `if tool.name not in disabled_names and config.is_tool_enabled(tool.name)`.
  **No ordering constraint relative to `SearchTools`** — DD-7's amendment
  removed the `source_index` entries that created one.
- [x] **AC-16** The call is guarded `if self.kb_provider is not None`,
  mirroring the established idiom at the MCP block, even though AC-12 makes
  it unnecessary for correctness — `tests/test_factory.py` and
  `tests/test_mcp_tool_provider.py` both pass `mcp_provider=None` as if it
  mattered, so the structural symmetry is what a reader expects here.
- [x] **AC-17** Registering the knowledge-base tools last does **not** make
  them shadow-proof — `ToolRegistry.register` is `self._tools[name] = tool`,
  last-write-wins. Collision is impossible because of the `kb__` prefix, and
  the code comment says **that**, not the inverted ordering claim.

### Discovery (DD-7, as amended)

- [x] **AC-18** `_format_result` gains a `kb__` branch in its **prefix parse**
  (beside the existing `_MCP_PREFIX` branch), rendering `kb:{slug}: …`.
  `_format_result(matches, query, *, total=None)` never sees `source_index`,
  so the group label comes from the tool name and nowhere else.
- [x] **AC-19** **No `source_index` entry is created for a knowledge base**
  (DD-7 as amended). A knowledge base has exactly one tool, so source-level
  en-bloc selection is degenerate — the per-tool path already finds it by the
  same text. A comment at the `kb__` branch records this, so a later reader
  does not "restore" the missing entry by symmetry with MCP.
- [x] **AC-20** `tests/test_search_tools.py`: a query matching the knowledge
  base's **description** (not its tool name) returns the tool, via the
  per-tool matching path. A second test asserts the rendered group label is
  `kb:{slug}:`.
- [x] **AC-21** A test pins the normalized-segment behaviour, including the
  recorded case where a slug itself contains `__` (`"My  Notes"` →
  `My__Notes` → `kb__My__Notes__search`, whose `split("__", 2)[1]` is `My`).
  Same latent flaw as the MCP path; recorded, not fixed.

### Result format (DD-8)

- [x] **AC-24** One header line naming the knowledge base, the query and the
  hit count; then per hit a citation line
  `[n] {path} #{seq} ({char_start}-{char_end})` followed by the chunk text.
- [x] **AC-25** The citation resolves the **chunk's own `item_id`**, never a
  `parent_id` — a registered folder and each walked file are both items, and
  the operator-meaningful path is the file's. The behavior spec's step 5
  asserts the child file's path, so this is a pinned contract.
- [x] **AC-26** No hits → one sentence naming the knowledge base and the
  query, never an empty string.
- [x] **AC-27** Degraded → one line above the hits carrying
  `SearchResult.degraded` **verbatim**, with the accompanying sentence
  depending on **which side** degraded: `semantic index rebuilding` /
  `semantic index busy` / `semantic index unavailable` are keyword-only
  results; `keyword index unavailable` is the reverse — those are *semantic*
  results, and "these are keyword results" there is backwards.
- [x] **AC-28** No per-hit text cap and no total cap in the tool. A comment
  records that the context governor already bounds tool results with
  `truncation_direction = "head"` — the right end, since hits are best-first —
  and that it **will** truncate on a small-context model, so "~20 KB" is a
  worst case and not a delivery guarantee.

### Isolation and the gate

- [x] **AC-29** `tests/test_factory.py`: an agent with `kb_ids=[kb_id]` has
  exactly one `kb__{slug}__search` in its registry; an agent with empty
  `kb_ids` has none; two agents with different attachments do not see each
  other's.
- [x] **AC-30** The factory-level DD-6 regression: an agent whose
  `enabled_tools` is a narrow built-in list **keeps** its `kb__` tool, and
  `disabled_tools=["kb__{slug}__search"]` still removes exactly that one.
  (The unit-level gate tests landed in Leg 1; this proves it end to end with
  a real tool registered.)

### Documentation

- [x] **AC-31** `the_one/agent/config.py::BASE_PROMPT` — it currently tells
  the model the catalog covers "BOTH built-in tools … AND tools from any MCP
  servers" and that results group as `built-in:` / `mcp:<server>:`. A third
  group makes the model's own instructions factually wrong about its own
  catalog; widen both sentences.
- [x] **AC-32** `CLAUDE.md`'s Knowledge bases paragraph gains the
  agent-facing half.
- [x] **AC-33** `the_one/agents.md` gains a Knowledge retrieval section and
  the `kb__` prefix rule beside the existing tool-registry material.
- [x] **AC-33b** `the_one/tools/_search_tools.py`'s module docstring, which
  currently describes only the built-in/MCP two-source shape, gains a line
  naming the `kb__` group — for a reader who never reaches `agents.md`.
- [x] **AC-34** `SECURITY-MODEL.md`'s Knowledge-base indexing bullet gains
  the **attachment-is-authorization** statement: an agent can reach exactly
  the knowledge bases the operator attached, the tool instance carries the
  `kb_id` so it is not an argument the model can forge, and there is no
  agent-facing route that creates or attaches one.

## Verification

```bash
PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_tool_provider.py tests/test_factory.py tests/test_search_tools.py -x --timeout 60
make test-unit
make lint
```

- AC-20's discovery test must use a query that matches the knowledge base's
  description and **not** its tool name, so it exercises description
  matching rather than trivially hitting the name.
- Pair every pytest run with `-x --timeout`; never `-m live`; never port 8484
  or the operator's default data directory.

## Citation Audit

Verified against the working tree with Leg 1 applied:

| Citation | Status |
|---|---|
| `factory.py` — `source_index` built only `if config.mcp_source_ids and self.mcp_provider is not None`, then `registry.register(SearchTools(..., source_index=source_index, ...))`; MCP block after the built-in provider loop, same `disabled_names` + `is_tool_enabled` filter | verified |
| `_search_tools.py::_format_result(matches, query, *, total=None)` — groups by `name.startswith(_MCP_PREFIX)` then `name.split("__", 2)[1]`; never reads `source_index` | verified |
| `_search_tools.py::_filter_candidates` — source-level matches union `tool_names_prefixed` with per-tool matches; a tool found only source-side is description-only; score is `max(source, per_tool)` | verified — and this is what establishes that a one-tool source_index entry is degenerate (DD-7 amendment) |
| `SearchTools.__init__` — `self._source_index = source_index or {}` (empty dict is falsy → fresh dict) | verified; **no longer reachable as a defect** after the DD-7 amendment, since no knowledge-base entry is written |
| `agent/core.py::Agent._execute_tool` — calls `tool.execute(**args)` with no schema validation; wraps a raised exception as `[error] Tool execution failed: {e}` | verified |
| `mcp/_tool.py::MCPClientTool.__init__` — instance attrs before `super().__init__`, `_TOOL_NAME_MAX_LEN` enforced by raising `MCPRegistrationError`, `agent_name` passed through | verified |
| `agent/config.py::BASE_PROMPT` — names both the two-source catalog and the `built-in:` / `mcp:<server>:` group labels | verified |
| `api.py::create_knowledge_base` — `if "id" not in data: data["id"] = uuid.uuid4().hex[:12]`, so `kb_id` is client-supplyable | verified |
| `agent/config.py::UNGATED_TOOL_PREFIXES` — present and containing `"kb__"` (Leg 1) | verified |

## Post-Completion Checklist

- [x] All acceptance criteria checked off
- [x] Leg status → `landed` (implementation complete; flight-end review still owes `completed`)
- [x] Leg checked off in `flight.md`
- [x] Flight log updated with outcomes, deviations and anomalies
