# Leg: ws-pre-step-visibility-tagging

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

## Objective

Close the F5 live-broadcast carry-forward: at `interfaces/web/app.py:_process_and_broadcast` (around line 817), inject `"visibility": OPERATOR_VISIBILITY` into the `user_event` dict-literal BEFORE the broadcast call, gated on `session.platform is not None`. The post-step Message-level tagging at L997-1004 (the refresh path) is unchanged; leg 6 closes the live path. Update the mission Known Issue to mark the live-broadcast WS-typed asymmetry as RESOLVED.

## Context

- **Mission Known Issue (mission.md)**: "Live-broadcast WS-typed visibility-tagging asymmetry (surfaced in Flight 5 debrief, owned by Flight 6)". F5's storage-edge shim tags `Message.visibility = OPERATOR_VISIBILITY` AFTER `agent.step` runs — correct for persistence and refresh-render. But the live broadcast at `app.py:817-819` fires BEFORE `agent.step` and emits a raw dict event WITHOUT the visibility key. Operator-typed messages on connector-attached sessions appear UNMARKED until refresh. Leg 6 closes this by adding the key at the dict-literal source.
- **Flight In-Flight §8 (flight.md)**: "At `_process_and_broadcast` in `interfaces/web/app.py` (around line 817-819), inject `"visibility": OPERATOR_VISIBILITY` into the `user_event` dict when `session.platform is not None`, BEFORE the live broadcast. The `session_locks[session.id]` taken at line 258 serializes this against `_inbound.py:155`'s `dispatch_inbound`, so there is no race. Closes F5 carry-forward."
- **Architect framing correction (cycle-1 flight log)**: leg 6 is dict-literal injection at L817-819, NOT Message-level tagging (which is the refresh path's job). The two sites are independent.
- **Render-side wiring is already complete** (per the mission Known Issue note): JS reads `data.visibility` through `addMsg`, `buildToolMsg`, and the streaming-bubble closure. The render path consumes the new key automatically — no JS changes needed.
- **Symmetry with the inbound dispatcher**: `connectors/_inbound.py` (post-leg-2) emits broadcast events for inbound user messages that DO carry visibility via the codec's projection at `db/codec.py:173-176`. Leg 6 brings the WS-typed path to symmetry — both operator-console paths now broadcast with the visibility key.
- **Codec projection precedent** (`db/codec.py:173-176`): the codec already conditionally adds `"visibility": Message.visibility` to the event dict when `visibility is not None`. Leg 6 mirrors this projection at the dict-literal site BEFORE the message exists as a Message.
- **`session.platform`** is set when the session is connector-attached (per `app.py:455-456,468` — restored from `ChatSession.platform` at the restore-from-DB site). For web-native sessions, `session.platform is None` and leg 6's branch does nothing.

## Inputs

- `the_one/interfaces/web/app.py:806-820` — `_process_and_broadcast` user-event broadcast site (the leg's target)
- `the_one/interfaces/web/app.py:38-40` — `OPERATOR_VISIBILITY` + `tag_post_step_visibility` imports (already present from F5)
- `the_one/interfaces/web/app.py:195-209` — `Session.platform` field declaration
- `the_one/db/codec.py:173-176` — visibility projection precedent
- `missions/10-bi-directional-comms-connectors/mission.md` — Known Issue to mark resolved
- `tests/test_app.py` (or wherever `_process_and_broadcast` tests live) — extend with the leg-6 invariant

## Outputs

- `the_one/interfaces/web/app.py:817-819` — inject `"visibility": OPERATOR_VISIBILITY` into `user_event` dict when `session.platform is not None`, BEFORE `_send_to_session`
- `missions/10-bi-directional-comms-connectors/mission.md` — mark the live-broadcast WS-typed visibility-tagging asymmetry Known Issue as RESOLVED with a closure note pointing to this leg
- `tests/test_app.py` (or equivalent) — new test asserting the live-broadcast event carries `visibility=operator` on connector-attached sessions and does NOT carry it on web-native sessions (or carries `None`)
- Flight log gains a leg-6 entry

## Acceptance Criteria

- [ ] `user_event` at `app.py:817-819` carries `"visibility": OPERATOR_VISIBILITY` when `session.platform is not None`, BEFORE the broadcast at L819
- [ ] On `session.platform is None` (web-native session), `user_event` does NOT carry the `visibility` key (or carries `None` — match the codec's projection rule: only add the key when the value is meaningful). **Decision**: only add the key when the value is non-None (matches `db/codec.py:173-176`'s precedent — the key is meaningful presence-marked).
- [ ] The post-step Message-level tagging at L997-1004 is UNCHANGED (separate site; refresh path).
- [ ] Mission `Known Issues` section marks the live-broadcast WS-typed asymmetry CLOSED with `[x]` and a note pointing to F6 L6.
- [ ] New test in `tests/test_app.py` (or equivalent) asserts the leg-6 invariant: live broadcast on a connector-attached session carries `visibility=operator` (or `OPERATOR_VISIBILITY` constant); live broadcast on a web-native session does NOT carry the key
- [ ] F1-F5 + leg-1a/1b/1c/2/3/4/5 regression byte-identical
- [ ] `ruff check` clean on `the_one/interfaces/web/app.py`

## Verification Steps

- `grep -n "visibility.*OPERATOR_VISIBILITY\|user_event\[" the_one/interfaces/web/app.py | head` — confirm the injection site
- `docker exec the-one pytest -x --timeout 30 tests/test_app.py` — new + existing tests pass
- `docker exec the-one pytest -x --timeout 30` — full suite passes
- `grep -n "Live-broadcast WS-typed" missions/10-bi-directional-comms-connectors/mission.md` — confirm the Known Issue is checked off

## Implementation Guidance

1. **Locate the exact target lines** with `grep -n "user_event = {" the_one/interfaces/web/app.py`. The dict-literal at the live-broadcast site is the only modification. Current shape (around line 817):

   ```python
   user_event = {"type": "user", "content": user_input, "source": source}
   session.add_event(user_event)
   await _send_to_session(session, user_event, exclude=exclude_user_echo)
   ```

2. **Replace with conditional injection**:

   ```python
   user_event: dict[str, Any] = {"type": "user", "content": user_input, "source": source}
   # M10 F06 L6: close the F5 live-broadcast carry-forward. The
   # operator-typed message on a connector-attached session must
   # carry the visibility tag at LIVE broadcast time (the refresh
   # path's post-step Message-level tagging at L997-1004 handles
   # the persistence side; this site handles the live side). Mirrors
   # the codec's projection rule at db/codec.py:173-176 — only emit
   # the key when the value is meaningful. The session_locks[session.id]
   # at L258 serializes against connectors/_inbound.py:155's
   # dispatch_inbound, so there is no race.
   if session.platform is not None:
       user_event["visibility"] = OPERATOR_VISIBILITY
   session.add_event(user_event)
   await _send_to_session(session, user_event, exclude=exclude_user_echo)
   ```

   The `dict[str, Any]` annotation is added defensively because mypy may otherwise infer a narrower type from the literal that conflicts with the conditional assignment. The Python module already imports `Any` from `typing` (verify; add if missing).

3. **Update `mission.md` Known Issues** at the `[ ] Live-broadcast WS-typed visibility-tagging asymmetry` line. Change `[ ]` to `[x]` and append a closure note: `Closed by Flight 6 Leg 6 — operator-typed messages on connector-attached sessions now carry visibility=operator at live broadcast time; refresh path is unchanged.`

4. **Write the test** in `tests/test_app.py` (or wherever `_process_and_broadcast` tests live — verify with `grep -rln "_process_and_broadcast" tests/`). New test class or function:

   ```python
   async def test_live_broadcast_carries_operator_visibility_on_connector_attached_session(...):
       """F6 L6: closes the F5 carry-forward.

       Mock a session with platform='stub' (connector-attached). Call
       _process_and_broadcast. Inspect the broadcast events captured by
       the test's _send_to_session monkeypatch. The first event (the
       user echo) MUST carry visibility=OPERATOR_VISIBILITY.
       """
       # ... fixture setup mirrors existing _process_and_broadcast tests ...
       assert user_event["visibility"] == OPERATOR_VISIBILITY


   async def test_live_broadcast_omits_visibility_on_web_native_session(...):
       """Sister test: session.platform=None → no visibility key."""
       # ... fixture setup with platform=None ...
       assert "visibility" not in user_event
   ```

   Find the existing test for `_process_and_broadcast` (the F5 storage-edge shim test is the closest precedent — search `tests/` for `_process_and_broadcast` or `OPERATOR_VISIBILITY`). Mirror its fixture pattern.

5. **Run verification**:
   1. `docker exec the-one pytest -x --timeout 30 tests/test_app.py` (or the test file holding `_process_and_broadcast` tests)
   2. `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py` — leg-2 + F5 regression
   3. `docker exec the-one pytest -x --timeout 30` — full suite passes
   4. `docker exec the-one ruff check the_one/interfaces/web/app.py` — clean

6. **Update flight log** with leg-6 entry: site of the injection, test additions, mission Known Issue closure note, F5 carry-forward closure confirmation.

7. **Set leg status `landed`**. Do NOT modify flight.md. Do NOT commit.

## Edge Cases

- **`session.platform == ""`** (empty string, NOT None): the F5 storage-edge shim handles this case the same as None per the F5 implementation. Leg 6 mirrors — `is not None` check passes for `""` (which is unlikely but possible if a future restore path mis-fills the field). The defensive stance accepts this; the visibility tag fires on empty-string platforms too, which is the safer side (operator-only marker visible).
  - **Counter-decision**: leg 6 uses `is not None` exclusively to match the F5 shim's behavior at L997. If a future leg standardizes on truthiness, both sites change together.
- **Streamed multi-event broadcasts** (assistant chunks, tool_calls): leg 6 only modifies the USER event dict. Other events use their own dict-literal sites; their visibility is set by the post-step `tag_post_step_visibility` walk at L997-1004 (the refresh path). Live broadcasts of assistant/tool events on connector-attached sessions go through a DIFFERENT code path (the streaming/usage events) — leg 6 does NOT close visibility on those. F10 territory if needed; the F5 debrief flagged the operator-echo path as the primary visibility-render gap.
- **Concurrent inbound during operator-typed broadcast**: per-session lock at L258 serializes the WS path. Leg 2's dispatcher takes the same lock at `_inbound.py:155`. The two paths cannot interleave on the same session_id. Documented.
- **Web-native session with no `Session.platform` field set**: defaults to `None` per `Session.platform: str | None = None` at the dataclass definition. The injection branch correctly skips.
- **The injection happens BEFORE `session.add_event(user_event)`**: meaning the in-memory history ALSO gets the visibility-tagged event. This is a minor positive — refreshing inside the same process (without a DB hit) returns the tagged event. Documented in the inline comment.

## Files Affected

- `the_one/interfaces/web/app.py` — single dict-literal injection at L817-819 (~10 lines including comment)
- `missions/10-bi-directional-comms-connectors/mission.md` — flip the Known Issue checkbox + closure note (~2 lines)
- `tests/test_app.py` (or equivalent test file) — 2 new tests (~50 lines)
- `the_one/db/codec.py` — UNCHANGED
- `the_one/connectors/visibility.py` — UNCHANGED
- The flight log gains a leg-6 entry

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (regression net byte-identical)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT modify flight.md
- [ ] Do NOT commit (deferred-batched workflow)

## Citation Audit

Citations verified at design time:
- `the_one/interfaces/web/app.py:806-820` — confirmed (`_process_and_broadcast` user-event broadcast)
- `the_one/interfaces/web/app.py:38-40` — confirmed (imports for `OPERATOR_VISIBILITY` + `tag_post_step_visibility`)
- `the_one/interfaces/web/app.py:195-209` — confirmed (`Session.platform`)
- `the_one/interfaces/web/app.py:997-1004` — confirmed (post-step tagging — refresh path, UNCHANGED by this leg)
- `the_one/db/codec.py:173-176` — codec visibility projection (precedent)
- `missions/10-bi-directional-comms-connectors/mission.md` — Known Issue line for live-broadcast WS-typed asymmetry

All citations verified clean.
