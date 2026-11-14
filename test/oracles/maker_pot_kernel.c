/*
 * Pointer-free C11 kernel of uint64-scale Maker/Sky Pot.drip/join/exit.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * rpow uses wrapping-detect half-up; production oracle uses unsigned __int128.
 * Original C; does not copy makerdao/dss pot.sol (AGPL, hash-pinned elsewhere).
 */
int pot_u_mul_ok(int a, int b) {
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

int pot_u_add_ok(int a, int b) {
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

int pot_u_sub_ok(int a, int b) {
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

int pot_rpow(int x, int n, int base) {
  int z;
  int odd;
  if (base <= 0) {
    return 0;
  }
  if (n == 0) {
    return base;
  }
  if (x == 0) {
    return 0;
  }
  z = x;
  if (n - (n / 2) * 2 == 0) {
    z = base;
  }
  n = n / 2;
  while (n > 0) {
    if (pot_u_mul_ok(x, x) == 0) {
      return 0;
    }
    x = (x * x + base / 2) / base;
    odd = n - (n / 2) * 2;
    if (odd == 1) {
      if (pot_u_mul_ok(z, x) == 0) {
        return 0;
      }
      z = (z * x + base / 2) / base;
    }
    n = n / 2;
  }
  return z;
}

int pot_drip_ok(int dsr, int chi, int rho, int now_ts, int pie_total) {
  int rp;
  int tmp;
  int delta;
  if (dsr < 0) {
    return 0;
  }
  if (chi < 0) {
    return 0;
  }
  if (now_ts < rho) {
    return 0;
  }
  if (pie_total < 0) {
    return 0;
  }
  rp = pot_rpow(dsr, now_ts - rho, 1000000000);
  if (pot_u_mul_ok(rp, chi) == 0) {
    return 0;
  }
  tmp = (rp * chi) / 1000000000;
  if (pot_u_sub_ok(tmp, chi) == 0) {
    return 0;
  }
  delta = tmp - chi;
  if (pot_u_mul_ok(pie_total, delta) == 0) {
    return 0;
  }
  return 1;
}

int pot_join_ok(int now_ts, int rho, int chi, int pie_user, int pie_total, int wad) {
  if (now_ts != rho) {
    return 0;
  }
  if (chi < 0) {
    return 0;
  }
  if (wad < 0) {
    return 0;
  }
  if (pot_u_mul_ok(chi, wad) == 0) {
    return 0;
  }
  if (pot_u_add_ok(pie_user, wad) == 0) {
    return 0;
  }
  if (pot_u_add_ok(pie_total, wad) == 0) {
    return 0;
  }
  return 1;
}

int pot_exit_ok(int chi, int pie_user, int pie_total, int wad) {
  if (chi < 0) {
    return 0;
  }
  if (wad < 0) {
    return 0;
  }
  if (pot_u_mul_ok(chi, wad) == 0) {
    return 0;
  }
  if (pot_u_sub_ok(pie_user, wad) == 0) {
    return 0;
  }
  if (pot_u_sub_ok(pie_total, wad) == 0) {
    return 0;
  }
  return 1;
}
