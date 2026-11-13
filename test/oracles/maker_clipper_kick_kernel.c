/*
 * Pointer-free C11 kernel of uint64-scale Clipper.kick top+coin.
 * Eligible for lin_from_c (no *, ->, struct, union, float, goto, __int128).
 * Naive signed * is uint64-scale only; production oracle uses unsigned wrap.
 * Original C; does not copy makerdao/dss clip.sol (AGPL, hash-pinned elsewhere).
 */
int ck_u_mul_ok(int a, int b) {
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

int ck_u_add_ok(int a, int b) {
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

int ck_kick_ok(int tab, int lot, int usr, int kicks, int val, int par, int buf, int tip, int chip, int auth, int stopped) {
  int prod1;
  int feed;
  int top;
  int go;
  int w;
  if (auth != 1) {
    return 0;
  }
  if (stopped >= 1) {
    return 0;
  }
  if (tab < 1) {
    return 0;
  }
  if (lot < 1) {
    return 0;
  }
  if (usr != 1) {
    return 0;
  }
  if (ck_u_add_ok(kicks, 1) == 0) {
    return 0;
  }
  if (par < 1) {
    return 0;
  }
  if (ck_u_mul_ok(val, 1000) == 0) {
    return 0;
  }
  prod1 = val * 1000;
  if (ck_u_mul_ok(prod1, 1000000) == 0) {
    return 0;
  }
  feed = (prod1 * 1000000) / par;
  if (ck_u_mul_ok(feed, buf) == 0) {
    return 0;
  }
  top = (feed * buf) / 1000000;
  if (top < 1) {
    return 0;
  }
  go = 0;
  if (tip > 0) {
    go = 1;
  }
  if (chip > 0) {
    go = 1;
  }
  if (go == 1) {
    if (ck_u_mul_ok(tab, chip) == 0) {
      return 0;
    }
    w = (tab * chip) / 1000;
    if (ck_u_add_ok(tip, w) == 0) {
      return 0;
    }
  }
  return 1;
}
