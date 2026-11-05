"""Deterministic Python/Node traces for examples, overflow and intermediate derives."""
import json
from pathlib import Path
import random
import shutil
import subprocess
import unittest
from sedrava_records import plain
from sedrava_core import parse, transition
from sedrava_syntax import document_kind
from web_codegen import generate

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('node'), 'Node.js required for differential conformance')
class AlphaConformance(unittest.TestCase):
    def test_example_and_boundary_traces(self):
        sources = [p.read_text(encoding='utf-8') for p in sorted((ROOT / 'examples').glob('*.sdr')) if p.name != 'timer.sdr' and document_kind(p.read_text(encoding='utf-8')) == 'app']
        sources.append('''app "Boundaries"
state n = -2147483648
state other = 0
derive echo = n + 0
action negate: n = -n
action max: n = 2147483647
action overflow:
    other = 1
    n = n + 1
action reset: n = 0
screen main:
    value n
''')
        sources.append('''app "Intermediate derive"
state n = 0
derive doubled = n * 2
action bad:
    n = 2147483647
    n = 0
action good: n = 10
screen main:
    value doubled
''')
        rng = random.Random(9001)
        payload = []
        expected = []
        for source in sources:
            program = parse(source)
            sequence = [rng.choice(list(program.actions)) for _ in range(80)]
            trace = []
            state = program.states.copy()
            for action in sequence:
                try:
                    state, accepted = transition(program, state, action)
                    error = False
                except ValueError:
                    error = True
                trace.append({'state': {k: plain(v) for k,v in state.items()}, 'error': error})
            expected.append(trace)
            payload.append({'script': generate(source).split('<script>', 1)[1].split('</script>', 1)[0], 'sequence': sequence})
        runner = r'''
const vm = require('node:vm');
const data = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const output = data.map(item => {
  const context = vm.createContext({document:{querySelectorAll:()=>[],getElementById:()=>null}});
  vm.runInContext(item.script, context);
  const actions = vm.runInContext('actions', context);
  let state = vm.runInContext('({...initialState})', context);
  return item.sequence.map(action => {
    let error = false;
    try { state = actions[action](state); } catch (_) { error = true; }
    return {state: JSON.parse(JSON.stringify(state)), error};
  });
});
process.stdout.write(JSON.stringify(output));
'''
        result = subprocess.run(['node', '-e', runner], input=json.dumps(payload), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
