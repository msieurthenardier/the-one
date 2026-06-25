# Flight Debrief: Agent-loop Resource Governance & Context-budget Management

**Date**: 2026-06-25
**Flight**: [Agent-loop Resource Governance & Context-budget Management](flight.md)
**Status**: landed
**Duration**: 2026-06-23 (planned) → 2026-06-25 (landed)
**Legs Completed**: 6 of 6 (optional leg 7 HAT moot — covered by the live behavior test)

## Outcome Assessment

### Objectives Achieved
The flight installed the governance layer the F07 debrief (Recommendation 1) identified — the
agent loop had no governance over what tools pull into the LLM context. Delivered:
- A single **direction-aware context-budget governor** at `_execute_tool` bounding every tool
  result to a model-derived budget (`_governor.py` + `core.py`); per-tool LLM-facing caps
  retired (`tool_text_cap_bytes` removed; `output_cap_bytes` reclassified as a transport
  ceiling); transport/OOM safety caps kept. Single `bytes_per_token` accessor on the base.
- A **search-backend registry** with an honest-empty typed-error contract + 5 engines
  (DuckDuckGo keyless default + SearXNG + Google PSE + Brave + Tavily).
- **Encrypted tool-config secret persistence** (schema v32 `config`+`secrets` split, generic
  over any `secret:true`-marked field) fed to the resolver via `merged_config()`.
- A **search-config admin UI** (engine dropdown, generic `show_if` per-engine visibility,
  masked password inputs + eye-toggle).
- **Config-driven overlay thresholds** + a non-color screen-reader `aria-label`.

Verified live by the `agent-governance-and-search` Witnessed behavior test (**9/9 PASS**),
each checkpoint on a hard observable (the governor bound to exactly 262,144 B with its marker;
the overlay warn color + non-color aria-label; an encrypted masked-key round-trip; honest
search with zero fabricated URLs). The flight's robustness criterion is met.

### Mission Criteria Advanced
Like F07, this advances no *named* provider-layer criterion — it is a robustness addition from
the F07 debrief. It closes the F07 "No results found" known issue (DD3 honest-empty +
configurable backend) and supersedes F07 Recommendation 4 (surface `tool_text_cap_bytes` in
admin — now moot, the field is gone). Compaction remains the deferred own-mission gap.

## What Went Well
- **Per-leg design-review-before-implement caught every material defect before code.** The
  strongest cases: leg-3's keystone — the pre-review design merged secrets in
  `ToolConfigRepository.list_all()`, a method with **zero production callers** (the real feed
  is `factory.py` `merged_config()`); had it shipped, keys would have encrypted but never
  reached backends. Leg-2's false SSRF-client premise. Leg-4's never-wired string-enum
  dropdown (`search_backend` silently rendered as free-text). Leg-1's F07-repeat field-count
  guard. The strict 2nd-cycle-skip criterion ("only when adopting the reviewer's explicit
  recommendations verbatim") worked.
- **Largest single-flight test growth in M16**: +82 passing (3492 → **3574**), no new flakes,
  wall-clock 325s (inside the historical 296–346s band). 21 governor + 38 search-backend + 15
  persistence/migration + 9 config-endpoint tests.
- **Live Witnessed verification** with a low synthetic threshold (`THE_ONE_CONTEXT_WARN_PCT=5`)
  made the overlay warn transition observable in a short real conversation, and judged the
  governor/a11y/honesty on DOM/trace observables, not model self-report. Run on an **isolated**
  instance — the operator's daily-driver was never touched.
- **Clean generalizations**: the `secret:true`-marker-driven secret split and the generic
  `show_if` mechanism are reusable beyond web_search; the `bytes_per_token` promotion removed
  two duplicate accessors.

## What Could Be Improved

### Process
- **Config migrations broke the browser suite three times** (F06 once, F08 twice) because
  legs 1-3 ran `make test-unit` only — `test_flow_admin_tools_editor.py` was RED the whole
  time legs 2-3 were implemented, not caught until leg 4. Containment was reactive (design
  review) rather than proactive. → make a standing rule (below).
- **Search work was a 1-leg estimate that became 3 legs + browser-test repair.** Part scope
  expansion (appropriate), part underestimate of the honest-empty contract change + DDG
  no-results decision + SSRF fix + field-count/test-repointing fallout.

### Technical
- **`SearchError` docstring is malformed** (`_search_backends.py:84-89`) — parenthesized
  string-concatenation expression instead of a bare docstring; `__doc__` is effectively
  unusable. One-line fix.
- **`build_search_backend` fallback asymmetry**: a selected-but-unconfigured *named* engine
  raises `SearchUnavailableError` (honest), but an *unrecognized* engine name silently falls
  back to DDG — hiding a typo in `THE_ONE_SEARCH_BACKEND` or a stale config. Consider
  raise-or-warn on unknown name.
- **aiosqlite `Event loop is closed` teardown warnings** (18 this run) have ridden through
  F05/F06/F07/F08 debriefs unaddressed — carrying cost now exceeds the fix.
- **Surviving two-gate truncation for web text** (streaming abort → governor) — the middle
  `_truncate_response`/`output_cap_bytes` axis interaction with the governor is untested where
  an operator lowers `output_cap_bytes` below the 256 KB governor ceiling (default no-op).

### Documentation
- `secret:true` and `show_if` `json_schema_extra` keys are now deployed conventions but
  undocumented in the tool-authorship guide (`agents.md`) — future authors will rediscover by
  trial/error or invent a parallel convention.
- The governor covers the `ToolResult` leg, NOT the read-into-memory leg (`DownloadFileTool`
  is correctly ungoverned because it returns a short string) — the axis distinction needs a
  doc note so a future read-and-return tool author doesn't assume governor coverage.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Search work expanded 1 leg → registry+persistence+UI (3 legs) | Operator mid-flight pivot to a configurable 5-engine admin surface; split along backend/UI seam for reviewable scope | Yes — split persistence/UI for any "config + admin" feature |
| HIGH-2: reclassify `output_cap_bytes`, don't remove | Lower blast radius (range/Substitute/UI tests stay); governor layers on top | Yes — prefer reclassify over remove when a cap has live tests/UI |
| Leg-3 keystone re-targeted `list_all()` → `factory.merged_config()` | `list_all()` had zero production callers | n/a (a one-off correction; the lesson is "verify the consumer exists") |
| Leg-4 added a string-enum `<select>` branch | DD3 wrongly assumed `ui_hint:dropdown` rendered for free; it was gated on `ftype==='integer'` | n/a (gap fix) |
| Behavior-test URL/model hardened mid-run | Stale catalog model id (404) + gutenberg tool-timeout + transport-cap-vs-governor-ceiling | Yes — pin a deterministic 256KB–1MB URL + verify model id live (below) |

## Key Learnings
- **Verify the consumer exists before wiring a producer.** The leg-3 `list_all()` miss and the
  leg-4 dropdown gap are the same root: pre-flight recon read the *shape* of a surface without
  confirming the *path* end-to-end. Recon for an integration leg should trace the actual call
  chain (who calls `list_all()`? what `ftype` does `renderField` branch on?), not just the
  target's definition.
- **Model-catalog drift is an unresolved structural risk** (F5 did catalog work; F8's behavior
  test still 404'd on a stale id). Model-dependent behavior tests should verify the model id is
  live before step 1.
- **Low synthetic thresholds are the right apparatus for telemetry/threshold features** — make
  the transition reachable without consuming a real context window.
- The per-result governor is the **prerequisite** that makes the deferred compaction mission
  tractable — without it, even a compacted conversation could be re-poisoned by the next large
  tool result.

## Recommendations
1. **Standing rule: any leg that migrates a tool to a new Config class or adds/renames Config
   fields runs `make test-browser` before closing** (or the spec explicitly assigns the
   browser-test repair to a named downstream leg before the batch commits). This pattern has
   broken the browser suite 3× across F06/F08.
2. **Add "verify the model id is live" as a standing precondition in the behavior-test spec
   template** for any model-dependent test — closes the F5-lineage catalog-drift gap that
   stranded the F8 verify run mid-step.
3. **Fix the `SearchError` docstring** (`_search_backends.py:84-89`) — trivial, restores
   `__doc__`. Bundle with a `web.py` gate-order doc comment + `agents.md` notes on `secret:true`
   / `show_if` / the governor's `ToolResult`-only axis.
4. **Resolve the aiosqlite teardown warnings** (open since F05) — a `pytest.ini`/`asyncio_mode`
   filter; the noise-in-every-run cost now exceeds the fix.
5. **Consider a shared `merged_config()`/secret-split utility** — the pattern is now deployed
   identically on `MCPSource`, `Connector`, `ToolConfig`; a mixin/helper prevents a 4th
   implementation drifting (e.g. forgetting "secrets win on collision").

## Action Items
- [ ] Fix `SearchError` docstring (`_search_backends.py:84-89`). *(trivial — fold into next maintenance flight)*
- [ ] Adopt the "Config migration → run browser suite" leg rule (process; mission-debrief carry).
- [ ] Add "verify model id live" to the behavior-test spec template (mission-control side).
- [ ] Resolve aiosqlite `Event loop is closed` teardown warnings (open since F05).
- [ ] Document `secret:true`, `show_if`, and the governor's `ToolResult`-only axis in `agents.md`.
- [ ] Decide raise-vs-fallback for `build_search_backend` unknown-engine-name.
- [ ] **Residual "Stop" button** not torn down at stream end (pre-existing, F07-era; cosmetic) — correlate with `chat-loop-hang-and-cancel`; carry to `/mission-debrief`.
- [ ] **Conversation-level governor accounting** (cumulative pressure across many tool calls in a turn) — the per-result bound is in; cumulative is the compaction-mission prerequisite.
