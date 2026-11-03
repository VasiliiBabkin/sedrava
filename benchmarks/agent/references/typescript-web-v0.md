# TypeScript 5.9 Web reference for independent benchmark trials

This is a concise platform reference, not a counter solution.

- Source files use .ts and are compiled to JavaScript before browser use.
- Declare typed variables with let variableName: number = 0; or const.
- Integer number values are JavaScript Numbers. For int32 comparisons,
  restrict arithmetic to the signed 32-bit range as required by the task.
- Use document.querySelector to find DOM nodes and textContent to display
  text values. Use addEventListener("click", callback) for button actions.
- For local persistence across reload/restart, the Web Storage API provides
  localStorage.getItem(key) and localStorage.setItem(key, value). Serialized
  values are strings and require explicit parsing/validation.
- A Web app needs an HTML entry point that loads the compiled JavaScript.
- Toolchain:
  TypeScript version 5.9.3, Node.js 22, Chromium via Playwright 1.56.0.
- Typical compile command:
  tsc --target es2022 --lib dom,es2022 --strict SOURCE.ts --outDir DEST
- Serve the HTML and JavaScript artifacts via localhost for acceptance tests.
- Do not edit the independent acceptance evaluator.
