# Leg: notes-store-and-prompt

**Status**: completed
**Flight**: [Notes](../flight.md)

## Objective

Store per-agent notes behind an operator-owned switch (off by default), render
them into every built agent's prompt as a bounded "notes, not instructions"
block beneath the rules, and serve them to the operator over REST, with no
agent-facing tools yet (leg 2).

## Context

- Flight DDs that govern this leg:
  - **DD1:** v43, `agent_notes`, and the two `agents` columns, with
    `notes_next_number` outside `AgentConfig` and the upsert.
  - **DD2:** `notes_enabled` field, settings route, preserve-on-omit.
  - **DD4:** numbers.
  - **DD7:** origin columns and the LEFT JOIN display label.
  - **DD8:** normalisation with `" ".join(text.split())`, limits,
    de-duplication, one `write_transaction` per mutation.
  - **DD9:** `notes=None` means off, plus `RenderedNote`, `notes_present`,
    wording, case-insensitive neutralisation, `build_system_prompt` loading
    notes itself.
  - **DD11:** REST, with the settings route registered before `/{id}`.

  Read [flight.md](../flight.md) first.
- **Built on Flight 1:**
  - `the_one/agent/prompt_layers.py::build_system_prompt` (loads rules);
  - `the_one/agent/config.py::compose_system_prompt` (the `notes` keyword is
    reserved);
  - `the_one/db/_rules.py` (rules constants and renderer, placed in `db/` to
    avoid an import cycle);
  - `AgentRuleRepository` (`repositories.py:1524`), its transaction shape and
    its 0-based positions;
  - the `_rules_body` validation helper (`api.py:1318`), which never echoes
    input;
  - v42 (`schema.py:2617`).
- **Module placement (decided, following Flight 1's deviation):**
  - the notes constants, normalisation, `RenderedNote`, the renderer and the
    error types go in **`the_one/db/_notes.py`**, cycle-safe beside
    `_rules.py`;
  - leg 2 creates the `the_one/notes/` package for the tool provider and the
    tools.

  This supersedes DD8's "`the_one/notes/limits.py`" and is an allowed
  placement variation.
- The agent's own write path (tools, taint, the per-turn limit) is leg 2. This
  leg supplies the repository methods leg 2 calls: `create`,
  `update_by_agent` and `forget_by_agent`, each of which re-checks the switch
  internally.

## Inputs

- Branch `flight/02-notes` at `82a0396` (Flight 1 code plus the Flight 2 plan).
- Schema v42.

## Outputs

- v43 in `the_one/db/schema.py`, with `CURRENT_VERSION = 43`.
- `the_one/db/_notes.py`.
- `AgentNoteRepository` in `repositories.py`, and `AgentNote` in
  `the_one/db/models.py` beside `AgentRule`:
  - `untrusted` is a `bool`;
  - `untrusted_sources` is a decoded `list[str]`;
  - the listing rows also carry `origin_exists: bool` and the display
    `origin_label`.
- `AgentConfig.notes_enabled`, plus the `save` upsert and `_row_to_config`.
- `set_notes_enabled` on `SQLiteAgentStore`, a targeted `UPDATE`.
- `compose_system_prompt`'s new `notes` contract and `render_rules_block`'s
  `notes_present`.
- `build_system_prompt` loading notes.
- The REST routes.
- Tests, and `the_one/agents.md`.

## Acceptance Criteria

**Schema (DD1)**
- [ ] AC1. A fresh database and a populated v42 database both reach v43 with
      `agent_notes` (columns, CHECKs, FK `ON DELETE CASCADE ON UPDATE
      CASCADE`, `UNIQUE (agent_name, number)`), `agents.notes_enabled`
      (default 0) and `agents.notes_next_number` (default 1).
      - The ADD COLUMN steps are guarded by `PRAGMA table_info`, and the
        table and index creates are idempotent.
      - Re-running `ensure_schema` is a no-op.
      - The template-equals-replay guard passes.
- [ ] AC2. The migration test lives in `tests/test_db_migration.py`
      (`TestSchemaV43`) and covers:
      - rename carries notes (number and fields intact) and the counter;
      - delete removes them;
      - existing agents get `notes_enabled = 0`.

**Store (DD1, DD2, DD4, DD7, DD8)**
- [ ] AC3. `AgentConfig.notes_enabled: bool = False` is read by
      `_row_to_config` and written by `save`'s upsert.
      - `notes_next_number` is **not** on `AgentConfig`, not in `save`'s
        column list, and not in its `ON CONFLICT DO UPDATE` list.
      - A test saves a whole stale `AgentConfig` after notes were created and
        asserts the counter did not move back.
- [ ] AC4. `SQLiteAgentStore.set_notes_enabled(name, value)` is a targeted
      `UPDATE`, mirroring `set_self_revision_requires_approval`
      (`repositories.py:267`).
- [ ] AC5. `AgentNoteRepository(conn)` provides the methods below. Every
      mutating method uses **one** `write_transaction` and never nests (the
      Flight 1 rule).
      - `list_for_agent(name)`, ordered by `number`, returning the display
        label through a LEFT JOIN on `chat_sessions` and `origin_exists`;
      - `get(name, note_id)` and `get_by_number(name, number)`, which
        **return `None`** on a miss, like `AgentRuleRepository.get`;
      - `create(name, text, *, untrusted: bool, sources: list[str],
        origin_kind: str, origin_session_id: str | None, origin_label: str |
        None, origin_platform: str | None, origin_peer_id: str | None,
        origin_peer_name: str | None)`. It validates `origin_kind` against
        `web|connector|other` before the INSERT (a `ValueError`, never a raw
        `IntegrityError`), and then:
        - normalises the text;
        - re-checks `notes_enabled`, raising `NotesDisabledError` when it is
          off;
        - validates the per-note and total limits, raising `NoteLimitError`;
        - de-duplicates, returning the existing note with `created=False`
          rather than raising;
        - takes `number = notes_next_number`, then increments it;
        - returns `(note, created)`;
      - `update_by_agent(name, number, text, *, untrusted, sources)`, which
        re-checks the switch, normalises, and applies the limits.
        - The total check is `total - old_len + new_len`.
        - It refuses a duplicate of **another** note with
          `NoteDuplicateError`. The duplicate scan **excludes the note's own
          row**.
        - If the normalised text equals the note's current normalised text,
          it is an **allowed no-op**: nothing is written and it returns
          `changed=False`.
        - Otherwise it ORs `untrusted`, merges `sources` (deduplicated,
          capped at 10), keeps `origin_*`, and sets `updated_by='agent'`.
        - It returns `(note, changed)`;
      - `forget_by_agent(name, number)`, which re-checks the switch;
      - `update_by_operator(name, note_id, text)`, which normalises and
        applies the limits and de-duplication with the same self-exclusion,
        and the same no-op rule for identical text. It keeps the flag, sets
        `updated_by='operator'`, and has **no** switch check (DD11);
      - `delete(name, note_id)` and `clear(name) -> int`;
      - `total_chars(name, *, exclude_id=None)`, mirroring
        `AgentRuleRepository.total_chars`.

      The **mutators** (`update_*`, `forget_by_agent`, `delete`) raise
      `KeyError` on a miss. Every query is scoped by `agent_name`, so another
      agent's note is a miss, and the REST handlers map `KeyError` (or `None`
      from `get`) to 404.
- [ ] AC6. Normalisation is `" ".join(text.split())`, followed by **removing
      any remaining control characters** (Unicode category `Cc`, e.g. NUL).
      A test feeds Python string escapes (written as escapes in the test
      source): `\r\n`, U+2028, U+2029, U+0085, `\v`, `\f`, `\x1c` and
      `\x00` embedded in text, plus `"x\r\n[9] y"`. Each stores as a single
      line with no control characters. The length check uses the normalised
      text. Zero-width characters (U+200B) are left alone: neutralisation
      matches the literal `saved_notes` token, so they cannot forge a closing
      tag.
- [ ] AC7. De-duplication compares casefolded normalised text with trailing
      `.` and `!` stripped.

**Prompt (DD9)**
- [ ] AC8. `compose_system_prompt(base, persona, *, rules=(), notes=None)`:
      - `notes is None` omits the notes layer (byte-identical to Flight 1's
        output for the same rules);
      - `notes == []` renders the block with "No saved notes yet.";
      - a non-empty list renders `[n] text` lines by number, with
        `(unverified) ` after the number for untrusted notes.
      - The block wording is DD9's, verbatim, with "any rules above".
      - `RenderedNote(number, text, untrusted)` is a frozen dataclass
        **defined in `the_one/agent/config.py`**.
        `the_one/db/_notes.py` must **not** import `the_one.agent`:
        `render_notes_block` duck-types `.number`, `.text` and `.untrusted`
        (with a `TYPE_CHECKING`-only import if a type hint is wanted).
- [ ] AC9. `<saved_notes` and `</saved_notes` inside note text are neutralised
      case-insensitively, so a note containing `</SAVED_NOTES>` cannot close
      the block. A test proves it.
- [ ] AC10. When notes are present (`notes is not None`), the rules block
      gains "Rules take precedence over saved notes."
      `render_rules_block(rules, notes_present=False)` defaults to the Flight 1
      output, so existing tests pass unchanged. When notes are on but there
      are no rules, the notes layer still appears and no rules layer does.
- [ ] AC11. `build_system_prompt` loads `notes_enabled` and, when it is on, the
      notes (by number, as `RenderedNote`s), and passes `notes=None` when it
      is off or the agent has no row. The factory and the pending `next_turn`
      recompose therefore both carry notes. A test covers the pending path,
      and another covers the chat-only degraded path (which keeps the block).
- [ ] AC12. `tests/test_config.py:265` (`test_notes_are_reserved_and_ignored`)
      is rewritten for the new contract, as an intended contract change.

**REST (DD11)**
- [ ] AC13. The routes follow DD11:
      - `GET /api/agents/{name}/notes` returns `{enabled, notes, limits:
        {note_chars: 400, total_chars: 4000, writes_per_turn: 5}, usage:
        {total_chars}}`. Each note carries `id`, `number`, `text`,
        `untrusted`, `untrusted_sources`, `origin_kind`, `origin_session_id`,
        `origin_label` (the display label), `origin_exists`,
        `origin_platform`, `origin_peer_id`, `origin_peer_name`,
        `created_at`, `updated_at` and `updated_by`.
      - `PUT .../notes/settings` takes `{enabled}`, is **registered before**
        `PUT .../notes/{id}`, and returns `{enabled}`.
      - `PUT .../notes/{id}` takes `{text}` (an operator edit) and returns the
        note.
      - `DELETE .../notes/{id}` returns `{"status": "ok"}`.
      - `DELETE .../notes` returns `{deleted: n}`.
      - An unknown agent is 404. An unknown note, or another agent's note, is
        404.
      - A limit or duplicate error is 422 with a plain `detail` that never
        includes note text; type-validation 422s go through `_rules_body` or
        an equivalent.
- [ ] AC14. `update_agent` preserves the stored `notes_enabled` when the body
      omits it; `create_agent` defaults it to False. The
      `get_my_configuration` projection does not include `notes_enabled`,
      which a test pins.
- [ ] AC15. No agent-reachable tool exists yet (leg 2). No notes tool name
      appears in a built agent's registry, even with notes on.

**Gates and docs**
- [ ] AC16. `make test-unit` passes, with the skip count in the known band.
      `ruff check` and `ruff format --check` are clean.
- [ ] AC17. `the_one/agents.md` gains a "Notes store and prompt layer (M27
      F2)" section covering:
      - the schema and the counter rule;
      - the repository's methods and transaction shape;
      - normalisation and neutralisation;
      - the `notes=None`/`[]`/list contract and the wording;
      - the REST routes;
      - the known limitations: the pending fallback drops rules and notes; a
        notes-on `next_turn` recompose adds a block without tools.

## Verification Steps

- AC1-AC2: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py tests/test_schema_template.py -x --timeout 60`.
- AC3-AC7: a new `tests/test_notes_store.py`, on the schema template.
- AC8-AC12: `tests/test_config.py` and `tests/test_prompt_layers.py` (extend
  both), plus `tests/test_self_configuration_write.py` for the pending path.
- AC13-AC15: a new `tests/test_agent_notes_api.py` (authenticated client
  fixtures).
- AC16: `make test-unit`; `ruff check the_one/ tests/ scripts/`;
  `ruff format --check the_one/ tests/ scripts/`.

## Implementation Guidance

1. **v43.** Append `if version < 43:` after v42.
   - The ADD COLUMNs are guarded by `PRAGMA table_info(agents)` (the v35
     precedent).
   - `CREATE TABLE IF NOT EXISTS agent_notes` and
     `CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_notes_agent_number ON agent_notes (agent_name, number)`.
   - `INSERT OR IGNORE INTO schema_version` last, then commit.
   - `CURRENT_VERSION = 43`.
   - `tests/test_db_migration.py:5344` (`TestSchemaV42`) asserts
     `== 42 == CURRENT_VERSION`. Update it the way Flight 1 updated the v41
     assertion, as an intended change.
   - Add a v43 case that rewinds to v42 with `agent_notes` and both columns
     still present, then re-runs, proving the guards. Mirror `TestSchemaV35`:
     assert `type`, `notnull` and `dflt_value` on both new columns,
     `PRAGMA foreign_key_list(agent_notes)` (CASCADE/CASCADE), and
     `PRAGMA index_list` for the unique index.
2. **`the_one/db/_notes.py`** holds:
   - `NOTE_MAX_CHARS = 400`, `NOTES_TOTAL_MAX_CHARS = 4000`,
     `NOTE_WRITES_PER_TURN = 5`, `SOURCES_CAP = 10`;
   - `normalize_note_text`;
   - `dedup_key`;
   - `NoteLimitError`, `NoteDuplicateError` and `NotesDisabledError`, each
     with `.detail`, giving sizes only and never note text;
   - **no** `RenderedNote` here: it lives in `agent/config.py` (AC8);
   - `NOTES_HEADING` (the DD9 text);
   - `render_notes_block(notes)`, which neutralises the delimiter tokens with
     `re.sub(r"(?i)<(/?saved_notes)", r"&lt;\1", text)` or equivalent.
3. **Repository**, beside `AgentRuleRepository`. `create` reads
   `notes_enabled` and `notes_next_number` from `agents` inside the
   transaction (`SELECT ... WHERE name = ?`).
   - A missing agent raises `KeyError`.
   - The counter is incremented with an `UPDATE agents SET notes_next_number
     = notes_next_number + 1`.
   - The LEFT JOIN display label is
     `COALESCE(cs.title, n.origin_label)` with
     `cs.id IS NOT NULL AS origin_exists`. Check the actual `chat_sessions`
     title column name.
4. **`AgentConfig`, `save` and `_row_to_config`:** add `notes_enabled` exactly
   as `self_revision_requires_approval` was added (`repositories.py:228`,
   `:244`, `:261`, `:404`).
5. **Composer** (`agent/config.py`): implement AC8-AC10 and keep the docstring
   current. The deferred-import pattern for `render_notes_block` is the same
   as for `render_rules_block`.
6. **Loader** (`agent/prompt_layers.py`): load the agent row's `notes_enabled`
   (or read it through the store) and the notes. Build `RenderedNote`s and pass
   `notes=None` or the list.
7. **REST**, under `# ── Notes (M27 F2) ──` after the rules routes, reusing
   `_load_agent_or_404` and `_rules_body`.
   - The `enabled` body field is a pydantic `StrictBool`, so a 422 is returned
     for `"no"` or `1`.
   - `PUT .../notes/settings` for an unknown agent is 404: `set_notes_enabled`
     raises `KeyError`, as `set_self_revision_requires_approval` does.
   - The phrase "Rules take precedence over saved notes." is a named constant
     in `_rules.py`. Register the routes in this order:
   `GET .../notes`, `PUT .../notes/settings`, `PUT .../notes/{note_id}`,
   `DELETE .../notes/{note_id}`, `DELETE .../notes`.
8. **`update_agent` and `create_agent`:** add the preserve-on-omit line beside
   `api.py:915-916`.
9. **Tests** use the schema template. Only the migration tests call
   `ensure_schema` directly.
10. **Docs** per AC17.

## Edge Cases

- **Creating while notes are off** (leg 2's tools) raises `NotesDisabledError`.
  Operator edits and deletes are allowed while off.
- **Text that is empty after normalisation** raises `NoteLimitError` ("A note
  needs some text").
- **The total-limit check on update** uses `total - old_len + new_len`.
- **An operator edit that makes a note a duplicate of another** raises
  `NoteDuplicateError` (422).
- **`clear`** leaves `notes_next_number` alone, because numbers are never
  reused.
- **A purged origin session:** `origin_exists` is false, and the label falls
  back to the stored one, or "Untitled chat" when that is null.
- **An agent with no stored row** (including the synthesized `default`) has no
  notes, and the prompt gets `notes=None`. Its REST routes 404 through
  `_load_agent_or_404`. Document this.
- **`clear`** does not reset the counter (test it). Deleting and recreating an
  agent starts again at 1, because the row is new (test it).
- **Preserve-on-omit:** a Studio-style `PUT /api/agents/{name}` that omits
  `notes_enabled` leaves it on, and an explicit `false` turns it off. Test
  both.
- **Other `save()` callers** (`self_configuration/manage.py`) carry
  `notes_enabled` through `model_copy` of a loaded config. They have the same
  narrow race as the approval flag; note it in `agents.md`.

## Files Affected

- `the_one/db/schema.py`, `the_one/db/_notes.py` (new),
  `the_one/db/repositories.py`, `the_one/db/models.py` (if used).
- `the_one/agent/config.py`, `the_one/agent/prompt_layers.py`.
- `the_one/interfaces/web/api.py`.
- Tests: `tests/test_db_migration.py`, `tests/test_notes_store.py` (new),
  `tests/test_config.py`, `tests/test_prompt_layers.py`,
  `tests/test_self_configuration_write.py`, `tests/test_agent_notes_api.py`
  (new).
- `the_one/agents.md`.

## Citation Audit

Checked against `82a0396`:
- `AgentRuleRepository` is at `repositories.py:1524`.
- The v42 block is at `schema.py:2617`, with `CURRENT_VERSION = 42` at `:14`.
- `_rules_body` is at `api.py:1318`; the rules routes are at `:1338-1384`, with
  `/order` (`:1358`) before `/{rule_id}` (`:1370`).
- The approval flag is at `repositories.py:228`, `:244`, `:261`, `:267` and
  `:404`, and in `api.py:915-916`.
- `render_rules_block` is at `db/_rules.py:64`.
- `build_system_prompt` is in `agent/prompt_layers.py`.
- `test_notes_are_reserved_and_ignored` is at `tests/test_config.py:265`.

All were verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
