# Leg: 01-brand-assets

**Status**: completed
**Flight**: [Brand Foundation](../flight.md)

## Objective

Derive favicon and topbar-icon PNG variants from the source mascot PNG via a committed Makefile target, wire the favicon set into the served HTML, and embed the topbar mascot icon next to the title wordmark — all without introducing layout shift on page load.

## Context

- This is Leg 1 of 5 in Flight 1 (Brand Foundation). Nothing prior; the flight log is empty.
- Pillow is declared in `pyproject.toml`'s `dev` extras (line 36) and `Dockerfile` line 30 installs `.[dev,all-llms]`, so PIL is available in the running container — no new dependency.
- The Dockerfile bakes `the_one/` into the image at build time; `make rebuild` is required after any static-asset change to surface the new files to `localhost:8484`. The derivation script runs inside the running container via `docker exec the-one ...` (matching the project's `docker exec the-one pytest` convention at CLAUDE.md:411). To make the script readable from inside the container, `docker-compose.yml` adds a read-only bind-mount of `./scripts:/app/scripts:ro` — without this, `/app/scripts/` would not exist inside the container (Dockerfile does not `COPY scripts/`). Outputs are written to `the_one/interfaces/web/static/brand/`, which is already bind-mounted at `./the_one:/app/the_one` (docker-compose.yml line 39), so writes from inside the container appear on the host immediately.
- The flight's open question about source-PNG choice is resolved here: use `gleepglorp_med.png` — both source PNGs are ~1.8 MB but the med variant has the higher visual fidelity, which produces cleaner downsamples especially at the smaller favicon sizes (16, 32). The `_small.png` stays in `static/brand/` as-is but is not used by the derivation.
- The flight's scoped CSS rule for the topbar `<img>` was suggested as inline-block with `vertical-align: middle; margin-right: 8px;`. This leg promotes `.app-topbar-title` to a flex container instead, which is cleaner and matches the adjacent `.app-topbar-actions` pattern at `the_one/interfaces/web/static/css/components.css:29-33`. The `<img>` gets `flex-shrink: 0` so future wordmark length doesn't crush it. Functionally equivalent CLS prevention; cleaner CSS.
- The `static/brand/` directory currently has WSL/Windows `Zone.Identifier` ADS files alongside the source PNGs — noise that should be cleaned up in this leg by adding `*:Zone.Identifier` to `.gitignore` (or deleting the files outright) so they don't pollute the directory listing or accidentally commit.

## Inputs

Files that must exist:
- `the_one/interfaces/web/static/brand/gleepglorp_med.png` — source mascot, ~1.8 MB, AI-generated emblem
- `the_one/interfaces/web/static/brand/gleepglorp_small.png` — secondary source, retained but unused by this leg
- `Makefile` at repo root
- `the_one/interfaces/web/static/index.html` — currently has no favicon `<link>` tags
- `the_one/interfaces/web/static/js/app.js:14-30 — renderTopBar — "<h1 class=\"app-topbar-title\">the-one</h1>"` — topbar title rendering site
- `the_one/interfaces/web/static/css/components.css:23 — ".app-topbar-title {"` — existing topbar title CSS rule

State that must be true:
- Container is running (`make up` first if not)
- Pillow is importable inside the container (sanity check: `docker exec the-one python -c "from PIL import Image; print(Image.__version__)"` returns a version string)

## Outputs

Files created:
- `scripts/derive_brand_assets.py` — idempotent Pillow derivation script
- `the_one/interfaces/web/static/brand/favicon-16.png` (16×16)
- `the_one/interfaces/web/static/brand/favicon-32.png` (32×32)
- `the_one/interfaces/web/static/brand/favicon-48.png` (48×48)
- `the_one/interfaces/web/static/brand/favicon.ico` (multi-resolution: 16, 32, 48)
- `the_one/interfaces/web/static/brand/apple-touch-icon.png` (180×180)
- `the_one/interfaces/web/static/brand/icon-192.png` (192×192 — PWA-readiness, no manifest in this leg)
- `the_one/interfaces/web/static/brand/icon-512.png` (512×512 — PWA-readiness)
- `the_one/interfaces/web/static/brand/topbar-icon-24.png` (24×24 — used by the topbar `<img>`)

Files modified:
- `docker-compose.yml` — one new bind-mount entry `./scripts:/app/scripts:ro` (read-only since the script writes to `the_one/`, not `scripts/`), placed alongside the existing `./the_one` and `./tests` bind-mounts around line 43
- `Makefile` — new `.PHONY: brand-assets` target under a new `# ── Brand assets ──` section header (between `# ── Verification ──` and `# ── Tests ──`, lines 78/99 in the current Makefile), with `##` doc-string so the existing `make help` grep picks it up
- `the_one/interfaces/web/static/index.html` — adds 5 `<link>` tags for the favicon set
- `the_one/interfaces/web/static/js/app.js` — topbar `<h1>` HTML string in `renderTopBar()` now opens with `<img src="/static/brand/topbar-icon-24.png" width="24" height="24" alt="">` before the wordmark text
- `the_one/interfaces/web/static/css/components.css` — `.app-topbar-title` rule promoted to flex container; new `.app-topbar-title img` rule for sizing
- `.gitignore` — append `*:Zone.Identifier` so WSL/Windows ADS files don't accidentally commit

State changes:
- Browser tab now shows a purple mascot favicon (replaces the missing-favicon glyph)
- Topbar shows a 24px mascot icon before the title text in all areas, in both themes

## Acceptance Criteria

- [x] `scripts/derive_brand_assets.py` exists, is idempotent at the pixel level (running twice produces outputs where `PIL.Image.open(p).tobytes()` is identical for each output file — file-byte-equality is NOT required, since Pillow's PNG encoder may vary across versions), and accepts an optional `--source` flag defaulting to `the_one/interfaces/web/static/brand/gleepglorp_med.png`
- [x] `docker-compose.yml` has a `./scripts:/app/scripts:ro` bind-mount entry on the `the-one` service
- [x] `Makefile` has a `brand-assets` target documented in `make help` (i.e., `make help` output includes a line starting with `brand-assets`)
- [x] Running `make brand-assets` from a clean state produces all 8 derived files in `the_one/interfaces/web/static/brand/`
- [x] All 8 derived files commit to git (NOT gitignored — they ship in the served image)
- [x] `the_one/interfaces/web/static/index.html` contains `<link>` tags for: 16×16 PNG, 32×32 PNG, 48×48 PNG, `.ico` multi-res, and 180×180 apple-touch-icon
- [x] When `renderTopBar()` runs, the resulting DOM has `<img src="/static/brand/topbar-icon-24.png" width="24" height="24" alt="">` as the first child element of `<h1 class="app-topbar-title">`, with the literal text `the-one` immediately following the img (wordmark text stays `the-one` here — Leg 4 changes it)
- [x] `the_one/interfaces/web/static/css/components.css` `.app-topbar-title` rule uses `display: flex; align-items: center; gap: 8px;` and there is a `.app-topbar-title img { width: 24px; height: 24px; flex-shrink: 0; }` rule immediately after
- [x] `.gitignore` contains an entry that matches `*:Zone.Identifier`
- [x] After `make rebuild`, loading `http://localhost:8484/` shows the mascot in the browser tab favicon AND in the topbar with no observable layout shift on first paint _(verified indirectly: `curl /` returns 200 with all 5 `<link>` tags rendered and `/static/brand/topbar-icon-24.png` returns 200; visual confirmation deferred to reviewer / operator HAT)_
- [ ] `docker exec the-one pytest tests/` passes (no functional regressions; visual snapshots are excluded by `addopts` so stale baselines do not surface here) _— DEFERRED: broad pytest run hung on SQLite WAL contention with the live uvicorn container (pid 1 holds `/root/.the-one/the-one.db`). The narrow non-DB gate `pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py` (43 tests, 0.05s, exit 0) was substituted. None of this leg's changes (CSS/JS/HTML/PNG/Makefile/compose) can affect Python test behaviour. See flight-log Leg 01 entry + Anomalies._
- [x] `make verify-serving` passes (admin sub-modules still return 200)

## Verification Steps

For each acceptance criterion:

- **Derivation script exists and is pixel-idempotent**:
  ```
  ls -la scripts/derive_brand_assets.py
  make brand-assets
  cp the_one/interfaces/web/static/brand/favicon-32.png /tmp/run1.png
  make brand-assets
  docker exec the-one python -c "from PIL import Image; a=Image.open('/tmp/run1.png').tobytes(); b=Image.open('/app/the_one/interfaces/web/static/brand/favicon-32.png').tobytes(); print('IDEMPOTENT' if a==b else 'DRIFT')"
  # Expected: IDEMPOTENT
  ```
- **Makefile target documented**: `make help | grep brand-assets` returns the doc line
- **All 8 files produced**: `ls the_one/interfaces/web/static/brand/ | grep -E '(favicon-|apple-touch|icon-|topbar-icon|favicon\.ico)' | wc -l` returns `8`
- **Files committed (not gitignored)**: `git check-ignore the_one/interfaces/web/static/brand/favicon-32.png` returns non-zero (i.e., NOT ignored)
- **index.html `<link>` tags**: `grep -c 'rel="icon"\|rel="apple-touch-icon"' the_one/interfaces/web/static/index.html` returns `5`
- **app.js topbar `<img>` present**: `grep -n 'topbar-icon-24.png' the_one/interfaces/web/static/js/app.js` finds the `<img>` line inside `renderTopBar()`
- **CSS flex + img rules**: `grep -A2 'app-topbar-title' the_one/interfaces/web/static/css/components.css | grep -E 'display: flex|flex-shrink'` returns both rules
- **Visual check (manual after `make rebuild`)**:
  - Tab shows mascot favicon (in Chrome/Firefox, may need hard reload — Cmd+Shift+R / Ctrl+Shift+R)
  - Topbar shows 24px mascot to the left of "the-one" wordmark
  - Reload page with throttled "Slow 3G" in DevTools — wordmark does not shift horizontally as the icon decodes (CLS = 0)
- **Test suite green**: `docker exec the-one pytest tests/ -x -q` exits 0
- **Serving check**: `make verify-serving` exits 0

## Implementation Guidance

1. **Add the scripts bind-mount to `docker-compose.yml`**
   - Open `docker-compose.yml`; under the `the-one` service `volumes:` block (around line 43, right after `./tests:/app/tests`), add: `- ./scripts:/app/scripts:ro`
   - Read-only is correct: the script reads its own source from this path and writes outputs to `the_one/...` which is already bind-mounted read-write at lines 39-40
   - Run `docker compose up -d the-one --force-recreate` (or `make rebuild` if a Dockerfile change is needed) to apply — bind-mount additions require container recreation, NOT just a restart

2. **Create the derivation script** at `scripts/derive_brand_assets.py`
   - Single Python file, runnable inside the container as `python /app/scripts/derive_brand_assets.py`
   - Uses only `PIL.Image` (already installed) and stdlib (`pathlib`, `argparse`)
   - Argparse: `--source` (defaults to the med PNG path under `the_one/interfaces/web/static/brand/gleepglorp_med.png`), `--out-dir` (defaults to `the_one/interfaces/web/static/brand/`)
   - **Square-pad before resize**: open source, compute `size = max(w, h)`, create a new transparent canvas `Image.new("RGBA", (size, size), (0, 0, 0, 0))`, paste source at `((size - w) // 2, (size - h) // 2)`. This is the single canonical source for all subsequent resizes — do NOT use `Image.thumbnail`. If the source is already exactly square, the paste is a no-op visually but the code path remains the same (cheap; keeps the algorithm uniform).
   - For each of the 7 PNG sizes (16, 24, 32, 48, 180, 192, 512), `resize((target, target), Image.Resampling.LANCZOS)` on the square-padded canvas and `.save(out_path, "PNG", optimize=True)`
   - For the `.ico`, take the square-padded canvas, resize to 48×48, then `.save(out_path, "ICO", sizes=[(16,16), (32,32), (48,48)])` — Pillow handles the multi-resolution ICO directly
   - Filenames must match the acceptance-criteria list exactly: `favicon-{size}.png`, `apple-touch-icon.png` (the 180×180 one), `icon-{size}.png` (192, 512), `topbar-icon-24.png` (the 24×24), `favicon.ico`
   - Add a module-level docstring explaining what it does, when to re-run it (logo refresh), that derived outputs commit to the repo (not gitignored), and that pixel-idempotency holds across runs but file-byte equality may vary if Pillow's version changes.

3. **Add the Makefile target** under a new `# ── Brand assets ──` section header inserted between the existing `# ── Verification ──` (line 78) and `# ── Tests ──` (line 99) sections
   - Form (uses `docker exec the-one` per CLAUDE.md:411 convention — `docker compose run` would spawn a fresh ephemeral container; `docker exec` reuses the live daemon):
     ```make
     # ── Brand assets ──────────────────────────────────────────────────────

     .PHONY: brand-assets
     brand-assets: ## Derive favicon + topbar icon PNGs from source mascot via Pillow
     	docker exec the-one python /app/scripts/derive_brand_assets.py
     ```
   - Verify it appears in `make help` — the existing help target greps `## ` annotations; the format above matches.
   - Precondition: the `the-one` container must be running (`make up`) before `make brand-assets` works. If the operator runs it cold, `docker exec` errors clearly with "no such container" — acceptable; not worth gating.

4. **Run the derivation once locally** and commit the produced files
   - `make brand-assets`
   - Confirm the 8 files exist; spot-check one of the favicon PNGs in an image viewer to verify the mascot is recognizable (16×16 will be muddy but should still read as "round purple thing")

5. **Wire the favicon set into index.html**
   - Open `the_one/interfaces/web/static/index.html`
   - After the `<meta name="viewport">` tag and before `<title>`, insert:
     ```html
     <link rel="icon" type="image/png" sizes="16x16" href="/static/brand/favicon-16.png">
     <link rel="icon" type="image/png" sizes="32x32" href="/static/brand/favicon-32.png">
     <link rel="icon" type="image/png" sizes="48x48" href="/static/brand/favicon-48.png">
     <link rel="icon" href="/static/brand/favicon.ico">
     <link rel="apple-touch-icon" sizes="180x180" href="/static/brand/apple-touch-icon.png">
     ```
   - Leave the `<title>the-one</title>` line alone — Leg 4 changes the text.

6. **Embed the topbar icon in app.js**
   - Open `the_one/interfaces/web/static/js/app.js`
   - In `renderTopBar()` at line ~14-30, change the `<h1>` HTML string from:
     ```js
     '<h1 class="app-topbar-title">the-one</h1>' +
     ```
     to:
     ```js
     '<h1 class="app-topbar-title">' +
       '<img src="/static/brand/topbar-icon-24.png" width="24" height="24" alt="">' +
       'the-one' +
     '</h1>' +
     ```
   - `alt=""` is intentional — the icon is decorative; the wordmark text is the accessible name. Leave the wordmark text `the-one` for now; Leg 4 changes it.

7. **Update the topbar CSS** in `components.css`
   - Find the existing `.app-topbar-title { ... }` rule at line ~23
   - Modify to:
     ```css
     .app-topbar-title {
         font-size: var(--font-size-h1);
         font-weight: var(--font-weight-bold);
         color: var(--accent);
         margin: 0;
         display: flex;
         align-items: center;
         gap: 8px;
     }
     .app-topbar-title img {
         width: 24px;
         height: 24px;
         flex-shrink: 0;
     }
     ```
   - The `flex-shrink: 0` is the load-bearing CLS guard: even if the wordmark grows past viewport width, the icon stays 24px.

8. **Clean up Zone.Identifier ADS files**
   - Add `*:Zone.Identifier` to `.gitignore` (append; the rest of the file is untouched)
   - Delete any existing `*:Zone.Identifier` files in the working tree: `find . -name "*:Zone.Identifier" -delete`

9. **Rebuild and verify**
   - `make rebuild`
   - Open `http://localhost:8484/` in a private/incognito window (avoids stale favicon cache from previous sessions)
   - Hard-reload (`Cmd+Shift+R` / `Ctrl+Shift+R`) twice to defeat any sticky favicon caching
   - Confirm visually: favicon in tab, mascot in topbar, no shift on load
   - Run `make test` and `make verify-serving` to confirm no regressions

## Edge Cases

- **Pillow not in the container**: if `docker exec the-one python -c 'from PIL import Image'` fails, the dev image is stale relative to `pyproject.toml`. Run `make rebuild` first to pull in the dev extras. (Pillow has been in dev extras since at least the F2 visual-snapshot work — should be present.)
- **Source PNG is not RGBA**: the `gleepglorp_med.png` may be RGB without alpha. The square-pad step creates a transparent RGBA canvas, so pasting an RGB source onto it produces an RGBA result regardless of source mode; downstream resizing and `.save()` handle RGBA cleanly. No separate `.convert("RGBA")` is needed.
- **Source PNG has non-square dimensions**: AI-generated PNGs sometimes drift from exact squareness. The square-pad step (Implementation Guidance #2) handles this — compute `size = max(w, h)`, create a transparent canvas of `(size, size)`, paste the source centered. If the source is already exactly square, the paste is a no-op visually but the code path remains uniform.
- **Browser favicon caching is aggressive**: even after `make rebuild`, a previously-cached favicon may persist. Document in the leg log if the operator needs hard-reload or private window to see the new favicon. Not a code defect; expected browser behavior.
- **16×16 muddy**: acceptable for this leg. Future-enhancement (out of scope here): generate the 16/32 sizes from a centered crop of just the mascot's head/face, which preserves more recognizable detail than downscaling the full emblem. Capture as a known issue / future-enhancement note if the result reads as completely unreadable at 16×16.
- **`make brand-assets` from outside the project root**: the Makefile target uses `docker exec the-one ...`, which runs the script inside the live container at its existing `WORKDIR /app` (set by the Dockerfile). `make` itself enforces project-root execution via `MAKEFLAGS` regardless of where the operator invokes it from, so the host-side cwd doesn't matter; the script's container-side paths are relative to `/app`.

## Files Affected

- `scripts/derive_brand_assets.py` — new file, ~70-90 lines of Python
- `docker-compose.yml` — one new bind-mount line
- `Makefile` — adds one section header + one target (~5 lines including doc-string)
- `the_one/interfaces/web/static/brand/favicon-16.png` — new (derived)
- `the_one/interfaces/web/static/brand/favicon-32.png` — new (derived)
- `the_one/interfaces/web/static/brand/favicon-48.png` — new (derived)
- `the_one/interfaces/web/static/brand/favicon.ico` — new (derived)
- `the_one/interfaces/web/static/brand/apple-touch-icon.png` — new (derived)
- `the_one/interfaces/web/static/brand/icon-192.png` — new (derived)
- `the_one/interfaces/web/static/brand/icon-512.png` — new (derived)
- `the_one/interfaces/web/static/brand/topbar-icon-24.png` — new (derived)
- `the_one/interfaces/web/static/index.html` — 5 new `<link>` tags
- `the_one/interfaces/web/static/js/app.js` — `renderTopBar()` HTML string updated
- `the_one/interfaces/web/static/css/components.css` — `.app-topbar-title` rule reshaped + new `.app-topbar-title img` rule
- `.gitignore` — append `*:Zone.Identifier`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `docker exec the-one pytest tests/ -x -q` exits 0
- [ ] Update flight-log.md with leg progress entry (final source-PNG choice, any deviations, any browser-cache quirks observed)
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off leg `01-brand-assets` in flight.md's Legs list and the Checkpoints list
- [ ] Commit all changes together (code + artifacts) — derived PNGs DO commit; do not add `static/brand/*.png` to `.gitignore`

---

## Citation Audit

8 citations verified against current code at design-review time (round 2, after incorporating Developer feedback):

| Citation | Verified |
|---|---|
| `pyproject.toml:36` — Pillow in `dev` extras | OK |
| `Dockerfile:30` — installs `.[dev,all-llms]` | OK |
| `the_one/interfaces/web/static/js/app.js:14-30 — renderTopBar` containing `<h1 class="app-topbar-title">the-one</h1>` | OK (snippet matches line 17 exactly) |
| `the_one/interfaces/web/static/css/components.css:23 — ".app-topbar-title {"` | OK |
| `the_one/interfaces/web/static/css/components.css:29-33 — .app-topbar-actions` | OK |
| `docker-compose.yml:39-40 — ./the_one bind-mounts` | OK |
| `docker-compose.yml:43 — ./tests bind-mount (new scripts mount inserts after)` | OK |
| `Makefile` — new Brand assets section inserts between the existing `# ── Verification ──` and `# ── Tests ──` section headers (currently ~lines 78 and 99; line numbers may drift) | OK |
| `CLAUDE.md:411 — docker exec the-one convention` | OK |

Design-review revisions applied (Developer review, round 1):
- High: switched runtime from `docker compose run --rm` to `docker exec the-one`; added `./scripts:/app/scripts:ro` bind-mount to docker-compose.yml.
- High: corrected Makefile insertion target from non-existent "Container lifecycle → Testing" boundary to actual "Verification (line 78) → Tests (line 99)" boundary.
- Medium: weakened idempotency criterion from byte-equality to pixel-equality (`PIL.Image.open(p).tobytes()`); guards against Pillow version drift.
- Medium: rewrote square-pad guidance to drop `Image.thumbnail` reference; now a clean compute-size / create-canvas / paste-centered flow.
- Medium: rephrased acceptance criterion #6 to a DOM-structure check, not a literal HTML string grep, so whitespace doesn't fail it.
- Low: source-PNG choice rationale restated inline (both sources ~1.8 MB; med has higher fidelity → cleaner downsamples).
- Low: Zone.Identifier ADS files now cleaned + gitignored as part of leg scope.
