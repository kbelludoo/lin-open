import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

export function generateHardTaskCorpus() {
  const tasks = [];

  const taskTemplates = [
    // 1. Parser subtle edge cases
    {
      type: "edge_case",
      file: "src/parser.js",
      symbol: "parseVersion",
      title: "Handle leading whitespace and optional leading 'v' with build metadata",
      bug_find: "const regex = /^v?(\\d+)\\.(\\d+)\\.(\\d+)(?:-([0-9A-Za-z.-]+))?(?:\\+([0-9A-Za-z.-]+))?$/;",
      bug_replace: "const regex = /^(\\d+)\\.(\\d+)\\.(\\d+)$/;",
      instruction: "The regex in parseVersion fails on versions with leading 'v', prerelease identifiers, and build metadata (e.g. 'v1.2.3-alpha.1+build.123'). Fix parseVersion regex to support optional 'v', prerelease tag, and build tag."
    },
    // 2. Comparator numeric prerelease ordering
    {
      type: "unit_bug",
      file: "src/comparator.js",
      symbol: "compareIdentifiers",
      title: "Numeric vs alphanumeric prerelease identifier precedence",
      bug_find: "if (anum && bnum) {\n    const na = parseInt(a, 10);\n    const nb = parseInt(b, 10);\n    return na === nb ? 0 : na > nb ? 1 : -1;\n  }",
      bug_replace: "if (anum && bnum) {\n    return a.length - b.length;\n  }",
      instruction: "In compareIdentifiers (src/comparator.js), when both identifiers are numeric, they must be compared by integer value (parseInt). Fix compareIdentifiers to return 0 for equal, 1 if a > b, -1 if a < b."
    },
    // 3. Multi-module range satisfaction
    {
      type: "multi_module_regression",
      file: "src/ranges.js",
      symbol: "parseRange",
      title: "Tilde range minor bump boundary for major.minor.patch",
      bug_find: "return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `${base.major}.${base.minor + 1}.0` }];",
      bug_replace: "return [{ op: '>=', version: clean.slice(1) }, { op: '<=', version: `${base.major}.${base.minor + 1}.0` }];",
      instruction: "In parseRange (src/ranges.js), tilde range '~1.2.3' must strictly bound to '< 1.3.0', but currently uses '<=' allowing 1.3.0 to leak. Fix upper bound operator to strict '<'."
    },
    // 4. Satisfier maxSatisfying edge case
    {
      type: "multi_module_regression",
      file: "src/satisfier.js",
      symbol: "maxSatisfying",
      title: "maxSatisfying returning empty string on non-satisfaction",
      bug_find: "return max;",
      bug_replace: "return max || '';",
      instruction: "maxSatisfying in src/satisfier.js must return null (not empty string or undefined) when no version satisfies the range. Ensure it returns null if no valid version was found."
    },
    // 5. Comparator gt() strictness
    {
      type: "edge_case",
      file: "src/comparator.js",
      symbol: "gt",
      title: "Strict gt() must return false for equal version inputs",
      bug_find: "return c !== null && c > 0;",
      bug_replace: "return c !== null && c >= 0;",
      instruction: "gt(v1, v2) in src/comparator.js is returning true when versions are equal. Fix gt to return true strictly when compareVersions(v1, v2) > 0."
    }
  ];

  for (let i = 1; i <= 50; i++) {
    const tmpl = taskTemplates[(i - 1) % taskTemplates.length];
    tasks.push({
      task_id: `HARD_T${String(i).padStart(2, '0')}`,
      type: tmpl.type,
      title: `[#${i}] ${tmpl.title}`,
      file: tmpl.file,
      symbol: tmpl.symbol,
      bug_find: tmpl.bug_find,
      bug_replace: tmpl.bug_replace,
      instruction: tmpl.instruction
    });
  }

  const outPath = path.join(ROOT, 'dataset/hard_tasks.json');
  fs.writeFileSync(outPath, JSON.stringify(tasks, null, 2));
  console.log(`[+] Generated 50 hard maintenance tasks at: ${outPath}`);
  return tasks;
}

generateHardTaskCorpus();
