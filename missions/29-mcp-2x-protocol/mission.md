# Mission: MCP servers connect on the newest protocol

**Status**: active

## Outcome
An MCP server that speaks the newest MCP protocol revision (2026-07-28) connects to the-one on that revision, and its editor says so; every server on an older revision keeps working exactly as it does today, sign-in included.

## Context
The operator's Sonos MCP server moved to protocol 2026-07-28. The-one's MCP client is built on the official `mcp` SDK 1.x, whose newest revision is 2025-11-25 (the last 1.x release is the same), so the client offers 2025-11-25, the server negotiates down, and the MCP editor shows "protocol 2025-11-25". Only the `mcp` 2.x SDK speaks 2026-07-28, and 2.x is a breaking upgrade: a second HTTP client library, snake_case wire types, a new high-level server API, an RFC 9207 issuer parameter on the OAuth callback, and HTTP 401 responses no longer surfaced to the caller — which the-one relies on to start sign-in.

This mission began as sortie planning (2026-10-11) and was escalated when code interrogation showed two separate clusters of design decisions: porting to the new SDK without changing behaviour (including a security-sensitive sign-in redesign), and negotiating the new protocol. The full interrogation is in Flight 1's flight log.

## Success Criteria
- [ ] A server that supports 2026-07-28 connects on it: its MCP editor shows "protocol 2026-07-28", and its tools list and run from an agent's chat. *(behavior-test-backed: the operator's Sonos server)*
- [ ] A server that supports only an older revision (2024-11-05 through 2025-11-25) still connects on its revision, and its tools list and run, over both local (stdio) and remote (streamable HTTP) transports — proven for every older revision on at least one transport and for the newest older revision (2025-11-25) on both — and after its first successful connection it connects with no added delay the operator would notice (under 1 second over today).
- [ ] Signing in to a remote MCP server that requires OAuth still works end to end: the first connection prompts sign-in, the sign-in completes, and the server's tools run afterwards — including against an authorization server that requires the RFC 9207 issuer to be returned. *(behavior-test-backed: Cloudflare's MCP server; issuer check proven against the in-repo OAuth test server)*
- [ ] An agent's self-configuration tools still work, and their refusals still read as a one-line reason.
- [ ] When a server shares no protocol revision with the-one, or a tool asks for input the-one cannot provide, or a single streamed server event exceeds the size cap, the operator sees a plain one-line error — in the MCP editor's Test result and in the chat's tool result — instead of a crash.
- [ ] The Windows packaged build still builds and `the-one doctor` passes in it (the Windows installer-build CI lane).
- [ ] The unit suite and the full browser suite pass; existing tests change only for the SDK's new shapes, and every test whose expected value changes is listed with its reason in the flight log.

## Stakeholders
- **Operator** (sole user): runs MCP servers locally (stdio) and remotely (HTTP, some behind OAuth); wants the newest servers to work at their newest revision without losing anything that works today.

## Constraints
- 2026-07-28 support comes from the official `mcp` SDK, pinned exactly at 2.3.0 (operator decision). 2.3.0 was uploaded 2026-10-02 22:06 UTC; the operator waived the project's 14-day soak for this mission's new packages (2026-10-12).
- ~~The 14-day soak applies to every new transitive package too~~ — waived by the operator for this mission (2026-10-12).
- The client uses the SDK's automatic negotiation: try 2026-07-28 first, fall back to the initialize handshake (operator decision).
- No weakening of the stdio sandbox, the frozen-runtime environment sanitisation, the credential gate, or OAuth token handling.
- Only what the SDK requires moves to its HTTP client library (`httpx2`); the rest of the app stays on `httpx`, and no `httpx` exception handling remains on the SDK path.
- Remote MCP and OAuth requests verify TLS against the operating system's trust store (the SDK HTTP client's default), replacing the bundled certifi list on that path (operator decision, 2026-10-12); recorded in `SECURITY-MODEL.md`.
- Deliberate behaviour changes the 2.x SDK forces, accepted by the operator (2026-10-12), each failing with a plain error rather than being worked around: (1) a 1 MiB cap on a single streamed server event; (2) the MCP connection follows only same-origin, method-preserving redirects; (3) OAuth checks that the authorization server's metadata names the expected issuer, and drops stored credentials recorded for a different one; (4) a 404 before a session exists reads "Not Found" instead of "Session terminated". No other change to older servers' behaviour is intended.
- Work happens in a git worktree (`../the-one-sortie-03`, branch `mission/29-mcp-2x-protocol` and its flight branches); main carries unrelated work in progress.

### Out of scope
New MCP capabilities beyond tools — resources, prompts, subscriptions (including list-changed refresh), and fulfilling input-required requests (elicitation, roots, sampling) — are a future mission. Operator seed for it (2026-10-12): resources → agents can read them, and the MCP editor lists them; prompts → a picker in the chat composer, and the editor lists them; input-required and subscriptions undecided.

## Environment Requirements
- Host-native dev environment (WSL2), repo venv; browser lanes under `THE_ONE_TEST_NETNS=1`.
- A dedicated dev instance (non-8484 port + scratch data directory) for the HAT; the OAuth callback URL must be on that instance's port.
- Network access to the operator's Sonos MCP server and to `https://mcp.cloudflare.com/mcp`, with a Cloudflare account (free tier is enough).
- The Windows installer-build CI lane (Concourse `platform: windows` worker) for the packaged-build criterion; no hands-on Windows run (operator decision: the dev instance suffices for the HAT).

## Open Questions
- How does the-one detect "this server wants sign-in" now that the SDK no longer surfaces HTTP 401 and its `WWW-Authenticate` header? (Flight 1)
- Are the self-configuration refusals raised as the SDK's `ToolError` (and do the write tests that expect `ValueError` change), or as a class that is both? (Flight 1)
- Does the-one call the SDK's private `negotiate_auto` under the exact pin, or rebuild the same policy from the public `discover()`/`initialize()`? (Flight 2)
- How does the auth-posture probe classify a server that only speaks 2026-07-28 and rejects a bare `initialize`? (Flight 2)
- What do real third-party servers on older revisions do when probed with `server/discover` — reply with an error (fast fallback), drop it (10-second fallback), or close a stdio pipe (no fallback)? Is the negotiated era remembered per source? (Flight 2)

## Known Issues

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: Port to the `mcp` 2.x SDK at parity — every server connects exactly as before on the initialize handshake; the SDK-forced changes land (SDK HTTP path on its new client library, snake_case wire types with alias-preserving caches, era-agnostic reads of the negotiated revision and server metadata, sign-in detection redesign, RFC 9207 issuer through the OAuth callback, self-configuration and test servers on the new server API with one-line refusals preserved, soak floors, packaging collection and the Windows build lane); live sign-in check against Cloudflare.
- [ ] Flight 2: Automatic negotiation of 2026-07-28 — try the newest revision, fall back to the handshake without a noticeable delay; the editor shows the negotiated revision; plain errors for no shared revision, input-required and oversized events; older-revision fixtures; HAT against the Sonos server and a re-run of the Cloudflare sign-in under negotiation.
