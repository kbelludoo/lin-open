/*
 * Pointer-free C11 kernel of uint64-scale Maker/Sky DssLitePsm sell/buy.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy DssLitePsm.sol (hash-pinned elsewhere).
 */
int psm_wad(void) {
  return 1000000000;
}

int psm_halted(void) {
  return -1;
}

int psm_u_mul_ok(int a, int b) {
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

int psm_u_add_ok(int a, int b) {
  int s;
  if (a < 0) {
    return 0;
  }
  if (b < 0) {
    return 0;
  }
  s = a + b;
  if (s < 0) {
    return 0;
  }
  if (s < a) {
    return 0;
  }
  return 1;
}

int psm_u_sub_ok(int a, int b) {
  if (a < 0) {
    return 0;
  }
  if (b < 0) {
    return 0;
  }
  if (a < b) {
    return 0;
  }
  return 1;
}

int psm_pow10(int n) {
  int p;
  int i;
  if (n < 0) {
    return 0;
  }
  if (n > 9) {
    return 0;
  }
  p = 1;
  i = 0;
  while (i < n) {
    if (psm_u_mul_ok(p, 10) == 0) {
      return 0;
    }
    p = p * 10;
    i = i + 1;
  }
  return p;
}

int psm_to18(int scale_dec, int gem_dec) {
  if (scale_dec < 0) {
    return 0;
  }
  if (gem_dec < 0) {
    return 0;
  }
  if (scale_dec < gem_dec) {
    return 0;
  }
  return psm_pow10(scale_dec - gem_dec);
}

int psm_gem_wad(int gem, int to18) {
  if (gem < 0) {
    return 0;
  }
  if (to18 < 0) {
    return 0;
  }
  if (psm_u_mul_ok(gem, to18) == 0) {
    return 0;
  }
  return gem * to18;
}

int psm_fee(int dai, int tin, int wad) {
  int q;
  int r;
  int hi;
  int lo;
  if (dai < 0) {
    return 0;
  }
  if (tin < 0) {
    return 0;
  }
  if (wad <= 0) {
    return 0;
  }
  if (tin > wad) {
    return 0;
  }
  if (tin == 0) {
    return 0;
  }
  q = dai / wad;
  r = dai - (q * wad);
  if (psm_u_mul_ok(q, tin) == 0) {
    return 0;
  }
  if (psm_u_mul_ok(r, tin) == 0) {
    return 0;
  }
  hi = q * tin;
  lo = (r * tin) / wad;
  if (psm_u_add_ok(hi, lo) == 0) {
    return 0;
  }
  return hi + lo;
}

int psm_sell(int gem, int to18, int tin, int wad) {
  int dai;
  int fee;
  if (tin == psm_halted()) {
    return 0;
  }
  if (wad <= 0) {
    return 0;
  }
  dai = psm_gem_wad(gem, to18);
  if (dai == 0) {
    return 0;
  }
  if (tin == 0) {
    return dai;
  }
  fee = psm_fee(dai, tin, wad);
  if (psm_u_sub_ok(dai, fee) == 0) {
    return 0;
  }
  return dai - fee;
}

int psm_buy(int gem, int to18, int tout, int wad) {
  int dai;
  int fee;
  if (tout == psm_halted()) {
    return 0;
  }
  if (wad <= 0) {
    return 0;
  }
  dai = psm_gem_wad(gem, to18);
  if (dai == 0) {
    return 0;
  }
  if (tout == 0) {
    return dai;
  }
  fee = psm_fee(dai, tout, wad);
  if (psm_u_add_ok(dai, fee) == 0) {
    return 0;
  }
  return dai + fee;
}

int psm_sell_nofee(int kissed, int gem, int to18, int wad) {
  if (kissed != 1) {
    return 0;
  }
  return psm_sell(gem, to18, 0, wad);
}
