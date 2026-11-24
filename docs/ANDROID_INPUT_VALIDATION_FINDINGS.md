> Historical reference; not a current release or installation guide. [Current Rust documentation](README.ru.md).

# Android numeric input: device test findings (Sedrava 0.9)

Status: **observed on a physical Android device; UX follow-up required**.

## Confirmed behavior

- Generated `examples/input_goal.sdr` APK runs on Android.
- Numeric keyboard opens and editing is possible after separating draft text from committed state.
- `Plus` increments the state; `Reset` restores its declared initial value (`2`).
- The UI reflects the committed state and the conditional message reacts to the derived condition.
- Persisted state survives application restart (verified in an earlier device test).

## Boundary test: 11 is rejected

The program declares `rule target >= 0 and target <= 10`.

On device, the tester entered `11` while the last accepted state was `1`. The text field displayed `11`, but the state display remained `target: 1`. This confirms the invariant rejects the candidate rather than committing it.

**UX defect:** The field does not explain why its displayed draft differs from the committed value. The input looks valid even though it has been rejected.

## Required follow-up

1. Keep the editable draft separate from committed state; never silently commit invalid values.
2. When a draft is invalid, show an error state and accessible inline explanatory text (at least a generic message such as `Value does not satisfy the declared rules`).
3. Keep the draft editable so the user can correct it; clear the error as soon as the draft becomes valid.
4. Define and test behavior for empty text, lone minus sign, out-of-range 32-bit values, and external state changes (e.g. `Plus`/`Reset` while editing).
5. Verify Android and Web validation semantics remain consistent; add generated-code tests and device regression checks.

## Acceptance criteria

- Entering `11` leaves `target` unchanged and displays an obvious validation error.
- Editing the draft to `8` updates the committed state and clears the error.
- Restarting the app restores the last **accepted** value, not an invalid draft.
- `Plus` and `Reset` continue to work correctly.

This document records an observed issue; it does **not** claim the UX fix is implemented.

## Implementation progress (unverified)

The Android and Web generators now contain rule-aware input feedback and regression-generation tests. The generated UI is intended to retain invalid drafts, show an error, and persist only accepted state. **CI, actual Android compilation, and a fresh device test are still required**; this finding must remain open until those gates pass.
