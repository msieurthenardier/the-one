# Leg: tool-name-integrity

**Status**: landed
**Flight**: [Studio Surfaces](../flight.md)

## Objective

Make a knowledge base's derived tool name a function of `(kb.name, kb.id)`
alone — independent of the agent's attached set — and give the one remaining
name-moving event, rename, a rewrite that keeps `disabled_tools` entries
pointing at the tool the operator disabled.

## Context

This is the flight's **highest-risk leg** and its only cross-entity write. It is
server-side only: no UI, no JavaScript. The attach tab that consumes this leg's
new response field is Leg 3.

**Design decisions implemented**: DD-17 (unconditional discriminator), DD-3's
**read path only** (`{kb_id: tool_name}` on the agent response — the row
rendering is Leg 3), DD-4's **server half** (`kb_ids` keep-on-omit), DD-5
(rename rewrites `disabled_tools` across attached agents).

**Why DD-17 exists** (Architect cycle 3, operator decision): today
`_compute_tool_names` applies the discriminator only when a slug collides within
the agent's attached set or overflows 64 characters. That makes a derived name a
function of the **whole set**, so a name-keyed `disabled_tools` entry goes stale
— and the tool silently **re-enables** — on four distinct events: rename, a
delete that resolves a collision, an **attach** that creates one, and a
**detach** that resolves one. Cases 3 and 4 arrive through the attach tab Leg 3
introduces. Applying the discriminator unconditionally deletes three of the four
cases rather than defending them. Only rename remains, because the name is an
input to it.

**What this leg does NOT do**:

- No UI, no `studio.js`, no `knowledge-tab.js`. DD-13's union and DD-4's client
  half are Leg 3.
- **No rename affordance.** This leg makes rename *safe*; Leg 3 makes it
  *reachable*. `PUT /api/knowledge-bases/{kb_id}` already accepts `name` — that
  is the path this leg hardens.
- No `enabled_tools` rewrite. See AC-9.
- No data migration. No install holds a name-keyed `kb__` entry (Flight 5 landed
  one day ago onto a mission branch never merged to `main`), and the flight's
  Divert trigger fires if that turns out to be false.

**Prior-leg learnings**: Leg 1 landed the inventory and the search route; `make
test-unit` was green at 4740 passed. Leg 1 touched none of this leg's files
except `api.py`, and in a disjoint region (the knowledge-base routes, not the
agent routes).

## Inputs

- `the_one/knowledge/tool_provider.py` — `_compute_tool_names`,
  `_build_name`, `_discriminator`, `_normalize_kb_name`, `_TOOL_NAME_MAX_LEN`
  (64), `_NAME_PREFIX` (`kb__`), `_NAME_SUFFIX` (`__search`), `_FIXED_OVERHEAD`
  (12), `_HASH_LENGTHS` ((8, 12, 16)). Sole production caller:
  `KBToolProvider.get_tools_for_agent`.
- `tests/test_kb_tool_provider.py::TestComputeToolNames` — nine tests Flight 5
  landed; two of them pin the behaviour DD-17 inverts.
- `the_one/interfaces/web/api.py` — `_agent_response(cfg)` (sync, five call
  sites), `update_agent` (with its `mcp_overrides` and
  `self_revision_requires_approval` preserves), `update_knowledge_base`
  (`merged = existing.model_dump(); merged.update(data)`).
- `the_one/db/repositories.py::SQLiteAgentStore` — `list_by_provider` (the
  structural precedent for a scoped query), `load`, `save`. `agents.kb_ids` is
  `TEXT DEFAULT '[]'` holding a JSON array (`schema.py:58`, `:169`).
- `the_one/db/_write_lock.py::write_transaction` — raises on re-entry by the
  same task.
- `the_one/agent/config.py` — `UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")`;
  `is_tool_enabled` checks `disabled_tools` as a universal exact-name blacklist
  *after* the ungated-prefix gate.

## Outputs

- `the_one/knowledge/tool_provider.py` — unconditional discriminator; public
  `compute_tool_names`.
- `the_one/knowledge/kb_rename.py` (NEW, or an equivalently-placed helper in
  `the_one/knowledge/`) — DD-5's rewrite. **Must live under
  `the_one/knowledge/`**, so the web layer never imports an underscore-private
  symbol across a package boundary, and so Flight 7's `the_one/tools/naming.py`
  refactor inherits a known caller set.
- `the_one/db/repositories.py` — `SQLiteAgentStore.list_by_kb`.
- `the_one/interfaces/web/api.py` — `kb_tool_names` on the single-agent
  responses; `kb_ids` keep-on-omit in `update_agent`; the rename rewrite hooked
  into `update_knowledge_base`.
- `tests/test_kb_tool_provider.py` — two tests **renamed and inverted in
  place**, new DD-17 invariance tests.
- `tests/test_db_api.py` — `kb_ids` preserve, `kb_tool_names` field, rename
  rewrite end-to-end.
- New or extended repository tests for `list_by_kb`.
- `tests/behavior/kb-agent-query-round-trip.md` — re-authored per L2-D10. Its
  **run log under `runs/` is explicitly not touched.**

## Leg Design Decisions

**L2-D1 — The discriminator becomes unconditional, but the WARNING logs do
not.** In `_compute_tool_names`, `hash_len_by_id[kb.id]` is always
`_HASH_LENGTHS[0]`; the `over_length or colliding` condition disappears from
what is *applied*. It must **remain** as what is *logged*: the "name is too
long, truncating" and "collide on tool-name slug" warnings still fire only in
their own cases. Collapsing the two conditions into one would either spam a
warning for every ordinary knowledge base or silently drop the truncation
warning — and `tests/test_kb_tool_provider.py` asserts both messages.

**L2-D2 — `_build_name`'s `hash_len is None` branch stays, and its docstring is
corrected.** After L2-D1 nothing in `_compute_tool_names` passes `None`, so the
branch becomes unreachable from production. Keep it — `_build_name` is a pure
function with a documented contract and the widening loop still passes explicit
lengths — but its docstring currently says the `None` case is "only reachable
when the slug is both short enough and non-colliding", which becomes false.
Rewrite that sentence rather than leaving a comment that lies.

**L2-D3 — The slug budget is 43 characters, and that is arithmetic, not a
constant to introduce.** `_build_name` computes `max_slug_len =
_TOOL_NAME_MAX_LEN - _FIXED_OVERHEAD - reserved` = `64 - 12 - 9` = **43**
(`reserved` is `len(disc) + 1` = 9 at the 8-character discriminator). Do **not**
add a `43` literal anywhere; DD-16's operator-facing hint in Leg 3 is a separate
advisory number. This leg's job is to make the existing arithmetic yield 43,
which it already does once the discriminator is unconditional.

**L2-D4 — THREE assertions pin the inverted behaviour, in TWO different test
classes, and all are edited in place.** A repo-wide sweep for
`kb__<name>__search` literals returns about twenty hits; only three of them are
**derived** names. The distinction is the whole of this decision, because a
Developer sweeping for `kb__` will otherwise "fix" tests that are not broken.

**Must change — the name is produced by `_compute_tool_names`:**

| Location | Assertion |
|---|---|
| `tests/test_kb_tool_provider.py::TestComputeToolNames::test_single_short_name_no_discriminator` | `names == {"kb1": "kb__Docs__search"}` |
| `::TestComputeToolNames::test_two_distinct_short_names_no_discriminator` | `names["kb1"] == "kb__Docs__search"`, `names["kb2"] == "kb__Runbooks__search"` |
| `tests/test_kb_tool_provider.py::TestKBToolProvider::test_happy_path_builds_tool_per_kb` (a **different class**, ~line 279) | `{t.name for t in tools} == {"kb__Docs__search", "kb__Runbooks__search"}` — it drives the real `KBToolProvider.get_tools_for_agent`, not a stub |

**Must NOT change — the literal is an input, not an output.** These hand a
made-up `kb__…__search` string to a stub, a mock or a prefix check; nothing
derives it, so DD-17 cannot move it:

- `tests/test_factory_disable_enforcement.py` — `StubTool("kb__docs__search", …)`
- `tests/test_search_tools.py` — `_MockTool("kb__docs__search", …)` and its
  `kb:docs:` group-label assertions
- `tests/test_config.py` — `cfg.is_tool_enabled("kb__docs__search")` and
  `disabled_tools=["kb__x__search"]`, exercising the prefix gate
- `tests/test_kb_tool_provider.py` (~line 322) — a `KBSearchTool` constructed
  directly with an explicit `name=`
- `tests/test_factory.py::TestKBToolWiring` — a hand-rolled `StubKBProvider`
  substituted for the real provider at `factory.kb_provider`, building
  `KBSearchTool(name=f"kb__{kb_id}__search", …)` and asserting on those literals
  (`kb__kb1__search`, `kb__kb-a__search`, …). It never reaches
  `compute_tool_names`.

**Treat the list as a worked example of a rule, not as an exhaustive
enumeration.** The rule: *is this literal produced by `compute_tool_names`, or
handed in as an input?* Produced → it moves under DD-17 and must be updated.
Handed in → DD-17 cannot reach it and touching it silently weakens an unrelated
test. If the sweep turns up a sixth file this list does not name, classify it
with that rule rather than coming back for a ruling — and say so in the flight-log
entry so the next sweep starts from a longer list.

**Rename and invert in place — never delete and re-add**, so `git blame` records
the intent shift rather than showing new tests appearing from nowhere. Suggested
names for the first two: `test_single_short_name_still_gets_a_discriminator`,
`test_two_distinct_short_names_each_get_their_own_discriminator`; the third keeps
its name (its subject is still the happy path) and only its expected set moves.
The remaining seven `TestComputeToolNames` tests should pass unchanged; if one does
not, that is a finding to report, not a test to adjust.

**L2-D5 — `kb_tool_names` is served only by the single-agent responses.**
`_agent_response(cfg)` is synchronous and takes only the config, but the map
needs each `KnowledgeBase` row to derive a slug — an async repository read. So:
`_agent_response` gains an optional `kb_tool_names: dict[str, str] | None =
None` parameter, and the routes that serve the agent editor resolve it and pass
it. **The list route (`api.py:670`, inside a loop over every agent) does not** —
it would be an N+1 read per page load and the tile grid has no use for it.
Consequence to write down: a client must read `kb_tool_names` from the
single-agent fetch, never from the list. Resolve the ids exactly as
`KBToolProvider.get_tools_for_agent` does — `repo.get(kb_id)` per id, skipping a
`KeyError` with a WARNING — so a dangling id (DD-14) simply has no entry rather
than raising.

**L2-D6 — `list_by_kb` uses `json_each`, and that is not optional.**
`agents.kb_ids` is a JSON TEXT column, so `list_by_provider`'s plain column
equality does not transfer. `LIKE '%<id>%'` is **wrong** — it matches an id that
is a substring of another id. Use:

```sql
SELECT name FROM agents
WHERE EXISTS (SELECT 1 FROM json_each(agents.kb_ids) WHERE json_each.value = ?)
ORDER BY name
```

**Guard the column the way the read path already does.** Measured on this
host's SQLite (3.45.1): `json_each(NULL)` yields zero rows and is **safe**, but
`json_each('')` raises `OperationalError: malformed JSON`. The schema puts no
`NOT NULL` on `kb_ids`, and `_row_to_config` already defends both cases with
`json.loads(row["kb_ids"] or "[]")` — so the codebase does not treat the state as
impossible. Match that convention:

```sql
SELECT name FROM agents
WHERE kb_ids IS NOT NULL AND kb_ids != ''
  AND EXISTS (SELECT 1 FROM json_each(agents.kb_ids) WHERE json_each.value = ?)
ORDER BY name
```

JSON1 is already relied on elsewhere in `schema.py` — via `json_extract` rather
than `json_each`, but both are the same extension, so availability is settled
and only the function differs.

**L2-D7 — Rename ordering: compute both names in memory, then rename, then
rewrite.** `write_transaction` raises on re-entry by the same task, so the
knowledge-base update and the agent saves **cannot** be one atomic unit. The
order is forced and the reverse is a bug:

1. Load `existing` (already done by `update_knowledge_base`). Compute the old
   derived name from `existing.name` and the new one from the incoming name —
   both in memory, both depending only on `(name, kb_id)`, which is exactly what
   DD-17 guarantees and what makes this safe to do before the write.
2. Write the knowledge-base row.
3. For each agent from `list_by_kb(kb_id)`: `store.load`, replace the single
   `disabled_tools` entry equal to the old name with the new name, `store.save`.
   An agent with no matching entry is **not** saved at all.

**Each agent's load + replace + save is individually wrapped in
`try/except Exception`**, which logs a WARNING naming that agent and the
exception and then **continues to the next agent**. Nothing propagates past the
helper. This is stated at the same rigour as L2-D1's warn-vs-apply split because
the naive implementation — a plain `for` loop — violates AC-12 directly: one
agent's `save` failing (an encryptor round-trip, a constraint) would propagate
out through `update_knowledge_base` and surface as an unhandled 500, after the
rename has already committed.

A failure part-way leaves later agents unrewritten, which **fails open**. That
is a stated limitation, not an oversight: each unrewritten agent is named in a
WARNING log so the condition is diagnosable.

**L2-D8 — The rewrite goes through the store, never a raw `UPDATE`.**
`SQLiteAgentStore.load`/`save` decrypt and re-encrypt `mcp_overrides`
credentials on the round trip. A targeted `UPDATE agents SET disabled_tools = ?`
would be faster and would bypass the encryptor. **Do not write one.** Note that
the v7 schema migration — cited by DD-5 as the precedent for *rewriting tool
names across agents* — does use raw SQL; it is a migration running before the
encryptor exists, and its shape does not transfer here.

**L2-D9 — Nothing is done when the name is unchanged.** `update_knowledge_base`
accepts a full merged body, so a PUT that changes only, say, a description still
arrives with `name` present. Compare `existing.name` to the validated new name
and return early if equal — otherwise every knowledge-base PUT would load and
re-save every attached agent for nothing.

**A second early return sits behind it, on the derived names.** Two different raw
names can normalize to the same slug (`My Notes` and `My/Notes` both →
`My_Notes`), so the raw names differ while the derived tool name does not. Once
both derived names are computed (L2-D7 step 1), compare them too and return
before touching any agent when they are equal. Deciding it there — rather than
per agent inside the loop — keeps AC-8's "an agent with no matching entry is not
re-saved" about matching, and stops a no-op rename from loading every attached
agent to discover it had nothing to do.

**L2-D10 — Flight 5's behavior spec is re-authored by this leg, and its run log
is not touched.** `tests/behavior/kb-agent-query-round-trip.md` hardcodes the
**undiscriminated** literal `kb__KBQ-test__search` in six places (steps 3, 5, 6,
7, 8 and 9). Under DD-17 a knowledge base named `KBQ-test` derives
`kb__KBQ-test_<8 hex>__search`, so every scripted mock tool call in that spec
would name a tool the agent does not have, and a re-run would fail end to end
with "Unknown tool" — reporting a Flight 5 regression that did not happen. A
regression net that fails for a spec reason is worse than no net, because it
trains the reader to discount it.

- **This leg owns the re-author**, on DD-5's own principle: the change that
  breaks a contract owns the consequence. DD-18 says the same thing from the
  other side — a change to a contract a behavior spec pins is a deliberate spec
  re-author, not an inline edit.
- **Do not substitute a discriminated literal.** A hardcoded
  `kb__KBQ-test_a3f19c2e__search` rots the same way and encodes a hash no reader
  can verify by eye. Use the pattern this flight's own
  `kb-studio-round-trip.md` step 12 already establishes: **read the derived
  name, never compute it** — from `GET /api/agents/kbq-attached`'s
  `kb_tool_names`, the field AC-6 adds.
- **This is a step-table restructure, not an inline substitution, because the
  spec's own ordering forbids the obvious fix.** Verified: step 2 creates the
  knowledge base, **step 3 creates the mock provider carrying the scripted
  `tool_calls[0]["name"]`**, and **step 4 is the first point an agent exists**.
  `kb_tool_names` is served only by single-agent routes (L2-D5), so at step 3
  `GET /api/agents/kbq-attached` 404s — and the dependency is circular, since
  step 4's agents need the `provider_id` step 3 creates. The restructure, which
  needs **no renumbering** because step 4 already performs
  `GET /api/agents/kbq-attached`:
  1. **Step 3** creates the provider with a **placeholder** scripted call — any
     name; it is never driven before step 5.
  2. **Step 4**, after creating both agents, reads `kb_tool_names` from the
     `GET /api/agents/kbq-attached` it already issues, records the derived name,
     and `PUT /api/providers/{provider_id}` installs it as the scripted
     `tool_calls[0]["name"]`. Its Expected Result gains an assertion that the
     recorded name matches `kb__KBQ-test_…__search`.
  3. **Steps 5–9** refer to "the derived tool name recorded in step 4" instead
     of the literal. Step 7's restore-the-script PUT uses the same recorded
     value.
  The provider-reshaping `PUT` is not novel apparatus — **step 6 already does
  exactly that** twice to re-script the mock mid-run.
- **The tool name is not the spec's only Flight-6-invalidated assumption.**
  Step 8's parenthetical states, as a hazard to avoid: *"Omitting `kb_ids` sets
  it to `[]`, silently detaching the knowledge base, and this step would then
  fail looking like a whitelist regression."* That is the **pre-leg** behaviour;
  **AC-7 eliminates it.** Nothing breaks mechanically — the step resends
  `kb_ids` explicitly, and an explicit array is never an omission — but the
  sentence becomes a false statement about the shipped API, sitting inside a
  document whose job is to be a source of truth. Correct it to describe the
  post-AC-7 world, and **keep the explicit resend**, saying why: it keeps step
  9's readback able to distinguish "the blacklist worked" from "`kb_ids` was
  wiped", which stays worth asserting even once the wipe path is gone. Check
  step 9's parenthetical for the same assumption while there.
- **`tests/behavior/kb-agent-query-round-trip/runs/2026-09-17-22-08-29.md` is
  NOT edited.** A run log is historical evidence of what a past run observed;
  rewriting it would falsify the record. Its literals are correct *for the run
  that happened*.

## Acceptance Criteria

- [x] AC-1 — `_compute_tool_names` applies the `sha256(kb_id)[:8]` discriminator
      to **every** knowledge base. A single knowledge base named `Docs` with id
      `kb1` yields `kb__Docs_<8 hex>__search`, not `kb__Docs__search`.
- [x] AC-2 — A knowledge base's derived name is **unchanged** by the composition
      of the set it is computed with. Pinned by a test that computes the name for
      `[A]`, then for `[A, B]` where `B` has the same name as `A`, then for
      `[A, C]` where `C` does not, and asserts `A`'s name is identical in all
      three. This is DD-17's whole point and the invariant the behavior test's
      steps 16–17 exercise from the outside.
- [x] AC-3 — The over-length and collision **WARNING logs still fire only in
      their own cases** (L2-D1): an ordinary short, non-colliding name produces
      neither, while an over-length name still logs "too long" and a colliding
      pair still logs "collide".
- [x] AC-4 — Every derived name is still ≤ 64 characters, the discriminator is
      still applied at most once per name, and the widening loop (8→12→16) still
      resolves a forced discriminator collision. The seven Flight 5 tests that do
      not pin the inverted behaviour pass **unchanged**.
- [x] AC-5 — `compute_tool_names` is public (no leading underscore) and is what
      `api.py` imports. No underscore-private symbol from `the_one/knowledge/`
      is imported by `the_one/interfaces/`.
- [x] AC-6 — `GET /api/agents/{name}` returns `kb_tool_names` as
      `{kb_id: tool_name}` covering exactly the agent's resolvable `kb_ids`; a
      dangling id contributes no entry and raises nothing. **All four
      single-agent routes carry it, named explicitly so none is skipped**:
      `GET /api/agents/{name}`, `POST /api/agents` (create),
      `PUT /api/agents/{name}`, and `POST /api/agents/{name}/rename`.
      `GET /api/agents` (the list) does **not** (L2-D5).
- [x] AC-7 — `PUT /api/agents/{name}` with `kb_ids` **omitted** preserves the
      stored value, mirroring the `self_revision_requires_approval` preserve.
      A PUT with `kb_ids: []` present still clears it — omission and empty are
      distinguishable and mean different things.
- [x] AC-8 — Renaming a knowledge base via `PUT /api/knowledge-bases/{kb_id}`
      rewrites, for every agent whose `kb_ids` contains it, the `disabled_tools`
      entry equal to the old derived name into the new derived name. Entries
      matching nothing are left untouched, and an agent with no matching entry is
      not re-saved.
- [x] AC-9 — **`enabled_tools` is not touched.** `kb__` is in
      `UNGATED_TOOL_PREFIXES`, so `is_tool_enabled` never consults
      `enabled_tools` for a `kb__` name and an entry there is inert. The v7
      precedent rewrites both columns; this deliberately does not. Pinned by a
      test that puts a `kb__` name in `enabled_tools` and asserts a rename leaves
      it alone.
- [x] AC-10 — A knowledge-base PUT performs no agent reads or writes in **either**
      early-return case (L2-D9): the raw `name` field unchanged, **and** a raw
      name that changes but normalizes to the same derived tool name (`My Notes`
      → `My/Notes`, both slugging to `My_Notes`). Both need their own test; a
      test covering only the literal-unchanged case does not satisfy this.
- [x] AC-11 — `SQLiteAgentStore.list_by_kb(kb_id)` returns the names of exactly
      the agents whose `kb_ids` contains that id, ordered by name. Pinned by a
      test including **an id that is a substring of another agent's attached id**
      — the case a `LIKE` implementation gets wrong.
- [x] AC-12 — A rename that fails part-way through the agent rewrites leaves the
      knowledge base renamed, logs a WARNING **naming each unrewritten agent**,
      and does not raise to the caller.
- [x] AC-13 — `tests/behavior/kb-agent-query-round-trip.md` contains **no
      hardcoded derived tool name**, and its step 8/9 parentheticals no longer
      describe the pre-AC-7 omit-wipes behaviour. Verifiable: `grep -n
      "kb__KBQ-test" ` over the spec returns only `kb:KBQ-test:` group-label
      references (derived from the knowledge base's *name*, not its tool name,
      so unaffected by DD-17). Every step needing the tool name refers to the
      value recorded in step 4.
- [x] AC-14 — The run log under
      `tests/behavior/kb-agent-query-round-trip/runs/` is **unmodified**
      (`git status` shows it untouched).
- [x] AC-15 — `make lint` clean and `make test-unit` green, with the two renamed
      tests present under their new names and **no test deleted and re-added**
      (verifiable in the diff: the file shows renames and body edits, not a block
      removal plus a block addition).

## Verification Steps

- AC-1 through AC-4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_kb_tool_provider.py -x --timeout 30`.
- AC-2 specifically: the new set-invariance test described in the criterion.
- AC-5: `grep -rn "from the_one.knowledge import\|from the_one.knowledge\."
  the_one/interfaces/` shows no underscore-prefixed import.
- AC-6, AC-7, AC-8, AC-9, AC-10, AC-12: `PYTHON=.venv/bin/python bash
  scripts/run-tests.sh tests/test_db_api.py -x --timeout 30`.
- AC-11: the repository test module covering `SQLiteAgentStore`.
- AC-13, AC-14: `grep -n "kb__" tests/behavior/kb-agent-query-round-trip.md`
  and `git status tests/behavior/kb-agent-query-round-trip/`.
- AC-15: `make lint`; then `make test-unit` verbatim, alone, in the foreground;
  then `git diff tests/test_kb_tool_provider.py` read by eye to confirm the
  three assertions were edited in place and no test block was removed and
  re-added.

## Implementation Guidance

1. **`_compute_tool_names` first, with its tests.** Make the discriminator
   unconditional (L2-D1), keeping the two warning conditions as logging-only
   guards. Rename and invert the two tests in place (L2-D4), then add AC-2's
   set-invariance test. Run the file. Expect the other seven to pass untouched;
   if one does not, stop and report rather than adjusting it.
2. **Promote to `compute_tool_names`** and update the sole production caller
   (`KBToolProvider.get_tools_for_agent`) and the test module's import. Correct
   `_build_name`'s stale docstring sentence (L2-D2).
3. **`SQLiteAgentStore.list_by_kb`** with the `json_each` query (L2-D6), beside
   `list_by_provider`. Test it, including the substring case.
4. **The rename helper** in `the_one/knowledge/`. Give it the store, the kb id,
   the old name and the new name; have it do steps 2–3 of L2-D7's ordering and
   return the list of agents it could not rewrite. Unit-test it directly — this
   is the seam `list_by_kb` exists to provide.
5. **Wire it into `update_knowledge_base`** with L2-D9's early return, after the
   repository update has committed.
6. **`kb_ids` keep-on-omit** in `update_agent`, immediately alongside the
   `self_revision_requires_approval` preserve it mirrors.
7. **`kb_tool_names`** last (L2-D5): optional parameter on `_agent_response`,
   resolved by the single-agent routes only.
8. **Re-author `tests/behavior/kb-agent-query-round-trip.md`** per L2-D10, once
   `kb_tool_names` exists to read from. Leave its run log alone.
9. **Gates**: targeted files, then `make lint`, then `make test-unit` verbatim.

## Edge Cases

- **A rename to a name that normalizes to the same slug** (`My Notes` →
  `My/Notes`, both normalizing to `My_Notes`): the derived name does not change.
  The rewrite finds old == new and must be a no-op, not a self-assignment loop.
- **Two attached knowledge bases whose names collide** — still legal, still both
  discriminated, and now discriminated *identically to how they would be alone*.
  That is AC-2.
- **An agent with the same derived name in `disabled_tools` twice** (possible via
  the API): replace all occurrences, or de-duplicate. Either is acceptable;
  silently keeping one stale copy is not.
- **A dangling `kb_id`** (DD-14): contributes no `kb_tool_names` entry, is
  skipped with a WARNING, and must not make the whole response fail.
- **`kb_ids` omitted AND `mcp_overrides` omitted in the same PUT** — both
  preserves must apply; they are independent and neither may clobber the other.
- **An agent attached to the renamed knowledge base with `disabled_tools` NULL or
  empty** — `list_by_kb` returns it, and it must not be re-saved (AC-8).
- **The rename happens while an agent holds a live session.** Per DD-5, rename
  inherits the session-bound attachment contract: the running agent keeps its old
  tool name until the next build. This leg does not try to make rename
  retroactive, and the HAT walks that deliberately (DD-18).

## Citation Audit

Verified against the working tree on `flight/06-studio-surfaces` at the Leg 1
tip (Leg 1 uncommitted; its changes do not touch any symbol below except
`api.py`, in a disjoint region).

| Citation | Status |
|---|---|
| `knowledge/tool_provider.py::_compute_tool_names` — `over_length = len(raw_name) > _TOOL_NAME_MAX_LEN`, `colliding = len(slug_members[slug]) > 1`, `if over_length or colliding: hash_len_by_id[kb.id] = _HASH_LENGTHS[0]` … `else: hash_len_by_id[kb.id] = None` (DD-17's target) | verified |
| `knowledge/tool_provider.py::_compute_tool_names` — the two WARNING logs are nested inside `if over_length:` / `if colliding:` separately (L2-D1's logging-vs-applying split) | verified |
| `knowledge/tool_provider.py::_build_name` — `reserved = len(disc) + 1`; `max_slug_len = max(_TOOL_NAME_MAX_LEN - _FIXED_OVERHEAD - reserved, 0)`; docstring says the `None` case is "only reachable when the slug is both short enough and non-colliding" (L2-D2, L2-D3) | verified |
| `knowledge/tool_provider.py` — `_TOOL_NAME_MAX_LEN = 64`, `_NAME_PREFIX = "kb__"`, `_NAME_SUFFIX = "__search"`, `_FIXED_OVERHEAD = 12`, `_HASH_LENGTHS = (8, 12, 16)` → `64 - 12 - 9 = 43` (L2-D3 confirms DD-16's budget) | verified |
| `knowledge/tool_provider.py::KBToolProvider.get_tools_for_agent` — the sole production caller; resolves `kb_ids` via `repo.get(kb_id)` per id, skipping `KeyError` with a WARNING, returning `[]` when none resolve (L2-D5's pattern) | verified |
| `tests/test_kb_tool_provider.py::TestComputeToolNames::test_single_short_name_no_discriminator` — asserts `names == {"kb1": "kb__Docs__search"}` (breaks under DD-17) | verified |
| `tests/test_kb_tool_provider.py::TestComputeToolNames::test_two_distinct_short_names_no_discriminator` — asserts `kb__Docs__search` / `kb__Runbooks__search` (breaks under DD-17) | verified |
| `tests/test_kb_tool_provider.py` — the other seven tests in the class assert `len(name) <= 64`, an 8-hex discriminator, reorder stability, the "too long"/"collide"/"widening" log messages; none pins an undiscriminated name (L2-D4's "should pass unchanged") | verified |
| `db/schema.py:58`, `:169` — `kb_ids TEXT DEFAULT '[]'`; `db/repositories.py:220` `json.dumps(config.kb_ids)`, `:350` `json.loads(row["kb_ids"] or "[]")` (L2-D6's JSON-column premise) | verified |
| `db/repositories.py::SQLiteAgentStore.list_by_provider` — `SELECT name FROM agents WHERE provider_config_id = ? ORDER BY name`; plain column equality, the structural precedent that does **not** transfer | verified |
| `db/_write_lock.py::write_transaction` — raises on re-entry by the same task (L2-D7's forced ordering) | verified |
| `db/repositories.py::SQLiteAgentStore.save` — takes `write_transaction` itself and round-trips through the encryptor (L2-D8) | verified |
| `interfaces/web/api.py::update_agent` — `if "self_revision_requires_approval" not in data: data[...] = existing...`, the keep-on-omit precedent AC-7 mirrors; the `mcp_overrides` preserve sits immediately above it | verified |
| `interfaces/web/api.py::_agent_response` — `def _agent_response(cfg: AgentConfig) -> dict[str, Any]`, **synchronous**, five call sites (`:670` inside the list loop, `:681`, `:797`, `:862`, `:934`) (L2-D5) | verified |
| `interfaces/web/api.py::update_knowledge_base` — `merged = existing.model_dump(); merged.update(data)` then `KnowledgeBase.model_validate(merged)`; `existing` is already loaded before the write (L2-D7 step 1, L2-D9) | verified |
| `agent/config.py:15` — `UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")`; `:182` `is_ungated = tool_name.startswith(UNGATED_TOOL_PREFIXES)`, with `disabled_tools` checked as a universal blacklist after the gate (AC-9's premise) | verified |
| `agent/config.py:120` — `kb_ids: list[str] = Field(default_factory=list)` (AC-7's shape) | verified |
| `tests/test_kb_tool_provider.py::TestKBToolProvider::test_happy_path_builds_tool_per_kb` (~:279) — drives the real `KBToolProvider.get_tools_for_agent` and asserts `{"kb__Docs__search", "kb__Runbooks__search"}`; the **third** derived-name assertion, in a second class | verified, cycle 1 |
| `tests/behavior/kb-agent-query-round-trip.md` — literal `kb__KBQ-test__search` in steps 3, 5, 6, 7, 8, 9 (L2-D10) | verified, cycle 1 |
| `tests/test_factory_disable_enforcement.py`, `tests/test_search_tools.py`, `tests/test_config.py`, `tests/test_kb_tool_provider.py:322` — every `kb__…__search` literal in these is an **input** to a stub, mock, prefix check or explicit `name=`, never a derived output (L2-D4's do-not-touch list) | verified, cycle 1 |
| SQLite 3.45.1 measured on this host: `json_each(NULL)` yields zero rows (safe); `json_each('')` raises `OperationalError: malformed JSON`; `db/repositories.py::_row_to_config` already guards with `row["kb_ids"] or "[]"` (L2-D6's guard) | verified, cycle 1 |
| `db/schema.py` — the existing JSON1 usage is `json_extract`, not `json_each`; same extension, so availability is settled (L2-D6's precision) | verified, cycle 1 |
| `tests/behavior/kb-agent-query-round-trip.md` — step 2 creates the KB, **step 3 creates the provider carrying the scripted tool name**, **step 4 is the first step an agent exists** and already issues `GET /api/agents/kbq-attached`; step 6 already re-scripts the provider by `PUT` twice (L2-D10's restructure and its no-renumbering claim) | verified, cycle 2 |
| `tests/behavior/kb-agent-query-round-trip.md` step 8 — parenthetical reads "Omitting `kb_ids` sets it to `[]`, silently detaching the knowledge base…", the pre-AC-7 behaviour this leg eliminates (L2-D10's second invalidated assumption) | verified, cycle 2 |
| `tests/test_factory.py::TestKBToolWiring` — `StubKBProvider` builds `KBSearchTool(name=f"kb__{kb_id}__search", …)` at `:356` and asserts those literals; substituted at `factory.kb_provider`, never reaching `compute_tool_names` (L2-D4's fifth do-not-touch entry) | verified, cycle 2 |
| `tests/test_kb_tool_provider.py::TestComputeToolNames` — **nine** test methods; two are renamed and inverted, leaving **seven** unchanged (corrects an internal "six" in L2-D4's own prose) | verified, cycle 2 |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`; targeted files)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do NOT commit — the flight defers review and commit to Phase 2d (honored — nothing committed)
