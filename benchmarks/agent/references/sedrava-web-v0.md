# Sedrava 0.10 Web syntax reference for independent benchmark trials

This is a concise language reference, not a counter solution.

- Source is plain UTF-8 with .sdr extension.
- Declare the application name with: app "A title"
- Declare a typed scalar implicitly through its literal:
  state identifier = 0
  Scalar values may be signed int32, boolean, or Unicode text.
- To preserve a declared scalar across app reloads, use:
  persist identifier
  The persist directive follows its state declaration, before actions.
- Actions follow declarations, e.g.:
  action action_name: identifier = expression
  Expressions support identifiers, integer literals, + and -, with checked
  int32 arithmetic. Action assignments are atomic and validated.
- A one-screen UI uses:
  screen main:
      value identifier
      button "Visible label" -> action_name
  Four spaces indent widgets.
- CLI:
  python -m sedrava_cli check SOURCE.sdr
  python -m sedrava_cli test SOURCE.sdr
  python -m sedrava_cli build web SOURCE.sdr --output DEST/index.html
- The Web build produces a standalone HTML file with local state persistence
  when a state is declared persistent. Serve it over localhost for acceptance.
- Do not edit the independent acceptance evaluator.
