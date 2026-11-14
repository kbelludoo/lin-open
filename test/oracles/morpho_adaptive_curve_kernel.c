/*
 * Pointer-free C11 kernel of uint64-scale AdaptiveCurve _curve (WAD'=1000).
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Toy scale only; production oracle uses signed 128-bit WAD=1e18.
 * Original C; does not copy morpho-org/morpho-blue-irm Solidity (MIT, hash-pinned).
 */
int ac_k_curve(int rate, int err) {
  int coeff;
  int wad;
  wad = 1000;
  if (err < 0) {
    coeff = 750;
  } else {
    coeff = 3000;
  }
  return ((coeff * err / wad) + wad) * rate / wad;
}

int ac_k_bound(int x, int lo, int hi) {
  if (x < lo) {
    return lo;
  }
  if (x > hi) {
    return hi;
  }
  return x;
}

int ac_k_require_pos(int x) {
  if (x > 0) {
    return x;
  }
  return 0;
}
