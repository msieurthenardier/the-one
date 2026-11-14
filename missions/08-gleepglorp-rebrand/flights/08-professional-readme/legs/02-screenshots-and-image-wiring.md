# Leg: screenshots-and-image-wiring

**Status**: completed
**Flight**: [Professional README](../flight.md)

## Objective

Operator captures three dark-theme screenshots from a realistically-seeded GleepGlorp AI instance (Chat with trace expanded, Studio with agent editor visible, Administration with providers grid populated), commits them under `docs/screenshots/`, and the Flight Director swaps the three `<!-- SCREENSHOT: -->` HTML-comment placeholders in `README.md` for `<img>` references.

## Context

L01 landed the README with three HTML-comment placeholders at lines 17, 19, 21 (`chat-dark.png`, `studio-dark.png`, `admin-dark.png`). The agents.md `gated-debug-instrumentation` convention also landed in L01. This leg is **operator-heavy** — the FD cannot drive a browser to capture images; the operator boots the app, seeds demo state, captures, and the FD does the README image-wiring half once the PNGs are committed.

Key design decisions inherited from the flight:
- **Manual operator capture, no Playwright fixture** — screenshots regenerate rarely; an automated capture script is over-engineering
- **3 shots, dark theme only** — chat / studio / admin; light-theme parity is preserved by the existing pixel-snapshot test suite (gitignored)
- **Realistic seeded state, not empty states** — shows the system at intentional use
- **Explicit data-leak gate** — operator visually confirms no personal data, real conversation content, or real-world agent names appear in any committed PNG before commit

## Inputs

**State before this leg runs**:
- L01 committed at `814f8d3` (branch `flight/08-professional-readme`)
- `/README.md` exists with three `<!-- SCREENSHOT: {area}-dark.png -->` placeholders at lines 17, 19, 21
- `the_one/agents.md` has the `### gated-debug-instrumentation` convention entry
- No `docs/screenshots/` directory exists yet
- App is buildable via `make rebuild-clean` (Docker + Playwright Chromium baseline available)

## Outputs

**Files created**:
- `~/projects/the-one/docs/screenshots/chat-dark.png`
- `~/projects/the-one/docs/screenshots/studio-dark.png`
- `~/projects/the-one/docs/screenshots/admin-dark.png`

**Files modified**:
- `~/projects/the-one/README.md` — three `<!-- SCREENSHOT: -->` placeholders replaced with `<img>` references; each `<img>` wrapped in a `<p align="center">` for centering consistency with the hero asset

## Acceptance Criteria

- [x] `docs/screenshots/` directory exists at the repo root with exactly three PNG files: `chat-dark.png`, `studio-dark.png`, `admin-dark.png`
- [x] Each PNG shows the GleepGlorp AI app in dark theme (verified: dark page background, light text, violet accents)
- [x] Each PNG shows a representative populated state (NOT empty): Chat shows two assistant turns with a trace expanded; Studio shows the agent editor open with the General tab visible and provider/model populated; Administration shows the Ollama provider tile
- [x] No PNG contains personal data, real-world API keys, conversation content unfit for a public repo, or real-world agent names — FD visually verified before commit (only demo agent name `GleepGlorp`; only `host.docker.internal` URL in admin shot, not a real-world endpoint; sandbox-constrained chat exchange with no leakable content)
- [x] PNG viewports are consistent — 1440×900 DPR 1 (confirmed via `file *.png`)
- [x] `/README.md` no longer contains any `<!-- SCREENSHOT: -->` HTML-comment placeholders (`grep -c` returns 0)
- [x] `/README.md` contains three new `<img>` tags pointing to `docs/screenshots/{chat,studio,admin}-dark.png` in the same order as the original placeholders (lines 18, 22, 26)
- [x] Each new `<img>` includes an `alt` attribute describing the screenshot
- [x] README renders cleanly with all four images (hero + 3 screenshots) loading via local file paths
- [x] `docs/screenshots/` is NOT gitignored — `git check-ignore` exits with code 1

## Verification Steps

- **Screenshots committed**: `ls ~/projects/the-one/docs/screenshots/` shows exactly three files: `chat-dark.png`, `studio-dark.png`, `admin-dark.png`
- **PNGs are valid images**: `file ~/projects/the-one/docs/screenshots/*.png` reports each as `PNG image data, ...`
- **Dimensions consistent**: `for f in ~/projects/the-one/docs/screenshots/*.png; do file "$f"; done` — width × height should be the same across all three
- **Not gitignored**: `cd ~/projects/the-one && git check-ignore docs/screenshots/chat-dark.png ; echo "Exit code: $?"` — exit code should be 1 (NOT ignored)
- **README placeholders gone**: `grep -c "<!-- SCREENSHOT:" ~/projects/the-one/README.md` — zero matches
- **README `<img>` references present**: `grep -c "docs/screenshots/" ~/projects/the-one/README.md` — exactly 3 matches
- **README order preserved**: `grep -n "docs/screenshots/" ~/projects/the-one/README.md | head` — order is `chat-dark` → `studio-dark` → `admin-dark`
- **`alt` text present**: `grep -c 'alt="' ~/projects/the-one/README.md` — at least 4 matches (hero + 3 screenshots)
- **Visual sanity (operator)**: open README in VS Code preview or push branch to GitHub — all four images load without broken-image icons

## Implementation Guidance

### Step 1: Operator boots and seeds the app

Operator runs:
```bash
cd ~/projects/the-one
make rebuild-clean      # wipes DB volume, fresh start (HAT prep)
make _ensure-playwright # restore Playwright Chromium if wiped
```

Once the container is up at `http://localhost:8484`, operator seeds demo state:

1. **Configure a provider** (Administration → LLM Providers):
   - Pick whichever provider is convenient (ollama is the no-key-required default; Anthropic / OpenAI also fine if keys are available)
   - For the **Admin screenshot**, having ≥1 configured provider tile is the goal
   - For the **Chat screenshot**, the provider must work end-to-end (the chat needs a real LLM response, not an error)

2. **Configure an agent** (Studio → Agents → New):
   - Name: `GleepGlorp` (clean demo identity — NOT a real-world agent name)
   - System prompt: short and benign (e.g. "You are a helpful coding assistant.")
   - Tools: enable a few that will exercise the trace visualization (e.g. `read_file`, `list_dir`, `grep`)
   - Model: pick whichever the provider exposes
   - Save

3. **Run a chat exchange** (Chat → select the GleepGlorp agent → start a new session):
   - Ask something that triggers a tool call (e.g. "List the files in `the_one/llm/`.")
   - Wait for the agent to respond — confirm the tool-call trace renders on the assistant turn
   - Click the trace to expand it (so the screenshot shows the trace contents, not just a collapsed indicator)
   - Optionally send a second message to enrich the chat history

### Step 2: Theme to dark, set viewport

- In the topbar / Admin → General → Appearance, switch theme to **Dark**
- Set browser window to **1440×900** (working hypothesis — alternatives like 1280×800 or 1600×1000 are fine, just keep all three screenshots at the same dimensions)
- Use DevTools (F12 → Toggle device toolbar → set custom size) for exact dimension control, or rely on OS window-size if precise sizing isn't critical

### Step 3: Capture the three screenshots

For each screenshot:

1. **Chat (`chat-dark.png`)**:
   - Navigate to `http://localhost:8484/#chat`
   - The seeded session should be active (or click it in the session list)
   - The assistant turn with the tool-call trace EXPANDED should be visible
   - Capture the full viewport — DevTools "Capture full size screenshot" via Cmd/Ctrl+Shift+P → "screenshot", OR OS screenshot tool with browser window framed cleanly

2. **Studio (`studio-dark.png`)**:
   - Navigate to `http://localhost:8484/#studio`
   - Click the `GleepGlorp` agent to open the editor (so the screenshot shows the editor panel, not just the grid)
   - General tab or Tools tab — pick whichever looks more visually substantive
   - Capture

3. **Admin (`admin-dark.png`)**:
   - Navigate to `http://localhost:8484/#admin/llm-providers`
   - The configured provider tile should be visible in the grid
   - Capture

### Step 4: Visual data-leak check (operator)

Before saving the PNGs, the operator visually inspects each one:

- **NO real-world API keys** visible (masked entries are fine — verify masking is in effect)
- **NO personal data** in the chat (no real names, real conversations, real file paths from operator's home directory, etc.)
- **NO real-world agent names** — only the demo `GleepGlorp` agent
- **NO secrets** in URL bars, console panels, devtools network tabs (if DevTools is open in the screenshot, close it before capturing)

If anything is unfit for a public repo: recapture.

### Step 5: Commit PNGs to `docs/screenshots/`

```bash
cd ~/projects/the-one
mkdir -p docs/screenshots
# operator copies the three PNGs from wherever they were saved into docs/screenshots/
# (operator's responsibility — paths depend on OS / capture tool)
ls -la docs/screenshots/  # verify all three present
git check-ignore docs/screenshots/chat-dark.png ; echo "Exit: $?"  # must exit 1 (not ignored)
```

### Step 6: Wire `<img>` tags into README (Flight Director-handled)

The FD replaces the three placeholders. For each `<!-- SCREENSHOT: {area}-dark.png -->` block, substitute (the order in README is `chat`, `studio`, `admin`):

```html
<p align="center">
  <img src="docs/screenshots/chat-dark.png" alt="Chat — populated session with tool-call trace expanded" width="900">
</p>
```

(Width `900` is a hint — adjust to match the actual capture's natural pixel width, or omit if the natural width renders well.)

Each `<img>` wrapped in a centering `<p>` for visual consistency with the hero image at line 1-3.

After all three placeholders are replaced:
- `grep -c "<!-- SCREENSHOT:" README.md` should report 0
- `grep -c "docs/screenshots/" README.md` should report 3 (one per `<img src>` reference)
- Order must remain chat → studio → admin (matches the L01 placeholder order)

### Step 7: Verification + commit

- Open README in markdown preview — all four images (hero + 3 screenshots) render
- Run all "Verification Steps" listed above
- Update leg artifact: status `landed`, all `[x]` boxes ticked
- Update flight log: L02 Leg Progress entry
- Commit: `git add docs/screenshots/ README.md missions/.../legs/02-*.md missions/.../flight-log.md` (+ flight.md leg checkbox update) and commit with message:
  ```
  flight/08: screenshots + README image wiring (L02)

  Mission: 08
  ```

## Edge Cases

- **Capture tool produces JPG or HEIC, not PNG**: convert to PNG before committing. `magick input.jpg output.png` (ImageMagick) or `sips -s format png input.jpg --out output.png` (macOS). PNGs are preferred — lossless, supports transparency, and is the GitHub-rendering default.

- **Captured PNG is huge (>2 MB)**: GitHub renders fine but the repo grows. If the natural full-page screenshot is e.g. 4 MB, optimize via `pngquant --quality=80-95 input.png --output output.png` or similar. Target ≤500 KB per shot.

- **Dimensions inconsistent across the three shots**: the screenshots look uneven in the README. Recapture with consistent viewport (the visual sanity check during README preview will reveal this).

- **Provider that was configured won't accept connections**: e.g. ollama isn't running locally. Two options: (a) install/start ollama (`brew install ollama && ollama serve && ollama pull qwen2.5:7b`), (b) configure Anthropic / OpenAI with a real key. The chat screenshot REQUIRES a working LLM round-trip so the trace renders.

- **Trace doesn't expand visibly in the Chat screenshot**: F5 landed the per-response trace; verify by clicking the trace indicator on an assistant turn. If still not visible, the demo conversation may need a different prompt that triggers a tool call (try "list files in the current directory" to force a tool execution).

- **Operator can't get the trace expanded just-so**: a non-expanded trace is acceptable as a fallback — the chat-area shot still demonstrates the dialog-clean message stream (F5's primary mission win). Note the deviation in the flight log.

- **`docs/` ends up in `.gitignore`**: verify — current `.gitignore` only excludes `tests/browser/__snapshots__/`, not `docs/`. If something has been added to gitignore since L01 that masks the screenshots, remove the offending line.

## Files Affected

- `~/projects/the-one/docs/screenshots/` — NEW directory containing 3 PNGs
- `~/projects/the-one/README.md` — placeholders → `<img>` tags (3 substitutions, lines 17/19/21 area)

No other files touched. No source code, no tests, no other artifacts.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (Verification Steps grep/file/git commands all passed)
- [x] Operator/FD visually confirmed no data-leak in committed PNGs
- [x] Update flight-log.md with a Leg Progress entry for L02
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md (`[x] screenshots-and-image-wiring`)
- [x] NOT the final leg — flight.md status remains `in-flight`; L03 alignment HAT remains
- [x] Commit all changes (screenshots + README + artifacts) together in a single commit

## Citation Audit

5 code-location citations verified against current code at leg design time:

| Citation | Classification | Notes |
|---|---|---|
| `/README.md:17,19,21` — three `<!-- SCREENSHOT: -->` placeholders | OK | Verified via Read of post-L01 README |
| `/README.md:1-3` — hero image `<p align="center">` wrapper for `gleepglorp_med.png` | OK | Verified at design time — visual centering template that screenshots should match |
| `.gitignore:19` — `tests/browser/__snapshots__/` gitignore entry | OK | Verified during F8 flight design; `docs/` is NOT in `.gitignore` |
| `Makefile:27` — `rebuild-clean` target (wipes DB volume + rebuilds) | OK | Verified during F8 flight design |
| `the_one/agents.md` — `### gated-debug-instrumentation` convention entry landed by L01 | OK | Verified via L01 review (commit `814f8d3`) |

All citations verified clean. No drift.
