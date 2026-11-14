# Leg: 03-ci-image-pinning-and-dockerignore

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Pin all four Concourse pipeline image references to specific tags or digests, pin Playwright in `pyproject.toml` to match the CI image version, and add a `.dockerignore` excluding `.env`, `.git/`, `workspace/`, `.memory/`, `.pytest_cache/`, and other non-build paths.

## Context

Maintenance report findings 8.1, 8.4, 8.10 (see `maintenance/2026-05-04.md`).

- **8.1**: `ci/pipeline.yml` uses floating image tags at lines 10, 32, 63, 99: `docker:cli`, `curlimages/curl:latest`, `mcr.microsoft.com/playwright/python:v1.58.0-jammy`. The Playwright image is technically pinned by tag but mutable. The other three are genuinely floating. Builds are not reproducible; an upstream push can change behavior or introduce a supply-chain incident silently.
- **8.4**: No `.dockerignore` exists at repo root. Currently safe (only explicit `COPY the_one/`, `COPY pyproject.toml`, `COPY tests/`) but any future drift to `COPY . .` would silently include `.env`, `.git/`, `workspace/`, `.memory/`, `.pytest_cache/`, `missions/`, `docs/`. Build context is also larger than necessary.
- **8.10**: Playwright pinned to `v1.58.0-jammy` in CI image but `pyproject.toml` says `playwright>=1.48`. Versions can drift.

## Inputs

- `ci/pipeline.yml` (existing; 4 image references at lines 10, 32, 63, 99 per CI/CD reviewer)
- `Dockerfile` (existing; `FROM python:3.11-slim`)
- `pyproject.toml` (existing; `playwright>=1.48`)
- No `.dockerignore` exists

## Outputs

- All 4 pipeline image references pinned (digest `@sha256:...` OR specific semver tag)
- `pyproject.toml` Playwright pinned to `==1.58.0` (or whichever version matches the CI image)
- `.dockerignore` exists at repo root with appropriate excludes

## Acceptance Criteria

- [x] `ci/pipeline.yml` lines 10, 32, 99 — `image_resource:` blocks with `repository: docker, tag: cli` replaced with a pinned reference (e.g., `tag: 25.0.3-cli` or digest); SAME pin used at all three sites
- [x] `ci/pipeline.yml` lines 48, 55, 111 — INLINE `docker:cli` invocations inside `docker run` shell args replaced with the SAME pin (e.g., `docker:25.0.3-cli`)
- [x] `ci/pipeline.yml` line 63 — `image_resource:` block `repository: curlimages/curl, tag: latest` replaced with a pinned reference (e.g., `tag: 8.6.0` or digest)
- [x] `ci/pipeline.yml` line 23 — INLINE `mcr.microsoft.com/playwright/python:v1.58.0-jammy` retained (already tag-pinned); digest upgrade OPTIONAL
- [x] `grep -nE "docker:cli|tag: cli|tag: latest" ci/pipeline.yml` returns 0 hits after the leg (confirms all floating references replaced)
- [x] `pyproject.toml` `playwright` dependency pinned to `==1.58.0` (matching the CI image; `uv.lock` already at 1.58.0 so resolution is safe)
- [x] `.dockerignore` exists at repo root excluding at minimum: `.env*`, `.git/`, `workspace/`, `__pycache__/`, `*.egg-info/`, `missions/`, `docs/`, `.memory/`, `.pytest_cache/`, `.venv/`, `.benchmarks/`, `.ruff_cache/`, `the_one.egg-info/`
- [x] `docker compose build` (or `make rebuild`) succeeds with the new `.dockerignore` (no missing files)
- [x] `pip install -e ".[all-llms,dev]"` resolves with the pinned Playwright version
- [x] Browser tests `pytest -m browser tests/browser/` pass with the pinned Playwright (regression check)

## Verification Steps

- `cd ~/projects/the-one && grep -nE "image:|tag:|^\s+- name:|repository:" ci/pipeline.yml | grep -v "name: source"` — every image reference shows a non-`latest`, non-bare tag (or digest)
- `cd ~/projects/the-one && grep "playwright" pyproject.toml` — shows `==1.58.0` pin
- `cd ~/projects/the-one && cat .dockerignore` — file exists with the listed excludes
- `cd ~/projects/the-one && make rebuild 2>&1 | tail -20` — succeeds; image builds cleanly
- `cd ~/projects/the-one && pytest -m browser tests/browser/ -q 2>&1 | tail -10` — all green

## Implementation Guidance

1. **Pin pipeline image references** — semver-tag pin is the default for this leg; digest pin is OPTIONAL upgrade.
   - **Three `image_resource: docker:cli` blocks** at lines 10, 32, 99: change `tag: cli` → `tag: 25.0.3-cli` (or whatever stable semver tag is currently published — verify on hub.docker.com/_/docker before locking). All three sites use the SAME pin.
   - **Three INLINE `docker:cli` invocations** inside `docker run` shell args at lines 48, 55, 111: change `docker:cli` → `docker:25.0.3-cli` (same pin as above). Easy to miss because they're inside YAML string args, not `image_resource:` blocks.
   - **`image_resource: curlimages/curl:latest`** at line 63: change `tag: latest` → `tag: 8.6.0` (verify on hub.docker.com/_/curlimages-curl).
   - **Inline `mcr.microsoft.com/playwright/python:v1.58.0-jammy`** at line 23: already tag-pinned; leave alone (digest upgrade optional).
   - Concourse `registry-image` resource accepts a separate `digest:` field alongside `tag:` if the implementer chooses digest-pinning. Either is acceptable; tag-pin is the default for this leg.
   - **Verification grep** must return 0 hits after the change: `grep -nE "docker:cli|tag: cli|tag: latest" ci/pipeline.yml`

2. **Pin Playwright in `pyproject.toml`**
   - Open `pyproject.toml`. Locate the `playwright` dependency.
   - Change `playwright>=1.48` to `playwright==1.58.0` (or whatever exact version the CI image ships).
   - Run `pip install -e ".[all-llms,dev]"` to update the lockfile (`uv.lock`).
   - Run `pytest -m browser tests/browser/` to confirm no regression.

3. **Add `.dockerignore`**
   - Create `.dockerignore` at repo root. Recommended content:
     ```
     # Secrets and local config
     .env
     .env.*
     !.env.example

     # Git
     .git/
     .gitignore

     # Project state
     workspace/
     missions/
     docs/
     .memory/

     # Python build artifacts
     __pycache__/
     *.pyc
     *.pyo
     *.egg-info/
     the_one.egg-info/
     .pytest_cache/
     .ruff_cache/
     .benchmarks/

     # Virtual envs
     .venv/
     venv/

     # IDE
     .vscode/
     .idea/

     # Maintenance reports (mission artifacts; not needed in image)
     maintenance/
     ```
   - Run `make rebuild` to verify the build context is smaller and no required files are excluded.

4. **Verify everything still works**
   - `make rebuild` succeeds.
   - `make up` starts the container.
   - `make test-browser` passes.
   - `pytest -q --ignore=tests/browser` passes.

## Edge Cases

- **Pinning to a digest requires a digest-aware registry pull**: most Concourse `docker-image` resources support `tag:` or `digest:`. If the registry on the build worker doesn't return digests by default, fall back to specific semver tags.
- **Playwright `==1.58.0` may conflict with another transitive dep**: if `pip install` fails after the pin, check the conflict and either bump Playwright to the smallest version that resolves OR upgrade the conflicting dep.
- **Missing files after `.dockerignore`**: if `make rebuild` fails because a required file was excluded, audit the `Dockerfile` `COPY` paths and adjust `.dockerignore` accordingly.
- **The pinned Playwright version may not exist as a published wheel** — confirm `pip install playwright==1.58.0` resolves before locking the pin in.

## Files Affected

- `ci/pipeline.yml` — 3-4 image reference pins
- `pyproject.toml` — Playwright version pin
- `uv.lock` — regenerated by `pip install -e`
- `.dockerignore` — NEW file at repo root

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `make rebuild` succeeds
- [ ] Browser tests pass with pinned Playwright
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
