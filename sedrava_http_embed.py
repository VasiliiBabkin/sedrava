"""Embed a validated API0 read-only panel into a generated Sedrava Web app.

The panel remains isolated from local persistent state and actions.
"""
import html
import json
import re


def embed_api_panel(document: str, name: str, fields=None, *, title=None, loading=None, empty=None, error=None) -> str:
    if type(document) is not str or "</body>" not in document:
        raise ValueError("Generated Web document must contain a closing body tag")
    for label, value in (("title", title), ("loading", loading), ("empty", empty), ("error", error)):
        if value is not None and (type(value) is not str or not value or len(value) > 160):
            raise ValueError("Invalid HTTP display " + label)
    heading = html.escape(title if title is not None else name)
    messages = json.dumps({
        "loading": loading if loading is not None else "Loading…",
        "empty": empty if empty is not None else "No records",
        "error": error if error is not None else "Unable to load external data. Check network access and API CORS policy.",
    }, ensure_ascii=True)
    # JSON literals embedded in a script must not terminate the script element.
    messages = messages.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    if fields is not None:
        if (type(fields) is not list or not fields or len(fields) > 64
                or any(type(field) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", field) for field in fields)
                or len(fields) != len(set(fields))):
            raise ValueError("Invalid HTTP display field selection")
    visible = json.dumps(fields, ensure_ascii=True) if fields is not None else "null"
    panel = """
<style>
#sedrava-api-panel { margin-block: 1.5rem; }
#sedrava-api-panel #sedrava-api-status { min-height: 1.5em; }
#sedrava-api-panel #sedrava-api-results { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 17rem), 1fr)); gap: 1rem; margin-top: 1rem; }
#sedrava-api-panel #sedrava-api-results article { border: 1px solid currentColor; border-radius: .75rem; padding: 1rem; min-width: 0; overflow-wrap: anywhere; }
#sedrava-api-panel #sedrava-api-results dl { margin: 0; }
#sedrava-api-panel #sedrava-api-results dt { font-size: .85em; opacity: .75; margin-top: .75rem; }
#sedrava-api-panel #sedrava-api-results dt:first-child { margin-top: 0; }
#sedrava-api-panel #sedrava-api-results dd { margin: .2rem 0 0; }
</style>
<section id="sedrava-api-panel" aria-label="External data">
  <h2>""" + heading + """</h2>
  <p id="sedrava-api-status" role="status" aria-live="polite">Waiting to load</p>
  <button id="sedrava-api-reload" type="button">Reload external data</button>
  <div id="sedrava-api-results"></div>
</section>
<script type="module">
import {load} from './service.mjs';
const visibleFields = """ + visible + """;\nconst messages = """ + messages + """;
const status = document.getElementById('sedrava-api-status');
const results = document.getElementById('sedrava-api-results');
const button = document.getElementById('sedrava-api-reload');
let controller;
let sequence = 0;
async function refresh() {
  const current = ++sequence;
  controller?.abort();
  controller = new AbortController();
  button.disabled = true;
  status.textContent = messages.loading;
  results.replaceChildren();
  try {
    const data = await load({signal: controller.signal});
    if (current !== sequence) return;
    const rows = Array.isArray(data) ? data : [data];
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const article = document.createElement('article');
      const description = document.createElement('dl');
      for (const key of visibleFields ?? Object.keys(row)) {
        const value = row[key];
        if (!Object.prototype.hasOwnProperty.call(row, key)) continue;
        const term = document.createElement('dt');
        const detail = document.createElement('dd');
        term.textContent = key;
        detail.textContent = String(value);
        description.append(term, detail);
      }
      article.append(description);
      fragment.append(article);
    }
    results.replaceChildren(fragment);
    status.textContent = rows.length ? 'Loaded ' + rows.length + ' record(s)' : messages.empty;
  } catch (error) {
    if (current !== sequence) return;
    status.textContent = error?.name === 'AbortError' ? 'Request cancelled' :
      messages.error;
  } finally {
    if (current === sequence) button.disabled = false;
  }
}
button.addEventListener('click', refresh);
refresh();
</script>
"""
    return document.replace("</body>", panel + "</body>", 1)
