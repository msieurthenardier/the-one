# Leg: settings-api

**Status**: completed
**Flight**: [Administration & Completion](../flight.md)

## Objective
Add a `GET /api/settings` endpoint that returns all configuration values from the Settings singleton.

## Context
- Design decision D1: Settings are read-only display from live `settings` singleton
- The `Settings` class in `the_one/config.py` uses `pydantic_settings.BaseSettings` with fields: `llm_provider`, `llm_model`, `llm_base_url`, `host`, `port`, `data_dir`, `workspace_dir`, `concourse_target`, `concourse_pipeline`
- The `settings` singleton is instantiated at module level (`config.py:40`)
- `data_dir` and `workspace_dir` are `Path` objects that need string serialization
- All other API routes are in `the_one/interfaces/web/api.py` using a shared `APIRouter(prefix="/api")`
- Pydantic V2.11+ deprecates accessing `model_fields` on instances — use the class instead

## Inputs
- `the_one/config.py` — Settings class and singleton
- `the_one/interfaces/web/api.py` — existing API routes

## Outputs
- `the_one/interfaces/web/api.py` — with new `GET /settings` endpoint added

## Acceptance Criteria
- [x] `GET /api/settings` returns JSON with all fields from `Settings.model_fields`
- [x] `Path` values (`data_dir`, `workspace_dir`) serialized as strings, not PosixPath repr
- [x] All existing tests pass (`python3 -m pytest tests/ -x -q`)
- [x] No Pydantic deprecation warnings (use `Settings.model_fields` not `settings.model_fields`)

## Verification Steps
- `curl http://localhost:8081/api/settings` — returns JSON with all settings fields and string paths (requires running server)
- `python3 -m pytest tests/ -x -q` — all tests pass
- `ruff check the_one/interfaces/web/api.py` — no lint errors

## Implementation Guidance

1. **Add imports to `api.py`**
   - Add `from pathlib import Path` to imports
   - Add `from the_one.config import Settings, settings` to imports (import both the class and singleton)

2. **Add the endpoint before the `# ── Tools` section**
   - New section header: `# ── Settings ──────────────────────────────────────────────────────────────`
   - `@router.get("/settings")`
   - `async def get_settings() -> dict[str, Any]:`
   - Iterate over `Settings.model_fields` (the class, not the instance)
   - For each field, get the value from `settings` instance
   - Convert `Path` instances to `str`
   - Return the dict

## Edge Cases
- **Path serialization**: `Path` objects would serialize as `"PosixPath('/home/...')"` by default — must explicitly convert to `str`

## Files Affected
- `the_one/interfaces/web/api.py` — add imports and new endpoint

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
