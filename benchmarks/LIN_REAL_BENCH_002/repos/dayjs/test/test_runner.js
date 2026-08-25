import assert from 'assert';
import { isLeapYear, daysInMonth, addDays, formatDate } from '../src/index.js';

let passed = 0;
try {
  assert.strictEqual(isLeapYear(2024), true);
  assert.strictEqual(isLeapYear(2023), false);
  passed++;
  assert.strictEqual(daysInMonth(2024, 2), 29);
  passed++;
  assert.strictEqual(formatDate(new Date(2025, 0, 15)), '2025-01-15');
  passed++;
  console.log('Overall: PASS (' + passed + ' tests passed)');
} catch(e) {
  console.error('Overall: FAIL', e.message);
  process.exit(1);
}
