# Flight: Host-Native Runtime Readiness

**Status**: completed
**Mission**: [Native Desktop Installers](../../mission.md)

## Contributing to Criteria

- [ ] The app builds, runs, and is **tested entirely without Docker**; the
      developer `pip` install path remains supported and the existing test suite
      passes host-natively in CI.
- [ ] The installed app stores its data and encrypted secrets in an
      OS-appropriate per-user location and **preserves them across app restarts**;
      an existing `~/.the-one` directory is migrated rather than orphaned. *(path
      + migration logic lands here; the "installed app" packaging is later flights)*
- [ ] Sandbox enforcement is active on Linux **host-native** (no Docker) — the
      Mission-14 boundary continues to enforce once the container is gone.
- [ ] When a required external runtime for MCP servers is absent, the app
      **detects this and presents actionable, non-Docker guidance** rather than
      failing silently. *(detection + guidance surface lands here)*

---

## Pre-Flight

### Objective

Make GleepGlorp run, develop, and test as an ordinary host process with **no
Docker anywhere** — the precondition every later M15 flight builds on. This flight
(a) moves the data/secrets store to an OS-conventional per-user location and
migrates any legacy `~/.the-one`; (b) makes the Mission-14 Linux sandbox backend
work host-native via an empirical user-namespace probe with graceful degrade;
(c) detects absent external MCP runtimes (`node`/`uv`/…) and surfaces actionable,
non-Docker guidance in place of today's Docker-flavored error; (d) retires the
`docker exec` Makefile test flow for host-native invocation and stands up a
host-native pytest CI on GitHub Actions (including a bwrap-provisioned Linux job so
the sandbox boundary is exercised); and (e) closes the small set of Mission-14
end-of-mission maintenance debt that survived reconnaissance.

### Open Questions

- [x] How aggressively to migrate `~/.the-one`? → **Move/rename** (see Design
      Decisions). *(resolves a Mission-15 open question)*
- [x] `@requires_bwrap` tests in host-native CI? → **Provision bwrap in a dedicated
      Linux CI job** (see Design Decisions). *(resolves a Mission-15 open question)*
- [x] Is `SandboxError` an actual import cycle? → No literal runtime cycle, but a
      real **layering inversion** (sandbox-domain error living in the MCP module);
      relocate it. See Design Decisions and the flight log's Reconnaissance Report.
- [x] Does host-native bwrap actually contain on the primary dev box (WSL2)? →
      **Verified yes** at design time (see Prerequisites / flight log).

### Design Decisions

**One flight for the full host-native scope**: Keep data-dir + migration, runtime
detection, host-native sandbox, Makefile de-Docker, pytest CI, and M14 debt in a
single flight rather than splitting CI out.
- Rationale: Operator choice; matches the mission's original Flight-1 sketch and
  lands "host-native everywhere" as one coherent unit.
- Trade-off: Larger flight (7 legs, likely >3 days); mitigated by independent,
  individually-verifiable legs suited to batched execution.

**`~/.the-one` migration = move (rename)**: On first run, if the legacy
`~/.the-one` exists and the new OS-conventional location does **not**, rename the
legacy directory into place.
- Rationale: Clean single source of truth, no duplicated DB/secrets on disk.
- **Guard (critical)**: migration fires **only when `data_dir` is the default,
  platformdirs-resolved path** — never when it was explicitly supplied via
  `THE_ONE_DATA_DIR` or a test override. Otherwise every pytest run (which points
  `THE_ONE_DATA_DIR` at a fresh temp dir, `tests/conftest.py:53-56`) would rename
  the developer's real `~/.the-one` into a throwaway directory. Asserted by a test.
- Trade-off: Destructive if something else still references the old absolute path.
  Mitigated by the default-path-only guard above, the "only when target absent"
  condition, an explicit log line, and one-shot idempotency (safe under the repeated
  `ensure_dirs()` calls from `AgentFactory.create()`, `tools/execution.py:539`).

**OS-conventional paths via `platformdirs`**: Resolve `data_dir` per-OS — Linux
`$XDG_DATA_HOME/the-one` (≈ `~/.local/share/the-one`), macOS
`~/Library/Application Support/the-one`, Windows `%APPDATA%\the-one`.
- Rationale: Standard, well-maintained, cross-platform; replaces the hardcoded
  `Path.home() / ".the-one"` at `the_one/config.py:22` with one abstraction every
  existing read-site (`encryption.py`, `tools/execution.py`, connectors) already
  funnels through, so no call-site churn.
- Trade-off: One new runtime dependency (small, ubiquitous).

**Sandbox userns probe is empirical, not the procfs knob**: The host-native probe
attempts a real unprivileged user-namespace operation (and a minimal bwrap
invocation) rather than reading `/proc/sys/kernel/unprivileged_userns_clone`.
- Rationale: **Verified at design time** — that knob is *absent* on the WSL2 dev
  kernel (6.6 microsoft-standard), yet unprivileged userns and host-native bwrap
  containment both work. The Debian-ism knob is unreliable as the gate; an
  empirical attempt is the source of truth. The knob may be read as a fast-path
  hint only.
- Trade-off: A probe that spawns a process is marginally costlier than a file read;
  done once at backend selection, cached.

**Userns probe is additive in the factory; the `__init__` backstop stays**: The
bwrap-*missing* case already degrades to passthrough in the factory
(`platform/sandbox/factory.py:109-117`); `BubblewrapSandbox.__init__`'s raise
(`bubblewrap.py:83-89`) is a tested backstop (`tests/test_sandbox_bubblewrap.py:47-49`)
and **stays**. The genuinely new work is a userns probe in the factory's *selection*
logic (today it picks Bubblewrap whenever bwrap is present, regardless of userns,
`factory.py:119-124`): when bwrap is present but an empirical userns attempt fails,
select passthrough and emit a WARNING that **distinguishes** "bwrap not found" from
"bwrap present but user namespaces unavailable".
- Rationale: Additive change preserves the existing backstop + its test; the factory
  is already the degrade locus, so the probe belongs there. Host environments vary;
  the app must still run with enforcement-absence observable (M14 seam contract).
- Trade-off: Unenforced fallback on locked-down hosts; surfaced loudly, documented in
  install docs (later flight).

**`SandboxError` relocates to the sandbox package — definition moves, no back-edge
re-export**: Move the `SandboxError` *definition* into a sandbox-owned module
(`the_one/platform/sandbox/errors.py`); it subclasses `MCPClientError` via a
**one-way** import from `mcp/errors.py` (which stays a dependency-free leaf). Do
**not** re-export `SandboxError` back from `mcp/errors.py` — that back-edge is what
would manufacture an order-dependent circular import (the factory already documents
this deferral at `factory.py:62-64`). Instead, update the handful of importers
(`mcp/transports/stdio.py:74`; the sandbox `__init__.py:17`, which already re-exports;
and the `tests/test_sandbox_contract.py` identity assertions) to source it from the
sandbox package.
- Rationale: This is the actual layering fix the M14 debrief intended ("out of
  `mcp/errors.py`"). The sandbox-domain import path **already exists**
  (`platform/sandbox/__init__.py:17`), so M15 backends import from
  `the_one.platform.sandbox` — clean. Keeping the base one-way (sandbox → `mcp.errors`)
  preserves `issubclass(SandboxError, MCPClientError)` with no cycle.
- Trade-off: Updates ~2 non-test importers + the contract test rather than a
  transparent re-export — accepted to avoid the manufactured cycle the architect
  flagged. **Fallback** if relocation proves thornier than expected: leave the
  definition in `mcp/errors.py` and merely codify `the_one.platform.sandbox` as the
  canonical backend import path (the domain path already works) — document rather
  than move.

**Flight-1 CI scope is Linux host-native pytest (+ bwrap job); per-OS test matrix
rides with later flights**: CI runs the host-native suite on `ubuntu-latest`,
including a dedicated job with `bubblewrap` apt-installed so `@requires_bwrap` tests
execute. macOS/Windows *test* matrix expansion is deferred to Flights 2 (macOS
backend) and 3 (Windows PTY), where those platforms gain the code under test.
- Rationale: The sandbox/bwrap tests are Linux-only; Playwright browser tests run on
  Linux today. macOS/Windows test value arrives with their backends, not before.
  (This is the *test* CI; installer-build CI is Flight 6.)
- Trade-off: Tri-platform test CI isn't complete until F3; acceptable — no
  macOS/Windows-specific code exists to test in F1.

**No new behavior test authored for this flight**: Flight-1 criteria are
unit/integration/CI-verifiable (path resolution, migration, error-message content,
kernel-enforced containment via `@requires_bwrap`, green host-native CI).
- Rationale: Don't author behavior tests speculatively. The mission's
  behavior-test-backed criteria cluster in Flights 2 (macOS containment), 4 (native
  window), 5 (packaged-artifact spawn), and 7 (per-OS acceptance).
- Trade-off: None material; the containment property is already covered by the M14
  `@requires_bwrap` kernel-enforcement suite, which this flight makes run
  host-native.

### Prerequisites

- [x] **Mission 14 completed** — the shared sandbox seam + passthrough backend +
      selection factory exist (`platform/sandbox/factory.py`,
      `bubblewrap.py`, `passthrough.py`). Verified: mission status `completed`.
- [x] **Host-native bwrap containment verified on the primary dev box (WSL2)** —
      design-time empirical check (per the M14 "verify the load-bearing DD" lesson):
      `bwrap --unshare-all --ro-bind / / …` blocked an `/etc` write and network;
      `unshare --user` succeeded; `bwrap` is at `/bin/bwrap`. The
      `unprivileged_userns_clone` knob is absent — recorded as the reason the probe
      is empirical. Full transcript in the flight log.
- [ ] **GitHub Actions `ubuntu-latest` supports unprivileged userns for the bwrap
      job** — to be confirmed on first CI run (ubuntu-latest enables it by default;
      low risk). Divert criterion below covers the failure case.
- [x] `platformdirs` available on PyPI and license-compatible (BSD). Trivial.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (M14 complete; host-native bwrap verified; one prereq —
      `ubuntu-latest` userns for the bwrap CI job — confirmed on first CI run, low risk)
- [x] Validation approach defined
- [x] Legs defined
- [x] Human go/no-go to mark the flight `ready`

---

## In-Flight

### Technical Approach

Seven legs, ordered so the cleanup that other backends depend on lands first and CI
lands last (it proves the whole thing host-native):

1. Relocate `SandboxError` (clean base for backend error surfaces).
2. OS-conventional `data_dir` + legacy `~/.the-one` move-migration.
3. External-runtime detection + non-Docker guidance (replace the Docker-flavored
   MCP spawn error at `stdio.py:287-293`).
4. Linux sandbox host-native: empirical userns probe + graceful degrade.
5. De-Docker the Makefile: host-native test invocation, Playwright on host; full
   suite green host-native **locally** (incl. `@requires_bwrap`).
6. Host-native pytest CI on GitHub Actions (`ubuntu-latest`) + a bwrap-provisioned
   Linux job + Playwright/Chromium provisioning.
7. Close surviving M14 debt: add the two missing docs, retire the already-satisfied
   items as completed-with-evidence, investigate the `test_connectors_e2e` flake.

Legs 1–4 and 7 are largely independent and can batch in parallel; Leg 1 lands early
for cleanliness but is **not** a hard predecessor (2/3/7 don't touch `SandboxError`).
Leg 5 depends on host-native bwrap (verified present) plus its own de-docker work —
**not** strictly on Leg 4's probe (the factory already selects Bubblewrap whenever
bwrap is present, so `@requires_bwrap` passes host-native independent of the probe).
Leg 6 depends on Leg 5 (host-native invocation + the `requires_bwrap` target it adds).

### Checkpoints

- [ ] `SandboxError` relocated; all import sites resolve; full suite + `ruff` green.
- [ ] `data_dir` resolves to the OS-conventional location per platform; a legacy
      `~/.the-one` is moved into place exactly once (integration-tested with temp
      dirs); secrets still decrypt afterward.
- [ ] A missing MCP runtime yields actionable, **non-Docker** guidance — no
      `docker`/`make rebuild` strings in the surfaced message.
- [ ] Linux sandbox enforces **host-native** (write-outside-scope blocked, network
      denied) with no Docker; the factory degrades to passthrough with a *distinct*
      WARNING when userns is unavailable; the `__init__` raise backstop + its test
      remain.
- [ ] `make test*` runs host-native (no `docker exec`); full suite green
      host-native locally **including an explicit `-m requires_bwrap` run** (these
      are default-deselected, `pyproject.toml:76`).
- [ ] pytest CI green on `ubuntu-latest`, including a dedicated bwrap-provisioned job
      running `-m requires_bwrap`.
- [ ] The two missing docs are added; the `test_connectors_e2e` flake is fixed or
      quarantined with rationale.

### Adaptation Criteria

**Divert if**:
- Host-native bwrap does **not** work on GitHub `ubuntu-latest` runners (userns
  disabled) — the bwrap CI job would need a different mechanism (e.g., a privileged
  container step or a self-hosted runner); re-plan Leg 6's bwrap job only, keeping
  the rest.
- The `~/.the-one` move-migration cannot be made safe against data loss in some
  real scenario the "move-only-when-target-absent" guard doesn't cover — fall back
  to copy-leaving-original and log the divergence.

**Acceptable variations**:
- Exact module/path for the relocated `SandboxError`.
- Whether runtime-absence guidance surfaces via the web error response, the CLI, or
  both — as long as it's actionable and Docker-free.
- Exact `platformdirs` API usage and whether a thin wrapper is added.

### Legs

Leg specs are generated by `/leg` (or per-leg design in `/agentic-workflow`). Planned
breakdown:

1. `relocate-sandbox-error` — Move the `SandboxError` *definition* into the sandbox
   package (`platform/sandbox/errors.py`), subclassing `MCPClientError` via a one-way
   import from `mcp/errors.py` (a verified zero-import leaf, so **no cycle**; **no
   re-export back-edge** — see Design Decisions). Repoint **every** importer that
   sources `SandboxError` from `the_one.mcp.errors` — complete set from design review
   (the naive "~2 importers" estimate was ~3× low; missing any fails the suite at
   import):
   - Source: `mcp/transports/stdio.py:74`, `platform/sandbox/__init__.py:17`
     (re-export + docstring line 10), `platform/sandbox/bubblewrap.py:35`,
     `mcp/_tool_provider.py:57`, `mcp/_tool.py:35`, `interfaces/web/api.py:1542`
     (function-local). In-`mcp`-package importers pull from
     `the_one.platform.sandbox.errors` directly (depends only on the `mcp.errors`
     leaf — no cycle).
   - Tests: `test_sandbox_contract.py:32` (repoint `CanonicalSandboxError` to
     `the_one.platform.sandbox.errors`, keeping the `issubclass` + `is` identity
     assertions meaningful), `test_sandbox_bubblewrap.py:15`,
     `test_mcp_sandbox_integration.py:76`, `test_mcp_stdio_sandbox.py:54`,
     `test_mcp_stdio_error_translation.py:20`, `test_mcp_pool.py:33`,
     `test_mcp_stdio_test_connect.py:281`, `test_mcp_tool_provider.py:50`.
   Drop the now-stale duplicated-predicate note at `factory.py:62-64`. Suite + `ruff`
   green. Lands early for a clean backend error base, but is **not** a hard
   predecessor of Legs 2/3/7.
2. `os-conventional-data-dir` — Add `platformdirs`; resolve `data_dir` per-OS at
   `the_one/config.py:22`; implement one-shot move-migration of legacy `~/.the-one`
   **only when `data_dir` is the default platformdirs-resolved path and the target is
   absent** (never under an explicit `THE_ONE_DATA_DIR`/test override — see Design
   Decisions); update the `tools/filesystem.py:48` doc example. Integration tests for
   per-OS path resolution, the migration, idempotency under repeated `ensure_dirs()`,
   and a test asserting an explicit override is **never** migrated. (The default-path
   test must monkeypatch the platformdirs resolver to a temp dir — conftest pins
   `THE_ONE_DATA_DIR`, so the default branch isn't reachable via env. Pydantic v2
   `model_fields_set` is a clean "was `data_dir` explicitly supplied?" signal;
   value-comparison against the resolved default also works.)
3. `external-runtime-detection` — `shutil.which` detection for `node`/`npx`/`uv`/
   `uvx`; replace the Docker-flavored spawn error at
   `mcp/transports/stdio.py:287-293` with actionable host-native guidance; surface
   it to the web/CLI MCP-source error path. Tests assert message content is
   Docker-free and names the missing runtime.
4. `linux-sandbox-host-native` — Add an empirical unprivileged-userns probe (real
   `unshare`/minimal-bwrap attempt; treat the absent procfs knob as a hint only) to
   the factory's **selection** logic (`factory.py:119-124`): when bwrap is present
   but userns is unavailable, select passthrough with a WARNING distinguishing
   no-bwrap from no-userns. The `BubblewrapSandbox.__init__` raise
   (`bubblewrap.py:83-89`) and its test **stay** as a backstop — additive change.
   Implement the probe as a module-level, monkeypatchable function (e.g.
   `_userns_available()` on the factory module) and update the existing pure-unit
   `tests/test_sandbox_factory.py` bwrap-present cases (lines 56-66, 109-119,
   162-181, 251-254) to stub it `True` — otherwise the real probe makes those tests
   environment-dependent (pass on WSL2, fail where userns is off), breaking the
   module's pure-unit contract. Tests for the enforced path and the userns-degraded
   path (probe stubbed both ways).
5. `de-docker-makefile` — Replace `docker exec the-one …` test targets with
   host-native `pytest` invocation (container-vs-host detection or explicit host
   targets); add an explicit host-native `-m requires_bwrap` target (these tests are
   **default-deselected** at `pyproject.toml:76`, so de-dockering alone runs zero of
   them); provision Playwright/Chromium on the host cache; ensure
   `scripts/run-tests.sh` group-kill semantics work host-native. Verify the full
   suite green host-native locally **including an explicit `-m requires_bwrap` run**.
6. `pytest-ci` — New GitHub Actions workflow running the host-native suite on
   `ubuntu-latest` (the default `not requires_bwrap` selection); a **dedicated job**
   that `apt-get install -y bubblewrap` and runs `-m requires_bwrap` so the boundary
   is exercised; Playwright/Chromium provisioning step. Keep the existing lint
   workflow alongside. (Installer-build/signing CI is Flight 6 — out of scope.)
7. `m14-debt-closeout` — Add the non-merged-usr `--symlink` portability caveat to
   `SECURITY-MODEL.md` and the fork-safety convention to `agents.md`; record the
   already-satisfied M14 doc items as closed-with-evidence (see Reconnaissance
   Report); investigate `test_connectors_e2e.py::test_e2e_full_lifecycle` under
   repeat/load and fix or quarantine with rationale.

A final `verify-integration` checkpoint is folded into Leg 6: green host-native CI
(including the bwrap job) is the integration proof that the app runs and tests with
no Docker.

**Known-remaining Docker call-sites (out of this flight's scope):** the *test* flow
is fully de-Dockered here, but non-test Makefile targets still shell into the
container — `make smoke-runtimes` (`docker compose exec`) and `make brand-assets`
(`docker exec the-one …`). They're not test targets, so they sit outside Leg 5; the
mission's broader "retire Docker entirely" finishes across later flights. Noted so
"no Docker anywhere" isn't read as already-complete.

---

## Verification

- **Per-leg**: unit/integration tests colocated with each change (path resolution &
  migration, error-message content, userns-probe both paths, relocated-error
  imports).
- **Sandbox containment**: the existing M14 `@requires_bwrap` kernel-enforcement
  suite — made to run host-native by this flight — is the containment regression net
  (real filesystem/network/process-table assertions, not argv shape).
- **Integration**: full host-native suite green locally (Leg 5) and in CI (Leg 6),
  the bwrap CI job exercising the boundary.
- **No new behavior test** this flight — see Design Decisions for rationale.
