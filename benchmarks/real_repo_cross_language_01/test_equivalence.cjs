#!/usr/bin/env node
// API EQUIVALENCE: Python vs TypeScript ms library
// Verifies identical outputs for identical inputs across languages

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const TEST_CASES = [
  '100', '1m', '1h', '2d', '1y', '1.5h', '-100ms', '100 milliseconds', '2.5 hrs',
  '1mo', '2w', '30s', '500', '10s', '2.5m', '1.25d', '0.5h'
];

const FORMAT_CASES = [100, 60000, 3600000, 172800000, 31557600000, -5400000, 0, 1500, 86400000, 2592000000];

// Run Python and capture outputs
console.log('=== API EQUIVALENCE: Python vs TypeScript ===');
console.log('');

// Python parse + format
const pyScript = `
import json, sys
sys.path.insert(0, '.')
from ms_library import parse, format_ms

results = {"parse": {}, "format": {}}
for case in ${JSON.stringify(TEST_CASES)}:
    try:
        val = parse(case)
        results["parse"][case] = val
    except Exception as e:
        results["parse"][case] = str(e)

for val in ${JSON.stringify(FORMAT_CASES)}:
    try:
        results["format"][str(val)] = format_ms(val)
    except Exception as e:
        results["format"][str(val)] = str(e)

print(json.dumps(results))
`;

fs.writeFileSync(path.join(__dirname, '_py_equiv.py'), pyScript);

let pyResults;
try {
  const out = execSync(
    '"C:\\Program Files\\Python314\\python.exe" _py_equiv.py',
    { cwd: __dirname, encoding: 'utf8', stdio: 'pipe' }
  );
  pyResults = JSON.parse(out.trim());
} catch (e) {
  console.log('Python failed:', e.stdout || e.message);
  process.exit(1);
}

// TypeScript parse + format
const tsScript = `
import { parse, format } from '../real_repo_ms/src/index.ts';

const results: Record<string, any> = {"parse": {}, "format": {}};
const testCases = ${JSON.stringify(TEST_CASES)};
const formatCases = ${JSON.stringify(FORMAT_CASES)};

for (const t of testCases) {
  try {
    results["parse"][t] = parse(t);
  } catch (e: any) {
    results["parse"][t] = e.message;
  }
}

for (const v of formatCases) {
  try {
    results["format"][String(v)] = format(v);
  } catch (e: any) {
    results["format"][String(v)] = e.message;
  }
}

console.log(JSON.stringify(results));
`;

fs.writeFileSync(path.join(__dirname, '_ts_equiv.ts'), tsScript);

let tsResults;
try {
  const out = execSync(
    'node --experimental-strip-types _ts_equiv.ts',
    { cwd: __dirname, encoding: 'utf8', stdio: 'pipe' }
  );
  tsResults = JSON.parse(out.trim());
} catch (e) {
  console.log('TypeScript failed:', e.stdout || e.message);
  process.exit(1);
}

// Compare
let parseMatch = 0, parseMismatch = 0;
let formatMatch = 0, formatMismatch = 0;

console.log('PARSE EQUIVALENCE:');
for (const t of TEST_CASES) {
  const py = pyResults.parse[t];
  const ts = tsResults.parse[t];
  const match = py === ts;
  if (match) parseMatch++; else parseMismatch++;
  const status = match ? 'PASS' : 'FAIL';
  console.log(`  ${status}  parse("${t}")  py=${py}  ts=${ts}`);
}

console.log('');
console.log('FORMAT EQUIVALENCE:');
for (const v of FORMAT_CASES) {
  const key = String(v);
  const py = pyResults.format[key];
  const ts = tsResults.format[key];
  const match = py === ts;
  if (match) formatMatch++; else formatMismatch++;
  const status = match ? 'PASS' : 'FAIL';
  console.log(`  ${status}  format(${v})  py="${py}"  ts="${ts}"`);
}

console.log('');
console.log('=== SUMMARY ===');
console.log(`Parse: ${parseMatch}/${parseMatch + parseMismatch} matched`);
console.log(`Format: ${formatMatch}/${formatMatch + formatMismatch} matched`);
const totalMatch = parseMatch + formatMatch;
const total = parseMatch + parseMismatch + formatMatch + formatMismatch;
console.log(`Overall: ${totalMatch}/${total} matched (${(totalMatch/total*100).toFixed(1)}%)`);

if (parseMismatch + formatMismatch > 0) {
  console.log('');
  console.log('MISMATCHES DETECTED - requires investigation');
} else {
  console.log('');
  console.log('ALL OUTPUTS EQUIVALENT - cross-language semantic preservation confirmed');
}
