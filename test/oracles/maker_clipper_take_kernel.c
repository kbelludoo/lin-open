/*
 * Pointer-free C11 kernel of uint64-scale Clipper.take slice*price + chost.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed * is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss clip.sol (AGPL, hash-pinned elsewhere).
 */
int ct_u_mul_ok(int a, int b) {
  int p;
  if (a < 0) {
    return 0;
  }
  if (b < 0) {
    return 0;
  }
  if (a == 0) {
    return 1;
  }
  if (b == 0) {
    return 1;
  }
  p = a * b;
  if (p < 0) {
    return 0;
  }
  if (p / a != b) {
    return 0;
  }
  return 1;
}

int ct_min(int a, int b) {
  if (a < b) {
    return a;
  }
  return b;
}

int ct_take_ok(int tab, int lot, int amt, int maxp, int price, int chost, int running, int done, int stopped) {
  int slice;
  int owe;
  int tab_cap;
  int partial;
  int rem;
  if (stopped >= 3) {
    return 0;
  }
  if (running != 1) {
    return 0;
  }
  if (done != 0) {
    return 0;
  }
  if (price < 1) {
    return 0;
  }
  if (tab < 0) {
    return 0;
  }
  if (maxp < price) {
    return 0;
  }
  slice = ct_min(lot, amt);
  if (ct_u_mul_ok(slice, price) == 0) {
    return 0;
  }
  owe = slice * price;
  tab_cap = 0;
  if (tab < owe) {
    tab_cap = 1;
  }
  if (tab_cap == 1) {
    owe = tab;
    slice = owe / price;
  }
  partial = 0;
  if (tab_cap == 0) {
    if (owe < tab) {
      if (slice < lot) {
        partial = 1;
      }
    }
  }
  if (partial == 1) {
    rem = tab - owe;
    if (rem < chost) {
      if (tab <= chost) {
        return 0;
      }
    }
  }
  return 1;
}
