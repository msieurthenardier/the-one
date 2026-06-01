# Leg: bug-a-uvicorn-pydantic-reload-docs

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Document Bug A (operations gotcha, not a code defect): under `uvicorn --reload`, editing a **Pydantic class definition** can leave the running worker validating against a stale compiled core schema (a reference to the pre-reload class object survives), so the edit appears not to take effect. Add a short CLAUDE.md note — and minimally correct two now-stale lines in the same section — so the next operator/agent doesn't lose time to it: a worker restart (`docker compose restart the-one`) is the targeted fix.

## Context

- **Bug A lineage**: surfaced during F13 L6 diagnostic walk; confirmed-live in F14 recon. Classified ops/docs — NOT a code fix.
- **COMMITTED container command (design-review confirmed, cite this)**: `docker-compose.yml:18-23` `command:` block runs `uvicorn the_one.interfaces.web.app:app --host 0.0.0.0 --port 8484 --reload --reload-dir /app/the_one` WITH source bind-mounts — this is the committed dev default that runs at `localhost:8484`, NOT an operator-local override (the operator's local `docker-compose.yml` diff only adds 2 env vars). The image-baked default `Dockerfile:36` `CMD ["the-one","serve"]` → `main.py:21` `uvicorn.run(...)` has NO `--reload`. So: image default = no reload; committed compose dev = bind-mount + `--reload` (most host edits DO hot-reload).
- **The phenomenon (precise framing — design review)**: `uvicorn --reload` (watchfiles) restarts the reloader child on file change, so MOST edits do get a fresh import. The gotcha is narrower/intermittent: a Pydantic v2 model compiles a core schema bound to the class object at import; if anything still holds a reference to the *pre-reload* class object (a registry, a cached import, an already-instantiated dependency), validation runs against the STALE schema and your model edit appears not to take effect. Symptom signatures: a `ValidationError` on a field you just added, or a new validator not firing. The cited models (`AgentConfig` `agent/config.py:157`, `Connector` / `ChatSession` `db/models.py`) are Pydantic v2 — they are NOT `frozen=True`; say "compiled core schema bound to the class object," NOT "frozen models." Remedy: `docker compose restart the-one` (targeted — restarts the worker, reloads class objects fresh); `make rebuild` is the always-works hammer.
- **Stale lines to correct (design-review finding; scope decision: YES, fix them — the Bug A note can't be truthful beside false statements)**: CLAUDE.md `:37` ("editing source on the host does NOT update the running app") and `:58` ("live-reload is intentionally NOT enabled") describe the IMAGE-baked `the-one serve` path, but the COMMITTED compose dev setup bind-mounts source + runs `--reload`, so host edits DO propagate and hot-reload. Minimally correct these two lines to distinguish the image-baked default (no reload, `COPY`) from the committed compose dev path (bind-mount + `--reload` → host edits hot-reload), so the section is internally consistent with the new Bug A note. Keep the `make rebuild` guidance intact (it's still correct for image-path / full rebuilds).
- **Doc-only**: no code, no tests.

## Inputs

- `CLAUDE.md:35-60` — `## Local dev with Docker` (the natural home; the `make rebuild` guidance the note complements).
- The committed container command (entrypoint `the-one serve` → uvicorn invocation) — verify whether `--reload` is in the committed default or only the operator's local compose, so the note is accurate.

## Outputs

- A ~5-10 line CLAUDE.md subsection (under `## Local dev with Docker`, or an adjacent Operations note) describing the Pydantic-class-reload gotcha + the full-restart remedy.

## Acceptance Criteria

- [ ] CLAUDE.md gains a concise (~5-10 line) Bug A note under `## Local dev with Docker`: under `uvicorn --reload`, a Pydantic class-definition edit (`AgentConfig` / `Connector` / `ChatSession` / provider config models) can leave the worker validating against a stale compiled core schema; symptom = a `ValidationError` on a just-added field or a new validator not firing; remedy = `docker compose restart the-one` (targeted), `make rebuild` (hammer). Framed as an INTERMITTENT gotcha (most edits hot-reload fine), NOT "every model edit silently fails." Uses "compiled core schema bound to the class object," NOT "frozen."
- [ ] CLAUDE.md `:37` and `:58` minimally corrected to distinguish the image-baked `the-one serve` default (no `--reload`, `COPY`-baked) from the COMMITTED compose dev path (`docker-compose.yml:18-23` bind-mount + `--reload` → host edits hot-reload). The `make rebuild` guidance stays intact. After the edit the section is internally consistent (no statement contradicts the committed compose).
- [ ] The note/corrections are accurate against the committed command (`docker-compose.yml` `command:` block) — not worded as "if your setup has --reload" (it IS the committed default).
- [ ] No code or test changes (doc-only).

## Verification Steps

- Read the rendered CLAUDE.md section — the note is present, accurate, and consistent with the surrounding `make rebuild` guidance.
- `git diff CLAUDE.md` shows only the doc addition.

## Implementation Guidance

1. **Verify the actual container command** before wording the note: check the committed Dockerfile entrypoint / `the-one serve` definition and whether `--reload` is committed-default or operator-local. Word the note to be true for both (the gotcha applies wherever `--reload` is active).
2. **Add the note** under `## Local dev with Docker` (after the "When `make rebuild` is required / NOT required" paragraphs at `:58-60`, or as a short labeled sub-note). Keep it ~5-10 lines. Lead with the symptom (Pydantic model edits not taking effect / stale-schema errors), then the cause (frozen core schema bound to the first-imported class object), then the remedy (full restart/rebuild).
3. Do not restructure the surrounding section; this is an additive note.

## Edge Cases

- **Don't overclaim the failure rate**: `--reload` works for most edits; the Pydantic-class-schema staleness is intermittent (depends on a surviving reference to the pre-reload class object). Frame it as "if a model edit doesn't seem to take effect, restart the worker" — not "model edits never reload."
- **Don't overcorrect `:37`/`:58`**: the image-baked path genuinely has no reload and `make rebuild` is genuinely required for the COPY-baked default — keep that true statement; only add the compose-dev-path distinction so the section isn't self-contradictory.
- **Keep it operator-facing**: dev-loop gotcha, concise and practical.

## Files Affected

- `CLAUDE.md` — +~5-10 line Pydantic-class-reload note.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] CLAUDE.md note present, accurate, reconciled with existing guidance
- [ ] No code/test changes
- [ ] Update flight-log.md with L6 leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)
