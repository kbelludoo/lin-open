/*
 * Pointer-free C11 kernel of uint64-scale stairstep exponential price.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, wide ints).
 * Half-up rpow uses checked signed * (uint64-scale only).
 * Original C; does not copy makerdao/dss src/abaci.sol (AGPL, hash-pinned).
 */
int st_u_mul_ok(int a, int b) {
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

int st_muldiv_round(int a, int b, int d) {
  int p;
  int t;
  if (d <= 0) {
    return 0;
  }
  if (st_u_mul_ok(a, b) == 0) {
    return 0;
  }
  p = a * b;
  t = p + (d / 2);
  if (t < p) {
    return 0;
  }
  return t / d;
}

int st_rpow(int x, int n, int b) {
  int z;
  if (b <= 0) {
    return 0;
  }
  if (n < 0) {
    return 0;
  }
  if (n == 0) {
    return b;
  }
  if (x == 0) {
    return 0;
  }
  z = x;
  if ((n - (n / 2) * 2) == 0) {
    z = b;
  }
  n = n / 2;
  while (n > 0) {
    x = st_muldiv_round(x, x, b);
    if ((n - (n / 2) * 2) == 1) {
      z = st_muldiv_round(z, x, b);
    }
    n = n / 2;
  }
  return z;
}

int st_price(int top, int dur, int cut, int step) {
  int n;
  int p;
  int prod;
  if (top < 0) {
    return 0;
  }
  if (dur < 0) {
    return 0;
  }
  if (cut < 0) {
    return 0;
  }
  if (step < 1) {
    return 0;
  }
  if (cut > 1000000000) {
    return 0;
  }
  n = dur / step;
  p = st_rpow(cut, n, 1000000000);
  if (st_u_mul_ok(top, p) == 0) {
    return 0;
  }
  prod = top * p;
  return prod / 1000000000;
}
