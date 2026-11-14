/*
 * Pointer-free C11 kernel of uint64-scale Maker End cage(ilk)/skim/flow.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Original C; does not copy end.sol (hash-pinned elsewhere).
 * Parameter names avoid host pip_read()/vat_grab()/vat_ilks() lifts.
 */
int len_u_lt(int a, int b) {
  if (a < 0) {
    if (b >= 0) {
      return 0;
    }
  }
  if (a >= 0) {
    if (b < 0) {
      return 1;
    }
  }
  if (a < b) {
    return 1;
  }
  return 0;
}

int len_add_ok(int x, int y) {
  int z;
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  z = x + y;
  if (z < 0) {
    return 0;
  }
  if (len_u_lt(z, x) == 1) {
    return 0;
  }
  return 1;
}

int len_sub_ok(int x, int y) {
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  if (len_u_lt(x, y) == 1) {
    return 0;
  }
  return 1;
}

int len_mul_ok(int x, int y) {
  int z;
  if (x < 0) {
    return 0;
  }
  if (y < 0) {
    return 0;
  }
  if (y == 0) {
    return 1;
  }
  if (x == 0) {
    return 1;
  }
  z = x * y;
  if (z < 0) {
    return 0;
  }
  if (z / y != x) {
    return 0;
  }
  return 1;
}

int len_add(int x, int y) {
  if (len_add_ok(x, y) == 0) {
    return 0;
  }
  return x + y;
}

int len_sub(int x, int y) {
  if (len_sub_ok(x, y) == 0) {
    return 0;
  }
  return x - y;
}

int len_rmul(int x, int y) {
  if (len_mul_ok(x, y) == 0) {
    return 0;
  }
  return (x * y) / 1000000000;
}

int len_wdiv(int x, int y) {
  if (y <= 0) {
    return 0;
  }
  if (len_mul_ok(x, 1000000) == 0) {
    return 0;
  }
  return (x * 1000000) / y;
}

int len_min(int x, int y) {
  if (len_u_lt(x, y) == 1) {
    return x;
  }
  return y;
}

int len_cage_tag(int live, int tag_prev, int par, int pip) {
  if (live != 0) {
    return 0;
  }
  if (tag_prev != 0) {
    return 0;
  }
  if (par < 0) {
    return 0;
  }
  if (pip <= 0) {
    return 0;
  }
  return len_wdiv(par, pip);
}

int len_skim_owe_ok(int art, int rate, int tag) {
  int d;
  if (art < 0) {
    return 0;
  }
  if (rate < 0) {
    return 0;
  }
  if (tag <= 0) {
    return 0;
  }
  if (len_mul_ok(art, rate) == 0) {
    return 0;
  }
  d = (art * rate) / 1000000000;
  if (len_mul_ok(d, tag) == 0) {
    return 0;
  }
  return 1;
}

int len_skim_owe(int art, int rate, int tag) {
  int d;
  if (len_skim_owe_ok(art, rate, tag) == 0) {
    return 0;
  }
  d = (art * rate) / 1000000000;
  return (d * tag) / 1000000000;
}

int len_skim_wad(int ink, int owe) {
  if (ink < 0) {
    return 0;
  }
  if (owe < 0) {
    return 0;
  }
  return len_min(ink, owe);
}

int len_skim_gap_next(int gap, int owe, int wad) {
  int d;
  d = len_sub(owe, wad);
  return len_add(gap, d);
}

int len_flow_fix(int art_ilk, int rate, int tag, int gap, int debt) {
  int wad;
  int left;
  int num;
  int den;
  if (debt <= 0) {
    return 0;
  }
  if (len_skim_owe_ok(art_ilk, rate, tag) == 0) {
    return 0;
  }
  wad = len_skim_owe(art_ilk, rate, tag);
  if (len_sub_ok(wad, gap) == 0) {
    return 0;
  }
  left = wad - gap;
  if (len_mul_ok(left, 1000000000) == 0) {
    return 0;
  }
  num = left * 1000000000;
  den = debt / 1000000000;
  if (den <= 0) {
    return 0;
  }
  return num / den;
}

int len_cash_out(int wad, int fix) {
  return len_rmul(wad, fix);
}
