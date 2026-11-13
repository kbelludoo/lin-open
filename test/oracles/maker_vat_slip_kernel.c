/*
 * Pointer-free C11 kernel of uint64-scale vat.slip signed _add + wards.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed + is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss vat.sol (AGPL, hash-pinned elsewhere).
 */
int sl_s_add_ok(int x, int y) {
  int s;
  if (x < 0) {
    return 0;
  }
  s = x + y;
  if (y >= 0) {
    if (s < 0) {
      return 0;
    }
    if (s < x) {
      return 0;
    }
    return 1;
  }
  if (s < 0) {
    return 0;
  }
  if (s > x) {
    return 0;
  }
  return 1;
}

int sl_s_add(int x, int y) {
  if (sl_s_add_ok(x, y) == 0) {
    return 0;
  }
  return x + y;
}

int sl_slip_ok(int gem, int wad, int wards) {
  if (gem < 0) {
    return 0;
  }
  if (wards != 1) {
    return 0;
  }
  return sl_s_add_ok(gem, wad);
}

int sl_new_gem(int gem, int wad, int wards) {
  if (sl_slip_ok(gem, wad, wards) == 0) {
    return 0;
  }
  return sl_s_add(gem, wad);
}
