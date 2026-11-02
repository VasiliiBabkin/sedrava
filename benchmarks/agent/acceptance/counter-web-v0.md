# Counter Web acceptance test plan

This checklist is a **test specification**, not an automated browser suite.
Do not claim a behavioral pass until an independent test runner implements
and executes every applicable case against the built Web application.

| ID | Setup | Action | Required observation |
| --- | --- | --- | --- |
| C01 | Fresh isolated storage | Open app | Count is 0 |
| C02 | Count 0 | Increment once | Count is 1 |
| C03 | Count 1 | Decrement twice | Count is -1 |
| C04 | Count -1 | Reset | Count is 0 |
| C05 | Count 0 | Increment 3 times, decrement once | Count is 2 |
| C06 | Count 2 | Reload page | Count is 2 |
| C07 | Count 2 | Close and reopen app in same storage profile | Count is 2 |
| C08 | Count 2 | Reset, reload | Count is 0 |

## Evaluator implementation requirements

- Use a clean, isolated browser profile for each trial. Do not share storage.
- Locate controls by visible labels or documented accessible roles; avoid
  assumptions about DOM structure or framework internals.
- Verify displayed state after each action; use bounded waits, not arbitrary
  sleeps.
- Record the actual browser/runtime versions and complete test output.
- The build must run from a fresh checkout with documented dependencies.
- Do not substitute compiler unit tests for these end-to-end observations.
- If an action cannot be located, fail with an actionable diagnostic.
- Treat browser crashes, unavailable dependencies and environment outages
  separately from implementation failures, with evidence in logs.

The comparison is not ready until both languages have equivalent runnable
starters and a single independent browser evaluator can execute these cases.
