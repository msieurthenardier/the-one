# Flight: Supply-chain & CI gate

**Status**: ready
**Mission**: [Post-Mission-16 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] Dependency CVEs patched; `uv.lock` no longer pins vulnerable versions (D1)
- [ ] Pre-merge CI gate restored without undoing the Concourse cost-shift (C1/C4)

---

## Pre-Flight

### Objective
Patch the runtime-path dependency CVEs and restore a fast pre-merge CI gate — the
two "supply chain / gate" items that keep the codebase off Flight Ready.

### Open Questions
N/A — concrete fixes.

### Design Decisions
N/A (maintenance) — fix strategy in Technical Approach.

### Prerequisites
- [x] `uv` available for lockfile regeneration
- [x] `pip-audit` installed (`[dev]` dep)

### Pre-Flight Checklist
- [x] All open questions resolved — N/A
- [x] Design decisions documented — N/A
- [x] Prerequisites verified
- [x] Validation approach defined (pip-audit delta; PR-triggered check runs)
- [ ] Legs defined (during `/agentic-workflow`)

---

## In-Flight

### Technical Approach

**Leg 1 — Dependency CVE bump (D1).**
Evidence: `pip-audit` reports 24 vulns / 9 packages; `uv.lock` (dated 2026-06-15)
pins the exact vulnerable versions. Recommendation: bump the four runtime-path
pins and regenerate the lock:
- `aiohttp 3.14.0 → 3.14.1` (7 CVEs, pulled via discord.py)
- `starlette 1.2.1 → 1.3.1` (PYSEC-2026-248/249, on the request path)
- `cryptography 47.0.0 → 48.0.1` (GHSA-537c-gmf6-5ccf, at-rest encryption)
- `python-multipart 0.0.29 → 0.0.31` (3 CVEs, upload/form parsing — the image path)
- transitives as pulled: `pydantic-settings 2.13.1→2.14.2`, `soupsieve`,
  `lxml-html-clean 0.4.4`, `msgpack 1.1.2`.
Regenerate `uv.lock`, re-run `pip-audit` to confirm the runtime-closure delta
(pip 24.0 findings are toolchain-only, out of scope), then run the full suite to
confirm no behavioral regression from the bumps. Prefer minimal version moves that
clear the CVE; don't opportunistically bump unrelated pins.

**Leg 2 — Restore a pre-merge lint gate (C1 + C4).**
Evidence: GH Actions `lint.yml`/`test.yml` are `workflow_dispatch`-only since
`76659fb` (flight/8 cost-shift to local Concourse); Concourse's `repo` resource
polls `branch: main` → validates post-merge; the only pre-merge "gate" is a
`ci/README.md` note to run `fly execute`; no branch protection. 10 PRs merged with
no automated pre-merge verification. Recommendation: add a **lint-only**
`on: pull_request` GitHub Actions workflow running `ruff check` + `ruff format
--check` (~15s, negligible minutes) — the fast gate — and wire the already-declared
but never-invoked `pip-audit` (C4) as a step there or a parallel job. **Do not**
re-enable the heavy test/browser/windows lanes on GH Actions — the deliberate
cost-shift of those to the local Concourse worker stands; only the cheap
fail-fast lane belongs pre-merge. (Alternative if preferred: have Concourse post
commit statuses on PR refs — but the lint-only PR action is the lower-effort path.)

### Checkpoints
- [ ] `pip-audit` shows the four runtime CVEs cleared; `uv.lock` regenerated; suite green
- [ ] A PR-triggered lint (+ pip-audit) check runs and fails on a seeded violation

### Adaptation Criteria
**Divert if**: a dependency bump forces a breaking API change requiring code edits
beyond a trivial adjustment — surface it; don't silently expand scope.
**Acceptable variations**: exact transitive versions chosen by the resolver.

### Legs
> Planned one at a time during `/agentic-workflow`.
- [ ] `dependency-cve-bump` — bump 4 runtime pins + transitives, regen lock, pip-audit delta (D1)
- [ ] `pre-merge-lint-gate` — `on: pull_request` ruff + pip-audit workflow (C1/C4)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated (`ci/README.md` reflects the restored PR gate)

### Verification
`pip-audit` clean on the four runtime pins; the PR lint check visibly runs on a
test PR and fails on a violation; full suite green post-bump.
