# Leg: connector-observability

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)

## Objective

Make the Discord connector's inbound and outbound dispositions visible on a single greppable stdout stream (plus light per-account counters), so the F17 full-working-day soak can *assert* "stayed up / no silently-dropped inbound / 429s handled gracefully" instead of inferring it anecdotally.

## Context

- **Observe-premise gap (Architect + Developer-verified):** inbound dispositions are already written to DB `session_metadata` — `["audit"]` with `outcome:"deny"` at **three** `NeedsPairing` return sites (`_inbound.py:398-409`, `:418-431`, `:455-465`), and `["routing"]` with `disposition` ∈ {`no-eligible` (`:548`, `:604`, `:619` — the `:604/:619` ones are pool-acquire failures, same disposition value with a distinguishing `reason`), `policy-silent` (`:799`), `stepped` (`:822`), `command-intercepted` (`:693`, `:730`)} — but none reach the `docker logs` stdout stream an 8-hour soak greps. Outbound has **zero** observability: a 429 is only a generic WARNING, success is unlogged, no counters. Three inbound drops are silent / near-silent: bot-author filter (`_discord.py:933-937`), self filter (`:945-949`), and the factory-unavailable startup-race (`:956-964`, which already WARNs).
- **Vocabulary aligns to the DB audit/routing values** so an operator can grep-correlate the stdout line against the DB record: inbound `disposition` ∈ `stepped | command-intercepted | no-eligible | policy-silent | denied | dropped` (`denied` ↔ audit `outcome:"deny"`; pool-acquire failure is `no-eligible` + `reason`). Outbound `disposition` ∈ `ok | rate_limited | error`.
- **This is a log-projection/consolidation leg, NOT a "build the missing record" leg.** We ADD stdout lines (and best-effort counters) *alongside* the existing `session_metadata` appends — never replacing them, never double-counting.
- **Binding evidence surface = the stdout disposition stream.** Counters are a convenience aggregate that resets on pool-TTL eviction (accepted limitation, named in the flight).
- **Hard constraints:** ids + dispositions only — **never message content or tokens** in any log line. Mission constraints: do NOT modify the agent loop (`agent/core.py`, `agent/factory.py`); no env-var-driven runtime branching test seams (use DI/code-side stubs in tests); Single-User-Local security posture preserved.

## Inputs

- `the_one/connectors/_inbound.py` — `dispatch_inbound` with disposition decisions at multiple return sites (deny, no-eligible, pool-failure, policy-silent, admitted/stepped), each already appending to `session_metadata`.
- `the_one/connectors/_discord.py` — the outbound send path (~`:522-554`, including the `except discord.errors.HTTPException` → `ConnectorRateLimitError` 429 branch); the two silent inbound noise filters (`:934-937` bot-author, `:945-949` self).
- `the_one/connectors/_pool.py` — `_RegistryEntry` (~`:135-181`) and the account-cache snapshot pattern (`_get_account_cache_snapshot`) used by the discoverable-entities read path.
- `the_one/interfaces/web/api.py` — the discoverable-entities endpoint (`GET /connectors/{id}/discoverable-entities`, ~`:3022-3094`) as the precedent for surfacing per-account pool-entry state through a read path.

## Outputs

- A single-sourced disposition helper that emits one structured stdout line per inbound disposition and per outbound send, with a stable vocabulary.
- Stdout disposition lines wired at every `dispatch_inbound` return site (alongside, not replacing, the existing `session_metadata` append) + the two silent-filter `dropped` traces (debug level) + the outbound send sites.
- Per-account counters on the pool `_RegistryEntry`, incremented best-effort (no-op when no warm entry), surfaced via a connector-detail-family snapshot read path.
- Unit tests (DI/code-side stubs; no env-flag seam) covering the helper, the disposition vocabulary, counter increments, the snapshot read path, and the no-content/no-token guarantee.
- Full backend suite green.

## Acceptance Criteria

- [x] A **single shared disposition helper** exists (one home for the disposition vocabulary) that, given (account_id, channel_id, peer_id, kind∈{inbound,outbound}, disposition, optional reason/retry_after/latency_ms), emits exactly one structured stdout log line and best-effort increments the matching per-account counter. Inbound dispositions are exactly: `stepped | command-intercepted | no-eligible | policy-silent | denied | dropped` (aligned to the DB audit/routing values). Outbound dispositions are exactly: `ok | rate_limited | error`.
- [x] **Every `dispatch_inbound` disposition return site** emits one line via the helper, **alongside** the existing `session_metadata` append (audit/routing append unchanged — no replacement, no double-append). Specifically wired: the **three** `denied` sites (`:398-409`, `:418-431`, `:455-465`); `no-eligible` (`:548` rule/default-exhausted, `:604`/`:619` pool-acquire-failure with a `reason`); `policy-silent` (`:799`); `stepped` (`:822`); `command-intercepted` (`:693`, `:730`). The `NeedsPairing`-valid-prefix `permit` path (`:483-506`) does NOT return — it falls through to routing and is logged at whatever terminal disposition it reaches (no separate line at the permit site).
- [x] **Outbound send path** (`_discord.py:522-568` — the `try:` at `:522`, the `await destination.send(content)` at `:523`, through the `return SendResult(...)` at `:563-568`): start the timer just before the `try:` (`:522`) and stop after the send returns; a success emits `disposition=ok` with `latency_ms`; the 429 branch (`:533-554`) emits `disposition=rate_limited` with `retry_after` (as/just before `ConnectorRateLimitError` is raised — the typed-error behavior is unchanged); any other `HTTPException`/`Forbidden`/`NotFound`/send error emits `disposition=error` with an error-type label (not the message body). The **ephemeral followup path** (`_send_ephemeral_followup`, ~`:571`) emits its own `ok | error` line so slash-command replies aren't unobserved.
- [x] **The three silent/near-silent inbound drops** each emit a **debug-level** `disposition=dropped` line: `reason=bot-author` (`_discord.py:933-937`), `reason=self` (`:945-949`), `reason=factory-unavailable` (`:956-964`, on the unified stream alongside the existing WARNING). These remain non-dispatched (no behavior change); they are the only `dropped` sources.
- [x] **Per-account counters live on the pool `_RegistryEntry`** (or an account-keyed structure owned by the pool), incremented by the helper best-effort: when no warm entry exists the increment is a no-op (counters read "since the current pool entry warmed"). Counters are **not** lifted to module-level persistence (accepted reset-on-eviction limitation).
- [x] Counters are **surfaced through a connector-detail-family snapshot read path** mirroring `_get_account_cache_snapshot` (e.g. a `GET /connectors/{id}/…` stats field/endpoint). **NOT** the doctor probe (it spins its own short-lived client with no pool-state access). The read path returns the current counters for a warm account and degrades cleanly (empty/zero or the established "warm first" response) when no entry is warm.
- [x] **No log line contains message content or a token/secret** — only ids, dispositions, reasons, numeric latency/retry. A unit test asserts a representative payload with content+token yields a log line carrying neither.
- [x] Mission-constraint compliance: no change to `agent/core.py` or `agent/factory.py`; no `THE_ONE_TEST_MODE`-style env-var branching introduced; tests force the 429/error and no-warm-entry paths via DI/code-side stubs.
- [x] Unit tests cover: the helper's line format + vocabulary; each inbound disposition mapping; outbound ok/rate_limited/error; the two `dropped` traces; counter increment + best-effort no-op; the snapshot read path. Full backend suite green (`docker exec the-one pytest … -x --timeout 30 -q`, broader suite once at leg end).

## Verification Steps

- Helper + vocabulary: targeted unit test file for the disposition helper.
- Inbound wiring: a dispatcher-level test (or per-site assertions) that each disposition path logs exactly one inbound line and still appends to `session_metadata` (no double-append, no replacement).
- Outbound wiring: stub the discord send to return success / raise a 429 `HTTPException` / raise another error; assert the three disposition lines + that `ConnectorRateLimitError` still raises with `retry_after`.
- Counters: increment via the helper with a warm stub entry → readable via the snapshot path; with no warm entry → no-op, read path degrades cleanly.
- No-leak: a test passing content+token asserts neither appears in the emitted line.
- **Soak grep target (document in the leg + flight log):** the operator's full-day evidence stream is `docker logs the-one | grep -E 'connector\.(inbound|outbound)'`; every inbound message should account for exactly one `connector.inbound … disposition=(stepped|command-intercepted|no-eligible|policy-silent|denied|dropped)` line, and outbound sends for `connector.outbound … disposition=(ok|rate_limited|error)`. A `disposition=dropped` line is debug-level (raise log verbosity to see bot-author/self/factory-unavailable).
- Suite: `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_discord.py tests/test_connectors_pool.py -x --timeout 30 -q` (file names confirmed to exist), then the full backend suite once at leg end.

## Implementation Guidance

1. **Add the disposition helper** in a small `_observability.py`-style module in the connectors package. It owns the disposition vocabulary (constants/enum) and does two things: emit one structured stdout line (stdlib `logging.getLogger(__name__)`, human-readable `key=value` text consistent with existing connector logs — e.g. `connector.inbound account=… channel=… peer=… disposition=… reason=…`) and call the module-level `record_disposition(account_id, kind, disposition)` best-effort. Logging is unconditional; counting is best-effort.
2. **Wire inbound** at each disposition return site (the three `denied` sites `:398-409`/`:418-431`/`:455-465`; `no-eligible` `:548`/`:604`/`:619`; `policy-silent` `:799`; `stepped` `:822`; `command-intercepted` `:693`/`:730`) — add the helper call adjacent to the existing `session_metadata` append. Do not move or remove the append. `account_id` is the function's first param; `channel_id`/`peer_id` are on the envelope — all in scope at every site. Give the two pool-acquire-failure `no-eligible` sites a distinguishing `reason` so they're separable from rule-exhaustion `no-eligible`.
3. **Wire the three silent drops** in `_discord.py` (`:933-937` bot-author, `:945-949` self, `:956-964` factory-unavailable) with a debug-level `dropped` line each. They still `return` without dispatching — behavior unchanged.
4. **Wire outbound** in the `_discord.py` send path (`:522-568`): start a timer just before the `try:` (`:522`); the actual send is `await destination.send(content)` at `:523`; on the success `return` (`:563-568`) log `ok` with `latency_ms`; in the existing 429 branch (`:533-554`) log `rate_limited` with `retry_after`; in the `Forbidden`/`NotFound`/non-429-`HTTPException` branches log `error` with an error-type label. All raises stay exactly as-is. Add an `ok|error` line in `_send_ephemeral_followup` (~`:571`) for the followup send.
5. **Counters on the pool**: add `inbound_counters`/`outbound_counters` (`dict[str,int]`, `field(default_factory=dict)`) to `_RegistryEntry` (`:135-181`, mirroring the existing `discoverable_entities_cache` field). Add a **module-level** `record_disposition(account_id, kind, disposition)` to `_pool.py` (NOT a method — `_inbound.py` already imports `account_acquire`/`_get_account_cache_snapshot` from `_pool` at `:143`, so import this the same way): under the pool lock, locate the warm account entry (the `(_ACCOUNT_POOL_AGENT_SLOT, account_id)` key) and increment, or no-op if no warm entry. Add a sibling frozen snapshot (e.g. `_CountersSnapshot`) rather than widening `_DiscoverableCacheSnapshot` (different refresh lifecycle), and surface it on a connector-detail-family read path (mirror `GET /connectors/{id}/discoverable-entities`; do NOT touch the doctor probe — it has no warm-entry access).
6. **Tests** with DI/code-side stubs only. Run targeted files iteratively, full backend suite once at the end.

## Edge Cases

- **No double-counting / no double-append**: the audit/routing `session_metadata` append must remain exactly once per site; the helper adds the log line + best-effort counter only. A site that currently appends twice (if any) is pre-existing — do not "fix" it here; just don't add a second append.
- **No warm pool entry** (denied inbound before any acquire, or a quiet-then-evicted account): the log line still emits; the counter increment no-ops. The read path must not 500 — degrade like the discoverable-entities "warm first" response.
- **Content/token leakage**: be especially careful at the outbound site (the content being sent is right there) and the inbound sites (the message text is in scope). Log ids/dispositions/reasons only.
- **Latency timing**: measure only around the actual `destination.send` call; don't fold in unrelated awaits.
- **Concurrency**: counters may be incremented from concurrent dispatches — use a cheap, correct increment (the pool already guards entry access; reuse that discipline rather than adding heavyweight locking).

## Files Affected

- `the_one/connectors/_inbound.py` — add disposition-helper calls at each `dispatch_inbound` return site (alongside existing `session_metadata` appends).
- `the_one/connectors/_discord.py` — outbound send disposition lines (ok/rate_limited/error + latency); two silent-filter `dropped` debug lines.
- `the_one/connectors/_pool.py` — per-account counters on `_RegistryEntry` (or pool-owned map) + `record_disposition` + snapshot extension.
- `the_one/connectors/_observability.py` *(new, or co-located)* — the shared disposition helper + vocabulary.
- `the_one/interfaces/web/api.py` — surface counters via a connector-detail-family snapshot read path (mirror the discoverable-entities endpoint).
- `tests/…` — unit tests for the helper, wiring, counters, snapshot, and the no-leak guarantee.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(commit deferred to flight-end batch per /agentic-workflow)*

- [x] All acceptance criteria verified
- [x] Tests passing (targeted + full backend suite green)
- [x] Update flight-log.md with leg progress entry
- [x] Leg status set to `landed` (→ `completed` at flight-end commit)
- [ ] Check off this leg in flight.md (deferred to flight-end commit)
- [ ] If final leg of flight: (not final — L2 + L3 follow)
- [ ] Commit deferred to flight-end review (per /agentic-workflow batch model)
