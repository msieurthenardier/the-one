# Leg: 01b-f1-validator-extension-and-docs

**Status**: completed
**Flight**: [Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend](../flight.md)

## Objective

Extend F1's `_validate_mcp_source_config` with a `config.sandbox` sub-block validator (`writable_paths: list[str]` and `network_allowed: bool`, both optional with safe defaults), add 2 validation tests in `TestMCPSourceAPI`, and document F3's contracts (sandbox profile schema, strict-by-default trust model, dev/CI privilege-model decision, `MCPSandbox` Protocol forward-reference) in `CLAUDE.md` and `the_one/agents.md` so L2+ implementers can read the contract before the Protocol itself lands.

## Context

- **Documentation + validation-only leg.** Tiny Python diff (one new validation block inside an existing function plus 2 new tests); the bulk of the diff is doc prose. No runtime / sandbox code; no UI. The `MCPSandbox` Protocol does NOT yet exist (L2 lands it) — docs forward-reference it with an explicit "will be defined in L2" note so the doc paragraph is still useful before the symbol exists.
- **Why this leg comes after L1a, before L2.** L1a (completed 2026-05-06; flight log "Leg Progress / L1a") proved bwrap actually runs in the dev container under §10's privilege grants; that unblocks the rest of F3. L1b lands the cheapest two pieces that other legs and other-flight engineers need to be able to read: the validator (so the API rejects malformed sandbox sub-blocks at API time, before L4's runtime ever sees them) and the docs (so the F3 sandbox decisions §1, §4, §10, §11, §13 are searchable in CLAUDE.md / agents.md without spelunking the flight artifact). L2's adapter-contract leg can then cite the now-already-written agents.md paragraph for its capability matrix.
- **Validator pattern: "trust the runtime."** F1's existing `_validate_mcp_source_config` (`the_one/interfaces/web/api.py::_validate_mcp_source_config`) validates **shapes** at the API layer (string, list[str], dict[str,str]) but does NOT enforce **semantic** validity (e.g., `command` is a valid binary path, `cwd` exists on disk, env values are non-empty). Per flight §4, the sandbox sub-block follows the same pattern: `writable_paths` entries must each be a `str`, but absolute-path-shape (leading `/`, no `..`, exists on disk) is NOT enforced at the API layer — that's the runtime's responsibility (`bwrap --bind` and `BubblewrapSandbox.prepare_spawn` will fail loudly with `MCPSandboxError` at spawn time per §6's error-message catalog).
- **Sandbox sub-block storage shape** (flight §4): `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` lives plaintext alongside `command`/`args`/`env`. NOT encrypted (no secrets here; just policy). Both fields are OPTIONAL — when absent, defaults are `writable_paths=[]` (empty, fully read-only sandbox) and `network_allowed=False` (network OFF). The validator only fires when the field is present. The `SandboxProfile` dataclass that L2 defines will own the actual default-fill logic (its `from_dict` factory per flight §12); the API layer just gates shapes on the way in.
- **Stdio-only.** The sandbox section applies only to `type=="stdio"` sources. `streamable-http` sources don't spawn local processes, so `config.sandbox` on a streamable-http source is meaningless. **Decision for this leg**: validate `config.sandbox` only inside the `if source.type == "stdio":` branch. If a streamable-http source includes `config.sandbox`, the field is silently ignored at the API layer (the existing validator already ignores any non-listed config keys for streamable-http; no negative test is added here because none of the existing streamable-http tests assert "rejects extra keys"). This matches §5's UI decision to render the Sandbox sub-section for stdio mode only. Future-proofing: if remote-MCP sandboxing ever becomes a thing, a separate sandbox sub-block will live there with different semantics; this leg does NOT pre-emptively gate streamable-http for it.
- **Forward-reference to `MCPSandbox` Protocol.** L2 lands `MCPSandbox` (Protocol), `SandboxProfile` (dataclass), `SpawnSpec` (dataclass), and `MCPSandboxError` per flight §11 / §12 / §6 / §8. This leg's docs prose names those symbols and their module paths but explicitly notes "L2 lands the actual Protocol; this leg references it in docs" so a reader who greps for the symbol after L1b lands and before L2 lands doesn't get confused. The doc paragraph is structured so L2 can edit-in-place to tighten "will be defined" → "is defined at" without restructuring.
- **Per-leg lint gate.** Per flight §Legs convention: `ruff check the_one/ tests/` clean (or "no NEW ruff errors" relative to the pre-leg baseline) before `[HANDOFF:review-needed]`. The diff is small enough that a NEW-error check is overkill — full clean is the target.
- **Citation style.** Per flight §Legs: anchor by symbol-name (NOT `file:LINE`). The leg artifact uses `the_one/interfaces/web/api.py::_validate_mcp_source_config`-style anchors throughout.

## Inputs

What exists before this leg runs:

- L1a `completed` (flight log `## Leg Progress / ### L1a CI Compat Probe and Privilege Model`); dev container has `bubblewrap 0.11.0` installed and the §10 privilege grants applied; 5-assertion probe verbatim output captured.
- `the_one/interfaces/web/api.py::_validate_mcp_source_config` exists and currently validates stdio (`command`, `args`, `cwd`, `env`) and streamable-http (`url`, `headers`, `oauth.{issuer_url,client_id,scopes,redirect_uri}`) sub-blocks per F1; raises `HTTPException(status_code=422, detail=...)` on shape mismatch; called from both `create_mcp_source` and `update_mcp_source` after `MCPSource.model_validate`. Return type is `None`.
- `tests/test_db_api.py::TestMCPSourceAPI` exists; contains 13 existing tests covering CRUD, masking, `__MASKED__` PUT round-trip, validation rejection (stdio missing `command`, streamable-http missing `url`, unknown transport, env non-string-value, env non-dict), `/types` route ordering, and PUT transport-type-switch revalidation. Style: pytest `async def`, `client: AsyncClient` fixture from module-level `client` fixture, `assert resp.status_code == 422`, `assert "<keyword>" in resp.json()["detail"]`. Each test sends a single POST to `/api/mcp-sources` with `name`, `type`, `config`, `secrets` JSON body and asserts on the response.
- `the_one/CLAUDE.md` exists; has section `## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)`. F3 contracts will follow this section.
- `the_one/agents.md` exists; has bullet list "**F2 (MCP Client Foundation) contracts** — for full text, see CLAUDE.md..." inside `### the_one/db/repositories.py`. F3 contracts follow the same forward-pointer pattern.
- Flight artifact `flights/03-sandbox-adapter-and-bubblewrap/flight.md` is the authoritative source for §1, §4, §10, §11, §12, §13 — docs paragraph paraphrases NOT copies (CLAUDE.md / agents.md are the contract surface; flight.md is the design rationale).
- F2's existing `the_one/mcp/errors.py::MCPClientError` hierarchy exists; L2 will add `MCPSandboxError(MCPClientError)` per §6.
- No `THE_ONE_TEST_MODE` leak in image-level env (verified by L1a's defensive grep); §10 operational guardrail intact.

## Outputs

What exists after this leg completes:

- `the_one/interfaces/web/api.py::_validate_mcp_source_config` extended:
  - Inside the `if source.type == "stdio":` branch (after the existing `env` check, before the closing of that branch), a new sandbox sub-block validator runs when `cfg.get("sandbox")` is not None:
    - `sandbox` must be a `dict` (otherwise 422 with `"MCP source config.sandbox must be a dict if present."`).
    - If `"writable_paths"` is in `sandbox`: must be `list` of `str` (otherwise 422 with `"MCP source config.sandbox.writable_paths must be a list of strings."`). **No absolute-path-shape check** (per "trust the runtime"; L4's runtime raises `MCPSandboxError` if a path doesn't exist).
    - If `"network_allowed"` is in `sandbox`: must be `bool` (otherwise 422 with `"MCP source config.sandbox.network_allowed must be a boolean."`).
    - Unknown keys in the `sandbox` dict are NOT rejected at the API layer (mirrors the existing oauth sub-block which ignores unrecognised keys, and §12's `SandboxProfile.from_dict` policy of "unknown keys ignored"). Reserved namespace fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`) thus pass through untouched, ready for L2's `from_dict` to consume.
  - Both fields are OPTIONAL — absence does not 422; the runtime applies the strict-floor defaults (empty `writable_paths`, `network_allowed=False`) per `SandboxProfile` field defaults that L2 lands.
  - The validator's docstring is extended with one paragraph naming the new sub-block and the "trust the runtime" rationale.

- `tests/test_db_api.py::TestMCPSourceAPI` gains 2 new tests immediately after `test_validation_rejects_stdio_config_env_non_dict`:
  - `test_validation_rejects_stdio_config_sandbox_writable_paths_non_string_entry` — POST a stdio source with `config={"command": "echo", "sandbox": {"writable_paths": ["/data", 42]}}`. Asserts `resp.status_code == 422` and `"config.sandbox.writable_paths"` substring is in `resp.json()["detail"]`.
  - `test_validation_rejects_stdio_config_sandbox_network_allowed_non_bool` — POST a stdio source with `config={"command": "echo", "sandbox": {"network_allowed": "yes"}}`. Asserts `resp.status_code == 422` and `"config.sandbox.network_allowed"` substring is in `resp.json()["detail"]`.
  - Test docstrings reference "L1b: F1 API validator extended for `config.sandbox` sub-block per F3 §4."

- `CLAUDE.md` gains a new section `## F3 (MCP Sandbox) Contracts (authoritative for F4-F8)` immediately after `## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)`. The section contains numbered contracts paraphrased from flight design decisions §1, §4, §10, §11, §13 and a forward-reference to L2:
  1. **Module home** — `the_one/platform/sandbox/{__init__.py, base.py, bubblewrap.py}` (peer of `the_one/platform/env.py`, `the_one/platform/pty.py`). `MCPSandboxError` lives canonically at `the_one/mcp/errors.py` (alongside other `MCPClientError` subclasses); `the_one/platform/sandbox/__init__.py` re-exports for convenience but the canonical import path is `from the_one.mcp.errors import MCPSandboxError`. **L2 lands the actual code; this entry documents the contract for readers landing between L1b and L2.**
  2. **Strict-by-default trust model (§1)** — Locally spawned MCP server processes get a sandbox whose default posture is read-only filesystem outside an explicit operator-configured `writable_paths` list, network OFF unless `network_allowed=True`. Mission constraint #47's "trip-wire, not fence" framing applies in the OTHER direction here: the env-allowlist alone is a trip-wire; bwrap is the actual fence. Operator-trust threat model: the operator has some responsibility to not configure untrusted MCPs with broad `writable_paths` or `network_allowed=True`; the sandbox doesn't claim to defend against operator mistakes, only against MCP-author mistakes / supply-chain compromises within the sandboxed scope.
  3. **Sandbox profile storage (§4)** — `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` plaintext (NOT encrypted; no secrets). Both fields optional; defaults `[]` and `false` when absent. Reserved namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`, all bool-defaulting-True per §12) live in the same dict as advanced JSON-edit-only knobs; the API validator passes them through without inspection per "unknown keys ignored." NOT a separate column / NOT a separate table — schema unchanged from F1's v10. **L1b extends `_validate_mcp_source_config` with this sub-block validator at the API boundary; L2 lands `SandboxProfile.from_dict` for the runtime side.**
  4. **`MCPSandbox` Protocol shape (§11)** — `prepare_spawn(profile: SandboxProfile, command: str, args: list[str], env: dict[str, str], cwd: str | None = None) -> SpawnSpec`. `SpawnSpec` is a frozen dataclass with `command/args/env/cwd` plus Windows-only `creation_flags: int = 0` and `attribute_list: dict[str, Any] | None = None`. Linux/macOS callers feed `spec.command/args/env/cwd` directly into `mcp.client.stdio.StdioServerParameters(...)`; Windows fields exist purely so a future Windows backend can populate them without changing the Protocol. **L2 lands the Protocol; L3 implements `BubblewrapSandbox.prepare_spawn`; L4 wires it into `connect_stdio`.**
  5. **`MCPSandboxError(MCPClientError)` failure-mode boundary (§6)** — Failures BEFORE bwrap successfully wraps-and-execs the target command raise `MCPSandboxError` (bwrap binary missing, `writable_paths` entry doesn't exist, `EPERM` on `unshare`, container lacks privileges). Failures AFTER (target spawned but exits non-zero, initialize handshake fails) raise the existing `MCPConnectionError` / `MCPVersionMismatch` per F2. There is NO unsandboxed fallback; production never reads `THE_ONE_SANDBOX_DISABLED`. **L2 adds the exception class; L4 enforces the boundary in `connect_stdio`.**
  6. **Privilege model: dev container, browser-test CI, production (§10)** — Dev container: `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` (BOTH; SYS_ADMIN alone is filtered by docker's default seccomp profile per L1a's pre-§10 baseline `unshare(CLONE_NEWUSER) → EPERM`). Browser-test CI image (`mcr.microsoft.com/playwright/python:v1.58.0-jammy`): no privilege grants; `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` (BOTH; the double-flag is set ONLY by `tests/conftest.py::pytest_configure`, never in any image-level env source). Production: no flag, no skip — bwrap mandatory; `MCPSandboxError` raises if missing. **Operational guardrail**: `THE_ONE_TEST_MODE` MUST NOT appear in any Dockerfile, docker-compose service env, entrypoint script, k8s manifest, or CI variable; presence outside pytest is a deployment defect. **L1a verified the dev-container privilege grant lifted `unshare -U` EPERM and the 5-assertion probe; L4 wires the double-flag bypass.**
  7. **HOME override under sandbox (§13)** — `BubblewrapSandbox.prepare_spawn` overrides `env["HOME"] = "/tmp"` regardless of operator-supplied env. Reasoning: the assembled environ inherits HOME from the host (likely `/root` in the dev container), and `--ro-bind / /` makes `/root` read-accessible-but-not-writable, so subprocesses writing to `~/.cache` would hit EACCES. `/tmp` is writable via `--tmpfs /tmp`. **Operators cannot override HOME via the kv-table** — this is sandbox policy, not operator-configurable. Operators needing a specific HOME add the path to `writable_paths` AND set a different env var (e.g., `MY_HOME`) pointing at it. **L3 implements the override.**

  Sub-bullet at the end of the new section: "Forward-references in this section name symbols (`MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `MCPSandboxError`) that L2 lands; this F3 contract section is authoritative for the contracts, and the symbols themselves are authoritative for the implementation. Readers landing between L1b and L2 should treat the symbols as named-but-not-yet-importable."

- `the_one/agents.md` gains a paragraph + bullet block immediately after the existing F2 bullet list (just before `### the_one/agent/`). Format mirrors the F2 bullet block — header `**F3 (MCP Sandbox) contracts** — for full text, see CLAUDE.md "F3 (MCP Sandbox) Contracts":` followed by ~6 bullets, each one a one-line summary of items 1–7 above (collapsing where useful):
  - **F3 module home**: `the_one/platform/sandbox/` (peer of `the_one/platform/env.py`); `MCPSandboxError` canonical at `the_one/mcp/errors.py`. **L2 lands the package.**
  - **F3 trust model**: strict by default — read-only FS outside `writable_paths`; network OFF unless `network_allowed=True`. Operator's responsibility to scope writable paths and network policy per source.
  - **F3 sandbox-profile storage**: `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` plaintext; both fields optional; defaults `[]` / `false`; namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`) JSON-edit-only via API. **L1b extends the F1 API validator; L2 lands `SandboxProfile.from_dict`.**
  - **F3 Protocol shape**: `MCPSandbox.prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec`; `SpawnSpec` is frozen with command/args/env/cwd + Windows-only `creation_flags`/`attribute_list`. Linux/macOS callers feed `spec.command/args/env/cwd` into `StdioServerParameters`. **L2 lands.**
  - **F3 failure boundary**: `MCPSandboxError(MCPClientError)` for setup failures (bwrap missing, writable_paths nonexistent, EPERM on unshare); F2's `MCPConnectionError` for post-spawn failures. No unsandboxed fallback. **L2 adds the exception class; L4 enforces.**
  - **F3 privilege model**: dev container `cap_add: [SYS_ADMIN]` + `security_opt: [seccomp:unconfined]` (both required); Playwright CI uses pytest-only `THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1` double-flag bypass; production sandbox always on. **L1a applied the dev-container grants; L4 wires the bypass.**
  - **F3 HOME override**: `BubblewrapSandbox` forces `env["HOME"] = "/tmp"` so `~/.cache`-writing MCPs find a usable home dir under `--tmpfs /tmp`. Sandbox policy, not operator-configurable. **L3 implements.**

- This leg's status flipped from `planning` → `ready` (after design review approves) → `completed` (post-implementation).
- Leg checkbox in `flight.md` ticked.
- Flight log gains a `### L1b F1 Validator Extension and Docs` section under `## Leg Progress` containing: implementation summary (3 lines), the 2 new test names, and a one-line confirmation that `ruff check` is clean and `pytest tests/test_db_api.py::TestMCPSourceAPI -v` passes (count grows from 13 to 15).

## Acceptance Criteria

- [ ] **Validator extended for `config.sandbox` sub-block (stdio only)**: `the_one/interfaces/web/api.py::_validate_mcp_source_config` rejects with `HTTPException(status_code=422, ...)` and a sandbox-naming detail string when (a) `cfg["sandbox"]` is not a dict, (b) `cfg["sandbox"]["writable_paths"]` is present but not a list, (c) `cfg["sandbox"]["writable_paths"]` is a list containing a non-string entry, (d) `cfg["sandbox"]["network_allowed"]` is present but not a bool. The sandbox sub-block is gated inside the `if source.type == "stdio":` branch; streamable-http sources with `config.sandbox` are silently accepted (the field is ignored downstream by F4+).
- [ ] **Defaults work**: a POST to `/api/mcp-sources` with `{"name": "X", "type": "stdio", "config": {"command": "echo"}}` (NO sandbox key) returns 201 — the missing sandbox field does NOT trigger validation. A POST with `{"name": "Y", "type": "stdio", "config": {"command": "echo", "sandbox": {}}}` (empty sandbox dict) also returns 201 — both sub-fields optional.
- [ ] **Three new tests added** to `tests/test_db_api.py::TestMCPSourceAPI`:
  - `test_validation_rejects_stdio_config_sandbox_writable_paths_non_string_entry` — POST `config={"command": "echo", "sandbox": {"writable_paths": ["/data", 42]}}` → 422 with `"config.sandbox.writable_paths"` in detail.
  - `test_validation_rejects_stdio_config_sandbox_network_allowed_non_bool` — POST `config={"command": "echo", "sandbox": {"network_allowed": "yes"}}` → 422 with `"config.sandbox.network_allowed"` in detail.
  - `test_validation_accepts_stdio_config_empty_sandbox_dict` — POST `config={"command": "echo", "sandbox": {}}` → 201/200 (success). Locks the empty-dict happy path against an implementer footgun where `if sandbox:` (truthy check) would skip the dict-shape validator branch but `if "writable_paths" in sandbox:` would also skip; both behave correctly only with `if sandbox is not None:`.
  - All three tests pass: `pytest tests/test_db_api.py::TestMCPSourceAPI -v` shows count grew from the pre-leg baseline by exactly 3 (13 → 16); all pre-existing tests still pass.
- [ ] **No absolute-path-shape enforcement**: a POST with `{"command": "echo", "sandbox": {"writable_paths": ["data", "../etc"]}}` returns 201 (NOT 422) — relative paths and `..` traversal patterns survive the API layer per "trust the runtime"; the runtime's `bwrap --bind` will refuse them at spawn time. Verifiable by reading the diff (no path-shape isinstance/regex check added).
- [ ] **CLAUDE.md F3 section landed**: `CLAUDE.md` contains a new heading `## F3 (MCP Sandbox) Contracts (authoritative for F4-F8)` immediately after `## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)`. Section contains numbered contracts 1–7 enumerating module home / trust model / sandbox-profile storage / Protocol shape / failure boundary / privilege model / HOME override. Each forward-reference to a not-yet-existing symbol explicitly names L2/L3/L4 as the leg that lands the symbol. Verifiable by `grep -n '^## F3 (MCP Sandbox) Contracts' CLAUDE.md` returning exactly one line and the section being non-empty.
- [ ] **agents.md F3 bullets landed**: `the_one/agents.md` contains a `**F3 (MCP Sandbox) contracts** — for full text, see CLAUDE.md "F3 (MCP Sandbox) Contracts":` header followed by exactly 7 bullets covering module home / trust model / sandbox storage / Protocol shape / failure boundary / privilege model / HOME override, immediately after the existing F2 bullet block (currently ending "- **F2 dataclasses**: ..."). Verifiable by `grep -n 'F3 (MCP Sandbox) contracts' the_one/agents.md` returning one line.
- [ ] **`MCPSandbox` Protocol forward-reference is explicit**: every place L1b's docs name `MCPSandbox`, `SandboxProfile`, `SpawnSpec`, or `MCPSandboxError`, the prose includes wording on the order of "L2 lands the actual code; this entry documents the contract" — readable by an engineer who lands between L1b and L2 without confusion. Verifiable by reading the new doc sections.
- [ ] **Lint clean**: `ruff check the_one/ tests/` exits 0 with no NEW errors (the prior baseline had no errors per L1a flight log; full-clean is the target).
- [ ] **`pytest tests/test_db_api.py::TestMCPSourceAPI -v` green**: count grows by exactly 3 (13 → 16); all pre-existing tests still pass (no regression). Total wall-clock <2s.
- [ ] **No drift in unrelated contracts**: `grep -n "F2 (MCP Client Foundation) Contracts" CLAUDE.md` still returns one line at its original location; `grep -n "F2 (MCP Client Foundation) contracts" the_one/agents.md` likewise. The new F3 sections are ADDED, not replacing or restructuring F2.
- [ ] **No source-code changes outside `api.py` + the test file + the two doc files**: `git status --porcelain` shows only `the_one/interfaces/web/api.py`, `tests/test_db_api.py`, `CLAUDE.md`, `the_one/agents.md`, plus the flight artifacts (this leg file, flight-log.md, flight.md). No `the_one/platform/sandbox/` files, no `the_one/mcp/errors.py` change (those are L2's surface), no JS / CSS changes (L5b's surface).
- [ ] **Flight log updated**: `flight-log.md` gains `### L1b F1 Validator Extension and Docs` under `## Leg Progress` per the format used for L1a (Started / Completed / Status / Implementation summary / brief outputs). One paragraph sufficient.
- [ ] **Leg status flipped to `completed`** in this file's header; leg checkbox ticked in `flight.md` under `### Legs`.

## Verification Steps

Run from the repo root after applying the diff. Capture each command's exit code; any non-zero is a fail.

```bash
cd /home/cprch/projects/the-one

# --- 1. Diff scope check: only the four allowed source files plus flight artifacts ---
git status --porcelain
# Expect entries only for:
#   M the_one/interfaces/web/api.py
#   M tests/test_db_api.py
#   M CLAUDE.md
#   M the_one/agents.md
#   M missions/.../flight.md          (checkbox tick)
#   M missions/.../flight-log.md      (leg progress entry)
#   M missions/.../legs/01b-...md     (status flip)
# Anything else under the_one/ or tests/ is out-of-scope and rejects the leg.

# --- 2. Validator: stdio with sandbox writable_paths non-string entry → 422 ---
docker compose exec -T the-one python -m pytest \
    tests/test_db_api.py::TestMCPSourceAPI::test_validation_rejects_stdio_config_sandbox_writable_paths_non_string_entry -v
# Expect: 1 passed.

# --- 3. Validator: stdio with sandbox network_allowed non-bool → 422 ---
docker compose exec -T the-one python -m pytest \
    tests/test_db_api.py::TestMCPSourceAPI::test_validation_rejects_stdio_config_sandbox_network_allowed_non_bool -v
# Expect: 1 passed.

# --- 4. No regressions in TestMCPSourceAPI ---
docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI -v
# Expect: pre-leg-count + 3 passed (was 13, now 16). No failures, no errors.

# --- 5. Validator: absent sandbox key still works (existing test_crud sends no sandbox) ---
docker compose exec -T the-one python -m pytest tests/test_db_api.py::TestMCPSourceAPI::test_crud -v
# Expect: 1 passed.

# --- 6. Lint clean ---
docker compose exec -T the-one ruff check the_one/ tests/
# Expect: "All checks passed!" (exit 0).

# --- 7. Doc presence: F3 contracts section in CLAUDE.md and bullet block in agents.md ---
grep -n '^## F3 (MCP Sandbox) Contracts' CLAUDE.md
# Expect: exactly one match line.
grep -n 'F3 (MCP Sandbox) contracts' the_one/agents.md
# Expect: exactly one match line.

# --- 8. Forward-reference clarity: every named symbol has a "L2/L3/L4 lands" qualifier nearby ---
grep -A2 -E 'MCPSandbox|SandboxProfile|SpawnSpec|MCPSandboxError' CLAUDE.md | grep -E 'L2 lands|L3 lands|L4 lands|will be defined' | head -5
# Expect: at least one matching line per symbol cluster — visual confirmation that forward-refs
# are explicit, not bald symbol-name drops.

# --- 9. Existing F2 contracts unchanged ---
grep -n '^## F2 (MCP Client Foundation) Contracts' CLAUDE.md
# Expect: exactly one match at its original line. The new F3 section is ADDED, not
# restructuring F2. Confirm by `git diff -- CLAUDE.md` showing only ADDITIONS in the F2-adjacent
# region (no DELETIONS to the F2 paragraph itself).
```

If ANY assertion fails:
1. Do NOT signal `[COMPLETE:leg]`.
2. Capture the failing command + output in the flight log under `## Anomalies`.
3. Diagnose: most likely root causes are (a) the new validator branch is mis-indented and runs for streamable-http too (regression in `test_validation_rejects_streamable_http_missing_url`), (b) a doc heading was nested wrong (e.g., `### F3 ...` instead of `## F3 ...`) and the grep finds zero matches, (c) ruff flags an unused import added during the validator extension, (d) test naming collides with an existing test.

## Implementation Guidance

1. **Read `_validate_mcp_source_config` start-to-end** before editing. The function is structured as a two-arm if/elif on `source.type` with a defensive `else` branch that raises 422 for unknown transport literals. Adding the sandbox sub-block inside the stdio arm preserves that shape; do NOT add a parallel sandbox check outside the type-dispatch (that would double-validate for streamable-http or run for unknown literals). Anchor the addition immediately after the existing `env` check (the last sub-block in the stdio arm) and before the closing of the `if source.type == "stdio":` body.

2. **Validator block shape — follow the existing oauth-sub-block precedent** (the closest analogue: also an optional dict-of-fields-each-checked-when-present). Sketch:

   ```python
   sandbox = cfg.get("sandbox")
   # IMPORTANT: use `is not None` (NOT a truthy check). Empty dict `{}` must
   # pass through — the operator may post a sandbox sub-block with no fields,
   # and both writable_paths and network_allowed are individually optional.
   if sandbox is not None:
       if not isinstance(sandbox, dict):
           raise HTTPException(
               status_code=422,
               detail="MCP source config.sandbox must be a dict if present.",
           )
       if "writable_paths" in sandbox:
           writable_paths = sandbox["writable_paths"]
           if not isinstance(writable_paths, list) or not all(
               isinstance(p, str) for p in writable_paths
           ):
               raise HTTPException(
                   status_code=422,
                   detail="MCP source config.sandbox.writable_paths must be a list of strings.",
               )
       if "network_allowed" in sandbox:
           network_allowed = sandbox["network_allowed"]
           if not isinstance(network_allowed, bool):
               raise HTTPException(
                   status_code=422,
                   detail="MCP source config.sandbox.network_allowed must be a boolean.",
               )
   ```

   Notes:
   - `bool` is a subclass of `int` in Python — `isinstance(True, int)` returns True. The `network_allowed` check uses `isinstance(value, bool)` specifically (NOT `int`); a JSON `1` from a buggy client would be `int` not `bool` and fail. This matches the F1 validator's pattern of typing strictness.
   - **Do NOT enforce absolute-path shape on `writable_paths` entries** ("trust the runtime").
   - **Do NOT validate the namespace-flag fields** (`pid_unshare`, `ipc_unshare`, `uts_unshare`). Per §12 these are JSON-edit-only advanced knobs; the API passes them through, and L2's `SandboxProfile.from_dict` is responsible for type-mismatch rejection at construction time.

3. **Update the validator docstring** to reflect the new sub-block. Append one sentence: `config.sandbox is optional and may carry {writable_paths: list[str], network_allowed: bool}; both fields are optional within the sandbox sub-block. Path-shape and bool-shape are validated; absolute-path semantics are NOT enforced at the API layer — the runtime (BubblewrapSandbox.prepare_spawn, F3 L3) raises MCPSandboxError when bwrap rejects the path at spawn time.`

4. **Add 3 new tests in `tests/test_db_api.py::TestMCPSourceAPI`** immediately after `test_validation_rejects_stdio_config_env_non_dict`. Mirror the existing test pattern verbatim:

   ```python
   async def test_validation_rejects_stdio_config_sandbox_writable_paths_non_string_entry(
       self, client: AsyncClient
   ) -> None:
       """L1b: F1 API validator extended for config.sandbox sub-block per F3 §4."""
       resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "test-stdio-bad-sandbox-writable",
               "type": "stdio",
               "config": {"command": "echo", "sandbox": {"writable_paths": ["/data", 42]}},
               "secrets": {},
           },
       )
       assert resp.status_code == 422
       assert "config.sandbox.writable_paths" in resp.json()["detail"]

   async def test_validation_rejects_stdio_config_sandbox_network_allowed_non_bool(
       self, client: AsyncClient
   ) -> None:
       """L1b: F1 API validator extended for config.sandbox sub-block per F3 §4."""
       resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "test-stdio-bad-sandbox-network",
               "type": "stdio",
               "config": {"command": "echo", "sandbox": {"network_allowed": "yes"}},
               "secrets": {},
           },
       )
       assert resp.status_code == 422
       assert "config.sandbox.network_allowed" in resp.json()["detail"]

   async def test_validation_accepts_stdio_config_empty_sandbox_dict(
       self, client: AsyncClient
   ) -> None:
       """L1b: empty sandbox dict is valid — both writable_paths and network_allowed optional."""
       resp = await client.post(
           "/api/mcp-sources",
           json={
               "name": "test-stdio-empty-sandbox",
               "type": "stdio",
               "config": {"command": "echo", "sandbox": {}},
               "secrets": {},
           },
       )
       assert resp.status_code in (200, 201)
   ```

5. **Add the `## F3 (MCP Sandbox) Contracts` section to `CLAUDE.md`**. Insert immediately after the existing `## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)` block. The section is ADDED, not replacing F2.

   Style notes mirroring the F2 section:
   - Open with one-sentence framing then numbered contracts (CLAUDE.md F2 uses bolded inline mini-headers like `**1. Module layout** — ...`).
   - Each contract names the L2/L3/L4 leg that lands the symbol, in **bold** at the end of the contract text or as the closing sentence (e.g., `... **L2 lands the actual code; this entry documents the contract for readers landing between L1b and L2.**`).
   - Length budget: ~60–80 lines added under the new heading.

6. **Add the F3 bullet block to `the_one/agents.md`**. Insert after the line that currently reads `- **F2 dataclasses**: MCPTool and MCPToolResult ...` and before the next `### the_one/agent/` heading. Format mirrors the F2 bullet block one-for-one.

7. **Update flight log + flight + leg statuses last**, in this order:
   - Update `flight.md` to tick the L1b checkbox.
   - Append `### L1b F1 Validator Extension and Docs` to `flight-log.md` under `## Leg Progress` per the L1a format.
   - Flip this leg's status header to `completed`.

8. **Run the full Verification Steps** before signalling `[HANDOFF:review-needed]`. Capture each command's output for the flight log entry. Lint must be clean.

## Edge Cases

- **`bool` vs `int` in JSON**: a malicious client sending `{"network_allowed": 1}` (raw int, not Python `True`) would get a 422 because `isinstance(1, bool)` is `False`. This is the desired strict-typing behaviour and matches the F1 validator's pattern.
- **Namespace-flag fields pass through silently**: a POST with `{"command": "echo", "sandbox": {"pid_unshare": false}}` returns 201 — the API layer ignores unknown sandbox keys per `from_dict`'s "unknown keys ignored" policy. L2's `SandboxProfile.from_dict` is responsible for validating these advanced fields at runtime construction time.
- **Empty `writable_paths` list**: `config={"command": "echo", "sandbox": {"writable_paths": []}}` returns 201 — empty list is a valid (in fact default) `list[str]`.
- **String path that happens to be a relative path**: `config={"command": "echo", "sandbox": {"writable_paths": ["data/foo"]}}` returns 201 — the API does NOT enforce absolute-path shape per "trust the runtime." The runtime's `BubblewrapSandbox.prepare_spawn` (L3) will fail with `MCPSandboxError` when `bwrap --bind data/foo data/foo` rejects the path.
- **Streamable-http source with `config.sandbox` set**: returns 201 — the field is silently ignored at the API layer (the existing streamable-http validator doesn't check for it, and the new sandbox check is gated inside the stdio arm).
- **PUT type-switch from stdio → streamable-http with leftover `config.sandbox`**: the new validator branch is skipped on the streamable-http side, so a leftover `config.sandbox` from the previous stdio config does NOT trigger 422 on the type switch. This is correct behaviour per "silently accepted on streamable-http" — flagged here so a future reader doesn't misread it as a bug. The leftover sandbox sub-block is dead data on a streamable-http source (F4+ never reads it for remote transport).
- **PUT-only sandbox-rejection coverage gap (deliberate)**: this leg adds 3 POST-side tests but no PUT-specific sandbox-rejection test. The validator function is shared between POST and PUT (existing `test_put_transport_type_switch_revalidates_config` proves PUT runs the validator), so PUT-side rejection of a malformed `config.sandbox` is implicit. If a future routine-maintenance pass wants explicit PUT-side coverage, two more tests symmetric to the POST ones would suffice.
- **PUT-time validation**: `_validate_mcp_source_config` runs on both POST `create_mcp_source` AND PUT `update_mcp_source` (after `model_copy(update=data)`). The existing `test_put_transport_type_switch_revalidates_config` proves the validator runs on the merged post-copy state. So a PUT that adds a malformed `sandbox` block to an existing source ALSO gets 422 — without an additional test in L1b.
- **Fresh-install / migration**: existing rows in `mcp_sources` (post-F1, pre-F3) have no `config.sandbox` key. They continue to validate cleanly per the "absent sandbox is OK" path. No migration is needed; the field is purely additive within an existing JSON column.
- **Doc-prose forward-reference drift**: if L2 changes the canonical home of `MCPSandboxError`, the F3 contract's "Module home" entry needs to be updated. This happens via a follow-up commit during L2 (NOT a re-edit of L1b's leg artifact).

## Files Affected

- `the_one/interfaces/web/api.py` — extend `_validate_mcp_source_config` with a sandbox sub-block validator inside the stdio branch; extend its docstring.
- `tests/test_db_api.py` — add 2 new tests in `TestMCPSourceAPI` after `test_validation_rejects_stdio_config_env_non_dict`.
- `CLAUDE.md` — add a new section `## F3 (MCP Sandbox) Contracts (authoritative for F4-F8)` immediately after the existing F2 section.
- `the_one/agents.md` — add a `**F3 (MCP Sandbox) contracts** — for full text, see CLAUDE.md "F3 (MCP Sandbox) Contracts":` bullet block immediately after the existing F2 bullet block.
- `missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight-log.md` — append `### L1b F1 Validator Extension and Docs` under `## Leg Progress`.
- `missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/flight.md` — tick the L1b checkbox under `### Legs`.
- `missions/07-mcp-integration/flights/03-sandbox-adapter-and-bubblewrap/legs/01b-f1-validator-extension-and-docs.md` — flip `Status:` `planning` → `ready` (after design review) → `completed` (post-implementation).

**Explicitly NOT modified by this leg**: `the_one/platform/sandbox/` (does not exist yet — L2 creates), `the_one/mcp/errors.py` (`MCPSandboxError` is L2's surface), `the_one/mcp/transports/stdio.py` (`connect_stdio` integration is L4's surface), `tests/conftest.py` (`mcp_fixture_sandbox_profile` is L4's surface), `tests/fixtures/mcp/hello_server.py` (escape-attempt tools are L5a's surface), `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (UI sandbox section is L5b's surface), `Dockerfile`, `docker-compose.yml`, `Makefile`, `pyproject.toml`, `scripts/`, `.flightops/`. Any of those changes belong to a different leg.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `_validate_mcp_source_config` extended with sandbox sub-block (stdio arm only); docstring updated
- [ ] 3 new tests in `TestMCPSourceAPI` pass; pre-existing 13 tests still pass; total grew to 16
- [ ] `## F3 (MCP Sandbox) Contracts (authoritative for F4-F8)` section added to `CLAUDE.md`; F2 section unchanged
- [ ] F3 bullet block added to `the_one/agents.md` after F2 bullet block; F2 bullets unchanged
- [ ] Forward-references to `MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `MCPSandboxError` each carry an explicit "L2/L3/L4 lands" qualifier
- [ ] `ruff check the_one/ tests/` → exit 0, no errors (per-leg lint gate)
- [ ] `pytest tests/test_db_api.py::TestMCPSourceAPI -v` → all green; 16 passed
- [ ] `git status --porcelain` shows only the allowed paths (api.py, test_db_api.py, CLAUDE.md, agents.md, flight artifacts) — no out-of-scope edits
- [ ] Update flight-log.md with `### L1b F1 Validator Extension and Docs` under `## Leg Progress` (Started/Completed timestamps + 3-line implementation summary + green-test confirmation)
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md (under `### Legs`)
- [ ] **Do NOT commit** — agentic-workflow batches commits at flight end (per flight log "Flight Director Notes")
