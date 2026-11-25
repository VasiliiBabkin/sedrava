# http-cards-v0 — shared behavioral contract

Target: Web application with a read-only external JSON endpoint.

- Fetch a list of records from a configured HTTPS endpoint.
- Display only the title field of each validated record in cards.
- Show a loading state while the request is pending, an empty state for [], and an error state for HTTP failure or invalid response.
- Provide a retry action that can recover after an error.
- Render untrusted title strings as text, never executable HTML.
- Do not send mutations or modify local application state through the API.

Acceptance tests use a controlled endpoint to cover successful response, empty response, HTTP 500, malformed record, HTML-looking title, and recovery.

For Sedrava, this requires the experimental HTTP API0 branch; mark unsupported on the released 0.10 compiler.
