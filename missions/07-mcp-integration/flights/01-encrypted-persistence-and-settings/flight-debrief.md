# Flight Debrief: Encrypted MCP Source Persistence + Settings Page

**Date**: 2026-05-05
**Flight**: [Encrypted MCP Source Persistence + Settings Page](flight.md)
**Status**: landed
**Duration**: 2026-05-05T21:40:00Z – 2026-05-05T23:55:00Z (~2h 15m of compute time across 6 legs)
**Legs Completed**: 6 of 7 (L7 HAT deferred per flight adaptation criteria)

## Outcome Assessment

### Objectives Achieved

The flight landed the storage layer and operator-facing Settings page for MCP server definitions, exactly as scoped:

- **Schema v10 migration** rebuilt `mcp_sources` with field-segregated encryption (plaintext `config` + Fernet-encrypted `secrets` columns) and renamed the deprecated `'sse'` literal to `'streamable-http'` via CASE-WHEN-in-SELECT during the table-rebuild ceremony.
- **Encryption pipeline** extended in one pass: `MCPSourceRepository` Fernet-encrypts the secrets blob; the `/api/encryption/rotate` endpoint atomically re-encrypts both LLM provider api_keys AND MCP source secrets in a single crash-safe transaction with no non-DML statements between the first SELECT and the final commit.
- **HTTP surface**: `/api/mcp-sources` CRUD endpoints gain transport-aware validation (`_validate_mcp_source_config` with stdio/streamable-http branches and a defensive exhaustiveness `else: raise`), per-decoded-VALUE masking on GET responses, per-key `__MASKED__` sentinel handling on PUT, and a new `/api/mcp-sources/types` endpoint registered before `/{source_id}` per the route-ordering invariant.
- **Settings UI**: a 4th "MCP Servers" Settings sidebar entry; the closure-mirror enumeration in `admin.js` extended at all 18 touchpoints (parallel to providers); a new `mcp-servers-grid.js` sub-module; a new `mcp-server-editor.js` sub-module with transport-aware fields, a unified key/value table with per-row sensitive checkbox (the deferred design decision LOCKED at option c), an OAuth client config sub-section, per-key `__MASKED__` round-trip preservation, and bare `App.confirmDelete` (no agent-usage pre-gate — deferred to F4).

Verification: 1099 unit tests (+33 net new MCP-related) passing; 47/48 admin+mcp browser sweep (1 unrelated pre-existing F6 failure documented out-of-scope); `make lint` clean.

### Mission Criteria Advanced

This flight contributes to the following M07 success criteria:
- ✓ Operator can register / edit / remove MCP server definitions through a Settings surface that follows the existing design language and admin patterns (Studio Settings sidebar; M06 section-nav primitive)
- ✓ Sensitive configuration fields persisted in encrypted form using the same key + rotation pipeline that protects LLM-provider credentials
- ✓ Credentials never appear in plaintext outside the encryption boundary (no plaintext in API responses, logs, inspector trace pane); existing edit-form sentinel pattern preserved (per-key generalization)
- ✓ The Settings MCP section meets the M04/M06 design-language quality bar without alignment-flight rework (F1's contribution to the "design-language quality bar" criterion; the simplified inspector and Studio MCPs tab are F6/F8 contributions)

The mission's encryption-granularity Open Question is now permanently closed: field-segregated, two-column storage with per-key `__MASKED__` semantics on the dict.

## What Went Well

**Architecture**: the field-segregated encryption decision held up cleanly across all 6 legs without revision. The two-column storage (`config TEXT DEFAULT '{}'` + `secrets TEXT DEFAULT '{}'` Fernet-encrypted) is short, auditable, and gives the admin grid free non-decrypt rendering of plaintext fields like command/URL. The MCP storage shape now sits cleanly next to the LLM provider storage shape — both Fernet-encrypted but different content (single-column string vs JSON dict blob), with the MCP version representing a clean generalization of the provider pattern (per-key `__MASKED__`, migration-residue tolerance).

**All-in-memory rotation invariant**: best-executed decision in the flight. Code at `api.py:1294-1403` is structurally clean — SELECT both tables → re-encrypt all in memory → single `try:` block with both UPDATE loops → single `commit()` → file replace. The "no non-DML between SELECT and commit" rule (originally a v8 schema-migration constraint) extended to the rotation endpoint without surprises. `test_rotate_dual_surface_atomicity_on_db_failure` proves the single rollback covers both tables atomically.

**Defensive exhaustiveness**: `_validate_mcp_source_config`'s final `else: raise` (`api.py:616-628`) is dead code today (Pydantic Literal validation gates the type) but locks the contract that any future transport literal addition must extend the helper. Architecturally correct dead code worth promoting to a project-wide convention.

**Closure-mirror enumeration**: the L5 leg artifact enumerated all 18 touchpoints in `admin.js` up-front; the implementer worked through them as a checklist with zero closure-state leakage. The pattern has now landed three times (providers, tools, mcp-sources) and is genuinely repeatable. L5 deliberately upgraded the stale-then guard from the older providers pattern to the stricter tools pattern (cache-write inside the guard) — a strict improvement.

**CASE-WHEN-in-SELECT migration**: novel for this codebase (no in-codebase precedent for the CASE pattern in a value transformation); landed cleanly on first run with all 4 v10 tests passing including the v9-fixture row-preservation test that exercises the CASE branch directly.

**Per-key `__MASKED__` semantic**: the L3 generalization of the provider single-column `__MASKED__` to per-key dict handling is a clean extension. The L6 editor's per-row `_originalMasked` capture (via `data-original-masked` HTML attribute) makes round-trip preservation verifiable by masked-tail-equality after edit — `test_edit_streamable_http_source_changes_one_secret` proves change-one-leave-one works correctly.

**Test coverage discipline**: ~40 new tests (4 + 5 + 10 + 5 + 7 browser + 9 browser) with strong assertion quality. Spot-checks confirmed every new test asserts at least one positive AND one negative invariant (e.g., per-decoded-VALUE mask shape PLUS `not in resp.text` plaintext absence). Failure-path tests (rotation commit-failure, atomicity-on-failure, migration-residue) are exemplary.

**Documentation contracts captured**: `CLAUDE.md` and `agents.md` updated by the commit step with all four key contracts: field-segregated encryption, per-key `__MASKED__`, all-in-memory rotation invariant, OAuth `client_secret` payload-key routing. Spot-checked and verified accurate.

**Citation hygiene improving**: design reviews caught citation drift in L4 (stale `repositories.py:489`) and L6 (post-L5 line drift); fixes were applied before implementation. Anchor-by-symbol-name became the preferred pattern for late-flight legs.

**Adaptation criteria honored**: L7 HAT walkthrough deferred per the flight spec's explicit adaptation criteria. The right call given L1-L6 landed cleanly with no HAT-class issues surfaced.

## What Could Be Improved

### Process

- **L1→L2 "leg lands red, next leg lands green" anomaly is a methodology smell.** L1 deliberately left two tests failing (`tests/test_db_repositories.py:230,244`) because the L1 schema rejected `'sse'` but the Pydantic Literal still allowed it; L2 fixed both as part of "Update sites" work. The flight log captured this cleanly (Anomalies §L01) — but agentic-workflow's "leg's tests pass" gate is muddied by intentional partial-flight breakage. **Recommendation**: future leg breakdowns of this shape should either (a) bundle the test-fix into the producing leg with a comment "blocks N+1 model literal change but consistent with that change," or (b) explicitly mark the leg as "leg lands red, next leg lands green" with that as a first-class methodology pattern in `agentic-workflow.md`.

- **L6 was significantly larger than estimated** (867 lines of editor JS vs the leg's 600–750 estimate; +280 lines of test code on top). Single leg landed cleanly, so the size was livable, but the design-review cycle had to address a large surface in one pass. **Recommendation**: at the leg-design phase, when the estimated LOC exceeds 500 in a single new file, default to splitting (e.g., L6a kv-table+transport-aware fields / L6b OAuth section+dirty/save/delete plumbing).

- **Citation drift across legs as the file evolves**. L4's leg artifact cited `LLMProviderRepository.encryptor` at line 489 (the L2 leg's stale citation, propagated forward). L6's leg artifact's pre-L5 line citations needed correction at design review. The leg artifacts at `repositories.py:252-254` (a code comment) still cite the stale `:489`. **Recommendation**: every leg artifact's "Inputs" section should anchor by symbol/string (e.g., `LLMProviderRepository.__init__`) rather than line number. Some L1-L3 leg artifacts did this well; L4-L6 had drift residual that survived even after design-review fixes.

- **Pre-existing lint baseline carried forward through 4 legs.** 4 ruff failures inherited from L1-L4 (3 from this flight's earlier legs + 1 from main) accumulated through the flight without correction. They were caught at the flight-end Reviewer pass but should have been gated leg-by-leg. **Recommendation**: agentic-workflow's per-leg checklist should include `make lint` clean (or "no NEW ruff errors") as a pre-`[HANDOFF:review-needed]` gate.

### Technical

- **`_MASKED_API_KEY_SENTINEL` constant name is now misleading post-L3.** It's reused at four call sites and covers BOTH single-column `llm_providers.api_key` AND per-key `mcp_sources.secrets[*]`. Cosmetic debt; rename to `_MASKED_SENTINEL` should land before F5 (3rd reuse site). 5-minute refactor.

- **Transport literal `"streamable-http"` duplicated at 5 sites** (the flight log called this 3): `models.py:55` (Pydantic Literal — the real source of truth), `schema.py:380` (CHECK constraint), `api.py:648-651` (`/types` endpoint), `api.py:557,577` (`_validate_mcp_source_config` branches), `mcp-servers-grid.js:28` (`KNOWN_TRANSPORT_BADGES`). A `TRANSPORTS` module-level tuple in Python derived via `typing.get_args(MCPSource.model_fields['type'].annotation)` would consolidate 3 of the 5 sites; the JS already fetches from `/api/mcp-sources/types` cleanly. **Defer to F2** if F2 contemplates adding a transport literal; routine-maintenance candidate otherwise.

- **Migration-residue tolerance duplicated across 2 sites**: `MCPSourceRepository._ciphertext_to_secrets` (`repositories.py:259-281`) AND `rotate_encryption_key` (`api.py:1338-1349`) both swallow `InvalidToken` and treat as `{}`. A shared helper (e.g., `Encryptor.decrypt_or_empty(ciphertext)`) would unify them. Mild debt; surfaces if a third site (F5 OAuth flow?) needs the same logic.

- **L6 editor at 867 lines is ~2x `provider-editor.js`'s 451**. Some growth is justified (per-key MASKED, kv-table partitioning, OAuth section, type-driven field swap), but a fraction is structural near-duplication. **Future routine-maintenance candidate**: extract a `KvTableEditor` helper into `tools-form-helpers.js` once a third consumer materializes — likely F8's Studio MCPs override panel.

- **Closure-mirror dirty-gate `inEditor` expression grows linearly with sections.** Currently 3 disjuncts (`providers && providerFormMode || tools && toolFormMode || mcp-sources && mcpSourceFormMode`). A `defineAdminSection(spec)` registry would eliminate the manual extension. **Defer** until 5th section lands; premature now.

### Documentation

- **Concurrent-write-during-rotation race not documented.** L4 leg artifact marks it explicitly out-of-scope but neither `CLAUDE.md` nor `agents.md` carry the limitation forward. F2/F4 will introduce code that may write to `mcp_sources` more frequently — without a documented mutex/coordination contract, a future regression has no prior-art to point to. **Add a one-line note to `agents.md` under the rotation paragraph: "Rotation is operator-triggered, manual, infrequent; concurrent `/api/mcp-sources` writes during rotation are an acknowledged race (no mutex)."**

- **L6 stranded-secret edge case implemented but untested.** `mcp-server-editor.js:859-863` emits `secrets["oauth_client_secret"] = ""` when the operator clears all OAuth fields, dropping the dangling ciphertext. Without a regression test, a future refactor that drops this clearing logic would silently leave stranded ciphertexts. **Add `test_edit_clears_oauth_drops_stranded_secret` to `tests/browser/test_flow_admin_mcp_editor.py`** — ~25 lines.

- **Real-corruption `JSONDecodeError` propagation untested.** `_ciphertext_to_secrets` and `rotate_encryption_key` both explicitly let `JSONDecodeError` propagate (real corruption surfaces, doesn't get silently masked). No test exercises this path. **Add a unit test in `TestMCPSourceRepository`** that writes `secrets = encryptor.encrypt("not-json")` directly and asserts `repo.get(sid)` raises `JSONDecodeError`. ~10 lines.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L4 LLMProviderRepository.encryptor citation `:489` (stale) corrected to `:530` mid-design-review | L4's leg-design review caught the stale citation; the L2 leg had already used `:489` as a comment in `repositories.py` itself, propagating the staleness | No — but anchor-by-symbol convention should be standardized for leg artifacts (see Process recommendations) |
| L5 `fetchMcpSources` adopted the stricter tools-pattern stale-then guard (cache-write inside the guard) instead of the older providers pattern | The providers pattern has a known race window where a stale fetch resolving after navigation clobbers `providers = data` even though the populate short-circuits | Yes — a future routine-maintenance pass should retroactively bring providers up to this stricter pattern |
| L6 estimated 600–750 LOC, landed at 867 | Per-row MASKED capture, delegated event handlers, three-walk snapshot, type-routed payload assembly, OAuth section, stranded-secret cleanup all added incremental complexity | No — but threshold for "split a leg at design phase" (recommended ~500 LOC for a new file) should inform future single-file leg sizing |
| Pre-existing lint baseline of 4 ruff errors carried through L5 → cleaned up at flight-end | Per-leg lint gating not enforced; only flight-end Reviewer caught the 4 | Yes — agentic-workflow per-leg checklist should add a "no NEW ruff errors" gate before `[HANDOFF:review-needed]` |

**No design-level deviations.** All 7 flight design decisions held up without revision through the 6-leg implementation. Zero entries in the flight log's "Decisions" or "Deviations" sections after landing.

## Key Learnings

1. **The migration-residue tolerance is its own contract** that has to be honored at every site that decrypts MCP secrets — not just the repository. L4 had to mirror it independently. Future encrypted-storage migrations should design the residue-tolerance helper as a single shared utility from the start.

2. **The closure-mirror enumeration in admin.js is BIG (18 touchpoints) but predictable.** It survived L5 cleanly because the leg artifact enumerated all 18 in advance. The cost of getting one wrong is silent state leak between categories.

3. **`merged_config()` may not be the right primitive for stdio env-var assembly.** F2 design must spell out the assembly shape — `secrets[key]` overlays onto `config.env[key]`, both flatly merged into the spawned process's environ — rather than blindly consume `merged_config()`. The current flat-merge implementation works for the OAuth client_secret top-level key (where it lives at `secrets["oauth_client_secret"]`) but doesn't naturally handle the nested `config.env` ↔ `secrets` env-var-name overlay.

4. **The CASE-WHEN-in-SELECT pattern is reusable.** Clean, in-codebase precedent now exists for the next "rename a literal in a CHECK-constrained column" migration, of which there will likely be at least one more (e.g., the `LLMProviderConfig.type` literal grows over time).

5. **Defensive `else: raise` exhaustiveness checks on Pydantic Literal dispatch are zero-cost contract locks.** Worth establishing as a code-review convention. The pattern: every `if x.type == ... elif x.type == ...` chain over a Pydantic Literal MUST end with an `else: raise HTTPException(...)`. Catches future transport-literal additions that forget to extend the dispatch.

6. **Runtime OAuth token slots were NOT pre-landed despite the F1↔F5 column-shape contract claim** at `flight.md:49`. The contract was honored in spirit (F5 needs no schema migration because `secrets` is a free-form dict) but not in letter (no F1-side test or comment locks the F5-writer-can-add-`access_token`-etc.-keys invariant). F5's leg design must re-confirm this and add the writer code without expecting any L1/L2 plumbing.

## Recommendations

1. **F2/F4/F5 contract consumption (critical, forward-looking)**: F2 must consume `merged_config()` AND clarify env-var assembly shape; F4 must add agent-usage pre-gate to L6's delete path (the bare `App.confirmDelete` is deliberately deferred); F5 must look up the locked `secrets["oauth_client_secret"]` payload key by exact name. All three contracts captured in `CLAUDE.md` and `agents.md`; downstream flight design should re-confirm during their respective Phase 1b reconnaissance passes.

2. **Add three missing test cases as routine maintenance** before F5 lands: (a) L6 stranded-secret browser test (~25 LOC), (b) JSONDecodeError propagation unit test (~10 LOC), (c) concurrent-write-during-rotation documented limitation in `agents.md` (~1 line). All three are low-cost, high-leverage regression nets.

3. **Codify the closure-mirror enumeration pattern**: either document the 18-touchpoint shape in `agents.md` or `.flightops/PATTERNS.md`, OR extract a `defineAdminSection(spec)` helper that takes `{id, label, fetch, render, hydrate, serialize}` and registers all 18 touchpoints from a single description. High ROI when the next admin section lands (likely F8's Studio attach panel or a future inspector).

4. **Establish a per-leg lint gate in agentic-workflow methodology**: add `make lint` clean (or "no NEW ruff errors") to the per-leg post-completion checklist BEFORE `[HANDOFF:review-needed]`. This flight accumulated 4 lint errors across L1-L4 that were only caught at flight end — a per-leg gate would have surfaced each at the producing leg.

5. **Adopt anchor-by-symbol-name convention for leg-artifact citations**: in the "Inputs" section of every leg artifact, prefer `MCPSourceRepository.__init__` over `repositories.py:249-253`. Line numbers drift; symbols don't. This flight's later legs (L4-L6) had to correct citation drift mid-design-review — anchor-by-symbol would have eliminated that whole class of fix.

## Action Items

- [ ] **F5 leg design (when F5 starts)**: explicitly cover the runtime OAuth token slots gap. Re-affirm the F1↔F5 column-shape contract OR add F5-side writer tests that lock the `secrets["access_token"]` / `["refresh_token"]` / `["token_expires_at"]` keys.
- [ ] **F4 leg design (when F4 starts)**: spec out the agent-usage pre-gate for the L6 delete path. Mirror `provider-editor.js`'s pre-gate fetch + sibling banner pattern.
- [ ] **F2 leg design (when F2 starts)**: confirm env-var assembly shape (do NOT blindly consume `merged_config()` for stdio env vars). Spell out exactly how `secrets[key]` overlays onto `config.env[key]` for the spawned process's environ.
- [ ] **Routine maintenance (any flight in this neighborhood)**: rename `_MASKED_API_KEY_SENTINEL` → `_MASKED_SENTINEL` (4 sites in `api.py`); update the stale `LLMProviderRepository:489` comment in `repositories.py:252-254` to `:530`; add `agents.md` line about concurrent-write-during-rotation race.
- [ ] **Routine maintenance**: add `test_edit_clears_oauth_drops_stranded_secret` browser test (~25 LOC).
- [ ] **Routine maintenance**: add JSONDecodeError propagation unit test in `TestMCPSourceRepository` (~10 LOC).
- [ ] **Methodology improvement (mission-control)**: consider adding "no NEW ruff errors" to the per-leg `[HANDOFF:review-needed]` gate in `.claude/skills/agentic-workflow/SKILL.md`.
- [ ] **Methodology improvement (mission-control)**: consider documenting the "leg lands red, next leg lands green" pattern as first-class in `.claude/skills/agentic-workflow/SKILL.md` if the L1→L2 anomaly shape is expected to recur (likely yes for "schema migration → model update" flight shapes).
- [ ] **Methodology improvement (mission-control)**: consider documenting the closure-mirror enumeration shape in `.claude/skills/leg/SKILL.md` as a reference for "adding a new admin/UI section" leg type.
- [ ] **L7 (HAT) follow-up**: optional, deferred. User can opt into the HAT walkthrough as a follow-up to validate the new MCP Servers UI experientially. Operator path: empty-state CTA → create stdio source with mixed sensitive/non-sensitive env vars → edit one without retyping the secret → trigger key rotation → verify decrypt still works → delete with confirm.
