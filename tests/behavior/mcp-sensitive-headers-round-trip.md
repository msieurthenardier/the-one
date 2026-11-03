# Behavior Test: MCP Sensitive Headers Round Trip

**Slug**: `mcp-sensitive-headers-round-trip`
**Status**: active
**Created**: 2026-10-25 (Mission 31 Flight 5 Leg 07; run in Leg 12)
**Last Run**: 2026-10-28-14-36-06 (pass, 8/8; re-run after the M31 F6 L10 HAT re-authored step 6's hint; [run log](mcp-sensitive-headers-round-trip/runs/2026-10-28-14-36-06.md)). Previous: 2026-10-26-15-13-47 (pass, 8/8)

## Intent

Verifies, against a real running instance, that a sensitive header on a
streamable-HTTP MCP source is created, saved, re-masked, edited, unticked and
renamed without ever leaking into plaintext config or losing the stored secret.
It is the real-environment check of the server's secrets contract (flight DD5),
which no other spec covers: the server keeps a stored secret when the client
sends `__MASKED__` for an existing key, overwrites it for any other value,
deletes a key the client omits, and masks every `secrets` value on read
(`***...` plus the last four characters).

Unit and browser tests pin the payloads one request at a time. This spec drives
the whole editor as an operator would, observing two things at every step: what
the editor shows (UI) and what the server stored (the API's `GET
/api/mcp-sources/{id}`, which returns `config.headers` in the clear and
`secrets` masked). The stored row must never hold a mask string or a
plaintext secret in `config`, and must never lose a secret the operator did
not touch.

## Preconditions

- A dev instance built from the flight branch, on a dedicated non-default port
  (8486 or higher, assigned per run; never 8484, 8485 or 8491), with a
  **scratch data directory under `$HOME`** (e.g.
  `$HOME/the-one-behavior-test-scratch/mcp-headers/data`; not `/tmp`). Start it from a scratch
  working directory (e.g. `$HOME/the-one-behavior-test-scratch/mcp-headers/cwd`)
  with `THE_ONE_DEV_MODE=true`, as CLAUDE.md "Behavior-test
  credential convention" shows, and record the PID (stop it by that PID). A fresh
  data directory has no `api-credential`: run `THE_ONE_DATA_DIR=<data_dir> the-one
  rotate-api-credential` once before the first start. Follow that section for the
  credential (read `<data_dir>/api-credential`) and the browser handoff (mint a
  one-time handoff with `POST /api/session/handoff`, one per navigation to the
  app root from an unauthenticated state).
- No network access is needed. The source's URL is `http://127.0.0.1:9/mcp`
  (nothing listens there), so the editor's connection test fails fast and is
  not part of this spec.
- A browser apparatus can reach the dev instance, and a shell can call the API
  with `Authorization: Bearer <credential>`.
- The scratch instance holds no MCP sources at the start
  (`GET /api/mcp-sources` returns an empty list).

## Observables Required

- **browser**: the MCP server editor (Library, MCP servers): the Headers table,
  each row's Key, Value and Sensitive controls, the Save and Cancel buttons and
  the "Unsaved changes" caption.
- **http**: `GET /api/mcp-sources` and `GET /api/mcp-sources/{id}` with the
  bearer credential. `{SRC}` is the source's `id`.
- **shell** (optional cross-check): `sqlite3 {data_dir}/the-one.db "SELECT
  config FROM mcp_sources WHERE id='{SRC}'"` to confirm the plaintext config
  holds no secret text.

## Steps

Secrets: `S1` is `Bearer-first-secret-1111`, `S2` is `Bearer-second-secret-2222`.
Masks read back as `***...1111` and `***...2222`.

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | In the browser, open Library, then Add, then MCP server. Name it `sens-headers`, choose type `streamable-http`, set URL `http://127.0.0.1:9/mcp`. Add a row: key `Authorization`, value `S1`, tick **Sensitive**. Add a second row: key `X-Plain`, value `plain-value`, leave Sensitive off. Click Create. Then `GET /api/mcp-sources`, take the new source's id as `{SRC}`, and `GET /api/mcp-sources/{SRC}`. | The editor moves to the saved source. The stored row has `secrets` equal to `{"Authorization": "***...1111"}` and `config.headers` equal to `{"X-Plain": "plain-value"}`. `S1` appears nowhere in the response, and `Authorization` is not a key of `config.headers`. |
| 2 | Reload the page (a fresh handoff if the session needs one) and open `sens-headers` again. Look at the `Authorization` row. | The Headers table lists `X-Plain` and `Authorization`. The `Authorization` row's Sensitive switch is on and its value field reads `***...1111` as a stored secret (no Show control, and a hint that the secret is stored). [a11y] The switch is announced as a switch named "Sensitive, row 2" and the table is named "Headers". Save is disabled and no "Unsaved changes" caption shows. |
| 3 | Change only the name to `sens-headers-b`. Click Save. Read `GET /api/mcp-sources/{SRC}`. | The save succeeds with no error. `secrets` is still `{"Authorization": "***...1111"}` and `config.headers` is still `{"X-Plain": "plain-value"}`. The form reads clean after the save. |
| 4 | Type `S2` into the `Authorization` value (the stored mask is replaced as soon as you type). Click Save. Read `GET /api/mcp-sources/{SRC}`. Then look at the row. | `secrets.Authorization` is `***...2222`: the secret was replaced (the tail changed from `1111`). `config.headers` still has no `Authorization`. After the save the row is back in stored mode (value `***...2222`, no Show control) and the form is clean. |
| 5 | Untick **Sensitive** on the `Authorization` row. Look at the value field, then click Save. Read `GET /api/mcp-sources/{SRC}`. | Unticking clears the value (the field is empty and plain text, not the mask). After Save, `secrets` is `{}` and `config.headers.Authorization` is `""`. The mask text (`***`) and `S2` appear nowhere in `config`. (An empty value is stored differently by sensitivity: in `config.headers` when the row is not sensitive, as here, and in `secrets` when it is sensitive, as in step 7.) |
| 6a | (Setup, no judgment) Tick **Sensitive** again on the `Authorization` row, type `S1` into its value and Save. Read `GET /api/mcp-sources/{SRC}` and record the evidence that the row is stored. | `secrets.Authorization` is `***...1111` in the response, and the row shows stored mode. If it does not, stop: step 6b's precondition is not met. |
| 6b | Change the row's **key** to `X-Auth`, without touching the value. | As soon as the key changes, the value field empties and the hint under it asks for the value again ("Sensitive values must be re-entered when the key changes."). Save is enabled. |
| 7 | Without retyping, click Save. Read `GET /api/mcp-sources/{SRC}`. | The save succeeds. `secrets` no longer holds `Authorization`. `X-Auth` is stored with an empty value (`secrets["X-Auth"]` is `""`: an empty sensitive value lives in `secrets`, where an empty non-sensitive one lives in `config.headers`, as in step 5), `__MASKED__` and `S1` appear nowhere in the response, and the old secret was not carried under the new name. The form reads clean and the `X-Auth` row shows an empty value, not stored mode. |
| 8 | Type `S2` into the `X-Auth` value and Save. Edit `X-Plain`'s value to `changed`, then click Cancel. | After the first save `secrets["X-Auth"]` is `***...2222` and the row is in stored mode. After Cancel the `X-Plain` value is back to `plain-value`, the `X-Auth` row is still present in stored mode, and no row named `Authorization` has come back. `GET /api/mcp-sources/{SRC}` is unchanged by the Cancel. The evidence is a before/after API diff: read `GET /api/mcp-sources/{SRC}` immediately before clicking Cancel (after the save) and again after it, and the two responses are identical (`config`, `secrets` and any other field). |

## Out of Scope

- Connecting to a real MCP server, the connection check record, OAuth and the
  tools list (see `mcp-oauth-*` specs and the flight's later legs). The editor's
  automatic connection-status line (it probes the unreachable URL on open and may show
  a failed or checking state) is likewise not judged here.
- A typed secret that itself looks like a mask (`***` or `***...abcd`): the
  server's `_looks_masked` keeps or drops it on a PUT. This is a known limit of
  the server's contract, recorded for the flight debrief.
- Stdio sources' environment variables use the same table and code path; this
  spec exercises the headers variant.

## Variants (optional)

- Run steps 1-8 on a `stdio` source (type `stdio`, command `uvx`) with
  environment variables in place of headers. The stored dict is `config.env`.
