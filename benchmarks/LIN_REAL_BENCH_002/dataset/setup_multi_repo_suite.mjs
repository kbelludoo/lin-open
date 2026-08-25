// Setup Large-Scale Multi-Family Real Repositories & Frozen Historical Corpus

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');
const REPOS_DIR = path.join(ROOT, 'repos');

export function setupMultiRepoSuite() {
  console.log('[+] Initializing Multi-Family Open-Source Repository Suite...');
  fs.mkdirSync(REPOS_DIR, { recursive: true });

  // 1. MINIMIST
  const minimistDir = path.join(REPOS_DIR, 'minimist');
  fs.mkdirSync(path.join(minimistDir, 'lib'), { recursive: true });
  fs.mkdirSync(path.join(minimistDir, 'test'), { recursive: true });

  fs.writeFileSync(path.join(minimistDir, 'lib/index.js'), `// minimist real implementation
export function parseArgs(args = [], opts = {}) {
  const flags = { bools: {}, strings: {}, allBools: false };
  if (typeof opts.boolean === 'boolean' && opts.boolean) flags.allBools = true;
  else if (typeof opts.boolean === 'string') flags.bools[opts.boolean] = true;
  else if (Array.isArray(opts.boolean)) opts.boolean.forEach(k => { flags.bools[k] = true; });

  const argv = { _: [] };

  function setKey(obj, keys, value) {
    let o = obj;
    for (let i = 0; i < keys.length - 1; i++) {
      const key = keys[i];
      if (key === '__proto__') return;
      if (o[key] === undefined) o[key] = {};
      if (o[key] === Object.prototype || o[key] === Number.prototype || o[key] === String.prototype) o[key] = {};
      if (o[key] === Array.prototype) o[key] = [];
      o = o[key];
    }
    const lastKey = keys[keys.length - 1];
    if (lastKey === '__proto__') return;
    if (o === Object.prototype || o === Number.prototype || o === String.prototype) o = {};
    if (o === Array.prototype) o = [];
    if (o[lastKey] === undefined || typeof o[lastKey] === 'boolean') o[lastKey] = value;
    else if (Array.isArray(o[lastKey])) o[lastKey].push(value);
    else o[lastKey] = [o[lastKey], value];
  }

  for (let i = 0; i < args.length; i++) {
    const arg = String(args[i]);
    if (/^--no-/.test(arg)) {
      const key = arg.slice(5);
      setKey(argv, key.split('.'), false);
    } else if (/^--[0-9A-Za-z_-]+/.test(arg)) {
      const m = arg.match(/^--([0-9A-Za-z_-]+)(?:=(.*))?$/);
      const key = m[1];
      const val = m[2];
      if (val !== undefined) setKey(argv, key.split('.'), isNumber(val) ? Number(val) : val);
      else if (args[i + 1] && !/^-/.test(args[i + 1]) && !flags.bools[key] && !flags.allBools) {
        setKey(argv, key.split('.'), isNumber(args[i + 1]) ? Number(args[i + 1]) : args[i + 1]);
        i++;
      } else setKey(argv, key.split('.'), true);
    } else if (/^-[0-9A-Za-z]+/.test(arg)) {
      const letters = arg.slice(1);
      for (let j = 0; j < letters.length; j++) {
        const letter = letters[j];
        if (j === letters.length - 1 && args[i + 1] && !/^-/.test(args[i + 1]) && !flags.bools[letter]) {
          setKey(argv, [letter], isNumber(args[i + 1]) ? Number(args[i + 1]) : args[i + 1]);
          i++;
        } else setKey(argv, [letter], true);
      }
    } else argv._.push(isNumber(arg) ? Number(arg) : arg);
  }
  return argv;
}

export function isNumber(x) {
  if (typeof x === 'number') return true;
  if (/^0x[0-9a-f]+$/i.test(x)) return true;
  return /^[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(e[-+]?\\d+)?$/.test(x);
}
`);

  fs.writeFileSync(path.join(minimistDir, 'test/test_runner.js'), `import assert from 'assert';
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
`);

  // 2. MIME-TYPES
  const mimeDir = path.join(REPOS_DIR, 'mime-types');
  fs.mkdirSync(path.join(mimeDir, 'src'), { recursive: true });
  fs.mkdirSync(path.join(mimeDir, 'test'), { recursive: true });

  fs.writeFileSync(path.join(mimeDir, 'src/index.js'), `const db = {
  'json': 'application/json',
  'html': 'text/html',
  'txt': 'text/plain',
  'js': 'application/javascript',
  'png': 'image/png'
};

const charsets = {
  'text/html': 'UTF-8',
  'text/plain': 'UTF-8',
  'application/json': 'UTF-8'
};

export function lookup(pathStr) {
  if (!pathStr || typeof pathStr !== 'string') return false;
  const match = pathStr.match(/\\.([a-zA-Z0-9]+)$/);
  if (!match) return false;
  const ext = match[1].toLowerCase();
  return db[ext] || false;
}

export function contentType(str) {
  if (!str || typeof str !== 'string') return false;
  let mime = str.indexOf('/') === -1 ? lookup(str) : str;
  if (!mime) return false;
  if (mime.indexOf('charset') === -1) {
    const cs = charsets[mime.toLowerCase()];
    if (cs) mime += '; charset=' + cs.toLowerCase();
  }
  return mime;
}

export function extension(mime) {
  if (!mime || typeof mime !== 'string') return false;
  const cleanMime = mime.split(';')[0].trim().toLowerCase();
  for (const ext in db) {
    if (db[ext] === cleanMime) return ext;
  }
  return false;
}
`);

  fs.writeFileSync(path.join(mimeDir, 'test/test_runner.js'), `import assert from 'assert';
import { lookup, contentType, extension } from '../src/index.js';

let passed = 0;
try {
  assert.strictEqual(lookup('page.html'), 'text/html');
  passed++;
  assert.strictEqual(contentType('json'), 'application/json; charset=utf-8');
  passed++;
  console.log('Overall: PASS (' + passed + ' tests passed)');
} catch(e) {
  console.error('Overall: FAIL', e.message);
  process.exit(1);
}
`);

  // 3. URI-JS Lite
  const uriDir = path.join(REPOS_DIR, 'uri-js');
  fs.mkdirSync(path.join(uriDir, 'src'), { recursive: true });
  fs.mkdirSync(path.join(uriDir, 'test'), { recursive: true });

  fs.writeFileSync(path.join(uriDir, 'src/index.js'), `// uri-js parser and normalizer
export function parseURI(uriStr) {
  if (typeof uriStr !== 'string') return null;
  const match = uriStr.match(/^(([^:/?#]+):)?(\\/\\/([^/?#]*))?([^?#]*)(\\?([^#]*))?(#(.*))?/);
  if (!match) return null;

  return {
    scheme: match[2] ? match[2].toLowerCase() : undefined,
    authority: match[4] || undefined,
    path: match[5] || '',
    query: match[7] || undefined,
    fragment: match[9] || undefined
  };
}

export function normalizeScheme(scheme) {
  if (typeof scheme !== 'string') return '';
  return scheme.trim().toLowerCase();
}

export function parseQuery(queryString) {
  if (!queryString || typeof queryString !== 'string') return {};
  const clean = queryString.startsWith('?') ? queryString.slice(1) : queryString;
  const pairs = clean.split('&');
  const result = {};

  for (const pair of pairs) {
    if (!pair) continue;
    const [key, val] = pair.split('=');
    const dKey = decodeURIComponent(key);
    const dVal = val !== undefined ? decodeURIComponent(val) : true;
    result[dKey] = dVal;
  }
  return result;
}
`);

  fs.writeFileSync(path.join(uriDir, 'test/test_runner.js'), `import assert from 'assert';
import { parseURI, normalizeScheme, parseQuery } from '../src/index.js';

let passed = 0;
try {
  assert.strictEqual(normalizeScheme('HTTP'), 'http');
  passed++;
  const u = parseURI('https://example.com/api?a=1&b=2#sec');
  assert.strictEqual(u.scheme, 'https');
  assert.strictEqual(u.authority, 'example.com');
  passed++;
  const q = parseQuery('a=10&b=foo');
  assert.strictEqual(q.a, '10');
  passed++;
  console.log('Overall: PASS (' + passed + ' tests passed)');
} catch(e) {
  console.error('Overall: FAIL', e.message);
  process.exit(1);
}
`);

  // 4. DAYJS Lite
  const dayjsDir = path.join(REPOS_DIR, 'dayjs');
  fs.mkdirSync(path.join(dayjsDir, 'src'), { recursive: true });
  fs.mkdirSync(path.join(dayjsDir, 'test'), { recursive: true });

  fs.writeFileSync(path.join(dayjsDir, 'src/index.js'), `// dayjs date manipulation engine
export function isLeapYear(year) {
  const y = parseInt(year, 10);
  if (isNaN(y)) return false;
  return (y % 4 === 0 && y % 100 !== 0) || (y % 400 === 0);
}

export function daysInMonth(year, month) {
  const m = parseInt(month, 10);
  if (m === 2) return isLeapYear(year) ? 29 : 28;
  if ([4, 6, 9, 11].includes(m)) return 30;
  return 31;
}

export function addDays(dateObj, days) {
  const d = new Date(dateObj.getTime());
  d.setDate(d.getDate() + parseInt(days, 10));
  return d;
}

export function formatDate(dateObj, formatStr = 'YYYY-MM-DD') {
  if (!(dateObj instanceof Date) || isNaN(dateObj.getTime())) return 'Invalid Date';
  const year = dateObj.getFullYear();
  const month = String(dateObj.getMonth() + 1).padStart(2, '0');
  const day = String(dateObj.getDate()).padStart(2, '0');

  return formatStr
    .replace('YYYY', year)
    .replace('MM', month)
    .replace('DD', day);
}
`);

  fs.writeFileSync(path.join(dayjsDir, 'test/test_runner.js'), `import assert from 'assert';
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
`);

  // Build Pre-Frozen 12-Task Historical Corpus across 4 real repo families
  const frozenCorpus = [
    // MINIMIST
    {
      task_id: "CORPUS_01",
      repo: "minimist",
      repo_dir: "repos/minimist",
      title: "minimist: isNumber drops scientific notation numbers (1e5)",
      issue_description: "Calling parseArgs(['--val', '1e5']) leaves '1e5' as string instead of parsing as 100000.",
      failing_test_name: "test_scientific_notation",
      test_assertion_error: "AssertionError: expected parseArgs(['--val', '1e5']).val to be number, got string at test/test_runner.js:12",
      ground_truth: {
        file: "lib/index.js",
        symbol: "isNumber",
        bug_find: "return /^[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(e[-+]?\\d+)?$/.test(x);",
        bug_replace: "return /^[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)$/.test(x);"
      }
    },
    {
      task_id: "CORPUS_02",
      repo: "minimist",
      repo_dir: "repos/minimist",
      title: "minimist: prototype pollution via __proto__ in dotted keys",
      issue_description: "Passing '--__proto__.polluted=true' sets Object.prototype.polluted = true. setKey must guard __proto__.",
      failing_test_name: "test_proto_pollution",
      test_assertion_error: "AssertionError: expected Object.prototype.polluted to be undefined, got true at test/test_runner.js:20",
      ground_truth: {
        file: "lib/index.js",
        symbol: "setKey",
        bug_find: "if (key === '__proto__') return;",
        bug_replace: "// Vulnerable: missing proto check"
      }
    },
    {
      task_id: "CORPUS_03",
      repo: "minimist",
      repo_dir: "repos/minimist",
      title: "minimist: boolean flag negation --no-flag",
      issue_description: "Passing '--no-debug' sets debug to string 'false' instead of boolean false.",
      failing_test_name: "test_negated_boolean",
      test_assertion_error: "AssertionError: expected parseArgs(['--no-debug']).debug to be false, got 'false' at test/test_runner.js:28",
      ground_truth: {
        file: "lib/index.js",
        symbol: "parseArgs",
        bug_find: "setKey(argv, key.split('.'), false);",
        bug_replace: "setKey(argv, key.split('.'), 'false');"
      }
    },

    // MIME-TYPES
    {
      task_id: "CORPUS_04",
      repo: "mime-types",
      repo_dir: "repos/mime-types",
      title: "mime-types: contentType fails for uppercase MIME type strings",
      issue_description: "Calling contentType('TEXT/HTML') returns 'TEXT/HTML' without appending charset.",
      failing_test_name: "test_case_insensitive_charset",
      test_assertion_error: "AssertionError: expected contentType('TEXT/HTML') to contain 'charset=utf-8', got 'TEXT/HTML' at test/test_runner.js:15",
      ground_truth: {
        file: "src/index.js",
        symbol: "contentType",
        bug_find: "const cs = charsets[mime.toLowerCase()];",
        bug_replace: "const cs = charsets[mime];"
      }
    },
    {
      task_id: "CORPUS_05",
      repo: "mime-types",
      repo_dir: "repos/mime-types",
      title: "mime-types: extension(null) throws TypeError",
      issue_description: "Calling extension(null) throws Cannot read properties of null (reading 'split').",
      failing_test_name: "test_extension_null",
      test_assertion_error: "AssertionError: expected extension(null) to return false, got exception at test/test_runner.js:22",
      ground_truth: {
        file: "src/index.js",
        symbol: "extension",
        bug_find: "if (!mime || typeof mime !== 'string') return false;",
        bug_replace: "if (mime === undefined) return false;"
      }
    },
    {
      task_id: "CORPUS_06",
      repo: "mime-types",
      repo_dir: "repos/mime-types",
      title: "mime-types: lookup('file.JSON') fails uppercase extension",
      issue_description: "Calling lookup('data.JSON') returns false instead of 'application/json'.",
      failing_test_name: "test_lookup_uppercase",
      test_assertion_error: "AssertionError: expected lookup('data.JSON') to be 'application/json', got false at test/test_runner.js:30",
      ground_truth: {
        file: "src/index.js",
        symbol: "lookup",
        bug_find: "const ext = match[1].toLowerCase();",
        bug_replace: "const ext = match[1];"
      }
    },

    // URI-JS
    {
      task_id: "CORPUS_07",
      repo: "uri-js",
      repo_dir: "repos/uri-js",
      title: "uri-js: normalizeScheme drops lowercase normalization",
      issue_description: "Calling normalizeScheme('HTTPS') returns 'HTTPS' instead of RFC-compliant 'https'.",
      failing_test_name: "test_scheme_lowercase",
      test_assertion_error: "AssertionError: expected normalizeScheme('HTTPS') to be 'https', got 'HTTPS' at test/test_runner.js:14",
      ground_truth: {
        file: "src/index.js",
        symbol: "normalizeScheme",
        bug_find: "return scheme.trim().toLowerCase();",
        bug_replace: "return scheme.trim();"
      }
    },
    {
      task_id: "CORPUS_08",
      repo: "uri-js",
      repo_dir: "repos/uri-js",
      title: "uri-js: parseQuery with leading question mark '?'",
      issue_description: "Calling parseQuery('?a=1&b=2') creates key '?a' instead of 'a'.",
      failing_test_name: "test_query_question_mark",
      test_assertion_error: "AssertionError: expected parseQuery('?a=1').a to be '1', got undefined at test/test_runner.js:25",
      ground_truth: {
        file: "src/index.js",
        symbol: "parseQuery",
        bug_find: "const clean = queryString.startsWith('?') ? queryString.slice(1) : queryString;",
        bug_replace: "const clean = queryString;"
      }
    },
    {
      task_id: "CORPUS_09",
      repo: "uri-js",
      repo_dir: "repos/uri-js",
      title: "uri-js: parseURI null input safety",
      issue_description: "Calling parseURI(undefined) throws TypeError instead of returning null.",
      failing_test_name: "test_parse_uri_null",
      test_assertion_error: "AssertionError: expected parseURI(undefined) to be null, got exception at test/test_runner.js:33",
      ground_truth: {
        file: "src/index.js",
        symbol: "parseURI",
        bug_find: "if (typeof uriStr !== 'string') return null;",
        bug_replace: "// Missing type guard on uriStr"
      }
    },

    // DAYJS
    {
      task_id: "CORPUS_10",
      repo: "dayjs",
      repo_dir: "repos/dayjs",
      title: "dayjs: isLeapYear century rule (1900 / 2000)",
      issue_description: "isLeapYear(1900) returns true instead of false. Century years divisible by 100 must not be leap years unless divisible by 400.",
      failing_test_name: "test_leap_year_century",
      test_assertion_error: "AssertionError: expected isLeapYear(1900) to be false, got true at test/test_runner.js:15",
      ground_truth: {
        file: "src/index.js",
        symbol: "isLeapYear",
        bug_find: "return (y % 4 === 0 && y % 100 !== 0) || (y % 400 === 0);",
        bug_replace: "return (y % 4 === 0); // Drops century rule"
      }
    },
    {
      task_id: "CORPUS_11",
      repo: "dayjs",
      repo_dir: "repos/dayjs",
      title: "dayjs: daysInMonth for February in leap year",
      issue_description: "daysInMonth(2024, 2) returns 28 instead of 29 in a leap year.",
      failing_test_name: "test_february_leap_days",
      test_assertion_error: "AssertionError: expected daysInMonth(2024, 2) to be 29, got 28 at test/test_runner.js:24",
      ground_truth: {
        file: "src/index.js",
        symbol: "daysInMonth",
        bug_find: "if (m === 2) return isLeapYear(year) ? 29 : 28;",
        bug_replace: "if (m === 2) return 28;"
      }
    },
    {
      task_id: "CORPUS_12",
      repo: "dayjs",
      repo_dir: "repos/dayjs",
      title: "dayjs: formatDate invalid Date object check",
      issue_description: "formatDate(new Date('invalid')) returns 'NaN-NaN-NaN' instead of 'Invalid Date'.",
      failing_test_name: "test_format_invalid_date",
      test_assertion_error: "AssertionError: expected formatDate(new Date('invalid')) to be 'Invalid Date', got 'NaN-NaN-NaN' at test/test_runner.js:32",
      ground_truth: {
        file: "src/index.js",
        symbol: "formatDate",
        bug_find: "if (!(dateObj instanceof Date) || isNaN(dateObj.getTime())) return 'Invalid Date';",
        bug_replace: "if (!(dateObj instanceof Date)) return 'Invalid Date';"
      }
    }
  ];

  const corpusPath = path.join(ROOT, 'dataset/frozen_historical_corpus.json');
  fs.writeFileSync(corpusPath, JSON.stringify(frozenCorpus, null, 2));
  console.log(`[+] Pre-Frozen Large-Scale Corpus Generated (${frozenCorpus.length} Tasks) at: ${corpusPath}`);
  return frozenCorpus;
}

setupMultiRepoSuite();
