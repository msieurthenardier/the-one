# Flight Log: Chat Re-skin + Markdown Hardening

**Flight**: [Chat Re-skin + Markdown Hardening](flight.md)

## Summary

Not yet started.

---

## Leg Progress

---

## Decisions

### No-vendor reversal (mission-level, Flight Director, 2026-07-04)

**Context**: The mission-planning phase wrote a Design Decision to vendor `marked` + `DOMPurify` for the chat markdown pipeline, drawing on Flight-1-era research that assumed the renderer produced an untrusted HTML string needing sanitization.

**Discovery**: The Flight-4 code survey found `markdown.js` is a hand-rolled DOM-building parser — ZERO `innerHTML`, `render()` returns a `DocumentFragment`, literal `createElement` tag names, untrusted data reaching only `textContent`/`createTextNode` + a fail-closed `safeHref()` scheme allowlist, links always `rel="noopener noreferrer"`. XSS is impossible by construction.

**Independent adjudication**: A security-architect review (spawned per the operator's "use independent agents to research, look at best practices, then make the judgement call" directive) recommended **DO NOT VENDOR**, decisively: the classic DOMPurify threat classes (mXSS, parser-differential, DOM clobbering) all require parsing an untrusted HTML string, which this pipeline never does; vendoring `marked` (an HTML-string emitter) + DOMPurify would *worsen* posture by introducing an HTML-string→sanitize→fragment seam (reintroducing the `innerHTML`-class operation the codebase deliberately eliminated) and breaking the streaming fragment/partial-buffer contract, for a CommonMark-completeness gain that is UI-polish, not an impediment.

**Decision**: No library is vendored. The mission's third-party-loosening is NOT exercised. The security intent is delivered structurally: harden `markdown.js`, add a **no-HTML-string invariant guard** (retargeting the mission's "CI integrity verification" from vendored-file hash-pinning to invariant-guarding), and land the required **XSS regression suite** (expanded safeHref + mXSS-payloads-as-text + streaming-boundary tests). Syntax highlighting deferred.

**Rationale for reversal authority**: The operator delegated judgment calls ("make it by using independent agents to research... and ultimately you make the judgement call") and framed the third-party loosening as conditional ("can be loosened if it's an impediment to a good UI"). The existing parser is not an impediment. Reversing a planning DD on ground truth discovered during execution — with independent confirmation and full documentation — is correct Flight Director behavior. Mission constraint annotated (not silently rewritten); original framing preserved as commentary.

**Impact**: Flight 4 is primarily a chat RE-SKIN (the mission's actual outcome) plus markdown hardening, not a parser rewrite. Lower risk, delivers the security intent, respects the operator's supply-chain default.

---

## Deviations

---

## Anomalies

---

## Session Notes
