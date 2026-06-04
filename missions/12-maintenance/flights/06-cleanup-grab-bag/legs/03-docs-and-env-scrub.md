# Leg: docs-and-env-scrub

**Status**: ready
**Flight**: [Cleanup Grab-Bag](../flight.md)

## Objective
Correct the documentation and environment-config drift surfaced by the inspection: the phantom event in agents.md (DOC1), stale Slack/F9 forward-references (DOC2), `.env.example` dead/missing vars (DOC3), undocumented `os.environ` tunables (DOC4), and missing agents.md anchors (DOC5).

## Context
Maintenance report 2026-06-04, Category 6 + Category 9 findings:
- **DOC1**: `agents.md:578` documents a `connector-peer-approval-resolved` studio-event-bus event that does not exist (zero hits in the codebase); the UI actually updates via an optimistic client path (`chat.js:331`) + a 10s badge poll.
- **DOC2**: `connectors/README.md:99,106,118` and `registry.py:141,156` carry stale "Flight 9 / second connector / Slack" forward-references; only `discord` is registered (`registry.py:182`) and M11 is complete.
- **DOC3**: `.env.example` lists 3 dead vars (`THE_ONE_LLM_PROVIDER`, `THE_ONE_LLM_MODEL`, `THE_ONE_LLM_BASE_URL` — read nowhere; config moved to DB in v26) and omits 2 real ones (`THE_ONE_LOG_LEVEL`, `THE_ONE_DATA_DIR`).
- **DOC4**: 6 operational tunables read via raw `os.environ` are undocumented in `.env.example`: `THE_ONE_SESSION_CONTINUATION_SECONDS` (`connectors/_session.py`), `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` + `THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS` (`connectors/_pool.py`), `MCP_POOL_IDLE_TTL_SECONDS` (`mcp/_pool.py`), `THE_ONE_SANDBOX_DISABLED` (`mcp/transports/stdio.py`), `THE_ONE_REGISTER_STUB_CONNECTOR` (`app.py`, dev-gated).
- **DOC5**: `agents.md` lacks anchors for the streaming-parser duplication (P5) and the singleton-connection model.
- *(Note: the legacy `THE_ONE_INFERENCE_*` shim in `app.py:186-197` is an intentional deprecation warning — NOT debt, do not remove.)*

## Inputs
- `the_one/agents.md` (lines ~578 phantom event; needs P5/connection anchors).
- `the_one/connectors/README.md`, `the_one/connectors/registry.py`.
- `.env.example`.

## Outputs
- Corrected docs + env example matching actual behavior.

## Acceptance Criteria
- [ ] **DOC1**: `agents.md:578` describes the actual mechanism (optimistic client update + 10s poll), not the non-existent `connector-peer-approval-resolved` event
- [ ] **DOC2**: stale "Flight 9 / second connector / Slack" references in `README.md` + `registry.py` are removed or reframed as illustrative/hypothetical
- [ ] **DOC3**: the 3 dead `THE_ONE_LLM_*` lines are removed from `.env.example`; `THE_ONE_LOG_LEVEL` and `THE_ONE_DATA_DIR` are added
- [ ] **DOC4**: the operator-relevant `os.environ` tunables are documented in `.env.example` (with brief descriptions + defaults)
- [ ] **DOC5**: `agents.md` has brief anchors for the streaming-parser accumulator (coordinate with Flight 06 Leg 1) and the singleton-connection model
- [ ] The legacy `THE_ONE_INFERENCE_*` deprecation shim is left intact

## Verification Steps
- `grep -rn "connector-peer-approval-resolved" the_one/` → zero (DOC1 corrected, not re-introduced)
- `grep -rni "slack\|flight 9\|second connector" the_one/connectors/` → only intentional/illustrative mentions remain (DOC2)
- `grep -n "THE_ONE_LLM_" .env.example` → zero; `grep -n "THE_ONE_LOG_LEVEL\|THE_ONE_DATA_DIR" .env.example` → present (DOC3)
- `.env.example` lists the documented tunables (DOC4)
- `agents.md` has the new anchors (DOC5)

## Implementation Guidance

1. **DOC1** — rewrite the `agents.md:578` sentence to describe the optimistic-update + poll path. Optionally cross-link `chat.js:331`. (Do not implement the event — just document reality.)
2. **DOC2** — in `connectors/README.md` and `registry.py`, drop or soften the Slack/F9 references. If the "second connector" framing is useful as an extension example, mark it explicitly hypothetical.
3. **DOC3** — remove the 3 dead `THE_ONE_LLM_*` lines; add `THE_ONE_LOG_LEVEL` and `THE_ONE_DATA_DIR` with their defaults (from `config.py`).
4. **DOC4** — add a clearly-labeled "operational tunables" section to `.env.example` documenting the 6 vars (name, what it does, default). **Coordinate with Flight 05**, which adds `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` to the same file — sequence to avoid a merge conflict.
5. **DOC5** — add brief `agents.md` anchors for the streaming accumulator (Flight 06 Leg 1) and the singleton aiosqlite connection model.

## Edge Cases
- **`.env.example` is public** — keep examples generic; no real secrets or operator-specific paths.
- **Do not document dev-only/internal vars as if operator-facing** — `THE_ONE_REGISTER_STUB_CONNECTOR` is dev-gated; note it as such or omit.

## Files Affected
- `the_one/agents.md` - DOC1 correction + DOC5 anchors
- `the_one/connectors/README.md`, `the_one/connectors/registry.py` - DOC2
- `.env.example` - DOC3 + DOC4

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (docs-only, but run lint/suite if any code comment changed)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (not final)
- [ ] Commit all changes together (code + artifacts)
