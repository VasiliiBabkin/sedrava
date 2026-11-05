"""Generate a small accessible standalone HTML UI for an API0 service.

The page imports the generated sibling service.mjs module.
"""
import html
from sedrava_http import ApiService, JsonResponse


def generate_api_page(service: ApiService, schema: JsonResponse) -> str:
    if type(service) is not ApiService or type(schema) is not JsonResponse:
        raise ValueError("Expected validated API service and JSON schema")
    heading = html.escape(service.name)
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + heading + ''' — Sedrava</title>
<style>
:root{font-family:system-ui,sans-serif;color-scheme:light dark}
body{max-width:760px;margin:3rem auto;padding:0 1rem;line-height:1.5}
button{font:inherit;padding:.6rem 1.1rem;border-radius:.5rem;cursor:pointer}
article{border:1px solid #8886;border-radius:.7rem;padding:1rem;margin:.8rem 0;overflow-wrap:anywhere}
dt{font-weight:700}dd{margin:0 0 .7rem}#status{min-height:1.5rem}
</style></head><body>
<main><h1>''' + heading + '''</h1>
<p id="status" role="status" aria-live="polite">Waiting to load</p>
<button id="retry" type="button">Reload data</button>
<section id="results" aria-label="API results"></section></main>
<script type="module">
import {load} from './service.mjs';
const status = document.getElementById('status');
const results = document.getElementById('results');
const retry = document.getElementById('retry');
let controller;
let generation = 0;
async function refresh() {
  const current = ++generation;
  if (controller) controller.abort();
  controller = new AbortController();
  retry.disabled = true;
  status.textContent = 'Loading…';
  results.replaceChildren();
  try {
    const data = await load({signal: controller.signal});
    if (current !== generation) return;
    const rows = Array.isArray(data) ? data : [data];
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const card = document.createElement('article');
      const description = document.createElement('dl');
      for (const [key, value] of Object.entries(row)) {
        const term = document.createElement('dt');
        const detail = document.createElement('dd');
        term.textContent = key;
        detail.textContent = String(value);
        description.append(term, detail);
      }
      card.append(description);
      fragment.append(card);
    }
    results.replaceChildren(fragment);
    status.textContent = rows.length ? 'Loaded ' + rows.length + ' record(s)' : 'No records';
  } catch (error) {
    if (current !== generation) return;
    status.textContent = error?.name === 'AbortError' ? 'Request cancelled' :
      'Unable to load data. Check network access and API CORS policy.';
  } finally {
    if (current === generation) retry.disabled = false;
  }
}
retry.addEventListener('click', refresh);
refresh();
</script></body></html>
'''
