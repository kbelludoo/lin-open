import assert from 'assert';
import { parseArgs, isNumber } from '../lib/index.js';

let passed = 0;
try {
  assert.strictEqual(parseArgs(['--foo', 'bar']).foo, 'bar');
  passed++;
  assert.strictEqual(parseArgs(['-n', '123']).n, 123);
  passed++;
  assert.strictEqual(parseArgs(['--no-moo']).moo, false);
  passed++;
  console.log('Overall: PASS (' + passed + ' tests passed)');
} catch(e) {
  console.error('Overall: FAIL', e.message);
  process.exit(1);
}
