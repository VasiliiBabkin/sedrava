"""Embed a validated API0 read-only panel into a generated Sedrava Web app.

The panel remains isolated from local persistent state and actions.
"""
import html


def embed_api_panel(document: str, name: str) -> str:
    if type(document) is not str or "</body>" not in document:
        raise ValueError("Generated Web document must contain a closing body tag")
    heading = html.escape(name)
    panel = """
<section id="sedrava-api-panel" aria-label="External data">
  <h2>""" + heading + """</h2>
  <p id="sedrava-api-status" role="status" aria-live="polite">Waiting to load</p>
  <button id="sedrava-api-reload" type="button">Reload external data</button>
  <div id="sedrava-api-results"></div>
</section>
<script type="module">
import {load} from './service.mjs';
const panel = document.getElementById('sedrava-api-panel');
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
  status.textContent = 'Loading…';
  results.replaceChildren();
  try {
    const data = await load({signal: controller.signal});
    if (current !== sequence) return;
    const rows = Array.isArray(data) ? data : [data];
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const article = document.createElement('article');
      const description = document.createElement('dl');
      for (const [key, value] of Object.entries(row)) {
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
    status.textContent = rows.length ? 'Loaded ' + rows.length + ' record(s)' : 'No records';
  } catch (error) {
    if (current !== sequence) return;
    status.textContent = error?.name === 'AbortError' ? 'Request cancelled' :
      'Unable to load external data. Check network access and API CORS policy.';
  } finally {
    if (current === sequence) button.disabled = false;
  }
}
button.addEventListener('click', refresh);
refresh();
</script>
"""
    return document.replace("</body>", panel + "</body>", 1)
