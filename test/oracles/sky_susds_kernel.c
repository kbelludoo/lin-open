/*
 * Pointer-free C11 kernel of uint64-scale sUSDS convertToAssets / _divup.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed * is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy sky-ecosystem/sdai SUsds.sol (AGPL, hash-pinned).
 */
int su_u_mul_ok(int a, int b) {
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

int su_divup(int x, int y) {
  if (x < 0) {
    return 0;
  }
  if (y < 1) {
    return 0;
  }
  if (x == 0) {
    return 0;
  }
  return ((x - 1) / y) + 1;
}

int su_to_assets(int shares, int chi) {
  int ray;
  if (shares < 0) {
    return 0;
  }
  if (chi < 1) {
    return 0;
  }
  if (su_u_mul_ok(shares, chi) == 0) {
    return 0;
  }
  ray = 1000;
  return (shares * chi) / ray;
}

int su_to_shares(int assets, int chi) {
  int ray;
  if (assets < 0) {
    return 0;
  }
  if (chi < 1) {
    return 0;
  }
  ray = 1000;
  if (su_u_mul_ok(assets, ray) == 0) {
    return 0;
  }
  return (assets * ray) / chi;
}

int su_preview_mint(int shares, int chi) {
  if (shares < 0) {
    return 0;
  }
  if (chi < 1) {
    return 0;
  }
  if (su_u_mul_ok(shares, chi) == 0) {
    return 0;
  }
  return su_divup(shares * chi, 1000);
}
