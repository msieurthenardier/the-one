# Leg: 04-ci-and-runtime-teardown

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Tear out the agent-facing self-management surface from the deploy pipeline, container runtime, entrypoint script, app config, and selftest probe. Specifically: trim `ci/pipeline.yml` to a single `deploy` job (drop the `autopilot`, `pause-autopilot`, `unpause-autopilot`, `rollback`, and `restart` jobs and the `heartbeat` time resource); minimize `scripts/entrypoint.sh` to `set -e` + `exec "$@"`; drop the `/workspace` bind mount, `THE_ONE_WORKSPACE_DIR`, and the five `THE_ONE_CONCOURSE_*` env vars from `docker-compose.yml` and `ci/deploy.sh`; drop the `concourse-local_default` external Docker network attachment; drop the `concourse_target`, `concourse_pipeline`, and `workspace_dir` fields from `the_one/config.py::Settings`; rewrite the `/api/selftest` tool-use probe to read a path inside the running container (`/app/pyproject.toml`); and drop the `.deploy-status.json` read site from `/api/info` because nothing writes that file anymore. Update the one test that asserted on `workspace_dir` in the `/api/settings` payload.

## Context

L4 is the largest leg by surface area but coherent in intent: the CI pipeline and the runtime mount/env layout are all artifacts of the self-modification narrative the mission is parking. Every removal is a direct consequence of L1's tool deletions or the flight's Decision 3 (rip the `/workspace` mount).

The `deploy` and `test` jobs in `pipeline.yml` stay — they're the project's CI/CD path independent of the agent-facing self-management surface. Only the agent-facing jobs go.

**Codebase audit findings (2026-04-28, post-L1+L2+L3 uncommitted):**

- `ci/pipeline.yml` (286 lines, 6 jobs + 1 resource):
  - `resources:` (lines 1-5): `heartbeat` time resource. Used only by `autopilot`. Remove.
  - `autopilot` (lines 7-79). Triggered by heartbeat, calls the agent's `/api/chat` with a self-driving prompt that uses `mission_control` and `memory` (both removed in L1). Remove.
  - `deploy` (lines 80-197): `test` task → `build-and-deploy` task → `health-check` task with `on_failure: auto-rollback`. **Keep all of this** — it's the legitimate CI/CD path. The `auto-rollback` task at line 174-197 is deploy-internal recovery (re-runs deploy.sh with `rollback` arg), not the standalone `rollback` job — keep.
  - `rollback` (lines 199-224). Standalone job exposed as a tool to the agent (also triggerable manually). Remove — `RollbackTool` was deleted in L1.
  - `pause-autopilot` (lines 226-245). Remove.
  - `unpause-autopilot` (lines 247-266). Remove.
  - `restart` (lines 268-285). Remove — `RestartTool` was deleted in L1.
  - **Resulting `pipeline.yml`**: no `resources:` section, exactly one job (`deploy`) with three tasks (`test`, `build-and-deploy`, `health-check`) and the `auto-rollback` `on_failure` block.

- `docker-compose.yml` (38 lines):
  - Line 9: `- .:/workspace` volume — remove (Decision 3).
  - Line 16: `THE_ONE_WORKSPACE_DIR=/workspace` — remove.
  - Lines 18-23: `THE_ONE_CONCOURSE_TARGET`, `_PIPELINE`, `_URL`, `_USER`, `_PASS`, `_TEAM` (six env vars, but `_PASS` references `${THE_ONE_CONCOURSE_PASS}` from host env). Remove all six.
  - Line 24-25: `extra_hosts: - "host.docker.internal:host-gateway"` — **keep**. Used for the Ollama provider's `http://host.docker.internal:11434/v1` URL on line 14. Removing it would break local Ollama-backed runs. Mission Constraints don't require its removal.
  - Line 28: `- concourse` (network attachment) — remove.
  - Lines 32-34: `concourse: external: true ; name: concourse-local_default` — remove this network definition.
  - **Resulting `docker-compose.yml`**: only `default` network, only Ollama-related env vars + dev_mode, no Concourse env, no `/workspace` mount, `the_one_data` volume preserved.

- `scripts/entrypoint.sh` (33 lines): every line in the body is concourse/mission-control/fly setup that is moot after L1+L4. Mission Constraint says "agent has no path to read or carry through host secrets via subprocess inheritance" — but that's about Subprocess env, not entrypoint. The entrypoint shrinks to `#!/usr/bin/env bash\nset -e\nexec "$@"` (3 lines). Keep the file rather than deleting it (Dockerfile references it as `ENTRYPOINT`); deleting would require a Dockerfile edit too. Keep + minimize is the smaller change.

- `ci/deploy.sh` (31 lines): mirrors the docker-compose env layout. Remove the same six lines (`-v WORKSPACE_PATH:/workspace`, `-e THE_ONE_WORKSPACE_DIR`, the five `-e THE_ONE_CONCOURSE_*`), the `--network concourse-local_default` line, and keep `--add-host host.docker.internal:host-gateway` for Ollama. The `${WORKSPACE_PATH}` and `${CONCOURSE_PASS}` parameters become unused — drop the `CONCOURSE_PASS` parameter requirement. `${WORKSPACE_PATH}` may still be needed if the rollback re-tag path needs context (it doesn't — `docker tag the-one:rollback the-one:latest` is image-name-only). Drop `WORKSPACE_PATH` parameter too. Resulting deploy.sh: `set -eu`, `TAG="${1:?...}"`, optional rollback re-tag, `docker rm -f`, `docker run -d` with simplified env list.

- `pipeline.yml` `build-and-deploy` task params: drop `WORKSPACE_PATH: ((workspace-path))` — only the `test` task uses `WORKSPACE_PATH` to mount source-into-Playwright-image, which is legitimate (CI checkout source). The deploy task itself doesn't need workspace path because the **deploy.sh** invocation no longer mounts source. Wait — the deploy task at lines 124-128 mounts `${WORKSPACE_PATH}` to do `docker build` from the host source. That's legitimate (build needs source). Keep `WORKSPACE_PATH` for the build-and-deploy task. The `auto-rollback` task at 184-197 mounts `${WORKSPACE_PATH}:/src:ro` to access `deploy.sh` — also legitimate (the script lives in source). Keep `WORKSPACE_PATH`. Drop `CONCOURSE_PASS` from both `build-and-deploy` and `auto-rollback` tasks since deploy.sh no longer needs it.

- `the_one/config.py` (39 lines): drop lines 20 (`workspace_dir`), 22-24 (the `# Concourse CI` section header + `concourse_target` + `concourse_pipeline`). Resulting Settings: 5 fields (`host`, `port`, `dev_mode`, `data_dir`) plus the two computed properties.

- `the_one/interfaces/web/app.py:525` — `status_file = settings.workspace_dir / ".deploy-status.json"`. After dropping `workspace_dir`, this line raises `AttributeError`. Audit traced the writer: only `tools/self_deploy.py` ever wrote `.deploy-status.json` (deleted in L1); `ci/deploy.sh` does NOT write it. The file is gitignored but no longer produced. Drop the entire `status_file` block (lines 525-530); `/api/info` returns just `{"version": "0.1.0"}`.

- `the_one/interfaces/web/app.py:561` — `/api/selftest` tool-use probe currently invokes `agent.step("Read the file /workspace/pyproject.toml")`. After dropping the workspace mount, this path doesn't exist. Per flight Technical Approach, change to `/app/pyproject.toml` (the Dockerfile copies `pyproject.toml` to `/app/pyproject.toml` at line 12 of the Dockerfile). Verified `/app/pyproject.toml` exists in the running container (Dockerfile `WORKDIR /app` + `COPY pyproject.toml .`).

- `tests/test_db_api.py::test_path_values_are_strings` (lines 52-58) asserts `data["workspace_dir"]` exists in the `/api/settings` response. After dropping `workspace_dir` from `Settings`, the field disappears from the payload, the test KeyErrors (`data["workspace_dir"]` lookup). Update the assertion to drop the `workspace_dir` lines, asserting only on `data["data_dir"]`. Test in default suite — must fix in L4 to preserve green-build invariant.

- `tests/test_db_api.py::test_get_settings` iterates `Settings.model_fields`, verifying each field is present in the response. This test is field-list agnostic — passes regardless of which fields exist. No change.

- `tests/test_aiat.py::test_tool_use_file_read` (line 126) and `test_aiat_list_dir` (line 193) reference `/workspace/pyproject.toml` and `/workspace/the_one/tools/`. **Per flight Technical Approach**, these AIAT updates land in L6, not L4 — AIAT tests are `pytest -m live` off the default suite, so they don't break the build between legs. L4 leaves them alone; L6 sweeps them.

- `Dockerfile` installs `git`, `ca-certificates`, `curl` (apt). Per flight Technical Approach: "git apt package may still be wanted as a general-purpose binary available in the container... Keep for now." `curl` is used by the `HEALTHCHECK`. `ca-certificates` is needed for HTTPS web tools. **Keep all three.** No Dockerfile edits.

- `the_one/agents.md:42` mentions `workspace_dir` in the description of the Settings module: "*Key properties: `data_dir` (~/.the-one), `workspace_dir` (/workspace), `agents_dir` (data_dir / "agents"), `db_path` (data_dir / "the-one.db").*" Out of L4 scope (`*.md` narrative file — L5's job).

**Cross-cutting concerns:**

- The `concourse-local_default` external Docker network is owned by the `concourse-local` sibling project. Removing the attachment from the-one's compose file does NOT affect the concourse-local stack (per flight Adaptation Criteria *"Confirmed safe (no divert needed)"*).
- Concourse pipeline uses Concourse vars (`((var-name))`) at deploy time — those ARE referenced from a separate Concourse-secrets store, not from in-repo files. Removing the Concourse env vars from docker-compose / deploy.sh has no effect on the pipeline's ability to authenticate to Concourse for triggering the `deploy` job. The pipeline still works the same; the running container just no longer carries those secrets.
- The deploy task's `health-check` (pipeline.yml line 139-170) calls `${APP_URL}/api/selftest`. After L4's selftest path fix, the probe uses `/app/pyproject.toml` (a path that exists in the production container). The pipeline's auto-rollback should NO LONGER fire on every deploy.

## Inputs

- L1 + L2 + L3 landed (uncommitted): 7 tools and `behaviors.py` gone, `BASE_PROMPT` constant established with additive composition, schema at v7.
- `ci/pipeline.yml` at 286 lines, 5 to-be-removed jobs and 1 to-be-removed resource.
- `docker-compose.yml` at 38 lines with `/workspace` mount, six Concourse env vars, `concourse` network.
- `scripts/entrypoint.sh` at 33 lines with mission-control clone, fly install, fly login, two `safe.directory` lines.
- `ci/deploy.sh` at 31 lines mirroring docker-compose's env layout.
- `the_one/config.py::Settings` with `workspace_dir`, `concourse_target`, `concourse_pipeline` fields.
- `app.py:525-530` reads `.deploy-status.json` (dead read site — no writer left).
- `app.py:561` probes `/workspace/pyproject.toml` in `/api/selftest`.
- `tests/test_db_api.py::test_path_values_are_strings` asserts `data["workspace_dir"]`.
- Default unit test suite baseline: 395 passed + 1 pre-existing red.

## Outputs

After this leg:
- `ci/pipeline.yml` has exactly one job (`deploy`), no `resources:` section, ~120 lines.
- `docker-compose.yml` has no `/workspace` mount, no Concourse env vars, no `concourse` network, ~25 lines.
- `scripts/entrypoint.sh` has 3 lines: shebang, `set -e`, `exec "$@"`.
- `ci/deploy.sh` has no Concourse env, no `/workspace` mount, no `--network concourse-local_default`, ~22 lines.
- `the_one/config.py::Settings` has fields: `host`, `port`, `dev_mode`, `data_dir`. No `workspace_dir`, `concourse_target`, `concourse_pipeline`.
- `the_one/interfaces/web/app.py::info()` returns just `{"version": "0.1.0"}` (no `.deploy-status.json` block).
- `the_one/interfaces/web/app.py::selftest()` tool-use probe targets `/app/pyproject.toml`.
- `tests/test_db_api.py::test_path_values_are_strings` no longer asserts on `workspace_dir`.
- Default unit test suite green (395 passed, 1 pre-existing red).
- No commit — deferred to post-L6.

## Acceptance Criteria

- [ ] `ci/pipeline.yml` contains exactly one job named `deploy`. `rg -n "^  - name:" ci/pipeline.yml` returns one match.
- [ ] `ci/pipeline.yml` does NOT contain `autopilot`, `pause-autopilot`, `unpause-autopilot`, the standalone `rollback` job, the `restart` job, or the `heartbeat` resource. `rg -n "name: (autopilot|pause-autopilot|unpause-autopilot|heartbeat)|^  - name: rollback$|^  - name: restart$" ci/pipeline.yml` returns no output.
- [ ] `ci/pipeline.yml` retains the `deploy` job's three tasks (`test`, `build-and-deploy`, `health-check`) and the `on_failure: do: - task: auto-rollback` block.
- [ ] `docker-compose.yml` does not contain `/workspace`, `THE_ONE_WORKSPACE_DIR`, `THE_ONE_CONCOURSE_TARGET`, `THE_ONE_CONCOURSE_PIPELINE`, `THE_ONE_CONCOURSE_URL`, `THE_ONE_CONCOURSE_USER`, `THE_ONE_CONCOURSE_PASS`, `THE_ONE_CONCOURSE_TEAM`, or the `concourse` external network. `rg -n "/workspace|THE_ONE_CONCOURSE|THE_ONE_WORKSPACE_DIR|concourse-local_default" docker-compose.yml` returns no output.
- [ ] `docker-compose.yml` retains the `host.docker.internal:host-gateway` extra_hosts entry, the `the_one_data` volume, the port mapping `8484:8484`, the Ollama env vars (`THE_ONE_LLM_PROVIDER`, `_MODEL`, `_BASE_URL`), `THE_ONE_HOST=0.0.0.0`, and `THE_ONE_DEV_MODE=true`.
- [ ] `scripts/entrypoint.sh` is at most 5 lines, containing only the shebang, optionally a one-line comment, `set -e`, and `exec "$@"`. No `fly`, `mission-control`, `safe.directory`, `THE_ONE_CONCOURSE_*`, or `clone` references remain.
- [ ] `ci/deploy.sh` does not contain `/workspace`, `THE_ONE_WORKSPACE_DIR`, `THE_ONE_CONCOURSE_*`, or `--network concourse-local_default`. `rg -n "/workspace|THE_ONE_CONCOURSE|--network concourse-local_default" ci/deploy.sh` returns no output.
- [ ] `ci/deploy.sh` retains `--add-host host.docker.internal:host-gateway`.
- [ ] `the_one/config.py::Settings` has exactly four public fields (`host`, `port`, `dev_mode`, `data_dir`) plus the two `@property` accessors `agents_dir` and `db_path`. No `workspace_dir`, `concourse_target`, `concourse_pipeline`. Verified via `python -c "from the_one.config import Settings; assert set(Settings.model_fields) == {'host', 'port', 'dev_mode', 'data_dir'}, Settings.model_fields"`.
- [ ] `the_one/interfaces/web/app.py::info()` does not reference `settings.workspace_dir` or `.deploy-status.json`. The body returns `{"version": "0.1.0"}` unconditionally.
- [ ] `the_one/interfaces/web/app.py::selftest()` tool-use probe (around line 561) prompts the agent to read `/app/pyproject.toml` (or equivalent baked-in path), not `/workspace/pyproject.toml`.
- [ ] `tests/test_db_api.py::test_path_values_are_strings` asserts on `data["data_dir"]` only (no `workspace_dir` reference).
- [ ] `python -m pytest tests/ --tb=short -q --ignore=tests/browser` exits 0 (modulo the pre-existing CSS-token anomaly).
- [ ] `rg -n "workspace_dir|concourse_target|concourse_pipeline" the_one/ tests/ --glob '!*.md'` returns no matches. (`agents.md:42` is L5's job.)
- [ ] `rg -n "/workspace" the_one/ tests/ --glob '!*.md' --glob '!test_aiat.py'` returns no matches in production code or default-suite tests. The two `tests/test_aiat.py` references at lines 126 and 193 are explicitly out of scope (L6).
- [ ] Working tree on branch `flight/01-tool-reduction-self-modification-teardown`; **no commit made**.
- [ ] Flight log updated with leg progress entry under `## Leg Progress`, status `landed`. Add a Deviation entry naming the four out-of-flight-spec edits required for green-build / coherence: (a) `tests/test_db_api.py::test_path_values_are_strings` update, (b) `/api/info` `.deploy-status.json` block removal, (c) `ci/deploy.sh` parallel cleanup of env vars / network / mount, (d) `pipeline.yml` `CONCOURSE_PASS` parameter drop from `build-and-deploy` and `auto-rollback` tasks. Plus the Makefile comment touch-up (in-scope, not a deviation).
- [ ] Leg status set to `landed` in this file's header.

## Verification Steps

```bash
# 1. Pipeline trim
rg -n "^  - name:" ci/pipeline.yml
# Expected: one match — "  - name: deploy"

rg -n "name: (autopilot|pause-autopilot|unpause-autopilot|heartbeat)|^  - name: rollback$|^  - name: restart$" ci/pipeline.yml
# Expected: no output

# 2. docker-compose cleanup
rg -n "/workspace|THE_ONE_CONCOURSE|THE_ONE_WORKSPACE_DIR|concourse-local_default" docker-compose.yml
# Expected: no output

rg -n "host.docker.internal:host-gateway|the_one_data|THE_ONE_LLM_PROVIDER" docker-compose.yml
# Expected: matches confirming preserved entries

# 3. entrypoint.sh minimized
wc -l scripts/entrypoint.sh
# Expected: <= 5 lines (shebang + set -e + exec + maybe a comment)

rg -n "fly|mission-control|safe.directory" scripts/entrypoint.sh
# Expected: no output

# 4. deploy.sh cleanup
rg -n "/workspace|THE_ONE_CONCOURSE|--network concourse-local_default" ci/deploy.sh
# Expected: no output

rg -n "host.docker.internal:host-gateway" ci/deploy.sh
# Expected: one match

# 5. Settings model
python -c "from the_one.config import Settings; assert set(Settings.model_fields) == {'host', 'port', 'dev_mode', 'data_dir'}, Settings.model_fields; print('OK', Settings.model_fields.keys())"
# Expected: 'OK dict_keys([host, port, dev_mode, data_dir])'

# 6. /api/info no longer reads deploy-status
rg -n "deploy-status|workspace_dir" the_one/interfaces/web/app.py
# Expected: no output

# 7. /api/selftest probe path
rg -n '/app/pyproject.toml' the_one/interfaces/web/app.py
# Expected: one match

rg -n '/workspace/pyproject.toml' the_one/interfaces/web/app.py
# Expected: no output

# 8. test_db_api updated
rg -n 'workspace_dir' tests/test_db_api.py
# Expected: no output

# 9. Test suite green
python -m pytest tests/ --tb=short -q --ignore=tests/browser
# Expected: 395 passed, 1 pre-existing CSS-token failure

# 10. Wider grep — no stale workspace_dir / concourse references in default-suite scope
rg -n "workspace_dir|concourse_target|concourse_pipeline" the_one/ tests/ --glob '!*.md'
# Expected: no output

rg -n "/workspace" the_one/ tests/ --glob '!*.md' --glob '!test_aiat.py'
# Expected: no output (test_aiat.py refs are L6's; *.md is L5's)
```

## Implementation Guidance

Work from project root `~/projects/the-one`. Branch must be `flight/01-tool-reduction-self-modification-teardown`. Leg status `ready` → `in-flight` at start; `landed` at end. **No commit.**

1. **Trim `ci/pipeline.yml`**:
   - Delete lines 1-5 (the `resources:` section).
   - Delete lines 7-79 (the `autopilot` job).
   - Keep lines 80-197 (the `deploy` job and its `on_failure: auto-rollback` block).
   - Delete lines 199-285 (the `rollback`, `pause-autopilot`, `unpause-autopilot`, `restart` jobs).
   - The remaining file should start with `jobs:` (no `resources:`), have one `- name: deploy` block, and end after the `auto-rollback` task.
   - Inside the `build-and-deploy` task params, drop `CONCOURSE_PASS: ((concourse-pass))`. Same for the `auto-rollback` task.
   - Inside the `build-and-deploy` task's `docker run` invocation that calls deploy.sh, drop `-e CONCOURSE_PASS="${CONCOURSE_PASS}"`. Same for `auto-rollback`.
   - `WORKSPACE_PATH` stays — the build-and-deploy task uses it to mount source for `docker build`, and auto-rollback uses it to access `deploy.sh` from the source tree.

2. **Update `docker-compose.yml`**:
   - Delete line 9 (`- .:/workspace`).
   - Delete line 16 (`THE_ONE_WORKSPACE_DIR=/workspace`).
   - Delete lines 18-23 (the six `THE_ONE_CONCOURSE_*` env vars).
   - Delete line 28 (`- concourse` from networks list).
   - Delete lines 32-34 (`concourse: external: true ; name: concourse-local_default`).
   - Keep lines 24-25 (`extra_hosts: - "host.docker.internal:host-gateway"`).
   - Result should look like:
     ```yaml
     services:
       the-one:
         build: .
         container_name: the-one
         restart: unless-stopped
         ports:
           - "8484:8484"
         volumes:
           - the_one_data:/root/.the-one
         environment:
           - THE_ONE_LLM_PROVIDER=ollama
           - THE_ONE_LLM_MODEL=qwen2.5:7b
           - THE_ONE_LLM_BASE_URL=http://host.docker.internal:11434/v1
           - THE_ONE_HOST=0.0.0.0
           - THE_ONE_DEV_MODE=true
         extra_hosts:
           - "host.docker.internal:host-gateway"
         networks:
           - default

     networks:
       default:

     volumes:
       the_one_data:
     ```

3. **Replace `scripts/entrypoint.sh`** with the minimal version:
   ```bash
   #!/usr/bin/env bash
   set -e
   exec "$@"
   ```
   Optionally keep a one-line comment header (`# Container startup`); keep the file to avoid editing the Dockerfile's `ENTRYPOINT` directive.

4. **Update `ci/deploy.sh`** — drop the `/workspace` mount, the seven Concourse env vars, the `concourse-local_default` network attachment. Keep the `host.docker.internal:host-gateway` add-host. Result:
   ```bash
   #!/usr/bin/env sh
   set -eu

   TAG="${1:?Usage: deploy.sh <image-tag>}"

   # For rollback: re-tag the rollback image as latest
   if [ "$TAG" = "rollback" ]; then
     docker tag the-one:rollback the-one:latest || { echo "No rollback image found"; exit 1; }
   fi

   docker rm -f the-one 2>/dev/null || true
   docker run -d \
     --name the-one \
     --restart unless-stopped \
     -p 8484:8484 \
     -e THE_ONE_LLM_PROVIDER=ollama \
     -e THE_ONE_LLM_MODEL=qwen2.5:7b \
     -e THE_ONE_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
     -e THE_ONE_HOST=0.0.0.0 \
     --add-host host.docker.internal:host-gateway \
     the-one:latest
   ```
   Note: `THE_ONE_DEV_MODE` is NOT set here (production deploys are non-dev). `WORKSPACE_PATH` and `CONCOURSE_PASS` are no longer required parameters — drop their references in pipeline.yml's deploy task too (per step 1).

5. **Update `the_one/config.py`** — drop three lines from `Settings`:
   - Line 20: `workspace_dir: Path = Path("/workspace")`
   - Line 22 (the `# Concourse CI` section comment header — drop it since the section is empty)
   - Line 23: `concourse_target: str = "local"`
   - Line 24: `concourse_pipeline: str = "the-one"`

   Resulting `the_one/config.py::Settings`:
   ```python
   class Settings(BaseSettings):
       model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

       # Web
       host: str = "127.0.0.1"
       port: int = 8484

       # Dev mode (gates the mock provider type)
       dev_mode: bool = False

       # Paths
       data_dir: Path = Path.home() / ".the-one"

       @property
       def agents_dir(self) -> Path:
           return self.data_dir / "agents"

       @property
       def db_path(self) -> Path:
           return self.data_dir / "the-one.db"

       def ensure_dirs(self) -> None:
           self.data_dir.mkdir(parents=True, exist_ok=True)
   ```

6. **Update `the_one/interfaces/web/app.py::info()`** at line 517-532. Drop the `.deploy-status.json` block entirely. Resulting handler:
   ```python
   @app.get("/api/info")
   async def info() -> dict[str, Any]:
       return {"version": "0.1.0"}
   ```
   Also drop the `import json as _json` line since it was only used inside the deleted block (verify by grep).

7. **Update `the_one/interfaces/web/app.py::selftest()`** at line 561. Change:
   ```python
   async for msg in agent.step("Read the file /workspace/pyproject.toml"):
   ```
   to:
   ```python
   async for msg in agent.step("Read the file /app/pyproject.toml"):
   ```
   The path `/app/pyproject.toml` exists in the running container (Dockerfile line 12: `COPY pyproject.toml .` with `WORKDIR /app`).

8. **Update `tests/test_db_api.py::test_path_values_are_strings`** (lines 52-58). Drop the two `workspace_dir` lines:
   ```python
   async def test_path_values_are_strings(self, client: AsyncClient) -> None:
       resp = await client.get("/api/settings")
       data = resp.json()
       assert isinstance(data["data_dir"], str)
       assert "PosixPath" not in data["data_dir"]
   ```

9. **Run the unit suite**:
   ```bash
   python -m pytest tests/ --tb=short -q --ignore=tests/browser
   ```
   Expected: 395 passed, 1 pre-existing CSS-token failure.

10. **Run the targeted verification commands** from the Verification Steps section.

11. **Update the flight log**:
    - Append a `### 04-ci-and-runtime-teardown` entry under `## Leg Progress` with status `landed`, summary of changes (pipeline trim, compose cleanup, entrypoint minimization, deploy.sh cleanup, Settings shrink, /api/info simplification, /api/selftest probe-path fix, test_db_api fixture update).
    - Append a Deviation entry under `## Deviations` listing the out-of-flight-spec edits required for green-build:
      - `the_one/interfaces/web/app.py::info()`: dropped the `.deploy-status.json` block (no writer remained — `self_deploy.py` was deleted in L1, and `ci/deploy.sh` doesn't write the file). Required because dropping `workspace_dir` from `Settings` would otherwise leave an `AttributeError` at runtime.
      - `tests/test_db_api.py::test_path_values_are_strings`: dropped the two `workspace_dir` assertions. Required because `/api/settings` no longer carries that field.
      - `ci/deploy.sh`: parallel cleanup of the same env vars / mounts removed from `docker-compose.yml`, plus drop of `WORKSPACE_PATH` and `CONCOURSE_PASS` parameters. Flight Technical Approach explicitly mentioned trimming docker-compose but didn't mention the parallel deploy.sh cleanup; logical consequence and required for the deploy pipeline to keep working.
      - `pipeline.yml` build-and-deploy + auto-rollback tasks: dropped `CONCOURSE_PASS` parameter and env-var passthrough since deploy.sh no longer uses it.

12. **Update `Makefile` comment**: line 6-7 currently says *"(The `/workspace` bind-mount is used by tests which spawn their own uvicorn subprocess; it does NOT feed the served app.)"*. After L4 drops the bind-mount, this parenthetical is stale. Replace the whole parenthetical with: `(Tests spawn their own uvicorn subprocess via the conftest fixtures; that path is independent of the container.)` — preserves the spirit (tests don't go through the container) without referencing the removed mount. Single-paragraph edit; no Makefile-target changes.

13. **Set leg status to `landed`** in this file's header. Do **NOT** commit. Do **NOT** check off the leg in `flight.md`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`/api/info` consumers**: browser tests (`tests/browser/conftest.py`, `tests/browser/test_markdown.py`, `tests/browser/test_app_fixture.py`) and AIAT (`tests/test_aiat.py`) all hit `/api/info` for startup-poll / health-check. None of them assert on the `deploy` field. After L4, the response shrinks to `{"version": "0.1.0"}` — still 200, still parseable as JSON. No consumer impact.
- **Deploy pipeline first-run with new selftest path**: the deploy task's health-check job calls `/api/selftest` against the freshly-deployed container. After L4, the probe path is `/app/pyproject.toml`. Verified the file exists in the container via Dockerfile inspection (line 12: `COPY pyproject.toml .` with `WORKDIR /app`). The `read_file` tool's path scope (current behavior at L4 timeline — F2 hasn't run yet) is permissive; `/app/pyproject.toml` is readable. No path-scope rejection expected.
- **Existing `~/.the-one/the-one.db` files** with `workspace_dir` set in `.env`: pydantic-settings ignores unknown env vars per `model_config = {..., "extra": "ignore"}`. Dropping the `Settings` field doesn't break startup against an existing `.env`.
- **`ENTRYPOINT ["/entrypoint.sh"]`** in Dockerfile (line 24) — keeps working; the minimized script still does `exec "$@"` which honors the `CMD ["the-one", "serve"]`.
- **The `test` task in `pipeline.yml`** uses `WORKSPACE_PATH` to mount source into the Playwright image. Independent of L4's runtime cleanup. Keep `WORKSPACE_PATH` parameter on the `test` task.
- **Concourse pipeline must be re-pushed** (`fly set-pipeline -p the-one -c ci/pipeline.yml`) for the trim to take effect against the live Concourse instance. L4 does NOT push the pipeline — that's a deployment step, out of leg scope. Operator concern; flight debrief / HAT can flag it.
- **`tests/browser/seeders.py:71`** comment was already updated in L1. No repeat work in L4.
- **Test count drift**: L3 added one test (395 = 394 + new v7 test). L4 doesn't add or remove any tests; the count stays at 395 + 1 pre-existing red.
- **`admin/system-page.js` cosmetic regression in the L4 → L5 window**: `the_one/interfaces/web/static/js/areas/admin/system-page.js:11-22` hardcodes `data_dir`, `workspace_dir`, `host`, `port`, `concourse_target`, `concourse_pipeline` as fields to render. After L4 drops three of those from `Settings`, the `/api/settings` payload omits them; the JS continues to render their labels with empty values, including the entire "Concourse CI" subsection header. Browser tests don't assert on this text (verified — no matches for `concourse` or `workspace_dir` in `tests/browser/`), so the build stays green. The Studio admin Environment view will show empty rows / a stale Concourse subsection until L5's UI cleanup. **Acceptable interim incoherence** — same coherence pattern as the L1+L2 inter-leg note. HAT (L7) covers the post-L5 cleanup.
- **`/api/selftest` path-fix correctness against a live Ollama-backed agent**: not verifiable in L4's unit suite. The unit tests don't spin up a real container with `/app/pyproject.toml` and a real LLM. Verification happens at L7 (HAT pass) and at the next deploy-pipeline run, where `health-check`'s call to `${APP_URL}/api/selftest` either succeeds (deploy lands) or auto-rollback fires (per flight Adaptation Criteria — explicit divert trigger).
- **`ci/deploy.sh` does NOT carry `THE_ONE_DEV_MODE`** (intentional asymmetry vs `docker-compose.yml`). Compose serves the local-dev workflow where `THE_ONE_DEV_MODE=true` enables the mock LLM provider; `ci/deploy.sh` is the production deploy path where dev mode should be off. The asymmetry is correct and matches the existing pre-L4 `deploy.sh` shape.

## Files Affected

- `ci/pipeline.yml` — drop `resources:` + four jobs (autopilot, rollback, pause-autopilot, unpause-autopilot, restart); drop `CONCOURSE_PASS` parameter from build-and-deploy and auto-rollback tasks
- `docker-compose.yml` — drop `/workspace` mount, six Concourse env vars, `concourse` network attachment, network definition
- `scripts/entrypoint.sh` — minimize to 3 lines
- `ci/deploy.sh` — drop `/workspace` mount, seven Concourse env vars, `--network concourse-local_default`, drop `WORKSPACE_PATH` and `CONCOURSE_PASS` parameters
- `the_one/config.py` — drop `workspace_dir`, `concourse_target`, `concourse_pipeline` fields and the `# Concourse CI` section header
- `the_one/interfaces/web/app.py` — simplify `/api/info` to return `{"version": "0.1.0"}`; change `/api/selftest` tool-use probe path
- `tests/test_db_api.py` — drop two `workspace_dir` assertions in `test_path_values_are_strings`
- `Makefile` — update the lines 6-7 parenthetical to drop the `/workspace` bind-mount reference (no target changes)
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — append leg progress + deviation

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (NOTE: per the agentic-workflow skill, this leg does NOT commit; the post-L6 review handles commit. Mark leg `landed`, not `completed`.):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/ --ignore=tests/browser` green except for the pre-existing CSS anomaly)
- [ ] Update flight-log.md with leg progress entry (status `landed`)
- [ ] Update flight-log.md `## Deviations` section with the out-of-flight-spec edits
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do **NOT** check off this leg in flight.md yet (deferred to post-L6 commit)
- [ ] Do **NOT** commit (deferred to post-L6 batch commit)
- [ ] Signal `[HANDOFF:review-needed]`
