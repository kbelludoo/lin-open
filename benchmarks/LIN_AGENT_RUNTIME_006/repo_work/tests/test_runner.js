import { parseVersion, isValid } from '../src/parser.js';
import { compareVersions, gt, lt, gte, lte, eq } from '../src/comparator.js';
import { parseRange, satisfiesRange } from '../src/ranges.js';
import { maxSatisfying, minSatisfying } from '../src/satisfier.js';
import { checkSemverInvariants } from '../src/invariants.js';

export function runAllTests() {
  const results = [];

  function test(name, fn) {
    try {
      const pass = fn();
      results.push({ name, passed: Boolean(pass) });
    } catch (err) {
      results.push({ name, passed: false, error: err.message });
    }
  }

  // Test Suite
  test("valid_version_parsing", () => isValid("1.2.3") && isValid("v2.0.0-rc.1+build.123"));
  test("invalid_version_parsing", () => !isValid("invalid") && !isValid("1.2") && !isValid("1.2.3.4"));
  test("comparison_major", () => gt("2.0.0", "1.9.9"));
  test("comparison_minor", () => gt("1.3.0", "1.2.9"));
  test("comparison_patch", () => gt("1.2.4", "1.2.3"));
  test("comparison_prerelease", () => lt("1.0.0-alpha", "1.0.0") && lt("1.0.0-alpha.1", "1.0.0-alpha.beta"));
  test("caret_range_major", () => satisfiesRange("1.5.0", "^1.2.3") && !satisfiesRange("2.0.0", "^1.2.3"));
  test("caret_range_zero_minor", () => satisfiesRange("0.2.5", "^0.2.3") && !satisfiesRange("0.3.0", "^0.2.3"));
  test("tilde_range", () => satisfiesRange("1.2.9", "~1.2.3") && !satisfiesRange("1.3.0", "~1.2.3"));
  test("wildcard_range", () => satisfiesRange("99.99.99", "*"));
  test("max_satisfying", () => maxSatisfying(["1.0.0", "1.5.0", "2.0.0"], "^1.0.0") === "1.5.0");
  test("min_satisfying", () => minSatisfying(["1.2.0", "1.5.0", "2.0.0"], "^1.0.0") === "1.2.0");
  test("invariants", () => checkSemverInvariants().valid);

  const passedCount = results.filter(r => r.passed).length;
  const failedCount = results.length - passedCount;

  return {
    passed: failedCount === 0,
    total: results.length,
    passedCount,
    failedCount,
    failures: results.filter(r => !r.passed)
  };
}

if (process.argv[1] && process.argv[1].endsWith("test_runner.js")) {
  const res = runAllTests();
  console.log(`Tests: ${res.passedCount}/${res.total} passed. Overall: ${res.passed ? "PASS" : "FAIL"}`);
  if (!res.passed) {
    console.log("Failures:", res.failures);
  }
}
