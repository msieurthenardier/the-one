# Leg: release-workflow

**Status**: landed
**Flight**: [Windows on shared metadata, and one release](../flight.md)

## Objective
One `release.yml` replaces the Windows-only tag workflow. It audits, gates the version, builds Windows, Linux and macOS through their reusable workflows, and publishes all four packages, plus `SHA256SUMS`, to one GitHub release.

The version comes from one place. Squawks 0260 and 0262 are fixed. The docs and the contributor check are made ready for the release.

## Context
- **Flight DDs:**
  - DD6: the dynamic version, the lock lanes and their uv versions, the release gate.
  - DD7: `release.yml`'s jobs, inputs, tag-path fallbacks, the publish hardening, the retirements, the `.dmg` retention, the stub.
  - DD9: squawks 0260 and 0262.
  - DD10: the contributor check against the release.
  - DD11: outward steps need the operator's go; no tag before this leg lands.
- **What legs 1-3 produced:**
  - **`windows-packages.yml`:**
    - `workflow_call` with `version`/`mode`;
    - artifacts `windows-installer` (14 days, N only) and `windows-packages-logs`;
    - `full` runs `build.ps1` plus `smoke.py`.
  - **`linux-packages.yml`:** `workflow_call` with `version`; artifact `linux-packages` (3 days).
  - **`macos-packages.yml`:** `workflow_call` with `version`/`mode`; artifact `macos-dmg` (7 days, rising to 14 here).
  - **Package file names:**
    - `the-one-setup-<V>.exe`;
    - `GleepGlorp_AI-<V>-arm64.dmg`;
    - `GleepGlorp_AI-<V>-x86_64.AppImage`;
    - `gleepglorp-ai_<deb version>_amd64.deb`, where the Debian version is `render.deb_version`, so `0.12.0` stays `0.12.0`, and `.devN` becomes `~devN`.

    Confirm each pattern against the three workflows and `render.py`.
- **The Windows lifecycle result** (leg 3, run `40259389810`) is in the flight log. If it found defects, they are leg 3's to fix, not this leg's.
- **What still depends on `windows-installer.yml`:**
  - `tests/test_release_notes.py` (`WORKFLOW = … "windows-installer.yml"`, `test_workflow_publish_step_uses_notes_files`);
  - `tests/test_packaging_locked_closure.py` (`LOCKED_CLOSURE_REQUIRED` lists `.github/workflows/windows-installer.yml`; the leg 3 review changed this list, so re-read it);
  - `docs/releases/README.md` ("How it is used" names that workflow's publish step);
  - `ci/README.md` (lines about `windows-installer.yml` as the `v*` release path);
  - `.github/workflows/pr-lint.yml`'s comment referencing it.

  Grep again for any other dependents.
- **Flight 1's leftover stub** `.github/workflows/packaging-probe-windows.yml` is deleted.
- **The lock lanes (DD6):**
  - uv 0.9.30 in `ci/tasks/{lint,test,bwrap,browser}.yml` (an image tag) and `windows-tests.yml` (`pip install uv==0.9.30`);
  - uv 0.10.0 in `linux-packages.yml`/`macos-packages.yml`;
  - an unpinned uv in `pr-lint.yml` and `scripts/windows_test_copy.py`;
  - `build.ps1`'s own uv: check what it installs.
- **Squawks:**
  - `squawks/0260-model-catalog-never-refreshes.md`: refresh the seed, with a self-contained test and no committed upstream dump (the operator's no-golden-files rule).
  - `squawks/0262-desktop-upgrade-safety-docs.md`.
- **Shared files with Mission 31** (`pyproject.toml`, `uv.lock`, `README.md`, `CLAUDE.md`, `the_one/agents.md`, `ci/README.md`): additive edits in their own sections. If `origin/main` moved, the Flight Director merges `main` at a checkpoint, never under a running Developer.

## Inputs
- Legs 1-3 committed.
- `the_one/__init__.py` has `__version__ = "0.11.8"`. This leg does **not** bump it (leg 6 does).

## Outputs
**Phase 4a:**
- `pyproject.toml` with a dynamic version, and `uv.lock` regenerated.
- `.github/workflows/release.yml` (new); `windows-installer.yml` and `packaging-probe-windows.yml` deleted.
- `macos-packages.yml`: `.dmg` retention raised to 14 days, with the `on:` block untouched.
- `packaging/release/release.stub.yml` (the stub for `main`).
- `scripts/release_check.py`, or an addition to `render.py`: the version gate, callable from the workflow.
- `scripts/release_assets.py` (or a step): selects the four exact file names for V and writes `SHA256SUMS`.
- Tests:
  - the version gate;
  - the dynamic-version pin (renamed);
  - the `release.yml` structure (jobs, `needs`, tag-path expressions, the publish `if:`, permissions, concurrency, the frozen dispatch inputs equal to the stub's);
  - `test_release_notes.py` re-pointed;
  - `test_packaging_locked_closure.py` updated.

**Phase 4b:**
- Squawk 0260's fix and its test.
- Squawk 0262's docs.
- `docs/releases/README.md`, `ci/README.md`, `README.md` "Install", `CLAUDE.md` (an additive "Release (M32 F4)" paragraph, and the Windows packaging paragraph updated for `build.ps1`), `the_one/agents.md` (additive).
- `docs/macos-contributor-check.md` and `tests/behavior/macos-app-install.md` updated (DD10).
- A draft `docs/releases/v0.12.0.md`, for the operator to approve in leg 6.

## Acceptance Criteria

### Phase 4a
- [x] **AC1: the dynamic version.**
  - `pyproject.toml`: `dynamic = ["version"]`, `[tool.setuptools.dynamic] version = {attr = "the_one.__version__"}`, and no static `version`.
  - `uv lock` is run with **uv 0.10.0**, and `uv.lock`'s `revision` is unchanged. The diff is recorded in the flight log: what uv writes for the `the-one` package entry.
  - `tests/test_packaging_metadata.py::test_pyproject_version_matches_dunder_version` is renamed, as a rename rather than delete-and-add, to something like `test_pyproject_version_is_dynamic_from_dunder`, and asserts the dynamic declaration.
  - `pip install -e .` in a scratch venv reports `the-one` at `__version__` (`importlib.metadata.version("the-one")` in that venv).
- [x] **AC2: the lock lanes.**
  - With **uv 0.9.30** (a scratch `pip install uv==0.9.30` in a temporary venv): `uv sync --locked --extra all-llms --extra dev` (or `uv lock --check`) succeeds against the regenerated lock, in a scratch copy of the repo so the worktree's `.venv` is untouched.
  - With **uv 0.10.0**: `uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms` succeeds and yields the same closure as before. Diff the exported requirement names and versions, and record it.
  - The unpinned lanes are reasoned through. Record the uv each would get today, and whether `pr-lint.yml` needs `--frozen` (DD6: it keeps checking the lock).
- [x] **AC3: the version gate** (`scripts/release_check.py`, stdlib only, tested). It takes `--event` (from `github.event_name`), `--ref` and `--input-version`, and prints the version or fails. The tag path is chosen by `--event push` **and** a `refs/tags/v` ref, never by the ref alone: a `workflow_dispatch --ref v0.12.0` is a dry run. A test covers that case.
  - It loads `packaging/render.py` by path (`importlib.util.spec_from_file_location`), never `import packaging.render`, because the name shadows the PyPI `packaging` distribution.
  - It also validates the `platforms` input: comma-separated, no spaces, each of `windows`/`linux`/`macos`, at least one. An unknown or blank token fails the dispatch.
  - On a tag, it requires:
    - `refs/tags/vX.Y.Z`, with `X.Y.Z` exactly `__version__`;
    - a final release (`render._release_parts` with no dev number);
    - the tagged commit an ancestor of `origin/main`. The workflow fetches with `fetch-depth: 0`, and the check is `git merge-base --is-ancestor`.
  - On a dispatch, it accepts the input version in the strict grammar (`X.Y.Z` or `X.Y.Z.devN`), or `__version__` when the input is empty.
  - It runs the version through `render.load(…, {"version": V})`, so every platform's derived field (`deb_version`, `bundle_version`, `bundle_short_version`) is valid.
  - Unit tests cover: a tag equal to `__version__`; a tag not equal; a `.devN` tag (refused); `v0.12.0rc1` (refused); a non-ancestor (refused, through a tmp git repo); dispatch empty or dev; and the derived values for `0.12.0` (`CFBundleVersion` `0.12.9999`).
- [x] **AC4: `release.yml`.**
  - **Triggers:** `push: tags: ["v*"]` and `workflow_dispatch` with inputs:
    - `version` (string, default `""`);
    - `platforms` (string, default `windows,linux,macos`);
    - `macos_mode` (choice `full`|`lifecycle`, default `full`);
    - `windows_mode` (choice `full`|`lifecycle`, default `full`).
  - **Concurrency:** group `release-${{ github.event_name == 'push' && github.ref || 'dispatch' }}`, `cancel-in-progress: false`. With a group per event, a dry-run dispatch can never take a pending tag run's slot. **Permissions:** `contents: read` at the top.
  - **`audit` job:** the release-closure `pip-audit`, with `pr-lint.yml`'s extras and flags, plus `uv export --frozen`, using **`uv==0.10.0`**, pinned like the three builds. `pr-lint.yml` is left as it is (its unpinned bare `uv export` is recorded as a known gap in the flight log, not changed here).
  - **`version` job:** checkout with `fetch-depth: 0`, the AC3 gate, output `version`.
  - **`windows`, `linux`, `macos` jobs:**
    - `needs: [audit, version]`;
    - `uses: ./.github/workflows/<platform>-packages.yml`;
    - `with: version: ${{ needs.version.outputs.version }}`, plus the mode (`${{ inputs.windows_mode || 'full' }}`; macOS likewise; Linux has no mode);
    - `if: github.event_name == 'push' || contains(format(',{0},', inputs.platforms), ',<platform>,')`.
  - **`publish` job** (`runs-on: ubuntu-latest`, `permissions: contents: write`):
    - `if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')`;
    - `needs` all three platform jobs plus `version`;
    - downloads the three artifacts by name;
    - selects exactly the four packages for V by exact name (none missing, nothing extra) and writes `SHA256SUMS`;
    - creates the release as a **draft**, or reuses an existing draft. `gh release view <tag>` does not find a draft, so detect one with `gh release list --json tagName,isDraft,name` (bounded). The title and body come from `scripts/release_notes.py` and `docs/releases/$TAG.md`, falling back to the title `"$TAG"` with `--generate-notes`;
    - verifies the four files and `SHA256SUMS` exist **before** creating anything, and logs which branch ran (new draft, existing draft, or existing published release);
    - uploads all five files with `--clobber`, then publishes (`gh release edit --draft=false`);
    - an existing **non-draft** release is never re-titled and gets `--clobber` uploads only (today's rule for hand-written titles).
  - **No secrets** beyond `github.token`.
  - **The tests** parse the YAML and pin:
    - the jobs, their `needs`, `uses` paths and `with` values;
    - every tag-path fallback expression;
    - the publish `if:`;
    - the top-level permissions and `publish`'s;
    - the concurrency;
    - that the dispatch inputs equal the stub's byte for byte.
  - **Called workflows:** a called workflow's own `permissions: contents: read` and `concurrency` stay as they are. Note in a comment that no standalone platform dispatch may run during a release (the DD7 rule).
- [x] **AC5: the retirements.**
  - `windows-installer.yml` and `packaging-probe-windows.yml` are deleted.
  - `tests/test_release_notes.py` points at `release.yml`'s publish job, and its test checks the same notes logic there.
  - `tests/test_packaging_locked_closure.py` no longer lists the deleted file, and requires the locked sequence wherever the release builds: through `build.ps1`, and `release.yml`'s `audit` export.
  - `git grep -n "windows-installer.yml"` outside `missions/` and `squawks/` returns only deliberate historical mentions, each listed in the flight log. The known stale mentions to clean up are:
    - `tests/test_windows_build_recipe.py` (~192, an `EXEMPT` entry);
    - `pyproject.toml` comments (~47, ~145; shared file, edits minimal);
    - `packaging/windows/README.md` (~217-228, which also drops "push no `v*` tag before then");
    - `the_one/agents.md` (~1722);
    - comments in `packaging/windows/build.ps1` (~47) and `windows-packages.yml` (~71);
    - `ci/README.md` (6, 29, 92, 121), including line 6's "untouched and still owns official releases".
- [x] **AC6:** `macos-packages.yml`'s `.dmg` artifact retention and `linux-packages.yml`'s `linux-packages` artifact retention are both 14 days, so a failed `publish` can be re-run within that window. Neither `on:` block changes (show the `git diff` limited to those files).
- [x] **AC7: the stub.** `packaging/release/release.stub.yml` holds `release.yml`'s `workflow_dispatch` block exactly (no `push` trigger, no `publish` job) and one no-op job. The test pins equality with the real file's dispatch inputs. The Flight Director opens the stub PR. The stub's name and inputs freeze once it merges.
- [x] **AC8:** `make test-unit` passes (12 skips), only on a quiet host. Otherwise report it and do not run. Ruff is clean.

### Phase 4b
- [x] **AC9: squawk 0260, "seed as a floor" (the operator's decision, 2026-10-26).**
  - **Why the squawk's original fix is not used:** the design review ran the live fetch. 25 of the 77 seed pairs are gone upstream: 14 anthropic, all 200k, and 11 openai, seven of them 400k. Pruning them would lose those windows, and the problem would come back. The operator chose instead to make the refresh treat the seed as a floor, the way `scripts/refresh_model_catalog.py` already does. This is a small, approved design change that goes beyond the squawk's original scope; record it in the squawk.
  - **The change, in `the_one/llm/model_catalog.py::refresh_catalog_cache`:** the all-or-nothing seed-coverage guard becomes a merge.
    - The projected catalog is written with every seed pair it lacks added from the seed, and the fetched values win where both have a pair.
    - The defence the guard existed for (an empty or garbage fetch silently losing entries) holds by construction, because a degenerate fetch yields the seed plus the floor. Keep a guard that refuses to write when the fetch projected **no** models for a provider the seed covers, and log it.
    - Log one INFO line per refresh, with the count of seed-floored pairs (not one line per pair). There is no warning on a normal launch.
    - Update the function's docstring.
  - **Tests in `tests/test_model_catalog_refresh.py`:**
    - `test_guard_blocks_write_when_payload_missing_seed_pair` is renamed and inverted (rename, not delete) to, for example, `test_missing_seed_pair_is_kept_from_the_seed`: the cache is written, and it contains the seed's value for the missing pair.
    - Add:
      - a fetched value overrides the seed's for the same pair;
      - a provider that projects zero models is still refused;
      - no WARNING is logged in the floored case.
    - Fixtures are a few lines and built in the test. No upstream dump is committed.
  - **The seed refresh for v0.12.0:** run `scripts/refresh_model_catalog.py` (read it first for its usage) once at leg time, live from this host, and commit the regenerated `the_one/llm/data/model_catalog.json`. The script keeps existing seed pairs as a floor. Record the date and the counts (pairs added and changed per provider) in the flight log and the squawk. Check that `the-one doctor`'s catalog gate still resolves its probe model (`the_one/diagnostics.py`, the bundled-seed probe).
  - **The longer-term fix is logged as GitHub issue #316:** dynamic Claude windows from the Models API's `max_input_tokens`. Name it in the squawk's disposition and in the mission's Known Issues line, replacing the recurrence note.
  - **Squawk record:** the corrective action and verification go in the squawk, with status `in-progress`. The Flight Director marks it `completed` at the commit.
- [x] **AC10: squawk 0262.** An additive paragraph in `the_one/agents.md` (the desktop launcher or macOS packaging section). It names:
  - `tests/test_desktop_split_guard.py` and the rule "patch a name in the module that defines it; state lives on `session_state.state`; platform decisions live on `boot_policy` (Flight 4)";
  - the pywebview/PyObjC upgrade checklist: `tests/test_pywebview_cocoa_canary.py` green, **and** `gh workflow run macos-packages.yml --ref <branch> -f mode=lifecycle`;
  - that macOS CI is hosted-only and dispatch-limited.

  Plus one sentence in `CLAUDE.md`'s macOS packaging paragraph pointing to it. The squawk is updated as in AC9.
- [x] **AC11: the docs.**
  - **`docs/releases/README.md`:** "How it is used" now describes `release.yml` (audit → version → three builds → publish, drafts first, `SHA256SUMS`).
  - **`ci/README.md`:** the topology table and text, with `release.yml` as the `v*` path; the Concourse task builds through `build.ps1`; the `fly execute` line kept.
  - **`README.md` "Install":** every platform points at the GitHub release page, with the asset names, and links to the three install guides. Source install unchanged.
  - **`CLAUDE.md`:**
    - an additive "Release (M32 F4)" paragraph covering `release.yml`, the dispatch dry run (`gh workflow run release.yml --ref <branch> -f version=X.Y.Z.devN -f macos_mode=lifecycle -f windows_mode=lifecycle`), the version gate, "never a standalone platform dispatch during a release", and that the version lives only in `the_one/__init__.py`;
    - the Windows packaging (M15 F5) paragraph gains one sentence on `build.ps1` and the `[windows]` section.
  - **`the_one/agents.md`:** an additive "Release workflow (M32 F4)" section, and a "Windows packaging" update (`build.ps1`, the staged spec, the `}}_is1` identity, the graceful quit sequence, `lifecycle.ps1`).
  - All edits are additive and in their own sections.
- [x] **AC12: the contributor check (DD10).** `docs/macos-contributor-check.md` and `tests/behavior/macos-app-install.md` are updated so that:
  - N is the dry run's `0.12.0.dev1` `.dmg`: an Actions artifact, sign-in needed, downloaded as a zip; say how to find it;
  - N+1 is the `v0.12.0` release `.dmg`;
  - step 9's N+2 waits for the first patch release, with a note;
  - the added checks are: a real zsh with nvm on `PATH` (does `doctor`'s `path:` line show the nvm node?), logout while the app runs, a quit during boot, and whether a splash appears at all on first launch (squawk 0261's open verification);
  - the spec stays `draft`, with "Last Run: never".
- [x] **AC13: a draft `docs/releases/v0.12.0.md`.** It follows `docs/releases/README.md`'s format: the title `# v0.12.0 — GleepGlorp AI on macOS and Linux`, or similar. Its body covers:
  - the new macOS `.dmg` and Linux AppImage and `.deb` (with the guides);
  - the Windows installer now quitting the app cleanly on upgrade;
  - the window behaviour fixes;
  - the model catalog fix;
  - Notes: from v0.11.8, Windows closes the running app once by force; macOS unsigned approval; data locations unchanged.

  It is marked draft in the flight log; the operator approves its text in leg 6.
- [x] **AC14:** `make test-unit` passes (12 skips) on a quiet host, and ruff is clean.

## Verification Steps
- AC1-AC8:
  - `.venv/bin/python -m pytest tests/test_packaging_metadata.py tests/test_release_check.py tests/test_release_workflow.py tests/test_release_notes.py tests/test_packaging_locked_closure.py tests/test_windows_packages_workflow.py -x --timeout 30` (unit files: plain pytest);
  - the AC1 and AC2 command outputs in the flight log;
  - `git grep` for AC5.
- AC9: the squawk's verification; `.venv/bin/python -m pytest tests/test_model_catalog*.py tests/test_diagnostics*.py -x --timeout 30`.
- AC10-AC13: read the docs; check every command and path they name exists.
- AC8 and AC14: `make test-unit`, ruff.

## Implementation Guidance
1. **Two spawns.** The first Developer does phase 4a and hands back `[HANDOFF:review-needed]`. The Flight Director reviews, commits and opens the stub PR. A second Developer does phase 4b and lands the leg.
2. **The dynamic version first.** Do it in a scratch copy for the uv checks (AC2), so the worktree's `.venv` and lock are touched only by the one real `uv lock`.
3. **Write the gate as a tested script** the workflow calls (`python scripts/release_check.py --ref "$GITHUB_REF" --input-version "$INPUT"`), not inline shell logic. Do the same for asset selection.
4. **`release.yml`'s `publish`** reuses `windows-installer.yml`'s notes logic (`scripts/release_notes.py`, the UTF-8 title file), adapted to draft-then-publish. Delete the old workflow only after `release.yml` and its tests exist.
5. **No pushes, PRs, tags or dispatches.** Those are the Flight Director's.

## Edge Cases
- **A re-run of a tag's release.yml after a partial publish:** the draft already exists. Upload with `--clobber`, then publish. A non-draft published release gets uploads only (never re-titled).
- **A dispatch while a tag run is pending:** they are in different concurrency groups (AC4), so neither displaces the other.
- **A dispatch with `platforms=macos`:** the `windows` and `linux` jobs are skipped. `publish` is skipped anyway on a dispatch.
- **`needs` on a skipped job:** `publish` runs only on a push, where all three platforms run. Make sure the skipped-job semantics never let `publish` run with a platform missing, through the explicit `if:` plus `needs`, and the exact-name check.
- **`deb_version` for `0.12.0`** is `0.12.0`, and for `0.12.0.dev1` it is `0.12.0~dev1`. The asset selection uses `render.deb_version`, never a guess.
- **The live seed refresh fails or is offline at leg time:** the code change and its tests still land. Record it and leave the seed unchanged, with `[BLOCKED:catalog-fetch]` noted only for the seed part.

## Citation Audit
Checked at `7ecc171`:
- `.github/workflows/windows-installer.yml`: the `pip-audit` job, the notes/publish step and `cancel-in-progress: true`: verified.
- `.github/workflows/{linux,macos,windows}-packages.yml`: `workflow_call` inputs and artifact names: verified (`windows-installer` from leg 3b).
- `tests/test_release_notes.py`: `WORKFLOW` and `test_workflow_publish_step_uses_notes_files`: verified.
- `ci/tasks/{lint,test,bwrap,browser}.yml`: `uv sync --locked`; `ci/tasks/windows-tests.yml`: `uv==0.9.30`: verified.
- `docs/releases/README.md` "How it is used": verified.
- `CLAUDE.md`'s macOS packaging paragraph (M32 F3) and `the_one/agents.md` "Linux packaging (M32 F2)"/"macOS packaging (M32 F3)" sections: verified.
- `squawks/0260-…`, `squawks/0262-…`: verified (open).
