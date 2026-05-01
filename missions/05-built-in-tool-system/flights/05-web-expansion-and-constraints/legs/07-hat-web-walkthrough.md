# Leg: 07-hat-web-walkthrough

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Operator-driven HAT validating that the agent recovers gracefully from every new F5 constraint type and that the F4 WebSocket fixes hold for slow `download_file` operations. Interactive — non-autonomous. Flight Director drives via `POST /api/chat` against the Haiku45 agent and records each scenario's tool-call + response chain.

## Context

- L0–L6 landed (uncommitted). All F5 source live in the working tree; uvicorn `--reload` picks up edits automatically.
- HAT scope was reduced to **9 operator-driven scenarios** (was 10 in original spec). DNS-rebind moved to L1 unit test (cannot be exercised operator-driven).

## Acceptance Criteria

- [x] **Scenario 1 — `http_request` happy path**: agent fetches a small public URL; tool returns `[200]\n<body>` under the cap.
- [x] **Scenario 2 — `http_request` size-cap truncation**: agent fetches a large URL; tool returns truncated body with marker `[... truncated N bytes; showing last M bytes of response ...]`.
- [x] **Scenario 3 — SSRF block (cloud metadata)**: agent fetches `http://169.254.169.254/`; tool returns `[error] [constraint]` (block fires either at SSRF resolve-then-pin OR via direct-IP refusal).
- [x] **Scenario 4 — SSRF block (RFC1918)**: agent fetches `http://10.0.0.1/`; tool returns `[error] [constraint]`.
- [x] **Scenario 5 — SSRF allowlist (operator-broadened)**: agent (with `extra_allowed_hosts=["localhost"]` operator override) fetches `http://localhost:8484/api/info`; tool returns `[200]` with the API info body.
- [x] **Scenario 6 — SSRF allowlist (agent-narrowed)**: same operator allowlist, but agent's `tool_overrides` narrows `extra_allowed_hosts` to `[]`; request to `localhost:8484` is now blocked. Validates the `Narrow` semantic.
- [x] **Scenario 7 — `fetch_url` readability extraction**: agent fetches a public article; tool returns markdown of main content (e.g., `# Title` followed by article body).
- [x] **Scenario 8 — `download_file` happy path**: agent downloads a small URL to an in-scope path; tool returns `[200] downloaded N bytes to /path`; file exists.
- [x] **Scenario 9 — slow `download_file` UI rejoin**: operator submits a slow download; switches conversations; rejoins; sees download still in progress + history intact (validates F4 WebSocket fixes hold for web tools).
- [x] **Inline fix applied — IP-literal SSRF bypass** (HAT scenario 3 surfaced it). `SSRFGuardedTransport`'s IP-literal short-circuit was calling `super().handle_async_request(request)` directly, bypassing the SSRF block check. Fix: added `_is_ssrf_blocked(ip)` check (and `extra_allowed_hosts` operator override) inside the IP-literal branch. 5 new regression tests in `tests/test_web_helpers.py::TestSSRFGuardedTransport` (loopback / RFC1918 / cloud-metadata blocked; public passes; operator override). Full suite: 991 passed (+5).
- [x] Mission Known Issues updated with any small-model artifacts (none — all 9 scenarios passed cleanly with Haiku 4.5).

## HAT Outcome

**All 9 scenarios PASSED with Haiku 4.5.** One inline fix landed for an IP-literal SSRF bypass discovered in scenario 3 — pre-fix, the agent's `http://169.254.169.254/` request fell through to the actual TCP connect (which then failed with `[error] All connection attempts failed`); post-fix, the SSRF guard refuses the IP literal at policy time with `[error] [constraint] IP literal 169.254.169.254 is in the SSRF block list`. The unit-test suite already pinned the resolved-host SSRF block; the IP-literal pathway was a blind spot the HAT surfaced.

**Scenario summary**:
1. http_request happy path: example.com → `[200]` with body. ✓
2. response-size cap: 700KB Pride-and-Prejudice text with operator-narrowed cap=50KB → tail-preserved with marker `[... truncated 721189 bytes; showing last 51200 bytes of response ...]`. ✓
3. SSRF block (cloud metadata `169.254.169.254`): **inline fix needed**; post-fix → `[error] [constraint] IP literal 169.254.169.254 is in the SSRF block list`. ✓
4. SSRF block (RFC1918 `10.0.0.1`): `[error] [constraint] IP literal 10.0.0.1 is in the SSRF block list`. ✓
5. SSRF allowlist (operator-broadened `extra_allowed_hosts=["localhost:8484"]`): agent fetched `localhost:8484/api/info` → `[200]` with API info body. ✓
6. SSRF allowlist (agent-narrowed via `tool_overrides`): agent's narrow `[]` correctly nullified operator's allowlist → `[error] [constraint] all resolved IPs for localhost are blocked: ['::1', '127.0.0.1']`. ✓
7. fetch_url readability: example.com → markdown `# Example Domain` with paragraph + link. ✓
8. download_file happy path: 528 bytes written to `/root/downloads/example.html`. ✓
9. Slow download_file UI rejoin: WS responsive (new_session in 0.03s); rejoin history intact (2 events: user + tool_call); `is_processing=true` while still downloading. F4 WebSocket fixes hold for web tools. ✓

**Cleanup**: deleted temporary HAT5-allowlist agent; reset operator tool_configs HAT rows; removed `/root/downloads/` artifacts. Wikipedia rejected the default httpx UA (returned 403); F5 might want to default the User-Agent to `_DEFAULT_USER_AGENT` (operator-overridable) — recorded as L8 follow-up consideration, NOT blocking F5.

## Operator Walkthrough Instructions

Flight Director runs each scenario via `POST /api/chat` with `agent_name=Haiku45` (or `HAT5-allowlist` for scenarios 5 + 6 with the allowlist override). Records agent's tool-call + final response. Inline fixes spawn Developer agents for code changes if error wording is unclear.

---

## Post-Completion Checklist

- [x] All 9 scenarios validated
- [x] Inline fixes applied + re-verified (1 fix; IP-literal SSRF bypass)
- [x] Update flight-log.md with HAT outcomes
- [x] Append any small-model artifacts to mission Known Issues (none)
- [x] Set this leg's status to `landed`
- [ ] (NOT final leg — L8 follows; do NOT commit)
