function deepEqual(a, b) {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") {
    return false;
  }
  if (Array.isArray(a) !== Array.isArray(b)) return false;

  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) return false;
    }
    return true;
  }

  const keysA = Object.keys(a).sort();
  const keysB = Object.keys(b).sort();
  if (keysA.length !== keysB.length) return false;
  for (let i = 0; i < keysA.length; i++) {
    if (keysA[i] !== keysB[i]) return false;
    if (!deepEqual(a[keysA[i]], b[keysB[i]])) return false;
  }
  return true;
}

export function validateBackendResults(backendName, oracleResults, backendResults) {
  const levels = ["L0", "L1", "L2", "L3"];
  const validation = {
    backend: backendName,
    passed: true,
    levels: {}
  };

  for (const lvl of levels) {
    const expected = oracleResults[lvl];
    const actual = backendResults[lvl];
    if (!actual || actual.length !== expected.length) {
      validation.passed = false;
      validation.levels[lvl] = {
        passed: false,
        error: `Length mismatch: expected ${expected.length}, got ${actual ? actual.length : 0}`
      };
      continue;
    }

    let mismatches = 0;
    for (let i = 0; i < expected.length; i++) {
      if (!deepEqual(expected[i], actual[i])) {
        mismatches++;
      }
    }

    const levelPassed = mismatches === 0;
    if (!levelPassed) {
      validation.passed = false;
    }

    validation.levels[lvl] = {
      passed: levelPassed,
      total: expected.length,
      matches: expected.length - mismatches,
      mismatches,
      matchRate: (expected.length - mismatches) / expected.length
    };
  }

  return validation;
}
