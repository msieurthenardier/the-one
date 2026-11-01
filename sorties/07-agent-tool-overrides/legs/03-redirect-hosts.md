# Leg: redirect-hosts

**Status**: completed
**Flight**: [Agent tool overrides](../flight.md)

## Objective
Make every request a web tool sends, including each redirect hop, obey the tool's effective Allowed hosts and Denied hosts exactly as the first URL does, without breaking a relative redirect on a host the transport has pinned to an IP.

## Context
- Flight design decision **DD15** is the spec; read it in `../flight.md` in full (and criterion 5 of the charter). The flight log's planning notes record Architect review 2's reproduction of the relative-`Location` failure that the pin-on-a-copy fix prevents.
- **Leg 1 delivered** `NO_HOSTS` and made `_url_check` (`_web_config.py:337-367`) refuse every host when the allow list holds it, before any DNS; `host_allowlist` now carries `NarrowAnyWhenEmpty`. This leg factors the host part of `_url_check` out and reuses it in the transport.
- **Today:** `_url_check` runs once per tool call, on the first URL (`web.py:176,274,404`). `SSRFGuardedTransport.handle_async_request` (`_web_config.py:495-546`) runs on every request (httpx sends each redirect hop through the transport, streaming included), but checks only the SSRF block list and `extra_allowed_hosts`. It pins by mutating the caller's request in place (`request.extensions = {..., "sni_hostname": ...}`, `request.headers["Host"] = ...`, `request.url = request.url.copy_with(host=ip)`, `:527-537`). httpx then builds the next hop from that same request object, so a relative `Location` resolves against the IP.
- **Host forms differ:** `_url_check` reads `urlparse(url).hostname` (lowercased, `xn--` kept as given); the transport reads `request.url.host`, which httpx decodes to Unicode. One normaliser is used by both.
- **Callers:** the three web tools' `_build_transport(cfg)` (`web.py:152,262,385`) receive the tool's resolved, effective `WebConfig` (agent override applied, clipped since leg 1) and pass only `extra_allowed_hosts` today. The search backends (`_search_backends.py:238,303`) build the transport with `extra_allowed_hosts` only; they call fixed engine hosts and stay unchanged.
- **Release notes:** there is no unreleased notes file (`docs/releases/` holds one file per shipped version), so this leg's release-notes line goes into the flight log's "Release notes to carry" list, and leg 5 (`notice-surfaces`, DD14) assembles them.
- **Baseline:** the flight log's list; legs 1-2 and the drawer fix are uncommitted in this tree and are part of this leg's base.

## Inputs
- `the_one/tools/_web_config.py`: `_url_check` `:337-367`; `_host_matches` `:443-450`; `SSRFGuardedTransport` `:453-546` (`__init__` `:484-493`, `handle_async_request` `:495`).
- `the_one/tools/web.py`: `_build_transport` `:152-156`, `:262-266`, `:385-390`; their call sites `:177`, `:275`, `:406`; the `ConstraintError` handlers (`:230`, `:348`, `:441-444`) that turn a refusal into `[error] [constraint] …`.
- Test seams: `tests/test_web_helpers.py::_patch_super_dispatch` (`:336-349`) and `::_patch_getaddrinfo` (`:352-368`), which run the production transport with the network replaced. `tests/test_web_tools.py` monkeypatches `_build_transport` with `httpx.MockTransport`, which bypasses the transport by design.

## Outputs
- `_web_config.py`:
  - `normalize_host(host) -> str`: the ASCII form httpx itself dials.
    - The trailing root dot is stripped, then the host is lowercased and derived through `httpx.URL(f"http://{host}/").raw_host`, which applies the `idna` package's IDNA 2008/UTS 46. This matches what the transport connects to; the stdlib `idna` codec (IDNA 2003) would map `ß.de` to `ss.de`, a different host than httpx sends, and so weaken both lists. No new dependency: httpx is already one.
    - An IP literal (v4, or v6 with brackets stripped) is returned unchanged.
    - A host httpx refuses (`httpx.InvalidURL`, or `UnicodeError` and its `IDNAError` subclass: an empty label, a label over 63 characters) raises `ConstraintError`.
  - `_host_policy_check(host, host_allowlist, host_denylist)`: raises `ConstraintError` for `NO_HOSTS`, not-in-allow, or in-deny, comparing normalised forms on both sides. `_url_check` calls it, so its messages are unchanged for the first URL.
- `SSRFGuardedTransport`:
  - Gains optional `host_allowlist=()` and `host_denylist=()`.
  - `handle_async_request` runs `_host_policy_check` on `request.url.host` first, before the IP-literal branch, `extra_allowed_hosts` and resolution.
  - It pins on a **new** `httpx.Request` for the IP URL, carrying the method, a copy of the headers **as they are**, the same stream, and the extensions plus `sni_hostname` set to the normalised ASCII host. That request goes to `super()`, and the caller's request is never mutated.
  - The headers are not edited: `Request._prepare` already set `Host` to the original netloc (punycode, with a non-default port), and httpx's `_redirect_headers` gives a cross-origin hop a fresh one. Today's `request.headers["Host"] = original_host` (`_web_config.py:531`) drops the port and writes the Unicode form for an IDN host; this leg removes it.
  - httpcore passes `sni_hostname` as `server_hostname`, which needs ASCII; today it gets `request.url.host`, the Unicode form.
- `web.py`: each `_build_transport(cfg)` passes `cfg.host_allowlist` and `cfg.host_denylist` as well.
- Tests (below). The flight log gains the release-notes line.

## Acceptance Criteria
- [ ] **AC1 — hops obey the lists.** Through the real transport under a real `httpx.AsyncClient(follow_redirects=True)` (network replaced by `_patch_getaddrinfo` and `_patch_super_dispatch`), a 3xx from an allowed host is refused, with no request sent for the hop, when it redirects to a host that is:
  - not in a non-empty `host_allowlist`;
  - in `host_denylist`;
  - anywhere, while `host_allowlist` holds `NO_HOSTS`.

  The tool returns its `[error] [constraint] …` shape naming the refused host. This holds for each of `http_request`, `fetch_url` and `download_file` (at least one hop test per tool, through the tool's own `_build_transport`, so the lists are proven wired).
- [ ] **AC2 — relative redirect on a pinned host still works.** With a non-empty `host_allowlist` containing the host, `Location: /next` from a pinned (resolved, non-`extra_allowed`) host is followed and the call succeeds. Observed through a recording `getaddrinfo` wrapper defined in the test (the existing `_patch_getaddrinfo` ignores and does not record `host`): resolution is asked for the hostname on both hops, never for the IP. Each dispatched request targets the IP, with `sni_hostname` equal to the ASCII hostname and `Host` equal to the original netloc.
- [ ] **AC3 — the caller's request is not mutated, and an IP hop never borrows a name.** After a pinned request, the original `httpx.Request` object still has its hostname URL, its `Host` header still equals the original netloc (port kept when non-default), and its extensions carry no `sni_hostname` key. An absolute redirect to an IP literal is checked as that IP: refused when the allow list names only hostnames, and never treated as its predecessor's `sni_hostname`.
- [ ] **AC3b — port, IDN SNI and bad hosts.** A pinned request to `example.com:8080` dispatches with `Host: example.com:8080`. For an IDN host, `sni_hostname` is the punycode form. A `Location` host or list entry that IDNA refuses (`a..b`, a 64-character label) is a `ConstraintError` (the tool's `[error] [constraint] …`), never an unhandled exception.
- [ ] **AC4 — one host normalisation.** A punycode spelling (`xn--…`) and a Unicode spelling of the same host match each other in the allow list and in the deny list, both on the first URL (`_url_check`) and on a hop. Mixed case and a trailing dot match too. An allow entry `ss.de` does **not** match a request to `ß.de` (which httpx dials as `xn--zca.de`).
- [ ] **AC5 — unchanged behaviour where it should be.**
  - The search backends construct the transport as before, with no host lists, and their tests pass unchanged.
  - `extra_allowed_hosts` still skips the pin.
  - The SSRF block list still applies to every hop.
  - `redirect_cap` behaviour is unchanged.
  - `tests/test_web_tools.py` (MockTransport) passes unchanged.
- [ ] **AC6 — no regressions.** `THE_ONE_TEST_NETNS=1 make test-unit` shows only the baseline failures; ruff check and format are clean. No browser lane needs to run: no static file changes. If one does change, run the static guards and its lane.

## Verification Steps
- AC1-AC5: new tests in `tests/test_web_helpers.py` (transport level) and `tests/test_web_redirect_hosts.py` (tool level, through each tool's real `_build_transport` with `_patch_getaddrinfo` / `_patch_super_dispatch`, and a `response_factory` that returns a 3xx with a `Location` for the first request): `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_web_helpers.py tests/test_web_redirect_hosts.py tests/test_web_tools.py tests/test_web_config.py -x --timeout 30`.
- AC6: `THE_ONE_TEST_NETNS=1 make test-unit`; `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`.

## Implementation Guidance

1. **`normalize_host`** next to `_host_matches`, through `httpx.URL(...).raw_host` as in Outputs (not the stdlib `idna` codec). Wrap `httpx.InvalidURL` and `UnicodeError` into `ConstraintError`, so a malformed `Location` host or list entry never escapes as a generic exception. An IP literal (v4 or v6, brackets stripped) passes through untouched; `none.invalid` and plain ASCII come out unchanged. Normalise list entries the same way at comparison time; a list entry that cannot be normalised matches nothing (an allow entry) or is ignored (a deny entry) rather than failing the call. Lists are short, so no pre-index is needed.
2. **`_host_policy_check`**, then make `_url_check` call it (same exception texts).
3. **Transport:**
   - Add the two keyword arguments, materialised as tuples like `_extra_allowed`.
   - In `handle_async_request`, call `_host_policy_check(request.url.host, …)` first, before the IP-literal branch and before `extra_allowed_hosts`, so an IP hop is checked as an IP, and a host in both `extra_allowed_hosts` and the deny list is refused, as on the first URL.
   - Replace the in-place pin with a new request: `httpx.Request(request.method, request.url.copy_with(host=ip), headers=httpx.Headers(request.headers), stream=request.stream, extensions={**request.extensions, "sni_hostname": normalize_host(original_host)})`, passed to `super()`. Do not set `Host`.
   - Confirm against the installed httpx (`.venv`) that the stream and timeout extensions carry over, and that streaming responses still work for `download_file`.
4. **Wire the tools:** the three `_build_transport` methods pass `host_allowlist=cfg.host_allowlist, host_denylist=cfg.host_denylist`.
5. **Tests:**
   - The new `tests/test_web_redirect_hosts.py` imports `_patch_super_dispatch`, `_Recorder` and `_patch_getaddrinfo` from `tests/test_web_helpers.py`, not `test_web_stub_tool.py`'s copies, which have a different shape. For AC2 it adds a small recording `getaddrinfo` wrapper of its own.
   - A hop's 3xx is `httpx.Response(302, headers={"Location": ...})`; no body is needed.
   - Transport-level tests first: the hop refusals, the relative redirect, no mutation, the IP hop, the port and IDN SNI, bad hosts, normalisation including `ss.de` vs `ß.de`, and a cross-origin hop whose `Host` httpx rewrites.
   - Then one tool-level hop test per tool.
   - Falsify at least: the hop check (remove the transport call: the AC1 tests fail), and the pin on a copy (restore the in-place mutation: the AC2 relative-redirect test fails, reproducing Architect review 2's finding).
6. **Flight log:** append the release-notes line under a "Release notes to carry" heading (create it if absent): "Web tools now check Allowed hosts and Denied hosts on every redirect, not only the first address; a site that redirects to a host outside an agent's Allowed hosts (for example a CDN) now fails, and the host has to be added."

## Edge Cases
- **A redirect to the same host on another port:** the host lists match on host only (as `_host_matches` does for `extra_allowed_hosts`), so it is allowed.
- **`userinfo` or an explicit port in `Location`:** `request.url.host` excludes both.
- **An empty `host_allowlist`** (any host) with a non-empty deny list: only the deny list applies to hops.
- **Downloads streaming a redirected body:** the hop check happens before any byte of the hop is read, so no partial file is left beyond today's cleanup (`web.py:419-441`).
- **httpx's own redirect loop** passes `follow_redirects` hops through `handle_async_request` one by one; nothing in the transport should assume a single call per tool call.

## Files Affected
- `the_one/tools/_web_config.py`: `normalize_host`, `_host_policy_check`, `_url_check` delegating to it, the transport's lists and pin on a copy.
- `the_one/tools/web.py`: the three `_build_transport` methods.
- Tests: new `tests/test_web_redirect_hosts.py`; additions to `tests/test_web_helpers.py`.
- `sorties/07-agent-tool-overrides/flight-log.md`: the release-notes line.

### Citation Audit
Checked by the Flight Director against the worktree (base `628a97dd` plus legs 1-2 uncommitted), 2026-10-31: `_web_config.py:337-367,443-450,453-546` (the in-place pin at `:527-537`); `web.py:152-156,176-194,262-266,274-286,385-390,404-428`; `_search_backends.py:238,303`; `tests/test_web_helpers.py:336-368`; `tests/test_web_tools.py:71-77` (MockTransport bypass). `docs/releases/` has no unreleased file.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
