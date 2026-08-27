# Leg: external-credential-studio-ui

**Status**: completed
**Flight**: [External Client Access](../flight.md)

## Objective

Give the operator a Studio panel, on the agent's Self-configuration tab, to manage
external-client access: **grant** a credential (with a copy-once secret reveal + the
surface URL), **list** active grants, **revoke** one, and **rotate** one — all over
Leg 1's already-landed endpoints.

## Context

- Implements the operator-facing half of flight **DD2/DD7** — the mint/list/revoke/
  rotate endpoints exist and are tested (Leg 1); this leg is their UI. No new backend.
- **Additive UI on one established surface.** Mirrors Flight 2's self-configuration
  tab idiom exactly: fetch/callback functions in `areas/studio.js`, wired through
  `agent-editor.js:renderSelfConfigurationTab(panel, agent, callbacks)`, rendered by
  `areas/studio/self-configuration-tab.js`. Same `.editor-section` / `.section-title`
  / `.tool-enable-switch` / relative-timestamp / action-announcement-bridge patterns
  the tab already uses.
- **The copy-once secret is the one sensitivity.** The mint/rotate endpoints return
  the full `ext_<id>.<secret>` token exactly once (Leg 1, AC3/AC5); no read path
  returns it again. The UI must reveal it once, offer a copy affordance, and **never
  persist it** (no `localStorage`, no re-fetch, cleared on the next tab re-render).
- **Risk tier: LOW** (flight pre-tiering) — additive UI over settled, tested
  endpoints, single surface, no auth/gating logic in the client (the server mints,
  scopes, and revokes). The flight-end Reviewer + the crew's Accessibility Reviewer
  cover it; no separate leg-design review (the copy-once handling is display-only, per
  the flight's stated condition).

## Inputs

- Legs 1 & 2 landed: `POST/GET /api/agents/{name}/self-configuration/external-credentials`,
  `DELETE …/{identifier}`, `POST …/{identifier}/rotate` (Leg 1); the surface + tab
  exist.
- `areas/studio.js` self-config callback block (~:1020-1160) — the fetch idiom to
  mirror; `_refreshAgentAfterSelfConfigurationChange(name)` (~:1043) for post-mutation
  re-render.
- `areas/studio/self-configuration-tab.js` `renderSelfConfigurationTab` (~:185) — the
  DOM section idiom (enable section, approval section) to mirror; the
  action-announcement bridge for a11y focus/announce after an action.
- `agent-editor.js` callback wiring (~:199-211).

## Outputs

- Four callbacks in `areas/studio.js`: `mintExternalCredential(name, label)`,
  `fetchExternalCredentials(name)`, `revokeExternalCredential(name, identifier)`,
  `rotateExternalCredential(name, identifier)`.
- Wired through `agent-editor.js` into the tab's callbacks object.
- A new **External access** section in `self-configuration-tab.js`: grant control
  (label input + button), copy-once secret reveal, and a list of active grants with
  revoke + rotate.
- New CSS in `studio.css` if needed (reusing tokens/classes first); new testids
  registered per the existing convention.

## Acceptance Criteria

- [x] **AC1 — Section presence + enablement gate.** When the surface is **enabled**,
      the Self-configuration tab shows an **External access** section with a grant
      control and the active-grants list. When the surface is **disabled**, the grant
      control is disabled (or the section shows a one-line hint that enabling is
      required) and the list is empty — matching the server (mint 409s when not
      enabled; credentials cascade-away on disable).
- [x] **AC2 — Grant + copy-once reveal.** Entering a non-empty label and activating
      **Grant** calls mint and reveals the returned `ext_…` token **once**, together
      with the surface URL, with a copy affordance and a visible "shown once — copy it
      now" warning. The token is not persisted anywhere (no `localStorage`); it is
      cleared from the DOM on the next tab re-render. The new grant then appears in the
      list.
- [x] **AC3 — List is secret-free.** The active-grants list shows, per credential, the
      label, a relative "created" time, and the short identifier — never the secret
      (the list endpoint is secret-free by Leg 1 AC4). No secret text appears anywhere
      in the list DOM.
- [x] **AC4 — Revoke.** Revoking a grant (with a confirm affordance) calls the DELETE
      endpoint and removes it from the list; a subsequent use of that token would fail
      (server-enforced, Leg 1 — the UI just reflects removal).
- [x] **AC5 — Rotate.** Rotating a grant calls the rotate endpoint and reveals the
      **new** token once (same copy-once treatment as AC2); the list shows the grant
      with its new identifier, and the old identifier is gone.
- [x] **AC6 — Validation + errors.** An empty/whitespace label disables or rejects
      Grant with an inline message (no server round-trip). A failed mint/revoke/rotate
      (non-OK response) surfaces a non-throwing inline error in the section, not an
      unhandled rejection.
- [x] **AC7 — Accessibility.** The grant input has a programmatic label; buttons are
      keyboard-operable with visible focus; after grant/revoke/rotate, focus lands
      sensibly (not bounced to page top) and the action is announced via the tab's
      existing action-announcement bridge; the copy-once reveal is announced when it
      appears. Meets the same WCAG 2.1 AA bar the tab already holds.
- [x] **AC8 — Create-mode + tests.** In agent create-mode (`agent` is null) the
      section follows the tab's existing "save first" behavior (no external-access
      actions on an unsaved agent). Browser/DOM tests cover AC1-AC7 following the
      existing `tests/browser/test_studio_self_configuration_*` patterns; `make
      test-unit` and the relevant browser lane are green.

## Verification Steps

- AC1-AC6/AC8: a new `tests/browser/test_studio_self_configuration_external.py` (mirror
  `test_studio_self_configuration_history.py`): render the tab for an enabled agent,
  assert the section + grant flow (mint → token shown once → list updates), revoke
  removes, rotate reveals a new token; assert the disabled-state gate and create-mode
  "save first"; assert no secret appears in the list DOM.
- AC7: extend the a11y checks the existing tab tests use (label association, focus
  landing, announcement), and rely on the flight-end Accessibility Reviewer.
- Lint/format + `make test-unit`; run the browser lane per `scripts/run-tests.sh
  --lane …` for the new browser test.
- **Snapshot note (global rule):** do NOT introduce committed visual-snapshot
  baselines; assert on DOM shape / testids / a11y, not golden images.

## Implementation Guidance

1. **Callbacks** (`areas/studio.js`, mirror the self-config block): `mintExternalCredential`
   POSTs `{label}` and returns `{identifier, label, token, url}` (no agent re-render
   needed — the surface row is unchanged; just re-fetch the list);
   `fetchExternalCredentials` GETs the list; `revokeExternalCredential` DELETEs;
   `rotateExternalCredential` POSTs `…/rotate` and returns the new `{identifier,
   token}`. Each throws `new Error('… : HTTP ' + r.status)` on non-OK, matching the
   existing functions. Do NOT route these through
   `_refreshAgentAfterSelfConfigurationChange` (that re-renders the whole editor); a
   local list re-fetch keeps the copy-once reveal from being torn down before the
   operator copies — the reveal lives until an explicit dismiss or the next full tab
   render.
2. **Wiring** (`agent-editor.js`): add the four callbacks to the
   `renderSelfConfigurationTab` callbacks object, sourced from `callbacks.*` like the
   others.
3. **Section render** (`self-configuration-tab.js`): add an **External access**
   `.editor-section` after the revision-history section. Render the grant control
   (labelled input + `.btn-filled-primary` Grant button), a copy-once reveal region
   (hidden until a mint/rotate returns a token; shows the token in a readonly field +
   a copy button + the warning + the surface URL), and the active-grants list (one row
   per credential: label, relative created-time via the existing `formatTimeAgo`, the
   short identifier, a `.btn-outlined-primary` Rotate and a Revoke control with a
   confirm). Gate on `status.enabled` (AC1) and the create-mode "save first" notice.
4. **Secret hygiene**: hold the token only in the closure/DOM of the reveal region;
   never write it to `localStorage`/`sessionStorage`; clear it on re-render; the copy
   button copies from the readonly field.
5. **A11y**: reuse the tab's action-announcement bridge to announce grant/revoke/rotate
   and the reveal; ensure focus lands on the reveal (after grant/rotate) or the grant
   input (after revoke), never the page top; label the input; visible focus rings.
6. **CSS** (`studio.css`): reuse existing tokens/classes (`.editor-section`,
   `.section-title`, the button classes, `--status-*` tokens); add minimal new rules
   only for the reveal region / list rows, theme-aware and matching the tab's design
   language.
7. **Testids**: follow the existing `self-configuration-*` testid convention (e.g.
   `self-configuration-external-grant-label`, `-grant-btn`, `-token-reveal`,
   `-credential-row`, `-revoke-btn`, `-rotate-btn`); register per the project's
   testid-registry convention.

## Edge Cases

- **Disabled surface** → grant disabled + hint; list empty (server cascade). Re-enable
  → grant becomes actionable; prior grants do not return (they were revoked by the
  cascade — the operator grants fresh).
- **Rotate/revoke a now-stale row** (revoked out-of-band) → the endpoint 404s; surface
  a non-throwing inline error and re-fetch the list.
- **Copy-once reveal not copied** → it stays visible until dismissed or the next full
  tab render; the operator can re-grant if lost (a lost token cannot be re-shown, only
  re-minted — state this in the warning copy).
- **Long label / injection** → render label as text content (never HTML); the input is
  a plain value sent as JSON.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — four callbacks.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — callback wiring.
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` — the
  External access section.
- `the_one/interfaces/web/static/css/studio.css` — minimal new rules if needed.
- `tests/browser/test_studio_self_configuration_external.py` — NEW.
- Testid registry (per the project's convention) — new external-access testids.
- Docs: `SECURITY-MODEL.md` note (external-credential grant UI) — may fold into the
  flight-end doc pass.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` 4507 passed/10 skipped/0 failed; studio browser lane — new external test 8/8, existing self-config tab+history+queue 11/11)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (flight-end review completes it)
- [x] Check off this leg in flight.md
- [x] (Not final leg if the HAT runs — no flight-status change here)
- [x] Do NOT commit (deferred to flight-end review)

## Citation Audit
*(verified against `flight/03-external-client-access` post-Leg-2, 2026-08-27)*

- `areas/studio.js:1020-1160` — self-config fetch/callback block (`fetchSelfConfigurationStatus`,
  `enableSelfConfiguration`, `setSelfConfigurationApprovalMode`, `restoreSelfConfigurationRevision`,
  the `409`-stale handling idiom, `_refreshAgentAfterSelfConfigurationChange`). ✓
- `agent-editor.js:199-211` — `renderSelfConfigurationTab(panel, agent, callbacks)`
  wiring. ✓
- `self-configuration-tab.js:185 renderSelfConfigurationTab`; enable section (~:242),
  approval section (~:260); `formatTimeAgo` (~:106); the action-announcement bridge
  (~:81); testid convention on inputs. ✓
- Leg 1 endpoints: `POST/GET/DELETE/POST-rotate
  /api/agents/{name}/self-configuration/external-credentials[/{identifier}[/rotate]]`
  (landed in this flight's working tree). ✓
