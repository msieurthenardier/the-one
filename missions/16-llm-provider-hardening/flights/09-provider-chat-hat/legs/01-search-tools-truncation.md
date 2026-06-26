# Leg: search-tools-truncation

**Status**: landed
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

> **Landed (code merged in 0.2.10), pending live re-verify.** Implementation complete,
> unit tests green (`tests/test_search_tools.py` 54/54). Final `completed` transition
> waits on the installed-app verify (a fresh Sonos Agent chat finds & calls
> `set_volume`) once the 0.2.10 installer is built and installed.

## Objective
Make `search_tools` (a) always surface tools whose **name** matches a query token
even when more than `_MAX_SEARCH_RESULTS` tools match, and (b) report an honest
**truncation signal** with the real pre-cap total so the model re-searches instead of
concluding a tool doesn't exist.

## Context
- Fixes flight finding **F09-01** (see flight-log): the Sonos Agent (`ministral-3:8b`,
  Ollama) reported only 8 of the Sonos MCP server's 37 tools and insisted `set_volume`
  did not exist. Root cause is the `_MAX_SEARCH_RESULTS = 8` cap in
  `the_one/tools/_search_tools.py` silently dropping lower-ranked matches, with no
  honest total reported and name matches not outranking description-only matches.
- Operator-chosen fix shape (F09 triage): **signal + exact-name guarantee** — keep a
  focused result set for small models, but guarantee name matches and tell the model
  when results were truncated.
- Mechanism is provider-agnostic (lazy tool-discovery visibility filter in
  `agent/core.py` `_compute_visible_schemas`), but the fix lives entirely in the
  search-tools layer. No `LLMProvider`-contract impact.
- Current state already has a *weak* `capped` flag in `_format_result` that appends
  "(top matches)", but `_filter_candidates` applies the cap internally and discards the
  pre-cap count, so the true total ("8 of 37") cannot be reported; and `_match_score`
  scores name and description hits identically, so name matches do not outrank
  description-only matches.

## Inputs
- `the_one/tools/_search_tools.py` exists with `_filter_candidates`, `_match_score`,
  `_format_result`, `SearchTools.execute`, and `_MAX_SEARCH_RESULTS = 8`.
- `tests/test_search_tools.py` exists with cap/ranking coverage (incl. the
  "schema beyond position 8 is dropped" test at ~`:941-984`).

## Outputs
- `_search_tools.py`: name-token matches are guaranteed in results and ranked above
  description-only matches; the cap path reports the true pre-cap total; the result
  string instructs the model how to recover.
- `tests/test_search_tools.py`: updated/added coverage for the guarantee + signal.

## Acceptance Criteria
- [ ] A query whose token is a substring of a tool's **name** (e.g. `"volume"` →
      `set_volume`) returns that tool even when >8 tools match the query.
- [ ] When a query matches more tools than are returned, the result string states the
      **true total** (e.g. "showing 8 of 14") and tells the model it can narrow the
      query or search a tool name directly. The reported total is the real pre-cap
      match count, not a heuristic.
- [ ] Name-token matches are ranked above description-only matches (a tool matching in
      its name is not pushed out by tools matching only in their description).
- [ ] Empty-query behavior is unchanged (returns all non-excluded schemas, uncapped,
      original order — the `SEARCH_TOOLS_SCHEMA` contract invariant).
- [ ] `search_tools` is still excluded from results; no duplicate schemas.
- [ ] `pytest tests/test_search_tools.py` passes; full `make test` (or project
      equivalent) green.
- [ ] Live re-verify on the installed app: in a fresh Sonos Agent chat, asking to set a
      speaker's volume results in the agent finding and calling `set_volume` (no "there
      is no set_volume tool").

## Verification Steps
- `cd ~/projects/the-one && pytest tests/test_search_tools.py -q`
- Full suite: `make test` (or the project's standard command).
- Manual (installed app, after rebuild/reinstall per flight DD2): new Sonos Agent chat
  → "turn the kitchen down to 20" → agent calls `mcp__Sonos__set_volume`.

## Implementation Guidance

1. **Return the pre-cap total from the filter.**
   - Change `_filter_candidates` to return both the (capped) match list and the total
     number of matches before the cap — e.g. `tuple[list[dict], int]` — so callers can
     report an honest "N of M". Keep the empty-query path returning all matches with
     total == len (no cap).

2. **Guarantee name-token matches and rank them first.**
   - Distinguish a **name match** (a query token, or the fallback whole phrase, is a
     substring of the tool's `name`) from a description-only match.
   - Rank name matches above description-only matches (e.g. add a large name-match
     weight to the score, or partition into name-matches then description-matches).
   - When building the capped result, include **all** name matches even if they exceed
     the cap (recall wins for explicit name hits), then fill any remaining slots with
     the top description-only matches. (Document the chosen rule in the module
     docstring's "Matching semantics" block.)

3. **Honest truncation signal in `_format_result`.**
   - Replace the heuristic `capped = len(matches) == _MAX_SEARCH_RESULTS` with the real
     pre-cap total threaded from `_filter_candidates`.
   - When truncated, phrase the result so a small model can act, e.g.:
     `Found 8 of 14 tools matching 'volume' (showing the most relevant — narrow your
     query or search a specific tool name to see the rest): ...`

4. **Wire `execute`.**
   - Use the returned total; set the signal when total > returned count. Preserve the
     "No tools found matching {query!r}." path.

5. **Tests.**
   - Update the existing "beyond position 8 is dropped" test to reflect the new
     contract (a name match beyond position 8 is **kept**; a description-only match
     beyond the cap is still dropped but the total is reported).
   - Add: name-match guarantee with >8 matches; honest "N of M" total in the string;
     name-over-description ranking; empty-query unchanged.

## Edge Cases
- **More name matches than the cap**: include all name matches (cap is a floor for
  name hits, not a hard ceiling) — the focused-result rationale yields to "the model
  asked for this by name".
- **Multi-token query** where a token matches a name and another matches descriptions:
  treat as a name match (it has a name hit); rank above pure description matches.
- **Empty query**: unchanged — uncapped, original order, total == returned.
- **Stopword/short-token-only query**: existing whole-phrase fallback still applies;
  the name-vs-description distinction uses the fallback phrase against `name`.

## Files Affected
- `the_one/tools/_search_tools.py` — `_filter_candidates`, `_match_score`/ranking,
  `_format_result`, `SearchTools.execute`, module docstring "Matching semantics".
- `tests/test_search_tools.py` — updated + new cases.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md (F09-01 → resolved, with the fix summary)
- [ ] Set this leg's status to `completed`
- [ ] Check off / add this leg in flight.md
- [ ] Live re-verify on the installed app (rebuild/reinstall per DD2)
- [ ] Commit code + artifacts together
