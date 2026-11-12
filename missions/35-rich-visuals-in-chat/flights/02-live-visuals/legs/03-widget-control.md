# Leg: widget-control

**Status**: aborted (superseded before implementation, 2026-11-09)
**Flight**: [Live Visuals](../flight.md)

This leg was designed and design-reviewed but never started. The review (Developer, Sonnet, 2026-11-09) found it too large for one pass and changed its focus design. It is replaced by three legs:

- [`03-widget-frame-hardening`](03-widget-frame-hardening.md): the frame-side security controls (focus gate, link blocking, pause gate with an initial state), the prelude re-pin and the guard allowance.
- `04-widget-card` (designed after leg 3 lands): the card, marking, limits and notices, theme, `sweep()`, CSS, icons, catalogue and registry.
- `05-widget-lifecycle` (designed after leg 4 lands): the lifecycle manager, the cap and ceiling, the hang guard, reduced motion and visibility.

The review's findings and the operator's focus decision (frame-side gesture-recency rule; the page backstop and the `stopped-focus` card dropped) are recorded in the flight log's Flight Director Notes. Nothing was implemented under this leg.
