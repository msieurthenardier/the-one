# Leg: admin-model-lifecycle

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

Replace the simple model list in the Admin provider editor with a full lifecycle panel for ollama-type providers: VRAM usage summary, per-model loaded/available status, pull with progress bar (SSE), load/unload/delete action buttons. Non-ollama providers keep the existing simple model list.

## Context

- Current Admin provider form (`admin.js` `renderProviderForm`) shows a simple scrollable list of model names after connection test / model fetch
- Leg 03 added backend endpoints: `POST .../models/pull` (SSE), `POST .../models/delete`, `POST .../models/load`, `POST .../models/unload`, `GET .../models/status`
- The existing model list is rendered by `fetchProviderModels()` (admin.js ~line 665-707) which calls `GET /api/providers/{id}/models`
- UI is vanilla JS, dark theme with CSS variables (`--bg: #0a0a0a`, `--surface: #1a1a1a`, `--border: #2a2a2a`, `--fg: #e0e0e0`, `--accent: #4a9eff`)
- Ollama badge color: `#2ecc71` (green) -- use for positive states
- All HTML is constructed in JS (no templates) using innerHTML and DOM manipulation

## Inputs

- `the_one/interfaces/web/static/js/areas/admin.js` -- current provider form and model list rendering
- `the_one/interfaces/web/static/styles.css` -- existing admin CSS patterns
- Backend endpoints from leg 03 for lifecycle operations

## Outputs

- `admin.js` -- enhanced model section for ollama providers with lifecycle panel
- `styles.css` -- new CSS classes for VRAM summary, model status indicators, progress bar, action buttons

## Acceptance Criteria

- [ ] Ollama provider editor shows a "Models" section with two subsections: "Running" (loaded models with VRAM info) and "Available" (all pulled models)
- [ ] VRAM usage summary at top of Models section shows total VRAM used by loaded models (text-based, e.g., "4.1 GB loaded")
- [ ] Each model row shows: name, size (human-readable), loaded/available status indicator, and action buttons (load/unload, delete)
- [ ] "Pull Model" button opens inline input for model name + pull button, shows progress bar during pull via SSE reader
- [ ] Pull progress bar shows percentage and status text from SSE events
- [ ] Load button triggers `/models/load`, shows loading spinner, updates status when complete
- [ ] Unload button triggers `/models/unload`, updates status when complete
- [ ] Delete button shows confirmation prompt, triggers `/models/delete`, removes model from list
- [ ] Non-ollama providers continue showing the existing simple model list (no lifecycle UI)
- [ ] All actions show error feedback on failure (inline error messages, not alerts)
- [ ] UI refreshes model list and VRAM status after each lifecycle action completes
- [ ] No ruff violations (Python unchanged), no JS errors in browser console

## Verification Steps

- `cd ~/projects/the-one && python -m pytest tests/ -x --timeout=30` (ensure no backend regressions)
- Manual: open Admin -> LLM Providers -> edit an ollama provider -> verify lifecycle panel renders
- Manual: pull a model, observe progress bar; load/unload, observe status changes; delete with confirmation

## Implementation Guidance

1. **Add a `renderOllamaModels(providerId, container)` function**
   - Called instead of the simple model list when provider type is `ollama`
   - Fetches both `/api/providers/{id}/models` (available) and `/api/providers/{id}/models/status` (running) in parallel
   - Renders the VRAM summary, running models section, available models section, and pull UI

2. **VRAM usage summary**
   - Text-based summary showing total VRAM used by loaded models (Ollama doesn't report total GPU memory, so no proportional bar)
   - Data comes from `/models/status` -- each running model has `size_vram` field. Sum all `size_vram` values.
   - Format: `{used} GB loaded` with accent color text
   - If no running models: show "No models loaded"
   - If no VRAM data available: show "VRAM info unavailable"

3. **Model rows**
   - Running models: green dot indicator, name, VRAM size (`size_vram`), [Unload] button
   - Available (not running) models: gray dot indicator, name, file size (`size` from `/models` endpoint), [Load] [Delete] buttons
   - Use `escapeHtml` for display text, `escapeAttr` for data attributes on action buttons
   - Size formatting helper: bytes -> "4.1 GB", "780 MB", etc.
   - Action buttons: small, styled like existing `admin-provider-edit-btn` pattern

4. **Pull model UI**
   - "Pull Model" button at top of section
   - Clicking shows an inline row: text input for model name + [Pull] button
   - On pull: use `fetch()` with `ReadableStream` reader to parse SSE lines (EventSource only supports GET, pull is POST)
   - Show progress bar below input: `{status} -- {percentage}%` with filled bar
   - SSE events: `data: {"status": "pulling ...", "completed": N, "total": N}`
   - Handle `{"status": "success"}` terminal event explicitly to trigger model list refresh
   - On error (SSE `{"error": "..."}` event or fetch failure): show error message inline, hide progress bar

5. **Wire action buttons**
   - Each button calls the appropriate endpoint, shows a small spinner/disabled state during the request
   - On success: refresh the entire model panel (refetch both endpoints)
   - On failure: show inline error message near the button

6. **Modify `renderProviderForm` to branch on type**
   - Replace the `fetchProviderModels(provider.id)` call (~line 504) with a conditional
   - If `provider.type === 'ollama'`: call `renderOllamaModels(provider.id, modelsContainer)`
   - If not ollama: keep existing `fetchProviderModels` behavior

7. **CSS additions in `styles.css`** (use `admin-pf-` prefix to match existing convention)
   - `.admin-pf-vram-summary` -- VRAM usage text summary
   - `.admin-pf-model-row` -- flex row for each model (name, size, status, actions)
   - `.admin-pf-model-dot` -- small dot indicator (8px circle, green `.loaded` for running, gray for available)
   - `.admin-pf-pull-progress` -- progress bar container for pull operation
   - `.admin-pf-pull-fill` -- filled portion of progress bar (background: `--accent`)
   - `.admin-pf-pull-input` -- inline input row for model name during pull

## Edge Cases

- **No models pulled**: Show empty state with just the "Pull Model" button
- **No VRAM data from Ollama**: Show "VRAM info unavailable" instead of summary
- **Pull already in progress**: Disable pull button during active pull
- **Model name with special characters**: Escape HTML in all model names (use existing `escapeHtml` pattern)
- **Long model names**: Truncate with ellipsis (CSS text-overflow)

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin.js` -- new `renderOllamaModels`, modified `renderProviderForm`
- `the_one/interfaces/web/static/styles.css` -- new CSS classes for lifecycle UI

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes together (code + artifacts)
