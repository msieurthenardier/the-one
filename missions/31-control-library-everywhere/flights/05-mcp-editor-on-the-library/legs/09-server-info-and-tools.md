# Leg: server-info-and-tools

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Rebuild the MCP editor's Server section and tools list as DOM-built library controls, updated in place from the cache:
- `section`, `facts`, `disclosure` and `codeBlock`;
- A15 (tool and Instructions disclosures, each description once, field-label sub-labels);
- A16 (facts: Version, Protocol, Offers, Website; the protocol kept, B10).

Keep squawk 0102's repaint and squawk 0010's fail-closed URL handling. Delete the `.mcp-tool-*` and `.mcp-server-*` CSS families.

## Context
- **Flight decisions:** DD7 (A15, A16, B10; ledger rows 15, 16), DD10, DD11 (the families deleted here; `test_ui_disclosure_contract.py:243-259` retired or frozen).
- **Today** (`js/areas/studio/mcp-server-info.js`, 268 lines, all string-built):
  - **`renderToolsListHtml(tools)`:** `details.mcp-tool-item`, whose summary is the name plus " — " plus the description cut to 100 characters, plus a "▸" chevron span. The body has a "Prompt" label with the full description (or "(no description provided)") and an "Input Schema" label with `pre.mcp-tool-schema-content` (or "(no input schema)").
  - **`renderCapabilityFlags`:** "Server supports: **tools, resources, prompts**" (raw keys from `SPEC_CAPABILITY_KEYS`), or "Server announced no capabilities."
  - **`renderServerInfoSection(cache)`:**
    - the section title "Server";
    - an identity row: an icon `img` (src through `App.safeUrl`, dropped on rejection, `alt=""`), the title, the name subtitle (monospace) when it differs, a version line ("v1.4.2 · protocol 2026-07-28"), and the website (a link through `App.safeUrl`, inert text on rejection);
    - the capability line;
    - an Instructions `details` with a "▸" chevron (`mcp-server-instructions`);
    - a Metadata `details` with a `pre` (`mcp-server-meta`).
  - **`syncServerInfoSection(container, cache)`** replaces or inserts the section (the `tmp.innerHTML` sink; squawk 0102's repaint after a Test).
  - **The tools list** is written by `mcp-connection-status.js` (`listEl.innerHTML = renderToolsListHtml(data.tools)`) into `[data-testid=mcp-tools-list]` in the Tools section, which the controller's string builds with its title. Leg 08b stopped clearing it on Test start and empties it on Reset or Forget.
- **The library:**
  - `App.ui.disclosure({variant: 'bordered'|'plain', summary, meta, actions, open, onFirstOpen, testid, summaryTestid, …})`, a native `<details>` whose chevron is drawn by CSS (no "▸" text), its summary text carrying `data-confirm-title`;
  - `App.ui.facts({rows: [{label, value, mono, testid, valueTestid}], testid})` with `set(rows)`;
  - `App.ui.codeBlock({text, trim, maxHeight, label, testid})`;
  - `App.ui.section({title, layout: 'stack', testid})` with `setTitle`.
- **Tests that read these:**
  - `tests/browser/test_flow_studio_mcp_editor.py`: `.mcp-tool-item`/`-summary`/`-schema-content`, `.mcp-server-version-line`, `img.mcp-server-icon`, `.mcp-server-website`, `.mcp-capability-flags`, `.mcp-server-info-section + .mcp-tools-section`, `.editor-section.mcp-tools-section .section-title`, and the `mcp-server-info-section`/`-instructions`/`-meta` testids;
  - `tests/browser/test_mcp_test_connection_button.py` (`.mcp-tool-*`);
  - `tests/browser/test_ui_disclosure_contract.py:243-259` (uses `mcp-tool-item`);
  - `test_flow_studio_library_list.py` (the tools list after a Test).

  Enumerate the exact lines at the start with a grep.

## Inputs
- Leg 08b landed (the status row; the list cleared by Reset or Forget; `mcp-test-status` hidden after a success).

## Outputs
- **`mcp-server-info.js`** becomes `App.studio.mcpEditor.serverInfo.create({cache})`, which returns `{serverEl, toolsEl, update(cache), setTools(tools|null), destroy()}`:
  - **`serverEl`** is an `App.ui.section({title: 'Server', layout: 'stack', testid: 'mcp-server-info-section'})`, hidden when the cache has no server info (`cacheHasServerInfo`):
    - **the identity row:** the icon (`App.safeUrl` fail-closed: no `img` on rejection), the title, and the name subtitle when it differs (A16 keeps the subtitle as body text, not monospace, as the survey asked);
    - **`App.ui.facts`** (A16, B10), with rows only for values present:
      - "Version" (`1.4.2`);
      - "Protocol" (`2026-07-28`, mono);
      - "Offers" ("Tools, Resources, Prompts": the capability keys capitalised, in `SPEC_CAPABILITY_KEYS` order, or "Nothing announced");
      - "Website" (a link through `App.safeUrl`; inert text on rejection; `target=_blank`, `rel="noopener noreferrer"`);
    - **Instructions:** an `App.ui.disclosure({variant: 'plain', summary: 'Instructions', testid: 'mcp-server-instructions'})`. The body is a text block that keeps line breaks (`white-space: pre-wrap` through an owned class, or a `codeBlock` without mono if that is closer to today). No "▸" text (A15);
    - **Metadata:** a plain disclosure (`mcp-server-meta`) holding an `App.ui.codeBlock({text: json, label: 'Metadata', maxHeight})`.
  - **`toolsEl`** is an `App.ui.section({title: 'Tools', layout: 'stack', testid: 'mcp-tools-section'})` holding `[data-testid=mcp-tools-list]`, with the empty hint "Press Test to load this server's tools." (leg 08b's wording) when there are no tools. **It replaces the controller's string Tools section.**
  - **`setTools(tools)`:** one `App.ui.disclosure({variant: 'bordered', summary: name, meta: [short description], testid: 'mcp-tool-item'})` per tool (A15):
    - the summary is the tool name, with the description cut to 100 characters as `meta` (part of the summary's name, with no "▸");
    - the body has two field-label-style sub-labels, "Description" (the full text with line breaks, or "No description provided.") and "Input schema" (an `App.ui.codeBlock` of the JSON, `label: 'Input schema'`, or "No input schema.");
    - **the description shows once:** the summary meta is the short form, and the body holds the full text only when it is longer than the short form (otherwise the body omits "Description");
    - reconciled by tool name through `App.ui.util.syncChildren`, so open tool panels stay open across a Test that returns the same tools.
  - **`update(cache)`:** re-renders the Server section in place (facts `set`, the identity texts, the disclosures' bodies), keeping the section element and any open disclosure open (squawk 0102's repaint, without replacing the node). It replaces `syncServerInfoSection`.
- **The controller and `mcp-connection-status.js`:**
  - the Server and Tools strings are replaced by hosts for `serverEl` and `toolsEl`, in today's order (Server, then Tools; leg 10 applies B1's full order);
  - the status module calls `serverInfo.setTools(data.tools)` and `update(cache)` instead of `listEl.innerHTML` and `syncServerInfoSection`;
  - `destroy` is registered with `mount.onDestroy`.
- **Deleted:**
  - the `.mcp-tool-*` family, `.mcp-capability-flags*` and the `.mcp-server-*` identity, instructions and meta rules in `css/studio.css` (about `:130-337`, re-check), with the stale comment at about `:136-157` gone;
  - `test_ui_disclosure_contract.py:243-259`'s use of `mcp-tool-item`, retired or frozen as a fixture with a reason (the `_legacy_tool_css.py` precedent);
  - any `mcp-tool-*` class left in tests, retargeted to the testids and roles.
- **Guards:**
  - every sink in `mcp-server-info.js` (`tmp.innerHTML`) and the status module's `listEl.innerHTML` goes;
  - the ownership uses (`editor-section`, `section-title` from these strings) go;
  - totals lowered, move entries retired, no new use;
  - `App.escapeHtml` and `App.escapeAttr` calls gone from these files.
- **Testids:**
  - kept: `mcp-server-info-section`, `mcp-server-instructions`, `mcp-server-meta`, `mcp-tools-list`;
  - added: `mcp-tools-section` and `mcp-tool-item` (on the disclosure root), in the registry.
- **Tests:**
  - **A15:**
    - each tool's summary has no "▸" in its accessible name;
    - the short description appears once in the summary, and the full one in the body only when it is longer;
    - the sub-labels are "Description" and "Input schema" in the field-label style (a computed-style check that they match a field label's font size and weight);
    - Instructions is a disclosure, not styled as a section eyebrow;
  - **A16:**
    - the facts rows and their order;
    - "Offers" capitalised;
    - the protocol present (B10);
    - degenerate inputs: no version, no website, an empty capabilities object ("Nothing announced"), no instructions, a rejected website URL (inert text), a rejected icon (no `img`);
  - **squawk 0102:** after a Test the Server section updates in place, and an open Instructions disclosure stays open;
  - **reconciliation:** an open tool panel stays open after a Test that returns the same tools;
  - **squawk 0010:** a `javascript:` website and icon are rejected;
  - the retargeted selectors.
- **Captures:** the connected HTTP and stdio surfaces and `mcp-edit-http-open` into `m31-f5-l09`, compared with the previous set. Differences map to rows 15 and 16 only.

## Acceptance Criteria
- [ ] **A15 and A16** (with B10) as specified, each tested, including the degenerate inputs.
- [ ] **Squawk 0102's repaint** happens in place and keeps open disclosures (tested), and **squawk 0010** fails closed (tested).
- [ ] **No string markup left** in `mcp-server-info.js`; the families are deleted; `git grep -n "mcp-tool-item\|mcp-server-identity\|mcp-capability-flags" the_one/interfaces/web/static/` finds nothing.
- [ ] **Lanes and files pass:** `mcp`, `library`, `contracts-controls` (the disclosure contract, with `THE_ONE_REQUIRE_WEBKIT=1`); `make test-unit` and the static guards.
- [ ] **The captures differ only on rows 15 and 16** (FD-checked).
- [ ] **Guards lowered;** every `mcp-*.js` file at 800 lines or fewer.

## Verification Steps
- `git grep -n "mcp-tool-\|mcp-server-\|mcp-capability" tests/ the_one/interfaces/web/static/` before and after, and run each owning lane (DD10).
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp -x`; `--lane library -x`; `THE_ONE_REQUIRE_WEBKIT=1 … -m browser tests/browser/test_ui_disclosure_contract.py -x`.
- The static guards, then `make test-unit`. The capture compare.

## Implementation Guidance
1. **Tests first** (A15, A16, the in-place repaint, reconciliation, 0010) on the leg 08b tree; record which fail.
2. **The module:** the sections, facts, disclosures and code blocks, then `setTools` with `syncChildren`, then `update`.
3. **The controller and the status module wiring.**
4. **The deletions, the guards, the lanes, the captures and the ledger.**

## Edge Cases
- **A server with 50 or more tools:** the list renders without jank (`syncChildren`). No virtualisation is needed.
- **A tool name with odd characters:** the text goes through text nodes only.
- **A very long instruction text:** it wraps; no horizontal scroll at 1024.
- **The Metadata JSON:** the `codeBlock` with `maxHeight` scrolls, and is keyboard-scrollable when it overflows (the library's behaviour).

## Files Affected
- `js/areas/studio/mcp-server-info.js`, `mcp-connection-status.js`, `mcp-server-editor.js`; `css/studio.css`.
- `tests/browser/test_flow_studio_mcp_editor.py`, `test_mcp_test_connection_button.py`, `test_ui_disclosure_contract.py`, `test_flow_studio_library_list.py` (as grep shows); the guard tables; `docs/ui-testid-registry.md`; the flight log and ledger.

## Citation Audit
- `mcp-server-info.js`: read in full by the FD on the leg 05 tree. The `studio.css` ranges are from the code survey (`:130-224`, `:225-226`, `:233-337`, `:339-350`) and are re-checked at the start, because leg 08b deletes nearby rules.
- The library APIs: `js/ui/disclosure.js:6-24`, `js/ui/page.js:150-210` (header comments). FD grep.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
