import assert from 'assert';
import { lookup, contentType, extension } from '../src/index.js';

let passed = 0;
try {
  assert.strictEqual(lookup('page.html'), 'text/html');
  passed++;
  assert.strictEqual(contentType('json'), 'application/json; charset=utf-8');
  passed++;
  assert.strictEqual(extension('text/plain'), 'txt');
  passed++;
  console.log('Overall: PASS (' + passed + ' tests passed)');
} catch(e) {
  console.error('Overall: FAIL', e.message);
  process.exit(1);
}
