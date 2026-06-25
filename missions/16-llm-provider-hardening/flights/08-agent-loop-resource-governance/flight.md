# Flight: Agent-loop Resource Governance & Context-budget Management

**Status**: landed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
Like Flight 07, this does not advance a *named* provider-layer criterion — it is a
robustness addition, sourced from the F07 debrief (Recommendation 1). The F07 debrief
established that the three chat-loop defects are **one theme**: the agent loop has no
governance over what tools pull into the LLM context. They compound — `web_search`
returns nothing → the model guesses URLs → it scrapes large/streaming pages → hang
(fixed F07) or context-poison (fixed 0.2.6). This flight installs the governance layer.

- [x] No single tool result, regardless of source, can consume a disproportionate
      share of the model's context window; the operator can see when the conversation
      is approaching the context limit. **(Verified live — behavior test 9/9 PASS:
      governor bound to 262,144 B + overlay warn with non-color aria-label.)**

---

## Pre-Flight

### Objective
Install a single **context-budget governor** at the agent's tool-dispatch boundary so
**every** tool result is bounded (derived from the active model's context window)
before it enters the conversation — replacing today's inconsistent per-tool LLM-facing
caps. Add **conversation-level accounting** surfaced in the existing telemetry overlay
(color it orange→red as the context fills), as a warn-only guardrail. And make
`web_search` **reliable** (configurable backend; honest empty results) so the model
stops guessing URLs in the first place. Context **compaction** (eviction/summarization)
is explicitly out of scope — deferred to its own future mission.

### Open Questions
- [x] **Governor vs. per-tool caps** → DD1. Resolved (operator): central governor,
      retire the per-tool *LLM-facing* caps (transport/OOM safety caps stay).
- [x] **Conversation-level accounting scope** → DD2. Resolved (operator): full
      accounting + warn via the telemetry overlay (orange/red); NO eviction.
- [x] **web_search fix** → DD3. Resolved (operator): configurable backend,
      honest-empty default.
- [x] **Budget unit** → DD4. Resolved: bytes-with-heuristic (`BYTES_PER_TOKEN`), no
      tokenizer dependency.
- [ ] **Per-result budget fraction** — what share of the window may one tool result
      occupy (e.g. 1/8)? And the warn/critical overlay thresholds (e.g. 70% / 90%)?
      Resolve at leg design with a sensible default + env override.
- [ ] **Keyed search backend choice** — which provider (Brave / Tavily / SerpAPI) for
      the optional keyed path, and where the key lives (settings/env). DDG stays the
      keyless default; the keyed path is optional. Confirm at leg 2 design.

### Design Decisions

**DD1 — Central context-budget governor at `_execute_tool`**: every `ToolResult.content`
funnels through `_execute_tool` (core.py:535, returns `ToolResult(content=output)` at
:555). Insert a governor there that **head-preserves** `content` to a per-result budget
= `f(self.llm.max_context_tokens)` — a fraction of the model's window converted to bytes
via the `BYTES_PER_TOKEN` heuristic — with an absolute floor/ceiling, appending a
truncation marker. Applies uniformly to **all** tools (web, filesystem, shell, MCP,
future). **Retire the per-tool *LLM-facing* caps** (`tool_text_cap_bytes`; the
filesystem read cap's context role) now that the governor is the single guarantee.
- **Keep the safety caps**: the web tools' 1 MB `response_size_cap_bytes` streaming
  hard-abort (anti-hang/OOM — a transport guard, NOT an LLM cap) and the filesystem
  file-size read guard remain. The governor governs *what reaches the model*; the
  safety caps govern *what the process buffers/reads*. Different axes.
- Rationale: one boundary, one rule, derived from the actual window — no future tool
  can re-introduce the F07 context-poison by forgetting to add its own cap.
- Trade-off: a per-result cap can truncate a legitimately large-but-relevant result;
  the fraction is tunable, and conversation accounting (DD2) surfaces pressure.

**DD2 — Conversation accounting + telemetry-overlay warn (no eviction)**: the chat
telemetry overlay (F6/F7) already renders `context_tokens / max_context_tokens` as a
bar. Add **threshold coloring** — orange at a warn fraction (~70%), red at a critical
fraction (~90%) — so the operator sees the conversation filling. Warn-only: NO
automatic eviction or summarization.
- Rationale: cheap (leverages existing telemetry), gives observability + a guardrail,
  and lets us see how often the limit is approached before investing in compaction.
- Trade-off: it informs but does not *recover* a turn near the limit — that's the
  deferred compaction work.
- **Deferred to its own future mission**: context **compaction** (evict old tool
  results / summarize earlier turns). It's a subsystem (tool_use↔tool_result pairing
  constraints, persistence-codec impact, summary cost/latency/quality) — recorded as a
  mission-level backlog seed, not a Flight 8/9 leg.

**DD3 — Pluggable search backend, honest-empty default**: `_search_backends.py` already
has a `SearchBackend` Protocol + `DDGSearchBackend`. Make the backend **selectable via
config** (backend name + optional api_key). DDG stays the **keyless default** but must
**surface empty/blocked honestly** — distinguish "genuinely no results" from
"throttled/blocked/parse-failed" instead of a silent "No results found" (which is what
made the model guess URLs). Add an **optional keyed backend** (provider TBD at leg 2)
used only when a key is configured. No key required to ship.
- Rationale: the upstream fix — reliable search reduces the URL-guessing pressure that
  triggers the scrape-large-page failure mode.
- Trade-off: a keyed backend adds a secret + a dependency; gated behind config so the
  default stays keyless.
- **★ Refinement (operator, 2026-06-23):** "optional keyed backend" widened to a
  **registry of selectable engines** configured **inside the `web_search` tool's own
  config** (rendered by the existing schema-driven tools-admin section). Ship roster:
  DuckDuckGo (keyless default) + SearXNG (self-hosted URL) + Google PSE (key + CSE id) +
  Brave (key) + Tavily (key). DDG stays the zero-config default; keyed engines activate
  only when configured. The honest-empty contract is unchanged — it's the substance.
  Adds a tool-config **secret-at-rest** requirement (see leg `search-config-admin`).
  This is the admin surface the original `_search_backends.py` docstring reserved for
  "F6 admin" — now being built.

**DD4 — Budget in bytes via the `BYTES_PER_TOKEN` heuristic**, not true token counts —
no tokenizer dependency, consistent with the existing streaming/usage heuristics.
- Trade-off: approximate (±) vs. exact token counts; acceptable for a budget cap, and
  it inherits the same heuristic the usage telemetry already uses.

**DD5 — Verification apparatus**: unit tests for the governor (a large *valid* result
is capped to the model-derived budget; small results pass; cap scales with
`max_context_tokens`) generalized **across tool types** (web, filesystem, shell) — the
explicit F07 verification miss. Plus a behavior test (real :8485 instance) for the
overlay color transitions + "a stream-hunt conversation no longer degenerates."
- **Act**: WS driver / browser drive a conversation that returns a large tool result.
- **Observe**: the returned `ToolResult` content size (asserted in unit tests via the
  governor); the overlay's color class + `context_tokens` (DOM, via chrome-devtools).

### Prerequisites
- [ ] Dev instance runnable on :8485 with an agent that has web + filesystem tools.
- [ ] `self.llm.max_context_tokens` is resolved before the first tool dispatch
      (it resolves lazily on the first complete/stream call — confirm the governor has
      a sane fallback if a tool somehow dispatches pre-resolution).
- [ ] If a keyed search backend is chosen: an API key + a config/secret slot.
- [ ] No new network service/port (governor + accounting are in-process; search is
      outbound only).

### Pre-Flight Checklist
- [x] Open questions resolved (the two remaining — per-result fraction/thresholds and
      keyed-backend choice — resolve inside their legs by design)
- [x] Design decisions documented (DD1–DD5)
- [ ] Prerequisites verified
- [x] Validation approach defined (unit across tool types + behavior test + optional HAT)
- [ ] Legs defined (drafted below)

---

## In-Flight

### Technical Approach
1. **agent/core.py** — a governor applied to `ToolResult.content` in `_execute_tool`
   (and the error-result paths), head-preserving to `budget_bytes(self.llm.max_context_tokens)`.
2. **tools/_web_config.py, tools/filesystem.py** — retire the LLM-facing caps
   (`tool_text_cap_bytes`; the read cap's context role) now superseded by the governor;
   keep the transport/file-size safety caps.
3. **tools/_search_backends.py + config** — pluggable backend selection, honest-empty
   DDG, optional keyed backend.
4. **interfaces/web/static/js/areas/chat.js + chat.css** — threshold coloring on the
   telemetry overlay from the existing `context_tokens/max_context_tokens` fraction.

### Checkpoints
- [ ] Any tool result (web/fs/shell/MCP) returned to the model is bounded to a
      model-derived budget; the per-tool LLM-facing caps are gone (governor is the rule).
- [ ] A large *valid* fetch/read no longer poisons context (asserted on the returned
      size, generalized across tool types).
- [ ] The telemetry overlay turns orange/red as `context_tokens` approaches the window.
- [ ] `web_search` surfaces empty/blocked honestly; an optional keyed backend works
      when configured; DDG default still works keyless.
- [ ] Full suite green at/above the M16 baseline, no new flakes; behavior test passes.

### Adaptation Criteria
**Divert if**:
- Retiring a per-tool LLM cap turns out to also be load-bearing as a safety guard for
  that tool (re-scope: keep it as a safety cap, governor still adds the LLM bound).

**Acceptable variations**:
- Exact per-result budget fraction + overlay thresholds (env-overridable).
- Keyed search provider + key location.
- Whether the governor lives inline in `_execute_tool` or a small helper module.

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.
>
> **★ Scope expansion (operator, 2026-06-23, mid-flight).** The original
> `search-backend-pluggable` leg grew: rather than DDG + one optional keyed backend, the
> operator wants `web_search` to be **fully configurable** — a registry of selectable
> engines (DuckDuckGo keyless default + SearXNG + Google PSE + Brave + Tavily) configured
> **within the built-in `web_search` tool's own config** (surfaced by the existing
> schema-driven tools-admin section, NOT a new settings page). Informed by reading
> Open WebUI's web-search subsystem (one backend per engine; honest `raise` on errors vs
> `[]` on genuine-empty; DDG keyless special-case) — which independently validates the
> honest-empty contract this leg was already going to add. This splits the search work
> into TWO legs (backend registry, then admin secret-UI + encrypted persistence). See
> the flight-log Flight Director Notes for the full pivot rationale. DD3 refined below.

- [x] `context-budget-governor` - Governor at `_execute_tool` capping every
      `ToolResult.content` to `f(max_context_tokens)` (bytes-heuristic, head-preserving,
      marker); retire the per-tool LLM-facing caps (keep safety caps). Unit tests
      across web/fs/shell: large *valid* result capped, small passes, cap scales with
      the model window, error-results bounded too.
- [x] `search-backend-registry` - Honest-empty typed-error contract
      (`SearchBlockedError`/`SearchUnavailableError`: raise on blocked/throttled/parse-
      fail, `[]` only for genuine-empty); `SearchBackend` registry; 5 engines (DDG keyless
      default + SearXNG + Google PSE + Brave + Tavily); `search_backend` selector + per-
      engine config fields on the web-search tool config; backend resolved in
      `builtins.py` from config (replacing hardcoded `DDGSearchBackend()`). Per-backend
      tests (mocked HTTP) + honest-empty + selection. **Landed 2026-06-24** (commit
      deferred to flight end; leg 3 owes the secret-at-rest encryption).
- [x] `search-config-persistence` - Encrypted tool-config secrets at rest: generic
      `config`+`secrets` split on `ToolConfigRepository` (migration v32, encryptor threaded,
      mirroring `MCPSource`/`Connector`), driven by the `secret:true` markers; tool GET
      masks secrets, PUT preserves-on-masked; the factory feed uses `ToolConfig.merged_config()`
      so the resolver gives backends the real keys. No UI. (Split from `search-config-admin`
      for reviewable scope — persistence half.) **Landed 2026-06-24** (commit deferred to
      flight end; leg `search-config-admin-ui` owes the password-field UI + conditional
      visibility).
- [x] `search-config-admin-ui` - Tools-admin secret-field rendering (`ui_hint:"password"` +
      eye-toggle + `__MASKED__` sentinel, ported from the provider editor) and conditional
      per-engine field visibility (`show_if` — show an engine's key/URL only when it's
      selected). a11y reviewer applies. (UI half.) — landed; also wired the string-enum
      `<select>` for `search_backend` (the integer-only dropdown branch never rendered the
      enum). Browser suite 19 passed; unit 3565.
- [x] `context-fullness-overlay` - Orange/red threshold coloring on the telemetry
      overlay from `context_tokens/max_context_tokens`; env-tunable thresholds; a11y
      (not color-only — also a label/aria state). — landed; coloring kept-not-rebuilt,
      thresholds config-driven via `Settings` (clamp-on-invalid validator) + `/api/config`,
      non-color signal = dynamic container `aria-label`. Unit 3574; browser gate green.
- [x] `verify-integration` - Generalized "what does the model receive" tests; author +
      run the behavior test (incl. switch-engine-in-admin → search uses it); full suite
      green; record the compaction → own-mission backlog seed in mission.md. **Done:
      behavior test 9/9 PASS (`runs/2026-06-25-19-37-47.md`).**
- [ ] `uat-and-alignment` *(optional)* - Guided HAT: drive a real stream-hunt
      conversation; watch the overlay color + confirm no degenerate cut-off.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (unit across tool types + behavior test), full suite ≥ M16 baseline
- [ ] Documentation updated (governor budget env var; overlay thresholds; search config)

### Verification
- **Unit (generalized across tools — the F07 miss)**: a large *valid* result from each
  tool type is capped to the model-derived budget; small results pass unchanged; the
  cap scales with `max_context_tokens`.
- **Search**: honest empty/blocked surfacing; backend selection; keyed backend when
  configured; keyless DDG default intact.
- **Behavior test** (`/behavior-test {slug}`, :8485): a stream-hunt conversation no
  longer degenerates; the overlay color transitions at the thresholds.
- **Regression**: full unit suite green at/above the mission baseline, no new flakes.

---

## Design-Review Corrections (binding — Architect, approve-with-changes)

**[HIGH-1] The `WebConfig` field-count guard will break again (F07 repeat).**
`tests/test_web_config.py:33` asserts `len(WebConfig.model_fields) == 9`. Retiring
`tool_text_cap_bytes` (DD1) drops it to 8 — the exact failure the F07 0.2.6 fix-forward
hit. The leg that removes the field MUST update the assertion (→ 8) + docstring (:29-32)
AND run the FULL unit suite (~340s), not a web-only subset. (F07 debrief Rec 3.) Add to
leg-1 acceptance criteria.

**[HIGH-2] `output_cap_bytes` is a SECOND mis-axed LLM cap, with a truncation-direction
clash.** `execution.py:177` defaults to 256 KB, is **tail-preserving**, and its UI
labels are sized against model windows ("Opus headroom") — it is the shell-tool
equivalent of `tool_text_cap_bytes`, so DD1's "retire LLM-facing caps" must include it,
not just the web cap. BUT the governor is **head-preserving** while shell output needs
the **tail** (the `[exit code: N]` suffix + stderr tail that `_truncate_output`,
execution.py:360-405, deliberately keeps). **The governor must be direction-aware**
(head-preserve prose/pages, tail-preserve shell/exec output) — the same
consumer-dependent truncation lesson as F07's `_stream_read_with_cap` vs
`_stream_read_head_capped`. Leg 1 decides shell handling explicitly; do NOT silently
head-cap shell output. (Also check `tests/` for an ExecutionConfig field-count guard.)

**[HIGH-3] "Honest-empty" needs a backend return-contract change, not just selection.**
`DDGSearchBackend.search` (`_search_backends.py:167-187`) returns `[]` for blocked/
throttled, parse-fail/no-marker, AND true-empty alike; `WebSearchTool.execute`
(web.py:490) collapses all to "No results found." Leg 2's substantive work is the
**contract change** — raise a typed `SearchBlockedError`/`SearchUnavailableError` on
non-200 & no-marker, return `[]` only for genuine empty. The tool's existing
`except Exception` (web.py:497) then surfaces it as `[error] …` honestly. Backend
*selection* is one line at `builtins.py:182` (`cross_configs[SearchBackend] = …`); the
contract change is the leg. Re-scope leg 2 to lead with it.

**[MEDIUM-1] No shared `bytes_per_token` on the `LLMProvider` base.** Per-provider
`BYTES_PER_TOKEN_*` constants exist but the accessor lives only on subclasses; the
governor runs against `self.llm: LLMProvider`. Leg 1: promote a `bytes_per_token`
property to the base (default ~4.0) or use a governor-local constant. Decide at design.

**[MEDIUM-2 / LOW-1] DD2 coloring is ALREADY SHIPPED — rescope leg 3, don't rebuild.**
Threshold coloring (70/90 warn/crit) is live in `telemetry-overlay.js:83,:136` +
`chat.css:112-117`, driven by `context_tokens/max_context_tokens`. Leg 3's real (and
only) work: (a) make the thresholds **config-driven** (plumb to the frontend), and
(b) fix the **a11y gap** — the warn/crit signal is **color-only** (`aria-label` is
static, detail rows `aria-hidden`, pct span has no live/text state). Add a non-color
state (pct + "approaching limit" in `aria-label`, or a debounced `aria-live=polite`).
Verify-and-keep the coloring; don't re-implement it.

**[LOW-2] Governor floors `max_context_tokens`** — treat 0/None/absurdly-small as the
base default (128k) to be robust against a future mis-setting provider.
**[LOW-3] Exclude the MCP auth-required ToolResult** (`core.py:562`, fixed sentinel +
pause metadata) from the governor — cap only `output` (:554) and the error strings.
**[LOW-4] Note the cancel/partial-output ToolResult** (F07 interrupt path) is
constructed outside `_execute_tool` and bypasses the governor — confirm it's size-sane
or document the bypass (low risk: bounded by what was streamed).

**Architecture confirmations (no change needed):** `_execute_tool` is the correct single
chokepoint; implement the governor as a **pure helper** (`govern_tool_content(content,
max_context_tokens, *, fraction, floor, ceiling, direction)`) for unit-testability;
`max_context_tokens` resolution timing is safe (resolved on the first `stream()` before
any tool dispatch; sane class-attr fallback); `read_size_cap_bytes` correctly KEPT as a
file-size safety guard (the F07 cap-axis trap is avoided); governed/truncated content is
what persists (reload won't re-poison) — correct.
