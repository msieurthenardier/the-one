# Leg: root-cause-synthesis

**Status**: landed
**Flight**: [Recon & Root-Cause Spike](../flight.md)

> **Outcome:** consolidated the spike findings, promoted confirmed root causes to
> the mission, resolved the mission's open questions, and applied the operator's
> reframe (add #122 schema-compat flight as the new high-priority Flight 2; keep
> extended-thinking as a separate lower-priority feature flight). Go/no-go for all
> downstream flights recorded in the flight log ("Synthesis & Go/No-Go").

## Objective

Turn the spike's findings into durable, actionable guidance: confirmed root causes
in the mission, resolved open questions, a reshaped flight plan, and a go/no-go for
each downstream flight.

## Acceptance Criteria

- [x] Confirmed root causes promoted to mission **Known Issues** (#122, #105;
      hole #1 retired as falsified).
- [x] Mission **Open Questions** resolved (root-cause spike; any-llm → hand-roll;
      thinking-representation re-scoped to the optional flight).
- [x] Mission **Flights** reshaped: new high-priority Flight 2 (#122 schema
      compat); Flight 3 (#105 text-form recovery) approach refined; thinking moved
      to a separate lower-priority feature flight; Flights 4–5 reaffirmed.
- [x] Mission Outcome/SC annotated with a spike-correction banner (original
      framing preserved per the mid-pivot rule).
- [x] Go/no-go per downstream flight recorded in the flight log.

## Files Affected

- `missions/16-llm-provider-hardening/mission.md` — banner, Known Issues, Open
  Questions, Flights (annotated reframe).
- Flight log — synthesis + go/no-go.

---

## Post-Completion Checklist

- [x] Mission promoted + reframed
- [x] Go/no-go recorded
- [x] Leg status `landed`
