import { satisfiesRange } from './ranges.js';
import { compareVersions, gt, lt } from './comparator.js';

export function maxSatisfying(versions, rangeStr) {
  let max = null;
  for (const v of versions) {
    if (satisfiesRange(v, rangeStr)) {
      if (!max || gt(v, max)) {
        max = v;
      }
    }
  }
  return max;
}

export function minSatisfying(versions, rangeStr) {
  let min = null;
  for (const v of versions) {
    if (satisfiesRange(v, rangeStr)) {
      if (!min || lt(v, min)) {
        min = v;
      }
    }
  }
  return min;
}
