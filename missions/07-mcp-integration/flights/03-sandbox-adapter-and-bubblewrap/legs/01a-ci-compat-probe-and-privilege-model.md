# Leg: 01a-ci-compat-probe-and-privilege-model

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Install `bubblewrap` in the dev container, grant it the precise privilege combo (`cap_add: SYS_ADMIN` + `security_opt: seccomp:unconfined`) required for unprivileged-user-namespace creation under Docker, rebuild the container, and run a 5-assertion CI compatibility probe to mechanically prove that bwrap can wrap-and-exec under the new privilege model — gating L1b on a green probe.

## Context

- **Hard gate.** This is the FIRST leg of F3 and a hard gate on the rest of the flight: if any of the 5 probe assertions fail, the leg signals `[BLOCKED:reason]` and Adaptation Criteria's "HAT-on-host (developer's WSL2)" scope-trim is the fallback escalation path. L1b does not begin until all 5 pass.
- **Why both privilege grants are necessary** (flight §10): Docker's default seccomp profile filters `unshare(CLONE_NEWUSER)` *regardless of capabilities granted*. So `cap_add: [SYS_ADMIN]` alone won't unblock the user-namespace ops bwrap needs — `seccomp:unconfined` is required to drop the syscall filter. The dual change is the minimum-viable privilege grant for bwrap inside this container, and was committed at flight design time after Architect cycle-1 review. See flight §10 for the threat-model justification (single-developer dev box; trust delegation already total via bind-mounts).
- **Live-environment baseline** captured during Phase 1b reconnaissance (flight log Part B):
  - Dev container (`python:3.11-slim`): `which bwrap` → not found; `unshare -U true` → `Operation not permitted`; `CapBnd: 00000000a80425fb` (standard docker default — no `CAP_SYS_ADMIN`).
  - HOST (WSL2): `bwrap 0.9.0` available; user-namespaces working.
- **Probe pattern stake-tests bwrap argv shape used by L3.** The 5 assertions were chosen to exercise specifically the bwrap features `BubblewrapSandbox.prepare_spawn` will rely on (per flight §10 Technical Approach + §2 cwd handling): `--die-with-parent`, `--unshare-user`, `--unshare-pid`, `--ro-bind / /`, `--tmpfs /tmp`, `--chdir`, `--unshare-net`. Failing any of these in CI means L3's compiled bwrap argv won't run there.
- **No code changes outside Dockerfile + docker-compose.yml.** This leg is intentionally narrow: it modifies only the dev container's image build + the privilege grant; no Python, no JS, no tests under `tests/`, no `the_one/` source. The probe is run as a series of one-shot bash commands inside the rebuilt container — no committed probe script.
- **Playwright browser-test image is NOT probed in this leg** (flight log Architect Q6): browser tests don't exercise the MCP runtime; the Playwright CI image will use the `THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1` double-flag bypass per §10 — wired up in L4, not here.
- **`THE_ONE_TEST_MODE` operational guardrail (§10)**: this flag must NEVER be set in `Dockerfile`, `docker-compose.yml`, `scripts/entrypoint.sh`, k8s manifests, or any image-level env source. It is a pytest-only signal. L1a verifies (defensively) that no pre-existing Dockerfile/compose env entry sets it, so L4's double-flag bypass remains a pytest-only escape hatch. If the grep finds an existing setting, [BLOCKED:reason] and escalate.
- **Stake-test probe pattern**: per the flight §Legs convention, the 5-assertion probe IS the stake test for bwrap behavior under the chosen privilege model. (Symbol-anchor convention from F1 debrief does NOT apply here — this leg's diff is YAML+Dockerfile only, no Python/JS symbols.)

## Inputs

What exists before this leg runs:
- Branch `flight/03-sandbox-adapter-and-bubblewrap` checked out (created in flight prep; see flight log "Flight transition" entry).
- `Dockerfile` at the repo root (`~/projects/the-one/Dockerfile`) installs `git`, `ca-certificates`, `curl` via a single `apt-get install` line, base image `python:3.11-slim`. No `bubblewrap` package.
- `docker-compose.yml` at the repo root (`~/projects/the-one/docker-compose.yml`) defines the `the-one` service with `build: .`, dev bind-mounts, `THE_ONE_*` env vars; no `cap_add` or `security_opt` keys.
- `Makefile` provides `make rebuild` which runs `docker compose build the-one` + `docker compose up -d the-one` + a `verify-serving` healthcheck.
- A running container `the-one` may already be up; `make rebuild` is the canonical rebuild path.
- F2 has landed: `MCPClient`, `connect_stdio`, `MCPClientError` hierarchy all present in `the_one/mcp/`. None of these are touched in this leg.
- Mission constraint #80 ("Bubblewrap available in the dev container for local MCP sandboxing — added to the Dockerfile's apt install line") commits the install location: the dev container's apt install line, not a separate apt-get RUN block.

## Outputs

What exists after this leg completes:
- `Dockerfile` apt install line extended to include `bubblewrap` alongside `git`, `ca-certificates`, `curl` (single `apt-get install` invocation; preserves the existing `--no-install-recommends` + `rm -rf /var/lib/apt/lists/*` pattern).
- `docker-compose.yml` `the-one` service block adds `cap_add: [SYS_ADMIN]` and `security_opt: ["seccomp:unconfined"]` keys (well-formed YAML; placement adjacent to existing service-level keys; no other service config altered).
- Dev container rebuilt via `make rebuild` (or `docker compose build the-one && docker compose up -d the-one`) so the new layers are live.
- All 5 probe assertions pass when run inside the rebuilt container (proven by the recipe in Verification Steps).
- Flight log entry under `## Leg Progress / ### L1a CI Compat Probe and Privilege Model` documenting:
  - Each of the 5 probe commands and their output (verbatim or truncated lines, e.g., the `bwrap --version` line).
  - Resolution of any unexpected output.
  - The privilege-model rationale paragraph (one paragraph paraphrasing flight §10 — "both grants required because docker's default seccomp filters `unshare(CLONE_NEWUSER)` regardless of capabilities").
  - Diagnostic recipe: how to re-run the 5-assertion probe later for re-validation (e.g., on a different host kernel or after a docker daemon upgrade).
- This leg's status field flipped to `completed` and the leg checked off in `flight.md`.
- **NO** code changes outside Dockerfile + docker-compose.yml; **NO** new files under `the_one/`, `tests/`, `scripts/`, or anywhere else.

## Acceptance Criteria

- [ ] **Dockerfile updated**: the apt install line includes `bubblewrap` between (or alphabetically near) the existing `git`, `ca-certificates`, `curl` packages. Single RUN, single `apt-get install`, `--no-install-recommends` preserved, list cleanup preserved. The line-3 comment above the apt install is updated to reflect the new package set (e.g., `# Install git, curl (healthcheck + fly CLI), ca-certificates, and bubblewrap (MCP sandbox runtime — F3 §10)` — it currently says only "git and curl"). Exact wording is illustrative; the criterion is that the comment mention bubblewrap and not omit ca-certificates.
- [ ] **docker-compose.yml updated**: the `the-one` service block contains `cap_add: [SYS_ADMIN]` (or list-form equivalent) AND `security_opt: ["seccomp:unconfined"]` (or list-form equivalent). Both keys present; YAML parses cleanly via `docker compose config the-one` AND the grep recipe in Verification Steps prints both grants under the `the-one` service (not just somewhere in the rendered output).
- [ ] **No source-code changes**: `git status --porcelain` after the leg shows NO modifications under `the_one/`, `tests/`, `scripts/`, `pyproject.toml`, or `Makefile`. (Modifications to `Dockerfile`, `docker-compose.yml`, the flight log, the flight, and this leg file are expected.)
- [ ] **No `THE_ONE_TEST_MODE` leak in image-level env**: `grep -RIn 'THE_ONE_TEST_MODE' Dockerfile docker-compose.yml scripts/ Makefile 2>/dev/null` returns no matches (defensive check per §10's operational guardrail). If the grep finds a setting, [BLOCKED:reason] before proceeding.
- [ ] **Container rebuilt successfully**: `docker compose build the-one` + `docker compose up -d the-one` exits 0; the container reaches a `running` state via `docker compose ps`. (`make rebuild`'s `verify-serving` healthcheck additionally probes the FastAPI surface and depends on Ollama being reachable on the host; if Ollama is not running, fall back to manual `docker compose ps` verification — see Edge Cases.)
- [ ] **Probe assertion 1 (bwrap installed)**: `docker compose exec -T the-one bwrap --version` prints a version line beginning with `bubblewrap` (e.g., `bubblewrap 0.6.x` or `0.8.x` — Debian bookworm-slim ships ~0.8, but exact version is not constrained; the assertion is "version line prints, exit 0").
- [ ] **Probe assertion 2 (user-namespace unshare unblocked)**: `docker compose exec -T the-one unshare -U /bin/echo test` exits 0 and prints `test`. Specifically, the output must NOT contain `Operation not permitted` (the pre-§10 baseline failure). This proves seccomp + capability combo is correct.
- [ ] **Probe assertion 3 (bwrap minimal spawn works)**: `docker compose exec -T the-one bwrap --die-with-parent --unshare-user --unshare-pid --ro-bind / / --tmpfs /tmp -- /bin/echo hello` exits 0 and prints `hello`. This stake-tests the L3 `BubblewrapSandbox.prepare_spawn` argv floor (--unshare-user, --unshare-pid, --ro-bind /, --tmpfs /tmp).
- [ ] **Probe assertion 4 (bwrap --chdir cwd-handling stake-test)**: `docker compose exec -T the-one bwrap --die-with-parent --unshare-user --ro-bind / / --chdir /tmp -- /bin/pwd` exits 0 and prints `/tmp`. This stake-tests the §2 cwd-inside-ro-floor behavior that L3 + L4 will rely on.
- [ ] **Probe assertion 5 (bwrap --unshare-net network refusal)**: `docker compose exec -T the-one bwrap --die-with-parent --unshare-user --unshare-net --ro-bind / / -- /bin/sh -c 'getent hosts api.github.com 2>&1; exit 0'` exits 0 (the outer shell exits 0 to capture diagnostics), and the output contains a network-failure indicator — empty stdout, OR stderr containing `Temporary failure in name resolution` / `Name or service not known` / similar. Specifically, the output must NOT contain a successful resolution (no IPv4/IPv6 line printed). This stake-tests that `--unshare-net` actually disables the network namespace.
- [ ] **Hard-gate behavior on failure**: if any of assertions 1–5 fail, the leg signals `[BLOCKED:reason]` with the failing assertion(s) named, the verbatim error output, and a recommendation to invoke the Adaptation Criteria fallback ("HAT-on-host (developer's WSL2)" scope-trim) before L1b begins.
- [ ] **Flight log updated**: the flight log gains a `### L1a CI Compat Probe and Privilege Model` section under `## Leg Progress` containing (a) the 5 probe commands and their captured output; (b) one paragraph of privilege-model rationale paraphrased from §10 noting the actual Debian-shipped bwrap version; (c) a diagnostic recipe block for re-running the probe later (or a one-line pointer to this leg file's Verification Steps section — both are acceptable).
- [ ] **Leg status flipped to `completed`** (post-probe) by the implementing agent. (Status `ready` is set by the orchestrator after design review approves; `completed` is set here once all probe assertions pass.) Leg checkbox in `flight.md` ticked.

## Verification Steps

Run each command inside the dev container after `make rebuild`. Capture output verbatim into the flight log entry.

```bash
# --- Pre-checks: rebuild the container with the new privilege model in place ---
cd ~/projects/the-one
git status --short
# Expect: no modifications under the_one/, tests/, scripts/, pyproject.toml, Makefile.
# Expected modifications: Dockerfile, docker-compose.yml, flight artifacts.

# Defensive: ensure no THE_ONE_TEST_MODE leak in image-level env (§10 guardrail)
grep -RIn 'THE_ONE_TEST_MODE' Dockerfile docker-compose.yml scripts/ Makefile 2>/dev/null
# Expect: no matches. If a match exists, [BLOCKED:reason] before proceeding.

# Service-scoped config check — prints the cap_add and security_opt blocks
# under the the-one service so they're visually verifiable
docker compose config the-one | grep -E 'cap_add:|security_opt:|SYS_ADMIN|seccomp:unconfined'
# Expect: 4 lines — the two block headers and the two values

# Build + recreate container (use direct compose rather than `make rebuild` if
# Ollama isn't running on the host — verify-serving depends on the LLM endpoint;
# see Edge Cases)
docker compose build the-one && docker compose up -d --force-recreate the-one

docker compose ps
# Expect: the-one is running

# --- Assertion 1: bwrap is installed (capture both stdout+stderr defensively) ---
docker compose exec -T the-one bwrap --version 2>&1
# Expect: a line beginning "bubblewrap" (e.g., Debian bookworm-slim ships ~0.8.0); exit 0

# --- Assertion 2: unshare(CLONE_NEWUSER) is no longer EPERM ---
docker compose exec -T the-one unshare -U /bin/echo test
# Expect: prints "test"; exit 0
# Failure mode (§10 not applied correctly): "unshare: unshare failed: Operation not permitted"

# --- Assertion 3: minimal bwrap spawn (matches L3's argv floor) ---
docker compose exec -T the-one bwrap \
    --die-with-parent --unshare-user --unshare-pid \
    --ro-bind / / --tmpfs /tmp \
    -- /bin/echo hello
# Expect: prints "hello"; exit 0

# --- Assertion 4: bwrap --chdir cwd-inside-ro-floor (stake-tests §2) ---
docker compose exec -T the-one bwrap \
    --die-with-parent --unshare-user \
    --ro-bind / / --chdir /tmp \
    -- /bin/pwd
# Expect: prints "/tmp"; exit 0

# --- Assertion 5: --unshare-net actually blocks network ---
docker compose exec -T the-one bwrap \
    --die-with-parent --unshare-user --unshare-net \
    --ro-bind / / \
    -- /bin/sh -c 'getent hosts api.github.com 2>&1; exit 0'
# Expect: empty stdout OR a name-resolution-failure line; specifically NOT a successful IPv4/IPv6 line.
# Verbatim acceptable outputs include: "" (silent), "<...> Temporary failure in name resolution",
# "<...> Name or service not known", or other glibc resolver failure shapes. Outer shell exits 0
# so the assertion captures the diagnostic regardless.

# --- Control assertion: prove non-sandboxed DNS works (de-ambiguates assertion 5) ---
docker compose exec -T the-one getent hosts api.github.com
# Expect: a successful IPv4 line. If this FAILS, the host's DNS is broken and assertion 5
# is INCONCLUSIVE (DNS was already blocked, regardless of --unshare-net). Do NOT mark
# assertion 5 as passed in that case. Recovery: either fix host DNS and re-run, OR
# substitute an IP-literal probe that doesn't depend on resolver state, e.g.:
#   docker compose exec -T the-one bwrap --die-with-parent --unshare-user --unshare-net \
#       --ro-bind / / -- /bin/bash -c 'cat < /dev/tcp/8.8.8.8/53; exit 0'
# NOTE: /dev/tcp is bash-specific magic; Debian slim's /bin/sh is dash and does NOT
# support it. The fallback shell MUST be /bin/bash (which is present in python:3.11-slim).
# Under --unshare-net this should fail with "No route to host" or similar, regardless
# of DNS state — proving --unshare-net works even when DNS is broken.

# --- Cleanup verification: no stray containers or escaped processes ---
docker compose exec -T the-one pgrep -f 'bwrap' || true
# Expect: no running bwrap processes (each assertion was one-shot; --die-with-parent
# guarantees no orphans).
```

If ANY assertion fails or produces unexpected output:
1. Do NOT proceed to L1b.
2. Capture the verbatim output in the flight log under `## Anomalies`.
3. Diagnose: most likely causes are (a) seccomp grant didn't take effect (verify with `docker compose exec the-one grep Seccomp /proc/1/status` — should show `Seccomp: 0` for unconfined), (b) capability grant didn't take effect (verify with `docker compose exec the-one capsh --print | grep sys_admin` — should list `cap_sys_admin` in the bounding set), (c) host kernel doesn't permit unprivileged user-namespaces under any combination (rare on modern Linux/WSL2; if so, escalate to the §10 Adaptation Criteria fallback "HAT-on-host (WSL2)" scope-trim and discuss with the user before L1b).
4. Signal `[BLOCKED:reason]`.

## Implementation Guidance

1. **Edit `Dockerfile`** (two changes — one line + one comment). The current apt install line installs `git`, `ca-certificates`, `curl`. Add `bubblewrap` to the package list (alphabetical-ish placement is fine), preserving the single-RUN pattern with `--no-install-recommends` + `rm -rf /var/lib/apt/lists/*`. ALSO update the comment immediately above the apt line — it currently reads `# Install git and curl (health check + fly CLI download at runtime)` which is already stale wrt `ca-certificates` and will be more stale after `bubblewrap` lands. Generalize, e.g., `# Install git, curl (healthcheck + fly CLI), ca-certificates, and bubblewrap (MCP sandbox runtime — F3 §10)`.

2. **Edit `docker-compose.yml`** to add the privilege grants to the `the-one` service. Place the new keys adjacent to existing top-level service keys WITHOUT splitting an existing logical grouping — the recommended insertion point is **between `extra_hosts:` and `networks:`** (or alternatively between `ports:` and `command:` if you prefer keeping security-related keys near the runtime config). Verify YAML well-formedness with `docker compose config the-one`. Add a small comment block explaining why both grants are needed (paraphrasing flight §10):

   ```yaml
       # Sandbox privilege model (F3 §10): bubblewrap requires unprivileged
       # user-namespace creation, which docker's default seccomp profile
       # filters regardless of capabilities. Both grants are necessary —
       # SYS_ADMIN alone won't unblock unshare(CLONE_NEWUSER). See flight
       # spec §10 for the threat-model justification.
       cap_add:
         - SYS_ADMIN
       security_opt:
         - seccomp:unconfined
   ```

   Verify with `docker compose config`.

3. **Rebuild the container.** Two paths — pick based on whether the developer host has Ollama running:
   - **Preferred (when Ollama is reachable)**: `make rebuild` — runs `docker compose build the-one && docker compose up -d the-one` and a `verify-serving` healthcheck that probes the FastAPI `/api/info` endpoint, which depends on the LLM provider being reachable.
   - **Fallback (when Ollama is not running on the host)**: `docker compose build the-one && docker compose up -d --force-recreate the-one`, then verify the container is up via `docker compose ps`. The probe assertions don't need the LLM; they only need bwrap inside the rebuilt container. If `verify-serving` is the only thing failing and the container itself is up, the leg can proceed.

   Expect the build to take several minutes the first time (apt fetch for bubblewrap); subsequent rebuilds will reuse the layer cache unless the apt list itself changes.

4. **Run the 5-assertion probe** per the Verification Steps section. Capture output from each command; copy verbatim into the flight log entry.

5. **Update the flight log** with a `### L1a CI Compat Probe and Privilege Model` subsection under `## Leg Progress` containing:
   - Started/Completed timestamps.
   - The 5 probe commands + captured output (truncated to first/last few lines if very long; the version line + the success/failure determinant is what matters).
   - A one-paragraph rationale paraphrasing flight §10 ("Both grants required because docker's default seccomp profile filters `unshare(CLONE_NEWUSER)` regardless of capabilities — confirmed via `unshare -U true` returning EPERM under `cap_add: [SYS_ADMIN]` alone in pre-leg probing.").
   - A diagnostic recipe block: a fenced bash code block listing the same 5 commands with comments on what each proves, suitable for copy-paste re-validation by a future maintainer (e.g., after a kernel upgrade or a docker daemon swap).

6. **Flip leg status to `completed` and check off in flight.md**. Per the post-completion checklist; do NOT commit (the agentic-workflow batches commits at flight end per flight log "Flight Director Notes").

## Edge Cases

- **`bubblewrap` package name vs binary name**: the Debian/Ubuntu package is `bubblewrap` (not `bwrap`). The binary it installs is `/usr/bin/bwrap`. The Dockerfile installs the package; the probe invokes the binary. `shutil.which("bwrap")` (used by L3) will find it via PATH.
- **Container already running with old image**: `make rebuild` handles this — `docker compose up -d` recreates the container if the image hash changed. If for some reason the container is not recreated (rare; possible if compose detects no change), force it with `docker compose up -d --force-recreate the-one`.
- **`bwrap --version` may print to stderr depending on packaging**: capture with `2>&1` if assertion 1 fails on stdout-only inspection. The Debian package historically prints to stdout, but version output channel is not contractually stable across distros.
- **Network probe (assertion 5) on hosts without DNS**: if the host has no DNS configured at all, even the non-sandboxed `getent hosts api.github.com` would fail — making assertion 5 ambiguous (was it `--unshare-net`, or was DNS already broken?). The probe wraps the inner command in `sh -c '... ; exit 0'` so the outer exit is 0 regardless; the assertion is on the OUTPUT contents (must contain a failure indicator OR be empty). The control command in Verification Steps proves the container's DNS works in the non-sandboxed case; if the control fails, mark assertion 5 INCONCLUSIVE (do NOT pass it) and use the documented IP-literal fallback probe instead.
- **`make rebuild` depends on Ollama**: the Makefile's `rebuild` target invokes `verify-serving` as the success gate, which probes the FastAPI `/api/info` endpoint that in turn depends on the LLM provider (Ollama at `host.docker.internal:11434` per docker-compose.yml). If Ollama isn't running on the dev host, `make rebuild` will report a healthcheck failure even though the container itself is fine for L1a's purposes. Implementation Guidance §3 documents the fallback path (`docker compose build` + `up -d --force-recreate` + `docker compose ps`).
- **`--die-with-parent` behavior under WSL2 kernel**: §Adaptation Criteria flags this as a divert-if condition — if `--die-with-parent` doesn't behave as advertised under our specific kernel/seccomp combo, F3 documents the gap. None of the 5 assertions directly tests `--die-with-parent` semantics; they only test that bwrap accepts the flag without error. Deeper validation belongs in L4 integration tests, not here.
- **Diff size discipline**: this leg's diff should be **tiny** — one line added to Dockerfile (or 2 if a comment is added inline), 8–10 lines added to docker-compose.yml (with comment block). If the diff exceeds ~20 lines outside the flight log, the leg is doing something it wasn't asked to do; reject and re-scope.
- **Multiple developers / shared container**: this leg presumes a single-developer dev box per the §10 threat model. If another developer is sharing the container, the SYS_ADMIN + unconfined-seccomp grant applies to all users of the container — which is consistent with the existing total-trust posture (bind-mounts, etc.).

## Files Affected

- `~/projects/the-one/Dockerfile` — add `bubblewrap` to the apt install package list.
- `~/projects/the-one/docker-compose.yml` — add `cap_add: [SYS_ADMIN]` and `security_opt: [seccomp:unconfined]` to the `the-one` service block.
- `~/projects/the-one/missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight-log.md` — append `### L1a CI Compat Probe and Privilege Model` subsection under `## Leg Progress` with probe output + privilege-model rationale + diagnostic recipe.
- `~/projects/the-one/missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight.md` — tick the leg checkbox under `### Legs` after completion.
- `~/projects/the-one/missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/legs/01a-ci-compat-probe-and-privilege-model.md` — flip `Status:` from `planning` → `ready` (after design review) → `completed` (post-probe).

**Explicitly NOT modified by this leg**: `the_one/` source, `tests/`, `pyproject.toml`, `scripts/entrypoint.sh`, `Makefile`, `CLAUDE.md`, `the_one/agents.md`, `.flightops/`. Any of those changes belong to L1b or later legs.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] All 5 probe assertions passed (output captured in flight log)
- [ ] `git status --porcelain` shows ONLY Dockerfile, docker-compose.yml, flight-log.md, flight.md, and this leg's file as modified (no other paths)
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress / ### L1a CI Compat Probe and Privilege Model`, including the 5 captured outputs + the privilege-model rationale paragraph + the diagnostic recipe
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end (per flight log "Flight Director Notes")
