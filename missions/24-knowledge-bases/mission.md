# Mission: Knowledge Bases

**Status**: active

## Outcome

An operator points the app at a folder on their machine and the documents in it
become searchable by their agents. Nothing else is asked of them: the folder is
read, indexed, and kept current as files come and go. An operator attaches a
knowledge base to whichever agents should have it, the same way they attach an
MCP server, and those agents can consult it mid-conversation. Agents without the
attachment cannot reach it at all.

The whole thing works on a fresh install with no account, no API key, and no
network — and no file contents leave the machine. *(Amended at Flight 2
planning, 2026-09-14: an earlier draft allowed an operator to choose a backend
that sends contents off-machine; that option is out of this mission — see
Constraints.)*

## Context

Issue #160 has sat open since 2026-07-20 describing a knowledge-base feature
whose scaffold already exists in the tree: `KnowledgeBase` and `KBItem` models,
both tables with cascade delete, two repositories, an `AgentConfig.kb_ids`
attach field with a working codec, REST CRUD under `/knowledge-bases`, and two
21-line Studio placeholder panels. All of it inert. This mission fills the
scaffold in.

The issue is stale in four ways worth recording, because it will mislead anyone
who reads it as a spec:

- It targets schema **v33**. The schema is now at **v39**; this mission's
  migration is **v40**.
- Its line citations have drifted (the KB endpoints are `api.py:1370-1466`, not
  684-765).
- It points at "the connector inference config (`db/models.py:585-606`)" as the
  precedent for KB-level provider selection. Mission 23 removed that machinery;
  `models.py` is now 360 lines. The precedent no longer exists.
- Its citation for the double-gating footgun (`config.py:578-588`) is also
  stale; the live site is `the_one/agent/config.py:166-172`.

There is also unratified prior art. `docs/kb-architecture.md` surveys this exact
feature and recommends a different stack (LanceDB, BGE/Nomic via
sentence-transformers, LlamaIndex, Crawl4AI). Git history shows it was
pre-existing and untracked, swept into `ebf694d` incidentally rather than
adopted — the Mission 05 F3 flight log records it as "pre-existing, unrelated."
It is a research survey, not a decision, and this mission supersedes it. Its one
load-bearing claim, a "10s of GB per KB" scale target, has been revised down by
the operator to the ceiling in Constraints below. The doc should be amended or
retired to say so.

Three scope decisions separate this mission from the issue as written:

**Web crawling is out.** The issue's recursive same-domain BFS is the largest
complexity driver in it and is orthogonal to the case that motivates the
feature — making documents already on the machine searchable. URL items become a
follow-up mission. The `url` item type stays in the data model, dormant and
unreachable from the UI, so that mission is additive rather than a rework.

**Embeddings are not an LLM-provider concern.** The issue specifies
`LLMProvider.embed()`. That abstraction cannot hold a local static-embedding
model, which is not an `LLMProvider` and cannot be made into one. Delegating to
a configured provider is *one* backend behind an embedding seam, not the seam
itself.

**Extraction ships text only, but the seam ships complete.** PDF and Office are
a later mission. The extractor interface must accept them without the indexing
pipeline changing.

A fourth option was considered and rejected: operator-installed third-party
vector-store *packages*, discovered by entry point the way some apps do plugins.
It does not survive contact with how this app ships. The Windows build is a
frozen one-dir PyInstaller bundle with no `pip` inside it, so an operator-supplied
backend would have to be ABI-matched against the bundled CPython 3.11 with every
transitive dependency resolved by hand — working for a `pip install` dev setup
and breaking for the installer, which is the worst place for that split to land.
The connector registry is not a counter-example: it is an in-tree dict
(`connectors/registry.py`), and the tree contains no entry-point discovery, no
`importlib.metadata`, and no `sys.path` manipulation anywhere.

What that idea was reaching for is preserved without the loader. The seam is
real; it ships with the bundled local model as its one production
implementation and a test-only second implementation in its suite so it cannot
quietly take the shape of its only backend *(amended at Flight 2 planning —
an earlier draft promised two production implementations, the second a
provider-delegating one; the operator settled on non-LLM local embeddings as
the product)*. Any future backend — a remote store reached over HTTP by URL and API key, mirroring the
existing `openai-compatible` precedent, or something like LEANN, which discards
stored embeddings and recomputes them at query time for under 5% storage
overhead — slots in behind it without touching the pipeline.

What the mission inherits from the codebase is more than the issue credits:
`watchfiles` already ships transitively via `uvicorn[standard]`;
`ConnectorManager` is a working template for supervised per-entity background
tasks; `filesystem.py` already has `canonicalize`, `_is_descendant`,
`_is_binary`, and `_check_read_size`, which cover most of file-skipping and path
containment; and schema migration v37 is a rebuild template for a table carrying
a self-referential foreign key.

## Success Criteria

- [ ] Operator can register a folder on disk as a knowledge base source, and see each discovered item's index status including failures
- [ ] Files in a registered folder index automatically, and additions, modifications, and deletions are reflected without operator action or an app restart *(behavior-test-backed)*
- [ ] Indexing a large folder runs in the background without blocking the UI, and resumes rather than restarts after an interruption
- [ ] Operator can inspect a knowledge base's contents and metadata, and retrieve the source material behind any indexed item
- [ ] The embedding backend is bundled, local and non-LLM: it works on a fresh install with no account, no network, and no external service running, and no file contents leave the machine *(amended at Flight 2 planning — an earlier draft had the operator choose between backends and be warned when a choice sends contents off-machine; no such backend ships in this mission)*
- [x] Retrieval combines semantic and keyword matching, so a query naming an exact term finds it even when the embedding model ranks that term poorly *(Flight 5: `the_one/knowledge/retrieval.py` fuses the vector store and FTS5 by reciprocal rank, with one slot reserved for a keyword-only hit so the exact-term guarantee holds at every `limit`; pinned by five targeted tests including the crowding case that fails without the reserved slot)*
- [ ] A new file-format handler or a different vector store can be introduced without modifying the indexing pipeline
- [ ] A knowledge base can be attached to and detached from any agent in Studio *(behavior-test-backed)*
- [x] An attached agent can discover and query its knowledge bases during a chat session, and cannot reach one it is not attached to *(Flight 5; behavior-test-backed — `kb-agent-query-round-trip` 8/8 on 2026-09-17: an attached agent's tool result carried fixture prose retrieved from disk; an unattached agent got `Unknown tool` with no knowledge-base content; a narrowed built-in whitelist kept the tool and an explicit blacklist still removed it by name)*
- [ ] Existing installs upgrade with no data loss, the unit gate stays green, and the frozen Windows installer still builds and runs

## Stakeholders

**The operator** — the person running the app on their own machine. They want
their own documents answerable by their own agents, and they bear the cost if
that means shipping personal files to a third party. Every default here is set
for them.

**The dependency budget** — the app is deliberately framework-free and ships as
a frozen Windows installer, where every dependency is carried by every install
forever and `pip-audit` fails the release on any finding in the closure. This
stakeholder has no voice in the room, so the mission states its interest
explicitly. This mission knowingly spends against it (see Constraints); that
spend is a decision on record, not an accident.

## Constraints

- **No web crawling.** URL items remain dormant. Follow-up mission.
- **Extraction ships text only** — plain text, code, markdown. PDF and Office
  are a later mission, but the extractor seam must accept them without the
  indexing pipeline changing. Format coverage is deferred; format
  *extensibility* is not.
- **Corpus ceiling: low single-digit GB of raw text per knowledge base.** Not the
  10s of GB the superseded survey assumed, and not toy scale either. This rules
  brute-force cosine out as the primary store and rules LanceDB out on weight.
- **The default embedding backend is bundled and local.** It must work on a
  fresh install with no account, no network, and no external service. The
  operator accepted the resulting installer weight explicitly, and then
  re-accepted it against a corrected, larger figure. The closure adds roughly a
  dozen packages absent from `uv.lock` today — `model2vec`, `numpy`, `joblib`,
  `cloudpickle`, `safetensors`, `tokenizers`, `huggingface-hub`, `fsspec`,
  `hf-xet`, plus the vector store and its own `numkong` — three of them native
  extensions, against a current dependency payload the PyInstaller spec
  describes as ~38 MB. An earlier statement here of "five packages, ~16 MB" was
  measured too shallowly and understated it.
- **`huggingface_hub` ships, but is never permitted to fetch.** It arrives
  transitively via `tokenizers` and so cannot be dropped while the local backend
  is model2vec-based. Because model2vec's loader silently falls back to
  downloading a model whose local directory is missing, any code path that loads
  the bundled model must assert the packaged path exists first and run with
  `HF_HUB_OFFLINE=1`. Otherwise a model lost during packaging appears to work
  by fetching over the network — the exact failure the no-network criterion
  exists to forbid.
- **No backend that transmits file contents ships in this mission.** *(Amended
  at Flight 2 planning, 2026-09-14; the earlier constraint read "available but
  never silent".)* The operator settled on non-LLM local embeddings as the
  product. A provider-delegating or remote backend remains possible behind the
  seam as a future mission; if one ever ships, it must never be silent about
  where contents go. Its absence removes the Ollama environment requirement
  and the operator-facing backend chooser from this mission's scope.
- **The embedding backend is app-global, not per knowledge base.** Issue #160
  specified a per-KB `embedding_provider_config_id`, and this mission carried
  that forward until a survey of the field argued against it: AnythingLLM sets
  the embedder system-wide and explicitly cannot scope it per workspace, because
  changing it forces deleting and re-embedding every document. A per-KB choice
  buys flexibility nobody asked for and costs a dimension-mismatch case in the
  storage layer plus a per-KB re-index story. One backend, one vector space.
  Changing it is an explicit, costed, whole-corpus re-index.
- **Retrieval is hybrid: semantic plus keyword.** SQLite's FTS5 is already
  compiled into the interpreter the app ships and is entirely unused today, so
  keyword search costs no dependency and no second storage engine — it indexes
  the chunk text already living in SQLite under the vectors-only contract above.
  Hybrid matters more here than it would elsewhere: static embeddings trade
  quality for size, and keyword matching is what recovers exact terms, rare
  identifiers, and proper nouns that a small embedding model ranks poorly.
- **The vector store holds vectors and an id mapping — nothing else.** Chunk
  text and metadata live in SQLite, owned by the app, for every backend. This
  keeps the seam narrow rather than widening it to the union of what each
  candidate store wants to own, makes retrieval-by-link behave identically
  across backends, and means a remote store never receives document text — only
  embeddings. Stores that *can* own text and metadata are simply not asked to.
- **Cross-platform: Windows, macOS, and Linux.** Windows is the operator's own
  environment and the floor; the other two are expected to work. This rules out
  candidates with platform gaps regardless of their other merits — LanceDB, for
  instance, ships no Intel-Mac wheel.
- **The frozen Windows installer must still build and run.** Anything that
  cannot be packaged is not a candidate.
- **No frameworks.** Prefer the smallest dependency that meets the capability
  over the most capable one.
- **Attachment is authorization, not an adversarial boundary.** Isolation comes
  from `AgentFactory.create()` building a fresh `ToolRegistry` per agent. This is
  an operator-trust model and must be documented as such.
- **KB identity is baked into the tool instance.** One `kb__{name}__search` tool
  per attached knowledge base, mirroring `mcp__{src}__{tool}`. A single
  `kb_search(kb_name, query)` tool would dissolve isolation entirely, because
  the registry gates on tool name and not on arguments. This is an invariant,
  not a naming preference.
- **Session-bound attachment.** Attach and detach take effect on the next
  session, matching the existing MCP contract.

## Environment Requirements

- Host-native development (`make up`, `make test-unit`, `make test-browser`)
- Playwright for the browser lane; both Studio panels are covered there
- Ollama is **not** required — no provider-delegating backend ships in this
  mission *(amended at Flight 2 planning)*
- Windows/PyInstaller build reachable — a candidate that passes on Linux but not
  in the frozen build has not passed. Dev is Python 3.12.3 / SQLite 3.45.1; CI
  and the installer are Python 3.11.
- Windows is the operator's primary environment and the support floor; macOS and
  Linux are expected to work, and a candidate dependency lacking a wheel for any
  of the three is disqualified
- No network access required to run or test the default path

## Open Questions

- [ ] **Does `sqlite-vec` load in the frozen build?** No longer an open bet —
      a probe with a known safety net. `sqlite-vec` is 292 KB with **zero
      dependencies** and ships wheels for Windows, macOS (x86_64 and arm64), and
      Linux (x86_64 and aarch64); it delivers `vec0.dll` as package data, which
      the `collect_data_files` precedent in the PyInstaller spec already covers.
      The single risk is whether `enable_load_extension` survives in the frozen
      CPython 3.11 on the Windows runner. Because the bundled embedding backend
      drags `numpy` in regardless, brute-force cosine over SQLite BLOBs remains
      available as a degraded fallback for small corpora. Either way the seam
      ships with two real implementations rather than one — which is what keeps
      it from quietly taking the shape of its only backend. LanceDB is out
      on weight (~145 MB of wheels) and on the missing Intel-Mac wheel.

      **Amended during Flight 1 planning.** `sqlite-vec` performs exhaustive
      brute-force KNN and has no ANN index — ANN is upstream future work. Its
      real advantages are that vectors stay disk-backed rather than
      materialising in RAM, and that they live in the SQLite file the app
      already backs up; they are not a search-complexity improvement, and an
      earlier framing here of index-versus-scan was wrong. At 512 dimensions and
      this corpus ceiling an exhaustive scan is the binding constraint, so
      `usearch` (2.4 MB, HNSW, wheels on all three platforms, id→vector so it
      satisfies the vectors-only contract natively) is evaluated as a peer in
      Flight 1 rather than held in reserve. Its cost is leaving the single
      SQLite file: a second artifact outside the backup and migration path,
      needing its own rebuild-from-SQLite and crash-consistency story.

      **Amended after Flight 1 (debrief 2026-09-12).** Both candidates package
      and load in the frozen Windows bundle, each behind a permanent `doctor`
      probe; the *choice* is Flight 2's, made against a real corpus through the
      storage seam. Three measured inputs Flight 2 must start from, all in the
      Flight 1 log and debrief:
      1. **Every published `usearch` Windows wheel is built without numkong
         linkage** — `simd=serial`, permanently, verified by reading the
         binaries (0 `nk_*` symbol refs on Windows against 54 on Linux, across
         2.16.0–2.26.2). Linux and macOS wheels are accelerated. So on the
         operator's own platform usearch's margin over `sqlite-vec`'s
         exhaustive scan is HNSW candidate pruning alone, not SIMD distance
         kernels. **Flight 2 benchmarks on Windows, or discounts Linux numbers
         explicitly.** A Linux-only comparison would hand usearch acceleration
         the shipping product never has.
      2. The frozen embedding-probe peak working set is **247.1 MiB**, but that
         is whole-process (`numpy` + `tokenizers` + `safetensors` import weight
         plus the model, which is roughly a quarter of it). It answers whether
         the backend can stay warm in-process; the float16-vs-int8 vector
         *storage* question is arithmetic on dimension × chunk count × dtype
         width and is computed directly, not read off this figure.
      3. The installer doubled (71.2 → 141.8 MB). Flight 2 removes the losing
         store candidate — and `numkong` with it if usearch loses — in the same
         flight it makes the choice, and picks up the `hf-xet` trim (squawk
         0049) against the same closure change, since both need a frozen build
         to verify.
- [x] **Which model, and how it reaches the build.** Measured sizes:
      `potion-base-2M` 8.5 MB, `potion-base-8M` 31.1 MB, `potion-base-32M` and
      the retrieval-tuned `potion-retrieval-32M` 131.2 MB each. The
      retrieval-tuned model is the quality choice and is 4× the size of the
      figure the weight decision was first framed against. **Resolved in Flight
      1**: `potion-retrieval-32M` at float16, committed as package data. Its
      published `model.safetensors` is 123.2 MiB, over GitHub's hard 100 MiB
      per-blob limit, so float32 could not be committed at all without Git LFS;
      float16 clears the limit at roughly 62 MiB with plain git. For scale, the
      largest currently tracked file is a 1.7 MB PNG.
- [x] Chunking strategy and sizes, and whether they are per-KB configurable.
      **Resolved at Flight 2 planning (2026-09-14)**: app-wide, never per-KB —
      a paragraph-aware deterministic chunker with defaults of 1,000 characters
      and 150 overlap, configurable once under Administration (API in Flight 2,
      the panel in a later flight). See Flight 2 DD-7.
- [ ] Changing the embedding backend or model invalidates every stored vector —
      different dimensionality, different space. With the backend now app-global
      the blast radius is every knowledge base at once. Is switching offered at
      all, and if so how is the full re-index surfaced, costed, and made
      interruptible?
      *Partially answered at Flight 2 planning*: with no second production
      backend (see the DD-2 amendment above), "switching" means a model change.
      Flight 2's settings API refuses a `model_id`/`dim` change while any chunk
      exists (409); the re-index itself is designed with the pipeline in
      Flight 3.
- [ ] How are semantic and keyword results combined — reciprocal rank fusion, a
      weighted score, or keyword as a fallback when semantic recall is thin? And
      is the balance operator-tunable or fixed?
- [ ] Do `kb__` tools follow the built-in enable/disable whitelist path or the
      MCP-override path? The carve-out at `the_one/agent/config.py:166-172` (`AgentConfig.is_tool_enabled`; an earlier draft cited `config.py`, which is the wrong file) is hardcoded to the
      `mcp__` prefix, so a `kb__` name is currently treated as a built-in — any
      agent whose built-in tool list has been narrowed in Studio would silently
      lose every KB tool, with no error and no UI signal. Generalizing the prefix
      set and registering outside the gate are both viable; pick one deliberately
      and land the regression test in the same leg.
- [x] Should the folder→file relationship use the existing `parent_id` column or
      a new indexed `folder_item_id`? `parent_id` has zero readers anywhere in
      the tree today, and the relationship is only ever one level deep.
      **Resolved in Flight 3 (DD-2, 2026-09-15)**: `parent_id` is the link —
      folder deletion cleans descendants' chunks, FTS rows and vectors
      through the widened `KBItemRepository.delete`; no new column, no
      migration; `parent_id` stays unindexed (recorded).
- [x] Which files inside a registered folder are skipped, and by what rule —
      `_is_binary` and `_check_read_size` cover part of it; dotfiles, VCS
      metadata, and ignore files are undecided.
      **Resolved in Flight 3 (DD-3/DD-4/DD-5, 2026-09-15)**: a stat-only
      walk skips dot-prefixed names, `node_modules`/`__pycache__`/`venv`/
      `site-packages`, every symlink, and any suffix outside the extractor
      registry's allowlist (`.html`/`.log` deliberately absent; `.gitignore`
      not honoured — no `pathspec` dependency); a supported file over 10 MiB
      or with a null byte in its first 8 KiB becomes a `failed` item with a
      visible error, never a silent skip.
- [ ] Re-measure `usearch` build and incremental-upsert cost on Windows at
      1M vectors once a real corpus of that size exists (Flight 2 debrief
      Recommendation 5; Flight 3 reconnaissance R6). Flight 2's Windows 1M/3M
      figures (~2 h / ~7 h build, ~10–12 s / ~24 s save) are extrapolations
      from 200k measurements assuming an N-independent platform penalty;
      Flight 3's flush cadence was sized against them (save overhead ~9 %
      at 1M, Leg 2 measurement) and should be re-checked when the number
      is real.
      **Vehicle decided at Flight 4 planning (operator, 2026-09-16; Flight
      4 DD-12)**: folded into Flight 6 / mission close — a synthetic
      1M-chunk corpus generated at mission close and measured on the
      Windows worker, with Flight 3's flush constants re-checked against
      the number. Flight 4 added nothing to the measurement.

## Known Issues

- **`usearch` runs unaccelerated on Windows** (`simd=serial`, no numkong
  linkage in any published wheel). Upstream characteristic, not a packaging
  defect; changing it would mean building usearch from source on Windows. The
  `doctor` probe reports the condition in its detail line so a genuine
  DLL-resolution failure reads differently from this unlinked-wheel state.
  Surfaced by Flight 1.
- **Dead weight in the frozen bundle**: numkong's 1.15 MB `.pyd` on Windows
  (imported unconditionally by usearch, unreachable by it — unchanged
  reason). `hf-xet` (4.03 MB, a Hub transfer accelerator the
  offline-by-construction app never calls) was removed from the closure in
  Flight 2 Leg 6 (squawk 0049, completed). Surfaced by Flight 1.

- **`get_vector_store()` has no shutdown hook** — the indexing manager's
  drain is where dirty indexes get saved; a knowledge base with a store but
  no worker has no flush path at shutdown. Recorded at the Flight 3 debrief,
  unchanged by Flight 4 (the watcher never touches the store). **Resolution
  point: Flight 6 / mission close**, alongside the Windows 1M re-measure —
  not deferred again (Flight 4 debrief Recommendation 5).

## Branch Layout — mission branch, one-off

This mission is carried on a long-running **`mission/24-knowledge-bases`**
branch, cut from `main`. Each flight branch is cut from the mission branch and
its PR merges back into the mission branch; the mission merges to `main` once,
at the end. This is a **deliberate one-off**, not a change to the project's git
convention in `.flightops/ARTIFACTS.md`, which still describes flight branches
merging to `main` directly.

Why here and nowhere else: the mission's early flights carry more irreversible
and cross-cutting risk than any recent mission — a 62 MiB model blob committed
permanently to history, a dependency closure that doubled the installer, a v40
schema migration, and a vector-store choice still open at the time of writing.
Holding the whole mission off `main` until its seams exist and its gates are
green means `main` never carries a half-landed knowledge-base foundation, and a
divert or abort can be dropped as one branch rather than unpicked from `main`
flight by flight.

Operational consequences, recorded so the next flight does not rediscover them:

- Flight PRs target `mission/24-knowledge-bases`, not `main`. Flight 1's PR
  (#195) was first opened against `main` by mistake and retargeted at debrief.
- **No CI lane runs on the mission branch or on PRs into it.** Concourse
  tracks `main`, and `pr-lint.yml` triggers only on `pull_request` to `main`
  (`branches: [main]`) — so a flight PR targeting the mission branch gets
  neither lint, `pip-audit`, nor the unit gate. Flight 1's green checks on #195
  ran while it still targeted `main`; after retargeting it carries none. Until
  `pr-lint.yml`'s trigger is widened to `mission/**` (a one-line servicing
  squawk), every flight runs `make lint`, `make test-unit`, the release-closure
  `pip-audit`, and the frozen-Windows `fly execute` by hand before its PR
  merges, and records the results in its flight log. The final mission → `main`
  PR gets the full lane.
- Keep the mission branch rebased on or merged from `main` at flight
  boundaries so the final merge is not a mission's worth of drift.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned
> and created one at a time as work progresses. This list will evolve based on
> discoveries during implementation.

- [x] Flight 1: Dependency and packaging decision — prove the bundled embedding
      backend packages and runs in the frozen Windows build, probe whether both
      vector-store candidates (`sqlite-vec` and `usearch`) load there — the
      choice between them belongs to Flight 2, where a seam and a real corpus
      exist to measure against — settle model choice and delivery, and run
      `pip-audit` against the candidate
      closure rather than discovering findings at release closure. Thin
      dependency change, no user-visible feature; exists so the two
      hard-to-reverse choices are made on measurement.
- [x] Flight 2: Storage and embedding foundation — the v40 migration (widen the
      item-type CHECK via the v37 rebuild template, add app-level embedding
      config, add item status/error/hash/timestamp, create the chunk and vector
      tables plus the FTS5 index over chunk text),
      the embedding backend seam with the bundled local backend (plus a
      test-only second implementation), the vector storage seam with
      both of its backends and the vectors-only contract, the `sqlite-vec` vs
      `usearch` choice measured on Windows per the amended open question above
      (with the losing candidate removed in the same flight), and the repository
      and route gaps that currently leave no way to move an item out of
      `pending`.
- [x] Flight 3: Folder registration and indexing — the folder item type, path
      containment on registration, and the walk → filter → extract → chunk →
      embed → persist pipeline behind the extractor seam, running as a resumable
      background job with per-file checkpointing.
- [x] Flight 4: Change monitoring — a supervised per-folder watcher modelled on
      `ConnectorManager`, backed by a periodic reconciliation walk. The watcher
      is a latency optimization, not the source of truth: Linux inotify consumes
      one watch descriptor per directory against a per-user cap, and Windows can
      drop events under buffer overflow, so correctness rests on the walk.
- [x] Flight 5: Agent query — the KB tool provider, `AgentFactory` wiring, the
      `kb:` group in lazy search discovery, the hybrid retrieval path that fuses
      semantic and FTS5 results, and the `is_tool_enabled` prefix fix with its
      regression tests. *(landed 2026-09-17; behavior test
      `kb-agent-query-round-trip` 8/8. Fusion reserves one result slot for a
      keyword-only hit — plain reciprocal rank fusion cannot satisfy the
      exact-term criterion at the chosen candidate depth. `UsearchStore.query`
      gained a bounded lock **acquisition** so a query concurrent with a flush
      or rebuild degrades to keyword-only instead of waiting; the earlier
      bound-the-work design was measured to free the lock under a live
      reader.)*
- [ ] Flight 6: Studio surfaces — the global knowledge-base inventory and the
      per-agent attach tab, replacing both stubs. Carries Flight 3's waived HAT
      (register a folder, watch status, read chunks/source, re-index, read a
      failure, concurrent delete, restart-resume) as the seed of its HAT.
      Also carries the Windows 1M `usearch` re-measure (open question above;
      Flight 4 DD-12) and, from Flight 4, rendering `folders[].watch` /
      `watch_error` and the `monitoring` toggle.
