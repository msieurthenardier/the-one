# Leg: search-query-tokenization

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **Provenance.** This change was implemented as an in-flight adaptation during the 08A trial (the degraded
> blind-start discovery hop needs `search_tools` to resolve natural-language queries). 08A's degraded-discovery
> *approach* was abandoned, but this search improvement is **independently valuable** — it fixes the same
> brittleness for the capable path — so it is retained and documented here as its own leg. Code + tests already
> landed on `flight/03-degraded-over-routing`.

## Objective

Make `search_tools` resolve multi-word natural-language queries by tokenizing the query (match tools whose
name+description contains any query token, ranked by token-overlap, capped to the top N) instead of requiring
the whole query phrase to appear as a contiguous substring.

## Context

- **Problem.** `the_one/tools/_search_tools.py:_filter_candidates` matched `query.lower() in
  (name + " " + description).lower()` — a whole-phrase substring test. A query like "list files directory" or
  "run shell command" never appears verbatim in a single tool's text, so the search returned nothing, while a
  single keyword ("shell", "file") matched. This hurt any caller that searches in natural language — the 08A
  degraded hop made it visible, but the capable path has the same brittleness for verbose queries.
- **Fix.** Tokenize the query; match a tool if ANY token (after dropping <3-char tokens and a small stopword
  set) substring-hits its name+description; rank by distinct-token-overlap (desc, stable); cap non-empty-query
  results to the top `_MAX_SEARCH_RESULTS` (8). Empty query is exempt from the cap (the "list everything"
  affordance is preserved). Stopword-only queries fall back to the original-phrase substring (no catalog dump).

## Outputs

- `the_one/tools/_search_tools.py` — `_tokenize_query`, `_match_score`, tokenized `_filter_candidates` with
  ranking + `_MAX_SEARCH_RESULTS=8` cap (empty-query exempt); `_format_result` shows "(top matches)" when
  capped.
- `tests/test_search_tools.py` — tokenization, ranking, cap, empty-query-exemption, stopword-fallback, and
  MCP-source tokenized-match tests.

## Acceptance Criteria

- [x] Multi-word natural-language queries resolve: "run shell command" → shell/shell_session_*/python_exec;
      "list files directory" → list_dir/glob/read_file/etc. Unit-tested.
- [x] Ranking by distinct-token-overlap (a 2-token match ranks above a 1-token match). Unit-tested.
- [x] Non-empty queries capped to top `_MAX_SEARCH_RESULTS` (8); **empty query NOT capped** (returns all
      non-excluded). Unit-tested.
- [x] Stopword-only / empty-after-filter query falls back to whole-phrase substring (does not dump the
      catalog). Unit-tested.
- [x] `search_tools` itself still excluded; dedup + `_format_result` shape preserved; single-keyword queries
      behave as before. Unit-tested.
- [x] `make test-unit` green — **3375 passed / 10 skipped** (no regressions).

## Files Affected

- `the_one/tools/_search_tools.py` — tokenized matching + ranking + cap.
- `tests/test_search_tools.py` — new/extended tests.

## Citation Audit

2 citations verified at leg design time: `the_one/tools/_search_tools.py:_filter_candidates` (tokenized +
ranked + capped — confirmed live) and `_MAX_SEARCH_RESULTS` (module constant = 8). Implemented + tested on
branch `flight/03-degraded-over-routing`.
