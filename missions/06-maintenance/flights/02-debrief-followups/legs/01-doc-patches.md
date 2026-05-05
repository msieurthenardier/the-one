# Leg: 01-doc-patches

**Status**: completed
**Flight**: [Debrief Follow-ups](../flight.md)

## Objective

Land 3 small documentation patches surfaced by Flight 01's debrief as a single atomic leg: 2 `agents.md` entries for the new web-layer surfaces and a `CLAUDE.md` callout for the `THE_ONE_ORIGIN_ALLOWLIST` env var. The 4th item from the debrief — `api.py:810` rationale comment — was discovered during design review to **already exist** as a 5-line block at lines 805-809, shipped by Flight 01 Leg 05. That checklist item is therefore retired as already-satisfied; no code change in this leg.

## Context

Flight 01 debrief — "Documentation" section action items:

- **agents.md missing entries**: `OriginAllowlistMiddleware` and `_is_safe_provider_url` are new web-layer surfaces but `agents.md` (the architectural reference) has no entries for them.
- **`THE_ONE_ORIGIN_ALLOWLIST` only documented in `.env.example`** (commented). Neither `CLAUDE.md` nor `agents.md` calls it out. An operator reading either doc top-to-bottom would not learn the knob exists.
- **`api.py:810` rationale comment** — design-review surfaced that this is a duplicate concern: the comment block at lines 805-809 already explains the resolved-`base_url` post-`model_copy(update=data)` rationale more thoroughly than the leg's proposed one-liner. Item retired; no action.

## Inputs

- `the_one/agents.md` (existing; verified L93-98 module-map for `the_one/interfaces/`, L239-251 "Web tools (F5)" section ending at L250 before "SearchBackend Protocol (F5)" at L252, L1121-1141 "Provider type extension checklist")
- `CLAUDE.md` (existing; verified "Security posture" section spans L318-320 followed by `## Conventions` at L322; existing `### __MASKED__ sentinel for API key updates` heading at L76 — the cross-link target for the new `_is_safe_provider_url` entry)
- `the_one/interfaces/web/api.py` (existing; `_is_safe_provider_url` defined L643-675; called inside `_URL_VALIDATION_SKIPPED_TYPES`-guarded blocks at L772 / L811 / L864 — line numbers verified during design review)
- `the_one/interfaces/web/middleware.py` (existing; `OriginAllowlistMiddleware` at line 28)
- `.env.example` (existing; commented `THE_ONE_ORIGIN_ALLOWLIST` entry from Flight 01 Leg 05)
- `SECURITY-MODEL.md` (existing; created in Flight 01 Leg 07)

## Outputs

- `the_one/agents.md` has a new `### Origin allowlist (M06 F1 L5)` subsection inserted after L250 (end of "Web tools (F5)" block) and before L252 ("### SearchBackend Protocol (F5)"). Maintains SSRF-family adjacency.
- `the_one/agents.md` has a new `web/middleware.py` row added to the `the_one/interfaces/` module-map table at L93-98.
- `the_one/agents.md` has a new `### Provider URL validation (M06 F1 L5)` subsection inserted at the very top of `## Provider type extension checklist` (after L1125, before the numbered list at L1127).
- `CLAUDE.md` has a 2-3 line `THE_ONE_ORIGIN_ALLOWLIST` callout appended after L320 (last line of "Security posture" section), before `## Conventions` at L322.

## Acceptance Criteria

- [x] `grep "OriginAllowlistMiddleware\|Origin allowlist" the_one/agents.md` returns ≥1 architectural-context match
- [x] `grep "_is_safe_provider_url\|Provider URL validation" the_one/agents.md` returns ≥1 architectural-context match
- [x] `grep "web/middleware.py" the_one/agents.md` returns ≥1 match (module-map row)
- [x] `grep "THE_ONE_ORIGIN_ALLOWLIST" CLAUDE.md` returns ≥1 match
- [x] All entries are concise (≤8 lines per `agents.md` subsection, ≤3 lines for the `CLAUDE.md` callout)
- [x] Documentation reflects code accurately: the `_is_safe_provider_url` entry must describe the actual exemption set (`localhost` / `127.0.0.1` / `::1` / `*.localdomain` only — NOT RFC1918 / link-local / 0.0.0.0) AND the type-level skip via `_URL_VALIDATION_SKIPPED_TYPES = {"mock", "ollama"}`
- [x] No duplication: `agents.md` entries reference `SECURITY-MODEL.md` for policy details; mechanism details (port-wildcard matcher, digit-strict check, exemption set) live ONLY in `agents.md`. The `_is_safe_provider_url` entry cross-links to `### __MASKED__ sentinel for API key updates` in `CLAUDE.md` (L76).
- [x] No regression: `pytest -q --ignore=tests/browser --timeout=120` passes; `ruff check` + `ruff format --check` pass

## Verification Steps

- `cd /home/cprch/projects/the-one && grep -B 2 -A 10 "Origin allowlist (M06" the_one/agents.md | head -30`
- `cd /home/cprch/projects/the-one && grep -B 2 -A 8 "Provider URL validation (M06" the_one/agents.md | head -25`
- `cd /home/cprch/projects/the-one && grep "web/middleware.py" the_one/agents.md`
- `cd /home/cprch/projects/the-one && grep -B 1 -A 3 "THE_ONE_ORIGIN_ALLOWLIST" CLAUDE.md`
- `cd /home/cprch/projects/the-one && pytest -q --ignore=tests/browser --timeout=120 2>&1 | tail -10`
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/`

## Implementation Guidance

> **Note**: design review verified all line numbers below as of branch `flight/02-debrief-followups` HEAD. If the working tree changes before this leg runs, re-grep before locking edits — the methodology learning from Flight 1.

1. **Add `web/middleware.py` to the `the_one/interfaces/` module-map table at L93-98**:
   - Current rows are `cli.py` and `web/app.py`. Insert a new row between them or after `web/app.py`:
     ```markdown
     | `web/middleware.py` | `OriginAllowlistMiddleware`, `_is_safe_origin` | F1 L5 — ASGI middleware gating state-mutating HTTP + WS upgrades by `Origin`/`Referer` against `THE_ONE_ORIGIN_ALLOWLIST` |
     ```

2. **Add `### Origin allowlist (M06 F1 L5)` subsection between L250 and L252 in `agents.md`** (after Web tools, before SearchBackend Protocol — same SSRF/security family):
   ```markdown
   ### Origin allowlist (M06 F1 L5)

   `OriginAllowlistMiddleware` (`the_one/interfaces/web/middleware.py`) is an ASGI middleware that gates state-mutating HTTP requests (`POST` / `PUT` / `PATCH` / `DELETE`) and WebSocket upgrades by `Origin` / `Referer` against `THE_ONE_ORIGIN_ALLOWLIST`. Default allowlist is `http://127.0.0.1:*` and `http://localhost:*` — port-wildcard with strict-digits enforcement to reject `http://127.0.0.1.evil.com`-class confusion attacks. Missing-Origin requests pass through (server-to-server clients are NOT browser-originating). WS upgrade gating fires at the ASGI layer with `{"type": "websocket.close", "code": 1008}` BEFORE the route handler can `accept()` — `Depends()` cannot do this because it runs post-`accept()`. Policy and rationale: `SECURITY-MODEL.md`.
   ```

3. **Add `### Provider URL validation (M06 F1 L5)` subsection at the top of `## Provider type extension checklist`** (insert immediately after L1125 history note, before the numbered list at L1127):
   ```markdown
   ### Provider URL validation (M06 F1 L5)

   `_is_safe_provider_url` (`the_one/interfaces/web/api.py`) enforces `https://` for non-localhost hosts on LLM provider `base_url`. Called at endpoint time from `create_provider` (L772), `update_provider` (L811), and `test_provider` (L864) — NOT a Pydantic validator. Reason: `update_provider` accepts `__MASKED__` for unchanged fields (see `### __MASKED__ sentinel for API key updates` in `CLAUDE.md`); the validator must run on the **resolved** `base_url` post-`model_copy(update=data)`, not the request payload. Two skip layers: (a) provider types in `_URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})` bypass URL validation entirely; (b) for the remaining types, `http://` is allowed only when the host is `localhost`, `127.0.0.1`, `::1`, or any `*.localdomain` name. RFC1918 / link-local / `0.0.0.0` are NOT exempt — they require `https://`.
   ```

4. **Append `THE_ONE_ORIGIN_ALLOWLIST` callout to `CLAUDE.md`** — insert immediately after L320 (last line of "Security posture" section), before the `## Conventions` heading at L322. The result should look like:
   ```markdown
   ## Security posture

   See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the project's threat model and intentional security choices (no-auth-by-design, single-user local-only, Origin-allowlist mitigation, SSRF/subprocess boundaries).

   **Origin allowlist override**: set `THE_ONE_ORIGIN_ALLOWLIST` to a comma-separated list of `scheme://host:port` patterns (port supports `*` wildcard) to extend the default `http://127.0.0.1:*` / `http://localhost:*` allowlist. See `SECURITY-MODEL.md` for the threat-model context.

   ## Conventions
   ```

5. **Verify**:
   - All grep checks return matches.
   - Tests + ruff still green (this leg adds no semantic code change — purely docs).

## Edge Cases

- **`agents.md` may have grown**: re-grep cited line numbers (L93-98 module-map, L250-252 Web-tools/SearchBackend boundary, L1125 history-note line) before locking edits. The design-review pass verified them as of `flight/02-debrief-followups` HEAD; rebases or other concurrent edits could shift them.
- **CLAUDE.md "Security posture" section is single-paragraph (3 lines)**: the only natural insertion is appending after L320. Leg pins this explicitly to remove ambiguity.
- **Ruff format may want to reflow markdown**: ruff doesn't format `.md` files by default — this is a `.md`+code-comment-free change; ruff should be a no-op. Run `ruff check` + `ruff format --check` regardless to catch any incidental Python file modifications.

## Files Affected

- `the_one/agents.md` — 2 new `### ...` subsections + 1 new module-map table row (~6-8 lines each)
- `CLAUDE.md` — 2-3 line callout appended to "Security posture" section
- *(no `api.py` change — the `_is_safe_provider_url` rationale comment already exists at L805-809 from Flight 01 Leg 05)*

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All 4 grep verifications pass
- [x] `pytest -q --ignore=tests/browser --timeout=120` passes
- [x] `ruff check` + `ruff format --check` pass
- [x] Update flight-log.md with leg progress entry (note the api.py "already-satisfied" finding)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] DO NOT commit — deferred to flight close
