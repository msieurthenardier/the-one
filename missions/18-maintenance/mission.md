# Mission: Post-Mission-16 Maintenance

**Status**: active
**Depends on**: none (clears debt surfaced after Mission 16; touches `llm/`, `agent/`, `db/`, `interfaces/web/`, CI, deps)

## Outcome

Resolve the codebase-health issues identified in maintenance report
[2026-07-10](../../maintenance/2026-07-10.md): patch the dependency CVEs, make the
image-attach input path crash-resistant, restore a pre-merge CI gate, close the
Level-A accessibility gaps on the new attach UI, durably fix the aiosqlite
teardown flake, and clear the small doc/coverage debts. The codebase returns to
**Flight Ready** for the next capability mission.

## Context

Maintenance report [2026-07-10](../../maintenance/2026-07-10.md) (triggered by the
close of [Mission 16 — LLM Provider Layer Hardening](../16-llm-provider-hardening/mission.md)).
A four-reviewer inspection (Inspector, Security, CI/CD, Accessibility) plus an
Architect roundtable found the Mission-16 provider work solid (suite green ×2,
lint clean, no SSRF/injection/secret-leak) with a small, landable debt cluster:
dependency CVEs, an input-robustness pair (WS-crash + `-O`-strippable assert), a
CI pre-merge-gate regression, two attach-UI accessibility gaps, the long-carried
aiosqlite teardown flake, and minor doc/coverage debt. Two suspected items were
cleared during inspection (Leg-09 backstop = keep; Windows seed packaging = already
fixed) and the corresponding overstated Mission-16 lines are corrected here.

## Success Criteria

- [ ] The four runtime-path dependency CVEs (aiohttp, starlette, cryptography,
      python-multipart) are patched and `uv.lock` no longer pins vulnerable
      versions; pip-audit confirms the delta. *(D1)*
- [ ] A malformed `images` WebSocket payload no longer crashes the receive loop —
      the message branch catches broadly like its sibling branches, and
      `ImageContent`'s guard is `raise`, not a `-O`-strippable bare `assert`.
      *(S1 + S2)*
- [ ] Image attachments have a lightweight size/count cap (client + server).
      *(S3)*
- [ ] A pre-merge CI gate exists again — a fast lint-only (+ pip-audit) check runs
      on pull requests — without undoing the deliberate cost-shift of the heavy
      lanes to post-merge Concourse. *(C1 + C4)*
- [ ] The attach-UI accessibility gaps are closed: a live-region announces
      staging/removal, each staged image has a distinguishing accessible name, and
      the remove-glyph meets 4.5:1 in light theme. *(A1 + A2 + A3)*
- [ ] The aiosqlite `Event loop is closed` teardown is durably fixed (fixture-scope
      / `asyncio_mode`), not formally accepted. *(T1)*
- [ ] Doc/coverage hygiene: the live-thinking `visibility` field is emitted on the
      broadcast path; the two promised `agents.md` promotions are written; and a
      `/behavior-test` spec is authored for `save-preserves-config` and for
      `vision-round-trip`. *(DOC1 + DOC2 + T2 + T3)*

## Stakeholders

- **Operator / maintainer** — wants the debt cleared before the next capability
  mission (the agent-level config surface seeded by the Mission-16 debrief).

## Constraints

- Read-only findings become minimal, targeted fixes — no opportunistic refactors.
  Do **not** remove the Leg-09 backstop (inspection verdict: keep) and do **not**
  re-touch the resolved Windows seed packaging.
- Preserve the Mission-16 invariants: the `LLMProvider` contract, `str`-identical
  `Message.content` fast path, `__MASKED__`/Fernet credential handling.
- Don't undo the flight/8 CI cost-shift — restore only the fast pre-merge lane.

## Environment Requirements

- Existing Python 3.11+ host install (`pip -e ".[all-llms,dev]"`), `uv` for the
  lockfile, ruff, pytest, Playwright (`make test-browser`).

## Open Questions

N/A — findings are concrete; fix strategies are in each flight's Technical Approach.

## Known Issues

N/A — this mission clears known issues rather than surfacing new ones.

## Flights

> **Note:** Scaffolded from the 2026-07-10 maintenance report. Flights 1–3 are the
> load-bearing core; Flight 4 is hygiene and can slip if the mission needs to shrink.

- [x] Flight 1: **Supply-chain & CI gate** — bump the four runtime-path CVE pins +
      regenerate `uv.lock` (D1); restore a pre-merge lint-only (+ pip-audit) PR
      check without undoing the Concourse cost-shift (C1/C4). **LANDED** — pip-audit
      24→2 (2 dev/toolchain-only; runtime closure clean); 7 CVE floors raised in
      `pyproject.toml` so the installer re-resolve is guaranteed; new `pr-lint.yml`.
- [x] Flight 2: **Input robustness** — `ImageContent` bare-assert → `raise` +
      generic `except` on the WS message branch (S2/S1); image size/count cap
      (S3). **LANDED** — narrow content-build guard + malformed-shape validation;
      10 MB/image, max 10 count; real crash-guard + browser tests.
- [ ] Flight 3: **Attach-UI accessibility** — live-region on the staging region
      (A1), distinguishing per-image accessible names (A2), remove-glyph contrast
      (A3). One coherent leg over `chat.js`/`components.css`.
- [ ] Flight 4: **Test-infra & doc hygiene** — durable aiosqlite teardown fix
      (T1); live-thinking `visibility` emit + two `agents.md` promotions
      (DOC1/DOC2); correct the two overstated Mission-16 lines (Leg-09 "dead code";
      Windows packaging). Author `save-preserves-config` + `vision-round-trip`
      behavior-test specs (T2/T3).
