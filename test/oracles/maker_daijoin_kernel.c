/*
 * Pointer-free C11 kernel of uint64-scale DaiJoin.join/exit.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed * is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss join.sol (AGPL, hash-pinned elsewhere).
 */
int dj_u_mul_ok(int a, int b) {
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

int dj_u_add_ok(int a, int b) {
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

int dj_u_sub_ok(int a, int b) {
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

int dj_join_ok(int from_dai, int to_dai, int token, int wad) {
  int rad;
  if (from_dai < 0) {
    return 0;
  }
  if (to_dai < 0) {
    return 0;
  }
  if (token < 0) {
    return 0;
  }
  if (wad < 0) {
    return 0;
  }
  if (dj_u_mul_ok(1000000000, wad) == 0) {
    return 0;
  }
  rad = 1000000000 * wad;
  if (dj_u_sub_ok(from_dai, rad) == 0) {
    return 0;
  }
  if (dj_u_add_ok(to_dai, rad) == 0) {
    return 0;
  }
  if (dj_u_sub_ok(token, wad) == 0) {
    return 0;
  }
  return 1;
}

int dj_exit_ok(int live, int from_dai, int to_dai, int token, int wad) {
  int rad;
  if (live != 1) {
    return 0;
  }
  if (from_dai < 0) {
    return 0;
  }
  if (to_dai < 0) {
    return 0;
  }
  if (token < 0) {
    return 0;
  }
  if (wad < 0) {
    return 0;
  }
  if (dj_u_mul_ok(1000000000, wad) == 0) {
    return 0;
  }
  rad = 1000000000 * wad;
  if (dj_u_sub_ok(from_dai, rad) == 0) {
    return 0;
  }
  if (dj_u_add_ok(to_dai, rad) == 0) {
    return 0;
  }
  if (dj_u_add_ok(token, wad) == 0) {
    return 0;
  }
  return 1;
}
