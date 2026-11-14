# Leg: studio-vram-warnings

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

Add inline VRAM warnings in the Studio agent editor when the selected model on an ollama provider may not fit in available VRAM.

## Context

- Studio renders a provider dropdown (`#studio-provider`) and model input with datalist (`#studio-model`)
- When provider changes, `fetchModelsForProvider()` fetches available models and populates the datalist
- The `allProviders` array contains provider objects with `id`, `name`, `type` fields
- Backend provides: `GET /api/providers/{id}/models/status` (running models with `size_vram`) and `GET /api/providers/{id}/models` (available models with `size`)
- `ollama_api.show_model` and `estimate_vram` exist in the backend but there's no per-model VRAM estimate endpoint yet -- we can use the `size` field from `/models` as a proxy (file size approximates VRAM need)
- The flight spec says: "fetch VRAM status and model info, show inline amber warning when estimated model size exceeds available VRAM"
- Only ollama providers get VRAM warnings -- other types are unaffected

## Inputs

- `the_one/interfaces/web/static/js/areas/studio.js` -- model selection UI (~lines 235-351)
- `the_one/interfaces/web/static/styles.css` -- existing CSS patterns
- Backend endpoints: `/api/providers/{id}/models/status`, `/api/providers/{id}/models`

## Outputs

- `studio.js` -- VRAM warning logic on model selection for ollama providers
- `styles.css` -- warning banner styling

## Acceptance Criteria

- [ ] When user selects/types a model for an ollama provider, fetch VRAM status and check available memory
- [ ] Show inline amber warning below the model input when the model's estimated size exceeds available VRAM: "This model requires ~X GB VRAM, Y GB available -- may cause performance issues"
- [ ] Warning does not block selection -- user can still proceed
- [ ] Warning clears when model changes to one that fits, or when provider changes
- [ ] No warning shown for non-ollama providers
- [ ] Warning text uses human-readable sizes (e.g., "4.1 GB", "780 MB")
- [ ] No JS errors, no ruff violations

## Verification Steps

- `cd ~/projects/the-one && python -m pytest tests/ -x --timeout=30`
- Manual: Studio -> select ollama provider -> select a large model -> verify warning appears
- Manual: switch to non-ollama provider -> verify no warning

## Implementation Guidance

1. **Determine if selected provider is ollama**
   - In the model input change/input handler, look up the selected provider in `allProviders` by ID
   - If `provider.type !== 'ollama'`, clear any existing warning and return

2. **Fetch VRAM data on model selection**
   - When model input changes (debounce ~500ms to avoid excessive requests), fetch:
     - `GET /api/providers/{id}/models/status` -- running models with `size_vram`
     - `GET /api/providers/{id}/models` -- all models with `size` (file size as VRAM proxy)
   - Calculate: total VRAM in use = sum of `size_vram` from running models
   - Find selected model in the models list, get its `size` as estimated VRAM need
   - If model `size` > available VRAM (total minus in-use, or just compare to model size since we don't know total GPU memory -- simplify to: warn if model size > threshold or if already-loaded models + this model would be large)

3. **Simplified warning logic**
   - Since Ollama doesn't report total GPU VRAM, use a simpler approach:
   - Fetch `/models/status` to see what's loaded and their `size_vram`
   - Fetch `/models` to get the selected model's `size` (file size)
   - If the model is already loaded (appears in running list): no warning needed
   - If the model is NOT loaded and its file size is large (> sum of available size_vram of currently loaded models): show warning
   - The warning is informational, not a precise calculation -- "This model requires ~X GB. Currently Y GB loaded across Z models."

4. **Add warning element**
   - Add a `<div class="studio-vram-warning">` after the model input wrapper
   - Initially hidden, shown when warning applies
   - Amber/yellow styling: border-left with amber color, muted text

5. **Wire the event**
   - Listen on the model input for `change` and `input` events (debounced)
   - On provider change: clear the warning
   - Only fire VRAM check when provider is ollama-type

6. **CSS in styles.css**
   - `.studio-vram-warning` -- amber border-left, padding, muted amber text, hidden by default
   - `.studio-vram-warning.visible` -- display block

## Edge Cases

- **Model not in list**: User can type arbitrary model names -- if not found in fetched models, skip warning (can't estimate)
- **Provider has no models**: No warning needed
- **Network error fetching VRAM status**: Silently skip warning (don't break the flow)
- **Rapid model changes**: Debounce prevents excessive API calls

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` -- VRAM warning logic
- `the_one/interfaces/web/static/styles.css` -- warning styling

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes together (code + artifacts)
