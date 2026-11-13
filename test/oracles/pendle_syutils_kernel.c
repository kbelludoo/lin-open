/*
 * Pointer-free C11 kernel of uint64-scale Pendle SYUtils (ONE' = 1000).
 * Eligible for lin_from_c (no pointer sig, member-arrow, record types, fp, goto, wide ints).
 * Checked signed multiply fail-closes; not the 128-bit path of the LIN clone.
 * Original C; does not copy pendle-core-v2-public SYUtils.sol (GPL, hash-pinned).
 */
int psy_k_one(void) {
  return 1000;
}

int psy_k_mul_ok(int a, int b) {
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

int psy_k_floor_div(int a, int b) {
  if (b <= 0) {
    return 0;
  }
  if (a < 0) {
    return 0;
  }
  return a / b;
}

int psy_k_ceil_div(int a, int b) {
  int q;
  int r;
  if (b <= 0) {
    return 0;
  }
  if (a < 0) {
    return 0;
  }
  q = a / b;
  r = a - q * b;
  if (r == 0) {
    return q;
  }
  return q + 1;
}

int psy_k_sy_to_asset(int exchange_rate, int sy_amount) {
  int one;
  int prod;
  one = psy_k_one();
  if (psy_k_mul_ok(sy_amount, exchange_rate) == 0) {
    return 0;
  }
  prod = sy_amount * exchange_rate;
  return psy_k_floor_div(prod, one);
}

int psy_k_sy_to_asset_up(int exchange_rate, int sy_amount) {
  int one;
  int prod;
  one = psy_k_one();
  if (psy_k_mul_ok(sy_amount, exchange_rate) == 0) {
    return 0;
  }
  prod = sy_amount * exchange_rate;
  return psy_k_ceil_div(prod, one);
}

int psy_k_asset_to_sy(int exchange_rate, int asset_amount) {
  int one;
  int prod;
  one = psy_k_one();
  if (exchange_rate == 0) {
    return 0;
  }
  if (psy_k_mul_ok(asset_amount, one) == 0) {
    return 0;
  }
  prod = asset_amount * one;
  return psy_k_floor_div(prod, exchange_rate);
}

int psy_k_asset_to_sy_up(int exchange_rate, int asset_amount) {
  int one;
  int prod;
  one = psy_k_one();
  if (exchange_rate == 0) {
    return 0;
  }
  if (psy_k_mul_ok(asset_amount, one) == 0) {
    return 0;
  }
  prod = asset_amount * one;
  return psy_k_ceil_div(prod, exchange_rate);
}
