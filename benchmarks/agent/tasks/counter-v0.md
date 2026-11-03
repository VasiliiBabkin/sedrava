# counter-v0 — shared behavioral contract

Target: one-screen application, with local persistence.

- Display a signed integer count, initially 0 on a fresh installation.
- Increment adds exactly 1; decrement subtracts exactly 1; reset sets 0.
- The displayed value updates after every action.
- After an application reload/restart, the last committed value remains.
- No network access is required.

Acceptance tests must cover fresh state, +1, -1, reset, multiple operations, and persistence. Do not prescribe framework-specific widgets or storage APIs.

Record the supported integer range and use test values within the intersection of the compared implementations.
