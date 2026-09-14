# Flight Log: Storage and Embedding Foundation

**Flight**: [Storage and Embedding Foundation](flight.md)

## Summary

Planning. Not yet in flight.

---

## Leg Progress

*(none yet)*

---

## Decisions

*(runtime decisions not in the original plan)*

### Flight Director Notes

**Planning — 2026-09-14.** Branch: to be cut from `mission/24-knowledge-bases`
as `flight/02-storage-and-embedding-foundation` at flight start; PR back into
the mission branch per the mission's "Branch Layout" section. No CI lane runs
on that PR — `make lint`, `make test-unit`, `pip-audit` and the frozen
`fly execute` are run by hand and recorded here before merge.

---

## Reconnaissance Report

Source artifacts walked against current code before leg design: the mission
document's code citations and the Flight 2 bullet in its Flights list, Flight
1's flight spec (DD-6) and flight debrief (Recommendations 1–3, Action Items),
and the open squawk list. Classification per `/mission-control:flight` Phase 1b.

| # | Source item | Class | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | Mission: KB endpoints at `api.py:1370-1466` | confirmed-live (drifted range) | `the_one/interfaces/web/api.py:1370-1462` — eight routes, all `Request`-based hand-validation; no item update/status/search/reindex route | Keep; range is 1370–1462. Route gaps are Flight 2 scope |
| R2 | Mission: `mcp__` carve-out at `config.py:166-172` | drifted (wrong file) | Lives at `the_one/agent/config.py:146-172` (`AgentConfig.is_tool_enabled`), not `the_one/config.py` (that range is the legacy-data-dir rename). Content as described: `is_mcp = tool_name.startswith("mcp__")` | Correct the citation in `mission.md`. The decision itself belongs to the tool-registration flight, not Flight 2 |
| R3 | Mission: `parent_id` has zero readers | confirmed | Written at `repositories.py:443,448`, round-tripped at `:469`; DDL `schema.py:75`; no filter/join/traversal anywhere | Decision stays open for Flight 3 (folder→file); Flight 2 must not build a chunk hierarchy that competes with it |
| R4 | Mission F2 bullet: "widen the item-type CHECK via the v37 rebuild template" | confirmed-live (name drift) | Column is `kb_items.type` (`schema.py:76`: `CHECK (type IN ('file','url'))`), Pydantic `KBItem.type: Literal["file","url"]` (`models.py:94`); `item_type` has zero hits in the tree | Widen `type`; do not rename. v37 template at `schema.py:2141-2212`; v39's same-name rewrite note at `:2288-2299` argues for the simpler unconditional rewrite |
| R5 | Mission F2 bullet: "add app-level embedding config" | confirmed-live | No embedding settings anywhere (`the_one/config.py:52-78` Settings has none). Precedent: `app_metadata` key/value table, v31 (`schema.py:1936-1949`), `AppMetadataRepository` (`repositories.py:1237-1264`), plaintext, no encryptor | Design decision needed: where a backend choice that may carry a credential lives (see DD) |
| R6 | Mission F2 bullet: "add item status/error/hash/timestamp" | confirmed-live | `kb_items` has `status TEXT DEFAULT 'pending'` only — no CHECK, no error, no hash, no `updated_at`; no `UPDATE kb_items` statement exists in the tree; `KBItemRepository` (`repositories.py:422-477`) has no `update` | Flight 2 scope |
| R7 | Mission F2 bullet: "chunk and vector tables plus the FTS5 index over chunk text" | confirmed-live | No chunk table, no `vec0` table, no FTS anywhere (`grep fts5` → only the vec0 MATCH in diagnostics). FTS5 compiled into the dev venv's SQLite 3.45.1 (verified `CREATE VIRTUAL TABLE … USING fts5`) | Flight 2 scope. FTS5 in the **frozen** Windows bundle is unverified — see R13 |
| R8 | Mission F2 bullet: "repository and route gaps that leave no way to move an item out of `pending`" | confirmed-live | As R6; plus two pre-existing rough edges in the same routes: `create_kb_item` never checks the KB exists (FK `IntegrityError` → 500, `api.py:1443-1452`) and `delete_kb_item` ignores its `kb_id` path segment (`:1455-1462`) | Fold both edges into the route-gap leg; they are inside the surface Flight 2 already rewrites |
| R9 | Mission Constraint: FTS5 "compiled into the interpreter the app ships and entirely unused today" | partially-verified | Dev venv: yes. Frozen CPython 3.11 on Windows: not yet observed | Add an FTS5 line to the existing `doctor` gate set (unconditional, like the embedding probe) so the frozen run proves it — cheap, same shape as Flight 1's probes |
| R10 | Mission Constraint: `enable_load_extension` "genuinely varies across Python builds" | confirmed | Dev venv has it (`sqlite3.Connection.enable_load_extension` present, SQLite 3.45.1); frozen Windows proved it in Flight 1 (`sqlite-vec: OK` on `windows-worker`). App connection (`connection.py:45-58`) never calls it; the probe records this as Flight 2's work (`diagnostics.py:345-347`) | Flight 2 wires the load into the singleton connection with the probe's enable→load→disable discipline |
| R11 | F1 DD-6: "probe internals will need a light rewrite in Flight 2 to call through the seam" | partially-satisfied | Embedding probe's load path (`diagnostics.py:702-753`, `_force_hf_offline` `:665-679`) is exactly what the seam needs internally → mechanical swap. Store probes build throwaway tables and were never meant to integrate → no change needed | Scope the rewrite to the embedding probe only |
| R12 | F1 debrief Rec 1: benchmark stores on Windows or discount Linux | confirmed-live | usearch Windows wheels are `simd=serial` (F1 log, binary analysis); no benchmarking harness exists in the tree (no `bench*`, no `pytest-benchmark`); the only measurement surface is `doctor`'s detail line + `fly execute` | Apparatus DD needed (see DD) |
| R13 | F1 debrief Rec 2 / pyproject comment: remove the losing store in the same flight; pick up `hf-xet` (squawk 0049) | confirmed-live | `pyproject.toml:85-96` carries both stores with the comment "The loser is removed from the closure in Flight 2"; `hf-xet` is a hard dep of `huggingface-hub` on x86_64/arm64 (`uv.lock`), needs an override to drop; squawk 0049 open | Both land in the closure leg, verified by one frozen run |
| R14 | F1 debrief Rec 3: 247.1 MiB peak RSS is whole-process, not model-marginal | confirmed | F1 log "Frozen Windows Verification — Leg 2 (second run)" | Compute the float16-vs-int8 storage decision from DD-1 arithmetic, not from this figure |
| R15 | Mission: `models.py` is 360 lines, connector inference config removed | confirmed | `wc -l the_one/db/models.py` → 360 | Informational only |
| R16 | Mission Open Q: `kb__` tools vs whitelist gate | out-of-scope (F2) | `agent/config.py:166-172`; `factory.py` never reads `kb_ids` (`agent/config.py:110`: "reference IDs only — no functional behavior yet") | Belongs to the tool-registration flight. Flight 2 ships no agent tool |
| R17 | Discovered: Studio save path writes `kb_ids: []` on every agent save | new — out-of-scope (F2) | `studio.js:2035-2044` collects chips from a selector nothing renders; any API-set `kb_ids` is clobbered on UI save | Squawk candidate or fold into the Studio KB flight; flag to operator |
| R18 | Discovered: `KBItemRepository.get` has no caller and no route | confirmed-live | `repositories.py:434`; no `GET …/items/{item_id}` route | Route-gap leg adds the route |
| R19 | Discovered: no index on `kb_items(kb_id)` | confirmed-live | schema.py has no `idx_kb_items_*` | Add in v40, `CREATE INDEX` outside the `executescript` per `column-aware-index-create-for-rewind-paths` |
| R20 | Discovered: model2vec `encode()` defaults `use_multiprocessing=True` above 10,000 texts and `max_length=512` tokens | confirmed (venv probe) | `StaticModel.encode(sentences, max_length=512, batch_size=1024, use_multiprocessing=True, multiprocessing_threshold=10000)` | Seam must pin `use_multiprocessing=False` — a fork pool inside a uvicorn worker or a frozen bundle is a hazard — and own the 512-token truncation explicitly |
| R21 | Discovered: usearch `save()` returns bytes when given no path; `restore(buffer)` accepts bytes | confirmed (venv probe) | `Index.save(path_or_buffer=None) -> bytes`, `Index.restore(path_or_buffer, view=False)`; `sqlite_vec.serialize_int8` also exists | Widens the store design space: a usearch index could be persisted as a BLOB inside SQLite rather than a sidecar file — see DD |

**Items flagged for operator decision** (not auto-retired): R2 (citation fix in
`mission.md` — trivial, proposed to do during this planning pass), R17 (defect
outside Flight 2's surface), R9 (add an FTS5 doctor probe — proposed yes).

### Flight Director Notes — planning, design review

- **Crew interview (2026-09-14)** settled: recon follow-ups (citation fix,
  FTS5 probe, squawk 0050 for the Studio `kb_ids` clobber); settings live in
  `app_metadata` as two separate records with defaults, API only, UI later;
  seam with both stores, benchmark, human chooses, loser removed; benchmark
  as a committed script run on `windows-worker` via a one-off `fly execute`;
  full chunking policy now, app-wide, never per-KB; four-state item status
  with CHECK; **no provider-delegating backend** — the operator settled on
  non-LLM local embeddings as the product, and the mission was amended in
  five places to record it (outcome, Context, success criterion, Constraints,
  Environment Requirements) rather than worked around; no HAT leg.
- **Empirical premises verified on this host before the spec was written**:
  `vec0` partition keys + `vec_int8` binding + delete-by-rowid; `usearch`
  `save()`/`restore()` to bytes and path; FTS5 external-content delete;
  `aiosqlite` extension coroutines; `SQLITE_MAX_LENGTH` 1e9 (rules out
  usearch-as-BLOB at the ceiling); model2vec `encode` defaults
  (`use_multiprocessing=True` above 10k texts, `max_length=512`).
- **Design review cycle 1 (Architect, Opus) — `approve with changes`.** Two
  high-severity findings, both verified empirically by the reviewer and both
  accepted: (1) explicit `BEGIN`/`COMMIT` on the shared `aiosqlite` connection
  cannot deliver atomicity — another coroutine's `commit()` commits a partial
  write, and `BEGIN` raises under exactly the concurrency that motivates it;
  replaced by a write lock (DD-13). (2) plain `INTEGER PRIMARY KEY` recycles
  rowids, so a re-index could map a stale vector id to different text — a
  silent wrong answer; replaced by `AUTOINCREMENT` (DD-5). Six medium findings
  fixed: upsert semantics defined; the probe rewrite's test impact stated
  honestly; CHECKs as frozen inline literals; `indexing→pending` requeue;
  extension loading moved from the connection factory into the store (the
  factory rationale was shown false — a `vec0` DB opens and migrates without
  the extension); Leg 1 split (six legs now). Seven suggestions adopted,
  including setting the operator's latency bar **before** the benchmark runs
  — the reviewer's 200k-vector probe suggests sqlite-vec may miss any
  reasonable bar at 3M, so the `faiss-cpu` divert is live rather than
  theoretical. Changes are substantive → cycle 2.
- **Design review cycle 2 (same Architect) — `approve with changes`.** All
  cycle-1 fixes verified landed except one: the write lock was scoped to
  multi-statement writers, and the reviewer modelled a plain single-statement
  repository write committing mid-transaction — the previous chunks were
  destroyed with the lock in place. Fixed by widening the rule to **every
  committer** (`write_transaction()` guard wrapping every existing repository
  write, non-reentrant with re-entry detection, lint-enforced by a repo-source
  guard test; convention renamed `db-writes-hold-the-write-lock`). The
  reviewer also showed the second-connection alternative fails under WAL
  (`database is locked`), which turns DD-13's rejection from a preference
  into a measured fact. Two mediums fixed: `truncated` now has a stated
  computation (a `tokenize` pass on inputs over 512 chars, ~27 % worst-case)
  and the vector suite no longer depends on Leg 3's stub. Three lows fixed
  (retry route accepts `indexing`; DD-10's window is first-use, `_loaded`
  flag; norm tolerance 1e-3 against a measured 1.83e-4). S8–S10 and Q1–Q3
  adopted. **Two cycles used — the workflow's maximum.** Escalating the
  proceed decision to the operator at the spec walkthrough, per the Flight 1
  Leg 2 precedent: every finding arrived with a verified fix and none
  persisted across cycles, so the remaining risk is implementation-level and
  is covered by each leg's own design review and the flight-end Reviewer.
- **Spec walkthrough and operator decisions (2026-09-14)**: proceed past the
  two-cycle review maximum (same rationale as Flight 1 Leg 2 — every finding
  fixed and verified, none persisted; per-leg design reviews and the
  flight-end Reviewer cover the implementation-level residue); **latency bar
  set at p95 ≤ 250 ms** for one k = 10 query on Windows at the largest
  measured N, recorded here before any benchmark number exists; squawk 0051
  logged for the stale `api.py:4642-4647` aiosqlite comment (Leg 1 fixes the
  `schema.py:319-327` twin in-leg). Flight moved `planning` → `ready`.
