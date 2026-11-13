/*
 * Pointer-free C11 kernel of uint64-scale Dutch-auction linear price.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, wide ints).
 * Naive signed * is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss src/abaci.sol (AGPL, hash-pinned).
 */
int ab_u_mul_ok(int a, int b) {
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

int ab_factor(int dur, int tau) {
  int rem;
  int ray;
  if (dur < 0) {
    return 0;
  }
  if (tau < 1) {
    return 0;
  }
  if (dur >= tau) {
    return 0;
  }
  rem = tau - dur;
  ray = 1000000000;
  if (ab_u_mul_ok(rem, ray) == 0) {
    return 0;
  }
  return (rem * ray) / tau;
}

int ab_price(int top, int dur, int tau) {
  int f;
  if (top < 0) {
    return 0;
  }
  if (dur < 0) {
    return 0;
  }
  if (tau < 1) {
    return 0;
  }
  if (dur >= tau) {
    return 0;
  }
  f = ab_factor(dur, tau);
  if (ab_u_mul_ok(top, f) == 0) {
    return 0;
  }
  return (top * f) / 1000000000;
}
