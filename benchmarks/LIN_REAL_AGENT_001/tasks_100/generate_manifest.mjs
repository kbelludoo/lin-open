import fs from 'fs';
import path from 'path';

export function createTasks() {
  const tasks = [];

  // --- 1. UNIT BUGS (T001..T040) ---
  const unitPatterns = [
    {
      file: "src/parser.js",
      symbol: "parseVersion",
      issue: "Parsing fails on versions with leading 'v' or whitespace",
      flawed: "const regex = /^(\\d+)\\.(\\d+)\\.(\\d+)(?:-([0-9A-Za-z.-]+))?(?:\\+([0-9A-Za-z.-]+))?$/;",
      fixed: "const regex = /^v?(\\d+)\\.(\\d+)\\.(\\d+)(?:-([0-9A-Za-z.-]+))?(?:\\+([0-9A-Za-z.-]+))?$/;",
      test: "valid_version_parsing",
      invariant: "INV_PARSE_CLEAN"
    },
    {
      file: "src/comparator.js",
      symbol: "compareIdentifiers",
      issue: "Numeric identifiers compared as strings causing '10' < '2' inversion",
      flawed: "return a === b ? 0 : a > b ? 1 : -1;",
      fixed: "if (anum && bnum) { const na = parseInt(a, 10); const nb = parseInt(b, 10); return na === nb ? 0 : na > nb ? 1 : -1; }",
      test: "comparison_prerelease",
      invariant: "INV_NUMERIC_IDENTIFIERS"
    },
    {
      file: "src/comparator.js",
      symbol: "gt",
      issue: "Strict greater-than evaluates truthy on equal versions",
      flawed: "export function gt(v1, v2) { const c = compareVersions(v1, v2); return c !== null && c >= 0; }",
      fixed: "export function gt(v1, v2) { const c = compareVersions(v1, v2); return c !== null && c > 0; }",
      test: "comparison_major",
      invariant: "INV_STRICT_GT"
    },
    {
      file: "src/parser.js",
      symbol: "isValid",
      issue: "isValid returns true for null input",
      flawed: "export function isValid(versionStr) { return versionStr !== null; }",
      fixed: "export function isValid(versionStr) { return parseVersion(versionStr) !== null; }",
      test: "invalid_version_parsing",
      invariant: "INV_NULL_SAFETY"
    }
  ];

  for (let i = 1; i <= 40; i++) {
    const pat = unitPatterns[(i - 1) % unitPatterns.length];
    tasks.push({
      task_id: `T${String(i).padStart(3, '0')}`,
      type: "unit_bug",
      title: `[Unit Bug] ${pat.issue} (#${i})`,
      description: `Fix issue in ${pat.symbol} located in ${pat.file}: ${pat.issue}.`,
      target_file: pat.file,
      affected_symbols: [pat.symbol],
      affected_dependencies: [pat.file],
      flawed_snippet: pat.flawed,
      correct_snippet: pat.fixed,
      failing_test: pat.test,
      invariant: pat.invariant
    });
  }

  // --- 2. MULTI-MODULE REGRESSIONS (T041..T070) ---
  const multiPatterns = [
    {
      fileA: "src/comparator.js",
      fileB: "src/ranges.js",
      symbolA: "comparePrereleases",
      symbolB: "satisfiesRange",
      issue: "Prerelease precedence inversion breaks caret range satisfaction across modules",
      flawed: "if (preA.length === 0 && preB.length > 0) return -1;",
      fixed: "if (preA.length === 0 && preB.length > 0) return 1;",
      test: "caret_range_major",
      invariant: "INV_PRERELEASE_ISOLATION_BROKEN"
    },
    {
      fileA: "src/ranges.js",
      fileB: "src/satisfier.js",
      symbolA: "parseRange",
      symbolB: "maxSatisfying",
      issue: "Caret upper bound overflows major boundary leading to incorrect max version selection",
      flawed: "return [{ op: '>=', version: clean.slice(1) }, { op: '<=', version: `${base.major + 1}.0.0` }];",
      fixed: "return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `${base.major + 1}.0.0` }];",
      test: "max_satisfying",
      invariant: "INV_CARET_UPPER_EXCLUSIVE"
    },
    {
      fileA: "src/comparator.js",
      fileB: "src/invariants.js",
      symbolA: "compareVersions",
      symbolB: "checkSemverInvariants",
      issue: "Antisymmetry violation when comparing string representations",
      flawed: "if (p1.major !== p2.major) return p1.major < p2.major ? 1 : -1;",
      fixed: "if (p1.major !== p2.major) return p1.major > p2.major ? 1 : -1;",
      test: "invariants",
      invariant: "INV_ANTISYMMETRY_FAILED"
    }
  ];

  for (let i = 41; i <= 70; i++) {
    const pat = multiPatterns[(i - 41) % multiPatterns.length];
    tasks.push({
      task_id: `T${String(i).padStart(3, '0')}`,
      type: "multi_module_regression",
      title: `[Multi-Module] ${pat.issue} (#${i})`,
      description: `Regression spanning ${pat.fileA} and ${pat.fileB}: ${pat.issue}.`,
      target_file: pat.fileA,
      dependent_files: [pat.fileA, pat.fileB],
      affected_symbols: [pat.symbolA, pat.symbolB],
      affected_dependencies: [pat.fileA, pat.fileB],
      flawed_snippet: pat.flawed,
      correct_snippet: pat.fixed,
      failing_test: pat.test,
      invariant: pat.invariant
    });
  }

  // --- 3. COMPLEX EDGE CASES (T071..T100) ---
  const edgePatterns = [
    {
      file: "src/ranges.js",
      symbol: "parseRange",
      issue: "Zero-major caret range (^0.2.3) fails to constrain minor boundary at 0.3.0",
      flawed: "if (base.major > 0) { return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `${base.major + 1}.0.0` }]; } return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `1.0.0` }];",
      fixed: "if (base.major > 0) { return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `${base.major + 1}.0.0` }]; } if (base.minor > 0) { return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `0.${base.minor + 1}.0` }]; } return [{ op: '>=', version: clean.slice(1) }, { op: '<', version: `0.0.${base.patch + 1}` }];",
      test: "caret_range_zero_minor",
      invariant: "INV_ZERO_MAJOR_CARET_OVERFLOW"
    },
    {
      file: "src/ranges.js",
      symbol: "satisfiesRange",
      issue: "Prerelease version incorrectly satisfies normal release caret range",
      flawed: "if (p.prerelease.length > 0) { return true; }",
      fixed: "if (p.prerelease.length > 0 && target.prerelease.length === 0) { if (p.major !== target.major || p.minor !== target.minor || p.patch !== target.patch) { return false; } }",
      test: "invariants",
      invariant: "INV_PRERELEASE_ISOLATION_BROKEN"
    },
    {
      file: "src/satisfier.js",
      symbol: "minSatisfying",
      issue: "minSatisfying selects maximum instead of minimum version satisfying range",
      flawed: "if (!min || gt(v, min)) { min = v; }",
      fixed: "if (!min || lt(v, min)) { min = v; }",
      test: "min_satisfying",
      invariant: "INV_MIN_SATISFYING_MONOTONICITY"
    }
  ];

  for (let i = 71; i <= 100; i++) {
    const pat = edgePatterns[(i - 71) % edgePatterns.length];
    tasks.push({
      task_id: `T${String(i).padStart(3, '0')}`,
      type: "edge_case",
      title: `[Edge Case] ${pat.issue} (#${i})`,
      description: `Edge case in ${pat.symbol} in ${pat.file}: ${pat.issue}.`,
      target_file: pat.file,
      affected_symbols: [pat.symbol],
      affected_dependencies: [pat.file, "src/satisfier.js", "src/invariants.js"],
      flawed_snippet: pat.flawed,
      correct_snippet: pat.fixed,
      failing_test: pat.test,
      invariant: pat.invariant
    });
  }

  return tasks;
}

const manifest = createTasks();
fs.writeFileSync("benchmarks/LIN_REAL_AGENT_001/tasks_100/manifest.json", JSON.stringify(manifest, null, 2));
console.log(`Generated 100 tasks manifest: ${manifest.length} tasks recorded.`);
