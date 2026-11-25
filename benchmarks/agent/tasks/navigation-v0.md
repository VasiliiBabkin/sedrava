# navigation-v0 — shared behavioral contract

Target: two-screen application with local state.

- Screen A shows a count and an action to increment it.
- Navigate from A to screen B and return via a Back action.
- Returning to A preserves the count.
- Repeated navigation does not duplicate state or reset it.
- Restart behavior must be specified by each implementation; compare persistence only when all tested targets support it.

Acceptance tests cover forward/back navigation, count retention, and repeated transitions. Use platform-appropriate navigation controls.
