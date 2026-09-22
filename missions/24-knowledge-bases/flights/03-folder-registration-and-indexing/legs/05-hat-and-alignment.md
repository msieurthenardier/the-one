# Leg: hat-and-alignment

**Status**: completed
**Flight**: [Folder Registration and Indexing](../flight.md)

## Objective

A guided, operator-present walk of the flight's API surface on a dedicated
dev instance, using a folder of the operator's own choosing, to align on
response shapes, status behaviour and error messages before the flight
lands — fixing look-and-feel issues inline and routing anything that adds
behaviour through the fix-vs-feature gate. Optional (operator's call at
planning, DD-10).

## Context

- Flight DD-10 (scope and the fix-vs-feature gate), DD-8 (the contract a
  HAT change must re-author rather than patch: route paths, the status
  body's four file-item counts and `folders` list and four indexer states,
  the chunk row's five keys, the source body's five keys, the 202/409/422
  codes, the `scope` values). The behavior spec
  `kb-folder-index-round-trip` and its run log depend on that contract.
- Legs 1–4 completed at `5a2fcec`; the behavior test passed 8/8 on
  2026-09-15; unit gate 4,547 passed; frozen build 608700 PASS.
- Apparatus: a dev instance on 8485 with a scratch data directory (mint
  the credential first, then `make up`), `curl` with the bearer header.
  Never 8484, never the default data directory.

## Verification Steps (presented one at a time; the operator performs and reports)

1. **Start**: `THE_ONE_DATA_DIR=<scratch> the-one rotate-api-credential`, then `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> make up`; `GET /api/live` → 200. *(state: fresh instance, no knowledge bases)*
2. **Register a real folder of yours** (text, markdown or code; not a system directory): `POST /api/knowledge-bases` then `POST …/items` with `type: folder`. *(no-KB → registered)*: 201, canonical path echoed; then `GET …/status` a few times — watch `indexer` go `running` → `idle`, `items` counts move, `folders[0].status` reach `indexed`; note whether any file landed `failed` and whether its `error` text tells you why.
3. **Inspect**: `GET …/items` — do the skipped things (dotfiles, unsupported suffixes, symlinks) match your expectation for that folder? `GET …/items/{id}/chunks` and `…/source` for one file — are the chunk boundaries and the source text what you'd want an agent to see?
4. **Change and re-index**: edit one file, add one, delete one; `POST …/reindex` (default) → 202; watch `…/status`; confirm the three changes are reflected. Then `POST …/reindex?scope=all` and confirm `requeued` equals your `indexed`+`failed` file count.
5. **A failure you can read**: drop a >10 MiB text file into the folder, re-index, find it `failed` with the cap message in `GET …/items`. Is the message good enough for the Studio flight to show verbatim?
6. **Shared state you won't be looking at**: while a re-index of a larger folder is `running`, `DELETE /api/knowledge-bases/{kb_id}` from a second terminal — the worker must stop first (route contract), the delete must return 200, `GET /api/knowledge-bases` must not list it, and the app log (`.the-one.8485.log`) must show no traceback.
7. **Restart resumes**: with a large enough folder that a re-index takes seconds, `make down` mid-index, `make up`, and watch `…/status` finish without any further call. *(running → killed → resumed)*
8. **Teardown**: delete the KB, `make down`.

At every step, say what surprised you. Look-and-feel fixes (a message, a key name that reads wrong, a code you'd expect differently) ride the inline protocol; a request that adds behaviour is promoted to a scoped design review; any change to the DD-8 contract re-authors the behavior spec.

## Acceptance Criteria

**Waived by the operator on 2026-09-16 at Step 2**: the flight has no UI surface, so the walk is folded into Flight 6's HAT, where the same actions happen on a screen. Step 1 (apparatus) was performed; Steps 2–8 were not.

- [x] Every step above performed by the operator with the result reported — *waived (see above)*
- [x] Every issue raised either fixed inline or recorded — *none raised*
- [x] Operator states they are satisfied, or waives the remaining steps — *waived*
- [x] Flight log entry; any code change committed with review — *no code change*

## Files Affected

- Only what the HAT surfaces; otherwise the flight log and this artifact.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
