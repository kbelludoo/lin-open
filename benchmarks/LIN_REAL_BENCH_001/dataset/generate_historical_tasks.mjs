// Real-World Historical Bug Corpus Generator

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

export function createHistoricalTasks() {
  const tasks = [
    // 1. MINIMIST: Historical Issue #12 (Scientific notation number parse)
    {
      task_id: "MINIMIST_HIST_01",
      repo: "minimist",
      repo_dir: "repos/minimist",
      title: "minimist: isNumber fails on scientific exponent notation like 1e5",
      issue_description: "Calling parseArgs(['--val', '1e5']) parses '1e5' as string instead of 100000. isNumber regex fails to match exponential notation numbers.",
      failing_test_name: "test_scientific_notation",
      test_assertion_error: "AssertionError: expected argv.val to be 100000 (number), got '1e5' (string) at test/test_runner.js:18",
      ground_truth: {
        file: "lib/index.js",
        symbol: "isNumber",
        bug_find: "return /^[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(e[-+]?\\d+)?$/.test(x);",
        bug_replace: "return /^[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)$/.test(x); // Drops exponent matching"
      }
    },
    // 2. MINIMIST: Historical Issue #25 (Prototype pollution in setKey)
    {
      task_id: "MINIMIST_HIST_02",
      repo: "minimist",
      repo_dir: "repos/minimist",
      title: "minimist: prototype pollution via __proto__ in dotted keys",
      issue_description: "Passing '--__proto__.polluted=true' pollutes Object.prototype. setKey must prevent writes to __proto__ properties.",
      failing_test_name: "test_proto_pollution",
      test_assertion_error: "AssertionError: expected Object.prototype.polluted to be undefined, got true at test/test_runner.js:32",
      ground_truth: {
        file: "lib/index.js",
        symbol: "setKey",
        bug_find: "if (key === '__proto__') return; // Security fix",
        bug_replace: "// Vulnerable: missing proto check"
      }
    },
    // 3. MIME-TYPES: Historical Issue #42 (Case-sensitive charset lookup)
    {
      task_id: "MIME_HIST_01",
      repo: "mime-types",
      repo_dir: "repos/mime-types",
      title: "mime-types: contentType fails when uppercase mimetype string is passed",
      issue_description: "Calling contentType('TEXT/HTML') returns 'TEXT/HTML' without appending '; charset=utf-8'. Charset dictionary lookup is case-sensitive.",
      failing_test_name: "test_case_insensitive_content_type",
      test_assertion_error: "AssertionError: expected contentType('TEXT/HTML') to return 'text/html; charset=utf-8', got 'TEXT/HTML' at test/test_runner.js:14",
      ground_truth: {
        file: "src/index.js",
        symbol: "contentType",
        bug_find: "const cs = charsets[mime.toLowerCase()];",
        bug_replace: "const cs = charsets[mime]; // Case sensitive bug"
      }
    },
    // 4. MIME-TYPES: Historical Issue #50 (Null safety in extension())
    {
      task_id: "MIME_HIST_02",
      repo: "mime-types",
      repo_dir: "repos/mime-types",
      title: "mime-types: extension(null) throws TypeError",
      issue_description: "Calling extension(null) throws Cannot read properties of null (reading 'split') instead of returning false.",
      failing_test_name: "test_extension_null_safety",
      test_assertion_error: "AssertionError: expected extension(null) to be false, got exception at test/test_runner.js:22",
      ground_truth: {
        file: "src/index.js",
        symbol: "extension",
        bug_find: "if (!mime || typeof mime !== 'string') return false;",
        bug_replace: "if (mime === undefined) return false; // Missing null check"
      }
    }
  ];

  const outPath = path.join(ROOT, 'dataset/historical_bugs.json');
  fs.writeFileSync(outPath, JSON.stringify(tasks, null, 2));
  console.log(`[+] Generated ${tasks.length} Real-World Historical Bug Tasks at: ${outPath}`);
  return tasks;
}

createHistoricalTasks();
