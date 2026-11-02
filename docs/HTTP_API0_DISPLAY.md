# Experimental HTTP API0: declarative card fields

Status: **draft PR #31**, Web-only, not included in released Sedrava 0.10.0.

A service can end with an optional `display cards:` block. It selects and orders
fields of the validated JSON response; it does **not** change the response schema,
request permissions, local state, or actions.

```sedrava
service articles:
    origin "https://api.example.com"
    path "/posts"
    response many:
        id int32
        title text
    display cards:
        heading "Latest articles"
        loading "Loading articles…"
        empty "No articles yet"
        error "Could not load articles"
        title
        id
```

Use the service as the trailing declaration in a normal application source,
or provide it separately with `sedrava build web app.sdr --service articles.sdr`.
The generated HTML imports its sibling `service.mjs`. Browser CORS policy
must permit the request; serving files over HTTP(S) is recommended rather than
opening `file://` directly.

The display block is optional; absent it, every declared response field is shown
in schema order. Each selected field must be declared in `response`, be unique,
and use exactly eight spaces of indentation. Only `display cards:` is supported;
there is no arbitrary component placement, styling, template interpolation,
authentication, POST, or Android networking in API0.

Security: JSON remains strictly validated against the complete response schema;
values are rendered using `textContent`, not interpreted as HTML.

The optional `heading`, `loading`, `empty`, and `error` directives accept
JSON-quoted text (1–160 characters each). Each directive can occur only once.
The heading labels the whole external-data panel, not an individual record.
Strings are HTML-escaped or encoded as script-safe JSON literals, and record
values continue to render via `textContent`. The default English messages
remain in effect when directives are omitted.
