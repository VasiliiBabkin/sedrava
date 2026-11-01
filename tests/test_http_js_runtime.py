"""Exercise the generated module in real Node.js JavaScript runtime.

Uses a deterministic mocked Fetch response: no external service dependency.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from sedrava_http import ApiService, JsonField, JsonResponse
from sedrava_http_codegen import generate_fetch_module


NODE_TEST = r'''
import assert from 'node:assert/strict';
import { load } from './service.mjs';
const encoder = new TextEncoder();
let response = {status: 200, data: [{title:'Ready',id:7}], contentType:'application/json'};
let calls = 0;
globalThis.fetch = async (url, options) => {
  calls++;
  assert.equal(url, 'https://api.example.com/articles');
  assert.equal(options.method, 'GET');
  assert.equal(options.credentials, 'omit');
  assert.equal(options.redirect, 'error');
  const body = encoder.encode(JSON.stringify(response.data));
  return new Response(body, {status:response.status,headers:{'content-type':response.contentType}});
};
const expected = [{title:'Ready',id:7}];
assert.deepEqual(await load(), expected);
response.data = [{title:'<script>alert(1)</script>',id:8}];
assert.equal((await load())[0].title, '<script>alert(1)</script>');
response.data = [{title:'Wrong',id:true}];
await assert.rejects(load(), /Invalid int32/);
response.data = [{title:'Unexpected',id:1,other:'x'}];
await assert.rejects(load(), /Unexpected fields/);
response.data = [{title:'Oversized',id:1}];
response.contentType = 'text/html';
await assert.rejects(load(), /Expected JSON/);
response.contentType = 'application/json';
response.status = 500;
await assert.rejects(load(), /HTTP status 500/);
response.status = 200;
response.data = [{title:'x'.repeat(500),id:1}];
await assert.rejects(load(), /byte limit/);
assert.equal(calls, 7);
console.log('PASS: 7 generated JS API scenarios');
'''


class JavaScriptRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js runtime not installed")
    def test_generated_module_in_node(self):
        service = ApiService("articles", "https://api.example.com", "/articles", max_bytes=256)
        schema = JsonResponse((JsonField("title", "text"), JsonField("id", "int32")), many=True)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "service.mjs").write_text(generate_fetch_module(service, schema), encoding="utf-8")
            (folder / "runtime.mjs").write_text(NODE_TEST, encoding="utf-8")
            result = subprocess.run(["node", str(folder / "runtime.mjs")], cwd=folder,
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS: 7", result.stdout)
