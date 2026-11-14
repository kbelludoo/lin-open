/*
 * Pointer-free C11 kernel of uint64-scale Euler EVK IRMLinearKink.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy IRMLinearKink.sol (hash-pinned elsewhere).
 */
int eir_util_scale(void) {
  return 4294967295;
}

int eir_kink_half(void) {
  return 2147483648;
}

int eir_u_mul_ok(int a, int b) {
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

int eir_u_add_ok(int a, int b) {
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

int eir_auth_ok(int caller, int vault) {
  if (caller < 0) {
    return 0;
  }
  if (vault < 0) {
    return 0;
  }
  if (caller != vault) {
    return 0;
  }
  return 1;
}

int eir_util(int cash, int borrows) {
  int total;
  int scale;
  int u;
  if (cash < 0) {
    return 0;
  }
  if (borrows < 0) {
    return 0;
  }
  if (eir_u_add_ok(cash, borrows) == 0) {
    return 0;
  }
  total = cash + borrows;
  if (total == 0) {
    return 0;
  }
  scale = eir_util_scale();
  if (eir_u_mul_ok(borrows, scale) == 0) {
    return 0;
  }
  u = (borrows * scale) / total;
  if (u > scale) {
    return 0;
  }
  return u;
}

int eir_rate(int cash, int borrows, int base, int slope1, int slope2, int kink) {
  int u;
  int ir;
  int over;
  if (base < 0 || slope1 < 0 || slope2 < 0 || kink < 0) {
    return 0;
  }
  if (kink > eir_util_scale()) {
    return 0;
  }
  if (cash < 0 || borrows < 0) {
    return 0;
  }
  if (eir_u_add_ok(cash, borrows) == 0) {
    return 0;
  }
  if ((cash + borrows) != 0) {
    if (eir_u_mul_ok(borrows, eir_util_scale()) == 0) {
      return 0;
    }
  }
  u = eir_util(cash, borrows);
  ir = base;
  if (u <= kink) {
    if (eir_u_mul_ok(u, slope1) == 0) {
      return 0;
    }
    if (eir_u_add_ok(ir, u * slope1) == 0) {
      return 0;
    }
    return ir + (u * slope1);
  }
  if (eir_u_mul_ok(kink, slope1) == 0) {
    return 0;
  }
  if (eir_u_add_ok(ir, kink * slope1) == 0) {
    return 0;
  }
  ir = ir + (kink * slope1);
  over = u - kink;
  if (eir_u_mul_ok(slope2, over) == 0) {
    return 0;
  }
  if (eir_u_add_ok(ir, slope2 * over) == 0) {
    return 0;
  }
  return ir + (slope2 * over);
}

int eir_compute(int caller, int vault, int cash, int borrows, int base, int slope1, int slope2, int kink) {
  if (eir_auth_ok(caller, vault) == 0) {
    return 0;
  }
  return eir_rate(cash, borrows, base, slope1, slope2, kink);
}
